# =====================================
# Titan GitHub Tool Exceptions
# =====================================

"""Custom exceptions for the core read-only GitHub tool."""

from __future__ import annotations

from core.exceptions import ToolError


class GitHubError(ToolError):
    """Base exception for GitHub tool failures."""


class GitHubConfigurationError(GitHubError):
    """Raised when GitHub configuration is invalid or incomplete."""


class GitHubAuthenticationError(GitHubError):
    """Raised when the Personal Access Token is missing or rejected."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"GitHub authentication failed: {reason}")


class GitHubApiError(GitHubError):
    """Raised when the GitHub API returns an error response."""

    def __init__(self, status_code: int, reason: str, *, path: str = "") -> None:
        self.status_code = status_code
        self.reason = reason
        self.path = path
        detail = f"GitHub API error ({status_code}): {reason}"
        if path:
            detail = f"{detail} [{path}]"
        super().__init__(detail)


class GitHubNotFoundError(GitHubApiError):
    """Raised when a repository, path, or resource is not found."""

    def __init__(self, resource: str) -> None:
        self.resource = resource
        super().__init__(404, f"Resource not found: {resource}", path=resource)


class GitHubPermissionDeniedError(GitHubError):
    """Raised when permission evaluation denies a GitHub action."""

    def __init__(self, permission_id: str, reason: str) -> None:
        self.permission_id = permission_id
        self.reason = reason
        super().__init__(f"Permission denied for {permission_id}: {reason}")
