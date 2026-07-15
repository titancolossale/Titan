# =====================================
# Titan Tool Execution Engine
# =====================================

"""Execute ToolExecutionPlan instances through the ActionDispatcher."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from core.actions.action_dispatcher import ActionDispatcher
from core.actions.action_registry import ActionRegistry
from core.actions.action_result import ActionResult
from core.actions.exceptions import ActionNotFoundError
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.tools.exceptions import ToolNotRegisteredError
from core.tools.capability_registry import CapabilityRegistry
from core.tools.tool_loader import ToolLoader
from core.tools.tool_registry import ToolRegistry

from brain.tool_intelligence import (
    CORE_TOOLS_DIR,
    PlannedAction,
    ToolExecutionPlan,
    ToolIntelligence,
    ToolIntent,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StepExecutionRecord:
    """Outcome of a single planned action execution."""

    step_index: int
    tool_id: str
    action_id: str
    success: bool
    result: ActionResult
    skipped: bool = False
    block_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "tool_id": self.tool_id,
            "action_id": self.action_id,
            "success": self.success,
            "skipped": self.skipped,
            "block_index": self.block_index,
            "message": self.result.message,
            "errors": list(self.result.errors),
            "execution_time": round(self.result.execution_time, 4),
        }


@dataclass(frozen=True)
class ToolExecutionResult:
    """Aggregated outcome of executing a ToolExecutionPlan."""

    plan: ToolExecutionPlan
    success: bool
    completed_steps: tuple[StepExecutionRecord, ...]
    failed_steps: tuple[StepExecutionRecord, ...]
    skipped_steps: tuple[StepExecutionRecord, ...]
    execution_duration: float
    tool_outputs: dict[str, object]
    messages: tuple[str, ...]
    stopped_early: bool
    summary_message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "success": self.success,
            "completed_steps": [step.to_dict() for step in self.completed_steps],
            "failed_steps": [step.to_dict() for step in self.failed_steps],
            "skipped_steps": [step.to_dict() for step in self.skipped_steps],
            "execution_duration": round(self.execution_duration, 4),
            "tool_outputs": dict(self.tool_outputs),
            "messages": list(self.messages),
            "stopped_early": self.stopped_early,
            "summary_message": self.summary_message,
        }


@dataclass(frozen=True)
class RequestExecutionResult:
    """Full pipeline result: plan creation plus execution."""

    request: str
    plan: ToolExecutionPlan
    execution: ToolExecutionResult

    @property
    def success(self) -> bool:
        return self.execution.success

    @property
    def summary_message(self) -> str:
        return self.execution.summary_message

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "plan": self.plan.to_dict(),
            "execution": self.execution.to_dict(),
            "success": self.success,
            "summary_message": self.summary_message,
        }


@dataclass(frozen=True)
class _ExecutionBlock:
    """One tool block in plan execution order."""

    block_index: int
    tool_id: str
    actions: tuple[PlannedAction, ...]


@dataclass
class CoreToolRuntime:
    """Shared core tool stack for intelligence and execution."""

    tool_registry: ToolRegistry
    capability_registry: CapabilityRegistry
    action_registry: ActionRegistry
    permission_manager: PermissionManager
    dispatcher: ActionDispatcher
    intelligence: ToolIntelligence
    engine: ToolExecutionEngine


class ToolExecutionEngine:
    """Execute ToolExecutionPlan steps exclusively through ActionDispatcher."""

    def __init__(self, action_dispatcher: ActionDispatcher) -> None:
        self._dispatcher = action_dispatcher

    @property
    def dispatcher(self) -> ActionDispatcher:
        return self._dispatcher

    def execute(self, plan: ToolExecutionPlan) -> ToolExecutionResult:
        """Execute every step in *plan* and return an aggregated result."""
        started = time.perf_counter()
        logger.info(
            "ToolExecutionEngine start request=%r intent=%s tools=%s order=%s",
            plan.request,
            plan.intent.value,
            [tool.tool_id for tool in plan.selected_tools],
            list(plan.execution_order),
        )

        if not plan.requires_tools or not plan.execution_order:
            duration = time.perf_counter() - started
            summary = plan.intent_summary or "No tools required; conversation only."
            result = ToolExecutionResult(
                plan=plan,
                success=True,
                completed_steps=(),
                failed_steps=(),
                skipped_steps=(),
                execution_duration=duration,
                tool_outputs={},
                messages=(summary,),
                stopped_early=False,
                summary_message=summary,
            )
            self._log_summary(result)
            return result

        blocks = self._build_blocks(plan)
        completed: list[StepExecutionRecord] = []
        failed: list[StepExecutionRecord] = []
        skipped: list[StepExecutionRecord] = []
        messages: list[str] = []
        tool_outputs: dict[str, object] = {}
        stopped_early = False
        step_index = 0

        for block in blocks:
            if stopped_early:
                for action in block.actions:
                    skipped.append(
                        self._skipped_record(
                            step_index=step_index,
                            block_index=block.block_index,
                            tool_id=block.tool_id,
                            action_id=action.action_id,
                            reason="Execution stopped due to prior unrecoverable error.",
                        )
                    )
                    step_index += 1
                continue

            if not block.actions:
                failure = self._unknown_tool_result(block.tool_id)
                record = StepExecutionRecord(
                    step_index=step_index,
                    tool_id=block.tool_id,
                    action_id="",
                    success=False,
                    result=failure,
                    block_index=block.block_index,
                )
                failed.append(record)
                messages.extend(self._result_messages(failure, block.tool_id, ""))
                stopped_early = True
                step_index += 1
                logger.error(
                    "ToolExecutionEngine unknown tool block: tool=%s",
                    block.tool_id,
                )
                continue

            block_failed = False
            for action in block.actions:
                if block_failed:
                    skipped.append(
                        self._skipped_record(
                            step_index=step_index,
                            block_index=block.block_index,
                            tool_id=block.tool_id,
                            action_id=action.action_id,
                            reason="Skipped because a prior action in this tool block failed.",
                        )
                    )
                    step_index += 1
                    continue

                logger.info(
                    "ToolExecutionEngine tool start tool=%s action=%s step=%s",
                    block.tool_id,
                    action.action_id,
                    step_index,
                )
                try:
                    action_result = self._dispatcher.dispatch(
                        block.tool_id,
                        action.action_id,
                        dict(action.parameters),
                    )
                except ToolNotRegisteredError as exc:
                    action_result = ActionResult(
                        success=False,
                        message=str(exc),
                        errors=[str(exc)],
                        metadata={"tool_id": block.tool_id, "action_id": action.action_id},
                    )
                    stopped_early = True
                except ActionNotFoundError as exc:
                    action_result = ActionResult(
                        success=False,
                        message=str(exc),
                        errors=[str(exc)],
                        metadata={"tool_id": block.tool_id, "action_id": action.action_id},
                    )
                    stopped_early = True

                record = StepExecutionRecord(
                    step_index=step_index,
                    tool_id=block.tool_id,
                    action_id=action.action_id,
                    success=action_result.success,
                    result=action_result,
                    block_index=block.block_index,
                )
                messages.extend(
                    self._result_messages(action_result, block.tool_id, action.action_id)
                )

                if action_result.success:
                    completed.append(record)
                    tool_outputs[block.tool_id] = action_result.data
                    logger.info(
                        "ToolExecutionEngine tool finish tool=%s action=%s "
                        "success=true duration=%.4fs",
                        block.tool_id,
                        action.action_id,
                        action_result.execution_time,
                    )
                else:
                    failed.append(record)
                    block_failed = True
                    logger.warning(
                        "ToolExecutionEngine tool finish tool=%s action=%s "
                        "success=false duration=%.4fs errors=%s",
                        block.tool_id,
                        action.action_id,
                        action_result.execution_time,
                        action_result.errors,
                    )
                    if stopped_early:
                        step_index += 1
                        break

                step_index += 1

            if block_failed and not stopped_early:
                has_remaining_blocks = block.block_index < len(blocks) - 1
                if has_remaining_blocks and self._blocks_are_independent(plan):
                    logger.info(
                        "ToolExecutionEngine continuing after block failure "
                        "tool=%s independent_remaining=true",
                        block.tool_id,
                    )
                    continue
                stopped_early = True

        duration = time.perf_counter() - started
        success = bool(completed) and not failed and not stopped_early
        if not plan.requires_tools:
            success = True
        elif completed and failed and self._blocks_are_independent(plan):
            success = True
        elif completed and not failed:
            success = True
        else:
            success = False

        summary = self._build_summary(
            plan=plan,
            completed=completed,
            failed=failed,
            skipped=skipped,
            success=success,
        )
        result = ToolExecutionResult(
            plan=plan,
            success=success,
            completed_steps=tuple(completed),
            failed_steps=tuple(failed),
            skipped_steps=tuple(skipped),
            execution_duration=duration,
            tool_outputs=tool_outputs,
            messages=tuple(messages),
            stopped_early=stopped_early,
            summary_message=summary,
        )
        self._log_summary(result)
        return result

    @staticmethod
    def _build_blocks(plan: ToolExecutionPlan) -> tuple[_ExecutionBlock, ...]:
        tools_by_id = {tool.tool_id: tool for tool in plan.selected_tools}
        blocks: list[_ExecutionBlock] = []
        for block_index, tool_id in enumerate(plan.execution_order):
            selected = tools_by_id.get(tool_id)
            actions = selected.actions if selected is not None else ()
            blocks.append(
                _ExecutionBlock(
                    block_index=block_index,
                    tool_id=tool_id,
                    actions=actions,
                )
            )
        return tuple(blocks)

    @staticmethod
    def _blocks_are_independent(plan: ToolExecutionPlan) -> bool:
        if len(plan.execution_order) <= 1:
            return False
        return plan.intent == ToolIntent.COMPARE or len(plan.selected_tools) > 1

    @staticmethod
    def _unknown_tool_result(tool_id: str) -> ActionResult:
        message = f"Tool is not registered: {tool_id}"
        return ActionResult(
            success=False,
            message=message,
            errors=[message],
            metadata={"tool_id": tool_id},
        )

    @staticmethod
    def _skipped_record(
        *,
        step_index: int,
        block_index: int,
        tool_id: str,
        action_id: str,
        reason: str,
    ) -> StepExecutionRecord:
        return StepExecutionRecord(
            step_index=step_index,
            tool_id=tool_id,
            action_id=action_id,
            success=False,
            skipped=True,
            block_index=block_index,
            result=ActionResult(
                success=False,
                message=reason,
                errors=[reason],
                metadata={"tool_id": tool_id, "action_id": action_id, "skipped": True},
            ),
        )

    @staticmethod
    def _result_messages(
        result: ActionResult,
        tool_id: str,
        action_id: str,
    ) -> list[str]:
        prefix = f"[{tool_id}:{action_id}]" if action_id else f"[{tool_id}]"
        messages: list[str] = []
        if result.message:
            messages.append(f"{prefix} {result.message}")
        for error in result.errors:
            if error and error != result.message:
                messages.append(f"{prefix} {error}")
        if result.success and not result.message:
            messages.append(f"{prefix} completed successfully.")
        return messages

    @staticmethod
    def _build_summary(
        *,
        plan: ToolExecutionPlan,
        completed: list[StepExecutionRecord],
        failed: list[StepExecutionRecord],
        skipped: list[StepExecutionRecord],
        success: bool,
    ) -> str:
        if not plan.requires_tools:
            return plan.intent_summary or "No tools required; conversation only."
        if success and completed:
            tools = ", ".join(dict.fromkeys(step.tool_id for step in completed))
            return f"Executed {len(completed)} step(s) via {tools}."
        if completed and failed:
            return (
                f"Partial execution: {len(completed)} completed, "
                f"{len(failed)} failed, {len(skipped)} skipped."
            )
        if failed and not completed:
            return f"Execution failed: {len(failed)} step(s) failed."
        return "Execution finished with no completed steps."

    @staticmethod
    def _log_summary(result: ToolExecutionResult) -> None:
        logger.info(
            "ToolExecutionEngine summary success=%s duration=%.4fs "
            "completed=%s failed=%s skipped=%s stopped_early=%s",
            result.success,
            result.execution_duration,
            len(result.completed_steps),
            len(result.failed_steps),
            len(result.skipped_steps),
            result.stopped_early,
        )
        logger.info("ToolExecutionEngine summary_message: %s", result.summary_message)


def _bootstrap_loaded_tools(tool_registry: ToolRegistry) -> None:
    """Connect loaded tools that require explicit startup (e.g. Obsidian vault)."""
    for tool in tool_registry.list_tools():
        if tool.id != "obsidian":
            continue
        is_connected = getattr(tool, "is_connected", None)
        connect = getattr(tool, "connect", None)
        if callable(is_connected) and callable(connect) and not is_connected():
            try:
                connect()
                logger.info("Auto-connected loaded tool: %s", tool.id)
            except Exception as exc:
                logger.warning("Failed to auto-connect tool %s: %s", tool.id, exc)


def sync_action_runtime(
    tool_registry: ToolRegistry,
    action_registry: ActionRegistry,
    permission_manager: PermissionManager,
) -> None:
    """Register actions and permissions from loaded tools into shared runtime."""
    for tool in tool_registry.list_tools():
        tool_permissions = getattr(tool, "permission_manager", None)
        if tool_permissions is not None:
            for permission in tool_permissions.list_permissions():
                if not permission_manager.permission_exists(permission.id):
                    permission_manager.register_permission(permission)

        for action in tool.list_actions():
            if not permission_manager.permission_exists(action.permission_id):
                permission_manager.register_permission(
                    Permission(
                        id=action.permission_id,
                        name=action.name,
                        description=action.description,
                        level=PermissionLevel.SAFE,
                    )
                )
            if not action_registry.action_exists(tool.id, action.id):
                action_registry.register_action(action)


def build_core_tool_runtime(
    *,
    registry: ToolRegistry | None = None,
    capability_registry: CapabilityRegistry | None = None,
    scan_paths: list[Path] | None = None,
) -> CoreToolRuntime:
    """Build a shared ToolRegistry, ActionDispatcher, intelligence, and engine."""
    cap_registry = capability_registry or CapabilityRegistry()
    if registry is None:
        tool_registry = ToolRegistry(capability_registry=cap_registry)
    else:
        tool_registry = registry
        if tool_registry.capability_registry is None:
            tool_registry.attach_capability_registry(cap_registry)
        elif capability_registry is not None and tool_registry.capability_registry is not cap_registry:
            tool_registry.attach_capability_registry(cap_registry)

    if not tool_registry.list_tools():
        loader = ToolLoader(tool_registry, scan_paths=scan_paths or [CORE_TOOLS_DIR])
        loader.load()
        _bootstrap_loaded_tools(tool_registry)

    action_registry = ActionRegistry()
    permission_manager = PermissionManager()
    sync_action_runtime(tool_registry, action_registry, permission_manager)
    cap_registry.set_known_permissions(
        permission.id for permission in permission_manager.list_permissions()
    )

    dispatcher = ActionDispatcher(
        tool_registry=tool_registry,
        action_registry=action_registry,
        permission_manager=permission_manager,
    )
    intelligence = ToolIntelligence(tool_registry, capability_registry=cap_registry)
    engine = ToolExecutionEngine(dispatcher)
    return CoreToolRuntime(
        tool_registry=tool_registry,
        capability_registry=cap_registry,
        action_registry=action_registry,
        permission_manager=permission_manager,
        dispatcher=dispatcher,
        intelligence=intelligence,
        engine=engine,
    )


def build_default_tool_execution_engine(
    *,
    registry: ToolRegistry | None = None,
    scan_paths: list[Path] | None = None,
) -> ToolExecutionEngine:
    """Construct ToolExecutionEngine with discovered core tools."""
    return build_core_tool_runtime(registry=registry, scan_paths=scan_paths).engine
