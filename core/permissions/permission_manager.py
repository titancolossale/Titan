# =====================================
# Titan Core Permission Manager
# =====================================

"""Central registry and authorization gateway for Titan permissions."""

from __future__ import annotations

import logging

from core.permissions.exceptions import (
    PermissionAlreadyExistsError,
    PermissionNotFoundError,
)
from core.permissions.permission import Permission
from core.permissions.permission_policy import PermissionPolicy
from core.permissions.permission_result import PermissionResult

logger = logging.getLogger(__name__)


class PermissionManager:
    """Register, manage, and evaluate Titan permissions indexed by id.

    Every current and future Titan tool can register permissions here and
    delegate authorization checks through ``check_permission``.
    """

    def __init__(self, policy: PermissionPolicy | None = None) -> None:
        self._permissions: dict[str, Permission] = {}
        self._policy = policy or PermissionPolicy()

    def register_permission(self, permission: Permission) -> None:
        """Register a permission in the registry.

        Args:
            permission: Permission definition to add.

        Raises:
            PermissionAlreadyExistsError: If ``permission.id`` is already registered.
        """
        if permission.id in self._permissions:
            raise PermissionAlreadyExistsError(permission.id)
        self._permissions[permission.id] = permission
        logger.info(
            "Permission created: id=%s level=%s enabled=%s",
            permission.id,
            permission.level.value,
            permission.enabled,
        )

    def remove_permission(self, permission_id: str) -> None:
        """Remove a permission from the registry.

        Args:
            permission_id: Registry key of the permission to remove.

        Raises:
            PermissionNotFoundError: If ``permission_id`` is not registered.
        """
        self._require_permission(permission_id)
        del self._permissions[permission_id]
        logger.info("Permission removed: id=%s", permission_id)

    def permission_exists(self, permission_id: str) -> bool:
        """Return True if ``permission_id`` is registered."""
        return permission_id in self._permissions

    def get_permission(self, permission_id: str) -> Permission | None:
        """Return a registered permission by id, or ``None`` if absent."""
        return self._permissions.get(permission_id)

    def list_permissions(self) -> list[Permission]:
        """Return all registered permissions sorted by id."""
        return [self._permissions[key] for key in sorted(self._permissions)]

    def enable_permission(self, permission_id: str) -> None:
        """Mark a registered permission as enabled.

        Raises:
            PermissionNotFoundError: If ``permission_id`` is not registered.
        """
        permission = self._require_permission(permission_id)
        self._permissions[permission_id] = Permission(
            id=permission.id,
            name=permission.name,
            description=permission.description,
            level=permission.level,
            enabled=True,
            metadata=dict(permission.metadata),
        )
        logger.info("Permission enabled: id=%s", permission_id)

    def disable_permission(self, permission_id: str) -> None:
        """Mark a registered permission as disabled.

        Raises:
            PermissionNotFoundError: If ``permission_id`` is not registered.
        """
        permission = self._require_permission(permission_id)
        self._permissions[permission_id] = Permission(
            id=permission.id,
            name=permission.name,
            description=permission.description,
            level=permission.level,
            enabled=False,
            metadata=dict(permission.metadata),
        )
        logger.info("Permission disabled: id=%s", permission_id)

    def check_permission(self, permission_id: str) -> PermissionResult:
        """Evaluate authorization for a registered permission.

        Args:
            permission_id: Registry key of the permission to check.

        Returns:
            ``PermissionResult`` describing whether execution may proceed.

        Raises:
            PermissionNotFoundError: If ``permission_id`` is not registered.
        """
        permission = self._require_permission(permission_id)
        result = self._policy.evaluate(permission)
        logger.info(
            "Permission checked: id=%s level=%s allowed=%s",
            permission_id,
            result.level.value,
            result.allowed,
        )
        return result

    def _require_permission(self, permission_id: str) -> Permission:
        permission = self._permissions.get(permission_id)
        if permission is None:
            raise PermissionNotFoundError(permission_id)
        return permission
