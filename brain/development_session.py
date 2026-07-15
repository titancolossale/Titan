# =====================================
# Titan Development Session Runtime
# =====================================

"""Development Session Runtime V1 — persistent coding-session context.

Tracks feature progress across a development session. Never executes tools,
never writes repository files, and never applies generated patches.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from brain.code_generation_engine import GeneratedPatch
    from brain.code_modification_planner import CodeModificationPlan
    from brain.developer_workflow import DeveloperWorkflowPlan
    from brain.executive_function import ExecutiveFunction
    from brain.workspace_awareness import WorkspaceAwareness, WorkspaceSnapshot
    from context.context_manager import ContextManager
    from core.mission_manager import MissionManager
    from memory.memory_service import MemoryService

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_SESSION_PATH = "data/development_sessions.json"


class SessionState(str, Enum):
    """Lifecycle state for a development session."""

    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


@dataclass(frozen=True)
class SessionDecision:
    """Recorded choice made during a development session."""

    decision_id: str
    statement: str
    rationale: str
    timestamp: str
    source: str = "user"  # user | brain | workflow | planner

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "statement": self.statement,
            "rationale": self.rationale,
            "timestamp": self.timestamp,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionDecision:
        return cls(
            decision_id=str(data["decision_id"]),
            statement=str(data.get("statement") or ""),
            rationale=str(data.get("rationale") or ""),
            timestamp=str(data.get("timestamp") or _utc_now()),
            source=str(data.get("source") or "user"),
        )


@dataclass(frozen=True)
class PendingTask:
    """Remaining work item tracked in a session."""

    task_id: str
    description: str
    created_at: str
    source: str = "manual"
    related_files: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "created_at": self.created_at,
            "source": self.source,
            "related_files": list(self.related_files),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PendingTask:
        return cls(
            task_id=str(data["task_id"]),
            description=str(data.get("description") or ""),
            created_at=str(data.get("created_at") or _utc_now()),
            source=str(data.get("source") or "manual"),
            related_files=tuple(data.get("related_files") or ()),
        )


@dataclass(frozen=True)
class CompletedTask:
    """Finished step tracked in a session."""

    task_id: str
    description: str
    completed_at: str
    source: str = "manual"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "completed_at": self.completed_at,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompletedTask:
        return cls(
            task_id=str(data["task_id"]),
            description=str(data.get("description") or ""),
            completed_at=str(data.get("completed_at") or _utc_now()),
            source=str(data.get("source") or "manual"),
        )


@dataclass(frozen=True)
class SessionSummary:
    """Concise snapshot for “summarize today’s work” style requests."""

    session_id: str
    feature: str
    state: SessionState
    opened_modules: tuple[str, ...]
    reviewed_files: tuple[str, ...]
    plans_count: int
    patches_count: int
    completed_count: int
    pending_count: int
    decisions_count: int
    rejected_ideas_count: int
    narrative: str
    remaining: tuple[str, ...]
    key_decisions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "feature": self.feature,
            "state": self.state.value,
            "opened_modules": list(self.opened_modules),
            "reviewed_files": list(self.reviewed_files),
            "plans_count": self.plans_count,
            "patches_count": self.patches_count,
            "completed_count": self.completed_count,
            "pending_count": self.pending_count,
            "decisions_count": self.decisions_count,
            "rejected_ideas_count": self.rejected_ideas_count,
            "narrative": self.narrative,
            "remaining": list(self.remaining),
            "key_decisions": list(self.key_decisions),
        }

    def format_for_prompt(self) -> str:
        lines = [
            "DEVELOPMENT SESSION SUMMARY",
            f"- feature: {self.feature}",
            f"- state: {self.state.value}",
            f"- narrative: {self.narrative}",
            f"- plans: {self.plans_count} | patches: {self.patches_count}",
            f"- completed: {self.completed_count} | pending: {self.pending_count}",
        ]
        if self.remaining:
            lines.append("- remaining:")
            for item in self.remaining[:8]:
                lines.append(f"  - {item}")
        if self.key_decisions:
            lines.append("- decisions:")
            for item in self.key_decisions[:5]:
                lines.append(f"  - {item}")
        return "\n".join(lines)


@dataclass
class DevelopmentSession:
    """Mutable session record — persistence-friendly, no side effects."""

    session_id: str
    feature: str
    state: SessionState
    created_at: str
    updated_at: str
    paused_at: str | None = None
    ended_at: str | None = None
    mission_id: str | None = None
    user: str | None = None
    project_id: str | None = None
    opened_modules: list[str] = field(default_factory=list)
    reviewed_files: list[str] = field(default_factory=list)
    plans: list[dict[str, Any]] = field(default_factory=list)
    patches: list[dict[str, Any]] = field(default_factory=list)
    completed_tasks: list[CompletedTask] = field(default_factory=list)
    pending_tasks: list[PendingTask] = field(default_factory=list)
    decisions: list[SessionDecision] = field(default_factory=list)
    rejected_ideas: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    application_records: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "feature": self.feature,
            "state": self.state.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "paused_at": self.paused_at,
            "ended_at": self.ended_at,
            "mission_id": self.mission_id,
            "user": self.user,
            "project_id": self.project_id,
            "opened_modules": list(self.opened_modules),
            "reviewed_files": list(self.reviewed_files),
            "plans": list(self.plans),
            "patches": list(self.patches),
            "completed_tasks": [t.to_dict() for t in self.completed_tasks],
            "pending_tasks": [t.to_dict() for t in self.pending_tasks],
            "decisions": [d.to_dict() for d in self.decisions],
            "rejected_ideas": list(self.rejected_ideas),
            "notes": list(self.notes),
            "application_records": list(self.application_records),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DevelopmentSession:
        return cls(
            session_id=str(data["session_id"]),
            feature=str(data.get("feature") or ""),
            state=SessionState(data.get("state", SessionState.ACTIVE.value)),
            created_at=str(data.get("created_at") or _utc_now()),
            updated_at=str(data.get("updated_at") or _utc_now()),
            paused_at=data.get("paused_at"),
            ended_at=data.get("ended_at"),
            mission_id=data.get("mission_id"),
            user=data.get("user"),
            project_id=data.get("project_id"),
            opened_modules=list(data.get("opened_modules") or []),
            reviewed_files=list(data.get("reviewed_files") or []),
            plans=list(data.get("plans") or []),
            patches=list(data.get("patches") or []),
            completed_tasks=[
                CompletedTask.from_dict(t)
                for t in (data.get("completed_tasks") or [])
                if isinstance(t, dict)
            ],
            pending_tasks=[
                PendingTask.from_dict(t)
                for t in (data.get("pending_tasks") or [])
                if isinstance(t, dict)
            ],
            decisions=[
                SessionDecision.from_dict(d)
                for d in (data.get("decisions") or [])
                if isinstance(d, dict)
            ],
            rejected_ideas=list(data.get("rejected_ideas") or []),
            notes=list(data.get("notes") or []),
            application_records=list(data.get("application_records") or []),
        )

    def format_for_prompt(self) -> str:
        """Compact session block for Brain prompt injection."""
        lines = [
            "DEVELOPMENT SESSION",
            f"- id: {self.session_id}",
            f"- feature: {self.feature}",
            f"- state: {self.state.value}",
            f"- opened modules: {len(self.opened_modules)}",
            f"- reviewed files: {len(self.reviewed_files)}",
            f"- plans: {len(self.plans)} | patches: {len(self.patches)}",
            f"- completed: {len(self.completed_tasks)} | pending: {len(self.pending_tasks)}",
            f"- decisions: {len(self.decisions)}",
        ]
        if self.pending_tasks:
            lines.append("- pending:")
            for task in self.pending_tasks[:8]:
                lines.append(f"  - {task.description}")
        return "\n".join(lines)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe_preserve(
    items: list[str],
    additions: list[str] | tuple[str, ...],
) -> list[str]:
    seen = set(items)
    out = list(items)
    for item in additions:
        cleaned = str(item).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


def _default_document() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "active_session_id": None,
        "sessions": {},
    }


class DevelopmentSessionRuntime:
    """Maintain coherent development-session context across turns.

    Persistence: data/development_sessions.json (manager-owned).
    Execution: none — plans/patches are stored as advisory artifacts only.
    """

    def __init__(
        self,
        *,
        file_path: str | Path = DEFAULT_SESSION_PATH,
        workspace_awareness: WorkspaceAwareness | None = None,
        executive_function: ExecutiveFunction | None = None,
        mission_manager: MissionManager | None = None,
        memory_service: MemoryService | None = None,
        context_manager: ContextManager | None = None,
    ) -> None:
        self.file_path = Path(file_path)
        self._workspace_awareness = workspace_awareness
        self._executive_function = executive_function
        self._mission_manager = mission_manager
        self._memory_service = memory_service
        self._context_manager = context_manager
        self._active_session_id: str | None = None
        self._sessions: dict[str, DevelopmentSession] = {}
        self._load()

    # --- lifecycle ---

    def start(
        self,
        feature: str,
        *,
        mission_id: str | None = None,
        user: str | None = None,
        project_id: str | None = None,
        pending: list[str] | None = None,
        open_modules: list[str] | None = None,
    ) -> DevelopmentSession:
        """Start a new active development session for *feature*."""
        if self._active_session_id:
            current = self._sessions.get(self._active_session_id)
            if current and current.state == SessionState.ACTIVE:
                raise ValueError(
                    f"Active session already exists: {current.session_id} "
                    f"({current.feature}). Pause or end it first."
                )

        now = _utc_now()
        user = user or (
            self._context_manager.current_user if self._context_manager else None
        )
        project_id = project_id or (
            self._context_manager.active_project if self._context_manager else None
        )
        if mission_id is None:
            mission_id = self._resolve_mission_id()

        session = DevelopmentSession(
            session_id=str(uuid.uuid4()),
            feature=feature.strip() or "untitled feature",
            state=SessionState.ACTIVE,
            created_at=now,
            updated_at=now,
            mission_id=mission_id,
            user=user,
            project_id=project_id,
            opened_modules=list(open_modules or []),
            pending_tasks=[
                PendingTask(
                    task_id=str(uuid.uuid4()),
                    description=item,
                    created_at=now,
                    source="start",
                )
                for item in (pending or [])
                if str(item).strip()
            ],
        )
        self._sessions[session.session_id] = session
        self._active_session_id = session.session_id
        self._sync_workspace_open_files(session)
        self._save()
        logger.info(
            "Development session started: %s feature=%s",
            session.session_id,
            session.feature,
        )
        return session

    def update(
        self,
        *,
        session_id: str | None = None,
        feature: str | None = None,
        opened_modules: list[str] | None = None,
        reviewed_files: list[str] | None = None,
        plan: DeveloperWorkflowPlan | CodeModificationPlan | dict[str, Any] | None = None,
        patch: GeneratedPatch | dict[str, Any] | None = None,
        complete_task: str | None = None,
        add_pending: list[str] | None = None,
        decision: str | None = None,
        decision_rationale: str = "",
        decision_source: str = "user",
        reject_idea: str | None = None,
        note: str | None = None,
        workspace: WorkspaceSnapshot | None = None,
        application_record: dict[str, Any] | None = None,
        mark_patch_applied: bool = False,
    ) -> DevelopmentSession:
        """Update an active session with progress artifacts (no execution)."""
        session = self._require_session(session_id, allow_paused=False)
        now = _utc_now()

        if feature:
            session.feature = feature.strip()
        if opened_modules:
            session.opened_modules = _dedupe_preserve(
                session.opened_modules,
                opened_modules,
            )
        if reviewed_files:
            session.reviewed_files = _dedupe_preserve(
                session.reviewed_files,
                reviewed_files,
            )
        if workspace is not None:
            modules = getattr(workspace, "detected_modules", ()) or ()
            session.opened_modules = _dedupe_preserve(
                session.opened_modules,
                modules,
            )
            open_files = getattr(workspace, "open_files", ()) or ()
            session.reviewed_files = _dedupe_preserve(
                session.reviewed_files,
                open_files,
            )

        if plan is not None:
            session.plans.append(self._plan_artifact(plan))
            for step in self._extract_next_steps(plan):
                session.pending_tasks.append(
                    PendingTask(
                        task_id=str(uuid.uuid4()),
                        description=step,
                        created_at=now,
                        source="plan",
                    )
                )

        if patch is not None:
            session.patches.append(self._patch_artifact(patch))

        if application_record is not None:
            record = dict(application_record)
            record["_recorded_at"] = now
            session.application_records.append(record)
            kind = str(record.get("kind") or "application")
            tx_id = record.get("transaction_id")
            session.notes.append(
                f"patch_{kind}:{tx_id or 'n/a'}:"
                f"{record.get('status') or record.get('valid') or record.get('success')}"
            )

        if mark_patch_applied and session.patches:
            session.patches[-1]["_applied"] = True
            if application_record and application_record.get("transaction_id"):
                session.patches[-1]["_transaction_id"] = application_record[
                    "transaction_id"
                ]

        if add_pending:
            for item in add_pending:
                cleaned = str(item).strip()
                if cleaned:
                    session.pending_tasks.append(
                        PendingTask(
                            task_id=str(uuid.uuid4()),
                            description=cleaned,
                            created_at=now,
                            source="update",
                        )
                    )

        if complete_task:
            self._complete_pending(session, complete_task, now)

        if decision:
            session.decisions.append(
                SessionDecision(
                    decision_id=str(uuid.uuid4()),
                    statement=decision.strip(),
                    rationale=decision_rationale.strip(),
                    timestamp=now,
                    source=decision_source.strip() or "user",
                )
            )

        if reject_idea:
            idea = reject_idea.strip()
            if idea and idea not in session.rejected_ideas:
                session.rejected_ideas.append(idea)

        if note:
            cleaned_note = note.strip()
            if cleaned_note:
                session.notes.append(cleaned_note)

        session.updated_at = now
        self._save()
        return session

    def pause(self, session_id: str | None = None) -> DevelopmentSession:
        """Pause an active session and clear the active pointer."""
        session = self._require_session(session_id, allow_paused=False)
        now = _utc_now()
        session.state = SessionState.PAUSED
        session.paused_at = now
        session.updated_at = now
        if self._active_session_id == session.session_id:
            self._active_session_id = None
        self._maybe_remember_summary(session)
        self._save()
        logger.info("Development session paused: %s", session.session_id)
        return session

    def resume(self, session_id: str | None = None) -> DevelopmentSession:
        """Resume by id, or the most recent paused session."""
        if session_id:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Unknown session: {session_id}")
        else:
            session = self._latest_resumable()
            if session is None:
                raise ValueError("No paused development session to resume.")

        if session.state == SessionState.ENDED:
            raise ValueError(f"Session {session.session_id} has ended.")
        if self._active_session_id and self._active_session_id != session.session_id:
            active = self._sessions[self._active_session_id]
            if active.state == SessionState.ACTIVE:
                raise ValueError(
                    f"Cannot resume while session {active.session_id} is active."
                )

        now = _utc_now()
        session.state = SessionState.ACTIVE
        session.paused_at = None
        session.updated_at = now
        self._active_session_id = session.session_id
        self._save()
        logger.info("Development session resumed: %s", session.session_id)
        return session

    def end(self, session_id: str | None = None) -> DevelopmentSession:
        """End an active or paused session."""
        session = self._require_session(session_id, allow_paused=True)
        now = _utc_now()
        session.state = SessionState.ENDED
        session.ended_at = now
        session.updated_at = now
        if self._active_session_id == session.session_id:
            self._active_session_id = None
        self._maybe_remember_summary(session)
        self._save()
        logger.info("Development session ended: %s", session.session_id)
        return session

    def get_active(self) -> DevelopmentSession | None:
        """Return the currently active session, if any."""
        if not self._active_session_id:
            return None
        session = self._sessions.get(self._active_session_id)
        if session is None or session.state != SessionState.ACTIVE:
            return None
        return session

    def get_session(self, session_id: str) -> DevelopmentSession | None:
        """Return a session by id regardless of state."""
        return self._sessions.get(session_id)

    def summarize(self, session_id: str | None = None) -> SessionSummary:
        """Build a concise summary of session progress."""
        session = self._require_session(
            session_id,
            allow_paused=True,
            allow_ended=True,
        )
        remaining = tuple(t.description for t in session.pending_tasks)
        key_decisions = tuple(d.statement for d in session.decisions[-5:])
        narrative = (
            f"Feature '{session.feature}' — {len(session.completed_tasks)} done, "
            f"{len(session.pending_tasks)} pending, "
            f"{len(session.plans)} plan(s), {len(session.patches)} patch proposal(s)."
        )
        return SessionSummary(
            session_id=session.session_id,
            feature=session.feature,
            state=session.state,
            opened_modules=tuple(session.opened_modules),
            reviewed_files=tuple(session.reviewed_files),
            plans_count=len(session.plans),
            patches_count=len(session.patches),
            completed_count=len(session.completed_tasks),
            pending_count=len(session.pending_tasks),
            decisions_count=len(session.decisions),
            rejected_ideas_count=len(session.rejected_ideas),
            narrative=narrative,
            remaining=remaining,
            key_decisions=key_decisions,
        )

    # --- helpers ---

    def _resolve_mission_id(self) -> str | None:
        if self._executive_function is not None:
            focus_mission = self._executive_function.get_current_focus()
            if focus_mission is not None:
                return focus_mission.id
        if self._mission_manager is not None:
            getter = getattr(self._mission_manager, "get_active_mission", None)
            if callable(getter):
                active = getter()
                if active is not None:
                    return getattr(active, "id", None) or (
                        active.get("id") if isinstance(active, dict) else None
                    )
            runtime = getattr(self._mission_manager, "runtime", None)
            if runtime is not None:
                active = runtime.get_active_mission()
                if active is not None:
                    return active.id
        return None

    def _require_session(
        self,
        session_id: str | None,
        *,
        allow_paused: bool,
        allow_ended: bool = False,
    ) -> DevelopmentSession:
        if session_id:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Unknown session: {session_id}")
        else:
            if self._active_session_id:
                session = self._sessions.get(self._active_session_id)
            else:
                session = None
            if session is None and allow_paused:
                session = self._latest_resumable()
            if session is None and allow_ended:
                session = self._latest_any()
            if session is None:
                raise ValueError("No development session available.")

        if session.state == SessionState.ENDED and not allow_ended:
            raise ValueError(f"Session {session.session_id} has ended.")
        if session.state == SessionState.PAUSED and not allow_paused:
            raise ValueError(
                f"Session {session.session_id} is paused. Resume it before updating."
            )
        if session.state == SessionState.ACTIVE or allow_paused or allow_ended:
            return session
        raise ValueError(f"Session {session.session_id} is not usable.")

    def _latest_resumable(self) -> DevelopmentSession | None:
        paused = [
            s for s in self._sessions.values() if s.state == SessionState.PAUSED
        ]
        if not paused:
            return None
        return max(
            paused,
            key=lambda s: s.updated_at or s.paused_at or s.created_at,
        )

    def _latest_any(self) -> DevelopmentSession | None:
        if not self._sessions:
            return None
        return max(
            self._sessions.values(),
            key=lambda s: s.updated_at or s.created_at,
        )

    def _complete_pending(
        self,
        session: DevelopmentSession,
        complete_task: str,
        now: str,
    ) -> None:
        needle = complete_task.strip().lower()
        if not needle:
            return
        match_idx: int | None = None
        for idx, task in enumerate(session.pending_tasks):
            if task.task_id == complete_task.strip() or needle in task.description.lower():
                match_idx = idx
                break
        if match_idx is None:
            session.completed_tasks.append(
                CompletedTask(
                    task_id=str(uuid.uuid4()),
                    description=complete_task.strip(),
                    completed_at=now,
                    source="update",
                )
            )
            return
        task = session.pending_tasks.pop(match_idx)
        session.completed_tasks.append(
            CompletedTask(
                task_id=task.task_id,
                description=task.description,
                completed_at=now,
                source=task.source,
            )
        )

    def _plan_artifact(
        self,
        plan: DeveloperWorkflowPlan | CodeModificationPlan | dict[str, Any],
    ) -> dict[str, Any]:
        if isinstance(plan, dict):
            artifact = dict(plan)
        elif hasattr(plan, "to_dict"):
            artifact = plan.to_dict()
        else:
            artifact = {"repr": repr(plan)}
        artifact["_recorded_at"] = _utc_now()
        artifact["_artifact_type"] = type(plan).__name__
        return artifact

    def _patch_artifact(
        self,
        patch: GeneratedPatch | dict[str, Any],
    ) -> dict[str, Any]:
        if isinstance(patch, dict):
            artifact = dict(patch)
        elif hasattr(patch, "to_dict"):
            artifact = patch.to_dict()
        else:
            artifact = {"repr": repr(patch)}
        # Store proposal metadata only — never apply diffs to disk.
        artifact["_recorded_at"] = _utc_now()
        artifact["_artifact_type"] = type(patch).__name__
        artifact["_applied"] = False
        return artifact

    def _extract_next_steps(
        self,
        plan: DeveloperWorkflowPlan | CodeModificationPlan | dict[str, Any],
    ) -> list[str]:
        steps: list[str] = []
        if isinstance(plan, dict):
            raw = plan.get("next_steps") or []
            if isinstance(raw, (list, tuple)):
                steps.extend(str(s).strip() for s in raw if str(s).strip())
            impl = plan.get("implementation_steps") or []
            if isinstance(impl, (list, tuple)):
                for item in impl:
                    if isinstance(item, dict):
                        desc = item.get("description") or item.get("title") or ""
                        if str(desc).strip():
                            steps.append(str(desc).strip())
                    elif str(item).strip():
                        steps.append(str(item).strip())
            checklist = plan.get("checklist") or []
            if isinstance(checklist, (list, tuple)):
                steps.extend(str(s).strip() for s in checklist if str(s).strip())
            return steps[:12]

        next_steps = getattr(plan, "next_steps", None)
        if next_steps:
            steps.extend(str(s).strip() for s in next_steps if str(s).strip())

        implementation_steps = getattr(plan, "implementation_steps", None)
        if implementation_steps:
            for item in implementation_steps:
                desc = getattr(item, "description", None) or getattr(item, "title", None)
                if desc and str(desc).strip():
                    steps.append(str(desc).strip())

        checklist = getattr(plan, "checklist", None)
        if checklist:
            steps.extend(str(s).strip() for s in checklist if str(s).strip())

        return steps[:12]

    def _sync_workspace_open_files(self, session: DevelopmentSession) -> None:
        """Advisory workspace refresh from session open hints — no file writes."""
        if self._workspace_awareness is None:
            return
        hints = list(session.reviewed_files) or list(session.opened_modules)
        if not hints:
            return
        try:
            self._workspace_awareness.refresh(
                open_files=hints[:30],
                user=session.user,
                project_id=session.project_id,
            )
        except Exception:
            logger.debug("Workspace sync skipped for session %s", session.session_id)

    def _maybe_remember_summary(self, session: DevelopmentSession) -> None:
        """Optional short-term memory note — never invents facts."""
        if self._memory_service is None:
            return
        try:
            summary = self.summarize(session.session_id)
            self._memory_service.remember_session(
                f"[dev-session:{session.session_id[:8]}] {summary.narrative}"
            )
        except Exception:
            logger.debug(
                "Session memory note skipped for %s",
                session.session_id,
                exc_info=True,
            )

    def _load(self) -> None:
        if not self.file_path.exists():
            self._active_session_id = None
            self._sessions = {}
            return
        try:
            with self.file_path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to load development sessions from %s: %s", self.file_path, exc)
            self._active_session_id = None
            self._sessions = {}
            return

        if not isinstance(raw, dict):
            self._active_session_id = None
            self._sessions = {}
            return

        sessions_raw = raw.get("sessions") or {}
        loaded: dict[str, DevelopmentSession] = {}
        if isinstance(sessions_raw, dict):
            for key, value in sessions_raw.items():
                if not isinstance(value, dict):
                    continue
                try:
                    session = DevelopmentSession.from_dict(value)
                    loaded[session.session_id] = session
                except (KeyError, TypeError, ValueError) as exc:
                    logger.warning("Skipping corrupt session %s: %s", key, exc)

        self._sessions = loaded
        active_id = raw.get("active_session_id")
        if active_id and active_id in self._sessions:
            active = self._sessions[active_id]
            self._active_session_id = (
                active_id if active.state == SessionState.ACTIVE else None
            )
        else:
            self._active_session_id = None

    def _save(self) -> None:
        document = _default_document()
        document["active_session_id"] = self._active_session_id
        document["sessions"] = {
            session_id: session.to_dict()
            for session_id, session in self._sessions.items()
        }
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with self.file_path.open("w", encoding="utf-8") as file:
            json.dump(document, file, indent=4, ensure_ascii=False)
