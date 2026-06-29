# =====================================
# Titan Tool Capability
# =====================================

"""Tool capability metadata for the Phase 10A runtime (P10A-003)."""

from __future__ import annotations

from dataclasses import dataclass

from tools.tool_dependency import ToolDependency
from tools.tool_enums import ExecutionMode, InvocationMode, RiskLevel, ToolHealthState
from tools.tool_quota import UsageQuota
from tools.tool_schema import ToolParameter


@dataclass(frozen=True)
class ToolCapability:
    """Frozen descriptor for a registered tool's runtime metadata."""

    name: str
    description: str
    parameters: tuple[ToolParameter, ...]
    invocation_mode: InvocationMode = InvocationMode.SYNC
    execution_mode: ExecutionMode = ExecutionMode.LIVE
    supported_execution_modes: frozenset[ExecutionMode] = frozenset({ExecutionMode.LIVE})
    risk_level: RiskLevel = RiskLevel.SAFE
    health_state: ToolHealthState = ToolHealthState.UNKNOWN
    requires_confirmation: bool | None = None
    idempotent: bool = False
    timeout_seconds: float | None = None
    max_retries: int = 0
    cancellable: bool = False
    stream_chunk_type: str = "text"
    provider_name: str | None = None
    tags: frozenset[str] = frozenset()
    dependencies: tuple[ToolDependency, ...] = ()
    quota: UsageQuota | None = None
    action_type: str | None = None

    @classmethod
    def from_schema(
        cls,
        schema_name: str,
        description: str,
        parameters: list[ToolParameter],
        **kwargs: object,
    ) -> ToolCapability:
        """Build a capability from legacy ToolSchema fields."""
        return cls(
            name=schema_name,
            description=description,
            parameters=tuple(parameters),
            **kwargs,  # type: ignore[arg-type]
        )
