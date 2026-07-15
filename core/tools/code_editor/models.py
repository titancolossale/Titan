# =====================================
# Titan Code Editor Models
# =====================================

"""Serializable models for Controlled Patch Application V1."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PatchRiskLevel(str, Enum):
    """Risk classification for a patch preview or application."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ChangeKind(str, Enum):
    """Kind of filesystem change a patch would produce."""

    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"
    RENAME = "rename"


class TransactionStatus(str, Enum):
    """Lifecycle status for a patch application transaction."""

    PENDING = "pending"
    APPLIED = "applied"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True)
class AffectedFileChange:
    """One file-level change implied by a GeneratedPatch."""

    path: str
    kind: ChangeKind
    additions: int = 0
    deletions: int = 0
    baseline_hash: str | None = None
    current_hash: str | None = None
    renamed_from: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind.value,
            "additions": self.additions,
            "deletions": self.deletions,
            "baseline_hash": self.baseline_hash,
            "current_hash": self.current_hash,
            "renamed_from": self.renamed_from,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AffectedFileChange:
        return cls(
            path=str(data.get("path") or ""),
            kind=ChangeKind(str(data.get("kind") or ChangeKind.MODIFY.value)),
            additions=int(data.get("additions") or 0),
            deletions=int(data.get("deletions") or 0),
            baseline_hash=data.get("baseline_hash"),
            current_hash=data.get("current_hash"),
            renamed_from=data.get("renamed_from"),
        )


@dataclass(frozen=True)
class PatchValidationResult:
    """Structured validation report for a GeneratedPatch (no mutation)."""

    valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    affected_files: tuple[AffectedFileChange, ...] = ()
    files_to_create: tuple[str, ...] = ()
    files_to_modify: tuple[str, ...] = ()
    files_to_delete: tuple[str, ...] = ()
    files_to_rename: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    workspace_root: str = ""
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "affected_files": [item.to_dict() for item in self.affected_files],
            "files_to_create": list(self.files_to_create),
            "files_to_modify": list(self.files_to_modify),
            "files_to_delete": list(self.files_to_delete),
            "files_to_rename": list(self.files_to_rename),
            "conflicts": list(self.conflicts),
            "workspace_root": self.workspace_root,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PatchValidationResult:
        return cls(
            valid=bool(data.get("valid")),
            errors=tuple(data.get("errors") or ()),
            warnings=tuple(data.get("warnings") or ()),
            affected_files=tuple(
                AffectedFileChange.from_dict(item)
                for item in (data.get("affected_files") or [])
                if isinstance(item, dict)
            ),
            files_to_create=tuple(data.get("files_to_create") or ()),
            files_to_modify=tuple(data.get("files_to_modify") or ()),
            files_to_delete=tuple(data.get("files_to_delete") or ()),
            files_to_rename=tuple(data.get("files_to_rename") or ()),
            conflicts=tuple(data.get("conflicts") or ()),
            workspace_root=str(data.get("workspace_root") or ""),
            duration_seconds=float(data.get("duration_seconds") or 0.0),
        )


@dataclass(frozen=True)
class PatchPreview:
    """Human-readable preview of a GeneratedPatch (no mutation)."""

    affected_files: tuple[str, ...] = ()
    additions: int = 0
    deletions: int = 0
    new_files: tuple[str, ...] = ()
    removed_files: tuple[str, ...] = ()
    renamed_files: tuple[str, ...] = ()
    conflict_warnings: tuple[str, ...] = ()
    risk_level: PatchRiskLevel = PatchRiskLevel.MEDIUM
    change_summary: str = ""
    validation: PatchValidationResult | None = None
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "affected_files": list(self.affected_files),
            "additions": self.additions,
            "deletions": self.deletions,
            "new_files": list(self.new_files),
            "removed_files": list(self.removed_files),
            "renamed_files": list(self.renamed_files),
            "conflict_warnings": list(self.conflict_warnings),
            "risk_level": self.risk_level.value,
            "change_summary": self.change_summary,
            "validation": self.validation.to_dict() if self.validation else None,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PatchPreview:
        raw_validation = data.get("validation")
        return cls(
            affected_files=tuple(data.get("affected_files") or ()),
            additions=int(data.get("additions") or 0),
            deletions=int(data.get("deletions") or 0),
            new_files=tuple(data.get("new_files") or ()),
            removed_files=tuple(data.get("removed_files") or ()),
            renamed_files=tuple(data.get("renamed_files") or ()),
            conflict_warnings=tuple(data.get("conflict_warnings") or ()),
            risk_level=PatchRiskLevel(
                str(data.get("risk_level") or PatchRiskLevel.MEDIUM.value)
            ),
            change_summary=str(data.get("change_summary") or ""),
            validation=(
                PatchValidationResult.from_dict(raw_validation)
                if isinstance(raw_validation, dict)
                else None
            ),
            duration_seconds=float(data.get("duration_seconds") or 0.0),
        )


@dataclass(frozen=True)
class BackupEntry:
    """Manifest entry for one backed-up or newly created path."""

    path: str
    kind: ChangeKind
    backup_relative: str | None = None
    existed_before: bool = True
    content_hash_before: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind.value,
            "backup_relative": self.backup_relative,
            "existed_before": self.existed_before,
            "content_hash_before": self.content_hash_before,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackupEntry:
        return cls(
            path=str(data.get("path") or ""),
            kind=ChangeKind(str(data.get("kind") or ChangeKind.MODIFY.value)),
            backup_relative=data.get("backup_relative"),
            existed_before=bool(data.get("existed_before", True)),
            content_hash_before=data.get("content_hash_before"),
        )


@dataclass
class PatchTransaction:
    """Persistent transaction manifest for apply / rollback."""

    transaction_id: str
    workspace_root: str
    status: TransactionStatus
    created_at: str
    updated_at: str
    plan_request: str = ""
    backups: tuple[BackupEntry, ...] = ()
    files_created: tuple[str, ...] = ()
    files_modified: tuple[str, ...] = ()
    files_deleted: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    validation_valid: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "workspace_root": self.workspace_root,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "plan_request": self.plan_request,
            "backups": [item.to_dict() for item in self.backups],
            "files_created": list(self.files_created),
            "files_modified": list(self.files_modified),
            "files_deleted": list(self.files_deleted),
            "errors": list(self.errors),
            "validation_valid": self.validation_valid,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PatchTransaction:
        return cls(
            transaction_id=str(data.get("transaction_id") or ""),
            workspace_root=str(data.get("workspace_root") or ""),
            status=TransactionStatus(
                str(data.get("status") or TransactionStatus.PENDING.value)
            ),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            plan_request=str(data.get("plan_request") or ""),
            backups=tuple(
                BackupEntry.from_dict(item)
                for item in (data.get("backups") or [])
                if isinstance(item, dict)
            ),
            files_created=tuple(data.get("files_created") or ()),
            files_modified=tuple(data.get("files_modified") or ()),
            files_deleted=tuple(data.get("files_deleted") or ()),
            errors=tuple(data.get("errors") or ()),
            validation_valid=bool(data.get("validation_valid")),
        )


@dataclass(frozen=True)
class PatchApplicationResult:
    """Outcome of a controlled patch application attempt."""

    success: bool
    transaction_id: str | None = None
    status: TransactionStatus = TransactionStatus.FAILED
    files_created: tuple[str, ...] = ()
    files_modified: tuple[str, ...] = ()
    files_deleted: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    validation: PatchValidationResult | None = None
    rollback_performed: bool = False
    duration_seconds: float = 0.0
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "transaction_id": self.transaction_id,
            "status": self.status.value,
            "files_created": list(self.files_created),
            "files_modified": list(self.files_modified),
            "files_deleted": list(self.files_deleted),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "validation": self.validation.to_dict() if self.validation else None,
            "rollback_performed": self.rollback_performed,
            "duration_seconds": self.duration_seconds,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PatchApplicationResult:
        raw_validation = data.get("validation")
        return cls(
            success=bool(data.get("success")),
            transaction_id=data.get("transaction_id"),
            status=TransactionStatus(
                str(data.get("status") or TransactionStatus.FAILED.value)
            ),
            files_created=tuple(data.get("files_created") or ()),
            files_modified=tuple(data.get("files_modified") or ()),
            files_deleted=tuple(data.get("files_deleted") or ()),
            errors=tuple(data.get("errors") or ()),
            warnings=tuple(data.get("warnings") or ()),
            validation=(
                PatchValidationResult.from_dict(raw_validation)
                if isinstance(raw_validation, dict)
                else None
            ),
            rollback_performed=bool(data.get("rollback_performed")),
            duration_seconds=float(data.get("duration_seconds") or 0.0),
            message=str(data.get("message") or ""),
        )


@dataclass(frozen=True)
class PatchRollbackResult:
    """Outcome of restoring a prior patch transaction."""

    success: bool
    transaction_id: str
    status: TransactionStatus = TransactionStatus.FAILED
    files_restored: tuple[str, ...] = ()
    files_removed: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    duration_seconds: float = 0.0
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "transaction_id": self.transaction_id,
            "status": self.status.value,
            "files_restored": list(self.files_restored),
            "files_removed": list(self.files_removed),
            "errors": list(self.errors),
            "duration_seconds": self.duration_seconds,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PatchRollbackResult:
        return cls(
            success=bool(data.get("success")),
            transaction_id=str(data.get("transaction_id") or ""),
            status=TransactionStatus(
                str(data.get("status") or TransactionStatus.FAILED.value)
            ),
            files_restored=tuple(data.get("files_restored") or ()),
            files_removed=tuple(data.get("files_removed") or ()),
            errors=tuple(data.get("errors") or ()),
            duration_seconds=float(data.get("duration_seconds") or 0.0),
            message=str(data.get("message") or ""),
        )


@dataclass(frozen=True)
class PatchFileProposal:
    """Tool-local new-file proposal (mirrors GeneratedFile without Brain import)."""

    path: str
    content: str
    rationale: str = ""
    language: str = "python"
    confidence: float = 0.0


@dataclass(frozen=True)
class PatchEditProposal:
    """Tool-local edit proposal (mirrors GeneratedEdit without Brain import)."""

    path: str
    original_content: str
    proposed_content: str
    unified_diff: str
    rationale: str = ""
    symbols_touched: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True)
class PatchSummaryInfo:
    """Minimal summary fields needed for risk estimation."""

    request: str = ""
    change_type: str = "unknown"
    files_created: int = 0
    files_edited: int = 0
    review_count: int = 0
    confidence: float = 0.0
    complexity: str = "unknown"
    risk: str = "medium"
    requires_manual_review: bool = True
    notes: str = ""


@dataclass(frozen=True)
class ApplyablePatch:
    """Tool-local GeneratedPatch adapter — no Brain dependency."""

    plan_request: str
    files: tuple[PatchFileProposal, ...]
    edits: tuple[PatchEditProposal, ...]
    summary: PatchSummaryInfo = field(default_factory=PatchSummaryInfo)
    unified_diff_bundle: str = ""
    confidence: float = 0.0
    rationale: str = ""
    sources: dict[str, Any] = field(default_factory=dict)
    plan_approved: bool = False
    approved: bool = False
    review_items: tuple[Any, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_request": self.plan_request,
            "files": [
                {
                    "path": item.path,
                    "content": item.content,
                    "rationale": item.rationale,
                    "language": item.language,
                    "confidence": item.confidence,
                }
                for item in self.files
            ],
            "edits": [
                {
                    "path": item.path,
                    "original_content": item.original_content,
                    "proposed_content": item.proposed_content,
                    "unified_diff": item.unified_diff,
                    "rationale": item.rationale,
                    "symbols_touched": list(item.symbols_touched),
                    "confidence": item.confidence,
                }
                for item in self.edits
            ],
            "summary": {
                "request": self.summary.request,
                "change_type": self.summary.change_type,
                "files_created": self.summary.files_created,
                "files_edited": self.summary.files_edited,
                "review_count": self.summary.review_count,
                "confidence": self.summary.confidence,
                "complexity": self.summary.complexity,
                "risk": self.summary.risk,
                "requires_manual_review": self.summary.requires_manual_review,
                "notes": self.summary.notes,
            },
            "unified_diff_bundle": self.unified_diff_bundle,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "sources": dict(self.sources),
            "plan_approved": self.plan_approved,
            "approved": self.approved,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApplyablePatch:
        raw_summary = data.get("summary") or {}
        if not isinstance(raw_summary, dict):
            raw_summary = {}
        files = tuple(
            PatchFileProposal(
                path=str(item.get("path") or ""),
                content=str(item.get("content") or ""),
                rationale=str(item.get("rationale") or ""),
                language=str(item.get("language") or "python"),
                confidence=float(item.get("confidence") or 0.0),
            )
            for item in (data.get("files") or [])
            if isinstance(item, dict)
        )
        edits = tuple(
            PatchEditProposal(
                path=str(item.get("path") or ""),
                original_content=str(item.get("original_content") or ""),
                proposed_content=str(item.get("proposed_content") or ""),
                unified_diff=str(item.get("unified_diff") or ""),
                rationale=str(item.get("rationale") or ""),
                symbols_touched=tuple(item.get("symbols_touched") or ()),
                confidence=float(item.get("confidence") or 0.0),
            )
            for item in (data.get("edits") or [])
            if isinstance(item, dict)
        )
        summary = PatchSummaryInfo(
            request=str(raw_summary.get("request") or data.get("plan_request") or ""),
            change_type=str(raw_summary.get("change_type") or "unknown"),
            files_created=int(raw_summary.get("files_created") or len(files)),
            files_edited=int(raw_summary.get("files_edited") or len(edits)),
            review_count=int(raw_summary.get("review_count") or 0),
            confidence=float(
                raw_summary.get("confidence") or data.get("confidence") or 0.0
            ),
            complexity=str(raw_summary.get("complexity") or "unknown"),
            risk=str(raw_summary.get("risk") or "medium"),
            requires_manual_review=bool(
                raw_summary.get("requires_manual_review", True)
            ),
            notes=str(raw_summary.get("notes") or ""),
        )
        return cls(
            plan_request=str(data.get("plan_request") or ""),
            files=files,
            edits=edits,
            summary=summary,
            unified_diff_bundle=str(data.get("unified_diff_bundle") or ""),
            confidence=float(data.get("confidence") or 0.0),
            rationale=str(data.get("rationale") or ""),
            sources=dict(data.get("sources") or {}),
            plan_approved=bool(data.get("plan_approved")),
            approved=bool(data.get("approved")),
        )
