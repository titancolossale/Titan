# =====================================
# Titan Core Permissions Package
# =====================================

"""Universal authorization infrastructure for Titan tools."""

from core.permissions.exceptions import (
    PermissionAlreadyExistsError,
    PermissionError,
    PermissionNotFoundError,
)
from core.permissions.permission import Permission, PermissionLevel
from core.permissions.permission_manager import PermissionManager
from core.permissions.permission_policy import PermissionPolicy
from core.permissions.permission_result import PermissionResult

__all__ = [
    "Permission",
    "PermissionAlreadyExistsError",
    "PermissionError",
    "PermissionLevel",
    "PermissionManager",
    "PermissionNotFoundError",
    "PermissionPolicy",
    "PermissionResult",
]
