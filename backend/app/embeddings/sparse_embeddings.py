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


def warm_up() -> None:
    """Forces the model to download/initialize now, at app startup, rather
    than silently during a real user's first upload or chat message —
    Railway's container filesystem is ephemeral, so this download would
    otherwise happen fresh after every redeploy at an unpredictable moment.
    """
    _model()


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
