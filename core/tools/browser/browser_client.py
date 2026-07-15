# =====================================
# Titan Browser Client
# =====================================

"""HTTP client for read-only web page retrieval."""

from __future__ import annotations

import logging
from typing import Callable

import httpx

from core.exceptions import ToolTimeoutError
from core.tools.browser.browser_config import BrowserConfig
from core.tools.browser.exceptions import (
    BrowserFetchError,
    BrowserInvalidUrlError,
    BrowserResponseTooLargeError,
)
from core.tools.browser.html_parser import extract_language, extract_title
from core.tools.browser.models import PageResponse
from core.tools.browser.url_validator import validate_url

logger = logging.getLogger(__name__)

HttpHandler = Callable[[httpx.Request], httpx.Response]


class BrowserClient:
    """Fetch web pages over HTTP/HTTPS with safety limits.

    The client validates URLs, enforces download size limits, supports redirects,
    and logs every request without exposing sensitive response content.
    """

    def __init__(
        self,
        config: BrowserConfig | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        handler: HttpHandler | None = None,
    ) -> None:
        self._config = config or BrowserConfig.from_environment()
        if handler is not None and transport is not None:
            raise BrowserFetchError("", "Provide either transport or handler, not both")

        if handler is not None:
            transport = httpx.MockTransport(handler)

        timeout = httpx.Timeout(self._config.timeout)
        self._client = httpx.Client(
            transport=transport,
            timeout=timeout,
            follow_redirects=self._config.follow_redirects,
            headers={"User-Agent": self._config.user_agent},
        )

    @property
    def config(self) -> BrowserConfig:
        """Return the active client configuration."""
        return self._config

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def fetch_page(self, url: str) -> PageResponse:
        """Fetch a URL and return structured page data.

        Args:
            url: Target URL (http or https).

        Returns:
            Parsed page response including HTML body and metadata.

        Raises:
            BrowserInvalidUrlError: When URL validation fails.
            BrowserFetchError: When the HTTP request fails.
            BrowserResponseTooLargeError: When the body exceeds max size.
            ToolTimeoutError: When the request times out.
        """
        validated_url = validate_url(url, self._config)
        logger.info("Browser request started: url=%s", _safe_url_for_log(validated_url))

        try:
            response = self._client.get(validated_url)
        except httpx.TimeoutException as exc:
            logger.warning(
                "Browser request timed out: url=%s timeout=%ss",
                _safe_url_for_log(validated_url),
                self._config.timeout,
            )
            raise ToolTimeoutError(
                f"Browser request timed out after {self._config.timeout}s"
            ) from exc
        except httpx.RequestError as exc:
            reason = str(exc) or exc.__class__.__name__
            logger.warning(
                "Browser request failed: url=%s error=%s",
                _safe_url_for_log(validated_url),
                reason,
            )
            raise BrowserFetchError(validated_url, reason) from exc

        body = _read_limited_body(response, self._config.max_download_size, validated_url)
        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        content_language = response.headers.get("content-language", "")
        html = _decode_body(body, content_type)
        title = extract_title(html)
        language = extract_language(html, content_language)

        final_url = str(response.url)
        logger.info(
            "Browser request completed: url=%s status=%d size=%d",
            _safe_url_for_log(final_url),
            response.status_code,
            len(body),
        )

        return PageResponse(
            url=final_url,
            status_code=response.status_code,
            content_type=content_type or "application/octet-stream",
            language=language,
            response_size=len(body),
            html=html,
            title=title,
        )


def _read_limited_body(
    response: httpx.Response,
    max_size: int,
    url: str,
) -> bytes:
    """Read response content up to the configured maximum size."""
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_size:
                raise BrowserResponseTooLargeError(url, max_size)
        except ValueError:
            pass

    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > max_size:
            raise BrowserResponseTooLargeError(url, max_size)
        chunks.append(chunk)

    if not chunks and response.content:
        if len(response.content) > max_size:
            raise BrowserResponseTooLargeError(url, max_size)
        return response.content

    return b"".join(chunks)


def _decode_body(body: bytes, content_type: str) -> str:
    """Decode response bytes to text using UTF-8 with latin-1 fallback."""
    if not body:
        return ""

    charset = "utf-8"
    if "charset=" in content_type.lower():
        charset = content_type.lower().split("charset=", 1)[1].strip().split(";")[0]

    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _safe_url_for_log(url: str) -> str:
    """Return a URL safe for logging (credentials redacted)."""
    parsed = httpx.URL(url)
    if parsed.username or parsed.password:
        host = parsed.host or ""
        return f"{parsed.scheme}://***:***@{host}{parsed.path or ''}"
    return url
