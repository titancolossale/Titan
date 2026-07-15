# =====================================
# Titan Markdown Parser
# =====================================

"""Markdown structure awareness for Obsidian vault maintenance (Phase 12.5 Batch 3 — P125-011)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_CHECKLIST_RE = re.compile(r"^(\s*)[-*+]\s+\[([ xX])\]\s+(.+?)\s*$", re.MULTILINE)
_BULLET_RE = re.compile(r"^(\s*)[-*+]\s+(?!\[)(.+?)\s*$", re.MULTILINE)
_NUMBERED_RE = re.compile(r"^(\s*)\d+\.\s+(.+?)\s*$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"^(`{3,}|~{3,})(\w*)\s*$", re.MULTILINE)
_CALLOUT_RE = re.compile(r"^>\s*\[!(\w+)\]([+-]?)\s*(.*)$", re.MULTILINE)
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_INLINE_TAG_RE = re.compile(r"(?<!\w)#([\w-]+)")
_TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$", re.MULTILINE)
_TABLE_SEP_RE = re.compile(r"^\|(\s*:?-+:?\s*\|)+\s*$", re.MULTILINE)


@dataclass(frozen=True)
class HeadingSection:
    """A markdown heading and its span in the document body."""

    level: int
    title: str
    start: int
    end: int
    line_start: int
    line_end: int


@dataclass(frozen=True)
class ChecklistItem:
    """A task-list line in markdown."""

    indent: str
    checked: bool
    text: str
    start: int
    end: int
    line: int


@dataclass(frozen=True)
class CodeBlock:
    """A fenced code block."""

    fence: str
    language: str
    start: int
    end: int
    content_start: int
    content_end: int


@dataclass(frozen=True)
class MarkdownTable:
    """A markdown pipe table."""

    start: int
    end: int
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass
class MarkdownDocument:
    """Parsed markdown note with structural metadata."""

    raw: str
    frontmatter: str | None = None
    body: str = ""
    headings: list[HeadingSection] = field(default_factory=list)
    checklist_items: list[ChecklistItem] = field(default_factory=list)
    code_blocks: list[CodeBlock] = field(default_factory=list)
    tables: list[MarkdownTable] = field(default_factory=list)
    wikilinks: list[str] = field(default_factory=list)
    tags: set[str] = field(default_factory=set)


def split_frontmatter(content: str) -> tuple[str | None, str]:
    """Split YAML frontmatter from the note body."""
    if not content.startswith("---"):
        return None, content
    end = content.find("\n---", 3)
    if end == -1:
        return None, content
    frontmatter = content[: end + 4]
    body = content[end + 4 :]
    if body.startswith("\n"):
        body = body[1:]
    return frontmatter, body


def parse_frontmatter_tags(frontmatter: str | None) -> set[str]:
    """Extract tags from YAML frontmatter."""
    if not frontmatter:
        return set()
    block = frontmatter.strip("-\n")
    tags: set[str] = set()
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("tags:"):
            value = stripped.split(":", 1)[1].strip()
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1]
                for item in inner.split(","):
                    cleaned = item.strip().strip("\"'")
                    if cleaned:
                        tags.add(cleaned.lower())
            else:
                tags.add(value.strip("# ").lower())
    return tags


def find_headings(body: str) -> list[HeadingSection]:
    """Locate heading sections with end boundaries."""
    matches = list(_HEADING_RE.finditer(body))
    sections: list[HeadingSection] = []
    for index, match in enumerate(matches):
        level = len(match.group(1))
        title = match.group(2).strip()
        start = match.start()
        line_start = body[:start].count("\n")
        if index + 1 < len(matches):
            end = matches[index + 1].start()
            line_end = body[:end].count("\n")
        else:
            end = len(body)
            line_end = body.count("\n")
        sections.append(
            HeadingSection(
                level=level,
                title=title,
                start=start,
                end=end,
                line_start=line_start,
                line_end=line_end,
            )
        )
    return sections


def find_checklist_items(body: str) -> list[ChecklistItem]:
    """Locate `- [ ]` / `- [x]` task lines."""
    items: list[ChecklistItem] = []
    for match in _CHECKLIST_RE.finditer(body):
        checked = match.group(2).lower() == "x"
        items.append(
            ChecklistItem(
                indent=match.group(1),
                checked=checked,
                text=match.group(3).strip(),
                start=match.start(),
                end=match.end(),
                line=body[: match.start()].count("\n"),
            )
        )
    return items


def find_code_blocks(body: str) -> list[CodeBlock]:
    """Locate fenced code blocks without modifying inner content."""
    blocks: list[CodeBlock] = []
    lines = body.splitlines(keepends=True)
    offset = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        fence_match = _CODE_FENCE_RE.match(line.rstrip("\n"))
        if not fence_match:
            offset += len(line)
            index += 1
            continue
        fence = fence_match.group(1)
        language = fence_match.group(2)
        block_start = offset
        content_start = offset + len(line)
        index += 1
        while index < len(lines):
            current = lines[index]
            if current.rstrip("\n").startswith(fence[:3]):
                content_end = offset + len(current) - len(current)
                block_end = offset + len(current)
                blocks.append(
                    CodeBlock(
                        fence=fence,
                        language=language,
                        start=block_start,
                        end=block_end,
                        content_start=content_start,
                        content_end=content_end,
                    )
                )
                offset = block_end
                index += 1
                break
            offset += len(current)
            index += 1
        else:
            break
    return blocks


def find_tables(body: str) -> list[MarkdownTable]:
    """Locate pipe tables in markdown body."""
    tables: list[MarkdownTable] = []
    lines = body.splitlines(keepends=True)
    offset = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        if not _TABLE_ROW_RE.match(line.rstrip("\n")):
            offset += len(line)
            index += 1
            continue
        block_start = offset
        block_lines: list[str] = []
        while index < len(lines) and _TABLE_ROW_RE.match(lines[index].rstrip("\n")):
            block_lines.append(lines[index].rstrip("\n"))
            offset += len(lines[index])
            index += 1
        if len(block_lines) < 2 or not _TABLE_SEP_RE.match(block_lines[1]):
            continue
        header = _split_table_row(block_lines[0])
        rows = tuple(_split_table_row(row) for row in block_lines[2:])
        tables.append(
            MarkdownTable(
                start=block_start,
                end=offset,
                header=header,
                rows=rows,
            )
        )
    return tables


def _split_table_row(row: str) -> tuple[str, ...]:
    inner = row.strip().strip("|")
    return tuple(cell.strip() for cell in inner.split("|"))


def extract_wikilinks(body: str) -> list[str]:
    """Extract Obsidian wikilink targets."""
    return [match.group(1).strip() for match in _WIKILINK_RE.finditer(body)]


def extract_inline_tags(body: str) -> set[str]:
    """Extract inline #tags from body (excludes headings)."""
    tags: set[str] = set()
    for line in body.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        for match in _INLINE_TAG_RE.finditer(line):
            tags.add(match.group(1).lower())
    return tags


def parse_markdown(content: str) -> MarkdownDocument:
    """Parse a note into structural components."""
    frontmatter, body = split_frontmatter(content)
    doc = MarkdownDocument(
        raw=content,
        frontmatter=frontmatter,
        body=body,
        headings=find_headings(body),
        checklist_items=find_checklist_items(body),
        code_blocks=find_code_blocks(body),
        tables=find_tables(body),
        wikilinks=extract_wikilinks(body),
    )
    doc.tags = parse_frontmatter_tags(frontmatter) | extract_inline_tags(body)
    return doc


def normalize_heading(title: str) -> str:
    """Normalize a heading for case-insensitive comparison."""
    return re.sub(r"\s+", " ", title.strip().lower())


def find_section_by_heading(body: str, heading: str) -> HeadingSection | None:
    """Find a section whose heading matches (case-insensitive)."""
    target = normalize_heading(heading)
    for section in find_headings(body):
        if normalize_heading(section.title) == target:
            return section
    return None


def is_inside_protected_block(body: str, index: int) -> bool:
    """Return True when *index* falls inside a code block."""
    for block in find_code_blocks(body):
        if block.start <= index < block.end:
            return True
    return False
