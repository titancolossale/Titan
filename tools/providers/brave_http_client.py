# =====================================
# Titan Brave HTTP Client
# =====================================

"""Injectable HTTP transport for Brave Search API — mockable in CI (P10B-407)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Protocol


@dataclass(frozen=True)
class HttpResponse:
    """Minimal HTTP response for provider parsing."""

    status_code: int
    body: str
    headers: dict[str, str] = field(default_factory=dict)


class HttpTransport(Protocol):
    """Protocol for HTTP GET requests used by BraveSearchProvider."""

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str],
        timeout: float,
    ) -> HttpResponse:
        """Execute an HTTP GET request."""


class UrllibHttpTransport:
    """Production HTTP transport using urllib (stdlib only)."""

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str],
        timeout: float,
    ) -> HttpResponse:
        query = urllib.parse.urlencode(params)
        full_url = f"{url}?{query}" if query else url
        request = urllib.request.Request(full_url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                response_headers = {
                    key.lower(): value
                    for key, value in response.headers.items()
                }
                return HttpResponse(
                    status_code=response.getcode(),
                    body=body,
                    headers=response_headers,
                )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            response_headers = {
                key.lower(): value for key, value in exc.headers.items()
            }
            return HttpResponse(
                status_code=exc.code,
                body=body,
                headers=response_headers,
            )


@dataclass
class MockHttpTransport:
    """Test double that returns scripted responses keyed by URL prefix."""

    responses: dict[str, HttpResponse] = field(default_factory=dict)
    default_response: HttpResponse | None = None
    calls: list[dict[str, object]] = field(default_factory=list)
    side_effect: Callable[..., HttpResponse] | None = None

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str],
        timeout: float,
    ) -> HttpResponse:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "params": dict(params),
                "timeout": timeout,
            },
        )
        if self.side_effect is not None:
            return self.side_effect(
                url=url,
                headers=headers,
                params=params,
                timeout=timeout,
            )
        for prefix, response in self.responses.items():
            if url.startswith(prefix):
                return response
        if self.default_response is not None:
            return self.default_response
        return HttpResponse(status_code=500, body='{"message":"mock not configured"}')


def parse_json_body(body: str) -> dict:
    """Parse JSON response body; return empty dict on failure."""
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
