# =====================================
# Titan Markdown Editor
# =====================================

"""Smart, formatting-preserving note updates for Obsidian vaults (Phase 12.5 Batch 3 — P125-012)."""

from __future__ import annotations

import re
from enum import Enum

from tools.connectors.markdown_parser import (
    MarkdownDocument,
    find_checklist_items,
    find_section_by_heading,
    find_tables,
    parse_markdown,
    split_frontmatter,
)


class NoteUpdateMode(str, Enum):
    """Supported smart update strategies."""

    REPLACE = "replace"
    APPEND = "append"
    PREPEND = "prepend"
    INSERT_UNDER_HEADING = "insert_under_heading"
    REPLACE_SECTION = "replace_section"
    UPDATE_CHECKLIST = "update_checklist"
    UPDATE_TABLE = "update_table"


SUPPORTED_UPDATE_MODES = frozenset(mode.value for mode in NoteUpdateMode)


class MarkdownEditError(ValueError):
    """Raised when a smart update cannot be applied safely."""


def apply_note_update(
    content: str,
    mode: str,
    *,
    new_content: str = "",
    heading: str = "",
    checklist_item: str = "",
    checked: bool | None = None,
    table_row: int = -1,
    table_col: int = -1,
    cell_value: str = "",
    table_index: int = 0,
) -> str:
    """Apply a formatting-preserving update to note content."""
    normalized = mode.strip().lower()
    if normalized not in SUPPORTED_UPDATE_MODES:
        raise MarkdownEditError(f"Mode de mise à jour non supporté : {mode!r}")

    if normalized == NoteUpdateMode.REPLACE.value:
        return new_content

    if normalized == NoteUpdateMode.APPEND.value:
        return _append(content, new_content)

    if normalized == NoteUpdateMode.PREPEND.value:
        return _prepend(content, new_content)

    if normalized == NoteUpdateMode.INSERT_UNDER_HEADING.value:
        if not heading:
            raise MarkdownEditError("Paramètre heading requis pour insert_under_heading.")
        return _insert_under_heading(content, heading, new_content)

    if normalized == NoteUpdateMode.REPLACE_SECTION.value:
        if not heading:
            raise MarkdownEditError("Paramètre heading requis pour replace_section.")
        return _replace_section(content, heading, new_content)

    if normalized == NoteUpdateMode.UPDATE_CHECKLIST.value:
        if not checklist_item:
            raise MarkdownEditError("Paramètre checklist_item requis pour update_checklist.")
        return _update_checklist(
            content,
            checklist_item,
            checked=checked,
            heading=heading,
        )

    if normalized == NoteUpdateMode.UPDATE_TABLE.value:
        return _update_table(
            content,
            table_index=table_index,
            row=table_row,
            col=table_col,
            cell_value=cell_value,
            heading=heading,
        )

    raise MarkdownEditError(f"Mode non implémenté : {mode!r}")


def _append(content: str, addition: str) -> str:
    if not addition:
        return content
    if not content:
        return addition
    separator = "" if content.endswith("\n") else "\n"
    if not addition.startswith("\n") and not content.endswith("\n\n"):
        separator = "\n" if content.endswith("\n") else "\n\n"
    return f"{content}{separator}{addition}"


def _prepend(content: str, addition: str) -> str:
    if not addition:
        return content
    frontmatter, body = split_frontmatter(content)
    if frontmatter:
        separator = "\n" if addition.endswith("\n") else "\n\n"
        return f"{frontmatter}\n{addition}{separator}{body}"
    separator = "" if addition.endswith("\n") else "\n\n"
    return f"{addition}{separator}{content}"


def _insert_under_heading(content: str, heading: str, insertion: str) -> str:
    frontmatter, body = split_frontmatter(content)
    section = find_section_by_heading(body, heading)
    if section is None:
        raise MarkdownEditError(f"Section introuvable : {heading!r}")

    heading_line_end = body.find("\n", section.start)
    if heading_line_end == -1:
        insert_at = len(body)
    else:
        insert_at = heading_line_end + 1

    prefix = body[:insert_at]
    suffix = body[insert_at:]
    block = insertion if insertion.endswith("\n") else f"{insertion}\n"
    if suffix and not block.endswith("\n") and not suffix.startswith("\n"):
        block = f"{block}\n"
    updated_body = f"{prefix}{block}{suffix}"
    if frontmatter:
        return f"{frontmatter}\n{updated_body}"
    return updated_body


def _replace_section(content: str, heading: str, new_section_body: str) -> str:
    frontmatter, body = split_frontmatter(content)
    section = find_section_by_heading(body, heading)
    if section is None:
        raise MarkdownEditError(f"Section introuvable : {heading!r}")

    heading_line = body[section.start : body.find("\n", section.start) + 1]
    if not heading_line.endswith("\n"):
        heading_line = f"{heading_line}\n"

    replacement = new_section_body
    if replacement and not replacement.endswith("\n"):
        replacement = f"{replacement}\n"

    updated_body = f"{body[:section.start]}{heading_line}{replacement}{body[section.end:]}"
    if frontmatter:
        return f"{frontmatter}\n{updated_body}"
    return updated_body


def _update_checklist(
    content: str,
    item_text: str,
    *,
    checked: bool | None,
    heading: str,
) -> str:
    frontmatter, body = split_frontmatter(content)
    search_body = body
    offset = 0
    if heading:
        section = find_section_by_heading(body, heading)
        if section is None:
            raise MarkdownEditError(f"Section introuvable : {heading!r}")
        search_body = body[section.start : section.end]
        offset = section.start

    target = item_text.strip().lower()
    items = find_checklist_items(search_body)
    match = next(
        (item for item in items if item.text.strip().lower() == target),
        None,
    )
    if match is None:
        for item in items:
            if target in item.text.strip().lower():
                match = item
                break
    if match is None:
        raise MarkdownEditError(f"Élément checklist introuvable : {item_text!r}")

    mark = "x" if checked else " "
    if checked is None:
        mark = "x" if not match.checked else " "
    new_line = f"{match.indent}- [{mark}] {match.text}\n"
    absolute_start = offset + match.start
    absolute_end = offset + match.end
    line_end = body.find("\n", absolute_end)
    if line_end == -1:
        line_end = absolute_end
    else:
        line_end += 1
    updated_body = f"{body[:absolute_start]}{new_line.rstrip()}{body[line_end:]}"
    if frontmatter:
        return f"{frontmatter}\n{updated_body}"
    return updated_body


def _update_table(
    content: str,
    *,
    table_index: int,
    row: int,
    col: int,
    cell_value: str,
    heading: str,
) -> str:
    if row < 0 or col < 0:
        raise MarkdownEditError("Paramètres table_row et table_col requis pour update_table.")

    frontmatter, body = split_frontmatter(content)
    search_body = body
    body_offset = 0
    if heading:
        section = find_section_by_heading(body, heading)
        if section is None:
            raise MarkdownEditError(f"Section introuvable : {heading!r}")
        search_body = body[section.start : section.end]
        body_offset = section.start

    tables = find_tables(search_body)
    if not tables or table_index >= len(tables):
        raise MarkdownEditError(f"Table introuvable (index {table_index}).")

    table = tables[table_index]
    table_text = search_body[table.start : table.end]
    lines = table_text.splitlines()
    data_row_index = row + 2
    if data_row_index >= len(lines):
        raise MarkdownEditError(f"Ligne de table introuvable : {row}")

    cells = [cell.strip() for cell in lines[data_row_index].strip().strip("|").split("|")]
    if col >= len(cells):
        raise MarkdownEditError(f"Colonne introuvable : {col}")

    cells[col] = cell_value
    lines[data_row_index] = "| " + " | ".join(cells) + " |"
    new_table = "\n".join(lines)
    if not table_text.endswith("\n") and body[body_offset + table.end : body_offset + table.end + 1] == "\n":
        new_table = f"{new_table}\n"

    updated_search = (
        f"{search_body[:table.start]}{new_table}{search_body[table.end:]}"
    )
    if heading:
        updated_body = f"{body[:body_offset]}{updated_search}"
    else:
        updated_body = updated_search

    if frontmatter:
        return f"{frontmatter}\n{updated_body}"
    return updated_body


def describe_document(content: str) -> dict[str, object]:
    """Return structural summary for diagnostics."""
    doc: MarkdownDocument = parse_markdown(content)
    return {
        "has_frontmatter": doc.frontmatter is not None,
        "heading_count": len(doc.headings),
        "headings": [section.title for section in doc.headings],
        "checklist_count": len(doc.checklist_items),
        "code_block_count": len(doc.code_blocks),
        "table_count": len(doc.tables),
        "wikilink_count": len(doc.wikilinks),
        "tags": sorted(doc.tags),
    }
