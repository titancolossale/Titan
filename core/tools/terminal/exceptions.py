# =====================================
# Titan Terminal Tool Exceptions
# =====================================

"""Custom exceptions for the core Terminal tool."""

from __future__ import annotations

from core.exceptions import ToolError, ToolTimeoutError


class TerminalRuntimeError(ToolError):
    """Base exception for Terminal tool failures."""


class TerminalConfigurationError(TerminalRuntimeError):
    """Raised when Terminal configuration is invalid or incomplete."""


class TerminalSecurityError(TerminalRuntimeError):
    """Raised when a command is blocked by Terminal security policy."""

    def __init__(self, command: str, reason: str) -> None:
        self.command = command
        self.reason = reason
        super().__init__(f"Blocked command '{command}': {reason}")


class TerminalPathError(TerminalRuntimeError):
    """Raised when a working directory escapes the configured workspace."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Invalid working directory '{path}': {reason}")


class TerminalExecutionTimeoutError(TerminalRuntimeError, ToolTimeoutError):
    """Raised when a Terminal command exceeds the configured timeout."""

    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Terminal command interrupted after {timeout_seconds}s (timeout)."
        )


class TerminalOutputTooLargeError(TerminalRuntimeError):
    """Raised when captured stdout/stderr exceeds the configured limit."""

    def __init__(self, max_output_bytes: int) -> None:
        self.max_output_bytes = max_output_bytes
        super().__init__(
            f"Terminal output exceeds max size ({max_output_bytes} bytes)."
        )


class TerminalPermissionDeniedError(TerminalRuntimeError):
    """Raised when permission evaluation denies a Terminal action."""

    def __init__(self, permission_id: str, reason: str) -> None:
        self.permission_id = permission_id
        self.reason = reason
        super().__init__(f"Permission denied for {permission_id}: {reason}")
