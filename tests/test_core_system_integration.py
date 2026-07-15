# =====================================
# Titan Core System Integration Tests
# =====================================

"""Integration validation for the complete cognitive architecture wiring."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from brain.brain import Brain
from brain.cognitive_operating_system import CognitiveStage, ExecutionStatus
from brain.natural_language_orchestrator import DetectedIntent, SystemName
from core.titan import Titan


def _write(path: Path, content: str = "# note\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_python_project(root: Path, *, name: str = "TitanIntegration") -> Path:
    project = root / name
    project.mkdir(parents=True)
    _write(project / "requirements.txt", "pytest\n")
    _write(project / "README.md", f"# {name}\n")
    for pkg in ("core", "brain", "memory", "tools", "tests"):
        (project / pkg).mkdir(exist_ok=True)
        _write(project / pkg / "__init__.py", "")
    _write(
        project / "brain" / "engine.py",
        "class Engine:\n    def run(self):\n        return True\n",
    )
    return project


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return _make_python_project(tmp_path)


@pytest.fixture
def integrated_brain(brain: Brain, project: Path) -> Brain:
    """Brain fixture with a minimal Python project as workspace root."""
    brain.tool_manager._project_root = project  # type: ignore[attr-defined]
    return brain


# ---------------------------------------------------------------------------
# Composition root & shared instances
# ---------------------------------------------------------------------------


def test_titan_initializes_full_cognitive_stack() -> None:
    """Composition root must wire Brain, NLO, COS, AWE, and execution coordinator."""
    titan = Titan()
    b = titan.brain

    assert b.natural_language_orchestrator is not None
    assert b.cognitive_operating_system is not None
    assert b.autonomous_workflow_engine is not None
    assert b.reasoning_engine is not None
    assert b.meta_cognition is not None
    assert b.cognitive_context_builder is not None
    assert b.world_model is not None
    assert b.knowledge_learning_engine is not None
    assert b.execution_coordinator is not None
    assert b.execution_coordinator.cognitive_orchestrator is not None


def test_cognitive_orchestrator_shared_between_cos_and_workflow_engine() -> None:
    """COS and AWE must share one CognitiveOrchestrator from ExecutionCoordinator."""
    titan = Titan()
    orchestrator = titan.brain.execution_coordinator.cognitive_orchestrator

    assert titan.brain.cognitive_operating_system._cognitive_orchestrator is orchestrator
    assert titan.brain.autonomous_workflow_engine._cognitive_orchestrator is orchestrator


def test_cognitive_dependency_chain_order(integrated_brain: Brain) -> None:
    """Later subsystems must reference earlier ones (initialization contract)."""
    b = integrated_brain

    assert b.reasoning_engine._cognitive_context_builder is b.cognitive_context_builder
    assert b.meta_cognition is not None
    assert b.cognitive_operating_system._reasoning_engine is b.reasoning_engine
    assert b.cognitive_operating_system._meta_cognition is b.meta_cognition
    assert b.autonomous_workflow_engine._reasoning_engine is b.reasoning_engine


def test_brain_public_entry_points_remain_available(integrated_brain: Brain) -> None:
    """Backward-compatible Brain facades must remain callable."""
    b = integrated_brain

    assert callable(b.think)
    assert callable(b.process_request)
    assert callable(b.run_cognitive_cycle)
    assert callable(b.build_cognitive_execution_plan)
    assert callable(b.create_workflow)
    assert callable(b.reason)
    assert callable(b.build_cognitive_context_for_request)


# ---------------------------------------------------------------------------
# Cross-subsystem integration
# ---------------------------------------------------------------------------


def test_nlo_invokes_reasoning_before_downstream_systems(integrated_brain: Brain) -> None:
    """Informational requests must route through NLO → Reasoning → Brain systems."""
    result = integrated_brain.process_request("What is Python?")

    assert result.detected_intent == DetectedIntent.QUESTION
    assert SystemName.REASONING_ENGINE.value in result.systems_used.invoked
    assert result.final_response
    assert integrated_brain.last_orchestration_result is result


def test_nlo_graceful_degradation_when_workspace_unavailable(
    integrated_brain: Brain,
) -> None:
    """NLO must continue when an optional awareness subsystem fails."""
    with patch.object(
        integrated_brain,
        "refresh_workspace",
        side_effect=RuntimeError("workspace unavailable"),
    ):
        result = integrated_brain.process_request("Hello Titan")

    assert result.final_response
    assert SystemName.WORKSPACE_AWARENESS.value in " ".join(result.systems_used.skipped)


def test_cos_export_is_json_serializable(integrated_brain: Brain) -> None:
    """Exported cognitive execution records must be JSON-safe for Web App APIs."""
    plan = integrated_brain.build_cognitive_execution_plan("Integration export test")
    integrated_brain.execute_cognitive_plan(plan.plan_id)

    exported = integrated_brain.export_cognitive_execution(plan.execution_id)
    payload = json.dumps(exported, ensure_ascii=False)

    assert exported["execution_id"] == plan.execution_id
    assert "trace" in exported
    assert "metrics" in exported
    assert json.loads(payload)["status"] in {
        ExecutionStatus.COMPLETED.value,
        ExecutionStatus.AWAITING_CONFIRMATION.value,
    }


def test_workflow_export_is_json_serializable(integrated_brain: Brain) -> None:
    """Workflow exports must serialize cleanly for API consumers."""
    record = integrated_brain.create_workflow("Export workflow test")
    exported = integrated_brain.export_workflow(record.workflow_id)

    json.dumps(exported, ensure_ascii=False)
    assert exported["workflow_id"] == record.workflow_id
    assert exported["objective"] == "Export workflow test"


def test_orchestration_result_is_json_serializable(integrated_brain: Brain) -> None:
    """NLO OrchestrationResult.to_dict() must be JSON-safe."""
    result = integrated_brain.process_request("Run pytest in the project")
    payload = json.dumps(result.to_dict(), ensure_ascii=False)

    parsed = json.loads(payload)
    assert parsed["detected_intent"] in {
        DetectedIntent.TOOL_REQUEST.value,
        DetectedIntent.RESEARCH.value,
    }
    assert parsed["confidence"] > 0.0


def test_read_only_systems_do_not_mutate_long_term_memory(
    integrated_brain: Brain,
    tmp_path: Path,
) -> None:
    """World Model and Proactive Intelligence are read-only — no memory writes."""
    memory_path = integrated_brain.memory_service.long_term.file_path
    before = memory_path.read_text(encoding="utf-8") if memory_path.exists() else ""

    integrated_brain.refresh_world_model("Integration read-only check")
    integrated_brain.evaluate_proactive_context()

    after = memory_path.read_text(encoding="utf-8") if memory_path.exists() else ""
    assert before == after


def test_cognitive_modules_import_cleanly() -> None:
    """Key cognitive modules must import without circular dependency errors."""
    import importlib

    modules = (
        "brain.cognitive_operating_system",
        "brain.autonomous_workflow_engine",
        "brain.natural_language_orchestrator",
        "brain.cognitive_context_builder",
        "brain.reasoning_engine",
        "brain.meta_cognition",
        "brain.world_model",
        "brain.knowledge_learning_engine",
        "brain.proactive_intelligence",
        "brain.project_intelligence",
        "brain.code_intelligence",
        "brain.developer_workflow",
        "core.mission_runtime",
    )
    for name in modules:
        importlib.import_module(name)
