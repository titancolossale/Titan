# =====================================
# Titan Tool Decision — Patch Application Engine
# =====================================

"""Apply approved ModificationPlan patches safely (Phase 12 — P12-001)."""

from __future__ import annotations

import uuid
from pathlib import Path

from tools.decision.modification_models import ModificationPlan, PatchPreview, _CORE_RUNTIME_PATHS
from tools.decision.patch_confirmation_gate import is_valid_patch_confirmation
from tools.decision.patch_models import PatchApplicationResult
from tools.decision.patch_preview import read_file_safe
from tools.decision.patch_utils import apply_unified_diff, is_binary_content
from tools.decision.rollback_manager import RollbackManager
from tools.tool_enums import RiskLevel

_BLOCKED_BASENAMES: frozenset[str] = frozenset({
    ".env",
    ".env.local",
    ".env.production",
    "credentials.json",
    "secrets.json",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
})

_BLOCKED_SUFFIXES: frozenset[str] = frozenset({
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".crt",
})


class PatchApplicationEngine:
    """Validate and apply approved workspace modification plans."""

    def __init__(
        self,
        *,
        project_root: Path,
        rollback_manager: RollbackManager | None = None,
    ) -> None:
        self._project_root = project_root.resolve()
        self._rollback_manager = rollback_manager

    def apply(
        self,
        plan: ModificationPlan,
        *,
        confirmed: bool,
        confirmation_message: str = "",
        confirmation_token: str = "",
        patch_id: str = "",
    ) -> PatchApplicationResult:
        """Apply plan only when explicitly confirmed (P12-002)."""
        if not confirmed or not is_valid_patch_confirmation(confirmation_message):
            return self._result(
                applied=False,
                confirmation_token=confirmation_token,
                risk_level=plan.estimated_risk,
                errors=("Confirmation explicite requise — patch non appliqué.",),
            )

        validation_errors = self._validate_plan(plan)
        if validation_errors:
            return self._result(
                applied=False,
                confirmation_token=confirmation_token,
                risk_level=plan.estimated_risk,
                errors=tuple(validation_errors),
            )

        warnings = self._collect_high_risk_warnings(plan)
        backups = self._create_backups(plan)
        files_modified: list[str] = []
        files_created: list[str] = []
        files_skipped: list[str] = []
        new_contents: dict[str, str] = {}
        effective_patch_id = patch_id or confirmation_token or uuid.uuid4().hex[:12]

        try:
            for preview in plan.patch_previews:
                outcome, content = self._apply_preview(preview)
                if content is not None:
                    new_contents[preview.path] = content
                if outcome == "skipped":
                    files_skipped.append(preview.path)
                elif outcome == "created":
                    files_created.append(preview.path)
                elif outcome == "modified":
                    files_modified.append(preview.path)
        except Exception as exc:
            self._rollback(backups)
            return self._result(
                applied=False,
                confirmation_token=confirmation_token,
                risk_level=plan.estimated_risk,
                files_modified=tuple(files_modified),
                files_created=tuple(files_created),
                files_skipped=tuple(files_skipped),
                errors=(f"Échec application patch — rollback effectué: {exc}",),
                rollback_available=True,
                warnings=tuple(warnings),
                patch_id=effective_patch_id,
            )

        rollback_id: str | None = None
        if self._rollback_manager is not None:
            all_paths = tuple(
                dict.fromkeys(
                    (*files_modified, *files_created, *files_skipped),
                ).keys(),
            )
            file_contents = self._rollback_manager.capture_file_contents(
                all_paths,
                backups=backups,
                new_contents=new_contents,
            )
            snapshot = self._rollback_manager.record_snapshot(
                patch_id=effective_patch_id,
                confirmation_token=confirmation_token,
                risk_level=plan.estimated_risk,
                files_modified=tuple(files_modified),
                files_created=tuple(files_created),
                file_contents=file_contents,
            )
            rollback_id = snapshot.rollback_id

        return self._result(
            applied=True,
            confirmation_token=confirmation_token,
            risk_level=plan.estimated_risk,
            files_modified=tuple(files_modified),
            files_created=tuple(files_created),
            files_skipped=tuple(files_skipped),
            rollback_available=rollback_id is not None,
            warnings=tuple(warnings),
            patch_id=effective_patch_id,
            rollback_id=rollback_id,
        )

    def _validate_plan(self, plan: ModificationPlan) -> list[str]:
        """Validate plan safety constraints before any write (P12-003)."""
        errors: list[str] = []

        if plan.ambiguous:
            errors.append("Plan ambigu — clarification requise avant application.")

        if plan.files_to_delete:
            errors.append(
                "Opérations de suppression interdites — le plan contient des fichiers à supprimer.",
            )

        if not plan.patch_previews:
            errors.append("Aucun aperçu de patch disponible — rien à appliquer.")

        seen: set[str] = set()
        for preview in plan.patch_previews:
            path_error = self._validate_path(preview.path)
            if path_error:
                errors.append(f"{preview.path}: {path_error}")
            seen.add(preview.path)

        for rel_path in plan.files_to_delete:
            path_error = self._validate_path(rel_path)
            if path_error:
                errors.append(f"{rel_path}: {path_error}")

        return errors

    def _validate_path(self, rel_path: str) -> str | None:
        """Return error message when path violates safety rules."""
        if not rel_path or rel_path.strip() != rel_path:
            return "chemin invalide"

        normalized = rel_path.replace("\\", "/")
        if normalized.startswith("/") or ".." in normalized.split("/"):
            return "traversée de chemin interdite"

        if self._is_blocked_file(normalized):
            return "fichier protégé — modification interdite"

        target = (self._project_root / normalized).resolve()
        try:
            target.relative_to(self._project_root)
        except ValueError:
            return "écriture hors workspace interdite"

        if target.is_file():
            try:
                raw = target.read_bytes()
            except OSError as exc:
                return f"lecture impossible: {exc}"
            if is_binary_content(raw):
                return "fichier binaire — écriture interdite"

        return None

    @staticmethod
    def _is_blocked_file(rel_path: str) -> bool:
        """Detect .env, credentials, and other protected paths."""
        parts = rel_path.lower().replace("\\", "/").split("/")
        basename = parts[-1]
        if basename in _BLOCKED_BASENAMES:
            return True
        if any(part == ".env" for part in parts):
            return True
        if any(basename.endswith(suffix) for suffix in _BLOCKED_SUFFIXES):
            return True
        if "credentials" in basename and basename.endswith(".json"):
            return True
        return False

    @staticmethod
    def _collect_high_risk_warnings(plan: ModificationPlan) -> list[str]:
        """Warn when core runtime files are in scope (P12-003)."""
        warnings: list[str] = []
        for preview in plan.patch_previews:
            if preview.path in _CORE_RUNTIME_PATHS:
                warnings.append(
                    f"ATTENTION: {preview.path} est un fichier runtime critique.",
                )
        if plan.estimated_risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            warnings.append(
                f"Risque estimé {plan.estimated_risk.value.upper()} — revue manuelle recommandée.",
            )
        return warnings

    def _create_backups(self, plan: ModificationPlan) -> dict[str, str | None]:
        """Snapshot affected files before mutation (P12-005)."""
        backups: dict[str, str | None] = {}
        for preview in plan.patch_previews:
            target = self._project_root / preview.path
            if target.is_file():
                backups[preview.path] = read_file_safe(self._project_root, preview.path)
            else:
                backups[preview.path] = None
        return backups

    def _apply_preview(self, preview: PatchPreview) -> tuple[str, str | None]:
        """Apply one patch preview. Returns (outcome, new_content)."""
        path_error = self._validate_path(preview.path)
        if path_error:
            raise ValueError(f"{preview.path}: {path_error}")

        target = self._project_root / preview.path
        original = read_file_safe(self._project_root, preview.path)
        proposed = apply_unified_diff(original, preview.unified_diff)

        if is_binary_content(proposed):
            raise ValueError(f"{preview.path}: contenu binaire interdit")

        existed = target.is_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(proposed, encoding="utf-8")

        if preview.change_type == "create" or not existed:
            return "created", proposed
        if proposed == original:
            return "skipped", proposed
        return "modified", proposed

    def _rollback(self, backups: dict[str, str | None]) -> None:
        """Restore pre-application file state (P12-005)."""
        for rel_path, content in backups.items():
            target = self._project_root / rel_path
            if content is None:
                if target.is_file():
                    target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

    @staticmethod
    def _result(
        *,
        applied: bool,
        confirmation_token: str,
        risk_level: RiskLevel,
        files_modified: tuple[str, ...] = (),
        files_created: tuple[str, ...] = (),
        files_skipped: tuple[str, ...] = (),
        errors: tuple[str, ...] = (),
        rollback_available: bool = False,
        warnings: tuple[str, ...] = (),
        patch_id: str = "",
        rollback_id: str | None = None,
    ) -> PatchApplicationResult:
        return PatchApplicationResult(
            applied=applied,
            files_modified=files_modified,
            files_created=files_created,
            files_skipped=files_skipped,
            errors=errors,
            rollback_available=rollback_available,
            confirmation_token=confirmation_token,
            risk_level=risk_level,
            warnings=warnings,
            patch_id=patch_id,
            rollback_id=rollback_id,
        )
