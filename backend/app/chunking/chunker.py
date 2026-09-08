"""Turns an IngestedDocument into a list of Chunk objects.

Two strategies:
- Structure-aware (Markdown/DOCX): group consecutive blocks that share the
  same heading_path into one chunk, splitting a section further if it would
  exceed the token budget.
- Fixed-size sliding window (PDF/text/CSV): concatenate blocks up to the
  token budget with overlap, without merging across page boundaries (PDF)
  so the page-number citation for a chunk stays unambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import tiktoken

from app.ingestion.common import IngestedBlock, IngestedDocument

_ENCODING = tiktoken.get_encoding("cl100k_base")

STRUCTURED_FORMATS = {"markdown", "docx"}


def count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


@dataclass
class Chunk:
    doc_id: str
    filename: str
    source_format: str
    chunk_index: int
    text: str
    token_count: int
    heading_path: list[str] = field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    row_start: int | None = None
    row_end: int | None = None
    ocr_generated: bool = False


def chunk_document(doc: IngestedDocument, target_tokens: int = 500, overlap_tokens: int = 50) -> list[Chunk]:
    if doc.source_format in STRUCTURED_FORMATS:
        return _chunk_structured(doc, target_tokens)
    return _chunk_fixed_size(doc, target_tokens, overlap_tokens)


def _new_chunk(doc: IngestedDocument, index: int, blocks: list[IngestedBlock]) -> Chunk:
    text = "\n\n".join(b.text for b in blocks)
    pages = [b.page_number for b in blocks if b.page_number is not None]
    lines_start = [b.line_start for b in blocks if b.line_start is not None]
    lines_end = [b.line_end for b in blocks if b.line_end is not None]
    rows = [b.row_number for b in blocks if b.row_number is not None]

    return Chunk(
        doc_id=doc.doc_id,
        filename=doc.filename,
        source_format=doc.source_format,
        chunk_index=index,
        text=text,
        token_count=count_tokens(text),
        heading_path=blocks[0].heading_path if blocks else [],
        page_start=min(pages) if pages else None,
        page_end=max(pages) if pages else None,
        line_start=min(lines_start) if lines_start else None,
        line_end=max(lines_end) if lines_end else None,
        row_start=min(rows) if rows else None,
        row_end=max(rows) if rows else None,
        ocr_generated=any(b.ocr_generated for b in blocks),
    )


def _chunk_structured(doc: IngestedDocument, target_tokens: int) -> list[Chunk]:
    """Group consecutive content blocks under the same heading_path. A
    heading block itself is dropped from the chunk text (it's already
    captured in heading_path) but starts a new group.
    """
    chunks: list[Chunk] = []
    current_blocks: list[IngestedBlock] = []
    current_tokens = 0
    current_path: list[str] | None = None

    def flush():
        nonlocal current_blocks, current_tokens
        if current_blocks:
            chunks.append(_new_chunk(doc, len(chunks), current_blocks))
            current_blocks = []
            current_tokens = 0

    for block in doc.blocks:
        if block.block_type == "heading":
            # Heading text isn't content; it changes the path for what follows.
            flush()
            current_path = None
            continue

        if current_path is None:
            current_path = block.heading_path
        elif block.heading_path != current_path:
            flush()
            current_path = block.heading_path

        block_tokens = count_tokens(block.text)
        if current_blocks and current_tokens + block_tokens > target_tokens:
            flush()
            current_path = block.heading_path

        current_blocks.append(block)
        current_tokens += block_tokens

    flush()
    return chunks


def _chunk_fixed_size(doc: IngestedDocument, target_tokens: int, overlap_tokens: int) -> list[Chunk]:
    """Sliding window over blocks, grouped so PDF chunks never span pages."""
    chunks: list[Chunk] = []

    def groups_by_page():
        if doc.source_format != "pdf":
            yield doc.blocks
            return
        current_page = None
        group: list[IngestedBlock] = []
        for block in doc.blocks:
            if current_page is not None and block.page_number != current_page:
                if group:
                    yield group
                group = []
            current_page = block.page_number
            group.append(block)
        if group:
            yield group

    for group in groups_by_page():
        current: list[IngestedBlock] = []
        current_tokens = 0
        i = 0
        while i < len(group):
            block = group[i]
            block_tokens = count_tokens(block.text)

            if current and current_tokens + block_tokens > target_tokens:
                chunks.append(_new_chunk(doc, len(chunks), current))
                # Build overlap: keep trailing blocks whose combined tokens
                # are <= overlap_tokens, to seed the next chunk.
                overlap: list[IngestedBlock] = []
                overlap_count = 0
                for b in reversed(current):
                    bt = count_tokens(b.text)
                    if overlap_count + bt > overlap_tokens:
                        break
                    overlap.insert(0, b)
                    overlap_count += bt
                current = overlap
                current_tokens = overlap_count
                continue  # retry this block against the reset window

            current.append(block)
            current_tokens += block_tokens
            i += 1

        if current:
            chunks.append(_new_chunk(doc, len(chunks), current))

    return chunks
