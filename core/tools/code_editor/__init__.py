# =====================================
# Titan Code Editor Package
# =====================================

"""Controlled Patch Application V1 for GeneratedPatch proposals."""

from core.tools.code_editor.code_editor_tool import (
    CAPABILITY_APPLY_PATCH,
    CAPABILITY_PREVIEW_PATCH,
    CAPABILITY_ROLLBACK_PATCH,
    CAPABILITY_VALIDATE_PATCH,
    PERMISSION_APPLY,
    PERMISSION_PREVIEW,
    PERMISSION_ROLLBACK,
    PERMISSION_VALIDATE,
    CodeEditorTool,
)
from core.tools.code_editor.exceptions import (
    CodeEditorApprovalError,
    CodeEditorConfigurationError,
    CodeEditorConfirmationError,
    CodeEditorError,
    CodeEditorPathError,
    CodeEditorPermissionDeniedError,
    CodeEditorTransactionError,
    CodeEditorValidationError,
)
from core.tools.code_editor.models import (
    AffectedFileChange,
    ApplyablePatch,
    BackupEntry,
    ChangeKind,
    PatchApplicationResult,
    PatchEditProposal,
    PatchFileProposal,
    PatchPreview,
    PatchRiskLevel,
    PatchRollbackResult,
    PatchSummaryInfo,
    PatchTransaction,
    PatchValidationResult,
    TransactionStatus,
)
from core.tools.code_editor.patch_applier import PatchApplier
from core.tools.code_editor.patch_validator import PatchValidator

__all__ = [
    "CAPABILITY_APPLY_PATCH",
    "CAPABILITY_PREVIEW_PATCH",
    "CAPABILITY_ROLLBACK_PATCH",
    "CAPABILITY_VALIDATE_PATCH",
    "PERMISSION_APPLY",
    "PERMISSION_PREVIEW",
    "PERMISSION_ROLLBACK",
    "PERMISSION_VALIDATE",
    "AffectedFileChange",
    "ApplyablePatch",
    "BackupEntry",
    "ChangeKind",
    "CodeEditorApprovalError",
    "CodeEditorConfigurationError",
    "CodeEditorConfirmationError",
    "CodeEditorError",
    "CodeEditorPathError",
    "CodeEditorPermissionDeniedError",
    "CodeEditorTool",
    "CodeEditorTransactionError",
    "CodeEditorValidationError",
    "PatchApplier",
    "PatchApplicationResult",
    "PatchEditProposal",
    "PatchFileProposal",
    "PatchPreview",
    "PatchRiskLevel",
    "PatchRollbackResult",
    "PatchSummaryInfo",
    "PatchTransaction",
    "PatchValidationResult",
    "PatchValidator",
    "TransactionStatus",
]
