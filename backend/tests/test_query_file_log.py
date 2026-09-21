"""Unit tests for append-only query .txt logging."""

from types import SimpleNamespace

from app.core.query_file_log import _format_entry, append_query_log


def _log(**overrides):
    base = dict(
        id="q-1",
        user_id="u-1",
        conversation_id="c-1",
        scoped_document_id=None,
        model="gpt-4o",
        question="What is the leave policy?",
        rewritten_query="leave policy",
        answer="Employees get 20 days [1].",
        faithfulness_score=1.0,
        context_precision_score=0.8,
        answer_relevance_score=0.9,
        eval_passed=True,
        eval_detail={"claims": ["Employees get 20 days"]},
        input_tokens=100,
        output_tokens=20,
        latency_retrieval_ms=10,
        latency_rerank_ms=5,
        latency_llm_ms=50,
        latency_eval_ms=30,
        latency_total_ms=95,
        retrieved_dense=[{"chunk_id": "c1", "doc_id": "d1", "filename": "hr.pdf", "locator": "p.1", "score": 0.9}],
        retrieved_sparse=[],
        fused_candidates=[],
        reranked_chunks=[{"chunk_id": "c1", "doc_id": "d1", "filename": "hr.pdf", "locator": "p.1", "score": 0.95}],
        sources=[{"index": 1, "filename": "hr.pdf", "locator": "p.1", "text": "20 days of leave"}],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_format_entry_includes_eval_and_question():
    text = _format_entry(_log())
    assert "query_id: q-1" in text
    assert "What is the leave policy?" in text
    assert "faithfulness_score: 1.0" in text
    assert "eval_passed: True" in text
    assert "hr.pdf" in text


def test_append_query_log_writes_file(tmp_path, monkeypatch):
    from app.core import query_file_log
    from app.core.config import get_settings

    get_settings.cache_clear()
    log_path = tmp_path / "query_logs.txt"
    monkeypatch.setenv("QUERY_LOG_FILE", str(log_path))
    get_settings.cache_clear()

    append_query_log(_log())  # type: ignore[arg-type]

    content = log_path.read_text(encoding="utf-8")
    assert "query_id: q-1" in content
    assert "faithfulness_score: 1.0" in content

    get_settings.cache_clear()


def test_append_query_log_disabled_when_empty(tmp_path, monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("QUERY_LOG_FILE", "")
    get_settings.cache_clear()

    # Should not raise and should not create a default file under tmp.
    append_query_log(_log())  # type: ignore[arg-type]
    assert list(tmp_path.iterdir()) == []

    get_settings.cache_clear()
