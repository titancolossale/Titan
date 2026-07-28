# =====================================
# Titan Think Context Bundle
# =====================================

"""Typed data bundle passed between Brain pipeline stages (Phase 2 — P2-010)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from agents.agent_result import AgentResult
from context.models import ContextSnapshot
from memory.models import RetrievalResult
from tools.decision.models import ToolDecisionReport
from tools.tool_result import ToolRequest, ToolResult

if TYPE_CHECKING:
    from core.state_manager import WorkspaceState

logger = logging.getLogger(__name__)

_MISSION_MIRROR_FIELDS: tuple[str, ...] = (
    "active_mission",
    "active_mission_id",
    "active_mission_title",
    "active_mission_status",
    "active_mission_progress",
    "active_mission_priority",
    "active_mission_stage",
    # Phase 14.4 — progress / resume continuity
    "active_mission_last_completed_step",
    "active_mission_last_summary",
    "active_mission_progress_updated_at",
    "active_mission_current_objective",
    # Phase 14.5 — multi-mission workspace metadata
    "missions",
    "mission_queue_count",
    "paused_mission_count",
)

_PROJECT_MIRROR_FIELDS: tuple[str, ...] = (
    "active_project",
    "active_project_id",
    "active_project_status",
    "active_project_progress",
    "projects",
    # Phase 15.2 — progress / resume continuity
    "active_project_active_mission",
    "active_project_completed_missions",
    "active_project_last_completed_step",
    "active_project_last_summary",
    "active_project_progress_updated_at",
    "active_project_current_objective",
)

_GOAL_MIRROR_FIELDS: tuple[str, ...] = (
    "active_goal_id",
    "active_goal",
    "active_goal_status",
    "active_goal_progress",
    "goals",
    # Phase 16.2 — progress / resume continuity
    "active_goal_completed_projects",
    "active_goal_active_projects",
    "active_goal_paused_projects",
    "active_goal_total_projects",
    "active_goal_last_activity",
    "active_goal_current_project",
    "active_goal_current_mission",
    "active_goal_last_summary",
    "active_goal_progress_updated_at",
)

_SUMMARY_MAX_CHARS = 240


@dataclass(frozen=True)
class GoalContext:
    """WorkspaceState-derived active-goal awareness (Phase 16.1–16.3).

    Loaded once per think cycle from the request-scoped WorkspaceState alongside
    project and mission awareness — no duplicated GoalManager lookups.

    Phase 16.2 — progress metrics + resume continuity (current project/mission).
    Phase 16.3 — match confidence + selection reason for PromptBuilder.
    """

    name: str | None = None
    status: str | None = None
    progress: float | None = None
    goal_id: str | None = None
    # Phase 16.2 — progress metrics
    completed_projects: int = 0
    active_projects: int = 0
    paused_projects: int = 0
    total_projects: int = 0
    last_activity: str | None = None
    # Phase 16.2 — resume continuity
    current_project: str | None = None
    current_mission: str | None = None
    last_summary: str | None = None
    progress_updated_at: str | None = None
    # Phase 16.3 — automatic matching metadata
    match_confidence: float | None = None
    selection_reason: str | None = None

    @property
    def has_active_goal(self) -> bool:
        return bool(self.goal_id or self.name)

    def to_prompt_block(self) -> str:
        """Concise goal + confidence + resume section for LLM prompts (Phase 16.3)."""
        progress = self.progress
        if progress is None:
            progress_text = "None"
        else:
            progress_text = str(progress)
        confidence = self.match_confidence
        if confidence is None:
            confidence_text = "None"
        else:
            confidence_text = str(confidence)
        return (
            f"Current Goal:\n{self.name or 'None'}\n\n"
            f"Confidence:\n{confidence_text}\n\n"
            f"Reason for selection:\n{self.selection_reason or 'None'}\n\n"
            f"Goal Progress:\n{progress_text}\n\n"
            f"Current Project:\n{self.current_project or 'None'}\n\n"
            f"Current Mission:\n{self.current_mission or 'None'}"
        )

    @classmethod
    def from_workspace(cls, workspace: WorkspaceState | None) -> GoalContext | None:
        """Build goal awareness from WorkspaceState, or None when inactive."""
        if workspace is None:
            return None
        goal_id = getattr(workspace, "active_goal_id", None)
        name = getattr(workspace, "active_goal", None)
        status = getattr(workspace, "active_goal_status", None)
        progress = getattr(workspace, "active_goal_progress", None)
        if not goal_id and not status and progress is None:
            return None
        if not goal_id and not name:
            return None
        current_project = getattr(workspace, "active_goal_current_project", None)
        if not current_project:
            current_project = getattr(workspace, "active_project", None)
        current_mission = getattr(workspace, "active_goal_current_mission", None)
        if not current_mission:
            current_mission = (
                getattr(workspace, "active_mission_title", None)
                or getattr(workspace, "active_mission", None)
                or getattr(workspace, "active_project_active_mission", None)
            )
        return cls(
            name=name,
            status=status,
            progress=progress,
            goal_id=goal_id,
            completed_projects=int(
                getattr(workspace, "active_goal_completed_projects", 0) or 0
            ),
            active_projects=int(
                getattr(workspace, "active_goal_active_projects", 0) or 0
            ),
            paused_projects=int(
                getattr(workspace, "active_goal_paused_projects", 0) or 0
            ),
            total_projects=int(
                getattr(workspace, "active_goal_total_projects", 0) or 0
            ),
            last_activity=getattr(workspace, "active_goal_last_activity", None),
            current_project=current_project,
            current_mission=current_mission,
            last_summary=getattr(workspace, "active_goal_last_summary", None),
            progress_updated_at=getattr(
                workspace, "active_goal_progress_updated_at", None
            ),
        )


@dataclass(frozen=True)
class ProjectContext:
    """WorkspaceState-derived active-project awareness (Phase 15.1 / 15.2).

    Loaded once per think cycle from the request-scoped WorkspaceState alongside
    mission awareness — no duplicated ProjectManager / StateManager lookups.

    Phase 15.2 — resume continuity (active mission, last step, summary, objective).
    """

    name: str | None = None
    status: str | None = None
    progress: float | None = None
    project_id: str | None = None
    # Phase 15.2 — resume continuity
    active_mission: str | None = None
    completed_missions: tuple[str, ...] = ()
    last_completed_step: str | None = None
    last_summary: str | None = None
    progress_updated_at: str | None = None
    current_objective: str | None = None

    @property
    def has_active_project(self) -> bool:
        return bool(self.project_id or self.name)

    def to_prompt_block(self) -> str:
        """Concise project + resume section for LLM prompt assembly (Phase 15.2)."""
        progress = self.progress
        if progress is None:
            progress_text = "None"
        else:
            progress_text = str(progress)
        return (
            f"Current Project:\n{self.name or 'None'}\n\n"
            f"Project Progress:\n{progress_text}\n\n"
            f"Current Mission:\n{self.active_mission or 'None'}\n\n"
            f"Last Completed Step:\n{self.last_completed_step or 'None'}\n\n"
            f"Current Objective:\n{self.current_objective or 'None'}"
        )

    @classmethod
    def from_workspace(cls, workspace: WorkspaceState | None) -> ProjectContext | None:
        """Build project awareness from WorkspaceState, or None when inactive."""
        if workspace is None:
            return None
        project_id = getattr(workspace, "active_project_id", None)
        name = getattr(workspace, "active_project", None)
        status = getattr(workspace, "active_project_status", None)
        progress = getattr(workspace, "active_project_progress", None)
        if not project_id and not status and progress is None:
            # Legacy string-only active_project without a ProjectManager registry.
            return None
        if not project_id and not name:
            return None
        completed_raw = getattr(workspace, "active_project_completed_missions", None) or []
        completed = tuple(str(item) for item in completed_raw if item)
        return cls(
            name=name,
            status=status,
            progress=progress,
            project_id=project_id,
            active_mission=getattr(workspace, "active_project_active_mission", None),
            completed_missions=completed,
            last_completed_step=getattr(
                workspace, "active_project_last_completed_step", None
            ),
            last_summary=getattr(workspace, "active_project_last_summary", None),
            progress_updated_at=getattr(
                workspace, "active_project_progress_updated_at", None
            ),
            current_objective=getattr(
                workspace, "active_project_current_objective", None
            ),
        )


@dataclass(frozen=True)
class MissionContext:
    """WorkspaceState-derived active-mission awareness (Phase 14.3 / 14.4 / 14.5).

    Loaded once per think cycle from the request-scoped WorkspaceState and
    shared by every subsystem via ``ThinkContext.mission_context``.

    Phase 14.5 — includes concise queue/paused counts only; other missions never
    pollute the prompt with full payloads.
    """

    active_mission: str | None = None
    status: str | None = None
    progress: float | None = None
    priority: str | None = None
    stage: str | None = None
    # Phase 14.4 — resume continuity
    last_completed_step: str | None = None
    last_summary: str | None = None
    progress_updated_at: str | None = None
    current_objective: str | None = None
    # Phase 14.5 — concise multi-mission metadata
    queue_count: int = 0
    paused_count: int = 0

    @property
    def has_active_mission(self) -> bool:
        return bool(self.active_mission or self.status is not None)

    def to_prompt_block(self) -> str:
        """Concise mission section for LLM prompt assembly (Phase 14.5 / 15.1)."""
        progress = self.progress
        if progress is None:
            progress_text = "None"
        else:
            progress_text = str(progress)
        return (
            f"Current Mission:\n{self.active_mission or 'None'}\n\n"
            f"Active Mission:\n{self.active_mission or 'None'}\n\n"
            f"Status:\n{self.status or 'None'}\n\n"
            f"Mission Progress:\n{progress_text}\n\n"
            f"Progress:\n{progress_text}\n\n"
            f"Priority:\n{self.priority or 'None'}\n\n"
            f"Stage:\n{self.stage or 'None'}\n\n"
            f"Mission Queue Count:\n{self.queue_count}\n\n"
            f"Paused Mission Count:\n{self.paused_count}"
        )

    def to_resume_prompt_block(self) -> str:
        """Mission resume section for multi-turn continuity (Phase 14.4)."""
        progress = self.progress
        if progress is None:
            progress_text = "None"
        else:
            progress_text = str(progress)
        return (
            f"Mission Resume\n\n"
            f"Current Stage\n{self.stage or 'None'}\n\n"
            f"Previous Progress\n{progress_text}\n\n"
            f"Last Completed Step\n{self.last_completed_step or 'None'}\n\n"
            f"Current Objective\n{self.current_objective or 'None'}"
        )

    @classmethod
    def from_workspace(cls, workspace: WorkspaceState | None) -> MissionContext | None:
        """Build mission awareness from WorkspaceState, or None when inactive."""
        if workspace is None:
            return None
        title = workspace.active_mission_title or workspace.active_mission
        queue_count = int(getattr(workspace, "mission_queue_count", 0) or 0)
        paused_count = int(getattr(workspace, "paused_mission_count", 0) or 0)
        has_active = bool(workspace.active_mission_id or title)
        if not has_active and queue_count == 0 and paused_count == 0:
            return None
        if not has_active:
            # Counts-only awareness — no active mission for Brain reasoning.
            return cls(queue_count=queue_count, paused_count=paused_count)
        return cls(
            active_mission=title,
            status=workspace.active_mission_status,
            progress=workspace.active_mission_progress,
            priority=workspace.active_mission_priority,
            stage=workspace.active_mission_stage,
            last_completed_step=workspace.active_mission_last_completed_step,
            last_summary=workspace.active_mission_last_summary,
            progress_updated_at=workspace.active_mission_progress_updated_at,
            current_objective=workspace.active_mission_current_objective,
            queue_count=queue_count,
            paused_count=paused_count,
        )


def inject_mission_context(ctx: ThinkContext) -> MissionContext | None:
    """Derive and attach ``mission_context`` from ``ctx.workspace_state``.

    Does not reload StateManager — uses the request-scoped WorkspaceState only.
    Phase 14.4 — also logs resume load/inject diagnostics when a mission is active.
    """
    workspace = ctx.workspace_state
    if workspace is not None and (
        getattr(workspace, "active_mission_id", None)
        or getattr(workspace, "active_mission_title", None)
        or getattr(workspace, "active_mission", None)
    ):
        logger.info(
            "MISSION_RESUME_LOADED stage=%s progress=%s last_completed=%s "
            "objective=%s updated_at=%s",
            getattr(workspace, "active_mission_stage", None),
            getattr(workspace, "active_mission_progress", None),
            getattr(workspace, "active_mission_last_completed_step", None),
            getattr(workspace, "active_mission_current_objective", None),
            getattr(workspace, "active_mission_progress_updated_at", None),
        )

    mission_context = MissionContext.from_workspace(workspace)
    ctx.mission_context = mission_context
    logger.info(
        "MISSION_CONTEXT_INJECTED has_active=%s title=%s",
        mission_context is not None,
        getattr(mission_context, "active_mission", None),
    )
    if mission_context is not None and mission_context.has_active_mission:
        logger.info(
            "MISSION_RESUME_INJECTED stage=%s progress=%s last_completed=%s "
            "objective=%s",
            mission_context.stage,
            mission_context.progress,
            mission_context.last_completed_step,
            mission_context.current_objective,
        )
    return mission_context


def inject_project_context(ctx: ThinkContext) -> ProjectContext | None:
    """Derive and attach ``project_context`` from ``ctx.workspace_state``.

    Uses the same request-scoped WorkspaceState as mission injection — no extra
    StateManager or ProjectManager lookup.

    Phase 15.2 — also logs resume load/inject diagnostics when a project is active.
    """
    workspace = ctx.workspace_state
    if workspace is not None and (
        getattr(workspace, "active_project_id", None)
        or getattr(workspace, "active_project_status", None)
    ):
        logger.info(
            "PROJECT_RESUME_LOADED project=%s progress=%s active_mission=%s "
            "last_completed=%s objective=%s summary=%s updated_at=%s",
            getattr(workspace, "active_project", None),
            getattr(workspace, "active_project_progress", None),
            getattr(workspace, "active_project_active_mission", None),
            getattr(workspace, "active_project_last_completed_step", None),
            getattr(workspace, "active_project_current_objective", None),
            getattr(workspace, "active_project_last_summary", None),
            getattr(workspace, "active_project_progress_updated_at", None),
        )

    project_context = ProjectContext.from_workspace(workspace)
    ctx.project_context = project_context
    logger.info(
        "PROJECT_CONTEXT_INJECTED has_active=%s name=%s",
        project_context is not None and project_context.has_active_project,
        getattr(project_context, "name", None),
    )
    if project_context is not None and project_context.has_active_project:
        logger.info(
            "PROJECT_LOADED id=%s name=%r status=%s progress=%s",
            project_context.project_id,
            project_context.name,
            project_context.status,
            project_context.progress,
        )
        logger.info(
            "PROJECT_RESUME_INJECTED project=%s progress=%s active_mission=%s "
            "last_completed=%s objective=%s",
            project_context.name,
            project_context.progress,
            project_context.active_mission,
            project_context.last_completed_step,
            project_context.current_objective,
        )
    return project_context


def inject_goal_context(ctx: ThinkContext) -> GoalContext | None:
    """Derive and attach ``goal_context`` from ``ctx.workspace_state``.

    Uses the same request-scoped WorkspaceState as project/mission injection —
    no extra StateManager or GoalManager lookup.

    Phase 16.2 — also logs resume load/inject diagnostics when a goal is active.
    Phase 16.3 — attaches match confidence + selection reason from the
    pre-load GoalMatcher pass (single scan; no rematch).
    """
    workspace = ctx.workspace_state
    if workspace is not None and (
        getattr(workspace, "active_goal_id", None)
        or getattr(workspace, "active_goal_status", None)
    ):
        logger.info(
            "GOAL_RESUME_LOADED goal=%s progress=%s project=%s mission=%s "
            "completed=%s total=%s last_activity=%s updated_at=%s",
            getattr(workspace, "active_goal", None),
            getattr(workspace, "active_goal_progress", None),
            getattr(workspace, "active_goal_current_project", None)
            or getattr(workspace, "active_project", None),
            getattr(workspace, "active_goal_current_mission", None)
            or getattr(workspace, "active_mission_title", None)
            or getattr(workspace, "active_mission", None),
            getattr(workspace, "active_goal_completed_projects", 0),
            getattr(workspace, "active_goal_total_projects", 0),
            getattr(workspace, "active_goal_last_activity", None),
            getattr(workspace, "active_goal_progress_updated_at", None),
        )

    goal_context = GoalContext.from_workspace(workspace)
    if goal_context is not None:
        match_confidence = getattr(ctx, "goal_match_confidence", None)
        selection_reason = getattr(ctx, "goal_match_reason", None)
        if match_confidence is not None or selection_reason is not None:
            goal_context = replace(
                goal_context,
                match_confidence=match_confidence,
                selection_reason=selection_reason,
            )
    ctx.goal_context = goal_context
    logger.info(
        "GOAL_CONTEXT_INJECTED has_active=%s name=%s",
        goal_context is not None and goal_context.has_active_goal,
        getattr(goal_context, "name", None),
    )
    if goal_context is not None and goal_context.has_active_goal:
        logger.info(
            "GOAL_LOADED id=%s name=%r status=%s progress=%s",
            goal_context.goal_id,
            goal_context.name,
            goal_context.status,
            goal_context.progress,
        )
        logger.info(
            "GOAL_RESUME_INJECTED goal=%s progress=%s project=%s mission=%s",
            goal_context.name,
            goal_context.progress,
            goal_context.current_project,
            goal_context.current_mission,
        )
    return goal_context


def _summarize_mission_progress(response: str) -> str:
    """Build a short durable resume summary from the successful turn response."""
    text = " ".join((response or "").split())
    if not text:
        return ""
    if len(text) <= _SUMMARY_MAX_CHARS:
        return text
    return text[: _SUMMARY_MAX_CHARS - 3].rstrip() + "..."


def apply_mission_progress_update(ctx: ThinkContext) -> bool:
    """Write mission resume fields onto request-scoped WorkspaceState (Phase 14.4).

    Called after a successful think cycle. Mutates ``ctx.workspace_state`` only —
    persistence remains the single ``Brain._end_think`` StateManager write.
    Returns True when progress fields were updated.
    """
    from datetime import datetime, timezone

    workspace = ctx.workspace_state
    if workspace is None or ctx.skip_llm:
        return False

    mission = ctx.mission or {}
    has_active = bool(
        workspace.active_mission_id
        or workspace.active_mission_title
        or workspace.active_mission
        or mission.get("active")
    )
    if not has_active:
        return False

    response = (ctx.response or "").strip()
    if not response:
        return False

    completed = list(mission.get("completed_steps") or [])
    if mission.get("active"):
        stage = mission.get("current_step") or workspace.active_mission_stage
        progress_raw = mission.get("progress", mission.get("progress_percent"))
        progress = (
            float(progress_raw)
            if progress_raw is not None
            else workspace.active_mission_progress
        )
        last_completed = (
            completed[-1]
            if completed
            else workspace.active_mission_last_completed_step
        )
        objective = (
            mission.get("current_step")
            or mission.get("next_step")
            or mission.get("objective")
            or workspace.active_mission_current_objective
        )
        if mission.get("title"):
            workspace.active_mission = mission.get("title")
            workspace.active_mission_title = mission.get("title")
        if mission.get("id"):
            workspace.active_mission_id = mission.get("id")
        status = mission.get("status") or mission.get("state")
        if status is not None:
            workspace.active_mission_status = str(
                getattr(status, "value", status)
            )
    else:
        stage = workspace.active_mission_stage
        progress = workspace.active_mission_progress
        last_completed = workspace.active_mission_last_completed_step
        objective = (
            workspace.active_mission_current_objective
            or workspace.active_mission_stage
        )

    timestamp = datetime.now(timezone.utc).isoformat()
    summary = _summarize_mission_progress(response)

    workspace.active_mission_stage = stage
    workspace.active_mission_last_completed_step = last_completed
    workspace.active_mission_progress = progress
    workspace.active_mission_progress_updated_at = timestamp
    workspace.active_mission_last_summary = summary
    workspace.active_mission_current_objective = objective

    # Keep shared mission_context aligned with the updated resume slice.
    ctx.mission_context = MissionContext.from_workspace(workspace)

    logger.info(
        "MISSION_PROGRESS_UPDATED stage=%s progress=%s last_completed=%s "
        "objective=%s updated_at=%s",
        stage,
        progress,
        last_completed,
        objective,
        timestamp,
    )
    return True


def apply_project_progress_update(ctx: ThinkContext) -> bool:
    """Write project resume fields onto request-scoped WorkspaceState (Phase 15.2).

    Called after a successful think cycle (after mission progress update). Mutates
    ``ctx.workspace_state`` only — persistence remains the single
    ``Brain._end_think`` StateManager write. Returns True when progress fields
    were updated.
    """
    from datetime import datetime, timezone

    workspace = ctx.workspace_state
    if workspace is None or ctx.skip_llm:
        return False

    has_active = bool(
        workspace.active_project_id
        or (
            workspace.active_project
            and workspace.active_project_status is not None
        )
    )
    if not has_active:
        return False

    response = (ctx.response or "").strip()
    if not response:
        return False

    # Prefer mission-slice continuity already stamped this turn; fall back to
    # existing project resume fields.
    active_mission = (
        workspace.active_mission_title
        or workspace.active_mission
        or workspace.active_project_active_mission
    )
    last_completed = (
        workspace.active_mission_last_completed_step
        or workspace.active_project_last_completed_step
    )
    objective = (
        workspace.active_mission_current_objective
        or workspace.active_mission_stage
        or workspace.active_project_current_objective
    )
    progress = workspace.active_project_progress
    # Keep project progress aligned with active mission progress when present.
    if workspace.active_mission_progress is not None:
        progress = float(workspace.active_mission_progress)

    timestamp = datetime.now(timezone.utc).isoformat()
    summary = _summarize_mission_progress(response)

    workspace.active_project_progress = progress
    workspace.active_project_active_mission = active_mission
    workspace.active_project_last_completed_step = last_completed
    workspace.active_project_current_objective = objective
    workspace.active_project_last_summary = summary
    workspace.active_project_progress_updated_at = timestamp
    # updated_at is stamped by StateManager.update on the single end-of-think write.

    ctx.project_context = ProjectContext.from_workspace(workspace)

    logger.info(
        "PROJECT_PROGRESS_UPDATED project=%s progress=%s active_mission=%s "
        "last_completed=%s objective=%s updated_at=%s",
        workspace.active_project,
        progress,
        active_mission,
        last_completed,
        objective,
        timestamp,
    )
    return True


def apply_goal_progress_update(ctx: ThinkContext) -> bool:
    """Write goal resume fields onto request-scoped WorkspaceState (Phase 16.2).

    Called after a successful think cycle (after project progress update). Mutates
    ``ctx.workspace_state`` only — persistence remains the single
    ``Brain._end_think`` StateManager write. Returns True when progress fields
    were updated.
    """
    from datetime import datetime, timezone

    workspace = ctx.workspace_state
    if workspace is None or ctx.skip_llm:
        return False

    has_active = bool(
        workspace.active_goal_id
        or (
            workspace.active_goal
            and workspace.active_goal_status is not None
        )
    )
    if not has_active:
        return False

    response = (ctx.response or "").strip()
    if not response:
        return False

    current_project = (
        workspace.active_goal_current_project
        or workspace.active_project
    )
    current_mission = (
        workspace.active_goal_current_mission
        or workspace.active_mission_title
        or workspace.active_mission
        or workspace.active_project_active_mission
    )
    progress = workspace.active_goal_progress
    # Keep goal progress aligned with active project progress when present.
    if workspace.active_project_progress is not None:
        # Prefer stored goal aggregate when total_projects > 1; otherwise mirror.
        total = int(getattr(workspace, "active_goal_total_projects", 0) or 0)
        if total <= 1:
            progress = float(workspace.active_project_progress)

    timestamp = datetime.now(timezone.utc).isoformat()
    summary = _summarize_mission_progress(response)

    workspace.active_goal_progress = progress
    workspace.active_goal_current_project = current_project
    workspace.active_goal_current_mission = current_mission
    workspace.active_goal_last_summary = summary
    workspace.active_goal_progress_updated_at = timestamp

    # Rebuild from WorkspaceState but keep Phase 16.3 match metadata.
    rebuilt = GoalContext.from_workspace(workspace)
    if rebuilt is not None and (
        ctx.goal_match_confidence is not None or ctx.goal_match_reason is not None
    ):
        rebuilt = replace(
            rebuilt,
            match_confidence=ctx.goal_match_confidence,
            selection_reason=ctx.goal_match_reason,
        )
    ctx.goal_context = rebuilt

    logger.info(
        "GOAL_PROGRESS_UPDATED goal=%s progress=%s project=%s mission=%s "
        "completed=%s total=%s updated_at=%s",
        workspace.active_goal,
        progress,
        current_project,
        current_mission,
        getattr(workspace, "active_goal_completed_projects", 0),
        getattr(workspace, "active_goal_total_projects", 0),
        timestamp,
    )
    return True


def refresh_mission_context_from_state(
    ctx: ThinkContext,
    state_manager: Any,
) -> MissionContext | None:
    """Copy mirrored mission fields from StateManager into request WorkspaceState.

    Used after MissionManager lifecycle mutations so awareness stays current
    without an extra disk load — ``snapshot()`` is in-memory only.
    """
    if ctx.workspace_state is None or state_manager is None:
        return inject_mission_context(ctx)
    snap = state_manager.snapshot()
    for name in _MISSION_MIRROR_FIELDS:
        setattr(ctx.workspace_state, name, getattr(snap, name, None))
    return inject_mission_context(ctx)


def refresh_project_context_from_state(
    ctx: ThinkContext,
    state_manager: Any,
) -> ProjectContext | None:
    """Copy mirrored project fields from StateManager into request WorkspaceState."""
    if ctx.workspace_state is None or state_manager is None:
        return inject_project_context(ctx)
    snap = state_manager.snapshot()
    for name in _PROJECT_MIRROR_FIELDS:
        setattr(ctx.workspace_state, name, getattr(snap, name, None))
    return inject_project_context(ctx)


def refresh_goal_context_from_state(
    ctx: ThinkContext,
    state_manager: Any,
) -> GoalContext | None:
    """Copy mirrored goal fields from StateManager into request WorkspaceState."""
    if ctx.workspace_state is None or state_manager is None:
        return inject_goal_context(ctx)
    snap = state_manager.snapshot()
    for name in _GOAL_MIRROR_FIELDS:
        setattr(ctx.workspace_state, name, getattr(snap, name, None))
    return inject_goal_context(ctx)


@dataclass
class ThinkContext:
    """Mutable context accumulated across the think() pipeline."""

    user_message: str
    current_user: str = "Nolan"
    context_snapshot: ContextSnapshot | None = None
    situational_context: str = ""
    retrieved_memory: str = ""
    retrieval_result: RetrievalResult | None = None
    conversation_loaded: bool = False
    # Phase 13.2 — request-scoped WorkspaceState shared by every pipeline stage.
    workspace_state: WorkspaceState | None = None
    # Phase 14.3 — WorkspaceState-derived mission awareness (shared, single source).
    mission_context: MissionContext | None = None
    # Phase 15.1 — WorkspaceState-derived project awareness (shared, single source).
    project_context: ProjectContext | None = None
    # Phase 16.1 — WorkspaceState-derived goal awareness (shared, single source).
    goal_context: GoalContext | None = None
    # Phase 16.3 — GoalMatcher outcome from the pre-load single scan.
    goal_match_confidence: float | None = None
    goal_match_reason: str | None = None
    state: dict = field(default_factory=dict)
    mission: dict = field(default_factory=dict)
    executive_analysis: str = ""
    structured_plan_text: str = ""
    # Phase 17.1 — next-action Plan from PlanningEngine (single plan per think).
    # Phase 17.2 — may be evolved mid-turn on mission complete / blocked triggers.
    execution_plan: Any | None = None
    # Phase 17.3 — DecisionEngine selection among plan next-actions (single pass).
    # Phase 17.4 — feedback learning updates confidence / history on the same object.
    execution_decision: Any | None = None
    decision_text: str = ""
    # Phase 18.1 — ExecutionEngine task/result from the selected Decision (single pass).
    execution_task: Any | None = None
    execution_result: Any | None = None
    execution_text: str = ""
    agent_results: list[AgentResult] = field(default_factory=list)
    agent_results_text: str = ""
    conversation_window: list[str] = field(default_factory=list)
    conversation_summary: str = ""
    pinned_facts_text: str = ""
    reference_resolution: str = ""
    knowledge_hits: str | None = None
    tool_results: list[ToolResult] = field(default_factory=list)
    tool_results_text: str = ""
    tool_status_text: str = ""
    session_id: str = ""
    turn_id: str = ""
    tool_confirmed: bool = False
    confirmation_token: str | None = None
    confirmed_tool_requests: list[ToolRequest] = field(default_factory=list)
    decision_report: ToolDecisionReport | None = None
    initiative_text: str = ""
    learning_text: str = ""
    active_project: str = ""
    skip_llm: bool = False
    skip_agents: bool = False
    prompt: str = ""
    response: str = ""
    obsidian_consulted: bool = False
    obsidian_note_titles: list[str] = field(default_factory=list)
    browser_exploring: bool = False
    browser_source_labels: list[str] = field(default_factory=list)
    cognitive_execution: object | None = None
    cognitive_neural_state: str = ""
    orchestrator_progress: list[dict] = field(default_factory=list)
