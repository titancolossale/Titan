# =====================================
# Titan Obsidian Vault Helpers
# =====================================

"""Shared helpers for Obsidian vault path safety, backups, and text editing."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

VAULT_BACKUP_DIR = ".vault_backups"


class EditMode(str, Enum):
    """Supported note editing modes."""

    OVERWRITE = "overwrite"
    APPEND = "append"
    REPLACE = "replace"


def timestamp_utc() -> str:
    """Return a filesystem-safe UTC timestamp for backup filenames."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup_filename(relative_path: str, *, timestamp: str | None = None) -> str:
    """Build a flat backup filename from a vault-relative path."""
    stamp = timestamp or timestamp_utc()
    safe_path = relative_path.replace("\\", "/").strip("/")
    flat_name = safe_path.replace("/", "__")
    return f"{stamp}__{flat_name}"


def create_vault_backup(
    vault_root: Path,
    source: Path,
    *,
    relative_path: str,
) -> str:
    """Copy *source* into ``.vault_backups/`` and return the backup relative path.

    Args:
        vault_root: Resolved vault root directory.
        source: Absolute path to the file or directory being backed up.
        relative_path: Vault-relative path used for backup naming.

    Returns:
        Vault-relative path to the created backup entry.
    """
    backup_root = vault_root / VAULT_BACKUP_DIR
    backup_root.mkdir(parents=True, exist_ok=True)

    backup_name = backup_filename(relative_path)
    destination = backup_root / backup_name

    if source.is_file():
        shutil.copy2(source, destination)
    elif source.is_dir():
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
    else:
        raise FileNotFoundError(f"Backup source does not exist: {source}")

    backup_relative = destination.relative_to(vault_root).as_posix()
    logger.info("Created vault backup: %s -> %s", relative_path, backup_relative)
    return backup_relative


def coerce_edit_mode(mode: EditMode | str) -> EditMode:
    """Normalize an edit mode value to ``EditMode``."""
    if isinstance(mode, EditMode):
        return mode
    return EditMode(str(mode).strip().lower())


def apply_text_edit(
    current: str,
    *,
    mode: EditMode | str,
    content: str = "",
    search: str = "",
    replacement: str = "",
) -> str:
    """Apply a text edit to note content.

    Args:
        current: Existing note body.
        mode: ``overwrite``, ``append``, or ``replace``.
        content: Full body for overwrite/append operations.
        search: Text to find when mode is ``replace``.
        replacement: Replacement text when mode is ``replace``.

    Returns:
        Updated note body.

    Raises:
        ValueError: When replace mode cannot find *search* text.
    """
    normalized = coerce_edit_mode(mode)

    if normalized == EditMode.OVERWRITE:
        return content

    if normalized == EditMode.APPEND:
        if not content:
            return current
        if not current:
            return content
        if current.endswith("\n"):
            return f"{current}{content}"
        return f"{current}\n{content}"

    if normalized == EditMode.REPLACE:
        if not search:
            raise ValueError("Replace mode requires a non-empty search string.")
        if search not in current:
            raise ValueError(f"Search text not found in note: {search!r}")
        return current.replace(search, replacement, 1)

    raise ValueError(f"Unsupported edit mode: {mode!r}")


def ensure_markdown_extension(relative_path: str) -> str:
    """Ensure a note path ends with a ``.md`` extension."""
    path = Path(relative_path.strip().replace("\\", "/"))
    if path.suffix.lower() not in {".md", ".markdown"}:
        return f"{path.as_posix()}.md"
    return path.as_posix()
