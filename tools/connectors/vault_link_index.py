# =====================================
# Titan Vault Link Index
# =====================================

"""Backlink and wikilink indexing for Obsidian vault operations (Phase 22.0)."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from tools.connectors.markdown_parser import extract_wikilinks, parse_markdown

_WIKILINK_REPLACE_RE = re.compile(
    r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]",
)


def note_display_name(relative_path: str) -> str:
    """Return a user-facing note label without exposing vault filesystem paths."""
    stem = Path(relative_path.replace("\\", "/")).stem
    return stem.replace("-", " ").replace("_", " ").strip() or "Note"


def wikilink_target_stem(link_target: str) -> str:
    """Normalize a wikilink target to a comparable note stem."""
    target = link_target.split("|")[0].strip()
    return Path(target.replace("\\", "/")).stem.lower()


def build_backlink_index(
    note_paths: list[str],
    read_content: Callable[[str], str],
) -> dict[str, list[str]]:
    """
    Map note stem (lowercase) to relative paths of notes that link to it.

    Args:
        note_paths: Vault-relative markdown paths.
        read_content: Callable accepting a relative path and returning note text.
    """
    index: dict[str, list[str]] = {}
    for source_path in note_paths:
        try:
            content = read_content(source_path)
        except OSError:
            continue
        for link in extract_wikilinks(content):
            stem = wikilink_target_stem(link)
            if not stem:
                continue
            index.setdefault(stem, [])
            if source_path not in index[stem]:
                index[stem].append(source_path)
    return index


def collect_outlink_stems(content: str) -> list[str]:
    """Return wikilink target stems from note content."""
    return [wikilink_target_stem(link) for link in extract_wikilinks(content)]


def rewrite_wikilinks_after_rename(
    content: str,
    old_stem: str,
    new_stem: str,
) -> str:
    """Rewrite wikilinks pointing at *old_stem* to use *new_stem*."""
    old_lower = old_stem.lower()

    def replace(match: re.Match[str]) -> str:
        target = match.group(1)
        alias = match.group(2)
        if wikilink_target_stem(target) != old_lower:
            return match.group(0)
        if alias:
            return f"[[{new_stem}|{alias}]]"
        return f"[[{new_stem}]]"

    return _WIKILINK_REPLACE_RE.sub(replace, content)


def collect_vault_tags(
    note_paths: list[str],
    read_content: Callable[[str], str],
) -> dict[str, list[str]]:
    """Map tag (lowercase) to note paths that contain it."""
    tag_index: dict[str, list[str]] = {}
    for note_path in note_paths:
        try:
            content = read_content(note_path)
        except OSError:
            continue
        doc = parse_markdown(content)
        for tag in doc.tags:
            tag_index.setdefault(tag, [])
            if note_path not in tag_index[tag]:
                tag_index[tag].append(note_path)
    return tag_index
