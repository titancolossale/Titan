# =====================================
# Titan Core Action Registry
# =====================================

"""Central registry for tool actions indexed by tool id and action id."""

from __future__ import annotations

import logging

from core.actions.action import Action
from core.actions.exceptions import ActionAlreadyExistsError, ActionNotFoundError

logger = logging.getLogger(__name__)


class ActionRegistry:
    """Register and query Titan tool actions indexed by composite key."""

    def __init__(self) -> None:
        self._actions: dict[str, Action] = {}

    @staticmethod
    def _composite_key(tool_id: str, action_id: str) -> str:
        """Build the internal registry key for a tool action."""
        return f"{tool_id.strip()}:{action_id.strip()}"

    def register_action(self, action: Action) -> None:
        """Register an action in the registry.

        Args:
            action: Action definition to add.

        Raises:
            ActionAlreadyExistsError: If the composite key is already registered.
        """
        key = self._composite_key(action.tool_id, action.id)
        if key in self._actions:
            raise ActionAlreadyExistsError(action.tool_id, action.id)
        self._actions[key] = action
        logger.info(
            "Action registered: tool=%s action=%s permission=%s",
            action.tool_id,
            action.id,
            action.permission_id,
        )

    def remove_action(self, tool_id: str, action_id: str) -> None:
        """Remove an action from the registry.

        Args:
            tool_id: Registry id of the owning tool.
            action_id: Action key to remove.

        Raises:
            ActionNotFoundError: If the action is not registered.
        """
        key = self._composite_key(tool_id, action_id)
        self._require_action(tool_id, action_id, key)
        del self._actions[key]
        logger.info("Action removed: tool=%s action=%s", tool_id, action_id)

    def get_action(self, tool_id: str, action_id: str) -> Action | None:
        """Return a registered action by tool and action id, or ``None`` if absent."""
        return self._actions.get(self._composite_key(tool_id, action_id))

    def list_actions(self) -> list[Action]:
        """Return all registered actions sorted by tool id then action id."""
        return [
            self._actions[key]
            for key in sorted(
                self._actions,
                key=lambda composite: (
                    self._actions[composite].tool_id,
                    self._actions[composite].id,
                ),
            )
        ]

    def list_actions_by_tool(self, tool_id: str) -> list[Action]:
        """Return registered actions owned by ``tool_id`` sorted by action id."""
        normalized = tool_id.strip()
        return [
            action
            for action in self.list_actions()
            if action.tool_id == normalized
        ]

    def action_exists(self, tool_id: str, action_id: str) -> bool:
        """Return True when the composite action key is registered."""
        return self._composite_key(tool_id, action_id) in self._actions

    def _require_action(self, tool_id: str, action_id: str, key: str | None = None) -> Action:
        resolved_key = key or self._composite_key(tool_id, action_id)
        action = self._actions.get(resolved_key)
        if action is None:
            raise ActionNotFoundError(tool_id, action_id)
        return action
