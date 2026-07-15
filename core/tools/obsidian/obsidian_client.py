# =====================================
# Titan Obsidian Client
# =====================================

"""Filesystem client for an existing Obsidian vault with bounded read/write access."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from core.tools.obsidian.exceptions import (
    ObsidianConfigurationError,
    ObsidianFolderNotEmptyError,
    ObsidianFolderNotFoundError,
    ObsidianInvalidPathError,
    ObsidianNotConnectedError,
    ObsidianNoteExistsError,
    ObsidianNoteNotFoundError,
    ObsidianPathTraversalError,
    ObsidianUnsupportedExtensionError,
    ObsidianVaultAccessError,
    ObsidianVaultNotFoundError,
)
from core.tools.obsidian.models import NoteContent, NoteMetadata
from core.tools.obsidian.obsidian_config import ObsidianConfig
from core.tools.obsidian.vault_helpers import (
    EditMode,
    apply_text_edit,
    coerce_edit_mode,
    create_vault_backup,
    ensure_markdown_extension,
)

logger = logging.getLogger(__name__)


class ObsidianClient:
    """Connect to and operate on a bounded Obsidian vault directory.

    The client validates vault access, normalizes paths, prevents traversal
    outside the configured vault root, and creates backups before destructive
    write operations.
    """

    def __init__(self, config: ObsidianConfig) -> None:
        self._config = config
        self._vault_root: Path | None = None
        self._connected = False

    @property
    def config(self) -> ObsidianConfig:
        """Return the active client configuration."""
        return self._config

    @property
    def vault_root(self) -> Path | None:
        """Return the resolved vault root when connected."""
        return self._vault_root

    def connect(self) -> None:
        """Validate and connect to the configured vault path."""
        vault_path = self._config.vault_path.expanduser()
        if not vault_path.exists():
            raise ObsidianVaultNotFoundError(str(vault_path))
        if not vault_path.is_dir():
            raise ObsidianConfigurationError(
                f"Obsidian vault path is not a directory: {vault_path}"
            )

        resolved = vault_path.resolve()
        if not os.access(resolved, os.R_OK | os.X_OK):
            raise ObsidianVaultAccessError(
                str(resolved),
                "insufficient filesystem permissions to read the vault",
            )

        self._vault_root = resolved
        self._connected = True
        logger.info("Obsidian client connected to vault: %s", resolved)

    def disconnect(self) -> None:
        """Release the active vault connection."""
        if self._connected:
            logger.info("Obsidian client disconnected from vault: %s", self._vault_root)
        self._vault_root = None
        self._connected = False

    def is_connected(self) -> bool:
        """Return True when the client is connected to a validated vault."""
        return self._connected and self._vault_root is not None

    def list_folders(self) -> list[str]:
        """Return vault-relative folder paths, excluding configured folders."""
        root = self._require_connection()
        folders: list[str] = []

        for dirpath, dirnames, _filenames in os.walk(
            root,
            topdown=True,
            followlinks=self._config.follow_symlinks,
        ):
            current = Path(dirpath)
            dirnames[:] = [
                name
                for name in dirnames
                if not self._is_excluded_folder(name)
            ]

            if current == root:
                continue

            relative = current.relative_to(root).as_posix()
            if not self._path_has_excluded_segment(relative):
                folders.append(relative)

        folders.sort()
        logger.debug("Listed %d folders in vault", len(folders))
        return folders

    def list_files(self) -> list[str]:
        """Return vault-relative note paths matching allowed extensions."""
        root = self._require_connection()
        files: list[str] = []

        for dirpath, dirnames, filenames in os.walk(
            root,
            topdown=True,
            followlinks=self._config.follow_symlinks,
        ):
            dirnames[:] = [
                name
                for name in dirnames
                if not self._is_excluded_folder(name)
            ]

            current = Path(dirpath)
            for filename in filenames:
                path = current / filename
                relative = path.relative_to(root).as_posix()
                if self._path_has_excluded_segment(relative):
                    continue
                if not self._is_allowed_extension(path.suffix):
                    continue
                files.append(relative)

        files.sort()
        logger.debug("Listed %d note files in vault", len(files))
        return files

    def read_note(self, relative_path: str) -> NoteContent:
        """Read a note's content and metadata from the vault."""
        resolved = self._resolve_note_path(relative_path, must_exist=True)
        content = resolved.read_text(encoding=self._config.encoding)
        metadata = self._build_metadata(resolved, self.normalize_relative_path(relative_path))
        logger.info("Read note: %s", metadata.relative_path)
        return NoteContent(
            relative_path=metadata.relative_path,
            content=content,
            metadata=metadata,
        )

    def create_note(self, relative_path: str, content: str = "") -> NoteContent:
        """Create a new note in the vault."""
        self._require_write_access()
        normalized = ensure_markdown_extension(relative_path)
        resolved = self._resolve_note_path(normalized, must_exist=False)
        if resolved.exists():
            raise ObsidianNoteExistsError(self.normalize_relative_path(normalized))

        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding=self._config.encoding)
        metadata = self._build_metadata(resolved, self.normalize_relative_path(normalized))
        logger.info("Created note: %s", metadata.relative_path)
        return NoteContent(
            relative_path=metadata.relative_path,
            content=content,
            metadata=metadata,
        )

    def edit_note(
        self,
        relative_path: str,
        content: str,
        *,
        mode: EditMode | str = EditMode.OVERWRITE,
    ) -> NoteContent:
        """Edit an existing note using overwrite, append, or replace semantics."""
        normalized_mode = coerce_edit_mode(mode)
        if normalized_mode == EditMode.APPEND:
            return self.append_note(relative_path, content)
        if normalized_mode == EditMode.REPLACE:
            raise ObsidianInvalidPathError(
                relative_path,
                "replace mode requires replace_note with search/replacement parameters",
            )

        self._require_write_access()
        resolved = self._resolve_note_path(relative_path, must_exist=True)
        normalized = self.normalize_relative_path(relative_path)
        backup_path = create_vault_backup(
            self._require_connection(),
            resolved,
            relative_path=normalized,
        )
        resolved.write_text(content, encoding=self._config.encoding)
        note = self.read_note(normalized)
        logger.info(
            "Edited note (overwrite): %s backup=%s",
            normalized,
            backup_path,
        )
        return note

    def append_note(self, relative_path: str, content: str) -> NoteContent:
        """Append content to an existing note."""
        self._require_write_access()
        resolved = self._resolve_note_path(relative_path, must_exist=True)
        normalized = self.normalize_relative_path(relative_path)
        current = resolved.read_text(encoding=self._config.encoding)
        updated = apply_text_edit(current, mode=EditMode.APPEND, content=content)
        resolved.write_text(updated, encoding=self._config.encoding)
        note = self.read_note(normalized)
        logger.info("Appended to note: %s", normalized)
        return note

    def replace_note(
        self,
        relative_path: str,
        *,
        search: str,
        replacement: str = "",
    ) -> NoteContent:
        """Replace the first occurrence of selected text in a note."""
        self._require_write_access()
        resolved = self._resolve_note_path(relative_path, must_exist=True)
        normalized = self.normalize_relative_path(relative_path)
        backup_path = create_vault_backup(
            self._require_connection(),
            resolved,
            relative_path=normalized,
        )
        current = resolved.read_text(encoding=self._config.encoding)
        try:
            updated = apply_text_edit(
                current,
                mode=EditMode.REPLACE,
                search=search,
                replacement=replacement,
            )
        except ValueError as exc:
            raise ObsidianInvalidPathError(normalized, str(exc)) from exc

        resolved.write_text(updated, encoding=self._config.encoding)
        note = self.read_note(normalized)
        logger.info(
            "Replaced text in note: %s backup=%s",
            normalized,
            backup_path,
        )
        return note

    def delete_note(self, relative_path: str) -> dict[str, object]:
        """Delete a note after creating a backup."""
        self._require_write_access()
        resolved = self._resolve_note_path(relative_path, must_exist=True)
        normalized = self.normalize_relative_path(relative_path)
        backup_path = create_vault_backup(
            self._require_connection(),
            resolved,
            relative_path=normalized,
        )
        resolved.unlink()
        logger.info("Deleted note: %s backup=%s", normalized, backup_path)
        return {
            "relative_path": normalized,
            "backup_path": backup_path,
            "deleted": True,
        }

    def rename_note(self, relative_path: str, new_path: str) -> dict[str, object]:
        """Rename a note within the vault after creating a backup."""
        self._require_write_access()
        source = self._resolve_note_path(relative_path, must_exist=True)
        source_normalized = self.normalize_relative_path(relative_path)
        target_normalized = ensure_markdown_extension(new_path)
        target = self._resolve_note_path(target_normalized, must_exist=False)

        if target.exists():
            raise ObsidianNoteExistsError(self.normalize_relative_path(target_normalized))

        backup_path = create_vault_backup(
            self._require_connection(),
            source,
            relative_path=source_normalized,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
        result_path = self.normalize_relative_path(target_normalized)
        logger.info(
            "Renamed note: %s -> %s backup=%s",
            source_normalized,
            result_path,
            backup_path,
        )
        return {
            "source_path": source_normalized,
            "destination_path": result_path,
            "backup_path": backup_path,
        }

    def move_note(self, relative_path: str, destination_folder: str) -> dict[str, object]:
        """Move a note into another vault folder after creating a backup."""
        self._require_write_access()
        source = self._resolve_note_path(relative_path, must_exist=True)
        source_normalized = self.normalize_relative_path(relative_path)
        destination = self._resolve_folder_path(destination_folder, must_exist=False)
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / source.name

        if target.exists() and target.resolve() != source.resolve():
            raise ObsidianNoteExistsError(
                self.normalize_relative_path(
                    target.relative_to(self._require_connection()).as_posix()
                )
            )

        backup_path = create_vault_backup(
            self._require_connection(),
            source,
            relative_path=source_normalized,
        )

        if target.resolve() != source.resolve():
            source.rename(target)

        result_path = target.relative_to(self._require_connection()).as_posix()
        logger.info(
            "Moved note: %s -> %s backup=%s",
            source_normalized,
            result_path,
            backup_path,
        )
        return {
            "source_path": source_normalized,
            "destination_path": result_path,
            "backup_path": backup_path,
        }

    def create_folder(self, relative_path: str) -> dict[str, object]:
        """Create a folder inside the vault."""
        self._require_write_access()
        resolved = self._resolve_folder_path(relative_path, must_exist=False)
        if resolved.exists() and not resolved.is_dir():
            raise ObsidianInvalidPathError(
                relative_path,
                "a file already exists at the target folder path",
            )
        resolved.mkdir(parents=True, exist_ok=True)
        folder_path = resolved.relative_to(self._require_connection()).as_posix()
        logger.info("Created folder: %s", folder_path)
        return {"folder_path": folder_path, "created": True}

    def delete_folder(self, relative_path: str) -> dict[str, object]:
        """Delete an empty folder from the vault."""
        self._require_write_access()
        resolved = self._resolve_folder_path(relative_path, must_exist=True)
        if not resolved.is_dir():
            raise ObsidianFolderNotFoundError(self.normalize_relative_path(relative_path))

        entries = list(resolved.iterdir())
        if entries:
            raise ObsidianFolderNotEmptyError(
                resolved.relative_to(self._require_connection()).as_posix()
            )

        backup_path = create_vault_backup(
            self._require_connection(),
            resolved,
            relative_path=resolved.relative_to(self._require_connection()).as_posix(),
        )
        resolved.rmdir()
        folder_path = self.normalize_relative_path(relative_path)
        logger.info("Deleted folder: %s backup=%s", folder_path, backup_path)
        return {
            "folder_path": folder_path,
            "backup_path": backup_path,
            "deleted": True,
        }

    def note_exists(self, relative_path: str) -> bool:
        """Return True when the normalized note path exists in the vault."""
        root = self._require_connection()
        try:
            resolved = self._resolve_note_path(relative_path, must_exist=False)
        except (ObsidianPathTraversalError, ObsidianUnsupportedExtensionError):
            return False
        return resolved.exists() and resolved.is_file()

    def get_note_metadata(self, relative_path: str) -> NoteMetadata:
        """Return filesystem metadata for a note without reading its body."""
        resolved = self._resolve_note_path(relative_path, must_exist=True)
        if not resolved.is_file():
            raise ObsidianNoteNotFoundError(self.normalize_relative_path(relative_path))
        metadata = self._build_metadata(
            resolved,
            self.normalize_relative_path(relative_path),
        )
        logger.info("Fetched note metadata: %s", metadata.relative_path)
        return metadata

    def normalize_relative_path(self, relative_path: str) -> str:
        """Normalize a vault-relative path and reject traversal attempts."""
        if not relative_path or not str(relative_path).strip():
            raise ObsidianPathTraversalError(relative_path)

        candidate = Path(str(relative_path).strip().replace("\\", "/"))
        if candidate.is_absolute() or os.path.isabs(str(relative_path).strip()):
            raise ObsidianPathTraversalError(relative_path)

        parts: list[str] = []
        for part in candidate.parts:
            if part in ("", "."):
                continue
            if part == "..":
                raise ObsidianPathTraversalError(relative_path)
            parts.append(part)

        if not parts:
            raise ObsidianPathTraversalError(relative_path)

        normalized = Path(*parts).as_posix()
        if self._path_has_excluded_segment(normalized):
            raise ObsidianPathTraversalError(relative_path)
        return normalized

    def _require_connection(self) -> Path:
        if not self.is_connected() or self._vault_root is None:
            raise ObsidianNotConnectedError()
        return self._vault_root

    def _require_write_access(self) -> None:
        root = self._require_connection()
        if not os.access(root, os.W_OK):
            raise ObsidianVaultAccessError(
                str(root),
                "insufficient filesystem permissions to write to the vault",
            )

    def _resolve_bounded_path(
        self,
        relative_path: str,
        *,
        must_exist: bool,
        expect_file: bool = False,
        expect_dir: bool = False,
    ) -> Path:
        """Resolve a path under the vault root and reject escape attempts."""
        root = self._require_connection()
        normalized = self.normalize_relative_path(relative_path)
        candidate = root / normalized
        resolved = candidate.resolve()

        try:
            resolved.relative_to(root.resolve())
        except ValueError as exc:
            raise ObsidianPathTraversalError(relative_path) from exc

        if resolved.is_symlink():
            link_target = resolved.resolve()
            try:
                link_target.relative_to(root.resolve())
            except ValueError as exc:
                raise ObsidianPathTraversalError(relative_path) from exc
            resolved = link_target

        if must_exist and not resolved.exists():
            if expect_dir:
                raise ObsidianFolderNotFoundError(normalized)
            raise ObsidianNoteNotFoundError(normalized)

        if expect_file and resolved.exists() and not resolved.is_file():
            raise ObsidianInvalidPathError(normalized, "expected a file")

        if expect_dir and resolved.exists() and not resolved.is_dir():
            raise ObsidianInvalidPathError(normalized, "expected a folder")

        return resolved

    def _resolve_note_path(self, relative_path: str, *, must_exist: bool) -> Path:
        normalized = self.normalize_relative_path(
            ensure_markdown_extension(relative_path),
        )
        if not self._is_allowed_extension(Path(normalized).suffix):
            raise ObsidianUnsupportedExtensionError(Path(normalized).suffix)

        return self._resolve_bounded_path(
            normalized,
            must_exist=must_exist,
            expect_file=must_exist,
        )

    def _resolve_folder_path(self, relative_path: str, *, must_exist: bool) -> Path:
        normalized = self.normalize_relative_path(relative_path)
        return self._resolve_bounded_path(
            normalized,
            must_exist=must_exist,
            expect_dir=must_exist,
        )

    def _build_metadata(self, resolved: Path, relative_path: str) -> NoteMetadata:
        stat = resolved.stat()
        created = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        return NoteMetadata(
            filename=resolved.name,
            extension=resolved.suffix.lower(),
            size=stat.st_size,
            created=created,
            modified=modified,
            relative_path=relative_path,
        )

    def _is_allowed_extension(self, extension: str) -> bool:
        normalized = extension.lower()
        return normalized in {item.lower() for item in self._config.allowed_extensions}

    def _is_excluded_folder(self, folder_name: str) -> bool:
        return folder_name in self._config.excluded_folders

    def _path_has_excluded_segment(self, relative_path: str) -> bool:
        return any(
            segment in self._config.excluded_folders
            for segment in Path(relative_path).parts
        )
