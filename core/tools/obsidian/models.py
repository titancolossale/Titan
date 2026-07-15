# =====================================
# Titan Obsidian Tool Models
# =====================================

"""Structured data models for Obsidian vault operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NoteMetadata:
    """Filesystem metadata for a note inside the vault.

    Attributes:
        filename: Base name including extension.
        extension: File extension including the leading dot.
        size: File size in bytes.
        created: Creation timestamp from the filesystem.
        modified: Last modification timestamp from the filesystem.
        relative_path: Vault-relative POSIX path to the note.
    """

    filename: str
    extension: str
    size: int
    created: datetime
    modified: datetime
    relative_path: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "filename": self.filename,
            "extension": self.extension,
            "size": self.size,
            "created": self.created.isoformat(),
            "modified": self.modified.isoformat(),
            "relative_path": self.relative_path,
        }


@dataclass(frozen=True)
class NoteContent:
    """Note body and metadata returned by read operations."""

    relative_path: str
    content: str
    metadata: NoteMetadata

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "relative_path": self.relative_path,
            "content": self.content,
            "metadata": self.metadata.to_dict(),
        }
