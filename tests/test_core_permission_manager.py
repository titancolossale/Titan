# =====================================
# Titan Core Permission Manager Tests
# =====================================

"""Demo tests for the generic core permission management layer."""

from __future__ import annotations

import pytest

from core.permissions import (
    Permission,
    PermissionAlreadyExistsError,
    PermissionLevel,
    PermissionManager,
    PermissionNotFoundError,
)


@pytest.fixture
def manager() -> PermissionManager:
    return PermissionManager()


def _register_obsidian_permissions(manager: PermissionManager) -> None:
    manager.register_permission(
        Permission(
            id="obsidian.read_note",
            name="Read Obsidian Note",
            description="Read an existing note from the user's vault.",
            level=PermissionLevel.SAFE,
        )
    )
    manager.register_permission(
        Permission(
            id="obsidian.create_note",
            name="Create Obsidian Note",
            description="Create a new note in the user's vault.",
            level=PermissionLevel.CONFIRMATION_REQUIRED,
        )
    )
    manager.register_permission(
        Permission(
            id="obsidian.edit_note",
            name="Edit Obsidian Note",
            description="Modify an existing note in the user's vault.",
            level=PermissionLevel.CONFIRMATION_REQUIRED,
        )
    )
    manager.register_permission(
        Permission(
            id="obsidian.delete_note",
            name="Delete Obsidian Note",
            description="Delete a note from the user's vault.",
            level=PermissionLevel.BLOCKED,
        )
    )


def test_safe_permission_is_allowed(manager: PermissionManager) -> None:
    """SAFE permissions return allowed=True."""
    _register_obsidian_permissions(manager)

    result = manager.check_permission("obsidian.read_note")

    assert result.allowed is True
    assert result.level == PermissionLevel.SAFE
    assert result.permission_id == "obsidian.read_note"
    assert result.reason


def test_confirmation_required_permission_needs_confirmation(
    manager: PermissionManager,
) -> None:
    """CONFIRMATION_REQUIRED returns allowed=False with confirmation level."""
    _register_obsidian_permissions(manager)

    result = manager.check_permission("obsidian.create_note")

    assert result.allowed is False
    assert result.level == PermissionLevel.CONFIRMATION_REQUIRED
    assert result.permission_id == "obsidian.create_note"
    assert "confirmation" in result.reason.lower()


def test_blocked_permission_is_denied(manager: PermissionManager) -> None:
    """BLOCKED permissions return allowed=False."""
    _register_obsidian_permissions(manager)

    result = manager.check_permission("obsidian.delete_note")

    assert result.allowed is False
    assert result.level == PermissionLevel.BLOCKED
    assert result.permission_id == "obsidian.delete_note"


def test_register_duplicate_raises(manager: PermissionManager) -> None:
    """Duplicate permission ids are rejected."""
    permission = Permission(
        id="github.read_repo",
        name="Read Repository",
        description="Read repository metadata.",
        level=PermissionLevel.SAFE,
    )
    manager.register_permission(permission)

    with pytest.raises(PermissionAlreadyExistsError):
        manager.register_permission(permission)


def test_permission_registry_lifecycle(manager: PermissionManager) -> None:
    """Permissions can be listed, enabled, disabled, and removed."""
    permission = Permission(
        id="browser.open_page",
        name="Open Browser Page",
        description="Navigate to a URL in the browser tool.",
        level=PermissionLevel.SAFE,
    )
    manager.register_permission(permission)

    assert manager.permission_exists("browser.open_page")
    assert manager.get_permission("browser.open_page") == permission
    assert len(manager.list_permissions()) == 1

    manager.disable_permission("browser.open_page")
    disabled_result = manager.check_permission("browser.open_page")
    assert disabled_result.allowed is False
    assert disabled_result.level == PermissionLevel.BLOCKED

    manager.enable_permission("browser.open_page")
    enabled_result = manager.check_permission("browser.open_page")
    assert enabled_result.allowed is True
    assert enabled_result.level == PermissionLevel.SAFE

    manager.remove_permission("browser.open_page")
    assert manager.permission_exists("browser.open_page") is False

    with pytest.raises(PermissionNotFoundError):
        manager.check_permission("browser.open_page")
