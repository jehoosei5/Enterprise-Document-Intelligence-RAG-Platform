"""PDF parsing: native text extraction per page, falling back to OCR for
pages that yield no (or negligible) extractable text — i.e. scanned pages.
"""

from __future__ import annotations

import io
import logging

import fitz  # PyMuPDF
from PIL import Image

from app.ingestion.common import BlockType, IngestedBlock, IngestedDocument

logger = logging.getLogger(__name__)

# A page with fewer than this many non-whitespace chars of native text is
# treated as "no extractable text" and sent through OCR instead.
MIN_NATIVE_CHARS_PER_PAGE = 20

# Render scale for OCR rasterization (higher = better OCR accuracy, slower).
OCR_RENDER_ZOOM = 2.0


def _ocr_page(page: "fitz.Page") -> str:
    try:
        import pytesseract
    except ImportError as e:
        raise RuntimeError(
            "pytesseract is required for OCR fallback but is not installed, "
            "or the Tesseract binary is missing from PATH."
        ) from e

    matrix = fitz.Matrix(OCR_RENDER_ZOOM, OCR_RENDER_ZOOM)
    pix = page.get_pixmap(matrix=matrix)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    try:
        return pytesseract.image_to_string(img)
    except Exception as e:
        raise RuntimeError(
            "OCR fallback failed — this usually means the Tesseract binary "
            "isn't installed on this machine. Install it and ensure it's on "
            "PATH (or set pytesseract.pytesseract.tesseract_cmd) to enable "
            "scanned-PDF support."
        ) from e


def parse_pdf(file_path: str, doc_id: str, filename: str) -> IngestedDocument:
    blocks: list[IngestedBlock] = []
    order = 0
    ocr_used = False

    with fitz.open(file_path) as pdf:
        page_count = pdf.page_count
        for page_index in range(page_count):
            page = pdf.load_page(page_index)
            page_number = page_index + 1

            native_text = page.get_text("text") or ""
            used_ocr_this_page = False

            if len(native_text.strip()) < MIN_NATIVE_CHARS_PER_PAGE:
                logger.info(
                    "PDF %s page %d has negligible native text (%d chars); using OCR fallback",
                    filename, page_number, len(native_text.strip()),
                )
                native_text = _ocr_page(page)
                used_ocr_this_page = True
                ocr_used = True

            # Split on blank lines into paragraph-ish blocks; keeps chunking
            # from later having to re-tokenize one giant page string.
            paragraphs = [p.strip() for p in native_text.split("\n\n") if p.strip()]
            if not paragraphs:
                # Even single-newline text is better than dropping the page.
                paragraphs = [p.strip() for p in native_text.split("\n") if p.strip()]

            for para in paragraphs:
                blocks.append(
                    IngestedBlock(
                        text=para,
                        block_type=BlockType.PARAGRAPH,
                        order_index=order,
                        page_number=page_number,
                        ocr_generated=used_ocr_this_page,
                    )
                )
                order += 1

    return IngestedDocument(
        doc_id=doc_id,
        filename=filename,
        source_format="pdf",
        blocks=blocks,
        page_count=page_count,
        ocr_used=ocr_used,
    )
