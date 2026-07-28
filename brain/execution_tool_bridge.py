# =====================================
# Titan Execution Tool Bridge
# =====================================

"""Phase 18.3 Tool Execution Bridge.

Centralized path for cognitive ExecutionEngine → Tool Registry dispatch:

    Decision → ExecutionTask → Execution Safety → Tool Execution Bridge
    → Tool Registry → Tool Adapter → BridgeExecutionResult
    → WorkspaceState update → Decision feedback (via ExecutionEngine)

Does not recreate Tool Registry, ConfirmationGate, or PermissionManager.
Does not hardcode tool names — resolves exclusively via the registry.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Mapping

from brain.execution_tool_models import (
    DIAG_TOOL_CANCELLED,
    DIAG_TOOL_COMPLETED,
    DIAG_TOOL_DISPATCH,
    DIAG_TOOL_FAILED,
    DIAG_TOOL_STARTED,
    DIAG_TOOL_TIMEOUT,
    DIAG_TOOL_UNAVAILABLE,
    BridgeExecutionResult,
    BridgeExecutionStatus,
    ToolBridgeRequest,
)
from brain.tool_adapter import RegistryToolAdapter, ToolAdapter
from core.actions.action_registry import ActionRegistry
from core.permissions.permission import PermissionLevel
from core.permissions.permission_manager import PermissionManager
from core.tools.tool_registry import ToolRegistry
from tools.confirmation_gate import ConfirmationGate
from tools.tool_run_models import ToolExecutionContext

logger = logging.getLogger(__name__)


class ToolExecutionBridge:
    """Resolve, authorize, confirm, and dispatch tool actions for ExecutionEngine."""

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry | None = None,
        action_registry: ActionRegistry | None = None,
        permission_manager: PermissionManager | None = None,
        confirmation_gate: ConfirmationGate | None = None,
        default_timeout_seconds: float | None = None,
    ) -> None:
        self._registry = tool_registry if tool_registry is not None else ToolRegistry()
        self._action_registry = action_registry
        self._permission_manager = permission_manager
        self._confirmation_gate = confirmation_gate
        self._default_timeout = default_timeout_seconds
        # Resolve registry once; reuse adapters across dispatches.
        self._adapters: dict[str, ToolAdapter] = {}

    @property
    def tool_registry(self) -> ToolRegistry:
        return self._registry

    @property
    def action_registry(self) -> ActionRegistry | None:
        return self._action_registry

    def get_adapter(self, tool_id: str) -> ToolAdapter | None:
        """Return a cached adapter for ``tool_id``, creating it on first resolve."""
        cached = self._adapters.get(tool_id)
        if cached is not None:
            return cached
        tool = self._registry.get_tool(tool_id)
        if tool is None:
            return None
        adapter = RegistryToolAdapter(tool)
        self._adapters[tool_id] = adapter
        return adapter

    def invalidate_adapter(self, tool_id: str) -> None:
        """Drop a cached adapter (e.g. after registry unregister)."""
        self._adapters.pop(tool_id, None)

    def resolve_request(
        self,
        action: str | None,
        *,
        action_metadata: Mapping[str, Any] | None = None,
    ) -> ToolBridgeRequest | None:
        """Resolve a Decision action into a registry tool request, or None.

        Resolution order (no hardcoded tool names):
        1. Explicit ``action_metadata`` tool_id / action_id
        2. Composite action string ``tool_id:action_id`` / ``tool_id/action_id``
           when the tool_id exists in the registry
        3. Exact registry tool_id match (first listed action, or metadata action)
        """
        meta = dict(action_metadata or {})
        meta_tool = meta.get("tool_id") or meta.get("tool")
        meta_action = meta.get("action_id") or meta.get("action")
        raw_params = meta.get("parameters") or meta.get("params") or {}
        parameters: dict[str, Any] = (
            dict(raw_params) if isinstance(raw_params, Mapping) else {}
        )

        if meta_tool:
            tool_id = str(meta_tool).strip()
            adapter = self.get_adapter(tool_id)
            if adapter is None:
                return ToolBridgeRequest(
                    tool_id=tool_id,
                    action_id=str(meta_action or "").strip() or "unknown",
                    parameters=parameters,
                )
            action_id = str(meta_action or "").strip()
            if not action_id:
                ids = adapter.list_action_ids()
                action_id = ids[0] if ids else "unknown"
            return self._build_request(tool_id, action_id, parameters, adapter)

        text = (action or "").strip()
        if not text:
            return None

        for separator in (":", "/", "."):
            if separator not in text:
                continue
            left, right = text.split(separator, 1)
            tool_id = left.strip()
            action_id = right.strip()
            if not tool_id or not action_id:
                continue
            if self._registry.get_tool(tool_id) is None:
                continue
            adapter = self.get_adapter(tool_id)
            return self._build_request(
                tool_id, action_id, parameters, adapter
            )

        # Exact tool id — use first action unless metadata supplies one.
        if self._registry.get_tool(text) is not None:
            adapter = self.get_adapter(text)
            action_id = str(meta_action or "").strip()
            if not action_id and adapter is not None:
                ids = adapter.list_action_ids()
                action_id = ids[0] if ids else "unknown"
            return self._build_request(text, action_id or "unknown", parameters, adapter)

        return None

    def dispatch(
        self,
        *,
        action: str | None,
        workspace: Any | None = None,
        action_metadata: Mapping[str, Any] | None = None,
        confirmed: bool = False,
        confirmation_token: str | None = None,
        session_id: str = "default",
        user: str = "Nolan",
        turn_id: str | None = None,
        timeout_seconds: float | None = None,
        now: datetime | None = None,
        cognitive_message: str | None = None,
        preauthorized: bool = False,
    ) -> BridgeExecutionResult:
        """Full bridge pipeline for one ExecutionTask action.

        Args:
            preauthorized: When True, ExecutionSafety already approved this task —
                skip ConfirmationGate re-validation (cognitive tokens use
                ``__execution__``, not the real tool id).
        """
        stamp = now or datetime.now(timezone.utc)
        started = time.perf_counter()
        timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else self._default_timeout
        )

        request = self.resolve_request(action, action_metadata=action_metadata)
        logger.info(
            "%s action=%s tool_id=%s action_id=%s",
            DIAG_TOOL_DISPATCH,
            action,
            request.tool_id if request else None,
            request.action_id if request else None,
        )

        # Non-tool cognitive next-action — no registry dispatch.
        if request is None:
            message = cognitive_message or (
                f"Execution ready for action={action or 'None'}"
            )
            result = BridgeExecutionResult.cognitive_success(
                message=message,
                duration=max(0.0, time.perf_counter() - started),
                now=stamp,
            )
            self.apply_workspace_update(workspace, result)
            return result

        adapter = self.get_adapter(request.tool_id)
        if adapter is None:
            logger.info(
                "%s tool_id=%s reason=not_registered",
                DIAG_TOOL_UNAVAILABLE,
                request.tool_id,
            )
            result = BridgeExecutionResult.unavailable(
                tool_id=request.tool_id,
                reason=f"Tool unavailable: {request.tool_id} is not registered",
                duration=max(0.0, time.perf_counter() - started),
                now=stamp,
            )
            self.apply_workspace_update(workspace, result)
            return result

        if not adapter.enabled:
            logger.info(
                "%s tool_id=%s reason=disabled",
                DIAG_TOOL_UNAVAILABLE,
                request.tool_id,
            )
            result = BridgeExecutionResult.unavailable(
                tool_id=request.tool_id,
                reason=f"Tool unavailable: {request.tool_id} is disabled",
                duration=max(0.0, time.perf_counter() - started),
                now=stamp,
            )
            self.apply_workspace_update(workspace, result)
            return result

        if request.action_id not in adapter.list_action_ids():
            logger.info(
                "%s tool_id=%s action_id=%s reason=unknown_action",
                DIAG_TOOL_UNAVAILABLE,
                request.tool_id,
                request.action_id,
            )
            result = BridgeExecutionResult.unavailable(
                tool_id=request.tool_id,
                reason=(
                    f"Tool unavailable: action {request.action_id!r} "
                    f"not found on {request.tool_id}"
                ),
                duration=max(0.0, time.perf_counter() - started),
                now=stamp,
            )
            self.apply_workspace_update(workspace, result)
            return result

        permission_result = self._validate_permission(request)
        if permission_result is not None:
            self.apply_workspace_update(workspace, permission_result)
            return permission_result

        if not preauthorized:
            confirmation_result = self._validate_confirmation(
                request,
                adapter=adapter,
                confirmed=confirmed,
                confirmation_token=confirmation_token,
                session_id=session_id,
                user=user,
                turn_id=turn_id,
                started=started,
                now=stamp,
            )
            if confirmation_result is not None:
                self.apply_workspace_update(workspace, confirmation_result)
                return confirmation_result

        logger.info(
            "%s tool_id=%s action_id=%s",
            DIAG_TOOL_STARTED,
            request.tool_id,
            request.action_id,
        )
        result = adapter.execute(
            request.action_id,
            request.parameters,
            timeout_seconds=timeout,
        )
        # Prefer wall-clock around adapter call when adapter duration is zero.
        if result.duration <= 0:
            duration = max(0.0, time.perf_counter() - started)
            result = BridgeExecutionResult(
                status=result.status,
                message=result.message,
                success=result.success,
                duration=duration,
                tool_id=result.tool_id,
                action_id=result.action_id,
                error=result.error,
                blocked_reason=result.blocked_reason,
                result_summary=result.result_summary,
                completed_at=result.completed_at,
                reversible=result.reversible,
                rollback_token=result.rollback_token,
            )

        self._emit_completion_diagnostic(result)
        self.apply_workspace_update(workspace, result)
        return result

    def apply_workspace_update(
        self,
        workspace: Any | None,
        result: BridgeExecutionResult,
    ) -> None:
        """Mirror bridge outcome onto WorkspaceState (public fields only)."""
        if workspace is None:
            return

        if hasattr(workspace, "last_tool"):
            workspace.last_tool = result.tool_id
        if hasattr(workspace, "last_execution"):
            workspace.last_execution = result.execution_result
        if hasattr(workspace, "execution_duration"):
            workspace.execution_duration = round(float(result.duration), 4)
        if hasattr(workspace, "execution_status"):
            workspace.execution_status = result.status.value
        if hasattr(workspace, "last_error"):
            if result.status in (
                BridgeExecutionStatus.FAILED,
                BridgeExecutionStatus.TIMEOUT,
                BridgeExecutionStatus.FORBIDDEN,
                BridgeExecutionStatus.BLOCKED,
                BridgeExecutionStatus.CANCELLED,
            ):
                workspace.last_error = result.error or result.blocked_reason
            elif result.status == BridgeExecutionStatus.SUCCESS:
                workspace.last_error = None
            elif result.status == BridgeExecutionStatus.PARTIAL_SUCCESS:
                workspace.last_error = result.error

        # Keep active_tools concise — tool id only, never payloads.
        if result.tool_id and hasattr(workspace, "active_tools"):
            tools = list(getattr(workspace, "active_tools", None) or [])
            if result.status in (
                BridgeExecutionStatus.SUCCESS,
                BridgeExecutionStatus.PARTIAL_SUCCESS,
            ):
                if result.tool_id not in tools:
                    tools.append(result.tool_id)
                workspace.active_tools = tools[-8:]
            elif result.status in (
                BridgeExecutionStatus.FAILED,
                BridgeExecutionStatus.TIMEOUT,
                BridgeExecutionStatus.CANCELLED,
                BridgeExecutionStatus.FORBIDDEN,
                BridgeExecutionStatus.BLOCKED,
            ):
                workspace.active_tools = [
                    t for t in tools if t != result.tool_id
                ]

    def _build_request(
        self,
        tool_id: str,
        action_id: str,
        parameters: Mapping[str, Any],
        adapter: ToolAdapter | None,
    ) -> ToolBridgeRequest:
        permission_id = None
        requires_confirmation = bool(
            adapter.requires_confirmation if adapter is not None else False
        )
        if self._action_registry is not None:
            action = self._action_registry.get_action(tool_id, action_id)
            if action is not None:
                permission_id = action.permission_id
        return ToolBridgeRequest(
            tool_id=tool_id,
            action_id=action_id,
            parameters=dict(parameters),
            requires_confirmation=requires_confirmation,
            permission_id=permission_id,
        )

    def _validate_permission(
        self,
        request: ToolBridgeRequest,
    ) -> BridgeExecutionResult | None:
        """Return a terminal result when permission forbids; else None.

        ``CONFIRMATION_REQUIRED`` is not a hard forbid — confirmation validation
        runs next. ``BLOCKED`` / disabled permissions become FORBIDDEN.
        """
        if self._permission_manager is None or not request.permission_id:
            return None
        try:
            check = self._permission_manager.check_permission(request.permission_id)
        except Exception as exc:
            reason = f"Permission check failed: {exc}"
            logger.info(
                "%s tool_id=%s permission_id=%s reason=%s",
                DIAG_TOOL_FAILED,
                request.tool_id,
                request.permission_id,
                reason,
            )
            return BridgeExecutionResult(
                status=BridgeExecutionStatus.FORBIDDEN,
                message=reason,
                success=False,
                tool_id=request.tool_id,
                action_id=request.action_id,
                error=reason,
                blocked_reason=reason,
                result_summary=reason,
            )

        level_value = getattr(check.level, "value", check.level)
        if check.allowed or level_value == PermissionLevel.CONFIRMATION_REQUIRED.value:
            return None

        reason = check.reason or f"Permission denied: {request.permission_id}"
        logger.info(
            "%s tool_id=%s permission_id=%s reason=%s",
            DIAG_TOOL_FAILED,
            request.tool_id,
            request.permission_id,
            reason,
        )
        return BridgeExecutionResult(
            status=BridgeExecutionStatus.FORBIDDEN,
            message=reason,
            success=False,
            tool_id=request.tool_id,
            action_id=request.action_id,
            error=reason,
            blocked_reason=reason,
            result_summary=reason,
        )

    def _validate_confirmation(
        self,
        request: ToolBridgeRequest,
        *,
        adapter: ToolAdapter,
        confirmed: bool,
        confirmation_token: str | None,
        session_id: str,
        user: str,
        turn_id: str | None,
        started: float,
        now: datetime,
    ) -> BridgeExecutionResult | None:
        """Return BLOCKED when confirmation is required but missing/invalid."""
        needs_confirm = request.requires_confirmation or adapter.requires_confirmation
        if self._permission_manager is not None and request.permission_id:
            try:
                check = self._permission_manager.check_permission(request.permission_id)
                level = getattr(check, "level", None)
                level_value = getattr(level, "value", level)
                if level_value == PermissionLevel.CONFIRMATION_REQUIRED.value:
                    needs_confirm = True
            except Exception:
                pass

        if not needs_confirm:
            return None

        if self._confirmation_gate is not None:
            context = ToolExecutionContext(
                caller="execution_tool_bridge",
                user=user,
                session_id=session_id,
                turn_id=turn_id or "default",
                confirmed=confirmed,
                confirmation_token=confirmation_token,
            )
            # Public params digest only — empty dict when params unknown.
            valid = self._confirmation_gate.validate_confirmation(
                context,
                request.tool_id,
                dict(request.parameters),
            )
            if valid:
                return None
            reason = (
                f"Confirmation required for {request.tool_id}:{request.action_id}"
            )
            logger.info(
                "%s tool_id=%s action_id=%s reason=confirmation_required",
                DIAG_TOOL_CANCELLED,
                request.tool_id,
                request.action_id,
            )
            return BridgeExecutionResult(
                status=BridgeExecutionStatus.BLOCKED,
                message=reason,
                success=False,
                duration=max(0.0, time.perf_counter() - started),
                tool_id=request.tool_id,
                action_id=request.action_id,
                blocked_reason=reason,
                result_summary=reason,
                completed_at=now,
            )

        if confirmed:
            return None

        reason = f"Confirmation required for {request.tool_id}:{request.action_id}"
        logger.info(
            "%s tool_id=%s action_id=%s reason=confirmation_required",
            DIAG_TOOL_CANCELLED,
            request.tool_id,
            request.action_id,
        )
        return BridgeExecutionResult(
            status=BridgeExecutionStatus.BLOCKED,
            message=reason,
            success=False,
            duration=max(0.0, time.perf_counter() - started),
            tool_id=request.tool_id,
            action_id=request.action_id,
            blocked_reason=reason,
            result_summary=reason,
            completed_at=now,
        )

    @staticmethod
    def _emit_completion_diagnostic(result: BridgeExecutionResult) -> None:
        if result.status == BridgeExecutionStatus.TIMEOUT:
            logger.info(
                "%s tool_id=%s action_id=%s duration=%.4f",
                DIAG_TOOL_TIMEOUT,
                result.tool_id,
                result.action_id,
                result.duration,
            )
            return
        if result.status == BridgeExecutionStatus.CANCELLED:
            logger.info(
                "%s tool_id=%s action_id=%s",
                DIAG_TOOL_CANCELLED,
                result.tool_id,
                result.action_id,
            )
            return
        if result.success:
            logger.info(
                "%s tool_id=%s action_id=%s status=%s duration=%.4f",
                DIAG_TOOL_COMPLETED,
                result.tool_id,
                result.action_id,
                result.status.value,
                result.duration,
            )
            return
        logger.info(
            "%s tool_id=%s action_id=%s error=%s duration=%.4f",
            DIAG_TOOL_FAILED,
            result.tool_id,
            result.action_id,
            result.error or result.message,
            result.duration,
        )
