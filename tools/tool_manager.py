# =====================================
# Titan Tool Manager
# =====================================

"""Tool registry facade with policy enforcement (Phase 6 — P6-013)."""

from __future__ import annotations

from pathlib import Path

from config.settings import PROJECT_ROOT, TITAN_TOOL_RUNTIME_V2
from tools.default_tools import register_default_tools
from tools.tool_policy import ToolPolicy
from tools.tool_registry import ToolRegistry
from tools.tool_result import ToolResult
from tools.tool_run_models import ToolExecutionContext, ToolRun, ToolRunOutcome
from tools.tool_runtime import ToolRuntime
from tools.decision.provider_ranker import ProviderRanker
from tools.health_monitor import HealthMonitor
from tools.providers.defaults import create_provider_bootstrap, register_default_providers
from tools.providers.provider_executor import ProviderExecutor
from tools.providers.provider_performance_model import ProviderPerformanceModel
from tools.providers.provider_registry import ProviderRegistry
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
        if provider_registry is not None:
            self.provider_registry = provider_registry
            register_default_providers(
                self.provider_registry,
                project_root=self.project_root,
            )
        else:
            credential_manager, configuration_store = create_provider_bootstrap()
            self.provider_registry = ProviderRegistry(
                credential_manager=credential_manager,
                configuration_store=configuration_store,
            )
            register_default_providers(
                self.provider_registry,
                credential_manager=credential_manager,
                configuration_store=configuration_store,
                project_root=self.project_root,
            )
        self._health_monitor = HealthMonitor()
        self.provider_registry.sync_health(self._health_monitor)
        self.provider_executor = ProviderExecutor(
            registry=self.provider_registry,
            health_monitor=self._health_monitor,
        )
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
                provider_executor=self.provider_executor,
                health_monitor=self._health_monitor,
                project_root=self.project_root,
            )
        else:
            self._runtime = None

        if self._runtime is not None:
            self._runtime.provider_executor = self.provider_executor
            self._runtime.wire_performance_model()

        if register_defaults:
            self._register_defaults()

    def _register_defaults(self) -> None:
        """Register core tools via central registry (Phase 12.8 — P128-004)."""
        refresh = (
            self._runtime.refresh_catalog
            if self._runtime is not None
            else None
        )
        register_default_tools(
            self.registry,
            self.project_root,
            provider_executor=self.provider_executor,
            refresh_catalog=refresh,
        )

    @property
    def runtime(self) -> ToolRuntime | None:
        """Return the v2 runtime when enabled."""
        return self._runtime

    @property
    def performance_model(self) -> ProviderPerformanceModel | None:
        """Return the shared performance model when runtime v2 is active (P10B-1303)."""
        if self._runtime is None:
            return None
        return self._runtime.performance_model

    def provider_ranker(self) -> ProviderRanker:
        """Return a ranker bound to the shared performance model (P10B-1303)."""
        return ProviderRanker(performance_model=self.performance_model)

    def list_tools(self) -> list[str]:
        """Return registered tool names."""
        return self.registry.list_tools()

    def export_provider_dashboard(self) -> dict:
        """Export serializable provider inspection model for dashboards (P10B-206, P10B-1006)."""
        from tools.providers.provider_dashboard import build_dashboard_snapshot

        metadata = self.provider_registry.list_metadata()
        dashboard = build_dashboard_snapshot(metadata, self.provider_executor.telemetry)
        perf_metadata = self.export_provider_performance_analytics_metadata()
        if perf_metadata:
            dashboard["performance_metadata"] = perf_metadata
        perf_snapshot = self.export_provider_performance_snapshot()
        if perf_snapshot.get("providers"):
            dashboard["performance_summary"] = perf_snapshot
        return dashboard

    def _ensure_runtime(self) -> ToolRuntime:
        """Return v2 runtime, creating and wiring shared dependencies when needed."""
        if self._runtime is None:
            self._runtime = ToolRuntime(
                registry=self.registry,
                policy=self.policy,
                provider_registry=self.provider_registry,
                provider_executor=self.provider_executor,
                health_monitor=self._health_monitor,
                project_root=self.project_root,
            )
            self._runtime.refresh_catalog()
        else:
            self._runtime.provider_executor = self.provider_executor
            self._runtime.wire_performance_model()
        return self._runtime

    def export_provider_telemetry_snapshot(self) -> dict:
        """Export point-in-time provider telemetry snapshot (P10B-1003)."""
        return self.provider_executor.telemetry.snapshot().to_dict()

    def export_provider_performance_snapshot(self) -> dict:
        """Export point-in-time provider performance snapshot (P10B-1305)."""
        model = self.performance_model
        if model is None:
            return {"generated_at": "", "providers": []}
        return model.snapshot().to_dict()

    def get_rollback_history(self) -> list[dict]:
        """Expose rollback history via ToolRuntime for Brain (P12B2-006)."""
        runtime = self.runtime
        if runtime is None:
            return []
        return runtime.get_rollback_history()

    def rollback_history_size(self) -> int:
        """Return persisted rollback snapshot count (P12B2-006)."""
        runtime = self.runtime
        if runtime is None:
            return 0
        return runtime.rollback_history_size()

    def export_provider_performance_analytics_metadata(self) -> dict:
        """Export performance analytics schema metadata without UI (P10B-1306)."""
        from tools.providers.provider_dashboard import build_performance_dashboard_metadata

        model = self.performance_model
        if model is None:
            return build_performance_dashboard_metadata(None)
        return build_performance_dashboard_metadata(model.snapshot())

    def query_telemetry_last_hour(self) -> dict:
        """Return provider telemetry from the last hour (P10B-1105)."""
        persistence = self._telemetry_persistence()
        if persistence is None:
            return {}
        return persistence.last_hour(self.provider_executor.telemetry)

    def query_telemetry_last_day(self) -> dict:
        """Return provider telemetry from the last 24 hours (P10B-1105)."""
        persistence = self._telemetry_persistence()
        if persistence is None:
            return {}
        return persistence.last_day(self.provider_executor.telemetry)

    def query_provider_history(self, provider_id: str, *, hours: int | None = None) -> dict:
        """Return historical telemetry for a provider (P10B-1105)."""
        persistence = self._telemetry_persistence()
        if persistence is None:
            return {}
        return persistence.provider_history(
            provider_id,
            self.provider_executor.telemetry,
            hours=hours,
        )

    def query_latency_history(
        self,
        *,
        provider_id: str | None = None,
        hours: int | None = None,
    ) -> dict:
        """Return latency time-series metadata (P10B-1105)."""
        persistence = self._telemetry_persistence()
        if persistence is None:
            return {}
        return persistence.latency_history(
            self.provider_executor.telemetry,
            provider_id=provider_id,
            hours=hours,
        )

    def correlate_telemetry_run(self, run_id: str) -> dict:
        """Correlate telemetry records with a persisted tool run (P10B-1104)."""
        persistence = self._telemetry_persistence()
        if persistence is None or self._runtime is None or self._runtime.run_store is None:
            return {"run_id": run_id, "telemetry_records": [], "tool_run": None}
        return persistence.correlate_with_run_store(
            run_id,
            self.provider_executor.telemetry,
            self._runtime.run_store,
        )

    def export_telemetry_analytics_metadata(self) -> dict:
        """Export analytics schema metadata without UI (P10B-1106)."""
        persistence = self._telemetry_persistence()
        if persistence is None:
            from tools.providers.telemetry_persistence import TelemetryPersistenceManager

            return TelemetryPersistenceManager().analytics_metadata()
        return persistence.analytics_metadata()

    def _telemetry_persistence(self):
        """Return runtime telemetry persistence manager when v2 is active."""
        if self._runtime is None:
            return None
        return self._runtime.telemetry_persistence

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
        runtime = self._ensure_runtime()
        ctx = context or ToolExecutionContext(
            caller=caller,
            user="Nolan",
            session_id="default",
            turn_id="default",
        )
        return runtime.invoke(tool_name, params, ctx)

    def get_run(self, run_id: str) -> ToolRun | None:
        """Return a persisted tool run when runtime v2 is active."""
        if self._runtime is None:
            return None
        return self._runtime.get_run(run_id)

    def poll_run(self, run_id: str, *, timeout: float | None = None) -> ToolRunOutcome:
        """Poll an async tool run for completion."""
        runtime = self._ensure_runtime()
        return runtime.poll_run(run_id, timeout=timeout)

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
