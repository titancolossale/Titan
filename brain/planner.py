# =====================================
# Titan Planner
# =====================================

"""Build next-action plans from WorkspaceState + Goal / Project / Mission.

Phase 17.1 — Planning Engine foundation. Does not own Goal / Project / Mission
persistence; reads current focus and proposes what to do next.

Phase 17.2 — incremental evolution: compare previous plan to new workspace and
only recompute what changed (no unnecessary full rebuilds).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from brain.planning_models import (
    CHANGE_REASON_CONTENT_UPDATED,
    CHANGE_REASON_CREATED,
    CHANGE_REASON_GOAL_CHANGED,
    CHANGE_REASON_MISSION_BLOCKED,
    CHANGE_REASON_MISSION_COMPLETED,
    CHANGE_REASON_PROJECT_CHANGED,
    CHANGE_REASON_REFRESHED,
    CHANGE_REASON_WORKSPACE_CHANGED,
    Plan,
    PlanStatus,
    compute_priority_score,
    priority_weight,
)

logger = logging.getLogger(__name__)

# Rough minutes per remaining mission step for duration estimates.
_MINUTES_PER_STEP = 15.0

_BLOCKED_MISSION_STATES = frozenset({"BLOCKED", "WAITING"})

# Evolution modes returned alongside an evolved Plan.
EVOLVE_CREATED = "created"
EVOLVE_REBUILT = "rebuilt"
EVOLVE_UPDATED = "updated"
EVOLVE_REFRESHED = "refreshed"


class Planner:
    """Construct a ``Plan`` from workspace hierarchy (single-pass, no I/O)."""

    def build(
        self,
        *,
        workspace: Any | None = None,
        goal: Any | None = None,
        project: Any | None = None,
        mission: Any | None = None,
        mission_lookup: Callable[[str], Any | None] | None = None,
        now: datetime | None = None,
        change_reason: str | None = None,
        revision: int = 1,
        latest_changes: list[str] | None = None,
        created_at: datetime | None = None,
    ) -> Plan:
        """Build the next execution plan from current Goal / Project / Mission.

        Args:
            workspace: Request-scoped WorkspaceState (already loaded).
            goal: Optional active Goal entity.
            project: Optional active Project entity.
            mission: Optional active Mission entity.
            mission_lookup: Optional ``get_mission(id)`` for dependency checks.
            now: Optional clock override for tests.
            change_reason: Optional evolution reason (Phase 17.2).
            revision: Plan revision number (default 1 for new plans).
            latest_changes: Human-readable change bullets for prompts.
            created_at: Preserve lineage timestamp on incremental updates.

        Returns:
            A populated ``Plan`` (may be blocked or empty).
        """
        stamp = now or datetime.now(timezone.utc)
        current_goal = self._resolve_goal_name(goal, workspace)
        current_project = self._resolve_project_name(project, workspace)
        current_mission = self._resolve_mission_name(mission, workspace)

        dependencies = self._collect_dependencies(mission, mission_lookup)
        blocked_reason = self._resolve_blocked_reason(
            mission,
            workspace,
            dependencies,
            mission_lookup,
        )
        next_actions = self._build_next_actions(
            mission,
            workspace,
            project,
            goal,
            blocked=bool(blocked_reason),
        )
        estimated_duration = self._estimate_duration(mission, next_actions)

        importance = priority_weight(getattr(goal, "priority", None))
        urgency = priority_weight(
            getattr(mission, "priority", None)
            or getattr(workspace, "active_mission_priority", None)
            or getattr(project, "priority", None),
        )
        manual = priority_weight(
            getattr(mission, "priority", None)
            or getattr(project, "priority", None)
            or getattr(goal, "priority", None)
            or getattr(workspace, "active_mission_priority", None),
        )
        unmet = self._unmet_dependency_count(dependencies, mission_lookup)
        dependency_factor = 1.0 if unmet == 0 else max(0.0, 1.0 - 0.25 * unmet)
        is_blocked = bool(blocked_reason)
        priority_score = compute_priority_score(
            importance=importance,
            urgency=urgency,
            manual_priority=manual,
            dependency_factor=dependency_factor,
            is_blocked=is_blocked,
        )

        status = PlanStatus.BLOCKED if is_blocked else PlanStatus.ACTIVE
        if not is_blocked and self._is_hierarchy_completed(goal, project, mission):
            status = PlanStatus.COMPLETED
            next_actions = []
            estimated_duration = 0.0
            blocked_reason = None

        reason = change_reason or CHANGE_REASON_CREATED
        changes = list(latest_changes) if latest_changes is not None else [reason]

        return Plan(
            current_goal=current_goal,
            current_project=current_project,
            current_mission=current_mission,
            next_actions=next_actions,
            priority_score=priority_score,
            estimated_duration=estimated_duration,
            dependencies=dependencies,
            blocked_reason=blocked_reason,
            created_at=created_at or stamp,
            updated_at=stamp,
            status=status,
            revision=revision,
            change_reason=reason,
            latest_changes=changes,
        )

    def evolve(
        self,
        previous: Plan,
        *,
        workspace: Any | None = None,
        goal: Any | None = None,
        project: Any | None = None,
        mission: Any | None = None,
        mission_lookup: Callable[[str], Any | None] | None = None,
        now: datetime | None = None,
        forced_reason: str | None = None,
    ) -> tuple[Plan, str]:
        """Compare ``previous`` to the new workspace and update only what changed.

        Returns:
            ``(plan, mode)`` where mode is one of:
            ``created``, ``rebuilt``, ``updated``, ``refreshed``.
        """
        stamp = now or datetime.now(timezone.utc)
        candidate = self.build(
            workspace=workspace,
            goal=goal,
            project=project,
            mission=mission,
            mission_lookup=mission_lookup,
            now=stamp,
        )

        reasons = self._detect_change_reasons(
            previous,
            candidate,
            workspace=workspace,
            forced_reason=forced_reason,
        )
        content_changed = self._content_differs(previous, candidate)
        focus_changed = not self._same_focus(previous, candidate)

        # No substantive delta — soft refresh (preserve revision). Forced reasons
        # alone do not bump revision when plan content is unchanged.
        if not content_changed and not focus_changed:
            refreshed = Plan(
                current_goal=previous.current_goal,
                current_project=previous.current_project,
                current_mission=previous.current_mission,
                next_actions=list(previous.next_actions),
                priority_score=previous.priority_score,
                estimated_duration=previous.estimated_duration,
                dependencies=list(previous.dependencies),
                blocked_reason=previous.blocked_reason,
                created_at=previous.created_at,
                updated_at=stamp,
                status=previous.status,
                revision=previous.revision,
                change_reason=CHANGE_REASON_REFRESHED,
                latest_changes=[CHANGE_REASON_REFRESHED],
            )
            return refreshed, EVOLVE_REFRESHED

        if focus_changed:
            primary = self._primary_reason(reasons, default=CHANGE_REASON_CONTENT_UPDATED)
            changes = self._build_latest_changes(previous, candidate, reasons)
            rebuilt = self.build(
                workspace=workspace,
                goal=goal,
                project=project,
                mission=mission,
                mission_lookup=mission_lookup,
                now=stamp,
                change_reason=primary,
                revision=previous.revision + 1,
                latest_changes=changes,
                created_at=stamp,
            )
            return rebuilt, EVOLVE_REBUILT

        # Same focus — incremental field merge (preserve created_at / lineage).
        primary = self._primary_reason(reasons, default=CHANGE_REASON_CONTENT_UPDATED)
        changes = self._build_latest_changes(previous, candidate, reasons)
        updated = Plan(
            current_goal=candidate.current_goal,
            current_project=candidate.current_project,
            current_mission=candidate.current_mission,
            next_actions=list(candidate.next_actions),
            priority_score=candidate.priority_score,
            estimated_duration=candidate.estimated_duration,
            dependencies=list(candidate.dependencies),
            blocked_reason=candidate.blocked_reason,
            created_at=previous.created_at,
            updated_at=stamp,
            status=candidate.status,
            revision=previous.revision + 1,
            change_reason=primary,
            latest_changes=changes,
        )
        return updated, EVOLVE_UPDATED

    @staticmethod
    def _same_focus(previous: Plan, current: Plan) -> bool:
        return (
            previous.current_goal == current.current_goal
            and previous.current_project == current.current_project
            and previous.current_mission == current.current_mission
        )

    @staticmethod
    def _content_differs(previous: Plan, current: Plan) -> bool:
        return (
            previous.next_actions != current.next_actions
            or previous.priority_score != current.priority_score
            or previous.estimated_duration != current.estimated_duration
            or previous.dependencies != current.dependencies
            or previous.blocked_reason != current.blocked_reason
            or previous.status != current.status
        )

    def _detect_change_reasons(
        self,
        previous: Plan,
        candidate: Plan,
        *,
        workspace: Any | None,
        forced_reason: str | None,
    ) -> list[str]:
        reasons: list[str] = []
        if forced_reason:
            reasons.append(forced_reason)

        if previous.current_goal != candidate.current_goal:
            if CHANGE_REASON_GOAL_CHANGED not in reasons:
                reasons.append(CHANGE_REASON_GOAL_CHANGED)
        if previous.current_project != candidate.current_project:
            if CHANGE_REASON_PROJECT_CHANGED not in reasons:
                reasons.append(CHANGE_REASON_PROJECT_CHANGED)

        prev_blocked = previous.is_blocked
        now_blocked = candidate.is_blocked
        if not prev_blocked and now_blocked:
            if CHANGE_REASON_MISSION_BLOCKED not in reasons:
                reasons.append(CHANGE_REASON_MISSION_BLOCKED)
        if previous.status != PlanStatus.COMPLETED and candidate.status == PlanStatus.COMPLETED:
            if CHANGE_REASON_MISSION_COMPLETED not in reasons:
                reasons.append(CHANGE_REASON_MISSION_COMPLETED)

        # Workspace operational fields — only when plan content also shifted.
        if workspace is not None and self._content_differs(previous, candidate):
            ws_goal = self._resolve_goal_name(None, workspace)
            ws_project = self._resolve_project_name(None, workspace)
            ws_mission = self._resolve_mission_name(None, workspace)
            ws_step = getattr(workspace, "current_step", None)
            ws_next = getattr(workspace, "next_action", None)
            ws_status = str(
                getattr(workspace, "active_mission_status", None) or ""
            ).upper()
            ws_implies_change = (
                (ws_goal is not None and ws_goal != previous.current_goal)
                or (ws_project is not None and ws_project != previous.current_project)
                or (ws_mission is not None and ws_mission != previous.current_mission)
                or (
                    ws_step
                    and previous.next_actions
                    and str(ws_step) != previous.next_actions[0]
                )
                or (
                    ws_next
                    and previous.next_actions
                    and str(ws_next) != previous.next_actions[0]
                )
                or (ws_status == "BLOCKED" and not previous.is_blocked)
                or previous.next_actions != candidate.next_actions
            )
            if ws_implies_change and CHANGE_REASON_WORKSPACE_CHANGED not in reasons:
                reasons.append(CHANGE_REASON_WORKSPACE_CHANGED)

        if self._content_differs(previous, candidate) and not reasons:
            reasons.append(CHANGE_REASON_CONTENT_UPDATED)

        # Deduplicate while preserving order.
        seen: set[str] = set()
        ordered: list[str] = []
        for reason in reasons:
            if reason not in seen:
                seen.add(reason)
                ordered.append(reason)
        return ordered

    @staticmethod
    def _primary_reason(reasons: list[str], *, default: str) -> str:
        if not reasons:
            return default
        # Prefer the most specific trigger order.
        priority = (
            CHANGE_REASON_MISSION_COMPLETED,
            CHANGE_REASON_MISSION_BLOCKED,
            CHANGE_REASON_GOAL_CHANGED,
            CHANGE_REASON_PROJECT_CHANGED,
            CHANGE_REASON_WORKSPACE_CHANGED,
            CHANGE_REASON_CONTENT_UPDATED,
        )
        for key in priority:
            if key in reasons:
                return key
        return reasons[0]

    @staticmethod
    def _build_latest_changes(
        previous: Plan,
        candidate: Plan,
        reasons: list[str],
    ) -> list[str]:
        changes = list(reasons)
        if previous.next_actions != candidate.next_actions:
            changes.append("next_actions updated")
        if previous.status != candidate.status:
            changes.append(f"status {previous.status.value} → {candidate.status.value}")
        if previous.blocked_reason != candidate.blocked_reason:
            if candidate.blocked_reason:
                changes.append(f"blocked: {candidate.blocked_reason}")
            else:
                changes.append("block cleared")
        if previous.priority_score != candidate.priority_score:
            changes.append(
                f"priority {previous.priority_score} → {candidate.priority_score}"
            )
        # Deduplicate.
        seen: set[str] = set()
        ordered: list[str] = []
        for item in changes:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
        return ordered or [CHANGE_REASON_CONTENT_UPDATED]

    @staticmethod
    def _resolve_goal_name(goal: Any | None, workspace: Any | None) -> str | None:
        if goal is not None:
            name = getattr(goal, "name", None)
            if name:
                return str(name)
        if workspace is None:
            return None
        name = getattr(workspace, "active_goal", None)
        return str(name) if name else None

    @staticmethod
    def _resolve_project_name(
        project: Any | None,
        workspace: Any | None,
    ) -> str | None:
        if project is not None:
            name = getattr(project, "name", None)
            if name:
                return str(name)
        if workspace is None:
            return None
        name = getattr(workspace, "active_project", None)
        return str(name) if name else None

    @staticmethod
    def _resolve_mission_name(
        mission: Any | None,
        workspace: Any | None,
    ) -> str | None:
        if mission is not None:
            title = getattr(mission, "title", None)
            if title:
                return str(title)
        if workspace is None:
            return None
        title = getattr(workspace, "active_mission_title", None) or getattr(
            workspace,
            "active_mission",
            None,
        )
        return str(title) if title else None

    @staticmethod
    def _collect_dependencies(
        mission: Any | None,
        mission_lookup: Callable[[str], Any | None] | None,
    ) -> list[str]:
        deps: list[str] = []
        if mission is None:
            return deps
        parent_id = getattr(mission, "parent_mission", None)
        if parent_id:
            # Always key by id so mission_lookup can resolve completion status.
            deps.append(f"parent_mission:{parent_id}")
        # Remaining steps after the current one are soft dependencies for ordering.
        remaining = list(getattr(mission, "remaining_steps", None) or [])
        current = getattr(mission, "current_step", None)
        if remaining and current and current in remaining:
            idx = remaining.index(current)
            for step in remaining[idx + 1 :]:
                deps.append(f"step:{step}")
        elif remaining and current:
            for step in remaining:
                if step != current:
                    deps.append(f"step:{step}")
        return deps

    @staticmethod
    def _dependency_label(
        dep: str,
        mission_lookup: Callable[[str], Any | None] | None,
    ) -> str:
        if not dep.startswith("parent_mission:"):
            return dep
        parent_id = dep.split(":", 1)[1]
        if mission_lookup is None:
            return dep
        parent = mission_lookup(parent_id)
        if parent is None:
            return dep
        title = getattr(parent, "title", None)
        if title:
            return f"parent_mission:{title}"
        return dep

    @staticmethod
    def _unmet_dependency_count(
        dependencies: list[str],
        mission_lookup: Callable[[str], Any | None] | None,
    ) -> int:
        unmet = 0
        for dep in dependencies:
            if not dep.startswith("parent_mission:"):
                continue
            if mission_lookup is None:
                unmet += 1
                continue
            parent_id = dep.split(":", 1)[1]
            parent = mission_lookup(parent_id)
            if parent is None:
                unmet += 1
                continue
            state = getattr(parent, "state", None)
            status = getattr(parent, "status", None)
            state_value = getattr(state, "value", state)
            if str(status).upper() == "COMPLETED" or str(state_value).upper() == "COMPLETED":
                continue
            unmet += 1
        return unmet

    def _resolve_blocked_reason(
        self,
        mission: Any | None,
        workspace: Any | None,
        dependencies: list[str],
        mission_lookup: Callable[[str], Any | None] | None,
    ) -> str | None:
        if mission is not None:
            state = getattr(mission, "state", None)
            state_value = str(getattr(state, "value", state) or "").upper()
            status = str(getattr(mission, "status", "") or "").upper()
            if state_value in _BLOCKED_MISSION_STATES or status == "BLOCKED":
                notes = (getattr(mission, "notes", None) or "").strip()
                if notes:
                    return f"Mission blocked: {notes}"
                return f"Mission state is {state_value or status}"
        if workspace is not None:
            stage = str(getattr(workspace, "active_mission_stage", "") or "").upper()
            status = str(getattr(workspace, "active_mission_status", "") or "").upper()
            if stage in _BLOCKED_MISSION_STATES or status == "BLOCKED":
                return f"Mission status is {status or stage}"

        unmet_parents = [
            dep
            for dep in dependencies
            if dep.startswith("parent_mission:")
        ]
        if unmet_parents and self._unmet_dependency_count(
            unmet_parents,
            mission_lookup,
        ):
            label = self._dependency_label(unmet_parents[0], mission_lookup)
            return f"Waiting on dependency: {label}"
        return None

    @staticmethod
    def _build_next_actions(
        mission: Any | None,
        workspace: Any | None,
        project: Any | None,
        goal: Any | None,
        *,
        blocked: bool,
    ) -> list[str]:
        if blocked:
            return []
        actions: list[str] = []
        if mission is not None:
            current = getattr(mission, "current_step", None)
            nxt = getattr(mission, "next_step", None)
            remaining = list(getattr(mission, "remaining_steps", None) or [])
            if current:
                actions.append(str(current))
            if nxt and nxt != current:
                actions.append(str(nxt))
            for step in remaining:
                text = str(step)
                if text not in actions:
                    actions.append(text)
            if actions:
                return actions[:5]
            objective = getattr(mission, "objective", None) or getattr(
                mission,
                "description",
                None,
            )
            if objective:
                return [f"Advance mission: {objective}"]
            title = getattr(mission, "title", None)
            if title:
                return [f"Advance mission: {title}"]

        if workspace is not None:
            step = getattr(workspace, "current_step", None) or getattr(
                workspace,
                "active_mission_current_objective",
                None,
            )
            if step:
                return [str(step)]
            next_action = getattr(workspace, "next_action", None)
            if next_action:
                return [str(next_action)]

        if project is not None:
            name = getattr(project, "name", None)
            if name:
                return [f"Advance project: {name}"]
        if goal is not None:
            name = getattr(goal, "name", None)
            if name:
                return [f"Advance goal: {name}"]
        return []

    @staticmethod
    def _estimate_duration(
        mission: Any | None,
        next_actions: list[str],
    ) -> float | None:
        if not next_actions:
            return None
        remaining = list(getattr(mission, "remaining_steps", None) or []) if mission else []
        count = len(remaining) if remaining else len(next_actions)
        return round(max(1, count) * _MINUTES_PER_STEP, 1)

    @staticmethod
    def _is_hierarchy_completed(
        goal: Any | None,
        project: Any | None,
        mission: Any | None,
    ) -> bool:
        """True when the focused mission (or project/goal) is already completed."""
        if mission is not None:
            state = getattr(mission, "state", None)
            state_value = str(getattr(state, "value", state) or "").upper()
            status = str(getattr(mission, "status", "") or "").upper()
            return status == "COMPLETED" or state_value == "COMPLETED"
        if project is not None:
            status = str(getattr(project, "status", "") or "").upper()
            return status == "COMPLETED"
        if goal is not None:
            status = str(getattr(goal, "status", "") or "").upper()
            return status == "COMPLETED"
        return False
