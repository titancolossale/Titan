# =====================================
# Titan Code Editor Exceptions
# =====================================

"""Custom exceptions for Controlled Patch Application V1."""

from __future__ import annotations

from core.exceptions import ToolError


class CodeEditorError(ToolError):
    """Base exception for code editor / patch application failures."""


class CodeEditorConfigurationError(CodeEditorError):
    """Raised when workspace or backup configuration is invalid."""


class CodeEditorPermissionDeniedError(CodeEditorError):
    """Raised when permission evaluation denies a code editor action."""

    def __init__(self, permission_id: str, reason: str) -> None:
        self.permission_id = permission_id
        self.reason = reason
        super().__init__(f"Permission denied for {permission_id}: {reason}")


class CodeEditorValidationError(CodeEditorError):
    """Raised when a GeneratedPatch fails validation before application."""


class CodeEditorConfirmationError(CodeEditorError):
    """Raised when apply/rollback is attempted without explicit confirmation."""


class CodeEditorApprovalError(CodeEditorError):
    """Raised when a GeneratedPatch has not been human-approved."""


class CodeEditorPathError(CodeEditorError):
    """Raised when a patch path escapes the configured workspace."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Invalid patch path '{path}': {reason}")


class CodeEditorTransactionError(CodeEditorError):
    """Raised when a patch transaction cannot be loaded or restored."""
