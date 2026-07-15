# =====================================
# Titan Browser Configuration
# =====================================

"""Configuration for the core read-only Browser tool."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_DOWNLOAD_SIZE = 5 * 1024 * 1024  # 5 MiB
DEFAULT_USER_AGENT = "TitanBot/1.0 (Read-Only Browser Tool)"
DEFAULT_ALLOWED_SCHEMES: tuple[str, ...] = ("http", "https")


@dataclass(frozen=True)
class BrowserConfig:
    """Runtime configuration for read-only HTTP browser access.

    Attributes:
        timeout: Request timeout in seconds.
        max_download_size: Maximum response body size in bytes.
        user_agent: HTTP User-Agent header sent with every request.
        follow_redirects: Whether HTTP redirects are followed automatically.
        allowed_schemes: URL schemes permitted for fetch operations.
    """

    timeout: float = DEFAULT_TIMEOUT_SECONDS
    max_download_size: int = DEFAULT_MAX_DOWNLOAD_SIZE
    user_agent: str = DEFAULT_USER_AGENT
    follow_redirects: bool = True
    allowed_schemes: tuple[str, ...] = DEFAULT_ALLOWED_SCHEMES

    @classmethod
    def from_environment(cls) -> BrowserConfig:
        """Load configuration from Titan environment variables."""
        timeout = float(
            os.getenv("TITAN_BROWSER_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
        )
        max_download_size = int(
            os.getenv("TITAN_BROWSER_MAX_DOWNLOAD_SIZE", str(DEFAULT_MAX_DOWNLOAD_SIZE))
        )
        user_agent = os.getenv("TITAN_BROWSER_USER_AGENT", DEFAULT_USER_AGENT).strip()
        follow_redirects = (
            os.getenv("TITAN_BROWSER_FOLLOW_REDIRECTS", "true").lower() == "true"
        )
        schemes_raw = os.getenv("TITAN_BROWSER_ALLOWED_SCHEMES", "http,https").strip()
        allowed_schemes = tuple(
            scheme.strip().lower()
            for scheme in schemes_raw.split(",")
            if scheme.strip()
        ) or DEFAULT_ALLOWED_SCHEMES

        return cls(
            timeout=max(1.0, timeout),
            max_download_size=max(1024, max_download_size),
            user_agent=user_agent or DEFAULT_USER_AGENT,
            follow_redirects=follow_redirects,
            allowed_schemes=allowed_schemes,
        )
