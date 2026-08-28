from dataclasses import dataclass
from typing import Any

from markdown_it import MarkdownIt


@dataclass(frozen=True)
class ParsedMarkdown:
    text: str
    line_count: int
    headings: list[dict[str, Any]]
    blocks: list[dict[str, Any]]


class MarkdownParseError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _line_offsets(text: str) -> list[int]:
    offsets: list[int] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        offsets.append(offset)
        offset += len(line)
    return offsets


def _line_values(text: str) -> list[str]:
    return [line.rstrip("\r\n") for line in text.splitlines(keepends=True)]


def _source_block(
    text: str,
    lines: list[str],
    offsets: list[int],
    *,
    block_type: str,
    start_line: int,
    end_line: int,
    section_path: list[str],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    char_start = offsets[start_line]
    char_end = offsets[end_line - 1] + len(lines[end_line - 1])
    block = {
        "type": block_type,
        "text": text[char_start:char_end],
        "line_start": start_line + 1,
        "line_end": end_line,
        "char_start": char_start,
        "char_end": char_end,
        "source": {
            "line_start": start_line + 1,
            "line_end": end_line,
            "section_path": section_path.copy(),
        },
    }
    if metadata:
        block.update(metadata)
    return block


def _block_type(token_type: str) -> tuple[str, dict[str, Any]]:
    if token_type == "bullet_list_open":
        return "list", {"ordered": False}
    if token_type == "ordered_list_open":
        return "list", {"ordered": True}
    if token_type == "table_open":
        return "table", {}
    if token_type == "blockquote_open":
        return "quote", {}
    if token_type == "hr":
        return "thematic_break", {}
    return "", {}


def parse_markdown(content: bytes) -> ParsedMarkdown:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MarkdownParseError(
            "MATERIAL_SOURCE_INVALID_UTF8",
            "material is not valid UTF-8",
        ) from exc

    if not text.strip():
        raise MarkdownParseError(
            "MATERIAL_CONTENT_EMPTY",
            "material contains no text",
        )

    lines = _line_values(text)
    offsets = _line_offsets(text)
    tokens = MarkdownIt("default").parse(text)
    blocks: list[dict[str, Any]] = []

    for index, token in enumerate(tokens):
        if token.level != 0 or token.map is None:
            continue

        start_line, end_line = token.map
        if token.type == "heading_open":
            inline = tokens[index + 1]
            blocks.append(
                _source_block(
                    text,
                    lines,
                    offsets,
                    block_type="heading",
                    start_line=start_line,
                    end_line=end_line,
                    section_path=[],
                    metadata={
                        "level": int(token.tag[1:]),
                        "title": inline.content,
                    },
                )
            )
            continue

        if token.type == "paragraph_open":
            inline = tokens[index + 1]
            blocks.append(
                _source_block(
                    text,
                    lines,
                    offsets,
                    block_type="paragraph",
                    start_line=start_line,
                    end_line=end_line,
                    section_path=[],
                    metadata={"content": inline.content},
                )
            )
            continue

        if token.type in {"fence", "code_block"}:
            blocks.append(
                _source_block(
                    text,
                    lines,
                    offsets,
                    block_type="code_block",
                    start_line=start_line,
                    end_line=end_line,
                    section_path=[],
                    metadata={"language": token.info.strip() or None},
                )
            )
            continue

        block_type, metadata = _block_type(token.type)
        if block_type:
            blocks.append(
                _source_block(
                    text,
                    lines,
                    offsets,
                    block_type=block_type,
                    start_line=start_line,
                    end_line=end_line,
                    section_path=[],
                    metadata=metadata,
                )
            )

    blocks.sort(key=lambda block: block["line_start"])
    section_path: list[str] = []
    headings: list[dict[str, Any]] = []
    for block in blocks:
        if block["type"] == "heading":
            level = block["level"]
            title = block["title"].strip()
            section_path = section_path[: level - 1] + [title]
            block["source"]["section_path"] = section_path.copy()
            headings.append(
                {
                    "line": block["line_start"],
                    "level": level,
                    "text": title,
                    "section_path": section_path.copy(),
                }
            )
        else:
            block["source"]["section_path"] = section_path.copy()

    return ParsedMarkdown(
        text=text,
        line_count=len(lines),
        headings=headings,
        blocks=blocks,
    )
