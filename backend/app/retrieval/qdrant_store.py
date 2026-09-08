"""Qdrant collection management and dense-vector search.

The collection is created with both a `dense` and a `sparse` named vector
up front, even though v1 only ever populates/searches `dense` — Qdrant
can't cheaply add a new named vector to an existing collection later, and
v2's hybrid (BM25) search needs `sparse` to already exist.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.chunking.chunker import Chunk
from app.core.config import get_settings
from app.embeddings.azure_embeddings import get_embedding_dimension


@lru_cache
def get_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


def ensure_collection() -> None:
    """Idempotently create the collection if it doesn't exist yet."""
    settings = get_settings()
    client = get_client()

    existing = {c.name for c in client.get_collections().collections}
    if settings.qdrant_collection_name in existing:
        return

    client.create_collection(
        collection_name=settings.qdrant_collection_name,
        vectors_config={
            "dense": qmodels.VectorParams(
                size=get_embedding_dimension(),
                distance=qmodels.Distance.COSINE,
            ),
        },
        sparse_vectors_config={
            # IDF modifier: fastembed's BM25 encoder stores raw term
            # frequencies; this tells Qdrant to apply corpus-wide IDF
            # weighting at query time, which is what makes it BM25 rather
            # than plain term-frequency matching.
            "sparse": qmodels.SparseVectorParams(
                modifier=qmodels.Modifier.IDF,
            ),
        },
    )


@dataclass
class RetrievedChunk:
    chunk_id: str
    score: float
    text: str
    doc_id: str
    filename: str
    source_format: str
    heading_path: list[str]
    page_start: int | None
    page_end: int | None
    line_start: int | None
    line_end: int | None
    row_start: int | None
    row_end: int | None


def _chunk_payload(chunk: Chunk) -> dict:
    return {
        "doc_id": chunk.doc_id,
        "filename": chunk.filename,
        "source_format": chunk.source_format,
        "chunk_index": chunk.chunk_index,
        "text": chunk.text,
        "heading_path": chunk.heading_path,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "line_start": chunk.line_start,
        "line_end": chunk.line_end,
        "row_start": chunk.row_start,
        "row_end": chunk.row_end,
        "ocr_generated": chunk.ocr_generated,
    }


def upsert_chunks(
    chunks: list[Chunk],
    dense_vectors: list[list[float]],
    sparse_vectors: list[qmodels.SparseVector],
) -> None:
    settings = get_settings()
    client = get_client()

    points = [
        qmodels.PointStruct(
            id=str(uuid.uuid4()),
            vector={"dense": dense, "sparse": sparse},
            payload=_chunk_payload(chunk),
        )
        for chunk, dense, sparse in zip(chunks, dense_vectors, sparse_vectors, strict=True)
    ]
    if points:
        client.upsert(collection_name=settings.qdrant_collection_name, points=points)


def _to_retrieved_chunk(point) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=str(point.id),
        score=point.score,
        text=point.payload["text"],
        doc_id=point.payload["doc_id"],
        filename=point.payload["filename"],
        source_format=point.payload["source_format"],
        heading_path=point.payload.get("heading_path", []),
        page_start=point.payload.get("page_start"),
        page_end=point.payload.get("page_end"),
        line_start=point.payload.get("line_start"),
        line_end=point.payload.get("line_end"),
        row_start=point.payload.get("row_start"),
        row_end=point.payload.get("row_end"),
    )


def search_dense(query_vector: list[float], top_k: int) -> list[RetrievedChunk]:
    settings = get_settings()
    client = get_client()

    results = client.query_points(
        collection_name=settings.qdrant_collection_name,
        query=query_vector,
        using="dense",
        limit=top_k,
        with_payload=True,
    ).points

    return [_to_retrieved_chunk(point) for point in results]


def search_hybrid(
    dense_vector: list[float],
    sparse_vector: qmodels.SparseVector,
    fetch_k: int,
) -> list[RetrievedChunk]:
    """Dense + sparse (BM25) search fused server-side via Reciprocal Rank
    Fusion, in one Qdrant Query API call.
    """
    settings = get_settings()
    client = get_client()

    results = client.query_points(
        collection_name=settings.qdrant_collection_name,
        prefetch=[
            qmodels.Prefetch(query=dense_vector, using="dense", limit=fetch_k),
            qmodels.Prefetch(query=sparse_vector, using="sparse", limit=fetch_k),
        ],
        query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
        limit=fetch_k,
        with_payload=True,
    ).points

    return [_to_retrieved_chunk(point) for point in results]


def delete_document(doc_id: str) -> None:
    settings = get_settings()
    client = get_client()
    client.delete(
        collection_name=settings.qdrant_collection_name,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="doc_id", match=qmodels.MatchValue(value=doc_id))]
            )
        ),
    )
