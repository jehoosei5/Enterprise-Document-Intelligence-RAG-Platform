"""Query rewriting: clean up the raw user question into a better search
query before embedding it. When prior conversation turns are given, also
resolves follow-ups (pronouns/ellipsis) against them — e.g. "what about for
managers?" -> "How many PTO days do managers get?".
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

_SYSTEM_PROMPT_WITH_HISTORY = (
    "Rewrite the user's latest question into a clear, standalone search "
    "query for a document retrieval system, using the conversation history "
    "to resolve any pronouns, ellipsis, or implicit references (e.g. "
    '"what about for managers?" after a question about PTO days becomes '
    '"How many PTO days do managers get?"). Fix typos and expand '
    "abbreviations/acronyms too. Preserve the question's intent exactly — "
    "do not answer it, add information, or change what is being asked. "
    "Reply with ONLY the rewritten standalone query, no explanation."
)


@lru_cache
def _client() -> AzureOpenAI:
    settings = get_settings()
    return AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )


def rewrite_query(question: str, history: list[dict] | None = None) -> str:
    """Returns the rewritten query, or the original question unchanged if
    the rewrite call fails for any reason (fail open, not closed).

    history, if given, is a list of {"question": ..., "answer": ...} prior
    turns (oldest first), already capped by the caller to the last N turns.
    """
    settings = get_settings()
    try:
        if history:
            history_block = "\n\n".join(
                f"Q: {turn['question']}\nA: {turn['answer']}" for turn in history
            )
            user_prompt = f"Conversation history:\n\n{history_block}\n\nLatest question: {question}"
            system_prompt = _SYSTEM_PROMPT_WITH_HISTORY
        else:
            user_prompt = question
            system_prompt = _SYSTEM_PROMPT

        response = _client().chat.completions.create(
            model=settings.azure_openai_chat_deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        rewritten = (response.choices[0].message.content or "").strip()
        return rewritten or question
    except Exception:
        logger.warning("Query rewrite failed; falling back to original question", exc_info=True)
        return question
