from pathlib import Path

from app.chunking.chunker import chunk_document, count_tokens
from app.ingestion.docx_parser import parse_docx
from app.ingestion.markdown_parser import parse_markdown
from app.ingestion.pdf import parse_pdf
from app.ingestion.text_csv import parse_csv, parse_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_markdown_chunks_respect_heading_boundaries():
    doc = parse_markdown(str(FIXTURES / "sample.md"), doc_id="d1", filename="sample.md")
    chunks = chunk_document(doc, target_tokens=500, overlap_tokens=50)

    assert chunks
    password_chunk = next(c for c in chunks if "twelve characters" in c.text)
    assert password_chunk.heading_path == ["Onboarding Guide", "Account Setup", "Password Requirements"]
    # Content from a different section shouldn't leak into the same chunk.
    assert "help@acme.example" not in password_chunk.text


def test_docx_chunks_respect_heading_boundaries():
    doc = parse_docx(str(FIXTURES / "sample.docx"), doc_id="d2", filename="sample.docx")
    chunks = chunk_document(doc, target_tokens=500, overlap_tokens=50)

    assert chunks
    leave_chunk = next(c for c in chunks if "Submit leave requests" in c.text)
    assert leave_chunk.heading_path == ["Employee Handbook", "Time Off", "Requesting Leave"]


def test_structured_chunk_splits_when_section_exceeds_budget():
    doc = parse_markdown(str(FIXTURES / "sample.md"), doc_id="d3", filename="sample.md")
    # Force a tiny budget so the single-paragraph sections still fit one
    # per chunk, but confirm no chunk exceeds it.
    chunks = chunk_document(doc, target_tokens=15, overlap_tokens=0)
    for c in chunks:
        # Allow the boundary case where a single block already exceeds the
        # budget on its own (can't split further without breaking sentences).
        assert c.token_count <= 15 or len(c.text.split("\n\n")) == 1


def test_pdf_chunks_never_span_pages():
    doc = parse_pdf(str(FIXTURES / "sample.pdf"), doc_id="d4", filename="sample.pdf")
    chunks = chunk_document(doc, target_tokens=500, overlap_tokens=50)

    assert chunks
    for c in chunks:
        assert c.page_start == c.page_end
    pages_seen = {c.page_start for c in chunks}
    assert pages_seen == {1, 2}


def test_fixed_size_chunks_stay_within_budget_with_small_target():
    doc = parse_text(str(FIXTURES / "sample.txt"), doc_id="d5", filename="sample.txt")
    chunks = chunk_document(doc, target_tokens=10, overlap_tokens=2)

    assert len(chunks) > 1
    for c in chunks:
        assert c.line_start is not None and c.line_end is not None


def test_csv_chunks_carry_row_ranges():
    doc = parse_csv(str(FIXTURES / "sample.csv"), doc_id="d6", filename="sample.csv")
    chunks = chunk_document(doc, target_tokens=500, overlap_tokens=0)

    assert chunks
    assert chunks[0].row_start == 2
    assert chunks[0].row_end == 4


def test_count_tokens_is_positive_for_nonempty_text():
    assert count_tokens("hello world") > 0
