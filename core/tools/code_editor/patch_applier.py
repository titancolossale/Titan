# =====================================
# Titan Patch Applier
# =====================================

"""Atomic apply / rollback for approved GeneratedPatch proposals."""

from __future__ import annotations

import json
import logging
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.tools.code_editor.exceptions import (
    CodeEditorConfigurationError,
    CodeEditorTransactionError,
)
from core.tools.code_editor.models import (
    BackupEntry,
    ChangeKind,
    PatchApplicationResult,
    PatchRollbackResult,
    PatchTransaction,
    PatchValidationResult,
    TransactionStatus,
)
from core.tools.code_editor.patch_validator import PatchValidator, content_hash
from tools.decision.patch_utils import apply_unified_diff

logger = logging.getLogger(__name__)

BACKUP_ROOT_NAME = ".titan"
BACKUP_DIR_NAME = "backups"
MANIFEST_NAME = "manifest.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PatchApplier:
    """Apply GeneratedPatch proposals with timestamped backups and rollback."""

    def __init__(
        self,
        workspace_root: Path,
        *,
        validator: PatchValidator | None = None,
        backup_root: Path | None = None,
    ) -> None:
        self._workspace_root = workspace_root.resolve()
        self._validator = validator or PatchValidator(self._workspace_root)
        if backup_root is not None:
            self._backup_root = backup_root.resolve()
        else:
            self._backup_root = self._workspace_root / BACKUP_ROOT_NAME / BACKUP_DIR_NAME

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    @property
    def backup_root(self) -> Path:
        return self._backup_root

    def apply(
        self,
        patch: Any,
        *,
        validation: PatchValidationResult | None = None,
    ) -> PatchApplicationResult:
        """Apply *patch* atomically after a clean validation and backup snapshot."""
        started = time.perf_counter()
        validation = validation or self._validator.validate(patch)
        if not validation.valid:
            logger.info(
                "patch_apply_rejected reason=validation_failed errors=%d",
                len(validation.errors) + len(validation.conflicts),
            )
            return PatchApplicationResult(
                success=False,
                status=TransactionStatus.FAILED,
                errors=tuple(
                    list(validation.errors) + list(validation.conflicts)
                )
                or ("Validation failed.",),
                warnings=validation.warnings,
                validation=validation,
                duration_seconds=time.perf_counter() - started,
                message="Patch application rejected — validation failed.",
            )

        transaction_id = uuid.uuid4().hex
        tx_dir = self._backup_root / transaction_id
        try:
            tx_dir.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise CodeEditorConfigurationError(
                f"Cannot create backup directory: {exc}"
            ) from exc

        now = _utc_now()
        transaction = PatchTransaction(
            transaction_id=transaction_id,
            workspace_root=str(self._workspace_root),
            status=TransactionStatus.PENDING,
            created_at=now,
            updated_at=now,
            plan_request=patch.plan_request,
            validation_valid=True,
        )
        self._write_manifest(tx_dir, transaction)

        logger.info(
            "patch_apply_start transaction_id=%s affected=%d",
            transaction_id,
            len(validation.affected_files),
        )

        backups: list[BackupEntry] = []
        files_created: list[str] = []
        files_modified: list[str] = []
        applied_paths: list[str] = []

        try:
            backups = self._create_backups(patch, tx_dir)
            transaction.backups = tuple(backups)
            transaction.updated_at = _utc_now()
            self._write_manifest(tx_dir, transaction)

            for generated in patch.files:
                path = generated.path.replace("\\", "/")
                resolved = self._validator.resolve_path(path)
                resolved.parent.mkdir(parents=True, exist_ok=True)
                resolved.write_text(generated.content, encoding="utf-8", newline="\n")
                files_created.append(path)
                applied_paths.append(path)

            for edit in patch.edits:
                path = edit.path.replace("\\", "/")
                resolved = self._validator.resolve_path(path)
                current = resolved.read_text(encoding="utf-8").replace("\r\n", "\n").replace(
                    "\r", "\n"
                )
                if edit.unified_diff.strip():
                    new_content = apply_unified_diff(current, edit.unified_diff)
                else:
                    new_content = edit.proposed_content
                resolved.write_text(new_content, encoding="utf-8", newline="\n")
                files_modified.append(path)
                applied_paths.append(path)

        except Exception as exc:  # noqa: BLE001 — convert to structured failure
            logger.warning(
                "patch_apply_failed transaction_id=%s error=%s — restoring",
                transaction_id,
                type(exc).__name__,
            )
            restore_errors = self._restore_from_backups(backups, tx_dir)
            transaction.status = TransactionStatus.FAILED
            transaction.files_created = tuple(files_created)
            transaction.files_modified = tuple(files_modified)
            transaction.errors = (f"{type(exc).__name__}: {exc}", *restore_errors)
            transaction.updated_at = _utc_now()
            self._write_manifest(tx_dir, transaction)
            return PatchApplicationResult(
                success=False,
                transaction_id=transaction_id,
                status=TransactionStatus.FAILED,
                files_created=tuple(files_created),
                files_modified=tuple(files_modified),
                errors=transaction.errors,
                warnings=validation.warnings,
                validation=validation,
                rollback_performed=True,
                duration_seconds=time.perf_counter() - started,
                message="Patch application failed — repository restored.",
            )

        transaction.status = TransactionStatus.APPLIED
        transaction.files_created = tuple(files_created)
        transaction.files_modified = tuple(files_modified)
        transaction.backups = tuple(backups)
        transaction.updated_at = _utc_now()
        self._write_manifest(tx_dir, transaction)

        duration = time.perf_counter() - started
        logger.info(
            "patch_apply_success transaction_id=%s created=%d modified=%d "
            "duration=%.3f",
            transaction_id,
            len(files_created),
            len(files_modified),
            duration,
        )
        return PatchApplicationResult(
            success=True,
            transaction_id=transaction_id,
            status=TransactionStatus.APPLIED,
            files_created=tuple(files_created),
            files_modified=tuple(files_modified),
            validation=validation,
            rollback_performed=False,
            duration_seconds=duration,
            message="Patch applied successfully.",
        )

    def rollback(self, transaction_id: str) -> PatchRollbackResult:
        """Restore the exact pre-application state for *transaction_id*."""
        started = time.perf_counter()
        cleaned_id = transaction_id.strip()
        if not cleaned_id or "/" in cleaned_id or "\\" in cleaned_id:
            return PatchRollbackResult(
                success=False,
                transaction_id=cleaned_id,
                errors=("Invalid transaction id.",),
                duration_seconds=time.perf_counter() - started,
                message="Rollback rejected — invalid transaction id.",
            )

        tx_dir = self._backup_root / cleaned_id
        try:
            transaction = self._load_manifest(tx_dir)
        except CodeEditorTransactionError as exc:
            return PatchRollbackResult(
                success=False,
                transaction_id=cleaned_id,
                errors=(str(exc),),
                duration_seconds=time.perf_counter() - started,
                message="Rollback rejected — transaction not found.",
            )

        if transaction.status == TransactionStatus.ROLLED_BACK:
            return PatchRollbackResult(
                success=True,
                transaction_id=cleaned_id,
                status=TransactionStatus.ROLLED_BACK,
                duration_seconds=time.perf_counter() - started,
                message="Transaction already rolled back.",
            )

        if transaction.status not in {
            TransactionStatus.APPLIED,
            TransactionStatus.FAILED,
        }:
            return PatchRollbackResult(
                success=False,
                transaction_id=cleaned_id,
                status=transaction.status,
                errors=(
                    f"Cannot rollback transaction in status {transaction.status.value}.",
                ),
                duration_seconds=time.perf_counter() - started,
                message="Rollback rejected — invalid transaction status.",
            )

        logger.info("patch_rollback_start transaction_id=%s", cleaned_id)
        try:
            restored, removed = self._restore_transaction(transaction, tx_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "patch_rollback_failed transaction_id=%s error=%s",
                cleaned_id,
                type(exc).__name__,
            )
            return PatchRollbackResult(
                success=False,
                transaction_id=cleaned_id,
                status=transaction.status,
                errors=(f"{type(exc).__name__}: {exc}",),
                duration_seconds=time.perf_counter() - started,
                message="Rollback failed.",
            )

        transaction.status = TransactionStatus.ROLLED_BACK
        transaction.updated_at = _utc_now()
        self._write_manifest(tx_dir, transaction)

        duration = time.perf_counter() - started
        logger.info(
            "patch_rollback_success transaction_id=%s restored=%d removed=%d "
            "duration=%.3f",
            cleaned_id,
            len(restored),
            len(removed),
            duration,
        )
        return PatchRollbackResult(
            success=True,
            transaction_id=cleaned_id,
            status=TransactionStatus.ROLLED_BACK,
            files_restored=tuple(restored),
            files_removed=tuple(removed),
            duration_seconds=duration,
            message="Rollback completed successfully.",
        )

    def _create_backups(
        self,
        patch: Any,
        tx_dir: Path,
    ) -> list[BackupEntry]:
        backups: list[BackupEntry] = []
        files_dir = tx_dir / "files"
        files_dir.mkdir(parents=True, exist_ok=True)

        for generated in patch.files:
            path = generated.path.replace("\\", "/")
            resolved = self._validator.resolve_path(path)
            backups.append(
                BackupEntry(
                    path=path,
                    kind=ChangeKind.CREATE,
                    backup_relative=None,
                    existed_before=resolved.exists(),
                    content_hash_before=(
                        content_hash(resolved.read_text(encoding="utf-8"))
                        if resolved.is_file()
                        else None
                    ),
                )
            )

        for edit in patch.edits:
            path = edit.path.replace("\\", "/")
            resolved = self._validator.resolve_path(path)
            if not resolved.is_file():
                raise FileNotFoundError(f"Missing file for backup: {path}")
            safe_name = path.replace("/", "__").replace("\\", "__")
            backup_rel = f"files/{safe_name}"
            backup_path = tx_dir / backup_rel
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(resolved, backup_path)
            backups.append(
                BackupEntry(
                    path=path,
                    kind=ChangeKind.MODIFY,
                    backup_relative=backup_rel,
                    existed_before=True,
                    content_hash_before=content_hash(
                        resolved.read_text(encoding="utf-8")
                    ),
                )
            )
        return backups

    def _restore_from_backups(
        self,
        backups: list[BackupEntry],
        tx_dir: Path,
    ) -> tuple[str, ...]:
        errors: list[str] = []
        # Reverse order so creates are removed after modifies restored
        for entry in reversed(backups):
            try:
                resolved = self._validator.resolve_path(entry.path)
                if entry.kind == ChangeKind.CREATE:
                    if resolved.exists():
                        resolved.unlink()
                    continue
                if entry.backup_relative:
                    backup_path = tx_dir / entry.backup_relative
                    if backup_path.is_file():
                        resolved.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(backup_path, resolved)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Restore failed for {entry.path}: {exc}")
        return tuple(errors)

    def _restore_transaction(
        self,
        transaction: PatchTransaction,
        tx_dir: Path,
    ) -> tuple[list[str], list[str]]:
        restored: list[str] = []
        removed: list[str] = []
        for entry in reversed(transaction.backups):
            resolved = self._validator.resolve_path(entry.path)
            if entry.kind == ChangeKind.CREATE or not entry.existed_before:
                if resolved.exists():
                    resolved.unlink()
                    removed.append(entry.path)
                continue
            if entry.backup_relative:
                backup_path = tx_dir / entry.backup_relative
                if not backup_path.is_file():
                    raise CodeEditorTransactionError(
                        f"Missing backup file for {entry.path}"
                    )
                resolved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_path, resolved)
                restored.append(entry.path)
        return restored, removed

    def _write_manifest(self, tx_dir: Path, transaction: PatchTransaction) -> None:
        manifest_path = tx_dir / MANIFEST_NAME
        # Manifest stores paths/hashes/status only — never source contents or secrets.
        payload = transaction.to_dict()
        with manifest_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)

    def _load_manifest(self, tx_dir: Path) -> PatchTransaction:
        manifest_path = tx_dir / MANIFEST_NAME
        if not manifest_path.is_file():
            raise CodeEditorTransactionError(
                f"Transaction manifest not found: {tx_dir.name}"
            )
        try:
            with manifest_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise CodeEditorTransactionError(
                f"Cannot read transaction manifest: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise CodeEditorTransactionError("Corrupt transaction manifest.")
        return PatchTransaction.from_dict(data)
