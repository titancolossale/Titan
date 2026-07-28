# =====================================
# Titan Execution Safety Tests
# =====================================

"""Phase 18.2 — Execution Safety & Confirmation."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from brain.autonomy_policy import AutonomyPolicy
from brain.decision_engine import DecisionEngine
from brain.execution_engine import ExecutionEngine
from brain.execution_models import ExecutionStatus
from brain.execution_safety import (
    ExecutionRiskLevel,
    ExecutionSafetyEvaluator,
    SafetyDecision,
    sanitize_public_metadata,
)
from brain.planning_models import Plan, PlanStatus
from brain.prompt_builder import PromptBuilder
from brain.pipeline.context_bundle import ThinkContext
from core.state_manager import WorkspaceState
from tools.tool_capability import ToolCapability
from tools.tool_enums import RiskLevel


def _make_plan(*, actions: list[str], status: PlanStatus = PlanStatus.ACTIVE) -> Plan:
    stamp = datetime.now(timezone.utc)
    return Plan(
        current_goal="Ship Titan",
        current_project="Execution Safety",
        current_mission="Phase 18.2",
        next_actions=list(actions),
        priority_score=0.8,
        estimated_duration=30.0,
        dependencies=[],
        blocked_reason=None,
        created_at=stamp,
        updated_at=stamp,
        status=status,
    )


def _decide(action: str):
    plan = _make_plan(actions=[action])
    return plan, DecisionEngine(persist=False).decide(plan=plan)


def _policy(*, confirm_writes: bool = True, confirm_exec: bool = True) -> AutonomyPolicy:
    return AutonomyPolicy(
        require_confirmation_writes=confirm_writes,
        require_confirmation_exec=confirm_exec,
    )


# ---------------------------------------------------------------------------
# Classification / policy
# ---------------------------------------------------------------------------


def test_safe_reads_execute_without_confirmation() -> None:
    plan, decision = _decide("read project status")
    engine = ExecutionEngine(autonomy_policy=_policy(confirm_writes=True))
    workspace = WorkspaceState(active_project="Titan")
    result = engine.execute(
        decision=decision,
        plan=plan,
        workspace=workspace,
        send_feedback=False,
        action_metadata={"risk_level": "SAFE_READ", "execution_traits": ["read_only"]},
    )
    assert result.status == ExecutionStatus.COMPLETED
    assert result.success is True
    assert result.requires_confirmation is False
    assert engine.active_task is not None
    assert engine.active_task.risk_level == ExecutionRiskLevel.SAFE_READ.value
    assert workspace.confirmation_pending is False


def test_low_risk_writes_respect_confirm_writes_enabled() -> None:
    plan, decision = _decide("write note draft")
    engine = ExecutionEngine(autonomy_policy=_policy(confirm_writes=True))
    workspace = WorkspaceState(active_project="Titan")
    result = engine.execute(
        decision=decision,
        plan=plan,
        workspace=workspace,
        send_feedback=False,
        action_metadata={
            "risk_level": "LOW_RISK_WRITE",
            "action_type": "file_write",
            "execution_traits": ["read_write"],
        },
    )
    assert result.status == ExecutionStatus.AWAITING_CONFIRMATION
    assert result.requires_confirmation is True
    assert result.confirmation_id
    assert workspace.confirmation_pending is True
    assert workspace.confirmation_id == result.confirmation_id
    assert workspace.current_execution_risk == ExecutionRiskLevel.LOW_RISK_WRITE.value


def test_low_risk_writes_skip_confirmation_when_writes_disabled() -> None:
    plan, decision = _decide("write note draft")
    engine = ExecutionEngine(autonomy_policy=_policy(confirm_writes=False))
    result = engine.execute(
        decision=decision,
        plan=plan,
        send_feedback=False,
        action_metadata={
            "risk_level": "LOW_RISK_WRITE",
            "action_type": "file_write",
            "execution_traits": ["read_write"],
        },
    )
    assert result.status == ExecutionStatus.COMPLETED
    assert result.success is True


def test_high_risk_writes_always_require_confirmation() -> None:
    plan, decision = _decide("patch production config")
    engine = ExecutionEngine(autonomy_policy=_policy(confirm_writes=False))
    result = engine.execute(
        decision=decision,
        plan=plan,
        send_feedback=False,
        action_metadata={"risk_level": "HIGH_RISK_WRITE"},
    )
    assert result.status == ExecutionStatus.AWAITING_CONFIRMATION
    assert result.requires_confirmation is True


def test_destructive_actions_always_require_confirmation_with_impact() -> None:
    plan, decision = _decide("delete obsolete files")
    engine = ExecutionEngine(autonomy_policy=_policy(confirm_writes=False))
    result = engine.execute(
        decision=decision,
        plan=plan,
        send_feedback=False,
        action_metadata={
            "risk_level": "DESTRUCTIVE",
            "expected_impact": "Permanently deletes matching project files",
        },
    )
    assert result.status == ExecutionStatus.AWAITING_CONFIRMATION
    task = engine.active_task
    assert task is not None
    assert task.risk_level == ExecutionRiskLevel.DESTRUCTIVE.value
    assert task.safety is not None
    assert "Permanently deletes" in task.safety.expected_impact
    assert "Impact:" in result.message


def test_forbidden_actions_never_execute() -> None:
    plan, decision = _decide("bypass confirmation gate")
    engine = ExecutionEngine()
    result = engine.execute(
        decision=decision,
        plan=plan,
        send_feedback=False,
        action_metadata={"risk_level": "FORBIDDEN", "forbidden_reason": "Policy denial"},
    )
    assert result.status == ExecutionStatus.FORBIDDEN
    assert result.success is False
    assert "Policy denial" in (result.blocked_reason or result.message)
    assert engine.active_task is not None
    assert engine.active_task.status == ExecutionStatus.FORBIDDEN


def test_capability_metadata_preferred_over_action_name() -> None:
    plan, decision = _decide("delete something sounding scary but actually read")
    capability = ToolCapability(
        name="file_read",
        description="Read file",
        parameters=(),
        risk_level=RiskLevel.SAFE,
        requires_confirmation=False,
        tags=frozenset({"read_only"}),
    )
    engine = ExecutionEngine(autonomy_policy=_policy(confirm_writes=True))
    result = engine.execute(
        decision=decision,
        plan=plan,
        send_feedback=False,
        capability=capability,
        action_metadata={"execution_traits": ["read_only"]},
    )
    assert result.status == ExecutionStatus.COMPLETED
    assert engine.active_task.risk_level == ExecutionRiskLevel.SAFE_READ.value


def test_non_live_mode_skips_confirmation() -> None:
    plan, decision = _decide("write note")
    engine = ExecutionEngine(autonomy_policy=_policy(confirm_writes=True))
    result = engine.execute(
        decision=decision,
        plan=plan,
        send_feedback=False,
        execution_mode="mock",
        action_metadata={"risk_level": "HIGH_RISK_WRITE"},
    )
    assert result.status == ExecutionStatus.COMPLETED


# ---------------------------------------------------------------------------
# Confirmation lifecycle
# ---------------------------------------------------------------------------


def test_rejection_prevents_execution() -> None:
    plan, decision = _decide("write sensitive file")
    engine = ExecutionEngine(autonomy_policy=_policy(confirm_writes=True))
    held = engine.execute(
        decision=decision,
        plan=plan,
        send_feedback=False,
        action_metadata={"risk_level": "HIGH_RISK_WRITE"},
    )
    assert held.status == ExecutionStatus.AWAITING_CONFIRMATION
    token = held.confirmation_id
    assert token

    rejected = engine.reject(token, send_feedback=False)
    assert rejected.status == ExecutionStatus.CANCELLED
    assert rejected.success is False
    assert engine.active_task is not None
    assert engine.active_task.status == ExecutionStatus.CANCELLED
    assert engine.lookup_pending(token) is None

    # Confirm after reject must not execute.
    again = engine.confirm(token, send_feedback=False)
    assert again.success is False
    assert again.status != ExecutionStatus.COMPLETED


def test_expired_confirmation_prevents_execution() -> None:
    evaluator = ExecutionSafetyEvaluator(
        autonomy_policy=_policy(confirm_writes=True),
        confirmation_ttl_seconds=0.05,
    )
    engine = ExecutionEngine(
        safety_evaluator=evaluator,
        autonomy_policy=_policy(confirm_writes=True),
    )
    # Align gate TTL with evaluator.
    engine.confirmation_gate.token_ttl_seconds = 0.05

    plan, decision = _decide("write after delay")
    held = engine.execute(
        decision=decision,
        plan=plan,
        send_feedback=False,
        action_metadata={"risk_level": "HIGH_RISK_WRITE"},
    )
    token = held.confirmation_id
    assert token
    time.sleep(0.08)
    expired = engine.confirm(token, send_feedback=False)
    assert expired.success is False
    assert expired.status != ExecutionStatus.COMPLETED
    assert engine.active_task is not None
    assert engine.active_task.status != ExecutionStatus.COMPLETED


def test_duplicate_approval_does_not_duplicate_execution() -> None:
    plan, decision = _decide("write once")
    engine = ExecutionEngine(autonomy_policy=_policy(confirm_writes=False))
    held = engine.execute(
        decision=decision,
        plan=plan,
        send_feedback=False,
        action_metadata={"risk_level": "HIGH_RISK_WRITE"},
    )
    token = held.confirmation_id
    assert token

    first = engine.confirm(token, send_feedback=False)
    assert first.status == ExecutionStatus.COMPLETED
    assert first.success is True
    completed_count = sum(
        1 for entry in engine.history.entries if entry.status == ExecutionStatus.COMPLETED
    )
    assert completed_count == 1

    second = engine.confirm(token, send_feedback=False)
    assert second.task_id == first.task_id
    completed_count = sum(
        1 for entry in engine.history.entries if entry.status == ExecutionStatus.COMPLETED
    )
    assert completed_count == 1


def test_concurrent_approvals_execute_at_most_once() -> None:
    plan, decision = _decide("write concurrent")
    engine = ExecutionEngine(autonomy_policy=_policy(confirm_writes=False))
    held = engine.execute(
        decision=decision,
        plan=plan,
        send_feedback=False,
        action_metadata={"risk_level": "HIGH_RISK_WRITE"},
    )
    token = held.confirmation_id
    assert token
    results: list[Any] = []
    barrier = threading.Barrier(8)

    def _approve() -> None:
        barrier.wait()
        results.append(engine.confirm(token, send_feedback=False))

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(_approve) for _ in range(8)]
        for future in futures:
            future.result()

    completed = [r for r in results if r.status == ExecutionStatus.COMPLETED]
    assert len(completed) >= 1
    history_completed = [
        e for e in engine.history.entries if e.status == ExecutionStatus.COMPLETED
    ]
    assert len(history_completed) == 1


# ---------------------------------------------------------------------------
# Secrets / workspace / prompt / diagnostics
# ---------------------------------------------------------------------------


def test_sensitive_arguments_absent_from_logs_and_public_state(
    caplog: pytest.LogCaptureFixture,
) -> None:
    plan, decision = _decide("write secret file")
    engine = ExecutionEngine(autonomy_policy=_policy(confirm_writes=True))
    workspace = WorkspaceState(active_project="Titan")
    secret = "sk-super-secret-value-1234567890123456"
    with caplog.at_level(logging.INFO, logger="brain.execution_engine"):
        result = engine.execute(
            decision=decision,
            plan=plan,
            workspace=workspace,
            send_feedback=False,
            action_metadata={
                "risk_level": "HIGH_RISK_WRITE",
                "api_key": secret,
                "password": "hunter2",
                "path": "notes/todo.md",
            },
        )

    assert result.status == ExecutionStatus.AWAITING_CONFIRMATION
    blob = " ".join(record.getMessage() for record in caplog.records)
    assert secret not in blob
    assert "hunter2" not in blob
    assert "api_key" not in blob.lower() or secret not in blob

    state = workspace.to_dict()
    serialized = str(state)
    assert secret not in serialized
    assert "hunter2" not in serialized
    assert workspace.confirmation_pending is True
    assert workspace.confirmation_id == result.confirmation_id
    assert workspace.current_execution_risk == ExecutionRiskLevel.HIGH_RISK_WRITE.value

    pending = engine.lookup_pending(result.confirmation_id or "")
    assert pending is not None
    assert "api_key" not in pending.public_metadata
    assert "password" not in pending.public_metadata
    assert pending.public_metadata.get("path") == "notes/todo.md"


def test_sanitize_public_metadata_drops_secrets() -> None:
    cleaned = sanitize_public_metadata(
        {
            "path": "a.md",
            "token": "abc",
            "nested": {"api_key": "x", "ok": 1},
        }
    )
    assert cleaned == {"path": "a.md", "nested": {"ok": 1}}


def test_workspace_state_reflects_pending_confirmation() -> None:
    plan, decision = _decide("write vault note")
    engine = ExecutionEngine(autonomy_policy=_policy(confirm_writes=True))
    workspace = WorkspaceState(
        active_project="Titan",
        confirmation_pending=False,
        confirmation_id=None,
        current_execution_risk=None,
        blocked_reason=None,
    )
    result = engine.execute(
        decision=decision,
        plan=plan,
        workspace=workspace,
        send_feedback=False,
        action_metadata={"risk_level": "DESTRUCTIVE"},
    )
    assert workspace.confirmation_pending is True
    assert workspace.confirmation_id == result.confirmation_id
    assert workspace.current_execution_risk == "DESTRUCTIVE"
    assert workspace.brain_mode == "awaiting_confirmation"
    assert workspace.blocked_reason is None


def test_workspace_state_reflects_forbidden_block() -> None:
    plan, decision = _decide("forbidden op")
    engine = ExecutionEngine()
    workspace = WorkspaceState(active_project="Titan")
    engine.execute(
        decision=decision,
        plan=plan,
        workspace=workspace,
        send_feedback=False,
        action_metadata={"forbidden": True, "forbidden_reason": "Not allowed"},
    )
    assert workspace.confirmation_pending is False
    assert workspace.blocked_reason == "Not allowed"
    assert workspace.current_execution_risk == ExecutionRiskLevel.FORBIDDEN.value


def test_prompt_builder_injects_execution_safety_when_relevant() -> None:
    plan, decision = _decide("write high risk")
    engine = ExecutionEngine(autonomy_policy=_policy(confirm_writes=True))
    engine.execute(
        decision=decision,
        plan=plan,
        send_feedback=False,
        action_metadata={
            "risk_level": "HIGH_RISK_WRITE",
            "api_key": "should-not-appear",
        },
    )
    task = engine.active_task
    assert task is not None
    text = task.format_for_prompt()
    assert "Execution Safety" in text
    assert "Risk Level" in text
    assert "Confirmation Required" in text
    assert "should-not-appear" not in text

    prompt = PromptBuilder().build(
        ThinkContext(
            user_message="Go",
            current_user="Nolan",
            execution_text=text,
            execution_task=task,
            execution_result=engine.active_result,
        )
    )
    assert "EXÉCUTION ACTUELLE" in prompt
    assert "Execution Safety" in prompt
    assert "should-not-appear" not in prompt


def test_safety_diagnostics_emitted(caplog: pytest.LogCaptureFixture) -> None:
    plan, decision = _decide("write diag")
    engine = ExecutionEngine(autonomy_policy=_policy(confirm_writes=True))
    with caplog.at_level(logging.INFO, logger="brain.execution_engine"):
        held = engine.execute(
            decision=decision,
            plan=plan,
            send_feedback=False,
            action_metadata={"risk_level": "HIGH_RISK_WRITE"},
        )
        token = held.confirmation_id
        engine.confirm(token, send_feedback=False)

    messages = [record.getMessage() for record in caplog.records]
    assert any(m.startswith("EXECUTION_SAFETY_EVALUATED") for m in messages)
    assert any(m.startswith("EXECUTION_CONFIRMATION_REQUIRED") for m in messages)
    assert any(m.startswith("EXECUTION_CONFIRMED") for m in messages)
    assert any(m.startswith("EXECUTION_COMPLETED") for m in messages)


def test_forbidden_diagnostic(caplog: pytest.LogCaptureFixture) -> None:
    plan, decision = _decide("nope")
    with caplog.at_level(logging.INFO, logger="brain.execution_engine"):
        ExecutionEngine().execute(
            decision=decision,
            plan=plan,
            send_feedback=False,
            action_metadata={"risk_level": "FORBIDDEN"},
        )
    messages = [record.getMessage() for record in caplog.records]
    assert any(m.startswith("EXECUTION_FORBIDDEN") for m in messages)


def test_reject_diagnostic(caplog: pytest.LogCaptureFixture) -> None:
    plan, decision = _decide("write reject")
    engine = ExecutionEngine(autonomy_policy=_policy(confirm_writes=True))
    held = engine.execute(
        decision=decision,
        plan=plan,
        send_feedback=False,
        action_metadata={"risk_level": "HIGH_RISK_WRITE"},
    )
    with caplog.at_level(logging.INFO, logger="brain.execution_engine"):
        engine.reject(held.confirmation_id or "", send_feedback=False)
    messages = [record.getMessage() for record in caplog.records]
    assert any(m.startswith("EXECUTION_REJECTED") for m in messages)


def test_cognitive_actions_without_metadata_remain_safe_by_default() -> None:
    """Phase 18.1 regression — plain next-actions still auto-run."""
    plan, decision = _decide("Design models")
    result = ExecutionEngine().execute(
        decision=decision,
        plan=plan,
        send_feedback=False,
    )
    assert result.status == ExecutionStatus.COMPLETED
    assert result.success is True


def test_evaluator_insufficient_metadata_defaults_safer_than_safe_read() -> None:
    evaluator = ExecutionSafetyEvaluator(autonomy_policy=_policy())
    risk = evaluator.classify_risk(
        action="do the thing",
        action_metadata={"unknown_flag": True},
    )
    assert risk == ExecutionRiskLevel.LOW_RISK_WRITE
    assert risk != ExecutionRiskLevel.SAFE_READ
