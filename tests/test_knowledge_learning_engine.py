# =====================================
# Titan Knowledge Learning Engine Tests
# =====================================

"""Comprehensive tests for Knowledge & Learning Engine V1."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.brain import Brain
from brain.developer_workflow import DeveloperWorkflowPlan, WorkflowIntent
from brain.knowledge_learning_engine import (
    KnowledgeCategory,
    KnowledgeLearningEngine,
    KnowledgeSource,
    KnowledgeStatus,
)
from brain.llm import LLM
from brain.reasoning_models import (
    ReasoningDomain,
    ReasoningRecommendation,
    ReasoningResult,
    ReasoningRisk,
    ReasoningSummary,
    ReasoningUrgency,
    RequestUnderstanding,
)
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.mission_models import MissionState
from core.state_manager import StateManager
from memory.learning_memory import LearningMemory
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService
from tools.tool_enums import RiskLevel
from tools.tool_manager import ToolManager


def _engine(tmp_path: Path) -> KnowledgeLearningEngine:
    return KnowledgeLearningEngine(
        memory_service=MemoryService(
            short_term=MemoryManager(),
            long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
        ),
        learning_memory=LearningMemory(file_path=tmp_path / "learning_memory.json"),
        file_path=tmp_path / "knowledge_learning.json",
    )


def _build_brain(tmp_path: Path) -> Brain:
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Réponse de test."
    state = StateManager(file_path=tmp_path / "titan_state.json")
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )
    brain = Brain(
        agent_manager=AgentManager(memory_service=memory),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=memory,
        tool_manager=ToolManager(project_root=tmp_path),
        llm=mock_llm,
        learning_memory=LearningMemory(file_path=tmp_path / "learning_memory.json"),
    )
    brain.knowledge_learning_engine = KnowledgeLearningEngine(
        memory_service=brain.memory_service,
        learning_memory=brain.learning_memory,
        project_intelligence=brain.project_intelligence,
        code_intelligence=brain.code_intelligence,
        mission_manager=brain.mission_manager,
        developer_workflow=brain.developer_workflow,
        reasoning_engine=brain.reasoning_engine,
        executive_function=brain.executive_function,
        context_manager=brain.context_manager,
        file_path=tmp_path / "knowledge_learning.json",
    )
    return brain


def test_generate_candidate_knowledge(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    item = engine.generate_candidate_knowledge(
        title="Prefer pytest",
        description="Use pytest for all new Titan modules.",
        category=KnowledgeCategory.CONVENTION,
        tags=["testing", "pytest"],
    )

    assert item.id
    assert item.status == KnowledgeStatus.CANDIDATE
    assert item.verified is False
    assert item.confidence >= 0.25
    assert item.evidence_count == 1
    assert "pytest" in item.tags


def test_learn_from_feedback_creates_correction(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    result = engine.learn_from_feedback(
        "Non, utilise toujours pathlib au lieu de os.path.",
        user="Nolan",
    )

    assert result.candidates_created or result.candidates_updated
    item = (result.candidates_created or result.candidates_updated)[0]
    assert item.category in (
        KnowledgeCategory.CORRECTION,
        KnowledgeCategory.PATTERN,
    )
    assert item.source == KnowledgeSource.FEEDBACK


def test_repeated_correction_becomes_pattern(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    feedback = "Incorrect — préfère les imports absolus, pas relatifs."

    engine.learn_from_feedback(feedback, user="Nolan")
    result = engine.learn_from_feedback(feedback, user="Nolan")

    assert result.patterns_detected == 1
    item = (result.candidates_created or result.candidates_updated)[0]
    assert item.category == KnowledgeCategory.PATTERN
    assert item.evidence_count >= 2


def test_learn_from_execution_success_and_failure(tmp_path: Path) -> None:
    engine = _engine(tmp_path)

    success = engine.learn_from_execution(
        tool_name="browser",
        success=True,
        summary_message="Page fetched successfully.",
    )
    failure = engine.learn_from_execution(
        tool_name="python_exec",
        success=False,
        summary_message="Timeout after 5 seconds.",
    )

    success_item = success.candidates_created[0]
    failure_item = failure.candidates_created[0]
    assert success_item.category == KnowledgeCategory.STRATEGY_SUCCESS
    assert failure_item.category == KnowledgeCategory.STRATEGY_FAILURE
    assert "browser" in success_item.related_tools
    assert "python_exec" in failure_item.related_tools


def test_learn_from_execution_records_learning_memory(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    engine.learn_from_execution(
        tool_name="file_read",
        success=True,
        summary_message="Read config file.",
        user="Nolan",
    )

    records = engine._learning_memory.get_records_for_domain("tool_execution")
    assert len(records) == 1
    assert records[0].approach == "file_read"


def test_learn_from_code_change(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    result = engine.learn_from_code_change(
        files_changed=["brain/knowledge_learning_engine.py"],
        change_summary="Added knowledge learning engine module.",
        patch_approved=True,
    )

    item = result.candidates_created[0]
    assert item.category == KnowledgeCategory.CONVENTION
    assert item.source == KnowledgeSource.CODE_CHANGE
    assert "brain/knowledge_learning_engine.py" in item.related_files


def test_learn_from_interaction_with_outcome(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    result = engine.learn_from_interaction(
        "Run the browser tool on example.com",
        "Page loaded.",
        outcome="success — navigation completed",
        tools_used=["browser"],
    )

    categories = {
        item.category
        for item in result.candidates_created + result.candidates_updated
    }
    assert KnowledgeCategory.STRATEGY_SUCCESS in categories


def test_learn_from_interaction_routes_correction_to_feedback(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    result = engine.learn_from_interaction(
        "Non, ne fais pas ça.",
        "D'accord.",
    )

    assert result.source == KnowledgeSource.FEEDBACK


def test_learn_from_workflow(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    plan = DeveloperWorkflowPlan(
        goal="Add knowledge tests",
        context_summary="New learning engine",
        relevant_files=("brain/knowledge_learning_engine.py",),
        recommended_tools=("file_read", "python_exec"),
        recommended_commands=(),
        test_plan=("pytest tests/test_knowledge_learning_engine.py",),
        risk_level=RiskLevel.LOW,
        next_steps=("Create tests", "Run pytest", "Update docs"),
        requires_confirmation=False,
        intent=WorkflowIntent.CONTINUE_DEVELOPMENT,
    )

    result = engine.learn_from_workflow(plan, user="Nolan")
    item = result.candidates_created[0]
    assert item.category == KnowledgeCategory.WORKFLOW
    assert item.source == KnowledgeSource.WORKFLOW
    assert "file_read" in item.related_tools


def test_learn_from_reasoning(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    reasoning = ReasoningResult(
        message="Refactor auth module",
        understanding=RequestUnderstanding(
            objective="Refactor auth",
            constraints=(),
            urgency=ReasoningUrgency.NORMAL,
            domain=ReasoningDomain.CODE,
            requested_output="recommend",
            raw_message="Refactor auth module",
        ),
        summary=ReasoningSummary(
            objective="Refactor auth",
            domain=ReasoningDomain.CODE,
            urgency=ReasoningUrgency.NORMAL,
            requested_output="recommend",
            constraints=(),
            confidence_score=0.8,
            reasoning_quality_score=0.8,
            completeness_score=0.7,
            clarification_required=False,
            headline="Refactor with tests first",
        ),
        steps=(),
        alternatives=(),
        risks=(
            ReasoningRisk(
                id="r1",
                summary="Breaking API change",
                severity="high",
                mitigation="Add compatibility layer",
            ),
        ),
        assumptions=(),
        open_questions=(),
        recommendation=ReasoningRecommendation(
            strategy="Incremental refactor with tests first",
            supporting_arguments=("Minimize blast radius", "Enable rollback"),
            confidence=0.85,
        ),
    )

    result = engine.learn_from_reasoning(reasoning, user="Nolan")
    categories = {item.category for item in result.candidates_created}
    assert KnowledgeCategory.STRATEGY_SUCCESS in categories
    assert KnowledgeCategory.LESSON in categories


def test_approve_and_reject_candidate(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    item = engine.generate_candidate_knowledge(
        title="Test convention",
        description="Always run pytest before merge.",
    )

    approved = engine.approve_candidate(item.id, actor="Nolan", note="Confirmed.")
    assert approved is not None
    assert approved.status == KnowledgeStatus.VERIFIED
    assert approved.verified is True
    assert approved.confidence >= 0.75
    assert len(approved.verification_history) == 1

    second = engine.generate_candidate_knowledge(
        title="Reject me",
        description="Temporary draft.",
    )
    rejected = engine.reject_candidate(second.id, actor="Nolan", note="Not useful.")
    assert rejected is not None
    assert rejected.status == KnowledgeStatus.REJECTED
    assert rejected.confidence == 0.0


def test_list_candidates_and_verified(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    candidate = engine.generate_candidate_knowledge(
        title="Candidate only",
        description="Awaiting review.",
    )
    verified_item = engine.generate_candidate_knowledge(
        title="Verified item",
        description="Approved knowledge.",
    )
    engine.approve_candidate(verified_item.id)

    candidates = engine.list_candidates()
    verified = engine.list_verified_knowledge()

    assert any(item.id == candidate.id for item in candidates)
    assert any(item.id == verified_item.id for item in verified)
    assert all(item.status == KnowledgeStatus.VERIFIED for item in verified)


def test_search_knowledge(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    item = engine.generate_candidate_knowledge(
        title="Pytest convention",
        description="Use pytest for unit tests in tests/.",
        tags=["pytest", "testing"],
    )
    engine.approve_candidate(item.id)

    results = engine.search_knowledge("pytest", verified_only=True)
    assert any(r.id == item.id for r in results)

    unverified = engine.search_knowledge("pytest", verified_only=False)
    assert unverified


def test_update_confidence(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    item = engine.generate_candidate_knowledge(
        title="Confidence test",
        description="Track evidence growth.",
    )
    original = item.confidence

    updated = engine.update_confidence(
        item.id,
        evidence_increment=2,
        delta=0.1,
    )
    assert updated is not None
    assert updated.evidence_count == 3
    assert updated.confidence >= original


def test_merge_duplicate_knowledge(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    primary = engine.generate_candidate_knowledge(
        title="Duplicate A",
        description="Same lesson about imports — primary.",
    )
    duplicate = engine.generate_candidate_knowledge(
        title="Duplicate B",
        description="Same lesson about imports — duplicate.",
    )

    merged = engine.merge_duplicate_knowledge(primary.id, duplicate.id)
    assert merged is not None
    assert merged.evidence_count >= 2
    assert engine.get_knowledge(duplicate.id) is None
    assert any(record.action == "merged" for record in merged.verification_history)


def test_upsert_increments_evidence_on_duplicate_fingerprint(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    feedback = "Incorrect — always use pathlib for file paths."

    engine.learn_from_feedback(feedback, user="Nolan")
    result = engine.learn_from_feedback(feedback, user="Nolan")
    item = (result.candidates_created or result.candidates_updated)[0]

    assert item.evidence_count >= 2


def test_persistence_round_trip(tmp_path: Path) -> None:
    store = tmp_path / "knowledge_learning.json"
    engine = KnowledgeLearningEngine(file_path=store)

    item = engine.generate_candidate_knowledge(
        title="Persisted knowledge",
        description="Survives reload.",
    )
    engine.approve_candidate(item.id)

    reloaded = KnowledgeLearningEngine(file_path=store)
    loaded = reloaded.get_knowledge(item.id)
    assert loaded is not None
    assert loaded.status == KnowledgeStatus.VERIFIED
    assert loaded.title == "Persisted knowledge"


def test_format_for_prompt_verified_only(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    item = engine.generate_candidate_knowledge(
        title="Prompt knowledge",
        description="Visible after approval.",
        tags=["prompt"],
    )
    engine.approve_candidate(item.id)

    text = engine.format_for_prompt("prompt")
    assert "Prompt knowledge" in text
    assert "vérifiées" in text.lower() or "verif" in text.lower()


def test_learn_from_execution_with_mission_failure(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Failing mission", "Test failure learning", ["Run"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)

    result = brain.learn_from_execution(
        mission_id=mission.id,
        tool_name="terminal",
        success=False,
        summary_message="Command exited with code 1.",
    )

    assert result.candidates_created
    titles = [item.title.lower() for item in result.candidates_created]
    assert any("terminal" in title or "mission" in title for title in titles)


def test_brain_api_delegates_to_engine(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    item = brain.generate_candidate_knowledge(
        title="Brain facade",
        description="Created via Brain API.",
    )
    assert item.id

    approved = brain.approve_knowledge(item.id, note="OK")
    assert approved is not None
    assert approved.verified

    results = brain.search_knowledge("Brain facade")
    assert results


def test_learn_from_project_with_mock_intelligence(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    mock_pi = MagicMock()
    mock_summary = MagicMock()
    mock_summary.summary = "Titan uses a modular monolith with Brain as conductor."
    mock_summary.modules = [object(), object()]
    mock_pi.analyze_project.return_value = mock_summary
    mock_pi.find_feature.return_value = None
    engine._project_intelligence = mock_pi

    result = engine.learn_from_project("architecture overview", user="Nolan")
    assert result.candidates_created
    assert result.candidates_created[0].source == KnowledgeSource.PROJECT


def test_rejected_knowledge_excluded_from_search(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    item = engine.generate_candidate_knowledge(
        title="Rejected search test",
        description="Should not appear in default search.",
        tags=["rejected"],
    )
    engine.reject_candidate(item.id)

    results = engine.search_knowledge("rejected search test")
    assert not any(r.id == item.id for r in results)
