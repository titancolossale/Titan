# =====================================
# Titan Core Action Model
# =====================================

"""Action definitions exposed by Titan tools through the universal action layer."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Action:
    """A discrete capability exposed by a Titan tool.

    Attributes:
        id: Stable action key within the owning tool (e.g. ``read_note``).
        name: Human-readable action name.
        description: Short explanation of what the action does.
        tool_id: Registry id of the tool that owns this action.
        permission_id: Permission required before dispatching this action.
        parameters: Structured parameter schema for callers and planners.
        metadata: Optional structured context (capability tags, aliases, etc.).
    """

    id: str
    name: str
    description: str
    tool_id: str
    permission_id: str
    parameters: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)
