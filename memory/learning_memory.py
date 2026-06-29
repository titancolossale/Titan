# =====================================
# Titan Learning Memory
# =====================================

"""Tracks outcomes of approaches to inform future recommendations (Phase 9 — P9-020)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from config.settings import LEARNING_MEMORY_PATH

SCHEMA_VERSION = 1


class LearningOutcome(str, Enum):
    """Result of an attempted approach."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass
class LearningRecord:
    """One learning entry — what was tried and whether it worked."""

    domain: str
    approach: str
    outcome: LearningOutcome
    context: str = ""
    user: str = ""
    project_id: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    record_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["outcome"] = self.outcome.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LearningRecord:
        outcome_raw = data.get("outcome", LearningOutcome.UNKNOWN.value)
        try:
            outcome = LearningOutcome(outcome_raw)
        except ValueError:
            outcome = LearningOutcome.UNKNOWN
        return cls(
            domain=str(data.get("domain", "")),
            approach=str(data.get("approach", "")),
            outcome=outcome,
            context=str(data.get("context", "")),
            user=str(data.get("user", "")),
            project_id=str(data.get("project_id", "")),
            timestamp=str(data.get("timestamp", "")),
            record_id=str(data.get("record_id", "")),
        )


def default_schema() -> dict[str, Any]:
    """Return empty learning memory document."""
    return {"schema_version": SCHEMA_VERSION, "records": []}


class LearningMemory:
    """JSON-backed store for approach outcomes and confidence scoring."""

    def __init__(self, file_path: str | Path | None = None) -> None:
        self.file_path = Path(file_path or LEARNING_MEMORY_PATH)
        self._data = self.load()

    def load(self) -> dict[str, Any]:
        """Load learning records from disk."""
        if not self.file_path.exists():
            return default_schema()

        with self.file_path.open("r", encoding="utf-8") as file:
            raw = json.load(file)

        if raw.get("schema_version") != SCHEMA_VERSION:
            raw["schema_version"] = SCHEMA_VERSION
            raw.setdefault("records", [])

        return raw

    def save(self) -> None:
        """Persist learning records to disk."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with self.file_path.open("w", encoding="utf-8") as file:
            json.dump(self._data, file, indent=4, ensure_ascii=False)

    @property
    def records(self) -> list[LearningRecord]:
        """Return all learning records."""
        return [
            LearningRecord.from_dict(item)
            for item in self._data.get("records", [])
        ]

    def record_outcome(
        self,
        domain: str,
        approach: str,
        outcome: LearningOutcome,
        *,
        context: str = "",
        user: str = "",
        project_id: str = "",
    ) -> LearningRecord:
        """Append a learning record and persist."""
        import uuid

        record = LearningRecord(
            domain=domain.strip(),
            approach=approach.strip(),
            outcome=outcome,
            context=context.strip(),
            user=user,
            project_id=project_id,
            record_id=str(uuid.uuid4()),
        )
        self._data.setdefault("records", []).append(record.to_dict())
        self.save()
        return record

    def get_records_for_domain(
        self,
        domain: str,
        *,
        user: str | None = None,
        project_id: str | None = None,
    ) -> list[LearningRecord]:
        """Filter records by domain and optional user/project scope."""
        domain_lower = domain.lower()
        results: list[LearningRecord] = []
        for record in self.records:
            if record.domain.lower() != domain_lower:
                continue
            if user and record.user and record.user != user:
                continue
            if project_id and record.project_id and record.project_id != project_id:
                continue
            results.append(record)
        return results

    def confidence_for_approach(
        self,
        domain: str,
        approach: str,
        *,
        user: str | None = None,
    ) -> float:
        """Return confidence score 0.0–1.0 based on historical outcomes."""
        approach_lower = approach.lower()
        matching = [
            record
            for record in self.get_records_for_domain(domain, user=user)
            if record.approach.lower() == approach_lower
        ]
        if not matching:
            return 0.5

        weights = {
            LearningOutcome.SUCCESS: 1.0,
            LearningOutcome.PARTIAL: 0.6,
            LearningOutcome.FAILURE: 0.0,
            LearningOutcome.UNKNOWN: 0.5,
        }
        total = sum(weights[record.outcome] for record in matching)
        return total / len(matching)

    def get_lessons(
        self,
        domain: str,
        *,
        user: str | None = None,
        limit: int = 5,
    ) -> list[str]:
        """Return human-readable lessons from recent records."""
        records = self.get_records_for_domain(domain, user=user)
        records.sort(key=lambda record: record.timestamp, reverse=True)
        lessons: list[str] = []
        for record in records[:limit]:
            label = {
                LearningOutcome.SUCCESS: "réussi",
                LearningOutcome.FAILURE: "échoué",
                LearningOutcome.PARTIAL: "partiel",
                LearningOutcome.UNKNOWN: "incertain",
            }[record.outcome]
            lessons.append(f"[{label}] {record.approach}")
        return lessons

    def format_for_prompt(
        self,
        domain: str,
        *,
        user: str | None = None,
        limit: int = 3,
    ) -> str:
        """Format recent lessons for prompt injection."""
        lessons = self.get_lessons(domain, user=user, limit=limit)
        if not lessons:
            return ""
        lines = ["Apprentissages récents :"]
        lines.extend(f"  - {lesson}" for lesson in lessons)
        return "\n".join(lines)
