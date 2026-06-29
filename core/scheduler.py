# =====================================
# Titan Scheduler
# =====================================

"""Cron-like local scheduler for autonomous jobs (Phase 9 — P9-042)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from brain.autonomy_policy import AutonomyPolicy
from core.job_models import JobStatus, JobType, RecurrenceType, ScheduledJob
from core.job_store import JobStore


ClockFn = Callable[[], datetime]


class Scheduler:
    """Register, query, and advance scheduled jobs with policy guardrails."""

    def __init__(
        self,
        store: JobStore | None = None,
        policy: AutonomyPolicy | None = None,
        clock: ClockFn | None = None,
    ) -> None:
        self._store = store or JobStore()
        self._policy = policy or AutonomyPolicy.from_settings()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def store(self) -> JobStore:
        return self._store

    def register_job(
        self,
        job_type: JobType,
        title: str,
        scheduled_at: datetime,
        *,
        payload: dict | None = None,
        user: str = "Nolan",
        project_id: str = "",
        recurrence: RecurrenceType = RecurrenceType.ONCE,
        recurrence_value: str = "",
        max_runs: int = 0,
    ) -> ScheduledJob | None:
        """Create a job if policy allows; return None when cap reached."""
        if not self._policy.can_register_job(self._store.count_active()):
            return None

        job = ScheduledJob(
            job_id=str(uuid.uuid4()),
            job_type=job_type,
            title=title.strip(),
            payload=payload or {},
            scheduled_at=scheduled_at.astimezone(timezone.utc).isoformat(),
            recurrence=recurrence,
            recurrence_value=recurrence_value,
            user=user,
            project_id=project_id,
            max_runs=max_runs,
        )
        return self._store.add_job(job)

    def cancel_job(self, job_id: str) -> bool:
        """Mark a job cancelled."""
        job = self._store.get_job(job_id)
        if job is None:
            return False
        job.status = JobStatus.CANCELLED
        self._store.update_job(job)
        return True

    def list_jobs(
        self,
        *,
        user: str | None = None,
        status: JobStatus | None = None,
    ) -> list[ScheduledJob]:
        """Filter jobs by user and/or status."""
        results = self._store.jobs
        if user:
            results = [job for job in results if job.user == user]
        if status:
            results = [job for job in results if job.status == status]
        return results

    def due_jobs(self, at_time: datetime | None = None) -> list[ScheduledJob]:
        """Return pending jobs whose scheduled_at is at or before at_time."""
        now = at_time or self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        due: list[ScheduledJob] = []
        for job in self._store.jobs:
            if job.status != JobStatus.PENDING:
                continue
            if not job.scheduled_at:
                continue
            scheduled = datetime.fromisoformat(job.scheduled_at)
            if scheduled.tzinfo is None:
                scheduled = scheduled.replace(tzinfo=timezone.utc)
            if scheduled <= now:
                due.append(job)
        return due

    def advance_recurrence(self, job: ScheduledJob, ran_at: datetime) -> None:
        """Reschedule recurring jobs or mark one-shot jobs completed."""
        job.run_count += 1
        job.last_run_at = ran_at.astimezone(timezone.utc).isoformat()

        if job.max_runs > 0 and job.run_count >= job.max_runs:
            job.status = JobStatus.COMPLETED
            self._store.update_job(job)
            return

        if job.recurrence is RecurrenceType.ONCE:
            job.status = JobStatus.COMPLETED
            self._store.update_job(job)
            return

        next_run = self._next_run_time(job, ran_at)
        if next_run is None:
            job.status = JobStatus.COMPLETED
        else:
            job.scheduled_at = next_run.astimezone(timezone.utc).isoformat()
            job.status = JobStatus.PENDING
        self._store.update_job(job)

    def _next_run_time(
        self,
        job: ScheduledJob,
        ran_at: datetime,
    ) -> datetime | None:
        """Compute next run for recurring jobs."""
        if job.recurrence is RecurrenceType.INTERVAL_SECONDS:
            try:
                seconds = int(job.recurrence_value)
            except ValueError:
                return None
            return ran_at + timedelta(seconds=seconds)

        if job.recurrence is RecurrenceType.DAILY:
            return ran_at + timedelta(days=1)

        return None
