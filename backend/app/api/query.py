import json
import time
from collections.abc import Generator
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_accessible_doc_ids, get_current_user
from app.core.config import get_settings
from app.db.models import Conversation, QueryLog, User
from app.db.session import get_db
from app.embeddings.azure_embeddings import embed_text
from app.embeddings.sparse_embeddings import embed_text as sparse_embed_text
from app.evaluation.metrics import EvaluationResult, evaluate
from app.generation.generator import (
    StreamUsage,
    format_source_locator,
    generate_answer,
    parse_citations,
    stream_answer,
)
from app.retrieval.qdrant_store import RetrievedChunk, search_dense, search_hybrid, search_sparse
from app.retrieval.query_rewrite import rewrite_query
from app.retrieval.reranker import rerank
from app.schemas.query import QueryRequest, QueryResponse, SourceOut

router = APIRouter(tags=["query"])


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
    question: str,
    history: list[dict],
    accessible_doc_ids: list[str],
    top_k: int,
    settings,
) -> PipelineResult:
    """Shared by /query and /query/stream: rewrite -> dense/sparse debug
    retrieval + fused hybrid -> rerank. Only generation differs between the
    two endpoints.
    """
    rewritten = rewrite_query(question, history=history)

    retrieval_start = time.perf_counter()
    dense_vector = embed_text(rewritten)
    sparse_vector = sparse_embed_text(rewritten)
    debug_dense = search_dense(dense_vector, top_k=settings.debug_display_k, allowed_doc_ids=accessible_doc_ids)
    debug_sparse = search_sparse(sparse_vector, top_k=settings.debug_display_k, allowed_doc_ids=accessible_doc_ids)
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QueryResponse:
    settings = get_settings()
    top_k = request.top_k or settings.default_top_k
    total_start = time.perf_counter()

    conversation = _get_or_create_conversation(request, db, current_user)
    accessible_doc_ids = get_accessible_doc_ids(current_user, db)

    if not accessible_doc_ids:
        log = QueryLog(
            user_id=current_user.id,
            conversation_id=conversation.id,
            question=request.question,
            rewritten_query=request.question,
            answer="You don't have access to any documents yet.",
            model=settings.azure_openai_chat_deployment,
            latency_total_ms=int((time.perf_counter() - total_start) * 1000),
        )
        db.add(log)
        db.commit()
        db.refresh(log)
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
    pipeline = _run_retrieval_pipeline(request.question, history, accessible_doc_ids, top_k, settings)

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
            yield f"data: {json.dumps({'delta': answer})}\n\n"
            yield f"data: {json.dumps({'event': 'done', 'query_id': log.id, 'conversation_id': conversation.id, 'sources': [], 'input_tokens': 0, 'output_tokens': 0})}\n\n"
            return

        history = _get_history(conversation, db, settings)
        pipeline = _run_retrieval_pipeline(request.question, history, accessible_doc_ids, top_k, settings)

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
