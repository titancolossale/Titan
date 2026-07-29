# =====================================
# Titan State Manager
# =====================================

"""Live working-state ownership for Titan (Phase 13.1).

This module owns Titan's in-process operational state — not long-term memory
and not conversation history persistence. ``StateManager`` is the only
authorized mutator of ``WorkspaceState``.

Note: ``core.state_manager.WorkspaceState`` is distinct from
``brain.world_model.WorkspaceState`` (filesystem/workspace awareness slice).
"""

from __future__ import annotations

import copy
import json
import threading
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from config.settings import TITAN_STATE_PATH

SCHEMA_VERSION = 1

_WORKSPACE_FIELD_NAMES = frozenset(
    {
        "active_project",
        # Phase 15.1 — project registry mirror (ProjectManager is the owner)
        "active_project_id",
        "active_project_status",
        "active_project_progress",
        "projects",
        # Phase 15.2 — project progress / resume continuity
        "active_project_active_mission",
        "active_project_completed_missions",
        "active_project_last_completed_step",
        "active_project_last_summary",
        "active_project_progress_updated_at",
        "active_project_current_objective",
        # Phase 16.1 — goal registry mirror (GoalManager is the owner)
        "active_goal_id",
        "active_goal",
        "active_goal_status",
        "active_goal_progress",
        "goals",
        # Phase 16.2 — goal progress / resume continuity
        "active_goal_completed_projects",
        "active_goal_active_projects",
        "active_goal_paused_projects",
        "active_goal_total_projects",
        "active_goal_last_activity",
        "active_goal_current_project",
        "active_goal_current_mission",
        "active_goal_last_summary",
        "active_goal_progress_updated_at",
        "active_mission",
        "active_mission_id",
        "active_mission_title",
        "active_mission_status",
        "active_mission_progress",
        "active_mission_priority",
        "active_mission_stage",
        # Phase 14.4 — mission progress / resume slice
        "active_mission_last_completed_step",
        "active_mission_last_summary",
        "active_mission_progress_updated_at",
        "active_mission_current_objective",
        # Phase 14.5 — multi-mission workspace mirror
        "missions",
        "mission_queue_count",
        "paused_mission_count",
        "current_step",
        "current_goal",
        "next_action",
        "current_focus",
        "running_tasks",
        "active_tools",
        "important_decisions",
        "brain_mode",
        "progress",
        "conversation_state",
        # Phase 18.2 — execution safety mirror (no secrets / tool payloads)
        "current_execution_risk",
        "confirmation_pending",
        "confirmation_id",
        "blocked_reason",
        # Phase 18.3 — tool execution bridge mirror (no raw payloads)
        "last_tool",
        "last_execution",
        "execution_duration",
        "execution_status",
        "last_error",
        # Phase 18.4 — execution recovery mirror
        "current_retry",
        "retry_count",
        "rollback_available",
        "execution_recovered",
        "last_failure_reason",
        # Phase 20.2 — voice enrollment mirror (no embeddings / raw audio)
        "voice_enrollment_status",
        "voice_enrollment_user",
        "voice_samples_collected",
        "voice_samples_required",
        "voice_quality_status",
        "voice_verification_status",
        # Phase 20.3 — live voice session mirror (safe fields only)
        "voice_session_state",
        "voice_input_level",
        "voice_speech_detected",
        "voice_current_speaker",
        "voice_identity_confidence_band",
        "voice_transcription_status",
        "voice_brain_status",
        "voice_tts_status",
        "voice_interrupted",
        "updated_at",
    }
)

_LIST_FIELDS = frozenset(
    {
        "running_tasks",
        "active_tools",
        "important_decisions",
        "missions",
        "projects",
        "goals",
        "active_project_completed_missions",
    }
)
_DICT_FIELDS = frozenset({"conversation_state"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_conversation_state() -> dict[str, Any]:
    return {
        "last_user_message": None,
        "last_titan_response": None,
    }


@dataclass
class WorkspaceState:
    """Titan's live working state while the process is running.

    Owned exclusively by ``StateManager``. Callers must never mutate an
    instance returned by ``snapshot()`` or dicts returned by ``get_state()``
    expecting those mutations to affect Titan — use ``update()`` / ``merge()``.
    """

    active_project: str | None = "Titan"
    # Phase 15.1 — mirrored active-project slice (ProjectManager is the owner).
    active_project_id: str | None = None
    active_project_status: str | None = None
    active_project_progress: float | None = None
    projects: list[Any] = field(default_factory=list)
    # Phase 15.2 — progress / resume continuity across think cycles.
    active_project_active_mission: str | None = None
    active_project_completed_missions: list[Any] = field(default_factory=list)
    active_project_last_completed_step: str | None = None
    active_project_last_summary: str | None = None
    active_project_progress_updated_at: str | None = None
    active_project_current_objective: str | None = None
    # Phase 16.1 — mirrored active-goal slice (GoalManager is the owner).
    active_goal_id: str | None = None
    active_goal: str | None = None
    active_goal_status: str | None = None
    active_goal_progress: float | None = None
    goals: list[Any] = field(default_factory=list)
    # Phase 16.2 — goal progress / resume continuity across think cycles.
    active_goal_completed_projects: int = 0
    active_goal_active_projects: int = 0
    active_goal_paused_projects: int = 0
    active_goal_total_projects: int = 0
    active_goal_last_activity: str | None = None
    active_goal_current_project: str | None = None
    active_goal_current_mission: str | None = None
    active_goal_last_summary: str | None = None
    active_goal_progress_updated_at: str | None = None
    active_mission: str | None = None
    # Phase 14.2 — mirrored active-mission slice (MissionManager is the owner).
    active_mission_id: str | None = None
    active_mission_title: str | None = None
    active_mission_status: str | None = None
    active_mission_progress: float | None = None
    # Phase 14.3 — priority + stage mirrored for Brain mission awareness.
    active_mission_priority: str | None = None
    active_mission_stage: str | None = None
    # Phase 14.4 — progress / resume continuity across think cycles.
    active_mission_last_completed_step: str | None = None
    active_mission_last_summary: str | None = None
    active_mission_progress_updated_at: str | None = None
    active_mission_current_objective: str | None = None
    # Phase 14.5 — concise multi-mission workspace mirror (MissionManager owns truth).
    missions: list[Any] = field(default_factory=list)
    mission_queue_count: int = 0
    paused_mission_count: int = 0
    current_step: str | None = "Développement du State Manager"
    current_goal: str | None = None
    next_action: str | None = "Connecter le State Manager au Brain"
    current_focus: str | None = None
    running_tasks: list[Any] = field(default_factory=list)
    active_tools: list[Any] = field(default_factory=list)
    important_decisions: list[Any] = field(default_factory=list)
    brain_mode: str | None = "idle"
    progress: str | None = "En développement"
    conversation_state: dict[str, Any] = field(
        default_factory=_default_conversation_state
    )
    # Phase 18.2 — concise execution safety (never secrets / tool payloads).
    current_execution_risk: str | None = None
    confirmation_pending: bool = False
    confirmation_id: str | None = None
    blocked_reason: str | None = None
    # Phase 18.3 — tool execution bridge (public summaries only).
    last_tool: str | None = None
    last_execution: str | None = None
    execution_duration: float | None = None
    execution_status: str | None = None
    last_error: str | None = None
    # Phase 18.4 — execution recovery (lightweight public fields).
    current_retry: int = 0
    retry_count: int = 0
    rollback_available: bool = False
    execution_recovered: bool = False
    last_failure_reason: str | None = None
    # Phase 20.2 — voice enrollment progress (safe public fields only).
    voice_enrollment_status: str | None = None
    voice_enrollment_user: str | None = None
    voice_samples_collected: int = 0
    voice_samples_required: int = 0
    voice_quality_status: str | None = None
    voice_verification_status: str | None = None
    # Phase 20.3 — live voice session (no raw audio / embeddings / secrets).
    voice_session_state: str | None = None
    voice_input_level: float = 0.0
    voice_speech_detected: bool = False
    voice_current_speaker: str | None = None
    voice_identity_confidence_band: str | None = None
    voice_transcription_status: str | None = None
    voice_brain_status: str | None = None
    voice_tts_status: str | None = None
    voice_interrupted: bool = False
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain JSON-compatible dict (deep copy of containers)."""
        payload = asdict(self)
        payload["schema_version"] = SCHEMA_VERSION
        payload["running_tasks"] = copy.deepcopy(self.running_tasks)
        payload["active_tools"] = copy.deepcopy(self.active_tools)
        payload["important_decisions"] = copy.deepcopy(self.important_decisions)
        payload["missions"] = copy.deepcopy(self.missions)
        payload["projects"] = copy.deepcopy(self.projects)
        payload["goals"] = copy.deepcopy(self.goals)
        payload["active_project_completed_missions"] = copy.deepcopy(
            self.active_project_completed_missions
        )
        payload["conversation_state"] = copy.deepcopy(self.conversation_state)
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> WorkspaceState:
        """Build state from a mapping; unknown keys ignored; missing keys defaulted."""
        if not data:
            return cls()

        raw = dict(data)
        conversation = _default_conversation_state()
        incoming_conversation = raw.get("conversation_state")
        if isinstance(incoming_conversation, Mapping):
            conversation.update(copy.deepcopy(dict(incoming_conversation)))

        # Migrate legacy flat last-message keys into conversation_state.
        if "last_user_message" in raw and "last_user_message" not in (
            incoming_conversation or {}
        ):
            conversation["last_user_message"] = raw.get("last_user_message")
        if "last_titan_response" in raw and "last_titan_response" not in (
            incoming_conversation or {}
        ):
            conversation["last_titan_response"] = raw.get("last_titan_response")

        kwargs: dict[str, Any] = {}
        for item in fields(cls):
            name = item.name
            if name == "conversation_state":
                kwargs[name] = conversation
                continue
            if name not in raw:
                continue
            value = raw[name]
            if name in _LIST_FIELDS:
                kwargs[name] = list(value) if isinstance(value, list) else []
            elif name in _DICT_FIELDS:
                kwargs[name] = (
                    copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}
                )
            else:
                kwargs[name] = value
        return cls(**kwargs)

    def copy(self) -> WorkspaceState:
        """Return a deep copy safe for external inspection."""
        return WorkspaceState.from_dict(self.to_dict())


def default_schema() -> dict[str, Any]:
    """Return the default persisted WorkspaceState document."""
    return WorkspaceState().to_dict()


def _non_default_fields(state: WorkspaceState) -> dict[str, Any]:
    """Return only fields that differ from WorkspaceState defaults."""
    defaults = WorkspaceState()
    payload: dict[str, Any] = {}
    for item in fields(WorkspaceState):
        name = item.name
        if name == "updated_at":
            continue
        current = getattr(state, name)
        default = getattr(defaults, name)
        if current != default:
            if name in _LIST_FIELDS:
                payload[name] = list(current)
            elif name in _DICT_FIELDS:
                payload[name] = copy.deepcopy(dict(current))
            else:
                payload[name] = current
    return payload


class StateManager:
    """Thread-safe single owner of Titan's live ``WorkspaceState``.

    Persistence reuses Titan's JSON manager pattern under ``data/``
    (``TITAN_STATE_PATH``). No separate database is introduced.
    """

    def __init__(self, file_path: str | Path | None = None) -> None:
        self.file_path = Path(file_path) if file_path is not None else Path(TITAN_STATE_PATH)
        self._lock = threading.RLock()
        self._workspace: WorkspaceState = WorkspaceState()
        self.load()

    # ------------------------------------------------------------------
    # Required API
    # ------------------------------------------------------------------

    def load(self) -> WorkspaceState:
        """Load WorkspaceState from disk (or defaults when the file is missing).

        Missing files do not create a write. Returns a deep-copied snapshot.
        """
        with self._lock:
            if not self.file_path.exists():
                self._workspace = WorkspaceState()
                return self._workspace.copy()

            with self.file_path.open("r", encoding="utf-8") as file:
                raw = json.load(file)

            if not isinstance(raw, dict):
                self._workspace = WorkspaceState()
                return self._workspace.copy()

            self._workspace = WorkspaceState.from_dict(raw)
            return self._workspace.copy()

    def save(self) -> None:
        """Persist the current WorkspaceState to JSON."""
        with self._lock:
            if self._workspace.updated_at is None:
                self._workspace.updated_at = _utc_now_iso()
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("w", encoding="utf-8") as file:
                json.dump(self._workspace.to_dict(), file, indent=4, ensure_ascii=False)

    def reset(self) -> WorkspaceState:
        """Replace live state with defaults, stamp ``updated_at``, and persist."""
        with self._lock:
            self._workspace = WorkspaceState(updated_at=_utc_now_iso())
            self.save()
            return self._workspace.copy()

    def snapshot(self) -> WorkspaceState:
        """Return a deep copy of the current WorkspaceState."""
        with self._lock:
            return self._workspace.copy()

    def update(self, updates: Mapping[str, Any] | None = None, **kwargs: Any) -> WorkspaceState:
        """Replace provided WorkspaceState fields, stamp ``updated_at``, and persist.

        Unknown keys are ignored. Nested ``conversation_state`` values replace
        keys when a mapping is provided (shallow key update).
        """
        with self._lock:
            patch = {**(updates or {}), **kwargs}
            self._apply_update(patch, merge_conversation=True)
            self._workspace.updated_at = _utc_now_iso()
            self.save()
            return self._workspace.copy()

    def merge(self, patch: Mapping[str, Any] | WorkspaceState) -> WorkspaceState:
        """Deep-merge a patch into live state, stamp ``updated_at``, and persist.

        Scalar fields overwrite when present. List fields replace when present.
        ``conversation_state`` is shallow-merged key-by-key.

        When ``patch`` is a ``WorkspaceState``, only non-default field values are
        applied so callers can pass partially populated instances safely.
        """
        with self._lock:
            if isinstance(patch, WorkspaceState):
                data = _non_default_fields(patch)
            else:
                data = dict(patch)
            data.pop("schema_version", None)
            data.pop("updated_at", None)
            self._apply_update(data, merge_conversation=True)
            self._workspace.updated_at = _utc_now_iso()
            self.save()
            return self._workspace.copy()

    # ------------------------------------------------------------------
    # Backward-compatible API (Brain / existing callers)
    # ------------------------------------------------------------------

    def load_state(self) -> dict[str, Any]:
        """Legacy alias: load and return a dict snapshot with flat last-message keys."""
        self.load()
        return self.get_state()

    def save_state(self) -> None:
        """Legacy alias for ``save()``."""
        self.save()

    def get_state(self) -> dict[str, Any]:
        """Return a deep-copied dict view for prompt/pipeline consumers.

        Flattens ``conversation_state`` last-message keys for Brain compatibility.
        Mutations on the returned dict do not affect live state.
        """
        with self._lock:
            return self._dict_view(self._workspace)

    def update_state(self, key: str, value: Any) -> None:
        """Legacy single-key update via ``update()``."""
        self.update({key: value})

    def update_after_response(self, user_message: str, titan_response: str) -> None:
        """Record the latest turn messages into conversation live state."""
        self.merge(
            {
                "conversation_state": {
                    "last_user_message": user_message,
                    "last_titan_response": titan_response,
                }
            }
        )

    def show_state(self) -> str:
        """Pretty-print the current state dict (debug/inspection)."""
        return json.dumps(self.get_state(), indent=4, ensure_ascii=False)

    @property
    def state(self) -> dict[str, Any]:
        """Legacy read-only dict view (deep copy). Prefer ``get_state()`` / ``snapshot()``."""
        return self.get_state()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _apply_update(
        self,
        patch: Mapping[str, Any],
        *,
        merge_conversation: bool,
    ) -> None:
        for key, value in patch.items():
            if key == "schema_version" or key not in _WORKSPACE_FIELD_NAMES:
                # Accept legacy flat last-message writes via update_state.
                if key in {"last_user_message", "last_titan_response"}:
                    self._workspace.conversation_state[key] = value
                continue

            if key == "conversation_state":
                if not isinstance(value, Mapping):
                    continue
                if merge_conversation:
                    self._workspace.conversation_state.update(
                        copy.deepcopy(dict(value))
                    )
                else:
                    self._workspace.conversation_state = copy.deepcopy(dict(value))
                continue

            if key in _LIST_FIELDS:
                setattr(
                    self._workspace,
                    key,
                    list(value) if isinstance(value, list) else [],
                )
                continue

            setattr(self._workspace, key, value)

    @staticmethod
    def _dict_view(workspace: WorkspaceState) -> dict[str, Any]:
        payload = workspace.to_dict()
        conversation = payload.get("conversation_state") or {}
        payload["last_user_message"] = conversation.get("last_user_message")
        payload["last_titan_response"] = conversation.get("last_titan_response")
        return payload
