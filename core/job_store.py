# =====================================
# Titan Job Store
# =====================================

"""JSON persistence for scheduled jobs (Phase 9 — P9-041)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.settings import SCHEDULED_JOBS_PATH
from core.job_models import JobStatus, ScheduledJob

SCHEMA_VERSION = 1


def default_schema() -> dict[str, Any]:
    """Return empty scheduled jobs document."""
    return {"schema_version": SCHEMA_VERSION, "jobs": []}


class JobStore:
    """Load, save, and query scheduled jobs."""

    def __init__(self, file_path: str | Path | None = None) -> None:
        self.file_path = Path(file_path or SCHEDULED_JOBS_PATH)
        self._data = self.load()

    def load(self) -> dict[str, Any]:
        """Load jobs from disk."""
        if not self.file_path.exists():
            return default_schema()

        with self.file_path.open("r", encoding="utf-8") as file:
            raw = json.load(file)

        raw.setdefault("schema_version", SCHEMA_VERSION)
        raw.setdefault("jobs", [])
        return raw

    def save(self) -> None:
        """Persist jobs to disk."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with self.file_path.open("w", encoding="utf-8") as file:
            json.dump(self._data, file, indent=4, ensure_ascii=False)

    @property
    def jobs(self) -> list[ScheduledJob]:
        """Return all jobs as typed objects."""
        return [ScheduledJob.from_dict(item) for item in self._data.get("jobs", [])]

    def add_job(self, job: ScheduledJob) -> ScheduledJob:
        """Append a job and persist."""
        self._data.setdefault("jobs", []).append(job.to_dict())
        self.save()
        return job

    def update_job(self, job: ScheduledJob) -> None:
        """Replace a job by id."""
        jobs = self._data.get("jobs", [])
        for index, item in enumerate(jobs):
            if item.get("job_id") == job.job_id:
                jobs[index] = job.to_dict()
                self.save()
                return

    def get_job(self, job_id: str) -> ScheduledJob | None:
        """Find job by id."""
        for job in self.jobs:
            if job.job_id == job_id:
                return job
        return None

    def remove_job(self, job_id: str) -> bool:
        """Delete job by id; return True when removed."""
        jobs = self._data.get("jobs", [])
        filtered = [item for item in jobs if item.get("job_id") != job_id]
        if len(filtered) == len(jobs):
            return False
        self._data["jobs"] = filtered
        self.save()
        return True

    def count_active(self) -> int:
        """Count non-terminal jobs."""
        terminal = {JobStatus.COMPLETED, JobStatus.CANCELLED, JobStatus.FAILED}
        return sum(1 for job in self.jobs if job.status not in terminal)
