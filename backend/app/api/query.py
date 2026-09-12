import json
import time
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_accessible_doc_ids, get_current_user
from app.core.config import get_settings
from app.db.models import Conversation, QueryLog, User
from app.db.session import SessionLocal, get_db
from app.embeddings.azure_embeddings import embed_text
from app.embeddings.sparse_embeddings import embed_text as sparse_embed_text
from app.evaluation.metrics import EvaluationResult, evaluate
from app.generation.generator import (
    StreamUsage,
    format_source_locator,
    generate_answer,
    generate_chat_reply,
    generate_conversation_title,
    parse_citations,
    stream_answer,
    stream_chat_reply,
)
from app.retrieval.qdrant_store import RetrievedChunk, search_dense, search_hybrid, search_sparse
from app.retrieval.query_rewrite import rewrite_query
from app.retrieval.reranker import rerank
from app.schemas.query import QueryRequest, QueryResponse, SourceOut

router = APIRouter(tags=["query"])

# Shared by every request for the independent-I/O parallelization in
# _run_retrieval_pipeline (dense/sparse embed, and — when include_debug —
# the dense/sparse/hybrid Qdrant searches). Every client involved (Azure
# OpenAI, Qdrant, Cohere) is the sync SDK, hence threads, not asyncio.
_POOL = ThreadPoolExecutor(max_workers=4)


def _chunk_debug_dict(chunk: RetrievedChunk) -> dict:
    return {
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "filename": chunk.filename,
        "locator": format_source_locator(chunk),
        "score": chunk.score,
    }


def _source_dict(s) -> dict:
    return {"index": s.index, "filename": s.filename, "locator": s.locator, "text": s.text}


def _get_or_create_conversation(request: QueryRequest, db: Session, current_user: User) -> Conversation:
    if request.conversation_id:
        conversation = db.get(Conversation, request.conversation_id)
        if conversation is None or conversation.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation

    conversation = Conversation(user_id=current_user.id, title=request.question[:200])
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def _get_history(conversation: Conversation, db: Session, settings) -> list[dict]:
    rows = (
        db.query(QueryLog)
        .filter(QueryLog.conversation_id == conversation.id)
        .order_by(QueryLog.created_at.desc())
        .limit(settings.conversation_history_turns)
        .all()
    )
    rows.reverse()  # oldest first, for the rewrite prompt
    return [{"question": r.question, "answer": r.answer} for r in rows]


def _generate_and_save_conversation_title(conversation_id: str, question: str, answer: str) -> None:
    """Runs after the response has already gone out (a BackgroundTask for
    /query, called inline post-stream for /query/stream — either way,
    strictly after what the user is waiting on). Opens its own DB session
    rather than reusing the request-scoped one, which FastAPI may already
    have closed by the time a BackgroundTask body actually runs.
    """
    title = generate_conversation_title(question, answer)
    if not title:
        return  # fail open — the question[:200] placeholder stands.

    db = SessionLocal()
    try:
        conversation = db.get(Conversation, conversation_id)
        if conversation is not None:
            conversation.title = title[:200]
            db.commit()
    finally:
        db.close()


@dataclass
class PipelineResult:
    rewritten: str
    debug_dense: list[RetrievedChunk]
    debug_sparse: list[RetrievedChunk]
    candidates: list[RetrievedChunk]
    reranked: list[RetrievedChunk]
    latency_retrieval_ms: int
    latency_rerank_ms: int


def _run_retrieval_pipeline(
    rewritten: str,
    accessible_doc_ids: list[str],
    top_k: int,
    settings,
    include_debug: bool,
) -> PipelineResult:
    """Shared by /query and /query/stream: embed -> dense/sparse debug
    retrieval (only when include_debug — otherwise those two Qdrant calls
    are skipped entirely, they exist purely for the debug-trace view) +
    fused hybrid -> rerank. Rewriting happens in the caller (which also
    decides needs_retrieval before this is ever invoked). Independent I/O
    (the two embeds; the up-to-three Qdrant searches) runs concurrently via
    the shared thread pool.
    """
    retrieval_start = time.perf_counter()

    dense_future = _POOL.submit(embed_text, rewritten)
    sparse_future = _POOL.submit(sparse_embed_text, rewritten)
    dense_vector = dense_future.result()
    sparse_vector = sparse_future.result()

    if include_debug:
        debug_dense_future = _POOL.submit(
            search_dense, dense_vector, top_k=settings.debug_display_k, allowed_doc_ids=accessible_doc_ids
        )
        debug_sparse_future = _POOL.submit(
            search_sparse, sparse_vector, top_k=settings.debug_display_k, allowed_doc_ids=accessible_doc_ids
        )
        candidates_future = _POOL.submit(
            search_hybrid,
            dense_vector,
            sparse_vector,
            fetch_k=settings.hybrid_fetch_k,
            allowed_doc_ids=accessible_doc_ids,
        )
        debug_dense = debug_dense_future.result()
        debug_sparse = debug_sparse_future.result()
        candidates = candidates_future.result()
    else:
        debug_dense = []
        debug_sparse = []
        candidates = search_hybrid(
            dense_vector, sparse_vector, fetch_k=settings.hybrid_fetch_k, allowed_doc_ids=accessible_doc_ids
        )

    latency_retrieval_ms = int((time.perf_counter() - retrieval_start) * 1000)

    rerank_start = time.perf_counter()
    reranked = rerank(rewritten, candidates, top_k=top_k)
    latency_rerank_ms = int((time.perf_counter() - rerank_start) * 1000)

    return PipelineResult(
        rewritten, debug_dense, debug_sparse, candidates, reranked, latency_retrieval_ms, latency_rerank_ms
    )


@router.post("/query", response_model=QueryResponse)
def query(
    request: QueryRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QueryResponse:
    settings = get_settings()
    top_k = request.top_k or settings.default_top_k
    total_start = time.perf_counter()
    is_new_conversation = not request.conversation_id

    conversation = _get_or_create_conversation(request, db, current_user)
    accessible_doc_ids = get_accessible_doc_ids(current_user, db)

    if request.document_id:
        if request.document_id not in accessible_doc_ids:
            # 404, not 403 — same reasoning as the document endpoints.
            raise HTTPException(status_code=404, detail="Document not found")
        accessible_doc_ids = [request.document_id]

    if not accessible_doc_ids:
        log = QueryLog(
            user_id=current_user.id,
            conversation_id=conversation.id,
            question=request.question,
            rewritten_query=request.question,
            answer="You don't have access to any documents yet.",
            model=settings.azure_openai_chat_deployment,
            scoped_document_id=request.document_id,
            latency_total_ms=int((time.perf_counter() - total_start) * 1000),
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        if is_new_conversation:
            background_tasks.add_task(
                _generate_and_save_conversation_title, conversation.id, request.question, log.answer
            )
        return QueryResponse(
            query_id=log.id,
            conversation_id=conversation.id,
            answer=log.answer,
            sources=[],
            rewritten_query=request.question,
            input_tokens=0,
            output_tokens=0,
        )

    history = _get_history(conversation, db, settings)
    rewrite_result = rewrite_query(request.question, history=history)

    if not rewrite_result.needs_retrieval:
        # Conversational message (greeting, thanks, small talk, etc.) — the
        # model's own judgment call, not a keyword check. Skip retrieval/
        # rerank/citations entirely; a plain chat reply instead.
        llm_start = time.perf_counter()
        chat_result = generate_chat_reply(request.question, history=history)
        latency_llm_ms = int((time.perf_counter() - llm_start) * 1000)
        latency_total_ms = int((time.perf_counter() - total_start) * 1000)

        log = QueryLog(
            user_id=current_user.id,
            conversation_id=conversation.id,
            question=request.question,
            rewritten_query=rewrite_result.rewritten_query,
            answer=chat_result.answer,
            scoped_document_id=request.document_id,
            model=settings.azure_openai_chat_deployment,
            input_tokens=chat_result.input_tokens,
            output_tokens=chat_result.output_tokens,
            latency_llm_ms=latency_llm_ms,
            latency_total_ms=latency_total_ms,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        if is_new_conversation:
            background_tasks.add_task(
                _generate_and_save_conversation_title, conversation.id, request.question, chat_result.answer
            )
        return QueryResponse(
            query_id=log.id,
            conversation_id=conversation.id,
            answer=chat_result.answer,
            sources=[],
            rewritten_query=rewrite_result.rewritten_query,
            input_tokens=chat_result.input_tokens,
            output_tokens=chat_result.output_tokens,
        )

    pipeline = _run_retrieval_pipeline(
        rewrite_result.rewritten_query, accessible_doc_ids, top_k, settings, include_debug=request.evaluate
    )

    llm_start = time.perf_counter()
    result = generate_answer(request.question, pipeline.reranked)
    latency_llm_ms = int((time.perf_counter() - llm_start) * 1000)

    eval_start = time.perf_counter()
    eval_result = (
        evaluate(request.question, result.answer, pipeline.reranked)
        if request.evaluate
        else EvaluationResult()
    )
    latency_eval_ms = int((time.perf_counter() - eval_start) * 1000)

    latency_total_ms = int((time.perf_counter() - total_start) * 1000)

    sources = [SourceOut(**_source_dict(s)) for s in result.sources]

    log = QueryLog(
        user_id=current_user.id,
        conversation_id=conversation.id,
        question=request.question,
        rewritten_query=pipeline.rewritten,
        answer=result.answer,
        scoped_document_id=request.document_id,
        retrieved_dense=[_chunk_debug_dict(c) for c in pipeline.debug_dense],
        retrieved_sparse=[_chunk_debug_dict(c) for c in pipeline.debug_sparse],
        fused_candidates=[_chunk_debug_dict(c) for c in pipeline.candidates],
        reranked_chunks=[_chunk_debug_dict(c) for c in pipeline.reranked],
        sources=[_source_dict(s) for s in sources],
        model=settings.azure_openai_chat_deployment,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        faithfulness_score=eval_result.faithfulness,
        context_precision_score=eval_result.context_precision,
        answer_relevance_score=eval_result.answer_relevance,
        eval_passed=eval_result.passed,
        eval_detail=eval_result.detail,
        latency_retrieval_ms=pipeline.latency_retrieval_ms,
        latency_rerank_ms=pipeline.latency_rerank_ms,
        latency_llm_ms=latency_llm_ms,
        latency_eval_ms=latency_eval_ms,
        latency_total_ms=latency_total_ms,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    if is_new_conversation:
        background_tasks.add_task(
            _generate_and_save_conversation_title, conversation.id, request.question, result.answer
        )

    return QueryResponse(
        query_id=log.id,
        conversation_id=conversation.id,
        answer=result.answer,
        sources=sources,
        rewritten_query=pipeline.rewritten,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


@router.post("/query/stream")
def query_stream(
    request: QueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    settings = get_settings()
    top_k = request.top_k or settings.default_top_k
    total_start = time.perf_counter()
    is_new_conversation = not request.conversation_id

    conversation = _get_or_create_conversation(request, db, current_user)
    accessible_doc_ids = get_accessible_doc_ids(current_user, db)

    def event_stream() -> Generator[str, None, None]:
        if not accessible_doc_ids:
            answer = "You don't have access to any documents yet."
            log = QueryLog(
                user_id=current_user.id,
                conversation_id=conversation.id,
                question=request.question,
                rewritten_query=request.question,
                answer=answer,
                model=settings.azure_openai_chat_deployment,
                latency_total_ms=int((time.perf_counter() - total_start) * 1000),
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            if is_new_conversation:
                _generate_and_save_conversation_title(conversation.id, request.question, answer)
            yield f"data: {json.dumps({'delta': answer})}\n\n"
            yield f"data: {json.dumps({'event': 'done', 'query_id': log.id, 'conversation_id': conversation.id, 'sources': [], 'input_tokens': 0, 'output_tokens': 0})}\n\n"
            return

        history = _get_history(conversation, db, settings)
        rewrite_result = rewrite_query(request.question, history=history)

        if not rewrite_result.needs_retrieval:
            llm_start = time.perf_counter()
            usage = StreamUsage()
            full_text = ""
            for delta in stream_chat_reply(request.question, history, usage):
                full_text += delta
                yield f"data: {json.dumps({'delta': delta})}\n\n"
            latency_llm_ms = int((time.perf_counter() - llm_start) * 1000)
            latency_total_ms = int((time.perf_counter() - total_start) * 1000)

            log = QueryLog(
                user_id=current_user.id,
                conversation_id=conversation.id,
                question=request.question,
                rewritten_query=rewrite_result.rewritten_query,
                answer=full_text,
                model=settings.azure_openai_chat_deployment,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                latency_llm_ms=latency_llm_ms,
                latency_total_ms=latency_total_ms,
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            if is_new_conversation:
                _generate_and_save_conversation_title(conversation.id, request.question, full_text)

            final_event = {
                "event": "done",
                "query_id": log.id,
                "conversation_id": conversation.id,
                "rewritten_query": rewrite_result.rewritten_query,
                "sources": [],
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            }
            yield f"data: {json.dumps(final_event)}\n\n"
            return

        pipeline = _run_retrieval_pipeline(
            rewrite_result.rewritten_query, accessible_doc_ids, top_k, settings, include_debug=request.evaluate
        )

        llm_start = time.perf_counter()
        usage = StreamUsage()
        full_text = ""
        for delta in stream_answer(request.question, pipeline.reranked, usage):
            full_text += delta
            yield f"data: {json.dumps({'delta': delta})}\n\n"
        latency_llm_ms = int((time.perf_counter() - llm_start) * 1000)

        sources = parse_citations(full_text, pipeline.reranked)

        eval_start = time.perf_counter()
        eval_result = (
            evaluate(request.question, full_text, pipeline.reranked)
            if request.evaluate
            else EvaluationResult()
        )
        latency_eval_ms = int((time.perf_counter() - eval_start) * 1000)
        latency_total_ms = int((time.perf_counter() - total_start) * 1000)

        log = QueryLog(
            user_id=current_user.id,
            conversation_id=conversation.id,
            question=request.question,
            rewritten_query=pipeline.rewritten,
            answer=full_text,
            retrieved_dense=[_chunk_debug_dict(c) for c in pipeline.debug_dense],
            retrieved_sparse=[_chunk_debug_dict(c) for c in pipeline.debug_sparse],
            fused_candidates=[_chunk_debug_dict(c) for c in pipeline.candidates],
            reranked_chunks=[_chunk_debug_dict(c) for c in pipeline.reranked],
            sources=[_source_dict(s) for s in sources],
            model=settings.azure_openai_chat_deployment,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            faithfulness_score=eval_result.faithfulness,
            context_precision_score=eval_result.context_precision,
            answer_relevance_score=eval_result.answer_relevance,
            eval_passed=eval_result.passed,
            eval_detail=eval_result.detail,
            latency_retrieval_ms=pipeline.latency_retrieval_ms,
            latency_rerank_ms=pipeline.latency_rerank_ms,
            latency_llm_ms=latency_llm_ms,
            latency_eval_ms=latency_eval_ms,
            latency_total_ms=latency_total_ms,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        if is_new_conversation:
            _generate_and_save_conversation_title(conversation.id, request.question, full_text)

        final_event = {
            "event": "done",
            "query_id": log.id,
            "conversation_id": conversation.id,
            "rewritten_query": pipeline.rewritten,
            "sources": [_source_dict(s) for s in sources],
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "faithfulness_score": eval_result.faithfulness,
            "context_precision_score": eval_result.context_precision,
            "answer_relevance_score": eval_result.answer_relevance,
            "eval_passed": eval_result.passed,
        }
        yield f"data: {json.dumps(final_event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
