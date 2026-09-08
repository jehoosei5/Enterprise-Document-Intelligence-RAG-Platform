"""Picks the right parser by file extension. This is the only place that
needs to know the mapping from extension -> parser.
"""

from __future__ import annotations

from pathlib import Path

from app.ingestion.common import IngestedDocument
from app.ingestion.docx_parser import parse_docx
from app.ingestion.markdown_parser import parse_markdown
from app.ingestion.pdf import parse_pdf
from app.ingestion.text_csv import parse_csv, parse_text

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".md", ".markdown", ".txt", ".csv"}


class UnsupportedFileTypeError(ValueError):
    pass


def parse_document(file_path: str, doc_id: str, filename: str) -> IngestedDocument:
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        return parse_pdf(file_path, doc_id, filename)
    if ext == ".docx":
        return parse_docx(file_path, doc_id, filename)
    if ext in (".md", ".markdown"):
        return parse_markdown(file_path, doc_id, filename)
    if ext == ".txt":
        return parse_text(file_path, doc_id, filename)
    if ext == ".csv":
        return parse_csv(file_path, doc_id, filename)

    raise UnsupportedFileTypeError(
        f"Unsupported file extension '{ext}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}"
    )
