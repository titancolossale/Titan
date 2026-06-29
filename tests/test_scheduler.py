# =====================================
# Titan Scheduler Tests
# =====================================

"""Tests for Phase 9 scheduler (P9-042)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from brain.autonomy_policy import AutonomyPolicy
from core.job_models import JobStatus, JobType, RecurrenceType
from core.job_store import JobStore
from core.scheduler import Scheduler


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def test_register_and_list_jobs(tmp_path: Path) -> None:
    """Jobs persist and can be listed by user."""
    store = JobStore(file_path=tmp_path / "jobs.json")
    scheduler = Scheduler(store=store)
    at = _utc(2026, 6, 28, 10)

    job = scheduler.register_job(
        JobType.REMINDER,
        "Revoir la mission",
        at,
        user="Nolan",
        payload={"message": "Checkpoint"},
    )

    assert job is not None
    jobs = scheduler.list_jobs(user="Nolan", status=JobStatus.PENDING)
    assert len(jobs) == 1
    assert jobs[0].title == "Revoir la mission"


def test_due_jobs_with_fake_clock(tmp_path: Path) -> None:
    """Only pending jobs at or before clock time are due."""
    store = JobStore(file_path=tmp_path / "jobs.json")
    now = _utc(2026, 6, 28, 12)
    scheduler = Scheduler(store=store, clock=lambda: now)

    scheduler.register_job(
        JobType.REMINDER,
        "Past",
        _utc(2026, 6, 28, 11),
    )
    scheduler.register_job(
        JobType.REMINDER,
        "Future",
        _utc(2026, 6, 28, 13),
    )

    due = scheduler.due_jobs(now)
    assert len(due) == 1
    assert due[0].title == "Past"


def test_job_cap_blocks_registration(tmp_path: Path) -> None:
    """Policy max_scheduled_jobs prevents runaway scheduling."""
    store = JobStore(file_path=tmp_path / "jobs.json")
    policy = AutonomyPolicy(max_scheduled_jobs=1)
    scheduler = Scheduler(store=store, policy=policy)
    at = _utc(2026, 6, 28, 10)

    first = scheduler.register_job(JobType.REMINDER, "One", at)
    second = scheduler.register_job(JobType.REMINDER, "Two", at)

    assert first is not None
    assert second is None


def test_interval_recurrence_reschedules(tmp_path: Path) -> None:
    """Interval jobs reschedule after advance_recurrence."""
    store = JobStore(file_path=tmp_path / "jobs.json")
    scheduler = Scheduler(store=store)
    start = _utc(2026, 6, 28, 10)

    job = scheduler.register_job(
        JobType.REMINDER,
        "Recurring",
        start,
        recurrence=RecurrenceType.INTERVAL_SECONDS,
        recurrence_value="3600",
    )
    assert job is not None

    scheduler.advance_recurrence(job, start)
    updated = store.get_job(job.job_id)
    assert updated is not None
    assert updated.status is JobStatus.PENDING
    assert updated.run_count == 1

    next_at = datetime.fromisoformat(updated.scheduled_at)
    assert next_at == start + timedelta(seconds=3600)
