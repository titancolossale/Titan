# =====================================
# Titan Phase 19.4 Production Soak Tests
# =====================================

"""Focused regressions for live soak invariants (no live LLM required).

Heavy real-provider soak lives in ``scripts/phase19_4_live_soak.py``.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from pathlib import Path

import pytest

from api.chat_service import (
    _acquire_brain_lock,
    _release_brain_lock,
    reset_brain_lock_for_tests,
)
from brain.autonomy_policy import AutonomyPolicy
from brain.decision_engine import DecisionEngine
from brain.execution_engine import ExecutionEngine
from brain.execution_models import ExecutionStatus
from brain.execution_tool_models import BridgeExecutionResult
from brain.planning_engine import PlanningEngine
from brain.planning_models import Plan, PlanStatus
from brain.request_deadline import RequestDeadline
from core.goal_matcher import match_goal
from core.goal_models import Goal, GoalPriority, GoalState
from core.project_matcher import match_project
from core.project_models import Project, ProjectPriority, ProjectState
from core.state_manager import WorkspaceState
from core.web_conversations.db import (
    apply_migrations,
    backend_name,
    create_conversation_engine,
)
from core.web_conversations.models import MessageStatus
from core.web_conversations.repository import ConversationRepository
from core.web_conversations.service import ConversationService
from datetime import datetime, timezone


RAILWAY_BASE = "https://titan-production-e377.up.railway.app"


def _plan(actions: list[str]) -> Plan:
    stamp = datetime.now(timezone.utc)
    return Plan(
        current_goal="Soak",
        current_project="Soak",
        current_mission="Soak",
        next_actions=list(actions),
        priority_score=0.8,
        estimated_duration=10.0,
        dependencies=[],
        blocked_reason=None,
        created_at=stamp,
        updated_at=stamp,
        status=PlanStatus.ACTIVE,
    )


def test_railway_health_ready_auth_and_postgres() -> None:
    """Production contract: healthy, ready, auth on, Postgres conversation store."""
    with urllib.request.urlopen(f"{RAILWAY_BASE}/health", timeout=20) as resp:
        health = json.loads(resp.read().decode())
    with urllib.request.urlopen(f"{RAILWAY_BASE}/ready", timeout=20) as resp:
        ready = json.loads(resp.read().decode())

    assert health.get("status") == "ok"
    assert health.get("auth_required") is True
    assert health.get("session_auth") is True
    assert ready.get("status") == "ready"
    store = (ready.get("checks") or {}).get("conversation_store") or {}
    assert store.get("ok") is True
    assert store.get("backend") == "postgresql"

    req = urllib.request.Request(
        f"{RAILWAY_BASE}/chat/stream",
        data=b'{"message":"x"}',
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(Exception) as exc_info:
        urllib.request.urlopen(req, timeout=15)
    assert getattr(exc_info.value, "code", None) == 401


def test_high_risk_execution_requires_confirmation_and_does_not_dispatch() -> None:
    calls = {"n": 0}

    class _Bridge:
        def dispatch(self, **kwargs):
            calls["n"] += 1
            raise RuntimeError("must not dispatch")

        def apply_workspace_update(self, *a, **k) -> None:
            return None

    plan = _plan(["delete production database"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    engine = ExecutionEngine(
        autonomy_policy=AutonomyPolicy(
            require_confirmation_writes=True,
            require_confirmation_exec=True,
        ),
        tool_bridge=_Bridge(),
    )
    workspace = WorkspaceState(active_project="Soak")
    result = engine.execute(
        decision=decision,
        plan=plan,
        workspace=workspace,
        send_feedback=False,
        action_metadata={
            "risk_level": "CRITICAL",
            "execution_traits": ["destructive", "external_write"],
        },
    )
    assert result.requires_confirmation is True
    assert result.status == ExecutionStatus.AWAITING_CONFIRMATION
    assert calls["n"] == 0
    assert workspace.confirmation_pending is True


def test_safe_no_side_effect_execution_completes() -> None:
    class _Bridge:
        def dispatch(self, **kwargs):
            return BridgeExecutionResult.cognitive_success(message="ok")

        def apply_workspace_update(self, workspace, result) -> None:
            if workspace is not None:
                workspace.execution_status = result.status.value

    plan = _plan(["echo soak"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    engine = ExecutionEngine(
        autonomy_policy=AutonomyPolicy(
            require_confirmation_writes=True,
            require_confirmation_exec=True,
        ),
        tool_bridge=_Bridge(),
    )
    result = engine.execute(
        decision=decision,
        plan=plan,
        workspace=WorkspaceState(active_project="Soak"),
        send_feedback=False,
        action_metadata={
            "risk_level": "SAFE_READ",
            "execution_traits": ["read_only", "no_side_effect"],
        },
    )
    assert result.success is True
    assert result.status == ExecutionStatus.COMPLETED
    assert result.requires_confirmation is False


def test_planning_engine_creates_single_active_plan(tmp_path: Path) -> None:
    engine = PlanningEngine()
    workspace = WorkspaceState(active_project="Soak")
    plan1 = engine.plan_next(workspace=workspace)
    plan2 = engine.plan_next(workspace=workspace)
    assert engine.active_plan is plan2
    assert plan1 is not None and plan2 is not None


def test_project_and_goal_matchers_high_vs_low_confidence() -> None:
    now = datetime.now(timezone.utc)
    projects = [
        Project(
            id="a",
            name="Soak Alpha",
            description="A",
            status=ProjectState.ACTIVE.value,
            priority=ProjectPriority.NORMAL,
            created_at=now,
            updated_at=now,
            progress=0.0,
            mission_ids=[],
            completed_mission_ids=[],
            active_mission_id=None,
            aliases=["alpha"],
            keywords=["soak-a"],
        ),
        Project(
            id="b",
            name="Soak Beta",
            description="B",
            status=ProjectState.PAUSED.value,
            priority=ProjectPriority.NORMAL,
            created_at=now,
            updated_at=now,
            progress=0.0,
            mission_ids=[],
            completed_mission_ids=[],
            active_mission_id=None,
            aliases=["beta"],
            keywords=["soak-b"],
        ),
    ]
    high = match_project("Continue on Soak Beta please", projects)
    low = match_project("maybe later", projects)
    assert high.matched is True
    assert low.matched is False

    goals = [
        Goal(
            id="g1",
            name="Soak Goal Alpha",
            description="A",
            status=GoalState.ACTIVE.value,
            priority=GoalPriority.NORMAL,
            created_at=now,
            updated_at=now,
            progress=0.0,
            project_ids=[],
            active_project_id=None,
            aliases=["goal-alpha"],
            keywords=["soak-goal-a"],
        ),
        Goal(
            id="g2",
            name="Soak Goal Beta",
            description="B",
            status=GoalState.PAUSED.value,
            priority=GoalPriority.NORMAL,
            created_at=now,
            updated_at=now,
            progress=0.0,
            project_ids=[],
            active_project_id=None,
            aliases=["goal-beta"],
            keywords=["soak-goal-b"],
        ),
    ]
    g_high = match_goal("Focus on Soak Goal Beta now", goals)
    g_low = match_goal("hmm maybe", goals)
    assert g_high.matched is True
    assert g_low.matched is False


def test_brain_lock_timeout_emits_diagnostic(caplog: pytest.LogCaptureFixture) -> None:
    reset_brain_lock_for_tests()
    d1 = RequestDeadline.start(total_seconds=30, request_id="owner-1")
    assert _acquire_brain_lock("owner-1", d1) is not None
    # Request deadline must outlive the lock wait budget so we hit lock timeout,
    # not BrainTimeoutError.
    d2 = RequestDeadline.start(total_seconds=30, request_id="waiter-1")
    with caplog.at_level(logging.INFO):
        acquired = _acquire_brain_lock("waiter-1", d2, timeout_seconds=0.2)
    assert acquired is None
    assert any("CHAT_BRAIN_LOCK_TIMEOUT" in r.getMessage() for r in caplog.records)
    _release_brain_lock("owner-1")
    reset_brain_lock_for_tests()


def test_stale_brain_lock_is_reclaimed_after_max_hold(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    reset_brain_lock_for_tests()
    monkeypatch.setattr("api.chat_service.TITAN_BRAIN_LOCK_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr("api.chat_service.TITAN_BRAIN_LOCK_STALE_SECONDS", 0.2)
    monkeypatch.setattr("api.chat_service.TITAN_BRAIN_LOCK_RECLAIM_ENABLED", True)
    d1 = RequestDeadline.start(total_seconds=30, request_id="stale-owner")
    from api.chat_service import register_active_deadline, unregister_active_deadline
    from api.chat_service import _brain_lock_manager

    register_active_deadline(d1)
    assert _acquire_brain_lock("stale-owner", d1) is not None

    aged = time.monotonic() - 120.0
    with _brain_lock_manager._state_lock:
        _brain_lock_manager._ownership.acquired_at = aged
        _brain_lock_manager._ownership.last_heartbeat_at = aged
    d1.cancel()

    d2 = RequestDeadline.start(total_seconds=5, request_id="reclaimer")
    with caplog.at_level(logging.INFO):
        acquired = _acquire_brain_lock("reclaimer", d2, timeout_seconds=0.25)
    assert acquired is not None
    assert any("CHAT_BRAIN_LOCK_RECLAIMED" in r.getMessage() for r in caplog.records)
    _release_brain_lock("reclaimer", acquired)
    unregister_active_deadline("stale-owner")
    reset_brain_lock_for_tests()


def test_fresh_brain_lock_is_not_reclaimed_early(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_brain_lock_for_tests()
    monkeypatch.setattr("api.chat_service.TITAN_CHAT_DEADLINE_SECONDS", 30.0)
    monkeypatch.setattr("api.chat_service.TITAN_BRAIN_LOCK_TIMEOUT_SECONDS", 5.0)
    monkeypatch.setattr("api.chat_service.TITAN_BRAIN_LOCK_STALE_SECONDS", 45.0)
    d1 = RequestDeadline.start(total_seconds=30, request_id="fresh-owner")
    from api.chat_service import register_active_deadline, unregister_active_deadline

    register_active_deadline(d1)
    gen = _acquire_brain_lock("fresh-owner", d1)
    assert gen is not None
    d2 = RequestDeadline.start(total_seconds=5, request_id="waiter")
    acquired = _acquire_brain_lock("waiter", d2, timeout_seconds=0.15)
    assert acquired is None
    _release_brain_lock("fresh-owner", gen)
    unregister_active_deadline("fresh-owner")
    reset_brain_lock_for_tests()


def test_conversation_persistence_no_duplicate_assistant(tmp_path: Path) -> None:
    engine = create_conversation_engine(
        sqlite_path=tmp_path / "conversations.db",
        force_sqlite=True,
    )
    apply_migrations(engine)
    service = ConversationService(repository=ConversationRepository(engine=engine))
    conv = service.create_conversation("soak-user", title="t")
    service.repository.add_message(
        conversation_id=conv.id,
        user_id="soak-user",
        role="user",
        content="hi",
    )
    service.repository.add_message(
        conversation_id=conv.id,
        user_id="soak-user",
        role="assistant",
        content="hello",
        request_id="req-1",
        status=MessageStatus.COMPLETED.value,
    )
    service.repository.add_message(
        conversation_id=conv.id,
        user_id="soak-user",
        role="assistant",
        content="hello again",
        request_id="req-1",
        status=MessageStatus.COMPLETED.value,
    )
    _c, messages, total = service.get_conversation_with_messages(conv.id, "soak-user")
    assert total == 2
    assert backend_name(str(engine.url)) == "sqlite"
    assert all(
        m.status != MessageStatus.PENDING.value
        for m in messages
        if m.role == "assistant"
    )
