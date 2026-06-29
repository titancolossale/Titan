# =====================================
# Titan Confirmation Gate Tests
# =====================================

"""Unit tests for Phase 10A confirmation gating (P10A-021)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from brain.autonomy_policy import AutonomyPolicy
from tools.confirmation_gate import ConfirmationGate
from tools.tool_capability import ToolCapability
from tools.tool_enums import ExecutionMode, RiskLevel
from tools.tool_run_models import ToolExecutionContext, ToolRunStatus
from tools.tool_runtime import ToolRuntime


@pytest.fixture
def gate() -> ConfirmationGate:
    return ConfirmationGate(autonomy_policy=AutonomyPolicy.from_settings())


@pytest.fixture
def high_risk_capability() -> ToolCapability:
    return ToolCapability(
        name="python_exec",
        description="Execute Python",
        parameters=(),
        risk_level=RiskLevel.HIGH,
        action_type="python_exec",
    )


@pytest.fixture
def medium_write_capability() -> ToolCapability:
    return ToolCapability(
        name="file_write",
        description="Write file",
        parameters=(),
        risk_level=RiskLevel.MEDIUM,
        action_type="file_write",
        requires_confirmation=True,
    )


@pytest.fixture
def safe_capability() -> ToolCapability:
    return ToolCapability(
        name="time",
        description="Current time",
        parameters=(),
        risk_level=RiskLevel.SAFE,
    )


def test_requires_confirmation_high_risk_live(
    gate: ConfirmationGate,
    high_risk_capability: ToolCapability,
) -> None:
    """P10A-020: HIGH risk in LIVE always requires approval."""
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        execution_mode=ExecutionMode.LIVE,
    )
    assert gate.requires_confirmation(high_risk_capability, ctx)


def test_requires_confirmation_skipped_in_mock(
    gate: ConfirmationGate,
    high_risk_capability: ToolCapability,
) -> None:
    """P10A-020: non-LIVE modes skip confirmation envelope."""
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        execution_mode=ExecutionMode.MOCK,
    )
    assert not gate.requires_confirmation(high_risk_capability, ctx)


def test_requires_confirmation_skipped_on_dry_run(
    gate: ConfirmationGate,
    high_risk_capability: ToolCapability,
) -> None:
    """P10A-020: dry_run bypasses confirmation."""
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        dry_run=True,
    )
    assert not gate.requires_confirmation(high_risk_capability, ctx)


def test_evaluate_issues_pending_request(
    gate: ConfirmationGate,
    high_risk_capability: ToolCapability,
) -> None:
    """P10A-020: unconfirmed invocation returns ConfirmationRequest."""
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    result = gate.evaluate("python_exec", high_risk_capability, ctx, {"code": "1+1"})
    assert not result.satisfied
    assert result.request is not None
    assert result.request.tool_name == "python_exec"
    assert result.request.token


def test_validate_confirmation_accepts_matching_token(
    gate: ConfirmationGate,
    high_risk_capability: ToolCapability,
) -> None:
    """P10A-020: confirmed re-invocation with valid token passes."""
    params = {"code": "1+1"}
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    pending = gate.evaluate("python_exec", high_risk_capability, ctx, params)
    assert pending.request is not None

    confirmed_ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        confirmed=True,
        confirmation_token=pending.request.token,
    )
    validated = gate.evaluate("python_exec", high_risk_capability, confirmed_ctx, params)
    assert validated.satisfied


def test_validate_confirmation_rejects_wrong_params(
    gate: ConfirmationGate,
    high_risk_capability: ToolCapability,
) -> None:
    """P10A-020: token is bound to parameter digest."""
    params = {"code": "1+1"}
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    pending = gate.evaluate("python_exec", high_risk_capability, ctx, params)
    assert pending.request is not None

    confirmed_ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        confirmed=True,
        confirmation_token=pending.request.token,
    )
    validated = gate.evaluate(
        "python_exec",
        high_risk_capability,
        confirmed_ctx,
        {"code": "2+2"},
    )
    assert not validated.satisfied


def test_autonomy_policy_controls_medium_tools(
    medium_write_capability: ToolCapability,
) -> None:
    """P10A-020: MEDIUM tools respect AutonomyPolicy when not HIGH risk."""
    strict = ConfirmationGate(
        autonomy_policy=AutonomyPolicy(require_confirmation_writes=True),
    )
    relaxed = ConfirmationGate(
        autonomy_policy=AutonomyPolicy(require_confirmation_writes=False),
    )
    relaxed_cap = replace(medium_write_capability, requires_confirmation=None, risk_level=RiskLevel.LOW)
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    assert strict.requires_confirmation(medium_write_capability, ctx)
    assert not relaxed.requires_confirmation(relaxed_cap, ctx)


def test_safe_tool_skips_confirmation(
    gate: ConfirmationGate,
    safe_capability: ToolCapability,
) -> None:
    """P10A-020: SAFE tools proceed without confirmation."""
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    result = gate.evaluate("time", safe_capability, ctx, {})
    assert result.satisfied


def test_purge_expired_removes_stale_tokens(
    high_risk_capability: ToolCapability,
) -> None:
    """P10A-020: expired tokens are purged."""
    gate = ConfirmationGate(token_ttl_seconds=0.01)
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    gate.evaluate("python_exec", high_risk_capability, ctx, {"code": "1"})
    import time

    time.sleep(0.02)
    removed = gate.purge_expired()
    assert removed == 1


def test_runtime_invoke_pending_for_high_risk(project_root: Path) -> None:
    """P10A-021: runtime returns PENDING_CONFIRMATION for gated tools."""
    from tools.python_exec_tool import PythonExecTool
    from tools.tool_manager import ToolManager

    manager = ToolManager(
        project_root=project_root,
        use_runtime_v2=True,
        register_defaults=False,
    )
    manager.registry.register(PythonExecTool(project_root))
    assert manager.runtime is not None
    manager.runtime.refresh_catalog()

    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    outcome = manager.runtime.invoke(
        "python_exec",
        {"code": "print('ok')"},
        ctx,
    )
    assert outcome.status == ToolRunStatus.PENDING_CONFIRMATION
    assert outcome.confirmation_request is not None
    assert not outcome.is_terminal()


def test_runtime_confirmed_high_risk_executes(project_root: Path) -> None:
    """P10A-021: confirmed token allows high-risk execution."""
    from tools.python_exec_tool import PythonExecTool
    from tools.tool_manager import ToolManager

    manager = ToolManager(
        project_root=project_root,
        use_runtime_v2=True,
        register_defaults=False,
    )
    manager.registry.register(PythonExecTool(project_root))
    assert manager.runtime is not None
    manager.runtime.refresh_catalog()

    params = {"code": "print('confirmed')"}
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    pending = manager.runtime.invoke("python_exec", params, ctx)
    assert pending.confirmation_request is not None

    confirmed_ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        confirmed=True,
        confirmation_token=pending.confirmation_request.token,
    )
    outcome = manager.runtime.invoke("python_exec", params, confirmed_ctx)
    assert outcome.status == ToolRunStatus.COMPLETED
    assert outcome.result is not None
    assert outcome.result.success


def test_runtime_outcome_pending_maps_to_legacy_result(project_root: Path) -> None:
    """P10A-021: outcome_to_result preserves pending metadata for legacy callers."""
    from tools.python_exec_tool import PythonExecTool
    from tools.tool_manager import ToolManager

    manager = ToolManager(
        project_root=project_root,
        use_runtime_v2=True,
        register_defaults=False,
    )
    manager.registry.register(PythonExecTool(project_root))
    assert manager.runtime is not None
    manager.runtime.refresh_catalog()

    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    outcome = manager.runtime.invoke("python_exec", {"code": "1+1"}, ctx)
    result = manager.runtime.outcome_to_result(outcome)
    assert not result.success
    assert result.metadata.get("pending_confirmation") is True
    assert result.metadata.get("confirmation_token")


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path
