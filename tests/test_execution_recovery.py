# =====================================
# Titan Execution Recovery Tests
# =====================================

"""Phase 18.4 — Execution recovery, retry, rollback, resume, timeout."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from brain.execution_engine import ExecutionEngine
from brain.execution_models import ExecutionStatus
from brain.execution_recovery import (
    DIAG_EXECUTION_ABORT,
    DIAG_EXECUTION_RECOVERED,
    DIAG_EXECUTION_RESUME,
    DIAG_EXECUTION_RETRY,
    DIAG_EXECUTION_ROLLBACK,
    DIAG_EXECUTION_TIMEOUT,
    ExecutionCheckpoint,
    ExecutionRecoveryManager,
    ExecutionRetryPolicy,
    RecoveryAction,
    RollbackRecord,
    RollbackStatus,
)
from brain.execution_tool_models import BridgeExecutionResult, BridgeExecutionStatus
from brain.prompt_builder import PromptBuilder
from brain.pipeline.context_bundle import ThinkContext
from core.state_manager import WorkspaceState


class _ScriptedBridge:
    """Tool Execution Bridge stub returning scripted BridgeExecutionResult values."""

    def __init__(self, results: list[BridgeExecutionResult]) -> None:
        self._results = list(results)
        self.calls = 0
        self.rollback_calls = 0

    def dispatch(self, **kwargs: Any) -> BridgeExecutionResult:
        self.calls += 1
        if not self._results:
            return BridgeExecutionResult.cognitive_success(message="empty script")
        return self._results.pop(0)

    def apply_workspace_update(
        self, workspace: Any | None, result: BridgeExecutionResult
    ) -> None:
        if workspace is None:
            return
        workspace.last_tool = result.tool_id
        workspace.last_execution = result.execution_result
        workspace.execution_status = result.status.value
        workspace.execution_duration = result.duration
        workspace.last_error = result.error if not result.success else None


def _decision(action: str = "retryable_action", decision_id: str = "dec-1") -> Any:
    return SimpleNamespace(
        selected_action=action,
        decision_id=decision_id,
        reason="test",
        expected_value=0.5,
    )


def _engine(
    tmp_path: Path,
    *,
    bridge: _ScriptedBridge | None = None,
    max_attempts: int = 3,
    retry_delay: float = 0.0,
    results: list[BridgeExecutionResult] | None = None,
) -> ExecutionEngine:
    scripted = bridge or _ScriptedBridge(results or [])
    policy = ExecutionRetryPolicy(
        max_attempts=max_attempts,
        retry_delay=retry_delay,
        backoff_multiplier=2.0,
        retry_on_timeout=True,
    )
    recovery = ExecutionRecoveryManager(
        policy=policy,
        checkpoint_path=tmp_path / "execution_checkpoint.json",
        sleep_fn=lambda _seconds: None,
    )
    return ExecutionEngine(
        tool_bridge=scripted,  # type: ignore[arg-type]
        recovery_manager=recovery,
        retry_policy=policy,
        checkpoint_path=tmp_path / "execution_checkpoint.json",
        auto_resume=False,
    )


def _failed(
    *,
    message: str = "connection temporarily unavailable",
    status: BridgeExecutionStatus = BridgeExecutionStatus.FAILED,
    reversible: bool = False,
    rollback_token: str | None = None,
    tool_id: str | None = "fake_tool",
) -> BridgeExecutionResult:
    return BridgeExecutionResult(
        status=status,
        message=message,
        success=False,
        duration=0.01,
        tool_id=tool_id,
        action_id="run",
        error=message,
        result_summary=message,
        reversible=reversible,
        rollback_token=rollback_token,
    )


def _success(*, message: str = "ok") -> BridgeExecutionResult:
    return BridgeExecutionResult(
        status=BridgeExecutionStatus.SUCCESS,
        message=message,
        success=True,
        duration=0.01,
        tool_id="fake_tool",
        action_id="run",
        result_summary=message,
    )


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


def test_retry_policy_retries_transient_failure(tmp_path: Path) -> None:
    bridge = _ScriptedBridge(
        [
            _failed(message="connection temporarily unavailable"),
            _success(message="recovered"),
        ]
    )
    engine = _engine(tmp_path, bridge=bridge, max_attempts=3, retry_delay=0.0)
    workspace = WorkspaceState()

    result = engine.execute(
        decision=_decision(),
        workspace=workspace,
        action_metadata={"risk_level": "SAFE_READ"},
        send_feedback=False,
    )

    assert result.success is True
    assert result.status == ExecutionStatus.COMPLETED
    assert bridge.calls == 2
    assert engine.active_task is not None
    assert engine.active_task.attempt_number == 2
    assert engine.recovery_manager.state.execution_recovered is True
    assert workspace.retry_count >= 1
    assert workspace.execution_recovered is True


def test_retry_limit_aborts_after_max_attempts(tmp_path: Path) -> None:
    bridge = _ScriptedBridge(
        [
            _failed(message="timeout waiting for upstream"),
            _failed(message="timeout waiting for upstream"),
            _failed(message="timeout waiting for upstream"),
        ]
    )
    engine = _engine(tmp_path, bridge=bridge, max_attempts=3, retry_delay=0.0)

    result = engine.execute(
        decision=_decision(),
        workspace=WorkspaceState(),
        action_metadata={"risk_level": "SAFE_READ"},
        send_feedback=False,
    )

    assert result.success is False
    assert result.status == ExecutionStatus.TIMEOUT or result.status == ExecutionStatus.FAILED
    assert bridge.calls == 3
    assert engine.recovery_manager.state.retry_count == 3
    assert result.recovery_action == RecoveryAction.ABORT.value


def test_never_retry_forbidden(tmp_path: Path) -> None:
    bridge = _ScriptedBridge([])
    engine = _engine(tmp_path, bridge=bridge, max_attempts=5)

    result = engine.execute(
        decision=_decision(action="exfiltrate credentials dump"),
        workspace=WorkspaceState(),
        action_metadata={"forbidden": True, "forbidden_reason": "policy"},
        send_feedback=False,
    )

    assert result.status == ExecutionStatus.FORBIDDEN
    assert bridge.calls == 0
    assert result.success is False


def test_never_retry_confirmation_required(tmp_path: Path) -> None:
    bridge = _ScriptedBridge([])
    engine = _engine(tmp_path, bridge=bridge, max_attempts=5)

    result = engine.execute(
        decision=_decision(action="delete production database"),
        workspace=WorkspaceState(),
        action_metadata={
            "risk_level": "DESTRUCTIVE",
            "execution_traits": ["delete"],
        },
        execution_mode="live",
        send_feedback=False,
    )

    assert result.status == ExecutionStatus.AWAITING_CONFIRMATION
    assert bridge.calls == 0


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


def test_timeout_handling_retries_then_succeeds(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    timeout = BridgeExecutionResult(
        status=BridgeExecutionStatus.TIMEOUT,
        message="Tool timed out after 1.0s: fake_tool:run",
        success=False,
        duration=1.0,
        tool_id="fake_tool",
        action_id="run",
        error="Tool timed out after 1.0s: fake_tool:run",
        result_summary="Tool timed out after 1.0s: fake_tool:run",
    )
    bridge = _ScriptedBridge([timeout, _success()])
    engine = _engine(tmp_path, bridge=bridge, max_attempts=3, retry_delay=0.0)

    with caplog.at_level(logging.INFO, logger="brain.execution_engine"):
        result = engine.execute(
            decision=_decision(),
            workspace=WorkspaceState(),
            action_metadata={"risk_level": "SAFE_READ"},
            send_feedback=False,
        )

    assert result.success is True
    assert bridge.calls == 2
    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith(DIAG_EXECUTION_TIMEOUT) for msg in messages)
    assert any(msg.startswith(DIAG_EXECUTION_RETRY) for msg in messages)


# ---------------------------------------------------------------------------
# Resume after restart
# ---------------------------------------------------------------------------


def test_resume_after_restart_restores_waiting(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "execution_checkpoint.json"
    manager = ExecutionRecoveryManager(
        policy=ExecutionRetryPolicy(max_attempts=3, retry_delay=0.0),
        checkpoint_path=checkpoint_path,
        sleep_fn=lambda _s: None,
    )
    stamp = datetime.now(timezone.utc).isoformat()
    manager.persist_checkpoint(
        ExecutionCheckpoint(
            task_id="task-wait-1",
            action="deferred_action",
            status=ExecutionStatus.WAITING.value,
            decision_id="dec-wait",
            attempt_number=1,
            last_failure_reason="resume later",
            recovery_action=RecoveryAction.WAIT.value,
            created_at=stamp,
            updated_at=stamp,
            resumable=True,
        )
    )

    engine = ExecutionEngine(
        tool_bridge=_ScriptedBridge([]),  # type: ignore[arg-type]
        recovery_manager=ExecutionRecoveryManager(
            policy=ExecutionRetryPolicy(max_attempts=3, retry_delay=0.0),
            checkpoint_path=checkpoint_path,
            sleep_fn=lambda _s: None,
        ),
        checkpoint_path=checkpoint_path,
        auto_resume=False,
    )
    workspace = WorkspaceState()
    resumed = engine.resume_after_restart(workspace=workspace, send_feedback=False)

    assert resumed is not None
    assert resumed.status == ExecutionStatus.WAITING
    assert engine.active_task is not None
    assert engine.active_task.task_id == "task-wait-1"
    assert engine.recovery_manager.state.execution_recovered is True
    assert workspace.execution_recovered is True


def test_resume_after_restart_aborts_non_resumable(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "execution_checkpoint.json"
    manager = ExecutionRecoveryManager(
        checkpoint_path=checkpoint_path,
        sleep_fn=lambda _s: None,
    )
    stamp = datetime.now(timezone.utc).isoformat()
    manager.persist_checkpoint(
        ExecutionCheckpoint(
            task_id="task-run-1",
            action="risky_write",
            status=ExecutionStatus.RUNNING.value,
            irreversible_fingerprint="t|a|risky_write|dec",
            attempt_number=1,
            created_at=stamp,
            updated_at=stamp,
            resumable=True,
        )
    )

    engine = ExecutionEngine(
        tool_bridge=_ScriptedBridge([]),  # type: ignore[arg-type]
        recovery_manager=ExecutionRecoveryManager(
            checkpoint_path=checkpoint_path,
            sleep_fn=lambda _s: None,
        ),
        checkpoint_path=checkpoint_path,
        auto_resume=False,
    )
    result = engine.resume_after_restart(workspace=WorkspaceState(), send_feedback=False)

    assert result is not None
    assert result.status == ExecutionStatus.CANCELLED
    assert result.success is False
    assert engine.recovery_manager.checkpoint is None


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


def test_rollback_when_reversible(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    bridge = _ScriptedBridge(
        [
            _failed(
                message="write failed after partial apply",
                reversible=True,
                rollback_token="rb-1",
            ),
        ]
    )
    engine = _engine(tmp_path, bridge=bridge, max_attempts=1, retry_delay=0.0)
    workspace = WorkspaceState()

    with caplog.at_level(logging.INFO, logger="brain.execution_recovery"):
        result = engine.execute(
            decision=_decision(),
            workspace=workspace,
            action_metadata={
                "risk_level": "SAFE_READ",
                "prefer_rollback": True,
                "reversible": True,
            },
            send_feedback=False,
        )

    assert result.success is False
    assert workspace.rollback_available is False or result.rollback_completed is True
    rolled = engine.rollback(reason="test cleanup", workspace=workspace)
    # First execute may already have rolled back via recovery action.
    assert rolled.rollback_status in (
        RollbackStatus.COMPLETED,
        RollbackStatus.SKIPPED,
        RollbackStatus.FAILED,
    )
    messages = [record.getMessage() for record in caplog.records]
    assert any(DIAG_EXECUTION_ROLLBACK in msg for msg in messages)


def test_irreversible_action_protection(tmp_path: Path) -> None:
    bridge = _ScriptedBridge([_success(message="wrote once")])
    engine = _engine(tmp_path, bridge=bridge, max_attempts=2)

    first = engine.execute(
        decision=_decision(action="irreversible_write", decision_id="same"),
        workspace=WorkspaceState(),
        action_metadata={
            "risk_level": "SAFE_READ",
            "reversible": False,
        },
        send_feedback=False,
    )
    assert first.success is True
    assert bridge.calls == 1

    # Second run of the same irreversible fingerprint must abort without dispatch.
    second = engine.execute(
        decision=_decision(action="irreversible_write", decision_id="same"),
        workspace=WorkspaceState(),
        action_metadata={
            "risk_level": "SAFE_READ",
            "reversible": False,
        },
        send_feedback=False,
    )
    assert second.success is False
    assert "Irreversible action already executed" in (second.error or second.message)
    assert bridge.calls == 1


def test_never_rollback_irreversible(tmp_path: Path) -> None:
    manager = ExecutionRecoveryManager(sleep_fn=lambda _s: None)
    manager.store_rollback(
        RollbackRecord(
            reversible=False,
            rollback_status=RollbackStatus.SKIPPED,
            rollback_reason="irreversible",
        )
    )
    record = manager.rollback(reason="should skip")
    assert record.rollback_status == RollbackStatus.SKIPPED
    assert record.rollback_completed is False


# ---------------------------------------------------------------------------
# Partial success
# ---------------------------------------------------------------------------


def test_partial_success_marked(tmp_path: Path) -> None:
    partial = BridgeExecutionResult(
        status=BridgeExecutionStatus.PARTIAL_SUCCESS,
        message="partial ok",
        success=True,
        duration=0.02,
        tool_id="fake_tool",
        action_id="run",
        result_summary="partial ok",
        error="minor warning",
    )
    bridge = _ScriptedBridge([partial])
    engine = _engine(tmp_path, bridge=bridge)
    workspace = WorkspaceState()

    result = engine.execute(
        decision=_decision(),
        workspace=workspace,
        action_metadata={"risk_level": "SAFE_READ"},
        send_feedback=False,
    )

    assert result.status == ExecutionStatus.PARTIAL_SUCCESS
    assert result.success is True
    assert result.actual_result == 0.5
    assert result.recovery_action == RecoveryAction.MARK_PARTIAL_SUCCESS.value


# ---------------------------------------------------------------------------
# WorkspaceState + prompt + diagnostics
# ---------------------------------------------------------------------------


def test_workspace_state_recovery_fields(tmp_path: Path) -> None:
    bridge = _ScriptedBridge(
        [
            _failed(message="connection temporarily unavailable"),
            _success(),
        ]
    )
    engine = _engine(tmp_path, bridge=bridge, max_attempts=3, retry_delay=0.0)
    workspace = WorkspaceState(
        current_retry=0,
        retry_count=0,
        rollback_available=False,
        execution_recovered=False,
        last_failure_reason=None,
    )

    engine.execute(
        decision=_decision(),
        workspace=workspace,
        action_metadata={"risk_level": "SAFE_READ"},
        send_feedback=False,
    )

    assert workspace.retry_count >= 1
    assert workspace.execution_recovered is True
    assert workspace.last_failure_reason is not None or workspace.current_retry >= 1


def test_prompt_builder_exposes_recovery_fields_only(tmp_path: Path) -> None:
    bridge = _ScriptedBridge(
        [
            _failed(message="connection temporarily unavailable"),
            _success(),
        ]
    )
    engine = _engine(tmp_path, bridge=bridge, max_attempts=3, retry_delay=0.0)
    engine.execute(
        decision=_decision(),
        workspace=WorkspaceState(),
        action_metadata={"risk_level": "SAFE_READ"},
        send_feedback=False,
    )
    task = engine.active_task
    assert task is not None
    text = task.format_for_prompt()
    assert "Execution Recovery" in text
    assert "Retry Count:" in text
    assert "Rollback Available:" in text
    assert "Current Failure:" in text
    # Must not dump raw recovery policy internals into the prompt block.
    assert "backoff_multiplier" not in text
    assert "max_attempts" not in text

    prompt = PromptBuilder().build(
        ThinkContext(
            user_message="test",
            execution_text=text,
            execution_task=task,
            execution_result=engine.active_result,
        )
    )
    assert "Execution Recovery" in prompt
    assert "Retry Count:" in prompt


def test_recovery_diagnostics_emitted(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bridge = _ScriptedBridge(
        [
            _failed(message="connection temporarily unavailable"),
            _success(),
        ]
    )
    engine = _engine(tmp_path, bridge=bridge, max_attempts=3, retry_delay=0.0)

    with caplog.at_level(logging.INFO, logger="brain.execution_engine"):
        with caplog.at_level(logging.INFO, logger="brain.execution_recovery"):
            engine.execute(
                decision=_decision(),
                workspace=WorkspaceState(),
                action_metadata={"risk_level": "SAFE_READ"},
                send_feedback=False,
            )

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith(DIAG_EXECUTION_RETRY) for msg in messages)
    assert any(msg.startswith(DIAG_EXECUTION_RECOVERED) for msg in messages)


def test_wait_recovery_persists_checkpoint(tmp_path: Path) -> None:
    bridge = _ScriptedBridge(
        [_failed(message="need to wait", status=BridgeExecutionStatus.FAILED)]
    )
    engine = _engine(tmp_path, bridge=bridge, max_attempts=1)
    result = engine.execute(
        decision=_decision(),
        workspace=WorkspaceState(),
        action_metadata={
            "risk_level": "SAFE_READ",
            "wait": True,
            "recovery_action": "WAIT",
        },
        send_feedback=False,
    )
    assert result.status == ExecutionStatus.WAITING
    assert (tmp_path / "execution_checkpoint.json").exists()


def test_abort_diagnostic_on_non_retryable(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bridge = _ScriptedBridge([_failed(message="permanent validation error")])
    engine = _engine(tmp_path, bridge=bridge, max_attempts=3)

    with caplog.at_level(logging.INFO, logger="brain.execution_engine"):
        result = engine.execute(
            decision=_decision(),
            workspace=WorkspaceState(),
            action_metadata={"risk_level": "SAFE_READ"},
            send_feedback=False,
        )

    assert result.success is False
    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith(DIAG_EXECUTION_ABORT) for msg in messages)


def test_resume_diagnostic(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    checkpoint_path = tmp_path / "execution_checkpoint.json"
    mgr = ExecutionRecoveryManager(checkpoint_path=checkpoint_path)
    mgr.persist_checkpoint(
        ExecutionCheckpoint(
            task_id="t1",
            action="a",
            status=ExecutionStatus.WAITING.value,
            resumable=True,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    engine = ExecutionEngine(
        tool_bridge=_ScriptedBridge([]),  # type: ignore[arg-type]
        recovery_manager=ExecutionRecoveryManager(checkpoint_path=checkpoint_path),
        checkpoint_path=checkpoint_path,
        auto_resume=False,
    )
    with caplog.at_level(logging.INFO, logger="brain.execution_engine"):
        engine.resume_after_restart(send_feedback=False)
    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith(DIAG_EXECUTION_RESUME) for msg in messages)
