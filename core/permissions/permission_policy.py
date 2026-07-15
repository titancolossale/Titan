# =====================================
# Titan Core Permission Policy
# =====================================

"""Authorization policy evaluation for registered permissions."""

from __future__ import annotations

import logging

from core.permissions.permission import Permission, PermissionLevel
from core.permissions.permission_result import PermissionResult

logger = logging.getLogger(__name__)


class PermissionPolicy:
    """Evaluate permissions and return authorization decisions.

    This class decides authorization only — it never executes tool actions.
    """

    def evaluate(self, permission: Permission) -> PermissionResult:
        """Evaluate a permission and return an authorization result.

        Args:
            permission: Registered permission to evaluate.

        Returns:
            ``PermissionResult`` describing whether execution may proceed.
        """
        if not permission.enabled:
            result = PermissionResult(
                allowed=False,
                level=PermissionLevel.BLOCKED,
                reason=f"Permission '{permission.id}' is disabled.",
                permission_id=permission.id,
            )
            logger.debug(
                "Permission evaluated as disabled: id=%s allowed=%s",
                permission.id,
                result.allowed,
            )
            return result

        if permission.level == PermissionLevel.SAFE:
            result = PermissionResult(
                allowed=True,
                level=PermissionLevel.SAFE,
                reason="Permission granted.",
                permission_id=permission.id,
            )
        elif permission.level == PermissionLevel.CONFIRMATION_REQUIRED:
            result = PermissionResult(
                allowed=False,
                level=PermissionLevel.CONFIRMATION_REQUIRED,
                reason="User confirmation required before execution.",
                permission_id=permission.id,
            )
        else:
            result = PermissionResult(
                allowed=False,
                level=PermissionLevel.BLOCKED,
                reason="Permission is blocked by policy.",
                permission_id=permission.id,
            )

        logger.debug(
            "Permission evaluated: id=%s level=%s allowed=%s",
            permission.id,
            result.level.value,
            result.allowed,
        )
        return result
