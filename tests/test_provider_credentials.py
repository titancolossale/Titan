# =====================================
# Titan Provider Credential Tests
# =====================================

"""Tests for Phase 10B Batch 3.5 — Credential & Provider Configuration (P10B-301–P10B-306)."""

from __future__ import annotations

import pytest

from tools.health_monitor import HealthMonitor
from tools.providers.credential_manager import (
    CredentialManager,
    CredentialRequirement,
    CredentialStatus,
    CredentialType,
)
from tools.providers.defaults import create_provider_bootstrap, register_default_providers
from tools.providers.provider_configuration import (
    ProviderConfiguration,
    ProviderConfigurationStore,
)
from tools.providers.provider_context import ProviderContext
from tools.providers.provider_registry import ProviderRegistry
from tools.providers.web_search_provider import StubWebSearchProvider
from tools.tool_enums import ExecutionMode, ToolHealthState
from tools.tool_manager import ToolManager
from tools.tool_runtime import ToolRuntime
from tools.tool_policy import ToolPolicy
from tools.tool_registry import ToolRegistry


def test_credential_validation_configured_without_secrets() -> None:
    """P10B-303: Optional missing credentials report configured for stub mode."""
    manager = CredentialManager(env={})
    result = manager.validate("web_search")
    assert result.status == CredentialStatus.CONFIGURED
    assert result.configured
    public = result.to_public_dict()
    assert "api_key" not in str(public.values()).lower() or public["credential_name"] == ""


def test_credential_validation_missing_required() -> None:
    """P10B-303: Required missing credentials report missing status."""
    manager = CredentialManager(env={})
    manager.register_requirements(
        "web_search",
        (
            CredentialRequirement(
                name="api_key",
                env_var="TITAN_WEB_SEARCH_API_KEY",
                required=True,
            ),
        ),
        replace=True,
    )
    result = manager.validate("web_search")
    assert result.status == CredentialStatus.MISSING
    assert not result.configured
    assert "TITAN_WEB_SEARCH_API_KEY" in result.message


def test_credential_validation_invalid_placeholder() -> None:
    """P10B-303: Placeholder values are reported as invalid."""
    manager = CredentialManager(
        env={"TITAN_WEB_SEARCH_API_KEY": "your_key_here"},
    )
    result = manager.validate("web_search")
    assert result.status == CredentialStatus.INVALID


def test_credential_validation_does_not_expose_secret_values() -> None:
    """P10B-303: Validation exports never include secret values."""
    manager = CredentialManager(
        env={"TITAN_WEB_SEARCH_API_KEY": "super-secret-value-12345"},
    )
    result = manager.validate("web_search")
    exported = result.to_public_dict()
    assert "super-secret-value-12345" not in str(exported)


def test_provider_configuration_separate_from_credentials() -> None:
    """P10B-302: Configuration holds non-secret operational settings."""
    config = ProviderConfiguration(
        provider_id="web_search",
        enabled=True,
        priority=50,
        timeout_seconds=15.0,
        retry_count=3,
        execution_mode=ExecutionMode.MOCK,
        settings={"region": "eu-west"},
    )
    assert config.is_valid()
    assert config.settings["region"] == "eu-west"


def test_invalid_provider_configuration_reports_misconfigured() -> None:
    """P10B-305: Invalid configuration maps to MISCONFIGURED health."""
    config = ProviderConfiguration(
        provider_id="web_search",
        timeout_seconds=-1,
    )
    registry = ProviderRegistry(runtime_version="0.10.0")
    manager = CredentialManager(env={})
    store = ProviderConfigurationStore()
    store.register(config, replace=True)
    registry.attach_bootstrap(manager, store)
    registry.register(StubWebSearchProvider())
    health = registry.probe("web_search")
    assert health.state == ToolHealthState.MISCONFIGURED


def test_disabled_provider_reports_disabled_health() -> None:
    """P10B-305: Disabled provider maps to DISABLED health."""
    store = ProviderConfigurationStore()
    store.register(
        ProviderConfiguration(provider_id="web_search", enabled=False),
        replace=True,
    )
    manager = CredentialManager(env={})
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.attach_bootstrap(manager, store)
    context = ProviderContext(manager, store.get_or_default("web_search"))
    registry.register(StubWebSearchProvider(context=context))
    health = registry.probe("web_search")
    assert health.state == ToolHealthState.DISABLED


def test_missing_required_credentials_reports_missing_credentials_health() -> None:
    """P10B-305: Required credentials missing maps to MISSING_CREDENTIALS."""
    manager = CredentialManager(env={})
    manager.register_requirements(
        "web_search",
        (
            CredentialRequirement(
                name="api_key",
                env_var="TITAN_WEB_SEARCH_API_KEY",
                required=True,
            ),
        ),
        replace=True,
    )
    store = ProviderConfigurationStore()
    store.register(
        ProviderConfiguration(
            provider_id="web_search",
            settings={"require_credentials": True},
        ),
        replace=True,
    )
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.attach_bootstrap(manager, store)
    context = ProviderContext(manager, store.get_or_default("web_search"))
    registry.register(StubWebSearchProvider(context=context))
    health = registry.probe("web_search")
    assert health.state == ToolHealthState.MISSING_CREDENTIALS


def test_provider_bootstrap_wires_credential_manager() -> None:
    """P10B-304: Default bootstrap attaches CredentialManager to registry."""
    registry = ProviderRegistry(runtime_version="0.10.0")
    register_default_providers(registry)
    assert registry.credential_manager is not None
    assert registry.configuration_store is not None
    assert registry.get("web_search") is not None


def test_provider_bootstrap_default_stubs_remain_online() -> None:
    """Regression: stub providers stay ONLINE/DEGRADED without live credentials."""
    registry = ProviderRegistry(runtime_version="0.10.0")
    register_default_providers(registry)
    monitor = HealthMonitor()
    registry.sync_health(monitor)
    assert monitor.get_provider_health("web_search") == ToolHealthState.ONLINE
    assert monitor.get_provider_health("calendar") == ToolHealthState.DEGRADED


def test_health_transition_missing_to_online() -> None:
    """P10B-305: Health transitions when credentials become available."""
    env: dict[str, str | None] = {}
    manager = CredentialManager(env=env)
    manager.register_requirements(
        "web_search",
        (
            CredentialRequirement(
                name="api_key",
                env_var="TITAN_WEB_SEARCH_API_KEY",
                required=True,
            ),
        ),
        replace=True,
    )
    store = ProviderConfigurationStore()
    store.register(
        ProviderConfiguration(
            provider_id="web_search",
            settings={"require_credentials": True},
        ),
        replace=True,
    )
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.attach_bootstrap(manager, store)
    context = ProviderContext(manager, store.get_or_default("web_search"))
    registry.register(StubWebSearchProvider(context=context))

    missing = registry.probe("web_search")
    assert missing.state == ToolHealthState.MISSING_CREDENTIALS

    env["TITAN_WEB_SEARCH_API_KEY"] = "valid-production-key"
    online = registry.probe("web_search")
    assert online.state == ToolHealthState.ONLINE


def test_provider_metadata_includes_credential_status() -> None:
    """P10B-303: Metadata exposes credential status without secret values."""
    registry = ProviderRegistry(runtime_version="0.10.0")
    register_default_providers(registry)
    meta = registry.get_metadata("web_search")
    assert meta is not None
    assert meta.credential_status == CredentialStatus.CONFIGURED.value
    assert meta.configured is True
    assert meta.enabled is True
    payload = meta.to_dict()
    assert "super-secret" not in str(payload)


def test_tool_runtime_bootstraps_with_credential_layer() -> None:
    """P10B-304: ToolRuntime startup wires credential bootstrap."""
    runtime = ToolRuntime(registry=ToolRegistry(), policy=ToolPolicy())
    assert runtime.provider_registry is not None
    assert runtime.provider_registry.credential_manager is not None
    assert runtime.provider_registry.configuration_store is not None


def test_tool_manager_bootstraps_with_credential_layer(tmp_path) -> None:
    """P10B-304: ToolManager startup wires credential bootstrap."""
    manager = ToolManager(project_root=tmp_path, use_runtime_v2=True)
    assert manager.provider_registry.credential_manager is not None
    assert manager.provider_registry.configuration_store is not None


def test_credential_type_future_compatibility() -> None:
    """P10B-306: Credential types cover OAuth, JWT, refresh tokens, service accounts."""
    supported = {item.value for item in CredentialType}
    assert supported == {
        "api_key",
        "oauth",
        "jwt",
        "refresh_token",
        "service_account",
    }


def test_missing_credentials_blocks_provider_selection() -> None:
    """Regression: MISSING_CREDENTIALS blocks provider fallback routing."""
    from tools.providers.provider_executor import ProviderExecutor
    from tools.providers.web_search_provider import FallbackWebSearchProvider

    manager = CredentialManager(env={})
    manager.register_requirements(
        "web_search",
        (
            CredentialRequirement(
                name="api_key",
                env_var="TITAN_WEB_SEARCH_API_KEY",
                required=True,
            ),
        ),
        replace=True,
    )
    store = ProviderConfigurationStore()
    store.register(
        ProviderConfiguration(
            provider_id="web_search",
            settings={"require_credentials": True},
        ),
        replace=True,
    )
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.attach_bootstrap(manager, store)
    context = ProviderContext(manager, store.get_or_default("web_search"))
    registry.register(StubWebSearchProvider(context=context))
    registry.register(FallbackWebSearchProvider())
    monitor = HealthMonitor()
    registry.sync_health(monitor)
    assert monitor.get_provider_health("web_search") == ToolHealthState.MISSING_CREDENTIALS

    executor = ProviderExecutor(registry=registry, health_monitor=monitor)
    outcome = executor.execute("search", {"query": "test"}, capability="web_search")
    assert outcome.success
    assert outcome.provider_id == "web_search_fallback"
