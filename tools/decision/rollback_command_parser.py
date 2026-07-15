# =====================================
# Titan Tool Decision — Rollback Command Parser
# =====================================

"""Parse user rollback commands (Phase 12 Batch 2 — P12B2-003)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_RESTORE_PATCH_PATTERN = re.compile(
    r"restore\s+patch\s+([a-f0-9-]{8,36})",
    re.IGNORECASE,
)

_ROLLBACK_COMMANDS: frozenset[str] = frozenset({
    "rollback",
    "undo",
    "restore previous patch",
    "restaurer le patch précédent",
    "annuler le patch",
})


@dataclass(frozen=True)
class RollbackCommand:
    """Parsed rollback request targeting latest or a specific snapshot."""

    target_rollback_id: str | None = None


def normalize_command_message(message: str) -> str:
    """Normalize user input for rollback command matching."""
    return message.strip().lower().rstrip(".")


def parse_rollback_command(message: str) -> RollbackCommand | None:
    """Return RollbackCommand when message is a rollback request (P12B2-003)."""
    normalized = normalize_command_message(message)
    match = _RESTORE_PATCH_PATTERN.search(normalized)
    if match:
        return RollbackCommand(target_rollback_id=match.group(1))
    if normalized in _ROLLBACK_COMMANDS:
        return RollbackCommand(target_rollback_id=None)
    return None
