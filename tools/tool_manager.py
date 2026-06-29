# =====================================
# Titan Tool Manager
# =====================================

"""Tool registry facade with policy enforcement (Phase 6 — P6-013)."""

from __future__ import annotations

from pathlib import Path

from config.settings import PROJECT_ROOT, TITAN_TOOL_RUNTIME_V2
from tools.calendar_tool import CalendarTool
from tools.file_read_tool import FileReadTool
from tools.file_write_tool import FileWriteTool
from tools.python_exec_tool import PythonExecTool
from tools.time_tool import TimeTool
from tools.tool_policy import ToolPolicy
from tools.tool_registry import ToolRegistry
from tools.tool_result import ToolResult
from tools.tool_run_models import ToolExecutionContext, ToolRun, ToolRunOutcome
from tools.tool_runtime import ToolRuntime
from tools.providers.defaults import register_default_providers
from tools.providers.provider_registry import ProviderRegistry
from tools.web_search_tool import WebSearchTool


class ToolManager:
    """Register tools, enforce policy, and dispatch execution."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        registry: ToolRegistry | None = None,
        policy: ToolPolicy | None = None,
        register_defaults: bool = True,
        runtime: ToolRuntime | None = None,
        provider_registry: ProviderRegistry | None = None,
        use_runtime_v2: bool | None = None,
    ) -> None:
        self.project_root = (project_root or PROJECT_ROOT).resolve()
        self.registry = registry or ToolRegistry()
        self.policy = policy or ToolPolicy()
        self.provider_registry = provider_registry or ProviderRegistry()
        register_default_providers(self.provider_registry)
        self._use_runtime_v2 = (
            TITAN_TOOL_RUNTIME_V2 if use_runtime_v2 is None else use_runtime_v2
        )
        if runtime is not None:
            self._runtime = runtime
        elif self._use_runtime_v2:
            self._runtime = ToolRuntime(
                registry=self.registry,
                policy=self.policy,
                provider_registry=self.provider_registry,
            )
        else:
            self._runtime = None
        if register_defaults:
            self._register_defaults()

    def _register_defaults(self) -> None:
        """Register core Phase 6 tools if not already present."""
        defaults = [
            TimeTool(),
            FileReadTool(self.project_root),
            FileWriteTool(self.project_root),
            PythonExecTool(self.project_root),
            WebSearchTool(registry=self.provider_registry),
            CalendarTool(),
        ]
        for tool in defaults:
            if self.registry.get(tool.name) is None:
                self.registry.register(tool)
        if self._runtime is not None:
            self._runtime.refresh_catalog()

    @property
    def runtime(self) -> ToolRuntime | None:
        """Return the v2 runtime when enabled."""
        return self._runtime

    def list_tools(self) -> list[str]:
        """Return registered tool names."""
        return self.registry.list_tools()

    def run(
        self,
        tool_name: str,
        params: dict | None = None,
        *,
        caller: str = "brain",
        user: str = "Nolan",
        session_id: str = "default",
        turn_id: str = "default",
    ) -> ToolResult:
        """Execute a tool after policy check."""
        if self._runtime is not None:
            context = ToolExecutionContext(
                caller=caller,
                user=user,
                session_id=session_id,
                turn_id=turn_id,
            )
            outcome = self._runtime.invoke(tool_name, params, context)
            return self._runtime.outcome_to_result(outcome)

        if not self.policy.is_allowed(caller, tool_name):
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=self.policy.deny_message(caller, tool_name),
                source="tool_policy",
            )
        return self.registry.run(tool_name, params)

    def invoke(
        self,
        tool_name: str,
        params: dict | None = None,
        context: ToolExecutionContext | None = None,
        *,
        caller: str = "brain",
    ) -> ToolRunOutcome:
        """Execute through the v2 runtime and return a full outcome."""
        if self._runtime is None:
            self._runtime = ToolRuntime(
                registry=self.registry,
                policy=self.policy,
                provider_registry=self.provider_registry,
            )
        ctx = context or ToolExecutionContext(
            caller=caller,
            user="Nolan",
            session_id="default",
            turn_id="default",
        )
        return self._runtime.invoke(tool_name, params, ctx)

    def get_run(self, run_id: str) -> ToolRun | None:
        """Return a persisted tool run when runtime v2 is active."""
        if self._runtime is None:
            return None
        return self._runtime.get_run(run_id)

    def poll_run(self, run_id: str, *, timeout: float | None = None) -> ToolRunOutcome:
        """Poll an async tool run for completion."""
        if self._runtime is None:
            self._runtime = ToolRuntime(
                registry=self.registry,
                policy=self.policy,
                provider_registry=self.provider_registry,
            )
        return self._runtime.poll_run(run_id, timeout=timeout)

    def cancel_run(self, run_id: str, *, reason: str = "") -> bool:
        """Cancel an in-flight tool run."""
        if self._runtime is None:
            return False
        return self._runtime.cancel_run(run_id, reason=reason)

    def get_current_time(self) -> str:
        """Backward-compatible datetime string for Titan shell startup."""
        return self.run("time", caller="brain").data

    def format_tool_status(self) -> str:
        """Probe providers and return French health summary for Brain prompts."""
        runtime = self._runtime
        if runtime is None:
            return ""
        from tools.tool_status_formatter import ToolStatusFormatter

        snapshot = ToolStatusFormatter.probe_snapshot(
            self.provider_registry,
            runtime.health_monitor,
            runtime.catalog,
        )
        return ToolStatusFormatter.format_for_prompt(
            snapshot,
            provider_registry=self.provider_registry,
        )

    @property
    def confirmation_gate(self):
        """Return the runtime confirmation gate when v2 is active."""
        if self._runtime is None:
            return None
        return self._runtime.confirmation_gate
