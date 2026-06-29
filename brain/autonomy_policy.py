# =====================================
# Titan Autonomy Policy
# =====================================

"""User-configurable autonomy guardrails (Phase 9 — P9-001)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from config.settings import (
    AUTONOMY_AUTO_TOOL_USE,
    AUTONOMY_MAX_SCHEDULED_JOBS,
    AUTONOMY_PROACTIVE_LEVEL,
    AUTONOMY_REQUIRE_CONFIRMATION_EXEC,
    AUTONOMY_REQUIRE_CONFIRMATION_WRITES,
)


class ProactiveLevel(str, Enum):
    """Initiative surfacing intensity — off by default (Constitution Art. 11)."""

    OFF = "off"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AutonomousActionType(str, Enum):
    """Categories of actions subject to confirmation gates."""

    FILE_WRITE = "file_write"
    PYTHON_EXEC = "python_exec"
    WEB_SEARCH = "web_search"
    AUTOMATION = "automation"
    SCHEDULED_JOB = "scheduled_job"
    NOTIFICATION = "notification"
    TRADING = "trading"


_CONFIRMATION_MAP: dict[AutonomousActionType, str] = {
    AutonomousActionType.FILE_WRITE: "AUTONOMY_REQUIRE_CONFIRMATION_WRITES",
    AutonomousActionType.PYTHON_EXEC: "AUTONOMY_REQUIRE_CONFIRMATION_EXEC",
    AutonomousActionType.WEB_SEARCH: "AUTONOMY_REQUIRE_CONFIRMATION_WRITES",
    AutonomousActionType.AUTOMATION: "AUTONOMY_REQUIRE_CONFIRMATION_EXEC",
    AutonomousActionType.SCHEDULED_JOB: "AUTONOMY_REQUIRE_CONFIRMATION_WRITES",
    AutonomousActionType.NOTIFICATION: "AUTONOMY_REQUIRE_CONFIRMATION_WRITES",
    AutonomousActionType.TRADING: "AUTONOMY_REQUIRE_CONFIRMATION_EXEC",
}


@dataclass(frozen=True)
class AutonomyPolicy:
    """Policy constraints for proactive behavior, tools, and confirmations."""

    proactive_level: ProactiveLevel = ProactiveLevel.OFF
    auto_tool_use: bool = False
    require_confirmation_writes: bool = True
    require_confirmation_exec: bool = True
    max_scheduled_jobs: int = 10

    @classmethod
    def from_settings(cls) -> AutonomyPolicy:
        """Build policy from environment-backed settings."""
        level_raw = AUTONOMY_PROACTIVE_LEVEL.lower()
        try:
            level = ProactiveLevel(level_raw)
        except ValueError:
            level = ProactiveLevel.OFF

        return cls(
            proactive_level=level,
            auto_tool_use=AUTONOMY_AUTO_TOOL_USE,
            require_confirmation_writes=AUTONOMY_REQUIRE_CONFIRMATION_WRITES,
            require_confirmation_exec=AUTONOMY_REQUIRE_CONFIRMATION_EXEC,
            max_scheduled_jobs=AUTONOMY_MAX_SCHEDULED_JOBS,
        )

    def should_surface_initiative(self) -> bool:
        """True when initiative suggestions may appear in prompts."""
        return self.proactive_level is not ProactiveLevel.OFF

    def initiative_max_suggestions(self) -> int:
        """Cap suggestions by proactive level."""
        caps = {
            ProactiveLevel.OFF: 0,
            ProactiveLevel.LOW: 1,
            ProactiveLevel.MEDIUM: 2,
            ProactiveLevel.HIGH: 3,
        }
        return caps[self.proactive_level]

    def allows_background_jobs(self) -> bool:
        """Background scheduling requires at least low proactive level."""
        return self.proactive_level in (
            ProactiveLevel.LOW,
            ProactiveLevel.MEDIUM,
            ProactiveLevel.HIGH,
        )

    def requires_confirmation(self, action_type: AutonomousActionType) -> bool:
        """Return True when the action type needs explicit user approval."""
        if action_type in (
            AutonomousActionType.FILE_WRITE,
            AutonomousActionType.WEB_SEARCH,
            AutonomousActionType.SCHEDULED_JOB,
            AutonomousActionType.NOTIFICATION,
        ):
            return self.require_confirmation_writes
        if action_type in (
            AutonomousActionType.PYTHON_EXEC,
            AutonomousActionType.AUTOMATION,
            AutonomousActionType.TRADING,
        ):
            return self.require_confirmation_exec
        return True

    def can_register_job(self, current_job_count: int) -> bool:
        """Enforce max scheduled jobs cap."""
        return current_job_count < self.max_scheduled_jobs
