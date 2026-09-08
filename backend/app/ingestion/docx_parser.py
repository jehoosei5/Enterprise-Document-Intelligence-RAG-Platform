"""DOCX parsing via python-docx. Preserves heading structure (Heading 1..6
paragraph styles) so chunking can be structure-aware, and renders tables as
row-per-block text.
"""

from __future__ import annotations

import re

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.ingestion.common import BlockType, IngestedBlock, IngestedDocument

_HEADING_RE = re.compile(r"^Heading (\d)$", re.IGNORECASE)


def _heading_level(style_name: str) -> int | None:
    if style_name.lower() in ("title",):
        return 1
    m = _HEADING_RE.match(style_name or "")
    return int(m.group(1)) if m else None


def parse_docx(file_path: str, doc_id: str, filename: str) -> IngestedDocument:
    document = docx.Document(file_path)
    blocks: list[IngestedBlock] = []
    heading_stack: list[str] = []  # current path, indexed by level - 1
    order = 0

    def push_heading(level: int, text: str) -> None:
        del heading_stack[level - 1:]
        heading_stack.append(text)

    # Iterate body children in document order (paragraphs and tables are
    # siblings in the underlying XML; python-docx exposes them separately,
    # so we walk the element tree to preserve true order).
    body = document.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            para = Paragraph(child, document)
            text = para.text.strip()
            if not text:
                continue
            level = _heading_level(para.style.name if para.style else "")
            if level:
                push_heading(level, text)
                blocks.append(
                    IngestedBlock(
                        text=text,
                        block_type=BlockType.HEADING,
                        order_index=order,
                        heading_path=list(heading_stack[:-1]),
                        heading_level=level,
                    )
                )
            else:
                blocks.append(
                    IngestedBlock(
                        text=text,
                        block_type=BlockType.PARAGRAPH,
                        order_index=order,
                        heading_path=list(heading_stack),
                    )
                )
            order += 1
        elif child.tag.endswith("}tbl"):
            table = Table(child, document)
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells]
                row_text = " | ".join(cells)
                if not row_text.strip(" |"):
                    continue
                blocks.append(
                    IngestedBlock(
                        text=row_text,
                        block_type=BlockType.TABLE_ROW,
                        order_index=order,
                        heading_path=list(heading_stack),
                    )
                )
                order += 1

    return IngestedDocument(
        doc_id=doc_id,
        filename=filename,
        source_format="docx",
        blocks=blocks,
    )
