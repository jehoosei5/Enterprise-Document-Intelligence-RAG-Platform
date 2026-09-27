"""Append-only human-readable query/eval traces to a .txt file.

MySQL remains the source of truth for the API/dashboard; this file is a
local mirror for offline inspection. Failures are logged and swallowed so
a disk error never 500s a /query request.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings
from app.db.models import QueryLog

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()


def _format_chunks(label: str, chunks: list | None) -> list[str]:
    if not chunks:
        return [f"{label}: (none)"]
    lines = [f"{label}: {len(chunks)}"]
    for i, c in enumerate(chunks, start=1):
        lines.append(
            f"  [{i}] score={c.get('score')} file={c.get('filename')} "
            f"locator={c.get('locator')} chunk_id={c.get('chunk_id')}"
        )
    return lines


def _format_entry(log: QueryLog) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "=" * 80,
        f"timestamp: {ts}",
        f"query_id: {log.id}",
        f"user_id: {log.user_id}",
        f"conversation_id: {log.conversation_id}",
        f"scoped_document_id: {log.scoped_document_id}",
        f"model: {log.model}",
        f"question: {log.question}",
        f"rewritten_query: {log.rewritten_query}",
        "",
        "--- answer ---",
        log.answer or "",
        "",
        "--- evaluation ---",
        f"faithfulness_score: {log.faithfulness_score}",
        f"context_precision_score: {log.context_precision_score}",
        f"answer_relevance_score: {log.answer_relevance_score}",
        f"eval_passed: {log.eval_passed}",
        f"eval_detail: {log.eval_detail}",
        "",
        "--- tokens & latency (ms) ---",
        f"input_tokens: {log.input_tokens}  output_tokens: {log.output_tokens}",
        (
            f"retrieval: {log.latency_retrieval_ms}  rerank: {log.latency_rerank_ms}  "
            f"llm: {log.latency_llm_ms}  eval: {log.latency_eval_ms}  "
            f"total: {log.latency_total_ms}"
        ),
        "",
        "--- retrieval debug ---",
        *_format_chunks("dense", log.retrieved_dense),
        *_format_chunks("sparse", log.retrieved_sparse),
        *_format_chunks("fused", log.fused_candidates),
        *_format_chunks("reranked", log.reranked_chunks),
        "",
        "--- cited sources ---",
    ]
    if log.sources:
        for s in log.sources:
            lines.append(
                f"  [{s.get('index')}] {s.get('filename')} ({s.get('locator')})"
            )
            text = (s.get("text") or "").strip()
            if text:
                preview = text if len(text) <= 300 else text[:300] + "…"
                lines.append(f"      {preview}")
    else:
        lines.append("  (none)")

    lines.append("=" * 80)
    lines.append("")
    return "\n".join(lines)


def append_query_log(log: QueryLog) -> None:
    """Write one QueryLog row to the configured .txt file. Fail-open."""
    settings = get_settings()
    if not (settings.query_log_file or "").strip():
        return

    path = Path(settings.query_log_file.strip())
    if not path.is_absolute():
        # Resolve relative paths from backend/ (where uvicorn is typically run).
        path = Path(__file__).resolve().parents[2] / path

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = _format_entry(log)
        with _LOCK:
            with path.open("a", encoding="utf-8") as f:
                f.write(entry)
    except Exception:  # noqa: BLE001 — never break /query because of file I/O
        logger.warning("Failed to append query log to %s", path, exc_info=True)
