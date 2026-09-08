"""Cohere cross-encoder reranking of fused hybrid-search candidates down to
the final top-k. Fails open: if the Cohere call errors, falls back to the
fused (unreranked) order truncated to top_k rather than failing /query.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from functools import lru_cache

import cohere

from app.core.config import get_settings
from app.retrieval.qdrant_store import RetrievedChunk

logger = logging.getLogger(__name__)


@lru_cache
def _client() -> cohere.Client:
    settings = get_settings()
    return cohere.Client(api_key=settings.cohere_api_key)


def rerank(query: str, chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
    if not chunks:
        return []

    settings = get_settings()
    try:
        response = _client().rerank(
            model=settings.cohere_rerank_model,
            query=query,
            documents=[c.text for c in chunks],
            top_n=min(top_k, len(chunks)),
        )
        return [
            replace(chunks[r.index], score=r.relevance_score)
            for r in response.results
        ]
    except Exception:
        logger.warning("Rerank failed; falling back to fused order", exc_info=True)
        return chunks[:top_k]
