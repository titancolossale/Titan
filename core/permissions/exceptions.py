# =====================================
# Titan Core Permission Exceptions
# =====================================

"""Custom exceptions for the core permission management layer."""

from __future__ import annotations

from core.exceptions import TitanError


class PermissionError(TitanError):
    """Base exception for core permission management failures."""


class PermissionAlreadyExistsError(PermissionError):
    """Raised when registering a permission whose id is already registered."""

    def __init__(self, permission_id: str) -> None:
        self.permission_id = permission_id
        super().__init__(f"Permission already registered: {permission_id}")


class PermissionNotFoundError(PermissionError):
    """Raised when a permission id is not present in the registry."""

    def __init__(self, permission_id: str) -> None:
        self.permission_id = permission_id
        super().__init__(f"Permission not found: {permission_id}")
