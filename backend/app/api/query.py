from fastapi import APIRouter

from app.core.config import get_settings
from app.embeddings.azure_embeddings import embed_text
from app.generation.generator import generate_answer
from app.retrieval.qdrant_store import search_dense
from app.schemas.query import QueryRequest, QueryResponse, SourceOut

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    settings = get_settings()
    top_k = request.top_k or settings.default_top_k

    query_vector = embed_text(request.question)
    chunks = search_dense(query_vector, top_k=top_k)
    result = generate_answer(request.question, chunks)

    return QueryResponse(
        answer=result.answer,
        sources=[
            SourceOut(index=s.index, filename=s.filename, locator=s.locator, text=s.text)
            for s in result.sources
        ],
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
