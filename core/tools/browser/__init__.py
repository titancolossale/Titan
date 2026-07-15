# =====================================
# Titan Browser Tool Package
# =====================================

"""Read-only HTTP browser integration for Titan's core tool layer."""

from core.tools.browser.browser_client import BrowserClient
from core.tools.browser.browser_config import BrowserConfig
from core.tools.browser.browser_tool import (
    CAPABILITY_EXTRACT_LINKS,
    CAPABILITY_EXTRACT_TEXT,
    CAPABILITY_FETCH_HTML,
    CAPABILITY_OPEN_URL,
    CAPABILITY_PAGE_METADATA,
    BrowserTool,
    PERMISSION_EXTRACT,
    PERMISSION_FETCH,
    PERMISSION_OPEN_URL,
)
from core.tools.browser.exceptions import (
    BrowserConfigurationError,
    BrowserError,
    BrowserFetchError,
    BrowserInvalidUrlError,
    BrowserPermissionDeniedError,
    BrowserResponseTooLargeError,
)
from core.tools.browser.models import ExtractedLink, PageMetadata, PageResponse

__all__ = [
    "BrowserClient",
    "BrowserConfig",
    "BrowserConfigurationError",
    "BrowserError",
    "BrowserFetchError",
    "BrowserInvalidUrlError",
    "BrowserPermissionDeniedError",
    "BrowserResponseTooLargeError",
    "BrowserTool",
    "CAPABILITY_EXTRACT_LINKS",
    "CAPABILITY_EXTRACT_TEXT",
    "CAPABILITY_FETCH_HTML",
    "CAPABILITY_OPEN_URL",
    "CAPABILITY_PAGE_METADATA",
    "ExtractedLink",
    "PageMetadata",
    "PageResponse",
    "PERMISSION_EXTRACT",
    "PERMISSION_FETCH",
    "PERMISSION_OPEN_URL",
]
