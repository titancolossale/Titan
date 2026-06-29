# =====================================
# Titan Job Runner
# =====================================

"""Executes due scheduled jobs through pluggable handlers (Phase 9 — P9-043)."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Callable

from core.job_models import JobExecutionResult, JobStatus, JobType, ScheduledJob
from core.scheduler import Scheduler

logger = logging.getLogger(__name__)

ClockFn = Callable[[], datetime]


class JobHandler(ABC):
    """Contract for domain-specific job execution."""

    @abstractmethod
    def can_handle(self, job: ScheduledJob) -> bool:
        """Return True when this handler supports the job type."""

    @abstractmethod
    def execute(self, job: ScheduledJob) -> JobExecutionResult:
        """Run the job and return structured outcome."""


class ReminderJobHandler(JobHandler):
    """Local reminder jobs — no external notification yet."""

    def can_handle(self, job: ScheduledJob) -> bool:
        return job.job_type in (JobType.REMINDER, JobType.NOTIFICATION)

    def execute(self, job: ScheduledJob) -> JobExecutionResult:
        message = job.payload.get("message", job.title)
        return JobExecutionResult(
            job_id=job.job_id,
            success=True,
            message=f"Rappel : {message}",
            details={"user": job.user},
        )


class MissionCheckpointHandler(JobHandler):
    """Mission checkpoint jobs — surface checkpoint prompt for Brain."""

    def can_handle(self, job: ScheduledJob) -> bool:
        return job.job_type is JobType.MISSION_CHECKPOINT

    def execute(self, job: ScheduledJob) -> JobExecutionResult:
        checkpoint = job.payload.get("checkpoint", job.title)
        return JobExecutionResult(
            job_id=job.job_id,
            success=True,
            message=f"Point de contrôle mission : {checkpoint}",
            details={"project_id": job.project_id},
        )


class DefaultJobHandler(JobHandler):
    """Fallback handler for custom and future job types."""

    def can_handle(self, job: ScheduledJob) -> bool:
        return True

    def execute(self, job: ScheduledJob) -> JobExecutionResult:
        return JobExecutionResult(
            job_id=job.job_id,
            success=True,
            message=f"Job exécuté : {job.title}",
            details={"job_type": job.job_type.value},
        )


class JobRunner:
    """Dispatch due jobs to registered handlers with lifecycle management."""

    def __init__(
        self,
        scheduler: Scheduler,
        handlers: list[JobHandler] | None = None,
        clock: ClockFn | None = None,
        max_jobs_per_tick: int = 5,
    ) -> None:
        self._scheduler = scheduler
        self._handlers = handlers or [
            ReminderJobHandler(),
            MissionCheckpointHandler(),
            DefaultJobHandler(),
        ]
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._max_jobs_per_tick = max_jobs_per_tick
        self._last_results: list[JobExecutionResult] = []

    @property
    def last_results(self) -> list[JobExecutionResult]:
        """Results from the most recent tick."""
        return list(self._last_results)

    def register_handler(self, handler: JobHandler) -> None:
        """Add a handler — first match wins."""
        self._handlers.insert(0, handler)

    def tick(self, at_time: datetime | None = None) -> list[JobExecutionResult]:
        """Process due jobs up to max_jobs_per_tick."""
        now = at_time or self._clock()
        due = self._scheduler.due_jobs(now)[: self._max_jobs_per_tick]
        results: list[JobExecutionResult] = []

        for job in due:
            job.status = JobStatus.RUNNING
            self._scheduler.store.update_job(job)

            handler = self._resolve_handler(job)
            try:
                result = handler.execute(job)
            except Exception as exc:
                logger.exception("Job %s failed: %s", job.job_id, exc)
                result = JobExecutionResult(
                    job_id=job.job_id,
                    success=False,
                    message=str(exc),
                )

            if result.success:
                self._scheduler.advance_recurrence(job, now)
            else:
                job.status = JobStatus.FAILED
                self._scheduler.store.update_job(job)

            results.append(result)

        self._last_results = results
        return results

    def _resolve_handler(self, job: ScheduledJob) -> JobHandler:
        for handler in self._handlers:
            if handler.can_handle(job):
                return handler
        return DefaultJobHandler()
