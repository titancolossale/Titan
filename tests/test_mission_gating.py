# =====================================
# Titan Mission Gating Integration Tests
# =====================================

"""Integration tests for mission auto-creation gating in Brain (P1-091 / P1-092)."""

from __future__ import annotations

from brain.brain import Brain


def test_greeting_does_not_create_mission(brain: Brain) -> None:
    """P1-092: inactive mission + greeting must leave active=False."""
    assert brain.mission_manager.get_mission()["active"] is False

    brain.think("bonjour")

    assert brain.mission_manager.get_mission()["active"] is False


def test_explicit_mission_phrase_creates_mission(brain: Brain) -> None:
    """P1-091: explicit mission intent must create an active mission."""
    assert brain.mission_manager.get_mission()["active"] is False

    brain.think("nouvelle mission trading")

    mission = brain.mission_manager.get_mission()
    assert mission["active"] is True
    assert mission["title"] == "Créer un robot de trading"
