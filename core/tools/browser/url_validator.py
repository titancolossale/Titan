# =====================================
# Titan Browser URL Validator
# =====================================

"""Safe URL validation for read-only browser fetch operations."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

from core.tools.browser.browser_config import BrowserConfig
from core.tools.browser.exceptions import BrowserInvalidUrlError

_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "0.0.0.0",
        "::1",
    }
)

_IPV4_LITERAL = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def validate_url(url: str, config: BrowserConfig) -> str:
    """Validate and normalize a URL for safe HTTP fetching.

    Args:
        url: User-supplied URL string.
        config: Browser configuration with allowed schemes.

    Returns:
        Normalized URL string.

    Raises:
        BrowserInvalidUrlError: When the URL is malformed or blocked.
    """
    candidate = url.strip()
    if not candidate:
        raise BrowserInvalidUrlError(url, "URL is empty")

    parsed = urlparse(candidate)
    if not parsed.scheme or not parsed.netloc:
        raise BrowserInvalidUrlError(url, "URL must include scheme and host")

    scheme = parsed.scheme.lower()
    if scheme not in config.allowed_schemes:
        raise BrowserInvalidUrlError(
            url,
            f"Scheme '{scheme}' is not allowed (permitted: {', '.join(config.allowed_schemes)})",
        )

    if scheme in {"file", "ftp", "javascript", "data"}:
        raise BrowserInvalidUrlError(url, f"Scheme '{scheme}' is blocked")

    hostname = parsed.hostname
    if hostname is None:
        raise BrowserInvalidUrlError(url, "URL host is missing")

    host_lower = hostname.lower().rstrip(".")
    if host_lower in _BLOCKED_HOSTNAMES:
        raise BrowserInvalidUrlError(url, f"Host '{hostname}' is blocked")

    if host_lower.endswith(".localhost"):
        raise BrowserInvalidUrlError(url, f"Host '{hostname}' is blocked")

    if _is_blocked_ip(hostname):
        raise BrowserInvalidUrlError(url, f"Host '{hostname}' resolves to a blocked address")

    return candidate


def _is_blocked_ip(host: str) -> bool:
    """Return True when the host is a blocked IP address."""
    candidate = host
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]

    if not _IPV4_LITERAL.match(candidate) and ":" not in candidate:
        return False

    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return False

    if address.is_loopback:
        return True
    if address.is_private:
        return True
    if address.is_link_local:
        return True
    if address.is_multicast:
        return True
    if address.is_reserved:
        return True
    if address.is_unspecified:
        return True

    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        mapped = address.ipv4_mapped
        if mapped.is_loopback or mapped.is_private or mapped.is_link_local:
            return True

    return False
