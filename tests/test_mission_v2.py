# =====================================
# Titan Mission v2 Tests
# =====================================

"""Tests for Phase 8 mission schema, migration, and commands (P8-001–P8-020)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from brain.brain import Brain
from core.mission_manager import MissionManager
from core.mission_migrator import SCHEMA_VERSION, default_schema, migrate


def test_default_schema_is_v3() -> None:
    """P8-001: default schema includes schema_version and completed_steps."""
    schema = default_schema()
    assert schema["schema_version"] == SCHEMA_VERSION
    assert schema["completed_steps"] == []
    assert schema["status"] == "idle"
    assert schema["missions"] == {}
    assert schema["active_mission_id"] is None


def test_migrate_v1_adds_completed_steps_and_schema_version() -> None:
    """P8-002: legacy mission without schema_version migrates to v3."""
    legacy = {
        "active": True,
        "title": "Legacy",
        "objective": "Test",
        "steps": ["Step B", "Step C"],
        "current_step": "Step B",
        "status": "in_progress",
    }
    result = migrate(legacy)
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["completed_steps"] == []
    assert result["steps"] == ["Step B", "Step C"]
    assert result["current_step"] == "Step B"
    assert result["active_mission_id"] is not None
    assert len(result["missions"]) == 1


def test_migrate_v1_reinserts_orphan_current_step() -> None:
    """P8-002: current_step not in steps list is preserved on migration."""
    legacy = {
        "active": True,
        "title": "Orphan step",
        "steps": ["Step B"],
        "current_step": "Step A",
        "status": "in_progress",
    }
    result = migrate(legacy)
    assert "Step A" in result["steps"]
    assert result["current_step"] == "Step A"


def test_load_mission_migrates_on_disk(tmp_path: Path) -> None:
    """P8-002: MissionManager.load_mission auto-migrates legacy JSON."""
    file_path = tmp_path / "titan_mission.json"
    legacy = {
        "active": False,
        "title": None,
        "objective": None,
        "steps": [],
        "current_step": None,
        "status": "idle",
    }
    file_path.write_text(json.dumps(legacy), encoding="utf-8")

    manager = MissionManager(file_path=file_path)
    mission = manager.get_mission()

    assert mission["schema_version"] == SCHEMA_VERSION
    assert "completed_steps" in mission


def test_format_status_shows_completed_and_remaining(
    mission_manager: MissionManager,
) -> None:
    """P8-010: format_status lists completed and remaining steps."""
    mission_manager.create_mission(
        title="Trading Bot",
        objective="NQ robot",
        steps=["Backtest", "Execution", "Risk"],
    )
    mission_manager.complete_current_step()

    status = mission_manager.format_status()
    assert "Trading Bot" in status
    assert "Backtest" in status
    assert "Execution" in status


def test_handle_command_statut_mission(mission_manager: MissionManager) -> None:
    """P8-011: statut mission returns French status summary."""
    mission_manager.create_mission("Test", "Obj", ["A"])
    response = mission_manager.handle_command("statut mission")
    assert response is not None
    assert "Test" in response


def test_handle_command_terminer_etape(mission_manager: MissionManager) -> None:
    """P8-011: terminer étape advances mission without LLM."""
    mission_manager.create_mission("Test", "Obj", ["A", "B"])
    response = mission_manager.handle_command("terminer étape")
    assert response is not None
    assert "A" in response
    assert mission_manager.get_mission()["current_step"] == "B"


def test_handle_command_annuler_mission(mission_manager: MissionManager) -> None:
    """P8-012: annuler mission cancels active mission."""
    mission_manager.create_mission("Test", "Obj", ["A"])
    response = mission_manager.handle_command("annuler mission")
    assert response is not None
    assert "annulée" in response.lower()
    assert mission_manager.get_mission()["status"] == "cancelled"
    assert mission_manager.get_mission()["active"] is False


def test_handle_command_unknown_returns_none(
    mission_manager: MissionManager,
) -> None:
    """P8-011: non-mission messages return None."""
    assert mission_manager.handle_command("bonjour") is None


def test_brain_skips_llm_for_statut_mission(brain: Brain) -> None:
    """P8-020: statut mission returns direct response without LLM."""
    brain.mission_manager.create_mission("Pipeline Test", "Obj", ["Étape 1"])

    result = brain.think("statut mission")

    assert "Pipeline Test" in result
    assert brain.llm.ask.call_count == 0


def test_brain_skips_llm_for_terminer_etape(brain: Brain) -> None:
    """P8-020: terminer étape completes step without LLM."""
    brain.mission_manager.create_mission("Step Test", "Obj", ["A", "B"])

    result = brain.think("terminer étape")

    assert "A" in result
    assert brain.llm.ask.call_count == 0
    assert brain.mission_manager.get_mission()["current_step"] == "B"


def test_brain_mission_command_in_stage_order() -> None:
    """P8-020: mission_commands stage precedes load_or_create_mission."""
    from brain.pipeline.stages import STAGE_ORDER

    assert "mission_commands" in STAGE_ORDER
    assert STAGE_ORDER.index("mission_commands") < STAGE_ORDER.index(
        "load_or_create_mission",
    )
