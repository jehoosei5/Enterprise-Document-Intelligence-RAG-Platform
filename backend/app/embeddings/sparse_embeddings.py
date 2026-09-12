"""Local BM25 sparse-vector encoding via fastembed — no external API/key.
Mirrors azure_embeddings.py's shape so callers treat dense/sparse similarly.
"""

from __future__ import annotations

from functools import lru_cache

from fastembed import SparseTextEmbedding
from qdrant_client.http import models as qmodels

_MODEL_NAME = "Qdrant/bm25"


@lru_cache
def _model() -> SparseTextEmbedding:
    return SparseTextEmbedding(model_name=_MODEL_NAME)


def embed_texts(texts: list[str]) -> list[qmodels.SparseVector]:
    if not texts:
        return []

    embeddings = _model().embed(texts)
    return [
        qmodels.SparseVector(indices=e.indices.tolist(), values=e.values.tolist())
        for e in embeddings
    ]


def embed_text(text: str) -> qmodels.SparseVector:
    return embed_texts([text])[0]
