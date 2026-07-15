# =====================================
# Titan Tool Decision — Rollback Manager
# =====================================

"""Persistent rollback history and workspace restore (Phase 12 Batch 2 — P12B2-001)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config.settings import PROJECT_ROOT, ROLLBACK_HISTORY_PATH
from tools.decision.rollback_models import (
    FileContentSnapshot,
    RollbackAuditEntry,
    RollbackResult,
    RollbackSnapshot,
)
from tools.decision.patch_preview import read_file_safe
from tools.tool_enums import RiskLevel

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_schema() -> dict:
    """Return empty rollback history document."""
    return {"schema_version": SCHEMA_VERSION, "snapshots": [], "audit": []}


class RollbackManager:
    """Store successful patch snapshots and restore previous workspace versions."""

    def __init__(
        self,
        *,
        project_root: Path,
        file_path: Path | None = None,
        persist: bool = True,
    ) -> None:
        self._project_root = project_root.resolve()
        self._file_path = (file_path or ROLLBACK_HISTORY_PATH).resolve()
        self._persist = persist
        self._data = self._load()

    def record_snapshot(
        self,
        *,
        patch_id: str,
        confirmation_token: str,
        risk_level: RiskLevel,
        files_modified: tuple[str, ...],
        files_created: tuple[str, ...],
        file_contents: dict[str, tuple[str | None, str | None]],
    ) -> RollbackSnapshot:
        """Persist a snapshot after a successful patch application (P12B2-002)."""
        rollback_id = uuid.uuid4().hex[:12]
        snapshots = tuple(
            FileContentSnapshot(
                path=path,
                original_content=original,
                new_content=new,
            )
            for path, (original, new) in file_contents.items()
        )
        entry = RollbackSnapshot(
            rollback_id=rollback_id,
            patch_id=patch_id,
            timestamp=_utc_now_iso(),
            files_modified=files_modified,
            files_created=files_created,
            file_snapshots=snapshots,
            confirmation_token=confirmation_token,
            risk_level=risk_level,
        )
        self._data.setdefault("snapshots", []).append(entry.to_dict())
        self._append_audit("snapshot_created", rollback_id, f"patch_id={patch_id}")
        self._save()
        return entry

    def get_snapshot(self, rollback_id: str) -> RollbackSnapshot | None:
        """Return snapshot by id, skipping entries removed from persistence."""
        for raw in reversed(self._data.get("snapshots", [])):
            if raw.get("rollback_id") == rollback_id:
                return RollbackSnapshot.from_dict(raw)
        return None

    def get_latest_snapshot(self) -> RollbackSnapshot | None:
        """Return the most recent snapshot that has not been rolled back."""
        for raw in reversed(self._data.get("snapshots", [])):
            if raw.get("rolled_back"):
                continue
            return RollbackSnapshot.from_dict(raw)
        return None

    def list_history(self) -> list[RollbackSnapshot]:
        """Return all snapshots in chronological order."""
        return [
            RollbackSnapshot.from_dict(item)
            for item in self._data.get("snapshots", [])
        ]

    def history_size(self) -> int:
        """Return count of stored snapshots."""
        return len(self._data.get("snapshots", []))

    def list_history_summary(self) -> list[dict]:
        """Return lightweight history for Brain and ToolRuntime exposure (P12B2-006)."""
        return [
            {
                "rollback_id": item.rollback_id,
                "patch_id": item.patch_id,
                "timestamp": item.timestamp,
                "files_modified": list(item.files_modified),
                "files_created": list(item.files_created),
                "risk_level": item.risk_level.value,
                "rolled_back": item.rolled_back,
            }
            for item in self.list_history()
        ]

    def audit_entries(self) -> list[RollbackAuditEntry]:
        """Return append-only rollback audit trail (P12B2-004)."""
        return [
            RollbackAuditEntry.from_dict(item)
            for item in self._data.get("audit", [])
        ]

    def restore(
        self,
        rollback_id: str,
        *,
        confirmed: bool,
    ) -> RollbackResult:
        """Restore workspace files from a snapshot (P12B2-003, P12B2-004)."""
        history_size = self.history_size()
        if not confirmed:
            return RollbackResult(
                applied=False,
                rollback_id=rollback_id,
                files_restored=(),
                files_removed=(),
                errors=("Confirmation explicite requise — rollback non appliqué.",),
                rollback_history_size=history_size,
            )

        snapshot = self.get_snapshot(rollback_id)
        if snapshot is None:
            return RollbackResult(
                applied=False,
                rollback_id=rollback_id,
                files_restored=(),
                files_removed=(),
                errors=(f"Snapshot rollback introuvable ou supprimé: {rollback_id}",),
                rollback_history_size=history_size,
            )

        validation_errors = self._validate_snapshot(snapshot)
        if validation_errors:
            return RollbackResult(
                applied=False,
                rollback_id=rollback_id,
                files_restored=(),
                files_removed=(),
                errors=tuple(validation_errors),
                rollback_history_size=history_size,
            )

        files_restored: list[str] = []
        files_removed: list[str] = []

        try:
            for file_snap in snapshot.file_snapshots:
                path_error = self._validate_path(file_snap.path)
                if path_error:
                    raise ValueError(f"{file_snap.path}: {path_error}")

                target = self._project_root / file_snap.path
                if file_snap.original_content is None:
                    if target.is_file():
                        target.unlink()
                        files_removed.append(file_snap.path)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(file_snap.original_content, encoding="utf-8")
                    files_restored.append(file_snap.path)
        except OSError as exc:
            logger.exception("Rollback restore failed for %s", rollback_id)
            return RollbackResult(
                applied=False,
                rollback_id=rollback_id,
                files_restored=tuple(files_restored),
                files_removed=tuple(files_removed),
                errors=(f"Échec restauration rollback: {exc}",),
                rollback_history_size=history_size,
            )

        self._mark_rolled_back(rollback_id)
        self._append_audit(
            "rollback_applied",
            rollback_id,
            f"restored={len(files_restored)} removed={len(files_removed)}",
        )
        self._save()

        return RollbackResult(
            applied=True,
            rollback_id=rollback_id,
            files_restored=tuple(files_restored),
            files_removed=tuple(files_removed),
            errors=(),
            rollback_history_size=self.history_size(),
        )

    def capture_file_contents(
        self,
        rel_paths: tuple[str, ...],
        *,
        backups: dict[str, str | None],
        new_contents: dict[str, str],
    ) -> dict[str, tuple[str | None, str | None]]:
        """Build file content map from pre-patch backups and post-patch reads."""
        contents: dict[str, tuple[str | None, str | None]] = {}
        for path in rel_paths:
            original = backups.get(path)
            if path in new_contents:
                new = new_contents[path]
            else:
                new = read_file_safe(self._project_root, path)
            contents[path] = (original, new)
        return contents

    def _validate_snapshot(self, snapshot: RollbackSnapshot) -> list[str]:
        """Validate snapshot integrity before restore."""
        errors: list[str] = []
        if not snapshot.file_snapshots:
            errors.append("Snapshot vide — aucun fichier à restaurer.")
        for file_snap in snapshot.file_snapshots:
            path_error = self._validate_path(file_snap.path)
            if path_error:
                errors.append(f"{file_snap.path}: {path_error}")
        return errors

    def _validate_path(self, rel_path: str) -> str | None:
        """Return error when path would escape workspace."""
        if not rel_path or rel_path.strip() != rel_path:
            return "chemin invalide"
        normalized = rel_path.replace("\\", "/")
        if normalized.startswith("/") or ".." in normalized.split("/"):
            return "traversée de chemin interdite"
        target = (self._project_root / normalized).resolve()
        try:
            target.relative_to(self._project_root)
        except ValueError:
            return "restauration hors workspace interdite"
        return None

    def _mark_rolled_back(self, rollback_id: str) -> None:
        for item in self._data.get("snapshots", []):
            if item.get("rollback_id") == rollback_id:
                item["rolled_back"] = True
                break

    def _append_audit(self, event: str, rollback_id: str, detail: str = "") -> None:
        self._data.setdefault("audit", []).append(
            RollbackAuditEntry(
                event=event,
                rollback_id=rollback_id,
                timestamp=_utc_now_iso(),
                detail=detail,
            ).to_dict(),
        )

    def _load(self) -> dict:
        if not self._persist or not self._file_path.exists():
            return default_schema()
        try:
            with self._file_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Rollback history load failed (%s): %s", self._file_path, exc)
            return default_schema()
        if not isinstance(data, dict):
            return default_schema()
        data.setdefault("schema_version", SCHEMA_VERSION)
        data.setdefault("snapshots", [])
        data.setdefault("audit", [])
        return data

    def _save(self) -> None:
        if not self._persist:
            return
        try:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            with self._file_path.open("w", encoding="utf-8") as file:
                json.dump(self._data, file, indent=4, ensure_ascii=False)
        except OSError as exc:
            logger.error("Rollback history save failed: %s", exc)

    def clear(self) -> None:
        """Reset in-memory history (tests only)."""
        self._data = default_schema()
        if self._persist and self._file_path.exists():
            self._file_path.unlink(missing_ok=True)


_managers: dict[str, RollbackManager] = {}


def get_rollback_manager(
    project_root: Path | None = None,
    *,
    file_path: Path | None = None,
    persist: bool = True,
) -> RollbackManager:
    """Return a RollbackManager scoped to project_root (P12B2-001)."""
    root = (project_root or PROJECT_ROOT).resolve()
    resolved_path = file_path or (root / "data" / "rollback_history.json")
    key = f"{root}|{resolved_path}|{persist}"
    if key not in _managers:
        _managers[key] = RollbackManager(
            project_root=root,
            file_path=resolved_path,
            persist=persist,
        )
    return _managers[key]


def clear_rollback_managers() -> None:
    """Clear cached managers (tests only)."""
    _managers.clear()
