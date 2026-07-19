# =====================================
# Titan Request Deadline
# =====================================

"""Single wall-clock deadline for web chat — propagated through Brain stages."""

from __future__ import annotations

import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


class BrainTimeoutError(TimeoutError):
    """Raised when the global chat deadline is exhausted."""

    def __init__(
        self,
        message: str = "brain_timeout",
        *,
        last_completed_stage: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.last_completed_stage = last_completed_stage
        self.request_id = request_id


class RequestCancelledError(Exception):
    """Raised when the client abandons the in-flight chat request."""

    def __init__(
        self,
        message: str = "cancelled",
        *,
        last_completed_stage: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.last_completed_stage = last_completed_stage
        self.request_id = request_id


_deadline_var: ContextVar[RequestDeadline | None] = ContextVar(
    "titan_request_deadline",
    default=None,
)


@dataclass
class RequestDeadline:
    """One shared budget for API → Brain → provider work."""

    total_ms: int
    request_id: str
    started_monotonic: float = field(default_factory=time.monotonic)
    last_completed_stage: str = "received"
    cancel_event: threading.Event = field(default_factory=threading.Event)
    stage_timings_ms: dict[str, int] = field(default_factory=dict)

    @classmethod
    def start(cls, *, total_seconds: float, request_id: str) -> RequestDeadline:
        return cls(
            total_ms=max(1, int(round(total_seconds * 1000))),
            request_id=request_id,
        )

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started_monotonic) * 1000)

    def remaining_ms(self) -> int:
        return max(0, self.total_ms - self.elapsed_ms())

    def remaining_seconds(self) -> float:
        return self.remaining_ms() / 1000.0

    def mark_stage(self, stage: str) -> None:
        """Record stage completion and accumulate stage duration since last mark."""
        now_elapsed = self.elapsed_ms()
        previous = sum(self.stage_timings_ms.values())
        self.stage_timings_ms[stage] = max(0, now_elapsed - previous)
        self.last_completed_stage = stage

    def cancel(self) -> None:
        self.cancel_event.set()

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def check(self, stage: str | None = None) -> None:
        """Raise if cancelled or deadline exhausted."""
        if stage:
            self.last_completed_stage = stage
        if self.cancelled:
            raise RequestCancelledError(
                last_completed_stage=self.last_completed_stage,
                request_id=self.request_id,
            )
        if self.remaining_ms() <= 0:
            raise BrainTimeoutError(
                last_completed_stage=self.last_completed_stage,
                request_id=self.request_id,
            )

    def provider_timeout_seconds(self, *, configured: float, floor: float = 0.05) -> float:
        """Cap provider HTTP timeout to remaining budget (never nest beyond global)."""
        remaining = self.remaining_seconds()
        if remaining <= 0:
            return floor
        # Never return a timeout larger than the remaining global budget.
        return max(floor, min(float(configured), remaining)) if remaining >= floor else remaining

    def log_fields(self, **extra: Any) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "request_id": self.request_id,
            "elapsed_ms": self.elapsed_ms(),
            "remaining_budget_ms": self.remaining_ms(),
            "stage": self.last_completed_stage,
        }
        fields.update(extra)
        return fields


def get_request_deadline() -> RequestDeadline | None:
    return _deadline_var.get()


def set_request_deadline(deadline: RequestDeadline | None):
    """Bind deadline for the current context; return token for reset."""
    return _deadline_var.set(deadline)


def reset_request_deadline(token) -> None:
    _deadline_var.reset(token)


def check_deadline(stage: str | None = None) -> None:
    deadline = get_request_deadline()
    if deadline is not None:
        deadline.check(stage)
