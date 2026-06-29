# =====================================
# Titan MissionManager Tests
# =====================================

"""Baseline regression tests for MissionManager load/save and step behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.mission_manager import MissionManager

EXPECTED_DEFAULT_MISSION = {
    "schema_version": 2,
    "active": False,
    "title": None,
    "objective": None,
    "steps": [],
    "completed_steps": [],
    "current_step": None,
    "status": "idle",
}


def test_load_mission_returns_inactive_default_when_file_missing(
    tmp_path: Path,
) -> None:
    """Missing JSON file must yield inactive idle mission without writing to disk."""
    file_path = tmp_path / "titan_mission.json"
    assert not file_path.exists()

    manager = MissionManager(file_path=file_path)

    assert manager.get_mission() == EXPECTED_DEFAULT_MISSION
    assert not file_path.exists()


def test_create_mission_persists_active_mission_with_first_step(
    tmp_path: Path,
) -> None:
    """create_mission must activate mission, set current_step to first step, and save."""
    file_path = tmp_path / "titan_mission.json"
    manager = MissionManager(file_path=file_path)
    steps = ["Étape A", "Étape B", "Étape C"]

    manager.create_mission(
        title="Test Mission",
        objective="Valider le manager",
        steps=steps,
    )

    mission = manager.get_mission()
    assert mission["active"] is True
    assert mission["title"] == "Test Mission"
    assert mission["objective"] == "Valider le manager"
    assert mission["steps"] == steps
    assert mission["current_step"] == "Étape A"
    assert mission["status"] == "in_progress"

    reloaded = MissionManager(file_path=file_path)
    assert reloaded.get_mission() == mission


def test_complete_current_step_advances_then_marks_completed(
    mission_manager: MissionManager,
) -> None:
    """P8-003: complete_current_step preserves steps list and records history."""
    mission_manager.create_mission(
        title="Step Test",
        objective="Tester les étapes",
        steps=["Première", "Deuxième"],
    )

    mission_manager.complete_current_step()
    mission = mission_manager.get_mission()
    assert mission["steps"] == ["Première", "Deuxième"]
    assert mission["completed_steps"] == ["Première"]
    assert mission["current_step"] == "Deuxième"
    assert mission["active"] is True
    assert mission["status"] == "in_progress"

    mission_manager.complete_current_step()
    mission = mission_manager.get_mission()
    assert mission["steps"] == ["Première", "Deuxième"]
    assert mission["completed_steps"] == ["Première", "Deuxième"]
    assert mission["current_step"] is None
    assert mission["active"] is False
    assert mission["status"] == "completed"


@pytest.mark.parametrize(
    ("message", "expected_title", "expected_step_count"),
    [
        (
            "Je veux créer un robot de trading",
            "Créer un robot de trading",
            7,
        ),
        (
            "On doit améliorer Titan cette semaine",
            "Améliorer Titan",
            5,
        ),
        (
            "Aide-moi avec mon projet",
            "Mission générale",
            4,
        ),
    ],
)
def test_create_mission_from_message_keyword_paths(
    tmp_path: Path,
    message: str,
    expected_title: str,
    expected_step_count: int,
) -> None:
    """create_mission_from_message routes keywords to the correct mission template."""
    manager = MissionManager(file_path=tmp_path / "titan_mission.json")

    result = manager.create_mission_from_message(message)

    assert result["active"] is True
    assert result["title"] == expected_title
    assert result["objective"] == message
    assert len(result["steps"]) == expected_step_count
    assert result["current_step"] == result["steps"][0]
    assert result["status"] == "in_progress"

    reloaded = MissionManager(file_path=tmp_path / "titan_mission.json")
    assert reloaded.get_mission()["title"] == expected_title


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("bonjour", False),
        ("Bonjour Nolan, comment ça va ?", False),
        ("nouvelle mission trading", True),
        ("New mission: build a bot", True),
        ("/mission robot trading", True),
        ("Je veux créer une mission pour Titan", True),
        ("lancer une mission de refactor", True),
        ("Je veux créer un robot de trading", False),
        ("On doit améliorer Titan cette semaine", False),
        ("Aide-moi avec mon projet", False),
    ],
)
def test_should_create_mission_from_message_gate(
    tmp_path: Path,
    message: str,
    expected: bool,
) -> None:
    """P1-090: gate must allow explicit intent only, not casual keywords."""
    manager = MissionManager(file_path=tmp_path / "titan_mission.json")

    assert manager.should_create_mission_from_message(message) is expected
