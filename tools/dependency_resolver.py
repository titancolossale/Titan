# =====================================
# Titan Dependency Resolver
# =====================================

"""Pre-flight dependency validation wired to registry and health (Phase 10A — P10A-013)."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.exceptions import ToolDependencyError
from tools.health_monitor import HealthMonitor
from tools.tool_dependency import DependencyCheckResult, DependencyGraph, ToolDependency
from tools.tool_capability import ToolCapability
from tools.tool_registry import ToolRegistry


@dataclass
class DependencyResolver:
    """Resolve and validate tool dependencies before execution."""

    graph: DependencyGraph = field(default_factory=DependencyGraph)
    health_monitor: HealthMonitor = field(default_factory=HealthMonitor)
    _known_providers: set[str] = field(default_factory=set)
    _known_services: set[str] = field(default_factory=lambda: {"network", "filesystem"})

    def register_capability(self, capability: ToolCapability) -> None:
        """Register tool dependencies from capability metadata."""
        if capability.dependencies:
            self.graph.register_tool(capability.name, capability.dependencies)
        if capability.provider_name:
            self._known_providers.add(capability.provider_name)

    def register_provider(self, provider_id: str) -> None:
        """Mark a provider as known for dependency checks."""
        self._known_providers.add(provider_id)

    def check(self, tool_name: str, *, registry: ToolRegistry) -> DependencyCheckResult:
        """Verify required dependencies for a tool invocation."""

        def is_registered(ref_type: str, ref_id: str) -> bool:
            if ref_type == "tool":
                return registry.get(ref_id) is not None
            if ref_type == "provider":
                return ref_id in self._known_providers
            if ref_type == "service":
                return ref_id in self._known_services
            return False

        return self.graph.check(
            tool_name,
            is_registered=is_registered,
            health_lookup=self.health_monitor.health_lookup,
        )

    def assert_satisfied(
        self,
        tool_name: str,
        *,
        registry: ToolRegistry,
    ) -> DependencyCheckResult:
        """Run dependency check and raise ToolDependencyError when unsatisfied."""
        result = self.check(tool_name, registry=registry)
        if not result.satisfied:
            raise ToolDependencyError(result.message or "Dépendances indisponibles.")
        return result

    def get_dependencies(self, tool_name: str) -> tuple[ToolDependency, ...]:
        """Return declared dependencies for a tool."""
        return self.graph.get_dependencies(tool_name)
