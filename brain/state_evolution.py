# =====================================
# Titan State Evolution
# =====================================

"""Automatic WorkspaceState evolution during Brain.think() (Phase 13.3).

Infers operational field updates from pipeline context already produced in the
current turn — user message, mission, context snapshot — without a second Brain
pass or additional LLM call.

``StateManager`` remains the sole persistence owner; this module only proposes
and applies confident mutations onto the request-scoped ``WorkspaceState``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping

from brain.pipeline.context_bundle import ThinkContext
from core.state_manager import WorkspaceState

logger = logging.getLogger(__name__)

# Only apply inferred mutations at or above this confidence.
MIN_CONFIDENCE = 0.7

# Explicit / continuity signals may overwrite existing non-empty values.
HIGH_CONFIDENCE = 0.85

_CONTINUE_RE = re.compile(
    r"(?i)^\s*(?:continue|continuer|reprends?|reprendre|resume|resumer)"
    r"(?:\s+(?:avec|on|sur|le|la|l['’]|the|project|projet))?"
    r"\s+([A-Za-zÀ-ÿ][\wÀ-ÿ.\-]{0,63})\s*[.!]?\s*$"
)

_WORKING_RE = re.compile(
    r"(?i)^\s*(?:"
    r"we\s+are\s+(?P<en_verb>fixing|fixing|integrating|building|developing|"
    r"working\s+on|testing|planning)\s+(?:the\s+)?(?P<en_goal>.+?)"
    r"|"
    r"on\s+(?P<fr_verb>corrige|fixe|int[eè]gre|d[eé]veloppe|travaille\s+sur|"
    r"teste|planifie)\s+(?:le\s+|la\s+|les\s+|l['’])?(?P<fr_goal>.+?)"
    r"|"
    r"nous\s+(?P<fr_verb2>corrigeons|fixons|int[eé]grons|d[eé]veloppons|"
    r"testons|planifions)\s+(?:le\s+|la\s+|les\s+|l['’])?(?P<fr_goal2>.+?)"
    r")\s*[.!]?\s*$"
)

_FINISHED_RE = re.compile(
    r"(?i)^\s*(?:"
    r"we\s+finished(?:\s+this)?"
    r"|we(?:'re|\s+are)\s+done(?:\s+with\s+this)?"
    r"|on\s+a\s+termin[eé](?:\s+(?:ça|ca|ceci|cette\s+[ée]tape))?"
    r"|c['’]est\s+(?:fini|termin[eé])"
    r"|termin[eé](?:\s+(?:pour\s+)?(?:cette\s+[ée]tape|ça|ca))?"
    r"|done\s+with\s+this"
    r")\s*[.!]?\s*$"
)

_VERB_TO_STEP: dict[str, str] = {
    "fixing": "Integration",
    "fixing": "Integration",
    "integrating": "Integration",
    "corrige": "Integration",
    "fixe": "Integration",
    "intègre": "Integration",
    "integre": "Integration",
    "corrigeons": "Integration",
    "fixons": "Integration",
    "intégrons": "Integration",
    "integrons": "Integration",
    "building": "Development",
    "developing": "Development",
    "développe": "Development",
    "developpe": "Development",
    "développons": "Development",
    "developpons": "Development",
    "working on": "Development",
    "travaille sur": "Development",
    "testing": "Testing",
    "teste": "Testing",
    "testons": "Testing",
    "planning": "Planning",
    "planifie": "Planning",
    "planifions": "Planning",
}

_EVOLVABLE_FIELDS = frozenset(
    {
        "active_project",
        "active_mission",
        "current_step",
        "current_goal",
        "next_action",
        "current_focus",
        "progress",
        "brain_mode",
        "conversation_state",
    }
)


@dataclass(frozen=True)
class StateFieldUpdate:
    """One confident field mutation proposed for WorkspaceState."""

    field: str
    value: Any
    confidence: float
    reason: str


class StateEvolutionEngine:
    """Derive WorkspaceState updates from existing ThinkContext artifacts."""

    def apply(self, ctx: ThinkContext) -> list[StateFieldUpdate]:
        """Infer and apply confident updates onto ``ctx.workspace_state``.

        Returns the list of applied updates (empty when nothing changed).
        """
        workspace = ctx.workspace_state
        if workspace is None:
            logger.info("STATE_NO_CHANGE reason=no_workspace_state")
            return []

        proposals = self.propose(ctx)
        applied = self._apply_proposals(workspace, proposals)
        if not applied:
            logger.info("STATE_NO_CHANGE")
            return []

        field_names = ",".join(update.field for update in applied)
        logger.info("STATE_UPDATED fields=%s count=%d", field_names, len(applied))
        return applied

    def propose(self, ctx: ThinkContext) -> list[StateFieldUpdate]:
        """Build ordered field proposals from message + pipeline context."""
        proposals: list[StateFieldUpdate] = []
        message = (ctx.user_message or "").strip()
        if not message:
            return proposals

        proposals.extend(self._propose_from_message(message))
        proposals.extend(self._propose_from_mission(ctx.mission or {}))
        proposals.extend(self._propose_from_context_snapshot(ctx))
        return proposals

    def _propose_from_message(self, message: str) -> list[StateFieldUpdate]:
        proposals: list[StateFieldUpdate] = []

        continue_match = _CONTINUE_RE.match(message)
        if continue_match:
            project = self._clean_label(continue_match.group(1))
            if project:
                proposals.append(
                    StateFieldUpdate(
                        "active_project",
                        project,
                        0.92,
                        "continue_project",
                    )
                )
                proposals.append(
                    StateFieldUpdate(
                        "conversation_state",
                        {"status": "working"},
                        0.9,
                        "continue_project",
                    )
                )
                proposals.append(
                    StateFieldUpdate(
                        "brain_mode",
                        "working",
                        0.88,
                        "continue_project",
                    )
                )
            return proposals

        working_match = _WORKING_RE.match(message)
        if working_match:
            groups = working_match.groupdict()
            verb = (
                groups.get("en_verb")
                or groups.get("fr_verb")
                or groups.get("fr_verb2")
                or ""
            )
            goal_raw = (
                groups.get("en_goal")
                or groups.get("fr_goal")
                or groups.get("fr_goal2")
                or ""
            )
            goal = self._clean_label(goal_raw)
            step = _VERB_TO_STEP.get(verb.lower().strip())
            if goal:
                proposals.append(
                    StateFieldUpdate(
                        "current_goal",
                        goal,
                        0.9,
                        "working_on_goal",
                    )
                )
                proposals.append(
                    StateFieldUpdate(
                        "current_focus",
                        goal,
                        0.85,
                        "working_on_goal",
                    )
                )
                proposals.append(
                    StateFieldUpdate(
                        "conversation_state",
                        {"status": "working"},
                        0.88,
                        "working_on_goal",
                    )
                )
                proposals.append(
                    StateFieldUpdate(
                        "brain_mode",
                        "working",
                        0.85,
                        "working_on_goal",
                    )
                )
            if step:
                proposals.append(
                    StateFieldUpdate(
                        "current_step",
                        step,
                        0.88,
                        "working_on_goal",
                    )
                )
            return proposals

        if _FINISHED_RE.match(message):
            proposals.append(
                StateFieldUpdate(
                    "progress",
                    "Étape terminée",
                    0.92,
                    "finished_signal",
                )
            )
            proposals.append(
                StateFieldUpdate(
                    "next_action",
                    None,
                    0.92,
                    "finished_signal",
                )
            )
            proposals.append(
                StateFieldUpdate(
                    "conversation_state",
                    {"status": "idle"},
                    0.88,
                    "finished_signal",
                )
            )
            proposals.append(
                StateFieldUpdate(
                    "brain_mode",
                    "idle",
                    0.88,
                    "finished_signal",
                )
            )

        return proposals

    def _propose_from_mission(self, mission: Mapping[str, Any]) -> list[StateFieldUpdate]:
        """Fill empty mission-linked fields from an active mission (no overwrite)."""
        if not mission.get("active"):
            return []

        proposals: list[StateFieldUpdate] = []
        title = mission.get("title")
        if isinstance(title, str) and title.strip():
            proposals.append(
                StateFieldUpdate(
                    "active_mission",
                    title.strip(),
                    0.9,
                    "active_mission",
                )
            )
        step = mission.get("current_step")
        if isinstance(step, str) and step.strip():
            proposals.append(
                StateFieldUpdate(
                    "current_step",
                    step.strip(),
                    0.82,
                    "active_mission_step",
                )
            )
        objective = mission.get("objective")
        if isinstance(objective, str) and objective.strip():
            proposals.append(
                StateFieldUpdate(
                    "current_goal",
                    objective.strip(),
                    0.8,
                    "active_mission_objective",
                )
            )
        return proposals

    def _propose_from_context_snapshot(
        self,
        ctx: ThinkContext,
    ) -> list[StateFieldUpdate]:
        """Use situational snapshot only to fill empty project continuity."""
        snapshot = ctx.context_snapshot
        if snapshot is None:
            return []

        proposals: list[StateFieldUpdate] = []
        project = (snapshot.active_project or "").strip()
        # Snapshot defaults are not treated as high-confidence inferences.
        if project and project.lower() not in {"unknown", "n/a", "none"}:
            proposals.append(
                StateFieldUpdate(
                    "active_project",
                    project,
                    0.72,
                    "context_snapshot_project",
                )
            )
        return proposals

    def _apply_proposals(
        self,
        workspace: WorkspaceState,
        proposals: list[StateFieldUpdate],
    ) -> list[StateFieldUpdate]:
        """Apply proposals that clear the confidence / overwrite gates."""
        applied: list[StateFieldUpdate] = []
        # Later proposals for the same field lose to earlier higher-priority ones
        # unless they are strictly more confident.
        best_by_field: dict[str, StateFieldUpdate] = {}
        for proposal in proposals:
            if proposal.field not in _EVOLVABLE_FIELDS:
                continue
            if proposal.confidence < MIN_CONFIDENCE:
                continue
            existing = best_by_field.get(proposal.field)
            if existing is None or proposal.confidence > existing.confidence:
                best_by_field[proposal.field] = proposal

        for field_name, proposal in best_by_field.items():
            if not self._should_apply(workspace, proposal):
                continue
            old_value = self._read_field(workspace, field_name)
            self._write_field(workspace, field_name, proposal.value)
            new_value = self._read_field(workspace, field_name)
            if old_value == new_value:
                continue
            logger.info(
                "STATE_FIELD_CHANGED field=%s old=%r new=%r confidence=%.2f reason=%s",
                field_name,
                old_value,
                new_value,
                proposal.confidence,
                proposal.reason,
            )
            applied.append(proposal)
        return applied

    def _should_apply(
        self,
        workspace: WorkspaceState,
        proposal: StateFieldUpdate,
    ) -> bool:
        """Reject uncertain overwrites of already-valid state."""
        current = self._read_field(workspace, proposal.field)

        if proposal.field == "conversation_state":
            if not isinstance(proposal.value, Mapping):
                return False
            # Shallow merge: apply when any proposed key differs.
            current_map = current if isinstance(current, dict) else {}
            return any(
                current_map.get(key) != value for key, value in proposal.value.items()
            )

        if proposal.field == "next_action" and proposal.value is None:
            # Explicit clear on finish signals.
            return current is not None and str(current).strip() != ""

        if self._is_empty(current):
            return not self._is_empty(proposal.value)

        if current == proposal.value:
            return False

        # Existing non-empty values require high-confidence explicit signals.
        return proposal.confidence >= HIGH_CONFIDENCE

    @staticmethod
    def _is_empty(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        if isinstance(value, Mapping) and not value:
            return True
        return False

    @staticmethod
    def _read_field(workspace: WorkspaceState, field_name: str) -> Any:
        if field_name == "conversation_state":
            return dict(workspace.conversation_state)
        return getattr(workspace, field_name)

    @staticmethod
    def _write_field(workspace: WorkspaceState, field_name: str, value: Any) -> None:
        if field_name == "conversation_state":
            if isinstance(value, Mapping):
                workspace.conversation_state.update(dict(value))
            return
        setattr(workspace, field_name, value)

    @staticmethod
    def _clean_label(raw: str) -> str:
        text = (raw or "").strip().strip("\"'`")
        text = re.sub(r"[.!?]+$", "", text).strip()
        text = re.sub(r"\s+", " ", text)
        return text
