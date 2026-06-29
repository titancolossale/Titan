# =====================================
# Titan Autonomy Policy Tests
# =====================================

"""Tests for Phase 9 autonomy guardrails (P9-001)."""

from __future__ import annotations

from brain.autonomy_policy import (
    AutonomousActionType,
    AutonomyPolicy,
    ProactiveLevel,
)


def test_default_policy_is_conservative() -> None:
    """Proactive initiative off by default; confirmations required."""
    policy = AutonomyPolicy.from_settings()

    assert policy.proactive_level is ProactiveLevel.OFF
    assert policy.auto_tool_use is False
    assert policy.require_confirmation_writes is True
    assert policy.require_confirmation_exec is True


def test_proactive_level_caps_suggestions() -> None:
    """Higher proactive levels allow more initiative suggestions."""
    off = AutonomyPolicy(proactive_level=ProactiveLevel.OFF)
    low = AutonomyPolicy(proactive_level=ProactiveLevel.LOW)
    high = AutonomyPolicy(proactive_level=ProactiveLevel.HIGH)

    assert off.should_surface_initiative() is False
    assert low.should_surface_initiative() is True
    assert off.initiative_max_suggestions() == 0
    assert low.initiative_max_suggestions() == 1
    assert high.initiative_max_suggestions() == 3


def test_confirmation_gates_by_action_type() -> None:
    """Write vs exec actions respect separate confirmation flags."""
    policy = AutonomyPolicy(
        require_confirmation_writes=True,
        require_confirmation_exec=False,
    )

    assert policy.requires_confirmation(AutonomousActionType.FILE_WRITE) is True
    assert policy.requires_confirmation(AutonomousActionType.PYTHON_EXEC) is False


def test_job_cap_enforced() -> None:
    """Scheduler respects max_scheduled_jobs."""
    policy = AutonomyPolicy(max_scheduled_jobs=2)

    assert policy.can_register_job(0) is True
    assert policy.can_register_job(1) is True
    assert policy.can_register_job(2) is False


def test_background_jobs_require_proactive_level() -> None:
    """Background scheduling disabled when proactive is off."""
    off = AutonomyPolicy(proactive_level=ProactiveLevel.OFF)
    low = AutonomyPolicy(proactive_level=ProactiveLevel.LOW)

    assert off.allows_background_jobs() is False
    assert low.allows_background_jobs() is True
