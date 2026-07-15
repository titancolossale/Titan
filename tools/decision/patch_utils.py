# =====================================
# Titan Tool Decision — Patch Utils
# =====================================

"""Unified diff parsing and application helpers (Phase 12 — P12-001)."""

from __future__ import annotations

import re
from dataclasses import dataclass


_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class _DiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[tuple[str, str], ...]


def apply_unified_diff(original: str, unified_diff: str) -> str:
    """Apply a unified diff to original text content."""
    if not unified_diff.strip():
        return original

    hunks = _parse_hunks(unified_diff)
    if not hunks:
        return _extract_added_lines(unified_diff) if not original else original

    orig_lines = _split_lines(original)
    result: list[str] = []
    orig_idx = 0

    for hunk in hunks:
        target_idx = max(hunk.old_start - 1, 0)
        while orig_idx < target_idx and orig_idx < len(orig_lines):
            result.append(orig_lines[orig_idx])
            orig_idx += 1

        for op, text in hunk.lines:
            if op == " ":
                if orig_idx < len(orig_lines):
                    result.append(orig_lines[orig_idx])
                else:
                    result.append(text)
                orig_idx += 1
            elif op == "-":
                orig_idx += 1
            elif op == "+":
                result.append(text)

    while orig_idx < len(orig_lines):
        result.append(orig_lines[orig_idx])
        orig_idx += 1

    return _join_lines(result, original)


def _parse_hunks(unified_diff: str) -> list[_DiffHunk]:
    hunks: list[_DiffHunk] = []
    current_lines: list[tuple[str, str]] = []
    current_header: _DiffHunk | None = None

    for raw_line in unified_diff.splitlines():
        if raw_line.startswith("@@"):
            if current_header is not None:
                hunks.append(
                    _DiffHunk(
                        old_start=current_header.old_start,
                        old_count=current_header.old_count,
                        new_start=current_header.new_start,
                        new_count=current_header.new_count,
                        lines=tuple(current_lines),
                    ),
                )
            match = _HUNK_HEADER.match(raw_line.strip())
            if match is None:
                current_lines = []
                current_header = None
                continue
            old_count = int(match.group(2) or "1")
            new_count = int(match.group(4) or "1")
            current_header = _DiffHunk(
                old_start=int(match.group(1)),
                old_count=old_count,
                new_start=int(match.group(3)),
                new_count=new_count,
                lines=(),
            )
            current_lines = []
            continue

        if current_header is None:
            continue

        if raw_line.startswith(" "):
            current_lines.append((" ", raw_line[1:] + "\n"))
        elif raw_line.startswith("+"):
            current_lines.append(("+", raw_line[1:] + "\n"))
        elif raw_line.startswith("-"):
            current_lines.append(("-", raw_line[1:] + "\n"))

    if current_header is not None:
        hunks.append(
            _DiffHunk(
                old_start=current_header.old_start,
                old_count=current_header.old_count,
                new_start=current_header.new_start,
                new_count=current_header.new_count,
                lines=tuple(current_lines),
            ),
        )
    return hunks


def _extract_added_lines(unified_diff: str) -> str:
    added: list[str] = []
    for raw_line in unified_diff.splitlines():
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            added.append(raw_line[1:] + "\n")
    return "".join(added)


def _split_lines(content: str) -> list[str]:
    if not content:
        return []
    lines = content.splitlines(keepends=True)
    if not lines and content:
        return [content]
    return lines


def _join_lines(lines: list[str], original: str) -> str:
    body = "".join(lines)
    if original.endswith("\n") and body and not body.endswith("\n"):
        body += "\n"
    return body


def is_binary_content(content: str | bytes) -> bool:
    """Return True when content appears binary (null bytes or invalid UTF-8)."""
    if isinstance(content, bytes):
        if b"\x00" in content:
            return True
        try:
            content.decode("utf-8")
            return False
        except UnicodeDecodeError:
            return True
    return "\x00" in content
