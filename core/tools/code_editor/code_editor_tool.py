# =====================================
# Titan Code Editor Tool
# =====================================

"""Controlled Patch Application V1 — validate, preview, apply, rollback."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from config.settings import PROJECT_ROOT
from core.actions.action import Action
from core.actions.action_registry import ActionRegistry
from core.actions.action_result import ActionResult
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.tools.base_tool import BaseTool
from core.tools.code_editor.exceptions import (
    CodeEditorApprovalError,
    CodeEditorConfirmationError,
    CodeEditorError,
    CodeEditorPermissionDeniedError,
)
from core.tools.code_editor.models import (
    ApplyablePatch,
    PatchApplicationResult,
    PatchPreview,
    PatchRiskLevel,
    PatchRollbackResult,
    PatchValidationResult,
)
from core.tools.code_editor.patch_applier import PatchApplier
from core.tools.code_editor.patch_validator import PatchValidator, count_diff_stats

logger = logging.getLogger(__name__)

PERMISSION_VALIDATE = "code_editor.validate"
PERMISSION_PREVIEW = "code_editor.preview"
PERMISSION_APPLY = "code_editor.apply"
PERMISSION_ROLLBACK = "code_editor.rollback"

CAPABILITY_VALIDATE_PATCH = "validate_patch"
CAPABILITY_PREVIEW_PATCH = "preview_patch"
CAPABILITY_APPLY_PATCH = "apply_patch"
CAPABILITY_ROLLBACK_PATCH = "rollback_patch"

_CAPABILITY_PERMISSIONS: dict[str, str] = {
    CAPABILITY_VALIDATE_PATCH: PERMISSION_VALIDATE,
    CAPABILITY_PREVIEW_PATCH: PERMISSION_PREVIEW,
    CAPABILITY_APPLY_PATCH: PERMISSION_APPLY,
    CAPABILITY_ROLLBACK_PATCH: PERMISSION_ROLLBACK,
}

_ACTION_CAPABILITY_MAP: dict[str, str] = {
    "validate_patch": CAPABILITY_VALIDATE_PATCH,
    "preview_patch": CAPABILITY_PREVIEW_PATCH,
    "apply_patch": CAPABILITY_APPLY_PATCH,
    "rollback_patch": CAPABILITY_ROLLBACK_PATCH,
}

_DEFAULT_PERMISSIONS: tuple[Permission, ...] = (
    Permission(
        id=PERMISSION_VALIDATE,
        name="Validate Patch",
        description="Validate a GeneratedPatch without mutating the repository.",
        level=PermissionLevel.SAFE,
    ),
    Permission(
        id=PERMISSION_PREVIEW,
        name="Preview Patch",
        description="Preview a GeneratedPatch without mutating the repository.",
        level=PermissionLevel.SAFE,
    ),
    Permission(
        id=PERMISSION_APPLY,
        name="Apply Patch",
        description="Apply an approved GeneratedPatch after explicit confirmation.",
        level=PermissionLevel.CONFIRMATION_REQUIRED,
    ),
    Permission(
        id=PERMISSION_ROLLBACK,
        name="Rollback Patch",
        description="Restore a prior patch transaction after explicit confirmation.",
        level=PermissionLevel.CONFIRMATION_REQUIRED,
    ),
)

_PATCH_PARAMETER = {
    "patch": {
        "type": "object",
        "required": True,
        "description": "GeneratedPatch instance or serializable dict.",
    },
}

_CONFIRMED_PARAMETER = {
    "confirmed": {
        "type": "boolean",
        "required": False,
        "description": "Explicit human confirmation for mutating actions.",
    },
}


def _build_code_editor_actions(tool_id: str) -> tuple[Action, ...]:
    return (
        Action(
            id="validate_patch",
            name="Validate Patch",
            description="Validate a GeneratedPatch against the workspace.",
            tool_id=tool_id,
            permission_id=PERMISSION_VALIDATE,
            parameters=dict(_PATCH_PARAMETER),
            metadata={"capability": CAPABILITY_VALIDATE_PATCH},
        ),
        Action(
            id="preview_patch",
            name="Preview Patch",
            description="Preview additions, deletions, and risk for a GeneratedPatch.",
            tool_id=tool_id,
            permission_id=PERMISSION_PREVIEW,
            parameters=dict(_PATCH_PARAMETER),
            metadata={"capability": CAPABILITY_PREVIEW_PATCH},
        ),
        Action(
            id="apply_patch",
            name="Apply Patch",
            description=(
                "Apply an approved GeneratedPatch after explicit confirmation. "
                "Creates a reversible transaction under .titan/backups/."
            ),
            tool_id=tool_id,
            permission_id=PERMISSION_APPLY,
            parameters={**_PATCH_PARAMETER, **_CONFIRMED_PARAMETER},
            metadata={"capability": CAPABILITY_APPLY_PATCH},
        ),
        Action(
            id="rollback_patch",
            name="Rollback Patch",
            description="Restore the pre-application state for a transaction id.",
            tool_id=tool_id,
            permission_id=PERMISSION_ROLLBACK,
            parameters={
                "transaction_id": {
                    "type": "string",
                    "required": True,
                    "description": "Patch transaction id to restore.",
                },
                **_CONFIRMED_PARAMETER,
            },
            metadata={"capability": CAPABILITY_ROLLBACK_PATCH},
        ),
    )


class CodeEditorTool(BaseTool):
    """Controlled patch application tool for GeneratedPatch proposals.

    Never silently mutates the repository. Apply and rollback require both
    permission clearance and ``confirmed=True``. This tool is not part of Brain.
    """

    def __init__(
        self,
        *,
        workspace_root: Path | None = None,
        permission_manager: PermissionManager | None = None,
        action_registry: ActionRegistry | None = None,
        validator: PatchValidator | None = None,
        applier: PatchApplier | None = None,
    ) -> None:
        super().__init__()
        self._permission_manager = permission_manager or PermissionManager()
        self._register_default_permissions()

        root = (workspace_root or PROJECT_ROOT).resolve()
        self._workspace_root = root
        self._validator = validator or PatchValidator(root)
        self._applier = applier or PatchApplier(root, validator=self._validator)
        self._actions = _build_code_editor_actions(self.id)

        if action_registry is not None:
            self._register_actions(action_registry)

    @property
    def id(self) -> str:
        return "code_editor"

    @property
    def name(self) -> str:
        return "Code Editor"

    @property
    def description(self) -> str:
        return (
            "Validate, preview, apply, and rollback GeneratedPatch proposals "
            "with explicit confirmation, backups, and atomic restore."
        )

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def category(self) -> str:
        return "development"

    @property
    def requires_confirmation(self) -> bool:
        return True

    @property
    def capabilities(self) -> list[str]:
        return list(_CAPABILITY_PERMISSIONS.keys())

    @property
    def permission_manager(self) -> PermissionManager:
        return self._permission_manager

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def list_actions(self) -> list[Action]:
        return list(self._actions)

    def execute_action(self, action_id: str, **kwargs: object) -> ActionResult:
        registered_ids = {action.id for action in self._actions}
        if action_id not in registered_ids:
            message = f"Unsupported Code Editor action: {action_id}"
            logger.warning(message)
            return ActionResult(
                success=False,
                message=message,
                errors=[message],
                metadata={"action_id": action_id},
            )

        started = time.perf_counter()
        try:
            data = self._dispatch_action(action_id, **kwargs)
        except CodeEditorError as exc:
            message = str(exc)
            logger.warning(
                "code_editor_action_failed action=%s error=%s",
                action_id,
                message,
            )
            return ActionResult(
                success=False,
                message=message,
                errors=[message],
                execution_time=time.perf_counter() - started,
                metadata={"action_id": action_id},
            )
        except Exception as exc:
            message = str(exc)
            logger.exception(
                "code_editor_action_failed_unexpected action=%s error=%s",
                action_id,
                message,
            )
            return ActionResult(
                success=False,
                message=message,
                errors=[message],
                execution_time=time.perf_counter() - started,
                metadata={"action_id": action_id},
            )

        elapsed = time.perf_counter() - started
        success = bool(data.get("success", True))
        message = str(
            data.get(
                "message",
                f"Code Editor action '{action_id}' completed."
                if success
                else f"Code Editor action '{action_id}' failed.",
            )
        )
        return ActionResult(
            success=success,
            data=data,
            message=message,
            execution_time=elapsed,
            errors=list(data.get("errors") or []),
            metadata={"action_id": action_id, "capability": _ACTION_CAPABILITY_MAP.get(action_id)},
        )

    def execute(self, **kwargs: object) -> object:
        action_id = str(kwargs.pop("action", kwargs.pop("action_id", "validate_patch")))
        return self.execute_action(action_id, **kwargs)

    # --- Public API used by Brain facades ------------------------------------

    def validate_patch(self, patch: Any) -> PatchValidationResult:
        """Validate a GeneratedPatch without mutating the repository."""
        self._ensure_permission(PERMISSION_VALIDATE)
        generated = self._coerce_patch(patch)
        return self._validator.validate(generated)

    def preview_patch(self, patch: Any) -> PatchPreview:
        """Build a human-readable preview without mutating the repository."""
        self._ensure_permission(PERMISSION_PREVIEW)
        started = time.perf_counter()
        generated = self._coerce_patch(patch)
        validation = self._validator.validate(generated)

        additions = 0
        deletions = 0
        for edit in generated.edits:
            add, delete = count_diff_stats(edit.unified_diff)
            additions += add
            deletions += delete
        for created in generated.files:
            additions += created.content.count("\n") + (
                1 if created.content and not created.content.endswith("\n") else 0
            )

        new_files = tuple(item.path.replace("\\", "/") for item in generated.files)
        modified = tuple(item.path.replace("\\", "/") for item in generated.edits)
        affected = tuple(dict.fromkeys([*new_files, *modified]))
        conflict_warnings = tuple(
            list(validation.conflicts)
            + [w for w in validation.warnings if "conflict" in w.lower()]
        )
        risk = self._estimate_risk(generated, validation, additions, deletions)
        summary = self._build_change_summary(
            new_files=new_files,
            modified=modified,
            additions=additions,
            deletions=deletions,
            risk=risk,
            valid=validation.valid,
        )
        preview = PatchPreview(
            affected_files=affected,
            additions=additions,
            deletions=deletions,
            new_files=new_files,
            removed_files=validation.files_to_delete,
            renamed_files=validation.files_to_rename,
            conflict_warnings=conflict_warnings,
            risk_level=risk,
            change_summary=summary,
            validation=validation,
            duration_seconds=time.perf_counter() - started,
        )
        logger.info(
            "patch_preview affected=%d additions=%d deletions=%d risk=%s valid=%s",
            len(affected),
            additions,
            deletions,
            risk.value,
            validation.valid,
        )
        return preview

    def apply_patch(
        self,
        patch: Any,
        *,
        confirmed: bool = False,
    ) -> PatchApplicationResult:
        """Apply an approved GeneratedPatch after explicit confirmation."""
        self._ensure_permission(PERMISSION_APPLY, confirmed=confirmed)
        if not confirmed:
            raise CodeEditorConfirmationError(
                "apply_patch requires confirmed=True — no silent repository mutation."
            )

        generated = self._coerce_patch(patch)
        if not bool(getattr(generated, "approved", False)):
            raise CodeEditorApprovalError(
                "GeneratedPatch is not approved. Call patch.with_approval() first."
            )

        logger.info(
            "patch_apply_approval_ok plan_approved=%s patch_approved=%s",
            bool(getattr(generated, "plan_approved", False)),
            bool(getattr(generated, "approved", False)),
        )
        validation = self._validator.validate(generated)
        return self._applier.apply(generated, validation=validation)

    def rollback_patch(
        self,
        transaction_id: str,
        *,
        confirmed: bool = False,
    ) -> PatchRollbackResult:
        """Restore a prior transaction after explicit confirmation."""
        self._ensure_permission(PERMISSION_ROLLBACK, confirmed=confirmed)
        if not confirmed:
            raise CodeEditorConfirmationError(
                "rollback_patch requires confirmed=True — no silent repository mutation."
            )
        return self._applier.rollback(str(transaction_id))

    # --- Internals -----------------------------------------------------------

    def _dispatch_action(self, action_id: str, **kwargs: object) -> dict[str, Any]:
        if action_id == "validate_patch":
            result = self.validate_patch(kwargs.get("patch"))  # type: ignore[arg-type]
            payload = result.to_dict()
            payload["success"] = result.valid
            payload["message"] = (
                "Patch validation succeeded."
                if result.valid
                else "Patch validation failed."
            )
            payload["errors"] = list(result.errors) + list(result.conflicts)
            return payload

        if action_id == "preview_patch":
            result = self.preview_patch(kwargs.get("patch"))  # type: ignore[arg-type]
            payload = result.to_dict()
            payload["success"] = True
            payload["message"] = "Patch preview generated."
            payload["errors"] = []
            return payload

        if action_id == "apply_patch":
            confirmed = bool(kwargs.get("confirmed", False))
            result = self.apply_patch(kwargs.get("patch"), confirmed=confirmed)  # type: ignore[arg-type]
            payload = result.to_dict()
            payload["success"] = result.success
            payload["errors"] = list(result.errors)
            return payload

        if action_id == "rollback_patch":
            confirmed = bool(kwargs.get("confirmed", False))
            result = self.rollback_patch(
                str(kwargs.get("transaction_id") or ""),
                confirmed=confirmed,
            )
            payload = result.to_dict()
            payload["success"] = result.success
            payload["errors"] = list(result.errors)
            return payload

        raise CodeEditorError(f"Unsupported action: {action_id}")

    def _ensure_permission(
        self,
        permission_id: str,
        *,
        confirmed: bool = False,
    ) -> None:
        result = self._permission_manager.check_permission(permission_id)
        if result.allowed:
            return
        if (
            result.level == PermissionLevel.CONFIRMATION_REQUIRED
            and confirmed
        ):
            return
        raise CodeEditorPermissionDeniedError(permission_id, result.reason)

    def _coerce_patch(self, patch: Any) -> Any:
        if patch is None:
            raise CodeEditorError("Missing GeneratedPatch.")
        if isinstance(patch, ApplyablePatch):
            return patch
        if isinstance(patch, dict):
            return ApplyablePatch.from_dict(patch)
        # Duck-typed GeneratedPatch from Brain — no brain import in this package.
        if hasattr(patch, "files") and hasattr(patch, "edits"):
            return patch
        raise CodeEditorError(f"Unsupported patch type: {type(patch)!r}")

    def _estimate_risk(
        self,
        patch: Any,
        validation: PatchValidationResult,
        additions: int,
        deletions: int,
    ) -> PatchRiskLevel:
        if not validation.valid or validation.conflicts:
            return PatchRiskLevel.CRITICAL
        total_files = len(patch.files) + len(patch.edits)
        churn = additions + deletions
        summary_risk = ""
        if patch.summary is not None:
            summary_risk = str(getattr(patch.summary, "risk", "") or "").lower()
        if summary_risk in {"critical", "high"}:
            return (
                PatchRiskLevel.CRITICAL
                if summary_risk == "critical"
                else PatchRiskLevel.HIGH
            )
        if total_files >= 8 or churn >= 200:
            return PatchRiskLevel.HIGH
        if total_files >= 3 or churn >= 50 or patch.files:
            return PatchRiskLevel.MEDIUM
        return PatchRiskLevel.LOW

    def _build_change_summary(
        self,
        *,
        new_files: tuple[str, ...],
        modified: tuple[str, ...],
        additions: int,
        deletions: int,
        risk: PatchRiskLevel,
        valid: bool,
    ) -> str:
        status = "valid" if valid else "invalid"
        return (
            f"{status} patch: {len(new_files)} new file(s), "
            f"{len(modified)} edit(s), +{additions}/-{deletions}, "
            f"risk={risk.value}"
        )

    def _register_default_permissions(self) -> None:
        for permission in _DEFAULT_PERMISSIONS:
            if not self._permission_manager.permission_exists(permission.id):
                self._permission_manager.register_permission(permission)

    def _register_actions(self, action_registry: ActionRegistry) -> None:
        for action in self._actions:
            action_registry.register_action(action)


