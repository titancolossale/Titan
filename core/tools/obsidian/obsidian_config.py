# =====================================
# Titan Obsidian Configuration
# =====================================

"""Configuration for the core Obsidian vault client."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_ALLOWED_EXTENSIONS: tuple[str, ...] = (".md", ".markdown")
DEFAULT_EXCLUDED_FOLDERS: tuple[str, ...] = (
    ".obsidian",
    ".trash",
    ".git",
    ".vault_backups",
)
DEFAULT_ENCODING = "utf-8"


@dataclass(frozen=True)
class ObsidianConfig:
    """Runtime configuration for Obsidian vault access.

    Attributes:
        vault_path: Absolute or relative path to the user's existing vault.
        allowed_extensions: Note extensions permitted for read operations.
        excluded_folders: Folder names skipped during traversal.
        follow_symlinks: Whether directory walks may follow symbolic links.
        encoding: Text encoding used when reading note contents.
    """

    vault_path: Path
    allowed_extensions: tuple[str, ...] = DEFAULT_ALLOWED_EXTENSIONS
    excluded_folders: tuple[str, ...] = DEFAULT_EXCLUDED_FOLDERS
    follow_symlinks: bool = False
    encoding: str = DEFAULT_ENCODING

    @classmethod
    def for_vault(
        cls,
        vault_path: Path | str,
        *,
        allowed_extensions: tuple[str, ...] | None = None,
        excluded_folders: tuple[str, ...] | None = None,
        follow_symlinks: bool = False,
        encoding: str = DEFAULT_ENCODING,
    ) -> ObsidianConfig:
        """Build a configuration for a specific vault path."""
        return cls(
            vault_path=Path(vault_path).expanduser(),
            allowed_extensions=allowed_extensions or DEFAULT_ALLOWED_EXTENSIONS,
            excluded_folders=excluded_folders or DEFAULT_EXCLUDED_FOLDERS,
            follow_symlinks=follow_symlinks,
            encoding=encoding,
        )

    @classmethod
    def from_environment(cls, *, fallback_vault: Path | None = None) -> ObsidianConfig:
        """Load configuration from Titan settings with an optional fallback vault."""
        try:
            from config.settings import TITAN_OBSIDIAN_VAULT_PATH
        except ImportError:
            vault_path = fallback_vault
        else:
            vault_path = TITAN_OBSIDIAN_VAULT_PATH or fallback_vault

        if vault_path is None:
            raise ValueError("No Obsidian vault path configured.")

        return cls.for_vault(vault_path)
