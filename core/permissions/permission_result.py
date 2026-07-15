# =====================================
# Titan Core Permission Result
# =====================================

"""Structured authorization outcomes from permission evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from core.permissions.permission import PermissionLevel


@dataclass(frozen=True)
class PermissionResult:
    """Authorization decision for a single permission check.

    Attributes:
        allowed: Whether execution may proceed without further gates.
        level: Effective permission level after policy evaluation.
        reason: Human-readable explanation of the decision.
        permission_id: Registry id of the evaluated permission.
    """

    allowed: bool
    level: PermissionLevel
    reason: str
    permission_id: str
