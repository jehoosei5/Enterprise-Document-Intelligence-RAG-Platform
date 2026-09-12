"""Query rewriting: clean up the raw user question into a better search
query before embedding it. When prior conversation turns are given, also
resolves follow-ups (pronouns/ellipsis) against them — e.g. "what about for
managers?" -> "How many PTO days do managers get?".

Also decides, in the same call, whether the message needs document
retrieval at all versus a plain conversational reply — the model's own
general judgment call (greetings, thanks, small talk, "what can you do?",
etc.), not a hardcoded keyword/phrase list.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache

from openai import AzureOpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You help a document Q&A system. Given the user's message, decide "
    "whether it's a real question that needs searching the user's uploaded "
    "documents, or just conversational (a greeting, thanks, small talk, "
    "asking what you can do, etc. — anything that isn't actually asking "
    "about document content). Then, if it does need retrieval, rewrite it "
    "into a clear, standalone search query: fix typos, expand "
    "abbreviations/acronyms, make implicit intent explicit. Preserve the "
    "original meaning exactly — do not answer the question, add "
    "information, or change what is being asked. If it does NOT need "
    "retrieval, set rewritten_query to the message unchanged.\n\n"
    'Reply with ONLY a JSON object: {"needs_retrieval": true or false, '
    '"rewritten_query": "..."}'
)

_SYSTEM_PROMPT_WITH_HISTORY = (
    "You help a document Q&A system. Given the user's latest message and "
    "the conversation history, decide whether it's a real question that "
    "needs searching the user's uploaded documents, or just conversational "
    "(a greeting, thanks, small talk, asking what you can do, etc. — "
    "anything that isn't actually asking about document content). Then, if "
    "it does need retrieval, rewrite it into a clear, standalone search "
    "query, using the history to resolve any pronouns, ellipsis, or "
    'implicit references (e.g. "what about for managers?" after a question '
    'about PTO days becomes "How many PTO days do managers get?"). Fix '
    "typos and expand abbreviations/acronyms too. Preserve the question's "
    "intent exactly — do not answer it, add information, or change what is "
    "being asked. If it does NOT need retrieval, set rewritten_query to the "
    "message unchanged.\n\n"
    'Reply with ONLY a JSON object: {"needs_retrieval": true or false, '
    '"rewritten_query": "..."}'
)


@dataclass
class RewriteResult:
    rewritten_query: str
    needs_retrieval: bool


@lru_cache
def _client() -> AzureOpenAI:
    settings = get_settings()
    return AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )


def rewrite_query(question: str, history: list[dict] | None = None) -> RewriteResult:
    """Returns the rewritten query + whether retrieval is needed, or fails
    open to `needs_retrieval=True, rewritten_query=question` on any error
    (JSON parse failure, API error) — when in doubt, retrieve, don't
    silently drop a real question.

    history, if given, is a list of {"question": ..., "answer": ...} prior
    turns (oldest first), already capped by the caller to the last N turns.
    """
    settings = get_settings()
    try:
        if history:
            history_block = "\n\n".join(
                f"Q: {turn['question']}\nA: {turn['answer']}" for turn in history
            )
            user_prompt = f"Conversation history:\n\n{history_block}\n\nLatest message: {question}"
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
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
        rewritten = (parsed.get("rewritten_query") or "").strip()
        return RewriteResult(
            rewritten_query=rewritten or question,
            needs_retrieval=bool(parsed.get("needs_retrieval", True)),
        )
    except Exception:
        logger.warning("Query rewrite failed; falling back to original question", exc_info=True)
        return RewriteResult(rewritten_query=question, needs_retrieval=True)
