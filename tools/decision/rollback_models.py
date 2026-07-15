# =====================================
# Titan Tool Decision — Rollback Models
# =====================================

"""Persistent rollback snapshot types (Phase 12 Batch 2 — P12B2-002)."""

from __future__ import annotations

from dataclasses import dataclass

from tools.tool_enums import RiskLevel


@dataclass(frozen=True)
class FileContentSnapshot:
    """Original and post-patch content for one workspace file."""

    path: str
    original_content: str | None
    new_content: str | None


@dataclass(frozen=True)
class RollbackSnapshot:
    """Persisted snapshot of a successfully applied patch (P12B2-002)."""

    rollback_id: str
    patch_id: str
    timestamp: str
    files_modified: tuple[str, ...]
    files_created: tuple[str, ...]
    file_snapshots: tuple[FileContentSnapshot, ...]
    confirmation_token: str
    risk_level: RiskLevel
    rolled_back: bool = False

    def to_dict(self) -> dict:
        """Serialize for JSON persistence."""
        return {
            "rollback_id": self.rollback_id,
            "patch_id": self.patch_id,
            "timestamp": self.timestamp,
            "files_modified": list(self.files_modified),
            "files_created": list(self.files_created),
            "file_snapshots": [
                {
                    "path": item.path,
                    "original_content": item.original_content,
                    "new_content": item.new_content,
                }
                for item in self.file_snapshots
            ],
            "confirmation_token": self.confirmation_token,
            "risk_level": self.risk_level.value,
            "rolled_back": self.rolled_back,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RollbackSnapshot:
        """Deserialize from persisted JSON."""
        snapshots = tuple(
            FileContentSnapshot(
                path=str(item["path"]),
                original_content=item.get("original_content"),
                new_content=item.get("new_content"),
            )
            for item in data.get("file_snapshots", [])
        )
        return cls(
            rollback_id=str(data["rollback_id"]),
            patch_id=str(data["patch_id"]),
            timestamp=str(data["timestamp"]),
            files_modified=tuple(data.get("files_modified", [])),
            files_created=tuple(data.get("files_created", [])),
            file_snapshots=snapshots,
            confirmation_token=str(data.get("confirmation_token", "")),
            risk_level=RiskLevel(data.get("risk_level", RiskLevel.SAFE.value)),
            rolled_back=bool(data.get("rolled_back", False)),
        )


@dataclass(frozen=True)
class RollbackResult:
    """Outcome of restoring a rollback snapshot (P12B2-001)."""

    applied: bool
    rollback_id: str
    files_restored: tuple[str, ...]
    files_removed: tuple[str, ...]
    errors: tuple[str, ...]
    rollback_history_size: int = 0

    def to_dict(self) -> dict:
        """Serialize for DecisionReport and logging."""
        return {
            "applied": self.applied,
            "rollback_id": self.rollback_id,
            "files_restored": list(self.files_restored),
            "files_removed": list(self.files_removed),
            "errors": list(self.errors),
            "rollback_history_size": self.rollback_history_size,
        }


@dataclass(frozen=True)
class RollbackAuditEntry:
    """Append-only rollback audit record (P12B2-004)."""

    event: str
    rollback_id: str
    timestamp: str
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "event": self.event,
            "rollback_id": self.rollback_id,
            "timestamp": self.timestamp,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RollbackAuditEntry:
        return cls(
            event=str(data.get("event", "")),
            rollback_id=str(data.get("rollback_id", "")),
            timestamp=str(data.get("timestamp", "")),
            detail=str(data.get("detail", "")),
        )
