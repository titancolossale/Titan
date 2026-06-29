# =====================================
# Titan Exceptions
# =====================================

"""Application exception hierarchy (Phase 10A — P10A-001)."""

from __future__ import annotations


class TitanError(Exception):
    """Base exception for recoverable Titan subsystem failures."""


class ToolError(TitanError):
    """Base exception for tool runtime failures."""


class ToolNotFoundError(ToolError):
    """Raised when a tool name is not registered."""


class ToolValidationError(ToolError):
    """Raised when tool parameters fail schema validation."""


class ToolPermissionDenied(ToolError):
    """Raised when caller, user, or policy blocks tool invocation."""


class ToolConfirmationRequired(ToolError):
    """Raised when execution requires explicit user approval."""


class ToolTimeoutError(ToolError):
    """Raised when tool execution exceeds its timeout budget."""


class ToolCancelledError(ToolError):
    """Raised when a run is cancelled by user or system."""


class ToolQuotaExceeded(ToolError):
    """Raised when usage quota limits block invocation."""


class ToolDependencyError(ToolError):
    """Raised when a required tool dependency is unavailable."""


class ToolHealthError(ToolError):
    """Raised when tool or provider health prevents execution."""


class ProviderError(ToolError):
    """Base exception for provider-layer failures."""


class ProviderUnavailable(ProviderError):
    """Raised when a provider is offline or not configured."""


class ProviderVersionIncompatible(ProviderError):
    """Raised when a provider requires a newer tool runtime version."""
