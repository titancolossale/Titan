# =====================================
# Titan Python Runtime Exceptions
# =====================================

"""Custom exceptions for the core Python Runtime tool."""

from __future__ import annotations

from core.exceptions import ToolError, ToolTimeoutError


class PythonRuntimeError(ToolError):
    """Base exception for Python Runtime tool failures."""


class PythonConfigurationError(PythonRuntimeError):
    """Raised when Python Runtime configuration is invalid or incomplete."""


class PythonSyntaxError(PythonRuntimeError):
    """Raised when source code fails syntax validation."""

    def __init__(self, message: str, *, line: int | None = None) -> None:
        self.line = line
        super().__init__(message)


class PythonExecutionTimeoutError(PythonRuntimeError, ToolTimeoutError):
    """Raised when Python execution exceeds the configured timeout."""

    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Python execution interrupted after {timeout_seconds}s (timeout)."
        )


class PythonOutputTooLargeError(PythonRuntimeError):
    """Raised when captured stdout/stderr exceeds the configured limit."""

    def __init__(self, max_output_bytes: int) -> None:
        self.max_output_bytes = max_output_bytes
        super().__init__(
            f"Python output exceeds max size ({max_output_bytes} bytes)."
        )


class PythonWorkspaceLimitError(PythonRuntimeError):
    """Raised when workspace file-count limits are exceeded."""

    def __init__(self, max_file_count: int) -> None:
        self.max_file_count = max_file_count
        super().__init__(
            f"Python workspace exceeds max file count ({max_file_count})."
        )


class PythonPathError(PythonRuntimeError):
    """Raised when a script path escapes the allowed workspace root."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Invalid script path '{path}': {reason}")


class PythonPermissionDeniedError(PythonRuntimeError):
    """Raised when permission evaluation denies a Python Runtime action."""

    def __init__(self, permission_id: str, reason: str) -> None:
        self.permission_id = permission_id
        self.reason = reason
        super().__init__(f"Permission denied for {permission_id}: {reason}")
