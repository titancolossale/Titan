# =====================================
# Titan Decision Models
# =====================================

"""Decision types for next-action selection (Phase 17.3–17.4).

The Decision Engine answers: among all available plan actions, which one
should be executed next? Reuses PlanningEngine ``Plan.next_actions`` —
does not recreate Goal / Project / Mission ownership.

Phase 17.4 — decision feedback / learning: every completed action yields a
``DecisionFeedback`` that updates rolling history and future confidence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ActionCandidateScore:
    """Per-candidate scores from a single evaluation pass."""

    action: str
    priority: float
    urgency: float
    risk: float
    dependency: float
    estimated_value: float
    overall_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "priority": self.priority,
            "urgency": self.urgency,
            "risk": self.risk,
            "dependency": self.dependency,
            "estimated_value": self.estimated_value,
            "overall_score": self.overall_score,
        }


def compute_overall_score(
    *,
    priority: float,
    urgency: float,
    risk: float,
    dependency: float,
    estimated_value: float,
) -> float:
    """Combine factor scores into one ranking value (0.0–1.0).

    Risk lowers the overall score. Dependency readiness and estimated value
    raise it. Single formula — callers must not re-score after the pass.
    """
    p = max(0.0, min(1.0, priority))
    u = max(0.0, min(1.0, urgency))
    r = max(0.0, min(1.0, risk))
    d = max(0.0, min(1.0, dependency))
    v = max(0.0, min(1.0, estimated_value))
    raw = (
        0.25 * p
        + 0.20 * u
        + 0.25 * v
        + 0.15 * d
        + 0.15 * (1.0 - r)
    )
    return max(0.0, min(1.0, round(raw, 4)))


def compute_confidence(
    *,
    top_score: float,
    second_score: float | None,
    candidate_count: int,
) -> float:
    """Confidence from absolute strength and margin over the runner-up."""
    if candidate_count <= 0:
        return 0.0
    strength = max(0.0, min(1.0, top_score))
    if candidate_count == 1 or second_score is None:
        margin = 1.0
    else:
        margin = max(0.0, min(1.0, top_score - second_score))
    # Emphasize score quality; margin separates near-ties.
    raw = 0.65 * strength + 0.35 * margin
    return max(0.0, min(1.0, round(raw, 4)))


def compute_feedback_score(
    *,
    expected_value: float,
    actual_result: float,
    success: bool,
) -> float:
    """Compare expected vs actual into a signed feedback score (-1.0–1.0).

    Positive scores reinforce confidence; negative scores reduce it.
    """
    expected = max(0.0, min(1.0, float(expected_value)))
    actual = max(0.0, min(1.0, float(actual_result)))
    gap = actual - expected
    if success:
        # Meeting or beating expectation → solid positive; under-delivery softer.
        raw = 0.40 + 0.60 * ((gap + 1.0) / 2.0)
        return max(0.0, min(1.0, round(raw, 4)))
    # Failure is always negative; larger shortfall → stronger penalty.
    raw = -0.40 - 0.60 * ((expected - actual + 1.0) / 2.0)
    return max(-1.0, min(0.0, round(raw, 4)))


@dataclass(frozen=True)
class DecisionFeedback:
    """Outcome of one executed decision action (Phase 17.4)."""

    decision_id: str
    selected_action: str
    expected_value: float
    actual_result: float
    success: bool
    duration: float
    feedback_score: float
    completed_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "selected_action": self.selected_action,
            "expected_value": self.expected_value,
            "actual_result": self.actual_result,
            "success": self.success,
            "duration": self.duration,
            "feedback_score": self.feedback_score,
            "completed_at": self.completed_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionFeedback:
        completed_raw = data.get("completed_at")
        if isinstance(completed_raw, datetime):
            completed_at = completed_raw
        elif completed_raw:
            completed_at = datetime.fromisoformat(str(completed_raw))
        else:
            completed_at = datetime.now(timezone.utc)
        return cls(
            decision_id=str(data.get("decision_id") or ""),
            selected_action=str(data.get("selected_action") or ""),
            expected_value=float(data.get("expected_value") or 0.0),
            actual_result=float(data.get("actual_result") or 0.0),
            success=bool(data.get("success")),
            duration=float(data.get("duration") or 0.0),
            feedback_score=float(data.get("feedback_score") or 0.0),
            completed_at=completed_at,
        )


@dataclass(frozen=True)
class DecisionHistoryStats:
    """Aggregate metrics over the rolling decision history (Phase 17.4)."""

    success_rate: float
    average_feedback: float
    average_duration: float
    sample_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success_rate": self.success_rate,
            "average_feedback": self.average_feedback,
            "average_duration": self.average_duration,
            "sample_count": self.sample_count,
        }


@dataclass
class Decision:
    """Selected next action among plan candidates (Phase 17.3–17.4)."""

    selected_action: str | None
    reason: str
    confidence: float
    priority: float
    risk_score: float
    expected_value: float
    created_at: datetime
    updated_at: datetime | None = None
    candidates: list[ActionCandidateScore] = field(default_factory=list)
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # Phase 17.4 — learning context for PromptBuilder (populated by DecisionEngine).
    success_rate: float | None = None
    average_feedback: float | None = None
    average_duration: float | None = None
    learning_confidence: float | None = None
    recent_history: list[DecisionFeedback] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "selected_action": self.selected_action,
            "reason": self.reason,
            "confidence": self.confidence,
            "priority": self.priority,
            "risk_score": self.risk_score,
            "expected_value": self.expected_value,
            "created_at": self.created_at.isoformat(),
            "updated_at": (
                self.updated_at.isoformat() if self.updated_at is not None else None
            ),
            "candidates": [c.to_dict() for c in self.candidates],
            "success_rate": self.success_rate,
            "average_feedback": self.average_feedback,
            "average_duration": self.average_duration,
            "learning_confidence": self.learning_confidence,
            "recent_history": [f.to_dict() for f in self.recent_history],
        }

    def format_for_prompt(self) -> str:
        """Current Decision block for PromptBuilder (Phase 17.3 / 17.4)."""
        top = self.candidates[:3]
        if top:
            candidates_text = "\n".join(
                f"- {c.action} (score={c.overall_score:.4f}, "
                f"priority={c.priority:.4f}, risk={c.risk:.4f})"
                for c in top
            )
        else:
            candidates_text = "None"

        current_confidence = (
            self.learning_confidence
            if self.learning_confidence is not None
            else self.confidence
        )
        success_rate = (
            f"{self.success_rate:.4f}" if self.success_rate is not None else "None"
        )

        if self.recent_history:
            history_lines = []
            for entry in self.recent_history[-5:]:
                outcome = "success" if entry.success else "failure"
                history_lines.append(
                    f"- {entry.selected_action} ({outcome}, "
                    f"feedback={entry.feedback_score:.4f}, "
                    f"duration={entry.duration:.2f})"
                )
            history_text = "\n".join(history_lines)
        else:
            history_text = "None"

        return (
            f"Current Decision:\n"
            f"{self.selected_action or 'None'}\n\n"
            f"Reason:\n"
            f"{self.reason or 'None'}\n\n"
            f"Current Confidence:\n"
            f"{current_confidence}\n\n"
            f"Success Rate:\n"
            f"{success_rate}\n\n"
            f"Recent Decision History:\n"
            f"{history_text}\n\n"
            f"Top Candidate Actions:\n"
            f"{candidates_text}"
        )

    @classmethod
    def empty(cls, *, now: datetime | None = None, reason: str = "No candidate actions") -> Decision:
        """Idle decision when no plan actions are available."""
        stamp = now or datetime.now(timezone.utc)
        return cls(
            selected_action=None,
            reason=reason,
            confidence=0.0,
            priority=0.0,
            risk_score=0.0,
            expected_value=0.0,
            created_at=stamp,
            updated_at=stamp,
            candidates=[],
        )
