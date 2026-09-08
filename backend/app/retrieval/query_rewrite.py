"""Single-turn query rewriting: clean up the raw user question into a
better search query before embedding it. Not conversation-aware — resolving
multi-turn follow-ups is v4b's job (conversation memory), not this.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from openai import AzureOpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Rewrite the user's question into a clear, standalone search query for "
    "a document retrieval system. Fix typos, expand abbreviations/acronyms, "
    "and make implicit intent explicit. Preserve the original meaning "
    "exactly — do not answer the question, add information, or change what "
    "is being asked. Reply with ONLY the rewritten query, no explanation."
)


@lru_cache
def _client() -> AzureOpenAI:
    settings = get_settings()
    return AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )


def rewrite_query(question: str) -> str:
    """Returns the rewritten query, or the original question unchanged if
    the rewrite call fails for any reason (fail open, not closed).
    """
    settings = get_settings()
    try:
        response = _client().chat.completions.create(
            model=settings.azure_openai_chat_deployment,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            temperature=0,
        )
        rewritten = (response.choices[0].message.content or "").strip()
        return rewritten or question
    except Exception:
        logger.warning("Query rewrite failed; falling back to original question", exc_info=True)
        return question
