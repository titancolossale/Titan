# =====================================
# Titan Patch Validator
# =====================================

"""Validate GeneratedPatch proposals before controlled application."""

from __future__ import annotations

import hashlib
import logging
import re
import time
from pathlib import Path
from typing import Any

from core.tools.code_editor.models import (
    AffectedFileChange,
    ChangeKind,
    PatchValidationResult,
)
from tools.decision.patch_utils import apply_unified_diff, is_binary_content
from tools.path_guard import PathGuardError, resolve_allowed_path

logger = logging.getLogger(__name__)

_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")
_DIFF_FILE_HEADER = re.compile(r"^(---|\+\+\+) ")

_BLOCKED_BASENAMES: frozenset[str] = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        "credentials.json",
        "secrets.json",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
    }
)

_BLOCKED_SUFFIXES: frozenset[str] = frozenset(
    {
        ".pem",
        ".key",
        ".p12",
        ".pfx",
        ".crt",
    }
)


def content_hash(content: str | bytes) -> str:
    """Return a SHA-256 hex digest for text or bytes content.

    Text content is normalized to ``\\n`` newlines so Windows CRLF baselines
    compare equal to LF proposals used during generation.
    """
    if isinstance(content, bytes):
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            return hashlib.sha256(content).hexdigest()
        payload = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    else:
        payload = content.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def count_diff_stats(unified_diff: str) -> tuple[int, int]:
    """Count added and deleted content lines in a unified diff."""
    additions = 0
    deletions = 0
    for line in unified_diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


class PatchValidator:
    """Validate a GeneratedPatch against the configured workspace."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root.resolve()

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def validate(self, patch: Any) -> PatchValidationResult:
        """Run full pre-application validation without mutating the repository."""
        started = time.perf_counter()
        errors: list[str] = []
        warnings: list[str] = []
        conflicts: list[str] = []
        affected: list[AffectedFileChange] = []
        to_create: list[str] = []
        to_modify: list[str] = []
        to_delete: list[str] = []
        to_rename: list[str] = []

        logger.info(
            "patch_validation_start workspace=%s files=%d edits=%d",
            self._workspace_root,
            len(patch.files),
            len(patch.edits),
        )

        workspace_error = self._check_workspace_match(patch)
        if workspace_error:
            errors.append(workspace_error)

        if not patch.files and not patch.edits:
            errors.append("Patch contains no files or edits.")

        for generated in patch.files:
            change, file_errors, file_warnings, file_conflicts = self._validate_create(
                generated
            )
            errors.extend(file_errors)
            warnings.extend(file_warnings)
            conflicts.extend(file_conflicts)
            if change is not None:
                affected.append(change)
                to_create.append(change.path)

        for edit in patch.edits:
            change, file_errors, file_warnings, file_conflicts = self._validate_edit(edit)
            errors.extend(file_errors)
            warnings.extend(file_warnings)
            conflicts.extend(file_conflicts)
            if change is not None:
                affected.append(change)
                to_modify.append(change.path)

        # Deduplicate while preserving order
        to_create = list(dict.fromkeys(to_create))
        to_modify = list(dict.fromkeys(to_modify))

        valid = not errors and not conflicts
        duration = time.perf_counter() - started
        result = PatchValidationResult(
            valid=valid,
            errors=tuple(errors),
            warnings=tuple(warnings),
            affected_files=tuple(affected),
            files_to_create=tuple(to_create),
            files_to_modify=tuple(to_modify),
            files_to_delete=tuple(to_delete),
            files_to_rename=tuple(to_rename),
            conflicts=tuple(conflicts),
            workspace_root=str(self._workspace_root),
            duration_seconds=duration,
        )
        logger.info(
            "patch_validation_result valid=%s errors=%d conflicts=%d "
            "affected=%d duration=%.3f",
            result.valid,
            len(result.errors),
            len(result.conflicts),
            len(result.affected_files),
            duration,
        )
        return result

    def resolve_path(self, raw_path: str) -> Path:
        """Resolve a patch path inside the workspace or raise PathGuardError."""
        return resolve_allowed_path(raw_path, self._workspace_root, must_exist=False)

    def _check_workspace_match(self, patch: Any) -> str | None:
        sources = patch.sources or {}
        recorded = sources.get("workspace_root")
        if not recorded:
            return None
        try:
            recorded_root = Path(str(recorded)).resolve()
        except OSError:
            return f"Patch workspace_root is invalid: {recorded}"
        if recorded_root != self._workspace_root:
            return (
                "Patch workspace mismatch: generated against "
                f"{recorded_root}, current workspace is {self._workspace_root}."
            )
        return None

    def _validate_create(
        self,
        generated: Any,
    ) -> tuple[AffectedFileChange | None, list[str], list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        conflicts: list[str] = []
        path = generated.path.replace("\\", "/")

        try:
            resolved = self.resolve_path(path)
        except PathGuardError as exc:
            errors.append(str(exc))
            return None, errors, warnings, conflicts

        secret_error = self._secret_path_error(resolved)
        if secret_error:
            errors.append(secret_error)
            return None, errors, warnings, conflicts

        if is_binary_content(generated.content):
            errors.append(f"Binary content rejected for new file: {path}")
            return None, errors, warnings, conflicts

        if resolved.exists():
            conflicts.append(f"New file already exists (conflict): {path}")

        additions = generated.content.count("\n") + (
            1 if generated.content and not generated.content.endswith("\n") else 0
        )
        change = AffectedFileChange(
            path=path,
            kind=ChangeKind.CREATE,
            additions=additions,
            deletions=0,
            baseline_hash=None,
            current_hash=content_hash(resolved.read_text(encoding="utf-8"))
            if resolved.is_file()
            else None,
        )
        return change, errors, warnings, conflicts

    def _validate_edit(
        self,
        edit: Any,
    ) -> tuple[AffectedFileChange | None, list[str], list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        conflicts: list[str] = []
        path = edit.path.replace("\\", "/")

        try:
            resolved = self.resolve_path(path)
        except PathGuardError as exc:
            errors.append(str(exc))
            return None, errors, warnings, conflicts

        secret_error = self._secret_path_error(resolved)
        if secret_error:
            errors.append(secret_error)
            return None, errors, warnings, conflicts

        if not edit.unified_diff.strip():
            errors.append(f"Malformed patch: empty unified diff for {path}")
            return None, errors, warnings, conflicts

        if not self._looks_like_unified_diff(edit.unified_diff):
            errors.append(f"Malformed unified diff syntax for {path}")
            return None, errors, warnings, conflicts

        if not resolved.is_file():
            conflicts.append(f"Target file missing for edit: {path}")
            return None, errors, warnings, conflicts

        try:
            raw_bytes = resolved.read_bytes()
        except OSError as exc:
            errors.append(f"Cannot read {path}: {exc}")
            return None, errors, warnings, conflicts

        if is_binary_content(raw_bytes):
            errors.append(f"Binary file rejected: {path}")
            return None, errors, warnings, conflicts

        try:
            current = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"Binary or non-UTF-8 file rejected: {path}")
            return None, errors, warnings, conflicts

        current = current.replace("\r\n", "\n").replace("\r", "\n")
        original = edit.original_content.replace("\r\n", "\n").replace("\r", "\n")

        if is_binary_content(edit.original_content) or is_binary_content(
            edit.proposed_content
        ):
            errors.append(f"Binary content rejected for edit: {path}")
            return None, errors, warnings, conflicts

        baseline = content_hash(original)
        current_digest = content_hash(current)
        if baseline != current_digest:
            conflicts.append(
                f"Stale baseline / hash mismatch for {path}: "
                "file changed after patch generation."
            )

        try:
            applied = apply_unified_diff(current, edit.unified_diff)
        except Exception as exc:  # noqa: BLE001 — surface as validation conflict
            conflicts.append(f"Diff application conflict for {path}: {exc}")
            applied = None

        if applied is not None and baseline == current_digest:
            proposed = edit.proposed_content.replace("\r\n", "\n").replace("\r", "\n")
            if applied != proposed and proposed:
                warnings.append(
                    f"Applied diff for {path} differs from proposed_content; "
                    "using unified diff as source of truth."
                )

        additions, deletions = count_diff_stats(edit.unified_diff)
        change = AffectedFileChange(
            path=path,
            kind=ChangeKind.MODIFY,
            additions=additions,
            deletions=deletions,
            baseline_hash=baseline,
            current_hash=current_digest,
        )
        return change, errors, warnings, conflicts

    def _secret_path_error(self, resolved: Path) -> str | None:
        name = resolved.name.lower()
        if name in _BLOCKED_BASENAMES or resolved.suffix.lower() in _BLOCKED_SUFFIXES:
            return f"Secret or credential path blocked: {resolved.name}"
        return None

    def _looks_like_unified_diff(self, unified_diff: str) -> bool:
        lines = [line for line in unified_diff.splitlines() if line.strip()]
        if not lines:
            return False
        has_hunk = any(_HUNK_HEADER.match(line.strip()) for line in lines)
        has_headers = sum(1 for line in lines if _DIFF_FILE_HEADER.match(line)) >= 1
        has_ops = any(
            line.startswith("+") or line.startswith("-")
            for line in lines
            if not line.startswith("+++") and not line.startswith("---")
        )
        return bool(has_hunk or (has_headers and has_ops) or has_ops)
