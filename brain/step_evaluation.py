# =====================================
# Titan Step Evaluation Result
# =====================================

"""Structured step completion evaluation types (Phase 8 — P8-050)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StepEvaluation:
    """Result of mission step completion analysis."""

    step_completed: bool
    reason: str
    source: str = "explicit_phrase"

    @classmethod
    def from_llm_json(cls, data: dict) -> StepEvaluation:
        """Parse LLM JSON evaluator output."""
        completed = bool(data.get("step_completed", False))
        reason = str(data.get("reason", "")).strip() or "Évaluation LLM"
        return cls(step_completed=completed, reason=reason, source="llm")

    @classmethod
    def explicit(cls, reason: str = "Phrase explicite détectée") -> StepEvaluation:
        return cls(step_completed=True, reason=reason, source="explicit_phrase")

    @classmethod
    def not_completed(cls, reason: str = "Aucun signal de complétion") -> StepEvaluation:
        return cls(step_completed=False, reason=reason, source="none")
