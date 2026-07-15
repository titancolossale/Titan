# =====================================
# Titan Core Base Tool
# =====================================

"""Abstract contract for tools managed by the core tool registry."""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.actions.action import Action
from core.actions.action_result import ActionResult
from core.tools.tool_metadata import ToolMetadata


class BaseTool(ABC):
    """Abstract base class every Titan tool must inherit from.

    Subclasses declare identity and behavior through properties, expose discrete
    actions via ``list_actions`` / ``execute_action``, and may keep ``execute``
    for legacy callers. The registry may toggle ``enabled`` without re-registering.
    """

    def __init__(self) -> None:
        self._enabled: bool = True

    @property
    @abstractmethod
    def id(self) -> str:
        """Stable registry key for this tool."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable tool name."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description of what the tool does."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Semantic version string for the tool implementation."""

    @property
    @abstractmethod
    def category(self) -> str:
        """Logical grouping label (e.g. filesystem, web, system)."""

    @property
    def enabled(self) -> bool:
        """Whether the tool is currently enabled for invocation."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    @abstractmethod
    def requires_confirmation(self) -> bool:
        """True when live execution must be confirmed by the user."""

    @property
    @abstractmethod
    def capabilities(self) -> list[str]:
        """Capability identifiers exposed by this tool."""

    @property
    def author(self) -> str:
        """Tool author or maintainer."""
        return "Titan"

    @property
    def tags(self) -> list[str]:
        """Searchable tags for discovery."""
        return []

    @property
    def experimental(self) -> bool:
        """True when the tool is experimental."""
        return False

    @property
    def deprecated(self) -> bool:
        """True when the tool is deprecated."""
        return False

    @property
    def cost_estimate(self) -> str:
        """Relative cost hint (e.g. low, medium, high)."""
        return "low"

    @property
    def risk_level(self) -> str:
        """Relative risk level: low, medium, high, or critical."""
        return "medium" if self.requires_confirmation else "low"

    @property
    def streaming_support(self) -> bool:
        """True when the tool supports streaming responses."""
        return False

    @property
    def execution_traits(self) -> list[str]:
        """Execution characteristics: read_only, read_write, network, local, interactive."""
        traits: list[str] = ["local"]
        if self.category in {"web", "browser", "vcs", "email", "calendar", "trading"}:
            traits.append("network")
        if self.requires_confirmation or any(
            verb in cap
            for cap in self.capabilities
            for verb in ("write", "delete", "create", "edit", "patch", "execute", "run")
        ):
            traits.append("read_write")
        else:
            traits.append("read_only")
        if self.category in {"shell", "runtime", "terminal"}:
            traits.append("interactive")
        return sorted(set(traits))

    @property
    def input_schema(self) -> dict[str, object]:
        """Top-level input schema aggregated from actions."""
        properties: dict[str, object] = {}
        for action in self.list_actions():
            for name, spec in (action.parameters or {}).items():
                properties[name] = spec
        return {"type": "object", "properties": properties}

    @property
    def output_schema(self) -> dict[str, object]:
        """Top-level output schema hint."""
        return {"type": "object", "description": f"Structured result from {self.name}."}

    @property
    def examples(self) -> list[dict[str, object]]:
        """Optional usage examples for planners and UI."""
        return []

    @property
    def configuration_requirements(self) -> list[str]:
        """Environment variables or setup required before the tool is usable."""
        return []

    @property
    def status(self) -> str:
        """Operational status: active, disabled, error, experimental, or deprecated."""
        if self.deprecated:
            return "deprecated"
        if self.experimental:
            return "experimental"
        if not self.enabled:
            return "disabled"
        return "active"

    @abstractmethod
    def list_actions(self) -> list[Action]:
        """Return the discrete actions exposed by this tool."""

    @abstractmethod
    def execute_action(self, action_id: str, **kwargs: object) -> ActionResult:
        """Run a registered action and return a structured result."""

    @abstractmethod
    def execute(self, **kwargs: object) -> object:
        """Run the tool with the given parameters (legacy entry point)."""

    def to_metadata(self, *, author: str = "Titan") -> ToolMetadata:
        """Return an immutable metadata snapshot for this tool."""
        return ToolMetadata.from_tool(self, author=author)
