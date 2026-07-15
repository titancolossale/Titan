# =====================================
# Titan Tool Decision — Patch Models
# =====================================

"""Patch application result types (Phase 12 — P12-004)."""

from __future__ import annotations

from dataclasses import dataclass

from tools.tool_enums import RiskLevel


@dataclass(frozen=True)
class PatchApplicationResult:
    """Outcome of applying an approved ModificationPlan (P12-004)."""

    applied: bool
    files_modified: tuple[str, ...]
    files_created: tuple[str, ...]
    files_skipped: tuple[str, ...]
    errors: tuple[str, ...]
    rollback_available: bool
    confirmation_token: str
    risk_level: RiskLevel
    warnings: tuple[str, ...] = ()
    patch_id: str = ""
    rollback_id: str | None = None

    def to_dict(self) -> dict:
        """Serialize for DecisionReport and logging."""
        return {
            "applied": self.applied,
            "files_modified": list(self.files_modified),
            "files_created": list(self.files_created),
            "files_skipped": list(self.files_skipped),
            "errors": list(self.errors),
            "rollback_available": self.rollback_available,
            "confirmation_token": self.confirmation_token,
            "risk_level": self.risk_level.value,
            "warnings": list(self.warnings),
            "patch_id": self.patch_id,
            "rollback_id": self.rollback_id,
        }
