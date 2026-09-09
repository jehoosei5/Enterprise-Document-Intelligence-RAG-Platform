from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_accessible_doc_ids, get_current_user
from app.core.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.embeddings.azure_embeddings import embed_text
from app.embeddings.sparse_embeddings import embed_text as sparse_embed_text
from app.generation.generator import generate_answer
from app.retrieval.qdrant_store import search_hybrid
from app.retrieval.query_rewrite import rewrite_query
from app.retrieval.reranker import rerank
from app.schemas.query import QueryRequest, QueryResponse, SourceOut

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
def query(
    request: QueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QueryResponse:
    settings = get_settings()
    top_k = request.top_k or settings.default_top_k

    accessible_doc_ids = get_accessible_doc_ids(current_user, db)
    if not accessible_doc_ids:
        return QueryResponse(
            answer="You don't have access to any documents yet.",
            sources=[],
            rewritten_query=request.question,
            input_tokens=0,
            output_tokens=0,
        )

    rewritten = rewrite_query(request.question)

    dense_vector = embed_text(rewritten)
    sparse_vector = sparse_embed_text(rewritten)
    candidates = search_hybrid(
        dense_vector,
        sparse_vector,
        fetch_k=settings.hybrid_fetch_k,
        allowed_doc_ids=accessible_doc_ids,
    )

    reranked = rerank(rewritten, candidates, top_k=top_k)

    # Generation prompt uses the user's original question — the rewrite is
    # for retrieval only, so the answer's framing matches what they asked.
    result = generate_answer(request.question, reranked)

    return QueryResponse(
        answer=result.answer,
        sources=[
            SourceOut(index=s.index, filename=s.filename, locator=s.locator, text=s.text)
            for s in result.sources
        ],
        rewritten_query=rewritten,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
