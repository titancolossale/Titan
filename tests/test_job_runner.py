# =====================================
# Titan Job Runner Tests
# =====================================

"""Tests for Phase 9 job runner (P9-043)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.job_models import JobType
from core.job_runner import JobRunner
from core.job_store import JobStore
from core.scheduler import Scheduler


def test_job_runner_executes_due_reminder(tmp_path: Path) -> None:
    """Tick processes due reminder jobs once."""
    store = JobStore(file_path=tmp_path / "jobs.json")
    now = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)
    scheduler = Scheduler(store=store, clock=lambda: now)
    runner = JobRunner(scheduler, clock=lambda: now)

    scheduler.register_job(
        JobType.REMINDER,
        "Boire de l'eau",
        datetime(2026, 6, 28, 11, 0, tzinfo=timezone.utc),
        payload={"message": "Hydratation"},
    )

    results = runner.tick(now)

    assert len(results) == 1
    assert results[0].success is True
    assert "Hydratation" in results[0].message


def test_job_runner_respects_max_per_tick(tmp_path: Path) -> None:
    """Only max_jobs_per_tick jobs run in one tick."""
    store = JobStore(file_path=tmp_path / "jobs.json")
    now = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)
    scheduler = Scheduler(store=store, clock=lambda: now)
    runner = JobRunner(scheduler, clock=lambda: now, max_jobs_per_tick=1)

    for index in range(3):
        scheduler.register_job(
            JobType.REMINDER,
            f"Job {index}",
            datetime(2026, 6, 28, 11, 0, tzinfo=timezone.utc),
        )

    results = runner.tick(now)
    assert len(results) == 1
