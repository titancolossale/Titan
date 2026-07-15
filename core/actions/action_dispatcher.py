# =====================================
# Titan Core Action Dispatcher
# =====================================

"""Universal dispatcher for tool actions — no tool-specific logic."""

from __future__ import annotations

import logging
import time

from core.actions.action import Action
from core.actions.action_registry import ActionRegistry
from core.actions.action_result import ActionResult
from core.actions.exceptions import ActionNotFoundError
from core.permissions.exceptions import PermissionNotFoundError
from core.permissions.permission_manager import PermissionManager
from core.tools.base_tool import BaseTool
from core.tools.exceptions import ToolNotRegisteredError
from core.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class ActionDispatcher:
    """Dispatch registered actions to tools after permission verification.

    The dispatcher resolves the target tool and action, evaluates permissions,
    and delegates execution to ``BaseTool.execute_action``. It never contains
    tool-specific branching.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        action_registry: ActionRegistry,
        permission_manager: PermissionManager,
    ) -> None:
        self._tool_registry = tool_registry
        self._action_registry = action_registry
        self._permission_manager = permission_manager

    def dispatch(
        self,
        tool_id: str,
        action_id: str,
        parameters: dict[str, object] | None = None,
    ) -> ActionResult:
        """Dispatch an action to its owning tool.

        Args:
            tool_id: Registry id of the target tool.
            action_id: Action key registered for the tool.
            parameters: Keyword arguments forwarded to ``execute_action``.

        Returns:
            ``ActionResult`` describing the execution outcome.

        Raises:
            ToolNotRegisteredError: If ``tool_id`` is not registered.
            ActionNotFoundError: If ``action_id`` is not registered for the tool.
        """
        started = time.perf_counter()
        params = dict(parameters or {})

        tool = self._require_tool(tool_id)
        action = self._require_action(tool_id, action_id)

        if not tool.enabled:
            elapsed = time.perf_counter() - started
            message = f"Tool is disabled: {tool_id}"
            logger.warning("Action dispatch blocked: %s", message)
            return ActionResult(
                success=False,
                message=message,
                execution_time=elapsed,
                errors=[message],
                metadata=self._result_metadata(tool_id, action_id, action.permission_id),
            )

        denied_result = self._check_permission(action.permission_id)
        if denied_result is not None:
            elapsed = time.perf_counter() - started
            logger.warning(
                "Action permission denied: tool=%s action=%s permission=%s reason=%s",
                tool_id,
                action_id,
                action.permission_id,
                denied_result.message,
            )
            return ActionResult(
                success=False,
                message=denied_result.message,
                execution_time=elapsed,
                errors=list(denied_result.errors),
                metadata={
                    **dict(denied_result.metadata),
                    **self._result_metadata(tool_id, action_id, action.permission_id),
                },
            )

        logger.info("Dispatching action: tool=%s action=%s", tool_id, action_id)
        result = tool.execute_action(action_id, **params)
        elapsed = time.perf_counter() - started

        merged_metadata = {
            **dict(result.metadata),
            **self._result_metadata(tool_id, action_id, action.permission_id),
        }
        return ActionResult(
            success=result.success,
            data=result.data,
            message=result.message,
            execution_time=elapsed,
            errors=list(result.errors),
            metadata=merged_metadata,
        )

    def _require_tool(self, tool_id: str) -> BaseTool:
        tool = self._tool_registry.get_tool(tool_id)
        if tool is None:
            raise ToolNotRegisteredError(tool_id)
        return tool

    def _require_action(self, tool_id: str, action_id: str) -> Action:
        action = self._action_registry.get_action(tool_id, action_id)
        if action is None:
            raise ActionNotFoundError(tool_id, action_id)
        return action

    def _check_permission(self, permission_id: str) -> ActionResult | None:
        """Return an ``ActionResult`` when permission is denied, else ``None``."""
        try:
            permission_result = self._permission_manager.check_permission(permission_id)
        except PermissionNotFoundError as exc:
            message = str(exc)
            return ActionResult(
                success=False,
                message=message,
                errors=[message],
                metadata={"permission_id": permission_id},
            )

        if permission_result.allowed:
            return None

        return ActionResult(
            success=False,
            message=permission_result.reason,
            errors=[permission_result.reason],
            metadata={"permission_id": permission_id},
        )

    @staticmethod
    def _result_metadata(
        tool_id: str,
        action_id: str,
        permission_id: str,
    ) -> dict[str, object]:
        return {
            "tool_id": tool_id,
            "action_id": action_id,
            "permission_id": permission_id,
        }
