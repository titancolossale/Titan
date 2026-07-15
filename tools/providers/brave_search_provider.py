# =====================================
# Titan Brave Search Provider
# =====================================

"""Production Brave Search API provider — first live external integration (P10B-401)."""

from __future__ import annotations

import socket
import time
from typing import Callable
from urllib.error import URLError

from tools.provider_version import ProviderHealth, ProviderVersionInfo
from tools.providers.brave_http_client import (
    HttpTransport,
    UrllibHttpTransport,
    parse_json_body,
)
from tools.providers.credential_manager import CredentialStatus
from tools.providers.provider_context import ProviderContext
from tools.providers.provider_failure import ProviderFailureReason, health_state_for_failure
from tools.providers.provider_health_resolver import resolve_provider_health
from tools.providers.web_search_provider import SearchResponse, SearchResult, WebSearchProvider
from tools.tool_enums import ExecutionMode, ToolHealthState

_BRAVE_WEB_URL = "https://api.search.brave.com/res/v1/web/search"
_BRAVE_NEWS_URL = "https://api.search.brave.com/res/v1/news/search"

_BRAVE_VERSION = ProviderVersionInfo(
    provider_id="brave_search",
    version="1.0.0",
    min_runtime_version="0.10.0",
    api_version="v1",
    compatible_modes=frozenset({ExecutionMode.LIVE, ExecutionMode.MOCK}),
)

_VALID_FRESHNESS = frozenset({"pd", "pw", "pm", "py"})
_VALID_SAFE_SEARCH = frozenset({"off", "moderate", "strict"})

HealthCallback = Callable[[ToolHealthState, str], None]


class BraveSearchProvider(WebSearchProvider):
    """Brave Search API backend — credentials via CredentialManager only."""

    def __init__(
        self,
        *,
        context: ProviderContext | None = None,
        http_transport: HttpTransport | None = None,
        health_callback: HealthCallback | None = None,
    ) -> None:
        self.context = context
        self._http = http_transport or UrllibHttpTransport()
        self._health_callback = health_callback
        self._last_failure: ProviderFailureReason | None = None

    @property
    def provider_id(self) -> str:
        return "brave_search"

    @property
    def version_info(self) -> ProviderVersionInfo:
        return _BRAVE_VERSION

    def capabilities(self) -> frozenset[str]:
        return frozenset({"web_search"})

    def supported_actions(self) -> frozenset[str]:
        return frozenset({"search", "news"})

    def health_check(self) -> ProviderHealth:
        default = ProviderHealth(
            state=ToolHealthState.ONLINE,
            message="Brave Search API prêt.",
        )
        if self.context is None or self.context.credential_manager is None:
            return ProviderHealth(
                state=ToolHealthState.MISCONFIGURED,
                message="CredentialManager non injecté.",
            )

        validation = self.context.credential_manager.validate(self.provider_id)
        if validation.status == CredentialStatus.INVALID:
            return ProviderHealth(
                state=ToolHealthState.MISCONFIGURED,
                message=validation.message,
            )
        if validation.status == CredentialStatus.MISSING:
            return ProviderHealth(
                state=ToolHealthState.MISSING_CREDENTIALS,
                message=validation.message,
            )

        return resolve_provider_health(
            self.provider_id,
            context=self.context,
            default_health=default,
            require_credentials_in_live=True,
        )

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        top_k: int | None = None,
        freshness: str | None = None,
        safe_search: str | None = None,
        timeout: float | None = None,
    ) -> SearchResponse:
        """Execute a web search via Brave Search API."""
        return self._execute(
            endpoint=_BRAVE_WEB_URL,
            query=query,
            result_key="web",
            max_results=max_results,
            top_k=top_k,
            freshness=freshness,
            safe_search=safe_search,
            timeout=timeout,
        )

    def news(
        self,
        query: str,
        *,
        max_results: int = 5,
        top_k: int | None = None,
        freshness: str | None = None,
        safe_search: str | None = None,
        timeout: float | None = None,
    ) -> SearchResponse:
        """Execute a news search via Brave Search API."""
        return self._execute(
            endpoint=_BRAVE_NEWS_URL,
            query=query,
            result_key="results",
            max_results=max_results,
            top_k=top_k,
            freshness=freshness,
            safe_search=safe_search,
            timeout=timeout,
            nested=False,
        )

    def _execute(
        self,
        *,
        endpoint: str,
        query: str,
        result_key: str,
        max_results: int,
        top_k: int | None,
        freshness: str | None,
        safe_search: str | None,
        timeout: float | None,
        nested: bool = True,
    ) -> SearchResponse:
        cleaned_query = query.strip()
        if not cleaned_query:
            return self._failure_response(
                cleaned_query,
                "Requête vide.",
                ProviderFailureReason.UNKNOWN,
            )

        credential_error = self._validate_credentials_before_execution()
        if credential_error is not None:
            return credential_error

        api_key = self._get_api_key()
        if not api_key:
            return self._failure_response(
                cleaned_query,
                "Clé API Brave manquante.",
                ProviderFailureReason.INVALID_KEY,
            )

        count = top_k if top_k is not None else max_results
        count = max(1, min(int(count), 20))
        request_timeout = self._resolve_timeout(timeout)

        params: dict[str, str] = {"q": cleaned_query, "count": str(count)}
        if freshness:
            freshness_value = str(freshness).strip().lower()
            if freshness_value in _VALID_FRESHNESS or "to" in freshness_value:
                params["freshness"] = freshness_value
        if safe_search:
            safe_value = str(safe_search).strip().lower()
            if safe_value in _VALID_SAFE_SEARCH:
                params["safesearch"] = safe_value

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        }

        start = time.perf_counter()
        try:
            http_response = self._http.get(
                endpoint,
                headers=headers,
                params=params,
                timeout=request_timeout,
            )
        except TimeoutError:
            return self._failure_response(
                cleaned_query,
                "Délai dépassé lors de l'appel Brave Search.",
                ProviderFailureReason.TIMEOUT,
            )
        except (URLError, socket.timeout, OSError) as exc:
            reason = self._classify_network_error(exc)
            return self._failure_response(
                cleaned_query,
                f"Erreur réseau Brave Search : {exc}",
                reason,
            )

        latency_ms = (time.perf_counter() - start) * 1000.0
        failure = self._classify_http_failure(http_response.status_code, http_response.body)
        if failure is not None:
            message = self._extract_error_message(http_response.body) or failure.value
            return self._failure_response(cleaned_query, message, failure, latency_ms=latency_ms)

        payload = parse_json_body(http_response.body)
        results = self._parse_results(payload, result_key, nested=nested)
        self._last_failure = None
        self._emit_health(ToolHealthState.ONLINE, "Brave Search opérationnel.")

        return SearchResponse(
            query=cleaned_query,
            results=results,
            provider=self.provider_id,
            success=True,
            latency_ms=latency_ms,
        )

    def _validate_credentials_before_execution(self) -> SearchResponse | None:
        """P10B-406: Validate credentials before any API call."""
        if self.context is None or self.context.credential_manager is None:
            return self._failure_response(
                "",
                "CredentialManager non disponible.",
                ProviderFailureReason.INVALID_KEY,
            )
        validation = self.context.credential_manager.validate(self.provider_id)
        if validation.status == CredentialStatus.CONFIGURED:
            return None
        reason = ProviderFailureReason.INVALID_KEY
        if validation.status == CredentialStatus.MISSING:
            reason = ProviderFailureReason.INVALID_KEY
        return self._failure_response("", validation.message, reason)

    def _get_api_key(self) -> str | None:
        if self.context is None or self.context.credential_manager is None:
            return None
        return self.context.credential_manager.get_secret(self.provider_id, "api_key")

    def _resolve_timeout(self, timeout: float | None) -> float:
        if timeout is not None and timeout > 0:
            return float(timeout)
        if self.context is not None and self.context.configuration is not None:
            return float(self.context.configuration.timeout_seconds)
        return 30.0

    def _parse_results(
        self,
        payload: dict,
        result_key: str,
        *,
        nested: bool,
    ) -> list[SearchResult]:
        if nested:
            section = payload.get(result_key, {})
            raw_results = section.get("results", []) if isinstance(section, dict) else []
        else:
            raw_results = payload.get(result_key, [])
        if not isinstance(raw_results, list):
            return []

        parsed: list[SearchResult] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            snippet = str(
                item.get("description", item.get("snippet", "")),
            ).strip()
            if title or url:
                parsed.append(
                    SearchResult(
                        title=title or url,
                        url=url,
                        snippet=snippet,
                        source="brave",
                    ),
                )
        return parsed

    @staticmethod
    def _classify_http_failure(
        status_code: int,
        body: str,
    ) -> ProviderFailureReason | None:
        if 200 <= status_code < 300:
            return None
        lowered = body.lower()
        if status_code in (401, 403) or "subscription_token" in lowered or "invalid" in lowered:
            return ProviderFailureReason.INVALID_KEY
        if status_code == 429 or "rate" in lowered:
            return ProviderFailureReason.RATE_LIMIT
        if status_code in (502, 503, 504):
            return ProviderFailureReason.OFFLINE
        if status_code >= 500:
            return ProviderFailureReason.OFFLINE
        if status_code == 408:
            return ProviderFailureReason.TIMEOUT
        return ProviderFailureReason.UNKNOWN

    @staticmethod
    def _classify_network_error(exc: BaseException) -> ProviderFailureReason:
        if isinstance(exc, socket.timeout):
            return ProviderFailureReason.TIMEOUT
        if isinstance(exc, URLError):
            reason = getattr(exc, "reason", None)
            if isinstance(reason, socket.timeout):
                return ProviderFailureReason.TIMEOUT
            if reason is not None and "timed out" in str(reason).lower():
                return ProviderFailureReason.TIMEOUT
        message = str(exc).lower()
        if "timed out" in message or "timeout" in message:
            return ProviderFailureReason.TIMEOUT
        if "network" in message or "connection refused" in message:
            return ProviderFailureReason.NETWORK_ERROR
        if "offline" in message or "unreachable" in message:
            return ProviderFailureReason.OFFLINE
        return ProviderFailureReason.NETWORK_ERROR

    @staticmethod
    def _extract_error_message(body: str) -> str:
        payload = parse_json_body(body)
        for key in ("message", "error", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _failure_response(
        self,
        query: str,
        message: str,
        reason: ProviderFailureReason,
        *,
        latency_ms: float = 0.0,
    ) -> SearchResponse:
        self._last_failure = reason
        health = health_state_for_failure(reason)
        self._emit_health(health, message)
        return SearchResponse(
            query=query,
            provider=self.provider_id,
            success=False,
            error=message,
            failure_reason=reason.value,
            latency_ms=latency_ms,
        )

    def _emit_health(self, state: ToolHealthState, message: str) -> None:
        if self._health_callback is not None:
            self._health_callback(state, message)
