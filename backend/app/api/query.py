import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_accessible_doc_ids, get_current_user
from app.core.config import get_settings
from app.db.models import QueryLog, User
from app.db.session import get_db
from app.embeddings.azure_embeddings import embed_text
from app.embeddings.sparse_embeddings import embed_text as sparse_embed_text
from app.evaluation.metrics import EvaluationResult, evaluate
from app.generation.generator import format_source_locator, generate_answer
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


@router.post("/query", response_model=QueryResponse)
def query(
    request: QueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QueryResponse:
    settings = get_settings()
    top_k = request.top_k or settings.default_top_k
    total_start = time.perf_counter()

    accessible_doc_ids = get_accessible_doc_ids(current_user, db)
    if not accessible_doc_ids:
        log = QueryLog(
            user_id=current_user.id,
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
            answer=log.answer,
            sources=[],
            rewritten_query=request.question,
            input_tokens=0,
            output_tokens=0,
        )

    rewritten = rewrite_query(request.question)

    # --- Retrieval (dense-only + sparse-only for the debug trace, plus the
    # fused hybrid search that's actually used downstream) ---
    retrieval_start = time.perf_counter()
    dense_vector = embed_text(rewritten)
    sparse_vector = sparse_embed_text(rewritten)
    debug_dense = search_dense(dense_vector, top_k=settings.debug_display_k, allowed_doc_ids=accessible_doc_ids)
    debug_sparse = search_sparse(sparse_vector, top_k=settings.debug_display_k, allowed_doc_ids=accessible_doc_ids)
    candidates = search_hybrid(
        dense_vector,
        sparse_vector,
        fetch_k=settings.hybrid_fetch_k,
        allowed_doc_ids=accessible_doc_ids,
    )
    latency_retrieval_ms = int((time.perf_counter() - retrieval_start) * 1000)

    # --- Rerank ---
    rerank_start = time.perf_counter()
    reranked = rerank(rewritten, candidates, top_k=top_k)
    latency_rerank_ms = int((time.perf_counter() - rerank_start) * 1000)

    # --- Generation (original question — the rewrite is for retrieval only) ---
    llm_start = time.perf_counter()
    result = generate_answer(request.question, reranked)
    latency_llm_ms = int((time.perf_counter() - llm_start) * 1000)

    # --- Evaluation ---
    eval_start = time.perf_counter()
    eval_result = (
        evaluate(request.question, result.answer, reranked) if request.evaluate else EvaluationResult()
    )
    latency_eval_ms = int((time.perf_counter() - eval_start) * 1000)

    latency_total_ms = int((time.perf_counter() - total_start) * 1000)

    sources = [
        SourceOut(index=s.index, filename=s.filename, locator=s.locator, text=s.text) for s in result.sources
    ]

    log = QueryLog(
        user_id=current_user.id,
        question=request.question,
        rewritten_query=rewritten,
        answer=result.answer,
        retrieved_dense=[_chunk_debug_dict(c) for c in debug_dense],
        retrieved_sparse=[_chunk_debug_dict(c) for c in debug_sparse],
        fused_candidates=[_chunk_debug_dict(c) for c in candidates],
        reranked_chunks=[_chunk_debug_dict(c) for c in reranked],
        sources=[s.model_dump() for s in sources],
        model=settings.azure_openai_chat_deployment,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        faithfulness_score=eval_result.faithfulness,
        context_precision_score=eval_result.context_precision,
        answer_relevance_score=eval_result.answer_relevance,
        eval_passed=eval_result.passed,
        eval_detail=eval_result.detail,
        latency_retrieval_ms=latency_retrieval_ms,
        latency_rerank_ms=latency_rerank_ms,
        latency_llm_ms=latency_llm_ms,
        latency_eval_ms=latency_eval_ms,
        latency_total_ms=latency_total_ms,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return QueryResponse(
        query_id=log.id,
        answer=result.answer,
        sources=sources,
        rewritten_query=rewritten,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
