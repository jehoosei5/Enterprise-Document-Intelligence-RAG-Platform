from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class QueryLogSummary(BaseModel):
    id: str
    question: str
    answer: str
    faithfulness_score: float | None
    context_precision_score: float | None
    answer_relevance_score: float | None
    eval_passed: bool | None
    feedback: str | None
    latency_total_ms: int
    created_at: datetime

    model_config = {"from_attributes": True}


class QueryLogDetail(BaseModel):
    id: str
    question: str
    rewritten_query: str
    answer: str

    retrieved_dense: list | None
    retrieved_sparse: list | None
    fused_candidates: list | None
    reranked_chunks: list | None
    sources: list | None

    model: str
    input_tokens: int
    output_tokens: int

    faithfulness_score: float | None
    context_precision_score: float | None
    answer_relevance_score: float | None
    eval_passed: bool | None
    eval_detail: dict | None
    feedback: str | None

    latency_retrieval_ms: int
    latency_rerank_ms: int
    latency_llm_ms: int
    latency_eval_ms: int
    latency_total_ms: int

    created_at: datetime

    model_config = {"from_attributes": True}


class StatsBucket(BaseModel):
    date: date
    query_count: int
    avg_faithfulness: float | None
    avg_context_precision: float | None
    avg_answer_relevance: float | None
    pass_rate: float | None
    thumbs_up_rate: float | None
    avg_latency_total_ms: float


class StatsResponse(BaseModel):
    buckets: list[StatsBucket]


class FeedbackRequest(BaseModel):
    rating: Literal["up", "down"]
