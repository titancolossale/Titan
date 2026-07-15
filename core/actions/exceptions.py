# =====================================
# Titan Core Action Exceptions
# =====================================

"""Custom exceptions for the universal action execution framework."""

from __future__ import annotations

from core.exceptions import TitanError


class ActionError(TitanError):
    """Base exception for action framework failures."""


class ActionAlreadyExistsError(ActionError):
    """Raised when registering an action whose composite key is already registered."""

    def __init__(self, tool_id: str, action_id: str) -> None:
        self.tool_id = tool_id
        self.action_id = action_id
        super().__init__(f"Action already registered: {tool_id}.{action_id}")


class ActionNotFoundError(ActionError):
    """Raised when an action id is not present in the registry."""

    def __init__(self, tool_id: str, action_id: str) -> None:
        self.tool_id = tool_id
        self.action_id = action_id
        super().__init__(f"Action not found: {tool_id}.{action_id}")
