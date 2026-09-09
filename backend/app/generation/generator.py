"""Builds a grounded prompt from retrieved chunks, calls Azure OpenAI chat
completion, and maps the model's inline [n] citations back to source chunks.
"""

from __future__ import annotations

import re
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
    cited_indices = sorted({int(n) for n in _CITATION_RE.findall(answer_text)})

    sources = [
        Source(
            index=i,
            filename=chunks[i - 1].filename,
            locator=format_source_locator(chunks[i - 1]),
            text=chunks[i - 1].text,
        )
        for i in cited_indices
        if 1 <= i <= len(chunks)
    ]

    usage = response.usage
    return GeneratedAnswer(
        answer=answer_text,
        sources=sources,
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
    )
