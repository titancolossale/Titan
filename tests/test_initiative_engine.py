# =====================================
# Titan Initiative Engine Tests
# =====================================

"""Tests for Phase 9 initiative detection (P9-050)."""

from __future__ import annotations

from pathlib import Path

from brain.autonomy_policy import AutonomyPolicy, ProactiveLevel
from brain.initiative_engine import InitiativeEngine, InitiativeKind
from memory.learning_memory import LearningMemory, LearningOutcome


def test_initiative_suppressed_when_policy_off() -> None:
    """Default policy must not surface initiative signals."""
    engine = InitiativeEngine(policy=AutonomyPolicy(proactive_level=ProactiveLevel.OFF))
    result = engine.analyze("c'est urgent!", mission={"active": True})

    assert result.suppressed is True
    assert result.has_signals is False


def test_risk_keyword_triggers_signal() -> None:
    """Urgency keywords produce risk signals when proactive enabled."""
    engine = InitiativeEngine(
        policy=AutonomyPolicy(proactive_level=ProactiveLevel.MEDIUM),
    )
    result = engine.analyze("deadline demain pour le projet")

    assert result.has_signals
    assert any(signal.kind is InitiativeKind.RISK for signal in result.signals)


def test_learning_warnings_from_failed_records(tmp_path: Path) -> None:
    """Failed learning records surface learning initiative signals."""
    learning = LearningMemory(file_path=tmp_path / "learning.json")
    learning.record_outcome("Titan", "big refactor", LearningOutcome.FAILURE, user="Nolan")

    engine = InitiativeEngine(
        policy=AutonomyPolicy(proactive_level=ProactiveLevel.HIGH),
        learning_memory=learning,
    )
    result = engine.analyze("continuer", project_id="Titan", user="Nolan")

    assert any(signal.kind is InitiativeKind.LEARNING for signal in result.signals)


def test_format_for_prompt_empty_when_suppressed() -> None:
    """No prompt block when initiative is suppressed."""
    engine = InitiativeEngine()
    result = engine.analyze("test")
    assert result.format_for_prompt() == ""
