"""Plain text and CSV parsing. No heading structure available, so citations
are line-range (text) or row-number (CSV) based instead.
"""

from __future__ import annotations

import csv

from app.ingestion.common import BlockType, IngestedBlock, IngestedDocument

# Group this many lines of plain text into one block before chunking takes
# over; keeps very long files from producing one block per line.
TEXT_LINES_PER_BLOCK = 5


def parse_text(file_path: str, doc_id: str, filename: str) -> IngestedDocument:
    with open(file_path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    blocks: list[IngestedBlock] = []
    order = 0
    for start in range(0, len(lines), TEXT_LINES_PER_BLOCK):
        chunk_lines = lines[start:start + TEXT_LINES_PER_BLOCK]
        text = "".join(chunk_lines).strip()
        if not text:
            continue
        blocks.append(
            IngestedBlock(
                text=text,
                block_type=BlockType.PARAGRAPH,
                order_index=order,
                line_start=start + 1,
                line_end=min(start + TEXT_LINES_PER_BLOCK, len(lines)),
            )
        )
        order += 1

    return IngestedDocument(
        doc_id=doc_id,
        filename=filename,
        source_format="text",
        blocks=blocks,
    )


def parse_csv(file_path: str, doc_id: str, filename: str) -> IngestedDocument:
    blocks: list[IngestedBlock] = []
    order = 0

    with open(file_path, encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            header = []

        for row_number, row in enumerate(reader, start=2):  # row 1 = header
            if not any(cell.strip() for cell in row):
                continue
            # Render as "col: value" pairs so the LLM sees field names, not
            # just positional values.
            pairs = [
                f"{header[i] if i < len(header) else f'col{i}'}: {cell}"
                for i, cell in enumerate(row)
            ]
            text = "; ".join(pairs)
            blocks.append(
                IngestedBlock(
                    text=text,
                    block_type=BlockType.CELL,
                    order_index=order,
                    row_number=row_number,
                )
            )
            order += 1

    return IngestedDocument(
        doc_id=doc_id,
        filename=filename,
        source_format="csv",
        blocks=blocks,
        extra_metadata={"header": header},
    )
