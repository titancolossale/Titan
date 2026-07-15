# =====================================
# Titan Brave Search Provider Tests
# =====================================

"""Tests for Phase 10B Batch 4 — Brave Search live provider (P10B-401–P10B-407)."""

from __future__ import annotations

import json

import pytest

from tools.decision.execution_context import enrich_decision_report_from_result
from tools.decision.models import ToolDecisionReport
from tools.decision.intent import Intent
from tools.health_monitor import HealthMonitor
from tools.providers.brave_http_client import HttpResponse, MockHttpTransport
from tools.providers.brave_search_provider import BraveSearchProvider
from tools.providers.credential_manager import (
    CredentialManager,
    CredentialStatus,
    validate_brave_api_key,
)
from tools.providers.provider_configuration import ProviderConfigurationStore
from tools.providers.provider_context import ProviderContext
from tools.providers.provider_executor import ProviderExecutor
from tools.providers.provider_failure import ProviderFailureReason
from tools.providers.provider_registry import ProviderRegistry
from tools.providers.web_search_provider import StubWebSearchProvider
from tools.tool_enums import ExecutionMode, RiskLevel, ToolHealthState
from tools.web_search_tool import WebSearchTool

_VALID_KEY = "BSA-test-key-abcdefghijklmnopqrstuvwxyz"


def _brave_env(key: str = _VALID_KEY) -> dict[str, str | None]:
    return {"TITAN_BRAVE_SEARCH_API_KEY": key}


def _web_success_body() -> str:
    return json.dumps(
        {
            "web": {
                "results": [
                    {
                        "title": "Titan AI Project",
                        "url": "https://example.com/titan",
                        "description": "Agentic AI system.",
                    },
                ],
            },
        },
    )


def _news_success_body() -> str:
    return json.dumps(
        {
            "results": [
                {
                    "title": "Titan News",
                    "url": "https://news.example.com/titan",
                    "description": "Latest updates.",
                },
            ],
        },
    )


@pytest.fixture
def brave_registry() -> ProviderRegistry:
    credential_manager = CredentialManager(env=_brave_env())
    configuration_store = ProviderConfigurationStore.from_defaults()
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.attach_bootstrap(credential_manager, configuration_store)
    transport = MockHttpTransport(
        responses={
            "https://api.search.brave.com/res/v1/web/search": HttpResponse(
                status_code=200,
                body=_web_success_body(),
            ),
            "https://api.search.brave.com/res/v1/news/search": HttpResponse(
                status_code=200,
                body=_news_success_body(),
            ),
        },
    )
    context = ProviderContext(
        credential_manager=credential_manager,
        configuration=configuration_store.get_or_default("brave_search"),
    )
    registry.register(
        BraveSearchProvider(context=context, http_transport=transport),
    )
    registry.register(StubWebSearchProvider())
    return registry


def test_brave_search_success(brave_registry: ProviderRegistry) -> None:
    """P10B-402: Successful web search returns structured results."""
    provider = brave_registry.get("brave_search")
    assert isinstance(provider, BraveSearchProvider)
    response = provider.search("Titan AI", top_k=3, freshness="pw", safe_search="strict")
    assert response.success
    assert response.provider == "brave_search"
    assert len(response.results) == 1
    assert response.results[0].url == "https://example.com/titan"
    assert response.latency_ms >= 0


def test_brave_news_search(brave_registry: ProviderRegistry) -> None:
    """P10B-402: News search action returns news results."""
    provider = brave_registry.get("brave_search")
    assert isinstance(provider, BraveSearchProvider)
    response = provider.news("Titan news", top_k=5)
    assert response.success
    assert response.results[0].source == "brave"


def test_brave_invalid_key() -> None:
    """P10B-403/406: Invalid API key maps to INVALID_KEY without crashing."""
    transport = MockHttpTransport(
        responses={
            "https://api.search.brave.com/res/v1/web/search": HttpResponse(
                status_code=401,
                body='{"message":"SUBSCRIPTION_TOKEN_INVALID"}',
            ),
        },
    )
    manager = CredentialManager(env=_brave_env())
    context = ProviderContext(
        credential_manager=manager,
        configuration=ProviderConfigurationStore.from_defaults().get_or_default("brave_search"),
    )
    provider = BraveSearchProvider(context=context, http_transport=transport)
    response = provider.search("test")
    assert not response.success
    assert response.failure_reason == ProviderFailureReason.INVALID_KEY.value


def test_brave_timeout() -> None:
    """P10B-403: Timeout failures are handled gracefully."""
    def _timeout(**kwargs: object) -> HttpResponse:
        raise TimeoutError("request timed out")

    transport = MockHttpTransport(side_effect=_timeout)
    manager = CredentialManager(env=_brave_env())
    context = ProviderContext(
        credential_manager=manager,
        configuration=ProviderConfigurationStore.from_defaults().get_or_default("brave_search"),
    )
    provider = BraveSearchProvider(context=context, http_transport=transport)
    response = provider.search("test", timeout=0.1)
    assert not response.success
    assert response.failure_reason == ProviderFailureReason.TIMEOUT.value


def test_brave_offline() -> None:
    """P10B-403: Service unavailable maps to OFFLINE."""
    transport = MockHttpTransport(
        responses={
            "https://api.search.brave.com/res/v1/web/search": HttpResponse(
                status_code=503,
                body='{"message":"service unavailable"}',
            ),
        },
    )
    manager = CredentialManager(env=_brave_env())
    context = ProviderContext(
        credential_manager=manager,
        configuration=ProviderConfigurationStore.from_defaults().get_or_default("brave_search"),
    )
    provider = BraveSearchProvider(context=context, http_transport=transport)
    response = provider.search("test")
    assert not response.success
    assert response.failure_reason == ProviderFailureReason.OFFLINE.value


def test_brave_rate_limit() -> None:
    """P10B-403: Rate limit responses map to RATE_LIMIT."""
    transport = MockHttpTransport(
        responses={
            "https://api.search.brave.com/res/v1/web/search": HttpResponse(
                status_code=429,
                body='{"message":"rate limit exceeded"}',
            ),
        },
    )
    manager = CredentialManager(env=_brave_env())
    context = ProviderContext(
        credential_manager=manager,
        configuration=ProviderConfigurationStore.from_defaults().get_or_default("brave_search"),
    )
    provider = BraveSearchProvider(context=context, http_transport=transport)
    response = provider.search("test")
    assert not response.success
    assert response.failure_reason == ProviderFailureReason.RATE_LIMIT.value


def test_brave_network_error() -> None:
    """P10B-403: Network errors map to NETWORK_ERROR."""
    def _network_error(**kwargs: object) -> HttpResponse:
        raise OSError("network unreachable")

    transport = MockHttpTransport(side_effect=_network_error)
    manager = CredentialManager(env=_brave_env())
    context = ProviderContext(
        credential_manager=manager,
        configuration=ProviderConfigurationStore.from_defaults().get_or_default("brave_search"),
    )
    provider = BraveSearchProvider(context=context, http_transport=transport)
    response = provider.search("test")
    assert not response.success
    assert response.failure_reason == ProviderFailureReason.NETWORK_ERROR.value


def test_provider_health_updates_on_failure(brave_registry: ProviderRegistry) -> None:
    """P10B-404: ProviderExecutor updates HealthMonitor on provider failure."""
    transport = MockHttpTransport(
        responses={
            "https://api.search.brave.com/res/v1/web/search": HttpResponse(
                status_code=429,
                body='{"message":"rate limit"}',
            ),
        },
    )
    provider = brave_registry.get("brave_search")
    assert isinstance(provider, BraveSearchProvider)
    provider._http = transport  # noqa: SLF001 — test injection

    monitor = HealthMonitor()
    brave_registry.sync_health(monitor)
    executor = ProviderExecutor(registry=brave_registry, health_monitor=monitor)

    outcome = executor.execute(
        "search",
        {"query": "health test"},
        capability="web_search",
    )
    assert outcome.success
    assert outcome.provider_id == "web_search"
    assert monitor.get_provider_health("brave_search") == ToolHealthState.DEGRADED


def test_provider_health_online_after_success(brave_registry: ProviderRegistry) -> None:
    """P10B-404: Successful execution marks provider ONLINE."""
    monitor = HealthMonitor()
    brave_registry.sync_health(monitor)
    executor = ProviderExecutor(registry=brave_registry, health_monitor=monitor)

    outcome = executor.execute(
        "search",
        {"query": "Titan"},
        capability="web_search",
    )
    assert outcome.success
    assert outcome.provider_id == "brave_search"
    assert monitor.get_provider_health("brave_search") == ToolHealthState.ONLINE


def test_credential_validation_brave() -> None:
    """P10B-406: CredentialManager validates Brave API key without exposing it."""
    manager = CredentialManager(env=_brave_env())
    result = manager.validate("brave_search")
    assert result.status == CredentialStatus.CONFIGURED
    assert "BSA-test-key" not in result.to_public_dict().values()

    invalid = CredentialManager(env={"TITAN_BRAVE_SEARCH_API_KEY": "your_key_here"})
    invalid_result = invalid.validate("brave_search")
    assert invalid_result.status == CredentialStatus.INVALID

    missing = CredentialManager(env={})
    missing_result = missing.validate("brave_search")
    assert missing_result.status == CredentialStatus.MISSING


def test_validate_brave_api_key_helper() -> None:
    """P10B-406: Brave key validator rejects placeholders and short keys."""
    assert validate_brave_api_key(_VALID_KEY)
    assert not validate_brave_api_key("short")
    assert not validate_brave_api_key("your_key_here")


def test_decision_report_enriched_with_latency_and_fallback(
    brave_registry: ProviderRegistry,
) -> None:
    """P10B-405: DecisionReport includes latency and fallback metadata."""
    transport = MockHttpTransport(
        responses={
            "https://api.search.brave.com/res/v1/web/search": HttpResponse(
                status_code=429,
                body='{"message":"rate limit"}',
            ),
        },
    )
    provider = brave_registry.get("brave_search")
    assert isinstance(provider, BraveSearchProvider)
    provider._http = transport  # noqa: SLF001 — test injection

    monitor = HealthMonitor()
    brave_registry.sync_health(monitor)
    executor = ProviderExecutor(registry=brave_registry, health_monitor=monitor)

    report = ToolDecisionReport(
        intent=Intent.WEB_SEARCH,
        confidence=0.9,
        tool_required=True,
        candidate_tools=(),
        selected_tool="web_search",
        decision_reason="test",
        risk_level=RiskLevel.LOW,
        confirmation_required=False,
    )
    outcome = executor.execute(
        "search",
        {"query": "fallback"},
        capability="web_search",
    )
    assert outcome.fallback_used

    enriched = enrich_decision_report_from_result(
        report,
        {
            "provider_id": outcome.provider_id,
            "provider_score": outcome.provider_score,
            "provider_health": outcome.provider_health.value,
            "provider_version": outcome.provider_version,
            "execution_path": list(outcome.execution_path),
            "duration_ms": outcome.duration_ms,
            "fallback_used": outcome.fallback_used,
        },
    )
    assert enriched is not None
    assert enriched.selected_provider == "web_search"
    assert enriched.provider_latency_ms is not None
    assert enriched.fallback_used is True


def test_tool_runtime_brave_via_executor(brave_registry: ProviderRegistry) -> None:
    """P10B-401: WebSearchTool executes Brave provider through ProviderExecutor."""
    executor = ProviderExecutor(registry=brave_registry, health_monitor=HealthMonitor())
    tool = WebSearchTool(provider_executor=executor)
    result = tool.run(query="Titan", top_k=2, safe_search="moderate")
    assert result.success
    assert result.metadata.get("provider_id") == "brave_search"
    assert "Titan AI Project" in str(result.data)


def test_mock_http_records_calls(brave_registry: ProviderRegistry) -> None:
    """P10B-407: Mock HTTP layer captures requests without real API calls."""
    provider = brave_registry.get("brave_search")
    assert isinstance(provider, BraveSearchProvider)
    transport = provider._http  # noqa: SLF001
    assert isinstance(transport, MockHttpTransport)
    provider.search("mock test", top_k=2, freshness="pd")
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["params"]["q"] == "mock test"
    assert call["params"]["count"] == "2"
    assert call["params"]["freshness"] == "pd"
    token = call["headers"]["X-Subscription-Token"]
    assert token == _VALID_KEY
    assert "super-secret" not in str(call)


def test_brave_missing_credentials_blocked_from_selection() -> None:
    """Regression: Brave without credentials falls back to stub provider."""
    credential_manager = CredentialManager(env={})
    configuration_store = ProviderConfigurationStore.from_defaults()
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.attach_bootstrap(credential_manager, configuration_store)
    context = ProviderContext(
        credential_manager=credential_manager,
        configuration=configuration_store.get_or_default("brave_search"),
    )
    registry.register(BraveSearchProvider(context=context, http_transport=MockHttpTransport()))
    registry.register(StubWebSearchProvider())

    health = registry.probe("brave_search")
    assert health.state == ToolHealthState.MISSING_CREDENTIALS

    executor = ProviderExecutor(registry=registry, health_monitor=HealthMonitor())
    outcome = executor.execute("search", {"query": "stub"}, capability="web_search")
    assert outcome.success
    assert outcome.provider_id == "web_search"
