# =====================================
# Titan Browser Tool Exceptions
# =====================================

"""Custom exceptions for the core read-only Browser tool."""

from __future__ import annotations

from core.exceptions import ToolError


class BrowserError(ToolError):
    """Base exception for Browser tool failures."""


class BrowserConfigurationError(BrowserError):
    """Raised when Browser configuration is invalid or incomplete."""


class BrowserInvalidUrlError(BrowserError):
    """Raised when a URL fails safety validation."""

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"Invalid or blocked URL: {reason}")


class BrowserFetchError(BrowserError):
    """Raised when an HTTP request fails."""

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"Browser fetch failed for {url}: {reason}")


class BrowserResponseTooLargeError(BrowserError):
    """Raised when a response exceeds the configured download limit."""

    def __init__(self, url: str, max_size: int) -> None:
        self.url = url
        self.max_size = max_size
        super().__init__(
            f"Response from {url} exceeds max download size ({max_size} bytes)."
        )


class BrowserPermissionDeniedError(BrowserError):
    """Raised when permission evaluation denies a Browser action."""

    def __init__(self, permission_id: str, reason: str) -> None:
        self.permission_id = permission_id
        self.reason = reason
        super().__init__(f"Permission denied for {permission_id}: {reason}")
