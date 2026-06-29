# =====================================
# Titan Learning Memory Tests
# =====================================

"""Tests for Phase 9 learning memory layer (P9-020)."""

from __future__ import annotations

from pathlib import Path

from memory.learning_memory import LearningMemory, LearningOutcome


def test_record_and_retrieve_outcome(tmp_path: Path) -> None:
    """Learning records persist and filter by domain."""
    store = LearningMemory(file_path=tmp_path / "learning_memory.json")
    store.record_outcome(
        "coding",
        "async refactor",
        LearningOutcome.FAILURE,
        user="Nolan",
    )
    store.record_outcome(
        "coding",
        "incremental refactor",
        LearningOutcome.SUCCESS,
        user="Nolan",
    )

    records = store.get_records_for_domain("coding", user="Nolan")
    assert len(records) == 2


def test_confidence_reflects_outcomes(tmp_path: Path) -> None:
    """Failed approaches lower confidence; successes raise it."""
    store = LearningMemory(file_path=tmp_path / "learning_memory.json")
    store.record_outcome("planning", "big bang", LearningOutcome.FAILURE)
    store.record_outcome("planning", "big bang", LearningOutcome.FAILURE)

    confidence = store.confidence_for_approach("planning", "big bang")
    assert confidence == 0.0

    store.record_outcome("planning", "small steps", LearningOutcome.SUCCESS)
    assert store.confidence_for_approach("planning", "small steps") == 1.0


def test_format_for_prompt_empty_when_no_records(tmp_path: Path) -> None:
    """No prompt block when domain has no lessons."""
    store = LearningMemory(file_path=tmp_path / "learning_memory.json")
    assert store.format_for_prompt("trading") == ""
