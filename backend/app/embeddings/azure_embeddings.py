"""Thin wrapper around the Azure OpenAI embeddings endpoint."""

from __future__ import annotations

from functools import lru_cache

from openai import AzureOpenAI
from tenacity import retry, stop_after_attempt, wait_random_exponential

from app.core.config import get_settings

# Azure OpenAI embedding calls accept a batch of inputs; keep batches modest
# to stay well under request size/token limits.
MAX_BATCH_SIZE = 100


@lru_cache
def _client() -> AzureOpenAI:
    settings = get_settings()
    return AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )


@retry(wait=wait_random_exponential(min=1, max=20), stop=stop_after_attempt(5))
def _embed_batch(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    response = _client().embeddings.create(
        model=settings.azure_openai_embedding_deployment,
        input=texts,
    )
    # Azure returns results in the same order as the input.
    return [item.embedding for item in response.data]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts, batching to respect request-size limits."""
    if not texts:
        return []

    vectors: list[list[float]] = []
    for start in range(0, len(texts), MAX_BATCH_SIZE):
        batch = texts[start:start + MAX_BATCH_SIZE]
        vectors.extend(_embed_batch(batch))
    return vectors


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]


@lru_cache
def get_embedding_dimension() -> int:
    """Auto-detect the embedding dimension by embedding a throwaway string,
    rather than trusting a hardcoded env var that can drift out of sync with
    whatever model the AZURE_OPENAI_EMBEDDING_DEPLOYMENT actually points at.
    """
    return len(embed_text("dimension probe"))
