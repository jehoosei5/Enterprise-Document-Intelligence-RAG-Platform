from pathlib import Path

from app.ingestion.dispatch import parse_document
from app.ingestion.docx_parser import parse_docx
from app.ingestion.markdown_parser import parse_markdown
from app.ingestion.pdf import parse_pdf
from app.ingestion.text_csv import parse_csv, parse_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_pdf_extracts_pages_and_native_text():
    doc = parse_pdf(str(FIXTURES / "sample.pdf"), doc_id="d1", filename="sample.pdf")

    assert doc.source_format == "pdf"
    assert doc.page_count == 2
    assert doc.ocr_used is False
    assert len(doc.blocks) >= 2
    assert any("Revenue grew twelve percent" in b.text for b in doc.blocks)
    page1_blocks = [b for b in doc.blocks if b.page_number == 1]
    page2_blocks = [b for b in doc.blocks if b.page_number == 2]
    assert page1_blocks and page2_blocks
    assert all(not b.ocr_generated for b in doc.blocks)


def test_parse_docx_preserves_heading_structure():
    doc = parse_docx(str(FIXTURES / "sample.docx"), doc_id="d2", filename="sample.docx")

    assert doc.source_format == "docx"
    headings = [b for b in doc.blocks if b.block_type == "heading"]
    assert [h.text for h in headings] == [
        "Employee Handbook",
        "Time Off",
        "Requesting Leave",
        "Benefits",
    ]

    leave_para = next(b for b in doc.blocks if "Submit leave requests" in b.text)
    assert leave_para.heading_path == ["Employee Handbook", "Time Off", "Requesting Leave"]

    table_rows = [b for b in doc.blocks if b.block_type == "table_row"]
    assert any("Dental" in r.text for r in table_rows)


def test_parse_markdown_preserves_heading_structure():
    doc = parse_markdown(str(FIXTURES / "sample.md"), doc_id="d3", filename="sample.md")

    assert doc.source_format == "markdown"
    password_block = next(b for b in doc.blocks if "twelve characters" in b.text)
    assert password_block.heading_path == ["Onboarding Guide", "Account Setup", "Password Requirements"]

    support_block = next(b for b in doc.blocks if "help@acme.example" in b.text)
    assert support_block.heading_path == ["Onboarding Guide", "Support"]


def test_parse_text_groups_lines_into_blocks_with_line_ranges():
    doc = parse_text(str(FIXTURES / "sample.txt"), doc_id="d4", filename="sample.txt")

    assert doc.source_format == "text"
    assert len(doc.blocks) == 2
    assert doc.blocks[0].line_start == 1
    assert doc.blocks[0].line_end == 5
    assert doc.blocks[1].line_start == 6
    assert doc.blocks[1].line_end == 7


def test_parse_csv_renders_rows_with_column_names_and_row_numbers():
    doc = parse_csv(str(FIXTURES / "sample.csv"), doc_id="d5", filename="sample.csv")

    assert doc.source_format == "csv"
    assert len(doc.blocks) == 3
    assert doc.blocks[0].row_number == 2  # row 1 is the header
    assert "name: Alice Johnson" in doc.blocks[0].text
    assert "department: Engineering" in doc.blocks[0].text


def test_dispatch_picks_parser_by_extension():
    for filename in ["sample.pdf", "sample.docx", "sample.md", "sample.txt", "sample.csv"]:
        doc = parse_document(str(FIXTURES / filename), doc_id="d6", filename=filename)
        assert doc.blocks
