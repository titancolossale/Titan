# =====================================
# Titan Planning Models
# =====================================

"""Structured plan types for mission-linked planning (Phase 8 — P8-030).

Phase 17.1 — ``Plan`` is the next-action execution plan produced by the
Planning Engine from WorkspaceState + Goal / Project / Mission.

Phase 17.2 — plans evolve incrementally: ``revision``, ``change_reason``,
and ``latest_changes`` track what shifted when the workspace updates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class PlanStatus(str, Enum):
    """Lifecycle of a next-action execution plan."""

    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"


# Manual / importance / urgency weights from Goal|Project|Mission priority enums.
PRIORITY_WEIGHTS: dict[str, float] = {
    "LOW": 0.25,
    "NORMAL": 0.50,
    "HIGH": 0.75,
    "CRITICAL": 1.00,
}


def priority_weight(value: object | None, default: str = "NORMAL") -> float:
    """Map a priority enum/string to a 0.25–1.0 weight."""
    if value is None:
        key = default
    elif hasattr(value, "value"):
        key = str(getattr(value, "value")).upper()
    else:
        key = str(value).upper()
    return PRIORITY_WEIGHTS.get(key, PRIORITY_WEIGHTS[default])


def compute_priority_score(
    *,
    importance: float,
    urgency: float,
    manual_priority: float,
    dependency_factor: float = 1.0,
    is_blocked: bool = False,
) -> float:
    """Score what Titan should do next (0.0–1.0).

    Factors:
    - importance — typically goal priority
    - urgency — typically mission (or project) priority
    - manual_priority — explicit entity priority (mission > project > goal)
    - dependency_factor — 1.0 when clear; lower when unmet deps remain
    - blocked state — caps score and signals PLAN_BLOCKED separately
    """
    raw = (
        0.35 * importance
        + 0.35 * urgency
        + 0.20 * manual_priority
        + 0.10 * max(0.0, min(1.0, dependency_factor))
    )
    score = max(0.0, min(1.0, round(raw, 4)))
    if is_blocked:
        # Blocked plans stay visible but are deprioritized for execution.
        score = min(score, 0.35)
    return score


@dataclass
class PlanStep:
    """One actionable step within a structured plan."""

    order: int
    description: str
    linked_mission_step: str | None = None
    action_type: str = "respond"
    rationale: str = ""


@dataclass
class StructuredPlan:
    """Mission-aware turn plan produced by PlanningEngine (Phase 8)."""

    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    current_focus: str = ""
    mission_step: str | None = None
    domain: str = "general"

    def format_for_prompt(self) -> str:
        """French formatted block for PromptBuilder injection."""
        lines = [f"Objectif : {self.goal}"]
        if self.mission_step:
            lines.append(f"Étape mission liée : {self.mission_step}")
        if self.current_focus:
            lines.append(f"Focus actuel : {self.current_focus}")
        if self.domain != "general":
            lines.append(f"Domaine : {self.domain}")
        if self.steps:
            lines.append("Plan d'action :")
            for step in self.steps:
                marker = "→" if step.description == self.current_focus else f"{step.order}."
                suffix = f" [{step.action_type}]" if step.action_type != "respond" else ""
                lines.append(f"  {marker} {step.description}{suffix}")
        return "\n".join(lines)


# Canonical change_reason values for Phase 17.2 plan evolution.
CHANGE_REASON_CREATED = "plan_created"
CHANGE_REASON_MISSION_COMPLETED = "mission_completed"
CHANGE_REASON_MISSION_BLOCKED = "mission_blocked"
CHANGE_REASON_PROJECT_CHANGED = "project_changed"
CHANGE_REASON_GOAL_CHANGED = "goal_changed"
CHANGE_REASON_WORKSPACE_CHANGED = "workspace_changed"
CHANGE_REASON_CONTENT_UPDATED = "content_updated"
CHANGE_REASON_REFRESHED = "plan_refreshed"


@dataclass
class Plan:
    """Next-action execution plan — answers \"What should I do next?\".

    Built once per think from WorkspaceState + current Goal / Project / Mission.
    Does not replace GoalManager / ProjectManager / MissionManager ownership.

    Phase 17.2 — evolves in place across workspace changes: ``revision``
    increments on substantive updates; ``change_reason`` / ``latest_changes``
    explain what shifted.
    """

    current_goal: str | None
    current_project: str | None
    current_mission: str | None
    next_actions: list[str]
    priority_score: float
    estimated_duration: float | None
    dependencies: list[str]
    blocked_reason: str | None
    created_at: datetime
    updated_at: datetime
    status: PlanStatus = PlanStatus.ACTIVE
    revision: int = 1
    change_reason: str | None = None
    latest_changes: list[str] = field(default_factory=list)

    @property
    def is_blocked(self) -> bool:
        return self.status == PlanStatus.BLOCKED or bool(self.blocked_reason)

    @property
    def is_completed(self) -> bool:
        return self.status == PlanStatus.COMPLETED

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_goal": self.current_goal,
            "current_project": self.current_project,
            "current_mission": self.current_mission,
            "next_actions": list(self.next_actions),
            "priority_score": self.priority_score,
            "estimated_duration": self.estimated_duration,
            "dependencies": list(self.dependencies),
            "blocked_reason": self.blocked_reason,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status": self.status.value,
            "revision": self.revision,
            "change_reason": self.change_reason,
            "latest_changes": list(self.latest_changes),
        }

    def format_for_prompt(self) -> str:
        """Concise Current Plan block for PromptBuilder (Phase 17.1 / 17.2)."""
        actions = self.next_actions or []
        if actions:
            actions_text = "\n".join(f"- {action}" for action in actions)
        else:
            actions_text = "None"
        duration = (
            "None"
            if self.estimated_duration is None
            else f"{self.estimated_duration:g} min"
        )
        deps = ", ".join(self.dependencies) if self.dependencies else "None"
        changes = self.latest_changes or []
        if changes:
            changes_text = "\n".join(f"- {item}" for item in changes)
        else:
            changes_text = "None"
        return (
            f"Current Plan:\n"
            f"Goal: {self.current_goal or 'None'}\n"
            f"Project: {self.current_project or 'None'}\n"
            f"Mission: {self.current_mission or 'None'}\n"
            f"Status: {self.status.value}\n\n"
            f"Next Actions:\n{actions_text}\n\n"
            f"Priority:\n{self.priority_score}\n\n"
            f"Estimated Duration:\n{duration}\n\n"
            f"Dependencies:\n{deps}\n\n"
            f"Blocked Reason:\n{self.blocked_reason or 'None'}\n\n"
            f"Plan Revision:\n{self.revision}\n\n"
            f"Latest Changes:\n{changes_text}"
        )

    @classmethod
    def empty(cls, *, now: datetime | None = None) -> Plan:
        """Idle plan when no workspace focus exists."""
        stamp = now or datetime.now(timezone.utc)
        return cls(
            current_goal=None,
            current_project=None,
            current_mission=None,
            next_actions=[],
            priority_score=0.0,
            estimated_duration=None,
            dependencies=[],
            blocked_reason=None,
            created_at=stamp,
            updated_at=stamp,
            status=PlanStatus.ACTIVE,
            revision=1,
            change_reason=CHANGE_REASON_CREATED,
            latest_changes=[],
        )
