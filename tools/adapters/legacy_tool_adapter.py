# =====================================
# Titan Legacy Tool Adapter
# =====================================

"""Bridge Phase 6 BaseTool instances into the Phase 10A runtime (P10A-014)."""

from __future__ import annotations

from tools.base_tool import BaseTool
from tools.capability_catalog import CapabilityCatalog
from tools.dependency_resolver import DependencyResolver
from tools.tool_capability import ToolCapability
from tools.tool_dependency import ToolDependency
from tools.tool_enums import ExecutionMode, InvocationMode, RiskLevel, ToolHealthState
from tools.tool_registry import ToolRegistry
from tools.tool_schema import ToolSchema

_LEGACY_RISK_DEFAULTS: dict[str, RiskLevel] = {
    "time": RiskLevel.SAFE,
    "file_read": RiskLevel.LOW,
    "file_write": RiskLevel.HIGH,
    "python_exec": RiskLevel.HIGH,
    "web_search": RiskLevel.LOW,
    "calendar": RiskLevel.SAFE,
    "obsidian": RiskLevel.LOW,
    "browser": RiskLevel.LOW,
}

_LEGACY_PROVIDER_DEFAULTS: dict[str, str] = {
    "web_search": "web_search",
    "calendar": "calendar",
    "file_read": "file_system",
    "file_write": "file_system",
    "github": "github",
}

_LEGACY_EXECUTION_MODES: dict[str, frozenset[ExecutionMode]] = {
    "time": frozenset({ExecutionMode.LIVE, ExecutionMode.MOCK}),
    "file_read": frozenset({ExecutionMode.LIVE, ExecutionMode.MOCK, ExecutionMode.SIMULATION}),
    "file_write": frozenset(
        {ExecutionMode.LIVE, ExecutionMode.PAPER, ExecutionMode.MOCK, ExecutionMode.SIMULATION}
    ),
    "python_exec": frozenset({ExecutionMode.LIVE, ExecutionMode.MOCK, ExecutionMode.SIMULATION}),
    "web_search": frozenset({ExecutionMode.LIVE, ExecutionMode.MOCK}),
    "calendar": frozenset({ExecutionMode.LIVE, ExecutionMode.MOCK}),
    "github": frozenset({ExecutionMode.LIVE, ExecutionMode.MOCK}),
    "obsidian": frozenset({ExecutionMode.LIVE, ExecutionMode.MOCK, ExecutionMode.SIMULATION}),
    "browser": frozenset({ExecutionMode.LIVE, ExecutionMode.MOCK, ExecutionMode.SIMULATION}),
}

_LEGACY_ACTION_TYPES: dict[str, str] = {
    "file_write": "file_write",
    "python_exec": "python_exec",
    "web_search": "web_search",
    "calendar": "notification",
}

_LEGACY_REQUIRES_CONFIRMATION: dict[str, bool] = {
    "file_write": True,
    "python_exec": True,
}

_LEGACY_DEPENDENCIES: dict[str, tuple[ToolDependency, ...]] = {
    "web_search": (ToolDependency("provider", "web_search"),),
    "calendar": (ToolDependency("provider", "calendar"),),
    "file_read": (ToolDependency("provider", "file_system"),),
    "file_write": (ToolDependency("provider", "file_system"),),
    "github": (ToolDependency("provider", "github"),),
}


def capability_from_tool(tool: BaseTool) -> ToolCapability:
    """Build a ToolCapability from a legacy BaseTool schema."""
    schema: ToolSchema = tool.schema
    name = schema.name
    return ToolCapability.from_schema(
        schema.name,
        schema.description,
        list(schema.parameters),
        invocation_mode=InvocationMode.SYNC,
        execution_mode=ExecutionMode.LIVE,
        supported_execution_modes=_LEGACY_EXECUTION_MODES.get(
            name, frozenset({ExecutionMode.LIVE})
        ),
        risk_level=_LEGACY_RISK_DEFAULTS.get(name, RiskLevel.LOW),
        health_state=ToolHealthState.UNKNOWN,
        requires_confirmation=_LEGACY_REQUIRES_CONFIRMATION.get(name),
        action_type=_LEGACY_ACTION_TYPES.get(name),
        provider_name=_LEGACY_PROVIDER_DEFAULTS.get(name),
        dependencies=_LEGACY_DEPENDENCIES.get(name, ()),
        tags=frozenset({"legacy"}),
    )


def register_legacy_tools(
    registry: ToolRegistry,
    catalog: CapabilityCatalog,
    resolver: DependencyResolver,
) -> None:
    """Populate capability catalog and dependency resolver from registered tools."""
    for name in registry.list_tools():
        tool = registry.get(name)
        if tool is None:
            continue
        capability = capability_from_tool(tool)
        if catalog.get(name) is None:
            catalog.register(capability)
        try:
            resolver.register_capability(capability)
        except ValueError:
            pass
