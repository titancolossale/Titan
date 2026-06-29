# =====================================
# Titan Job Models
# =====================================

"""Typed structures for scheduled autonomous jobs (Phase 9 — P9-040)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, TypeVar

E = TypeVar("E", bound=Enum)


class JobStatus(str, Enum):
    """Lifecycle state of a scheduled job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    """Supported job categories — extensible for future phases."""

    REMINDER = "reminder"
    MISSION_CHECKPOINT = "mission_checkpoint"
    PROACTIVE_CHECK = "proactive_check"
    CUSTOM = "custom"
    TRADING_MONITOR = "trading_monitor"
    NOTIFICATION = "notification"


class RecurrenceType(str, Enum):
    """Recurrence patterns for scheduled jobs."""

    ONCE = "once"
    INTERVAL_SECONDS = "interval_seconds"
    DAILY = "daily"


@dataclass
class ScheduledJob:
    """One schedulable unit of autonomous work."""

    job_id: str
    job_type: JobType
    title: str
    payload: dict[str, Any] = field(default_factory=dict)
    scheduled_at: str = ""
    recurrence: RecurrenceType = RecurrenceType.ONCE
    recurrence_value: str = ""
    status: JobStatus = JobStatus.PENDING
    user: str = "Nolan"
    project_id: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    last_run_at: str = ""
    run_count: int = 0
    max_runs: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["job_type"] = self.job_type.value
        data["recurrence"] = self.recurrence.value
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScheduledJob:
        def _enum(value: str, enum_cls: type[E], default: E) -> E:
            try:
                return enum_cls(value)
            except ValueError:
                return default

        return cls(
            job_id=str(data.get("job_id", "")),
            job_type=_enum(str(data.get("job_type", "")), JobType, JobType.CUSTOM),
            title=str(data.get("title", "")),
            payload=dict(data.get("payload", {})),
            scheduled_at=str(data.get("scheduled_at", "")),
            recurrence=_enum(
                str(data.get("recurrence", "")),
                RecurrenceType,
                RecurrenceType.ONCE,
            ),
            recurrence_value=str(data.get("recurrence_value", "")),
            status=_enum(str(data.get("status", "")), JobStatus, JobStatus.PENDING),
            user=str(data.get("user", "Nolan")),
            project_id=str(data.get("project_id", "")),
            created_at=str(data.get("created_at", "")),
            last_run_at=str(data.get("last_run_at", "")),
            run_count=int(data.get("run_count", 0)),
            max_runs=int(data.get("max_runs", 0)),
        )


@dataclass
class JobExecutionResult:
    """Outcome of a single job run."""

    job_id: str
    success: bool
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
