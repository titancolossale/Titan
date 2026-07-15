# =====================================
# Titan Orchestrator Progress Formatter
# =====================================

"""Sanitized cognitive progress for web UI — Phase 24.0."""

from __future__ import annotations

from typing import Any

from brain.cognitive_models import CognitiveExecutionResult, CognitivePhase
from brain.cognitive_progress import PHASE_NEURAL_STATE, resolve_neural_state
from brain.pipeline.context_bundle import ThinkContext


def format_orchestrator_progress(
    think_ctx: ThinkContext | None,
) -> list[dict[str, Any]]:
    """Build high-level progress timeline from cognitive execution — no reasoning exposed."""
    if think_ctx is None or think_ctx.cognitive_execution is None:
        return []

    execution: CognitiveExecutionResult = think_ctx.cognitive_execution
    records: list[dict[str, Any]] = []
    seen_labels: set[str] = set()

    for event in execution.runtime.progress_events:
        label = event.label
        if label in seen_labels:
            continue
        seen_labels.add(label)
        records.append({
            "phase": event.phase.value,
            "label": label,
            "neural_state": resolve_neural_state(event.phase, event.tool),
            "tool": event.tool,
        })

    if execution.verification.summary and execution.verification.summary not in seen_labels:
        records.append({
            "phase": CognitivePhase.VERIFICATION.value,
            "label": "Vérification…",
            "neural_state": PHASE_NEURAL_STATE[CognitivePhase.VERIFICATION],
            "tool": None,
        })

    if not records:
        phase = execution.cognitive_phase
        records.append({
            "phase": phase.value,
            "label": "Compréhension de la demande…",
            "neural_state": resolve_neural_state(phase),
            "tool": None,
        })

    return records


def current_neural_state_from_context(think_ctx: ThinkContext | None) -> str:
    """Resolve current neural visualization state from think context."""
    if think_ctx is None:
        return "idle"
    if think_ctx.cognitive_neural_state:
        return think_ctx.cognitive_neural_state
    if think_ctx.cognitive_execution is not None:
        phase = think_ctx.cognitive_execution.cognitive_phase
        return resolve_neural_state(phase)
    return "idle"
