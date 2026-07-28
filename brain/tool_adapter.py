# =====================================
# Titan Tool Adapter
# =====================================

"""Normalized adapter interface between the Tool Execution Bridge and tools.

The bridge never contains tool-specific logic. Each adapter exposes a single
``execute()`` method that returns a normalized ``BridgeExecutionResult``.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from typing import Any, Mapping

from brain.execution_tool_models import (
    BridgeExecutionResult,
    BridgeExecutionStatus,
    _normalize_error_message,
)
from core.actions.action_result import ActionResult
from core.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)


class ToolAdapter(ABC):
    """Abstract adapter — one normalized execute entry point per tool instance."""

    @property
    @abstractmethod
    def tool_id(self) -> str:
        """Registry id of the wrapped tool."""

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Whether the wrapped tool is currently enabled."""

    @property
    @abstractmethod
    def requires_confirmation(self) -> bool:
        """Whether live execution requires user confirmation."""

    @abstractmethod
    def list_action_ids(self) -> list[str]:
        """Return action ids exposed by the wrapped tool."""

    @abstractmethod
    def execute(
        self,
        action_id: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> BridgeExecutionResult:
        """Run one action and return a normalized bridge result."""


class RegistryToolAdapter(ToolAdapter):
    """Adapter over a core ``BaseTool`` from the Tool Registry.

    Contains no tool-specific branching — only delegates to
    ``BaseTool.execute_action`` and normalizes the ``ActionResult``.
    """

    def __init__(self, tool: BaseTool) -> None:
        self._tool = tool

    @property
    def tool_id(self) -> str:
        return self._tool.id

    @property
    def enabled(self) -> bool:
        return bool(self._tool.enabled)

    @property
    def requires_confirmation(self) -> bool:
        return bool(self._tool.requires_confirmation)

    @property
    def tool(self) -> BaseTool:
        return self._tool

    def list_action_ids(self) -> list[str]:
        return [action.id for action in self._tool.list_actions()]

    def execute(
        self,
        action_id: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> BridgeExecutionResult:
        params = dict(parameters or {})
        started = time.perf_counter()
        stamp = datetime.now(timezone.utc)

        try:
            if timeout_seconds is not None and float(timeout_seconds) > 0:
                raw = self._execute_with_timeout(
                    action_id, params, float(timeout_seconds)
                )
            else:
                raw = self._tool.execute_action(action_id, **params)
        except FuturesTimeoutError:
            duration = max(0.0, time.perf_counter() - started)
            reason = (
                f"Tool timed out after {float(timeout_seconds):.1f}s: "
                f"{self.tool_id}:{action_id}"
            )
            return BridgeExecutionResult(
                status=BridgeExecutionStatus.TIMEOUT,
                message=reason,
                success=False,
                duration=duration,
                tool_id=self.tool_id,
                action_id=action_id,
                error=reason,
                result_summary=reason,
                completed_at=stamp,
            )
        except Exception as exc:
            duration = max(0.0, time.perf_counter() - started)
            return BridgeExecutionResult.from_exception(
                tool_id=self.tool_id,
                action_id=action_id,
                exc=exc,
                duration=duration,
                now=stamp,
            )

        duration = max(0.0, time.perf_counter() - started)
        return self._normalize_action_result(
            raw,
            action_id=action_id,
            duration=duration,
            now=stamp,
        )

    def _execute_with_timeout(
        self,
        action_id: str,
        params: dict[str, Any],
        timeout_seconds: float,
    ) -> ActionResult:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self._tool.execute_action, action_id, **params)
            return future.result(timeout=timeout_seconds)

    def _normalize_action_result(
        self,
        raw: ActionResult | Any,
        *,
        action_id: str,
        duration: float,
        now: datetime,
    ) -> BridgeExecutionResult:
        if isinstance(raw, ActionResult):
            success = bool(raw.success)
            message = (raw.message or "").strip()
            errors = [str(e) for e in (raw.errors or []) if e]
            if not message and errors:
                message = errors[0]
            if not message:
                message = (
                    f"{self.tool_id}:{action_id} completed successfully."
                    if success
                    else f"{self.tool_id}:{action_id} failed."
                )
            # Never attach raw.data — public summary only.
            summary = message
            if not success and errors:
                summary = _normalize_error_message(
                    Exception("; ".join(errors[:3]))
                )
            status = (
                BridgeExecutionStatus.SUCCESS
                if success
                else BridgeExecutionStatus.FAILED
            )
            # Partial when success flag is true but errors were also reported.
            if success and errors:
                status = BridgeExecutionStatus.PARTIAL_SUCCESS
            meta = raw.metadata if isinstance(getattr(raw, "metadata", None), dict) else {}
            reversible = bool(meta.get("reversible", False))
            rollback_token = meta.get("rollback_token") or meta.get("rollback_id")
            return BridgeExecutionResult(
                status=status,
                message=message,
                success=success,
                duration=duration if duration > 0 else float(raw.execution_time or 0.0),
                tool_id=self.tool_id,
                action_id=action_id,
                error=None if success else summary,
                result_summary=summary,
                completed_at=now,
                reversible=reversible,
                rollback_token=str(rollback_token) if rollback_token else None,
            )

        # Legacy execute() return — treat as opaque success without payload leak.
        return BridgeExecutionResult(
            status=BridgeExecutionStatus.SUCCESS,
            message=f"{self.tool_id}:{action_id} completed successfully.",
            success=True,
            duration=duration,
            tool_id=self.tool_id,
            action_id=action_id,
            result_summary=f"{self.tool_id}:{action_id} completed successfully.",
            completed_at=now,
        )
