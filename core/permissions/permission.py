# =====================================
# Titan Core Permission Model
# =====================================

"""Permission definitions for Titan's universal authorization layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PermissionLevel(str, Enum):
    """Authorization level assigned to a registered permission."""

    SAFE = "safe"
    CONFIRMATION_REQUIRED = "confirmation_required"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class Permission:
    """A registered authorization rule for a tool action or capability.

    Attributes:
        id: Stable registry key (e.g. ``obsidian.read_note``).
        name: Human-readable permission name.
        description: Short explanation of what the permission governs.
        level: Authorization level applied when the permission is evaluated.
        enabled: Whether the permission is active in the registry.
        metadata: Optional structured context for policy extensions.
    """

    id: str
    name: str
    description: str
    level: PermissionLevel
    enabled: bool = True
    metadata: dict[str, object] = field(default_factory=dict)
