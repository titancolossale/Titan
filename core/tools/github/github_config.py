# =====================================
# Titan GitHub Configuration
# =====================================

"""Configuration for the core read-only GitHub tool."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_API_BASE_URL = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_RETRY_COUNT = 2
DEFAULT_PER_PAGE = 30
DEFAULT_USER_AGENT = "TitanBot/1.0 (Read-Only GitHub Tool)"


@dataclass(frozen=True)
class GitHubConfig:
    """Runtime configuration for read-only GitHub API access.

    Attributes:
        token: Personal Access Token (never hardcoded; loaded from environment).
        api_base_url: GitHub REST API base URL.
        timeout_seconds: Request timeout in seconds.
        retry_count: Number of retries for transient failures.
        per_page: Default page size for list endpoints.
        user_agent: HTTP User-Agent header sent with every request.
    """

    token: str = ""
    api_base_url: str = DEFAULT_API_BASE_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    retry_count: int = DEFAULT_RETRY_COUNT
    per_page: int = DEFAULT_PER_PAGE
    user_agent: str = DEFAULT_USER_AGENT

    @property
    def has_token(self) -> bool:
        """Return True when a non-empty token is configured."""
        return bool(self.token.strip())

    @classmethod
    def from_environment(cls) -> GitHubConfig:
        """Load configuration from Titan environment variables.

        Secrets are read only from the environment — never hardcoded.
        """
        token = os.getenv("TITAN_GITHUB_TOKEN", "").strip()
        api_base = os.getenv("TITAN_GITHUB_API_BASE_URL", DEFAULT_API_BASE_URL).strip()
        timeout = float(
            os.getenv("TITAN_GITHUB_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
        )
        retry_count = int(
            os.getenv("TITAN_GITHUB_RETRY_COUNT", str(DEFAULT_RETRY_COUNT))
        )
        per_page = int(os.getenv("TITAN_GITHUB_PER_PAGE", str(DEFAULT_PER_PAGE)))
        user_agent = os.getenv("TITAN_GITHUB_USER_AGENT", DEFAULT_USER_AGENT).strip()

        return cls(
            token=token,
            api_base_url=(api_base or DEFAULT_API_BASE_URL).rstrip("/"),
            timeout_seconds=max(1.0, timeout),
            retry_count=max(0, retry_count),
            per_page=max(1, min(per_page, 100)),
            user_agent=user_agent or DEFAULT_USER_AGENT,
        )
