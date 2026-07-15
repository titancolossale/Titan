# =====================================
# Titan Core Action Result
# =====================================

"""Structured outcomes from action dispatch and tool execution."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ActionResult:
    """Result of an action dispatch or tool-level action execution.

    Attributes:
        success: Whether the action completed successfully.
        data: JSON-serializable payload produced by the action.
        message: Human-readable summary of the outcome.
        execution_time: Wall-clock duration in seconds for the dispatch.
        errors: Ordered list of error messages when ``success`` is False.
        metadata: Optional structured context (tool id, action id, permission, etc.).
    """

    success: bool
    data: object = None
    message: str = ""
    execution_time: float = 0.0
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
