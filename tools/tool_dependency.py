# =====================================
# Titan Tool Dependency Graph
# =====================================

"""Tool and service dependency declarations (Phase 10A — P10A-005)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from tools.tool_enums import ToolHealthState


@dataclass(frozen=True)
class ToolDependency:
    """A single dependency on another tool, provider, or abstract service."""

    ref_type: str
    ref_id: str
    required: bool = True


@dataclass(frozen=True)
class DependencyCheckResult:
    """Outcome of a pre-execution dependency check."""

    satisfied: bool
    unavailable: tuple[ToolDependency, ...] = ()
    message: str = ""


HealthLookup = Callable[[str, str], ToolHealthState]
RegistrationLookup = Callable[[str, str], bool]


@dataclass
class DependencyGraph:
    """Directed dependency graph with cycle detection at registration."""

    _dependencies: dict[str, tuple[ToolDependency, ...]] = field(default_factory=dict)

    def register_tool(self, name: str, dependencies: tuple[ToolDependency, ...]) -> None:
        """Register dependencies for a tool; raises on duplicate or cycle."""
        if name in self._dependencies:
            raise ValueError(f"Dependencies already registered for tool: {name}")
        self._dependencies[name] = dependencies
        if self._has_cycle(name):
            del self._dependencies[name]
            raise ValueError(f"Circular dependency detected for tool: {name}")

    def get_dependencies(self, tool_name: str) -> tuple[ToolDependency, ...]:
        """Return declared dependencies for a tool."""
        return self._dependencies.get(tool_name, ())

    def check(
        self,
        tool_name: str,
        *,
        is_registered: RegistrationLookup,
        health_lookup: HealthLookup,
    ) -> DependencyCheckResult:
        """Verify required dependencies are registered and not offline/disabled."""
        deps = self.get_dependencies(tool_name)
        unavailable: list[ToolDependency] = []

        for dep in deps:
            if not dep.required:
                continue
            if not is_registered(dep.ref_type, dep.ref_id):
                unavailable.append(dep)
                continue
            health = health_lookup(dep.ref_type, dep.ref_id)
            if health in (ToolHealthState.OFFLINE, ToolHealthState.DISABLED):
                unavailable.append(dep)

        if unavailable:
            labels = ", ".join(f"{d.ref_type}:{d.ref_id}" for d in unavailable)
            return DependencyCheckResult(
                satisfied=False,
                unavailable=tuple(unavailable),
                message=f"Dépendances indisponibles : {labels}",
            )
        return DependencyCheckResult(satisfied=True)

    def _has_cycle(self, start: str) -> bool:
        """Detect cycles reachable from start using DFS."""
        visited: set[str] = set()
        stack: set[str] = set()

        def visit(node: str) -> bool:
            if node in stack:
                return True
            if node in visited:
                return False
            visited.add(node)
            stack.add(node)
            for dep in self._dependencies.get(node, ()):
                if dep.ref_type == "tool" and visit(dep.ref_id):
                    return True
            stack.remove(node)
            return False

        return visit(start)
