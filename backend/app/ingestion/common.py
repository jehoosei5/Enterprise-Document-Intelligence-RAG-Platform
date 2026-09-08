"""Common intermediate representation (IR) that every format-specific parser
produces. Downstream stages (chunking, embedding, citation rendering) only
ever see this IR, so they stay format-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE_ROW = "table_row"
    LIST_ITEM = "list_item"
    CELL = "cell"  # CSV cell/row rendered as text


@dataclass
class IngestedBlock:
    """One atomic unit of content, in document order.

    Chunking groups/splits these; it never re-parses the source file.
    """

    text: str
    block_type: BlockType
    order_index: int

    # Structure-aware chunking hook: the stack of headings this block sits
    # under, e.g. ["Introduction", "Background"]. Empty for formats with no
    # heading structure (plain text/CSV, scanned PDFs).
    heading_path: list[str] = field(default_factory=list)
    heading_level: int | None = None  # 1 = H1, 2 = H2, ... only set when block_type == HEADING

    # Citation locators — populate whichever is meaningful for the source format.
    page_number: int | None = None       # PDF
    line_start: int | None = None        # plain text / CSV
    line_end: int | None = None
    row_number: int | None = None        # CSV

    ocr_generated: bool = False  # True if this block's text came from OCR, not native extraction


@dataclass
class IngestedDocument:
    doc_id: str
    filename: str
    source_format: str  # "pdf" | "docx" | "markdown" | "text" | "csv"
    blocks: list[IngestedBlock]
    page_count: int | None = None
    ocr_used: bool = False
    extra_metadata: dict = field(default_factory=dict)
