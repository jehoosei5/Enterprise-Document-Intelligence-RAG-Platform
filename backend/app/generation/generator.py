"""Builds a grounded prompt from retrieved chunks, calls Azure OpenAI chat
completion (streaming or not), and maps the model's inline [n] citations
back to source chunks.
"""

from __future__ import annotations

import re
from collections.abc import Generator
from dataclasses import dataclass
from functools import lru_cache

from openai import AzureOpenAI

from app.core.config import get_settings
from app.retrieval.qdrant_store import RetrievedChunk

_CITATION_RE = re.compile(r"\[(\d+)\]")

_SYSTEM_PROMPT = (
    "You are a document Q&A assistant. Answer the user's question using ONLY "
    "the numbered sources below. Every factual claim must be followed by a "
    "citation like [1] or [2] referencing the source it came from. If the "
    "sources don't contain the answer, say so plainly instead of guessing — "
    "never invent information that isn't in the sources."
)

_CHAT_SYSTEM_PROMPT = (
    "You are DocIntel's assistant, embedded in a company document Q&A tool. "
    "The user's message doesn't need document retrieval — it's "
    "conversational (a greeting, thanks, small talk, asking what you can "
    "do, etc.). Reply naturally and briefly, in plain text with no "
    "citations. If relevant, mention you can answer questions about their "
    "uploaded documents."
)

_TITLE_SYSTEM_PROMPT = (
    "Summarize this exchange into a short chat title, 6 words or fewer. "
    "No quotes, no trailing punctuation, no prefix like \"Title:\" — just "
    "the title text itself."
)


@lru_cache
def _client() -> AzureOpenAI:
    settings = get_settings()
    return AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )


def format_source_locator(chunk: RetrievedChunk) -> str:
    if chunk.page_start is not None:
        loc = f"page {chunk.page_start}" if chunk.page_start == chunk.page_end else f"pages {chunk.page_start}-{chunk.page_end}"
    elif chunk.line_start is not None:
        loc = f"lines {chunk.line_start}-{chunk.line_end}"
    elif chunk.row_start is not None:
        loc = f"rows {chunk.row_start}-{chunk.row_end}"
    elif chunk.heading_path:
        loc = " > ".join(chunk.heading_path)
    else:
        loc = "unknown location"
    return f"{chunk.filename} ({loc})"


def _build_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    sources_block = "\n\n".join(
        f"[{i + 1}] Source: {format_source_locator(c)}\n{c.text}"
        for i, c in enumerate(chunks)
    )
    return f"Sources:\n\n{sources_block}\n\nQuestion: {question}"


@dataclass
class Source:
    index: int
    filename: str
    locator: str
    text: str


@dataclass
class GeneratedAnswer:
    answer: str
    sources: list[Source]
    input_tokens: int
    output_tokens: int


def parse_citations(answer_text: str, chunks: list[RetrievedChunk]) -> list[Source]:
    """Maps the model's inline [n] citations back to the source chunks
    they refer to. Shared by both the sync and streaming generation paths.
    """
    cited_indices = sorted({int(n) for n in _CITATION_RE.findall(answer_text)})
    return [
        Source(
            index=i,
            filename=chunks[i - 1].filename,
            locator=format_source_locator(chunks[i - 1]),
            text=chunks[i - 1].text,
        )
        for i in cited_indices
        if 1 <= i <= len(chunks)
    ]


def generate_answer(question: str, chunks: list[RetrievedChunk]) -> GeneratedAnswer:
    settings = get_settings()

    if not chunks:
        return GeneratedAnswer(
            answer="I couldn't find any relevant information in the uploaded documents.",
            sources=[],
            input_tokens=0,
            output_tokens=0,
        )

    prompt = _build_prompt(question, chunks)
    response = _client().chat.completions.create(
        model=settings.azure_openai_chat_deployment,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    answer_text = response.choices[0].message.content or ""
    sources = parse_citations(answer_text, chunks)

    usage = response.usage
    return GeneratedAnswer(
        answer=answer_text,
        sources=sources,
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
    )


def _chat_messages(question: str, history: list[dict] | None) -> list[dict]:
    messages = [{"role": "system", "content": _CHAT_SYSTEM_PROMPT}]
    for turn in history or []:
        messages.append({"role": "user", "content": turn["question"]})
        messages.append({"role": "assistant", "content": turn["answer"]})
    messages.append({"role": "user", "content": question})
    return messages


def generate_chat_reply(question: str, history: list[dict] | None = None) -> GeneratedAnswer:
    """Plain conversational reply — no retrieval, no sources, no forced
    citations. Used when the rewrite step decides the message doesn't need
    document retrieval at all (a greeting, thanks, small talk, etc.).
    """
    settings = get_settings()
    response = _client().chat.completions.create(
        model=settings.azure_openai_chat_deployment,
        messages=_chat_messages(question, history),
    )
    answer_text = response.choices[0].message.content or ""
    usage = response.usage
    return GeneratedAnswer(
        answer=answer_text,
        sources=[],
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
    )


def generate_conversation_title(question: str, answer: str) -> str | None:
    """A short summary title for a conversation (like ChatGPT's
    auto-titled chats), generated from its first Q&A pair. Returns None on
    any failure — the caller should just leave the placeholder title
    (question[:200], set at conversation creation) in that case, same
    fail-open pattern as rewrite_query.
    """
    settings = get_settings()
    try:
        response = _client().chat.completions.create(
            model=settings.azure_openai_chat_deployment,
            messages=[
                {"role": "system", "content": _TITLE_SYSTEM_PROMPT},
                {"role": "user", "content": f"Question: {question}\n\nAnswer: {answer}"},
            ],
            temperature=0.3,
        )
        title = (response.choices[0].message.content or "").strip().strip('"')
        return title or None
    except Exception:
        return None


@dataclass
class StreamUsage:
    input_tokens: int = 0
    output_tokens: int = 0


def stream_answer(
    question: str, chunks: list[RetrievedChunk], usage_out: StreamUsage
) -> Generator[str, None, None]:
    """Yields answer text deltas as they arrive from Azure OpenAI. The
    caller accumulates them into the full answer text (for citation
    parsing + eval, which need the complete text). usage_out is mutated
    in place with token counts once the final chunk (which carries usage,
    via stream_options) arrives — Python generators can't cleanly both
    yield values and return a final value, so this is the simplest way to
    hand token usage back to the caller after the stream completes.
    """
    settings = get_settings()

    if not chunks:
        yield "I couldn't find any relevant information in the uploaded documents."
        return

    prompt = _build_prompt(question, chunks)
    stream = _client().chat.completions.create(
        model=settings.azure_openai_chat_deployment,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        stream=True,
        stream_options={"include_usage": True},
    )

    for chunk in stream:
        if chunk.usage is not None:
            usage_out.input_tokens = chunk.usage.prompt_tokens
            usage_out.output_tokens = chunk.usage.completion_tokens
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def stream_chat_reply(
    question: str, history: list[dict] | None, usage_out: StreamUsage
) -> Generator[str, None, None]:
    """Streaming counterpart to generate_chat_reply — plain conversational
    reply, no retrieval, no sources.
    """
    settings = get_settings()
    stream = _client().chat.completions.create(
        model=settings.azure_openai_chat_deployment,
        messages=_chat_messages(question, history),
        stream=True,
        stream_options={"include_usage": True},
    )
    for chunk in stream:
        if chunk.usage is not None:
            usage_out.input_tokens = chunk.usage.prompt_tokens
            usage_out.output_tokens = chunk.usage.completion_tokens
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
