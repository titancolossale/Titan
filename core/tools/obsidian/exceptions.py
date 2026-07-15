# =====================================
# Titan Obsidian Tool Exceptions
# =====================================

"""Custom exceptions for the core Obsidian vault integration."""

from __future__ import annotations

from core.exceptions import ToolError


class ObsidianError(ToolError):
    """Base exception for Obsidian tool failures."""


class ObsidianConfigurationError(ObsidianError):
    """Raised when Obsidian configuration is invalid or incomplete."""


class ObsidianVaultNotFoundError(ObsidianError):
    """Raised when the configured vault path does not exist."""

    def __init__(self, vault_path: str) -> None:
        self.vault_path = vault_path
        super().__init__(f"Obsidian vault not found: {vault_path}")


class ObsidianVaultAccessError(ObsidianError):
    """Raised when the vault exists but cannot be read."""

    def __init__(self, vault_path: str, reason: str) -> None:
        self.vault_path = vault_path
        self.reason = reason
        super().__init__(f"Obsidian vault access denied for {vault_path}: {reason}")


class ObsidianNotConnectedError(ObsidianError):
    """Raised when an operation requires an active vault connection."""

    def __init__(self) -> None:
        super().__init__("Obsidian client is not connected to a vault.")


class ObsidianNoteNotFoundError(ObsidianError):
    """Raised when a requested note does not exist in the vault."""

    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        super().__init__(f"Obsidian note not found: {relative_path}")


class ObsidianPathTraversalError(ObsidianError):
    """Raised when a path attempts to escape the vault root."""

    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        super().__init__(
            f"Path traversal blocked — path escapes vault root: {relative_path}"
        )


class ObsidianPermissionDeniedError(ObsidianError):
    """Raised when permission evaluation denies an Obsidian action."""

    def __init__(self, permission_id: str, reason: str) -> None:
        self.permission_id = permission_id
        self.reason = reason
        super().__init__(f"Permission denied for {permission_id}: {reason}")


class ObsidianUnsupportedExtensionError(ObsidianError):
    """Raised when a file extension is not allowed by configuration."""

    def __init__(self, extension: str) -> None:
        self.extension = extension
        super().__init__(f"Unsupported note extension: {extension}")


class ObsidianNoteExistsError(ObsidianError):
    """Raised when a write operation targets an existing note."""

    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        super().__init__(f"Obsidian note already exists: {relative_path}")


class ObsidianFolderNotFoundError(ObsidianError):
    """Raised when a folder path does not exist in the vault."""

    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        super().__init__(f"Obsidian folder not found: {relative_path}")


class ObsidianFolderNotEmptyError(ObsidianError):
    """Raised when deleting a folder that still contains entries."""

    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        super().__init__(f"Obsidian folder is not empty: {relative_path}")


class ObsidianInvalidPathError(ObsidianError):
    """Raised when a path is empty or otherwise invalid."""

    def __init__(self, relative_path: str, reason: str) -> None:
        self.relative_path = relative_path
        self.reason = reason
        super().__init__(f"Invalid Obsidian path ({relative_path}): {reason}")
