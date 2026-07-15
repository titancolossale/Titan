# =====================================
# Titan Provider Framework Tests
# =====================================

"""Tests for Phase 10A provider layer (P10A-028)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.exceptions import ProviderVersionIncompatible
from tools.audit.tool_audit_logger import ToolAuditLogger
from tools.capability_catalog import CapabilityCatalog
from tools.provider_version import ProviderHealth, ProviderVersionInfo
from tools.providers.base_provider import BaseProvider
from tools.providers.calendar_provider import StubCalendarProvider
from tools.providers.defaults import register_default_providers
from tools.providers.provider_registry import ProviderRegistry
from tools.providers.web_search_provider import (
    StubWebSearchProvider,
    WebSearchProvider,
)
from tools.tool_enums import ExecutionMode, ToolHealthState
from tools.tool_manager import ToolManager
from tools.tool_run_models import ToolExecutionContext, ToolRunStatus
from tools.tool_runtime import ToolRuntime
from tools.web_search_provider import StubWebSearchProvider as LegacyStub
from tools.web_search_tool import WebSearchTool


class _FutureRuntimeProvider(WebSearchProvider):
    """Provider requiring a newer runtime than available."""

    @property
    def version_info(self) -> ProviderVersionInfo:
        return ProviderVersionInfo(
            provider_id="web_search",
            version="99.0.0",
            min_runtime_version="99.0.0",
            compatible_modes=frozenset({ExecutionMode.LIVE}),
        )

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(state=ToolHealthState.ONLINE)

    def search(self, query: str, *, max_results: int = 5):
        from tools.providers.web_search_provider import SearchResponse

        _ = max_results
        return SearchResponse(query=query, provider="future")


def test_base_provider_stub_has_version_and_health() -> None:
    """P10A-025: reference stub exposes version_info and health_check."""
    provider = StubWebSearchProvider()
    assert provider.provider_id == "web_search"
    assert provider.version_info.version == "0.1.0"
    health = provider.health_check()
    assert health.state == ToolHealthState.ONLINE
    assert provider.supports_execution_mode(ExecutionMode.MOCK)


def test_calendar_stub_reports_degraded_health() -> None:
    """P10A-026: calendar stub is registered but degraded."""
    provider = StubCalendarProvider()
    health = provider.health_check()
    assert health.state == ToolHealthState.DEGRADED
    response = provider.execute("list")
    assert not response.success


def test_provider_registry_registers_and_lists() -> None:
    """P10A-024: registry stores providers by id."""
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.register(StubWebSearchProvider())
    registry.register(StubCalendarProvider())
    assert registry.list_ids() == ["calendar", "web_search"]
    assert registry.get("web_search") is not None


def test_provider_registry_rejects_incompatible_runtime() -> None:
    """P10A-024: min_runtime_version above current runtime is rejected."""
    registry = ProviderRegistry(runtime_version="0.10.0")
    with pytest.raises(ProviderVersionIncompatible):
        registry.register(_FutureRuntimeProvider())


def test_provider_registry_rejects_duplicate() -> None:
    """P10A-024: duplicate registration raises ValueError."""
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.register(StubWebSearchProvider())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(StubWebSearchProvider())


def test_provider_registry_probe_unknown_offline() -> None:
    """P10A-024: probing unknown provider returns OFFLINE."""
    registry = ProviderRegistry()
    health = registry.probe("missing")
    assert health.state == ToolHealthState.OFFLINE


def test_provider_registry_sync_health_to_monitor() -> None:
    """P10A-024: sync_health pushes provider states into HealthMonitor."""
    from tools.health_monitor import HealthMonitor

    registry = ProviderRegistry(runtime_version="0.10.0")
    register_default_providers(registry)
    monitor = HealthMonitor()
    registry.sync_health(monitor)
    assert monitor.get_provider_health("web_search") == ToolHealthState.ONLINE
    assert monitor.get_provider_health("calendar") == ToolHealthState.DEGRADED


def test_register_default_providers_idempotent() -> None:
    """P10A-027: default registration is safe to call twice."""
    registry = ProviderRegistry(runtime_version="0.10.0")
    register_default_providers(registry)
    register_default_providers(registry)
    assert len(registry.list_ids()) == 5
    assert "file_system" in registry.list_ids()
    assert "github" in registry.list_ids()


def test_web_search_tool_backward_compat_injected_provider() -> None:
    """P10A-025: direct provider injection still works."""
    tool = WebSearchTool(provider=LegacyStub())
    result = tool.run(query="Titan")
    assert result.success
    assert "stub" in result.source


def test_web_search_tool_resolves_from_registry() -> None:
    """P10A-025: tool resolves provider from ProviderRegistry."""
    registry = ProviderRegistry(runtime_version="0.10.0")
    register_default_providers(registry)
    tool = WebSearchTool(registry=registry)
    assert tool.provider.provider_id == "web_search"
    result = tool.run(query="test")
    assert result.success


def test_legacy_import_path_reexports() -> None:
    """P10A-025: tools.web_search_provider re-exports remain importable."""
    from tools.web_search_provider import StubWebSearchProvider, WebSearchProvider

    assert issubclass(StubWebSearchProvider, WebSearchProvider)
    assert issubclass(StubWebSearchProvider, BaseProvider)


def test_tool_runtime_wires_default_providers() -> None:
    """P10A-024: runtime registers stubs and syncs dependency resolver."""
    from tools.tool_policy import ToolPolicy
    from tools.tool_registry import ToolRegistry
    from tools.time_tool import TimeTool

    registry = ToolRegistry()
    registry.register(TimeTool())
    runtime = ToolRuntime(registry=registry, policy=ToolPolicy())
    assert runtime.provider_registry is not None
    assert "web_search" in runtime.provider_registry.list_ids()
    assert runtime.health_monitor.get_provider_health("web_search") == ToolHealthState.ONLINE


def test_tool_runtime_audit_includes_provider_version(tmp_path: Path) -> None:
    """P10A-024: audit events include provider_version for provider-backed tools."""
    from tools.adapters.legacy_tool_adapter import register_legacy_tools
    from tools.dependency_resolver import DependencyResolver
    from tools.tool_policy import ToolPolicy
    from tools.tool_registry import ToolRegistry

    audit_path = tmp_path / "audit.jsonl"
    audit_logger = ToolAuditLogger(enabled=True, file_path=audit_path)
    reg = ToolRegistry()
    reg.register(WebSearchTool())
    catalog = CapabilityCatalog()
    resolver = DependencyResolver()
    register_legacy_tools(reg, catalog, resolver)
    runtime = ToolRuntime(
        registry=reg,
        policy=ToolPolicy(),
        catalog=catalog,
        dependency_resolver=resolver,
        audit_logger=audit_logger,
    )
    from tools.tool_enums import ExecutionMode

    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        execution_mode=ExecutionMode.MOCK,
        metadata={"execution_mode_override": True},
    )
    outcome = runtime.invoke("web_search", {"query": "Titan"}, ctx)
    assert outcome.status == ToolRunStatus.COMPLETED
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    completed = [
        line for line in lines if '"event_type": "completed"' in line
    ]
    assert completed
    assert '"provider_version": "0.1.0"' in completed[-1]


def test_capability_catalog_export_with_providers() -> None:
    """P10A-011: export_with_providers merges provider version metadata."""
    from tools.adapters.legacy_tool_adapter import capability_from_tool

    catalog = CapabilityCatalog()
    catalog.register(capability_from_tool(WebSearchTool()))
    exported = catalog.export_with_providers(
        provider_versions={"web_search": "0.1.0"},
    )
    assert exported["web_search"]["provider_version"] == "0.1.0"


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "sample.txt").write_text("data", encoding="utf-8")
    return tmp_path


def test_tool_manager_shares_provider_registry(project_root: Path) -> None:
    """P10A-024: ToolManager exposes shared provider registry."""
    manager = ToolManager(project_root=project_root, use_runtime_v2=True)
    assert "web_search" in manager.provider_registry.list_ids()
    web_tool = manager.registry.get("web_search")
    assert isinstance(web_tool, WebSearchTool)
    assert web_tool.provider.provider_id == "web_search"
