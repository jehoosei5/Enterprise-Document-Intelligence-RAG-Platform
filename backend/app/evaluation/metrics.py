"""RAGAS-style eval metrics, hand-rolled against Azure OpenAI directly (not
the `ragas` package — it pulls in LangChain, which this project deliberately
avoids so the debug trace has full low-level visibility into every call).

Each metric fails open independently: a scoring function that errors
returns None (logged), rather than one failure blanking every score or
5xx-ing the /query request.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
from openai import AzureOpenAI

from app.core.config import get_settings
from app.embeddings.azure_embeddings import embed_texts
from app.retrieval.qdrant_store import RetrievedChunk

logger = logging.getLogger(__name__)


@lru_cache
def _client() -> AzureOpenAI:
    settings = get_settings()
    return AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )


def _json_chat(system_prompt: str, user_prompt: str) -> dict:
    """One chat completion constrained to JSON-object output."""
    settings = get_settings()
    response = _client().chat.completions.create(
        model=settings.azure_openai_chat_deployment,
        response_format={"type": "json_object"},
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)


# ---------------------------------------------------------------------------
# Faithfulness
# ---------------------------------------------------------------------------

_CLAIM_EXTRACTION_PROMPT = (
    "Break the given answer down into a list of atomic factual claims — "
    "each a single, standalone, checkable statement. Do not include claims "
    'that are just hedges (e.g. "I\'m not sure"). Reply as JSON: '
    '{"claims": ["claim 1", "claim 2", ...]}. If the answer makes no '
    'checkable factual claims, reply {"claims": []}.'
)

_FAITHFULNESS_VERDICT_PROMPT = (
    "You will be given a context and a list of claims. For each claim, "
    "decide if it is directly supported by the context (true) or not "
    "(false) — a claim not mentioned in the context is unsupported. Reply "
    'as JSON: {"verdicts": [{"claim": "...", "supported": true|false}, ...]}, '
    "one entry per input claim, in the same order."
)


def extract_claims(answer: str) -> list[str]:
    result = _json_chat(_CLAIM_EXTRACTION_PROMPT, answer)
    claims = result.get("claims", [])
    return [c for c in claims if isinstance(c, str) and c.strip()]


def score_faithfulness(
    claims: list[str], context_text: str
) -> tuple[float | None, list[dict] | None]:
    """Returns (score, per-claim verdict detail). 0 claims -> 1.0 (nothing
    to falsify). None on any failure (fails open).
    """
    if not claims:
        return 1.0, []

    try:
        user_prompt = (
            f"Context:\n{context_text}\n\nClaims:\n"
            + "\n".join(f"- {c}" for c in claims)
        )
        result = _json_chat(_FAITHFULNESS_VERDICT_PROMPT, user_prompt)
        verdicts = result.get("verdicts", [])
        if not verdicts:
            raise ValueError("Model returned no verdicts")

        supported = sum(1 for v in verdicts if v.get("supported"))
        score = supported / len(verdicts)
        return score, verdicts
    except Exception:
        logger.warning("Faithfulness scoring failed", exc_info=True)
        return None, None


# ---------------------------------------------------------------------------
# Context precision
# ---------------------------------------------------------------------------

_CONTEXT_PRECISION_PROMPT = (
    "You will be given a question and a numbered list of context passages, "
    "in the order they were retrieved. For each passage, decide if it is "
    "relevant to answering the question (true) or not (false). Reply as "
    'JSON: {"verdicts": [true|false, ...]}, one entry per passage, in the '
    "same order."
)


def _precision_from_verdicts(verdicts: list[bool]) -> float:
    """Rank-weighted precision: mean of precision@k over each position k
    that is itself relevant. 0 if nothing is relevant. This rewards
    relevant items appearing earlier — a naive relevant-count/total would
    ignore ranking entirely.
    """
    if not verdicts:
        return 0.0

    relevant_count = 0
    precision_sum = 0.0
    for k, is_relevant in enumerate(verdicts, start=1):
        if is_relevant:
            relevant_count += 1
            precision_sum += relevant_count / k

    if relevant_count == 0:
        return 0.0
    return precision_sum / relevant_count


def score_context_precision(
    question: str, chunks: list[RetrievedChunk]
) -> tuple[float | None, list[dict] | None]:
    if not chunks:
        return 0.0, []

    try:
        passages_block = "\n\n".join(f"[{i + 1}] {c.text}" for i, c in enumerate(chunks))
        user_prompt = f"Question: {question}\n\nPassages:\n\n{passages_block}"
        result = _json_chat(_CONTEXT_PRECISION_PROMPT, user_prompt)
        verdicts = result.get("verdicts", [])
        if len(verdicts) != len(chunks):
            raise ValueError(f"Expected {len(chunks)} verdicts, got {len(verdicts)}")

        score = _precision_from_verdicts([bool(v) for v in verdicts])
        detail = [
            {"index": i + 1, "filename": c.filename, "relevant": bool(v)}
            for i, (c, v) in enumerate(zip(chunks, verdicts, strict=True))
        ]
        return score, detail
    except Exception:
        logger.warning("Context precision scoring failed", exc_info=True)
        return None, None


# ---------------------------------------------------------------------------
# Answer relevance
# ---------------------------------------------------------------------------

_HYPOTHETICAL_QUESTIONS_PROMPT = (
    "Given an answer, generate {n} different questions that this answer "
    "would be a good response to. The questions should be phrased as if "
    "asked by someone who has NOT seen the answer. Reply as JSON: "
    '{{"questions": ["question 1", "question 2", ...]}}.'
)


def _mean_cosine_similarity(query_vector: list[float], vectors: list[list[float]]) -> float:
    if not vectors:
        return 0.0
    q = np.array(query_vector)
    sims = []
    for v in vectors:
        v = np.array(v)
        denom = (np.linalg.norm(q) * np.linalg.norm(v)) or 1.0
        sims.append(float(np.dot(q, v) / denom))
    return sum(sims) / len(sims)


def score_answer_relevance(question: str, answer: str) -> tuple[float | None, list[str] | None]:
    settings = get_settings()
    try:
        n = settings.eval_hypothetical_questions
        prompt = _HYPOTHETICAL_QUESTIONS_PROMPT.format(n=n)
        result = _json_chat(prompt, answer)
        questions = [q for q in result.get("questions", []) if isinstance(q, str) and q.strip()]
        if not questions:
            raise ValueError("Model returned no hypothetical questions")

        vectors = embed_texts(questions)
        query_vector = embed_texts([question])[0]
        score = _mean_cosine_similarity(query_vector, vectors)
        return score, questions
    except Exception:
        logger.warning("Answer relevance scoring failed", exc_info=True)
        return None, None


# ---------------------------------------------------------------------------
# Combined
# ---------------------------------------------------------------------------


@dataclass
class EvaluationResult:
    faithfulness: float | None = None
    context_precision: float | None = None
    answer_relevance: float | None = None
    passed: bool | None = None
    detail: dict = field(default_factory=dict)


def evaluate(question: str, answer: str, context_chunks: list[RetrievedChunk]) -> EvaluationResult:
    settings = get_settings()

    if not context_chunks:
        return EvaluationResult(detail={"skipped_reason": "no retrieved context"})

    claims = extract_claims(answer)
    faithfulness, faithfulness_detail = score_faithfulness(
        claims, "\n\n".join(c.text for c in context_chunks)
    )
    context_precision, context_precision_detail = score_context_precision(question, context_chunks)
    answer_relevance, hypothetical_questions = score_answer_relevance(question, answer)

    passed = faithfulness >= settings.faithfulness_pass_threshold if faithfulness is not None else None

    return EvaluationResult(
        faithfulness=faithfulness,
        context_precision=context_precision,
        answer_relevance=answer_relevance,
        passed=passed,
        detail={
            "claims": claims,
            "faithfulness_verdicts": faithfulness_detail,
            "context_precision_verdicts": context_precision_detail,
            "hypothetical_questions": hypothetical_questions,
        },
    )
