"""Markdown parsing via markdown-it-py's token stream. Headings (#..######)
build the heading_path used for structure-aware chunking; everything else
becomes paragraph/list-item blocks.
"""

from __future__ import annotations

from markdown_it import MarkdownIt

from app.ingestion.common import BlockType, IngestedBlock, IngestedDocument

_md = MarkdownIt("commonmark")


def parse_markdown(file_path: str, doc_id: str, filename: str) -> IngestedDocument:
    with open(file_path, encoding="utf-8", errors="replace") as f:
        raw = f.read()

    tokens = _md.parse(raw)
    blocks: list[IngestedBlock] = []
    heading_stack: list[str] = []
    order = 0

    i = 0
    in_list_item = False
    while i < len(tokens):
        tok = tokens[i]

        if tok.type == "heading_open":
            level = int(tok.tag[1])  # "h1" -> 1
            inline = tokens[i + 1]
            text = inline.content.strip()
            if text:
                del heading_stack[level - 1:]
                heading_stack.append(text)
                blocks.append(
                    IngestedBlock(
                        text=text,
                        block_type=BlockType.HEADING,
                        order_index=order,
                        heading_path=list(heading_stack[:-1]),
                        heading_level=level,
                    )
                )
                order += 1
            i += 3  # heading_open, inline, heading_close
            continue

        if tok.type == "paragraph_open":
            inline = tokens[i + 1]
            text = inline.content.strip()
            if text:
                blocks.append(
                    IngestedBlock(
                        text=text,
                        block_type=BlockType.LIST_ITEM if in_list_item else BlockType.PARAGRAPH,
                        order_index=order,
                        heading_path=list(heading_stack),
                    )
                )
                order += 1
            i += 3
            continue

        if tok.type == "bullet_list_open" or tok.type == "ordered_list_open":
            in_list_item = True
            i += 1
            continue
        if tok.type == "bullet_list_close" or tok.type == "ordered_list_close":
            in_list_item = False
            i += 1
            continue

        if tok.type == "fence" or tok.type == "code_block":
            text = tok.content.strip()
            if text:
                blocks.append(
                    IngestedBlock(
                        text=text,
                        block_type=BlockType.PARAGRAPH,
                        order_index=order,
                        heading_path=list(heading_stack),
                    )
                )
                order += 1
            i += 1
            continue

        i += 1

    return IngestedDocument(
        doc_id=doc_id,
        filename=filename,
        source_format="markdown",
        blocks=blocks,
    )
