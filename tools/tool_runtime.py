# =====================================
# Titan Tool Runtime
# =====================================

"""Central tool invocation runtime with pre-flight gates (Phase 10A — P10A-018)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config.settings import (
    TITAN_FALLBACK_TIMEOUT,
    TITAN_PROVIDER_FALLBACK_ENABLED,
    TITAN_TOOL_AUDIT_ENABLED,
    TITAN_TOOL_DEFAULT_EXECUTION_MODE,
    TITAN_TOOL_PERSIST_METRICS,
    TITAN_TOOL_PERSIST_RUNS,
    TITAN_TOOL_PERSIST_TELEMETRY,
    TITAN_TOOL_POLL_TIMEOUT_SECONDS,
    TITAN_TOOL_QUOTA_ENABLED,
    TOOL_METRICS_PATH,
    TOOL_TELEMETRY_PATH,
)
from core.exceptions import (
    ToolDependencyError,
    ToolHealthError,
    ToolPermissionDenied,
    ToolQuotaExceeded,
)
from tools.adapters.legacy_tool_adapter import register_legacy_tools
from tools.audit.tool_audit_logger import ToolAuditLogger
from tools.audit.tool_audit_models import ToolAuditEvent, compute_params_digest
from tools.capability_catalog import CapabilityCatalog
from tools.decision.execution_context import extract_decision_report
from tools.decision.models import ToolDecisionReport
from tools.decision.rollback_manager import RollbackManager, get_rollback_manager
from tools.providers.provider_fallback_policy import FallbackDecision, ProviderFallbackPolicy
from tools.cancellation_registry import CancellationRegistry
from tools.confirmation_gate import ConfirmationGate
from tools.dependency_resolver import DependencyResolver
from tools.executors.async_executor import AsyncExecutor
from tools.executors.sync_executor import SyncExecutor
from tools.health_monitor import HealthMonitor
from tools.permission_engine import PermissionEngine
from tools.permission_facade import PermissionFacade
from tools.permission_manager import PermissionLevel, PermissionManager, resolve_tool_action
from tools.providers.defaults import create_provider_bootstrap, register_default_providers
from tools.providers.provider_executor import ProviderExecutor
from tools.providers.provider_performance_model import ProviderPerformanceModel
from tools.providers.provider_registry import ProviderRegistry
from tools.providers.telemetry_persistence import TelemetryPersistenceManager
from tools.retry_policy import RetryPolicy
from tools.tool_capability import ToolCapability
from tools.tool_enums import ExecutionMode, InvocationMode, ToolHealthState
from tools.tool_metrics import MetricsCollector
from tools.tool_quota import QuotaTracker
from tools.tool_registry import ToolRegistry
from tools.tool_result import ToolResult
from tools.tool_run_models import ToolExecutionContext, ToolRun, ToolRunOutcome, ToolRunStatus, ConfirmationRequest
from tools.tool_run_store import ToolRunStore
from tools.tool_policy import ToolPolicy


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_execution_mode(value: str) -> ExecutionMode:
    try:
        return ExecutionMode(value.lower())
    except ValueError:
        return ExecutionMode.LIVE


@dataclass
class ToolRuntime:
    """Orchestrate pre-flight validation, execution, metrics, audit, and persistence."""

    registry: ToolRegistry
    policy: ToolPolicy
    catalog: CapabilityCatalog = field(default_factory=CapabilityCatalog)
    dependency_resolver: DependencyResolver = field(default_factory=DependencyResolver)
    health_monitor: HealthMonitor = field(default_factory=HealthMonitor)
    metrics_collector: MetricsCollector = field(default_factory=MetricsCollector)
    quota_tracker: QuotaTracker = field(default_factory=QuotaTracker)
    permission_engine: PermissionEngine | None = None
    permission_manager: PermissionManager | None = None
    permission_facade: PermissionFacade | None = None
    confirmation_gate: ConfirmationGate | None = None
    sync_executor: SyncExecutor | None = None
    async_executor: AsyncExecutor | None = None
    cancellation_registry: CancellationRegistry | None = None
    run_store: ToolRunStore | None = None
    audit_logger: ToolAuditLogger | None = None
    provider_registry: ProviderRegistry | None = None
    provider_executor: ProviderExecutor | None = None
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    default_execution_mode: ExecutionMode = field(
        default_factory=lambda: _parse_execution_mode(TITAN_TOOL_DEFAULT_EXECUTION_MODE)
    )
    persist_runs: bool = TITAN_TOOL_PERSIST_RUNS
    persist_metrics: bool = TITAN_TOOL_PERSIST_METRICS
    persist_telemetry: bool = TITAN_TOOL_PERSIST_TELEMETRY
    metrics_path: Path = field(default_factory=lambda: TOOL_METRICS_PATH)
    telemetry_path: Path = field(default_factory=lambda: TOOL_TELEMETRY_PATH)
    telemetry_persistence: TelemetryPersistenceManager | None = None
    performance_model: ProviderPerformanceModel | None = None
    poll_timeout_seconds: float = float(TITAN_TOOL_POLL_TIMEOUT_SECONDS)
    project_root: Path | None = None
    rollback_manager: RollbackManager | None = None

    def __post_init__(self) -> None:
        if self.permission_facade is None:
            self.permission_facade = PermissionFacade(policy=self.policy)
        if self.permission_engine is None:
            self.permission_engine = self.permission_facade.permission_engine
        if self.permission_manager is None:
            self.permission_manager = self.permission_facade.permission_manager
        if self.confirmation_gate is None:
            self.confirmation_gate = ConfirmationGate()
        if self.sync_executor is None:
            self.sync_executor = SyncExecutor(registry=self.registry)
        if self.cancellation_registry is None:
            self.cancellation_registry = CancellationRegistry()
        if self.async_executor is None:
            assert self.sync_executor is not None
            assert self.cancellation_registry is not None
            self.async_executor = AsyncExecutor(
                sync_executor=self.sync_executor,
                cancellation_registry=self.cancellation_registry,
            )
        if self.run_store is None:
            self.run_store = ToolRunStore(persist=self.persist_runs)
        if self.audit_logger is None:
            self.audit_logger = ToolAuditLogger(enabled=TITAN_TOOL_AUDIT_ENABLED)
        if self.provider_registry is None:
            credential_manager, configuration_store = create_provider_bootstrap()
            self.provider_registry = ProviderRegistry(
                credential_manager=credential_manager,
                configuration_store=configuration_store,
            )
        if self.provider_executor is None:
            self.provider_executor = ProviderExecutor(
                registry=self.provider_registry,
                health_monitor=self.health_monitor,
            )
        self.dependency_resolver.health_monitor = self.health_monitor
        register_default_providers(self.provider_registry)
        self._wire_providers()
        self.quota_tracker.enabled = TITAN_TOOL_QUOTA_ENABLED
        self._load_persisted_metrics()
        if self.telemetry_persistence is None:
            self.telemetry_persistence = TelemetryPersistenceManager(
                file_path=self.telemetry_path,
                persist=self.persist_telemetry,
            )
        if self.provider_executor is not None:
            self.telemetry_persistence.reload_on_startup(self.provider_executor.telemetry)
        self.wire_performance_model()
        register_legacy_tools(self.registry, self.catalog, self.dependency_resolver)
        if self.rollback_manager is None and self.project_root is not None:
            self.rollback_manager = get_rollback_manager(self.project_root)

    def get_rollback_history(self) -> list[dict]:
        """Expose available rollback history to Brain (P12B2-006)."""
        if self.rollback_manager is None:
            return []
        return self.rollback_manager.list_history_summary()

    def rollback_history_size(self) -> int:
        """Return count of persisted rollback snapshots (P12B2-006)."""
        if self.rollback_manager is None:
            return 0
        return self.rollback_manager.history_size()

    def wire_performance_model(self) -> None:
        """Bind or refresh performance model to the active telemetry collector (P10B-1301)."""
        if self.provider_executor is None:
            return
        collector = self.provider_executor.telemetry
        if self.performance_model is None:
            self.performance_model = ProviderPerformanceModel(collector=collector)
        elif self.performance_model.collector is collector:
            self.performance_model.invalidate()
        self.provider_executor.performance_model = self.performance_model

    def refresh_catalog(self) -> None:
        """Re-sync capabilities from registry after tools are added."""
        register_legacy_tools(self.registry, self.catalog, self.dependency_resolver)

    def _wire_providers(self) -> None:
        """Sync provider registry with dependency resolver and health monitor."""
        assert self.provider_registry is not None
        for provider_id in self.provider_registry.list_ids():
            self.dependency_resolver.register_provider(provider_id)
        self.provider_registry.sync_health(self.health_monitor)

    def invoke(
        self,
        tool_name: str,
        params: dict | None,
        context: ToolExecutionContext,
    ) -> ToolRunOutcome:
        """Run the full pre-flight pipeline and execute synchronously or async."""
        run_id = str(uuid.uuid4())
        params_dict = dict(params or {})
        params_digest = compute_params_digest(params_dict)
        capability = self.catalog.get(tool_name)

        if capability is None:
            if self.registry.get(tool_name) is None:
                return self._finalize_failed(
                    run_id,
                    tool_name,
                    context,
                    f"Outil inconnu : {tool_name}",
                    params_digest=params_digest,
                )
            self.refresh_catalog()
            capability = self.catalog.get(tool_name)
            if capability is None:
                return self._finalize_failed(
                    run_id,
                    tool_name,
                    context,
                    f"Capacité introuvable : {tool_name}",
                    params_digest=params_digest,
                )

        assert capability is not None

        decision_report = extract_decision_report(context)
        if decision_report is not None and decision_report.selected_tool:
            if decision_report.selected_tool != tool_name:
                return self._finalize_failed(
                    run_id,
                    tool_name,
                    context,
                    (
                        f"Décision/incohérence d'exécution : attendu "
                        f"{decision_report.selected_tool!r}, reçu {tool_name!r}"
                    ),
                    params_digest=params_digest,
                    capability=capability,
                    error_code="decision_mismatch",
                )

        validation_error = self._validate_params(tool_name, params_dict)
        if validation_error:
            return self._finalize_failed(
                run_id,
                tool_name,
                context,
                validation_error,
                params_digest=params_digest,
                capability=capability,
            )

        effective_context = self._resolve_context(context, capability)
        self._audit(
            event_type="invoked",
            run_id=run_id,
            tool_name=tool_name,
            context=effective_context,
            capability=capability,
            params_digest=params_digest,
        )

        try:
            self._preflight(
                tool_name,
                capability,
                effective_context,
                params=params_dict,
            )
        except ToolPermissionDenied as exc:
            return self._finalize_failed(
                run_id,
                tool_name,
                effective_context,
                str(exc),
                params_digest=params_digest,
                capability=capability,
                error_code="permission_denied",
                audit_event="denied",
            )
        except ToolQuotaExceeded as exc:
            return self._finalize_failed(
                run_id,
                tool_name,
                effective_context,
                str(exc),
                params_digest=params_digest,
                capability=capability,
                error_code="quota_exceeded",
                audit_event="denied",
            )
        except ToolDependencyError as exc:
            return self._finalize_failed(
                run_id,
                tool_name,
                effective_context,
                str(exc),
                params_digest=params_digest,
                capability=capability,
                error_code="dependency_unavailable",
                audit_event="denied",
            )
        except ToolHealthError as exc:
            return self._finalize_failed(
                run_id,
                tool_name,
                effective_context,
                str(exc),
                params_digest=params_digest,
                capability=capability,
                error_code="health_blocked",
                audit_event="denied",
            )

        confirmation = self._evaluate_confirmation(
            run_id,
            tool_name,
            capability,
            effective_context,
            params_dict,
            params_digest=params_digest,
            decision_report=decision_report,
        )
        if confirmation is not None:
            return confirmation

        health_state = self.health_monitor.get_tool_health(
            tool_name,
            capability=capability,
        )
        health_result = self.health_monitor.assert_ready(tool_name, capability)
        if health_result.state == ToolHealthState.DEGRADED and health_result.message:
            self._audit(
                event_type="degraded",
                run_id=run_id,
                tool_name=tool_name,
                context=effective_context,
                capability=capability,
                params_digest=params_digest,
                health_state=health_state,
                message=health_result.message,
            )

        if capability.invocation_mode in {InvocationMode.ASYNC, InvocationMode.BACKGROUND}:
            return self._invoke_async(
                run_id,
                tool_name,
                params_dict,
                effective_context,
                capability,
                health_state,
                params_digest=params_digest,
            )

        return self._invoke_sync(
            run_id,
            tool_name,
            params_dict,
            effective_context,
            capability,
            health_state,
            params_digest=params_digest,
            decision_report=decision_report,
        )

    def get_run(self, run_id: str) -> ToolRun | None:
        """Return a persisted run record."""
        assert self.run_store is not None
        return self.run_store.get(run_id)

    def poll_run(self, run_id: str, *, timeout: float | None = None) -> ToolRunOutcome:
        """Poll an async run until completion or timeout."""
        assert self.run_store is not None
        assert self.async_executor is not None

        run = self.run_store.get(run_id)
        if run is None:
            return ToolRunOutcome(
                run_id=run_id,
                status=ToolRunStatus.FAILED,
                error=f"Run introuvable : {run_id}",
            )

        if run.is_terminal():
            return self._run_to_outcome(run)

        wait_seconds = self.poll_timeout_seconds if timeout is None else timeout
        result = self.async_executor.poll(run_id, timeout=wait_seconds)
        if result is None:
            return ToolRunOutcome(
                run_id=run_id,
                status=run.status,
                error="Exécution en cours",
            )

        return self._complete_async_run(run_id, result)

    def cancel_run(self, run_id: str, *, reason: str = "") -> bool:
        """Request cancellation for an in-flight or queued run."""
        assert self.cancellation_registry is not None
        assert self.run_store is not None

        run = self.run_store.get(run_id)
        if run is None:
            return False
        if run.is_terminal():
            return False

        self.cancellation_registry.cancel(run_id, reason=reason)
        cancelled = ToolRun(
            run_id=run.run_id,
            tool_name=run.tool_name,
            status=ToolRunStatus.CANCELLED,
            caller=run.caller,
            user=run.user,
            session_id=run.session_id,
            turn_id=run.turn_id,
            execution_mode=run.execution_mode,
            health_state=run.health_state,
            error=reason or "Annulé",
            started_at=run.started_at,
            finished_at=_utc_now_iso(),
        )
        self.run_store.upsert(cancelled)
        self._audit(
            event_type="cancelled",
            run_id=run_id,
            tool_name=run.tool_name,
            context=ToolExecutionContext(
                caller=run.caller,
                user=run.user,
                session_id=run.session_id,
                turn_id=run.turn_id,
                execution_mode=run.execution_mode,
            ),
            capability=self.catalog.get(run.tool_name),
            success=False,
            error_code="cancelled",
            message=reason,
        )
        self.cancellation_registry.unregister(run_id)
        return True

    def _invoke_sync(
        self,
        run_id: str,
        tool_name: str,
        params: dict,
        context: ToolExecutionContext,
        capability: ToolCapability,
        health_state: ToolHealthState,
        *,
        params_digest: str,
        decision_report: ToolDecisionReport | None = None,
    ) -> ToolRunOutcome:
        """Execute synchronously with audit and persistence."""
        assert self.run_store is not None

        started_at = _utc_now_iso()
        running = ToolRun(
            run_id=run_id,
            tool_name=tool_name,
            status=ToolRunStatus.RUNNING,
            caller=context.caller,
            user=context.user,
            session_id=context.session_id,
            turn_id=context.turn_id,
            execution_mode=context.execution_mode,
            health_state=health_state,
            started_at=started_at,
        )
        self.run_store.upsert(running)
        self._audit(
            event_type="started",
            run_id=run_id,
            tool_name=tool_name,
            context=context,
            capability=capability,
            params_digest=params_digest,
            health_state=health_state,
            dependencies_checked=True,
        )

        self.quota_tracker.record_start(tool_name)
        perf_start = time.perf_counter()
        result: ToolResult | None = None
        timed_out = False

        try:
            result = self._execute_with_retries(
                tool_name,
                params,
                capability,
                run_id=run_id,
                context=context,
                decision_report=decision_report,
            )
        finally:
            duration_ms = (time.perf_counter() - perf_start) * 1000.0
            self.quota_tracker.record_finish(tool_name, capability.quota)
            if result is not None:
                self.metrics_collector.record(
                    tool_name,
                    duration_ms=duration_ms,
                    success=result.success,
                    timed_out=timed_out,
                )
                self._persist_metrics_snapshot()

        assert result is not None
        result.run_id = run_id
        result.metadata["execution_mode"] = context.execution_mode.value
        result.metadata["health_state"] = health_state.value
        self._record_provider_telemetry(
            run_id=run_id,
            tool_name=tool_name,
            context=context,
            result=result,
            decision_report=decision_report,
            duration_ms=duration_ms,
        )
        self._emit_provider_audit(
            run_id=run_id,
            tool_name=tool_name,
            context=context,
            capability=capability,
            result=result,
            decision_report=decision_report,
        )

        if not result.success:
            return self._finalize_run(
                run_id,
                tool_name,
                context,
                ToolRunStatus.FAILED,
                capability=capability,
                params_digest=params_digest,
                health_state=health_state,
                result=result,
                error=result.error,
                duration_ms=duration_ms,
                audit_event="failed",
                error_code="execution_failed",
            )

        return self._finalize_run(
            run_id,
            tool_name,
            context,
            ToolRunStatus.COMPLETED,
            capability=capability,
            params_digest=params_digest,
            health_state=health_state,
            result=result,
            duration_ms=duration_ms,
            audit_event="completed",
            success=True,
        )

    def _invoke_async(
        self,
        run_id: str,
        tool_name: str,
        params: dict,
        context: ToolExecutionContext,
        capability: ToolCapability,
        health_state: ToolHealthState,
        *,
        params_digest: str,
    ) -> ToolRunOutcome:
        """Queue execution on the async executor and return immediately."""
        assert self.run_store is not None
        assert self.async_executor is not None

        queued = ToolRun(
            run_id=run_id,
            tool_name=tool_name,
            status=ToolRunStatus.QUEUED,
            caller=context.caller,
            user=context.user,
            session_id=context.session_id,
            turn_id=context.turn_id,
            execution_mode=context.execution_mode,
            health_state=health_state,
            started_at=_utc_now_iso(),
        )
        self.run_store.upsert(queued)
        self._audit(
            event_type="queued",
            run_id=run_id,
            tool_name=tool_name,
            context=context,
            capability=capability,
            params_digest=params_digest,
            health_state=health_state,
        )

        self.quota_tracker.record_start(tool_name)

        def _on_complete(completed_run_id: str, result: ToolResult) -> None:
            duration_ms = 0.0
            self.quota_tracker.record_finish(tool_name, capability.quota)
            self.metrics_collector.record(
                tool_name,
                duration_ms=duration_ms,
                success=result.success,
            )
            self._persist_metrics_snapshot()
            self._complete_async_run(completed_run_id, result)

        running = ToolRun(
            run_id=run_id,
            tool_name=tool_name,
            status=ToolRunStatus.RUNNING,
            caller=context.caller,
            user=context.user,
            session_id=context.session_id,
            turn_id=context.turn_id,
            execution_mode=context.execution_mode,
            health_state=health_state,
            started_at=queued.started_at,
        )
        self.run_store.upsert(running)
        self._audit(
            event_type="started",
            run_id=run_id,
            tool_name=tool_name,
            context=context,
            capability=capability,
            params_digest=params_digest,
            health_state=health_state,
        )

        self.async_executor.submit(
            run_id,
            tool_name,
            params,
            timeout_seconds=capability.timeout_seconds,
            on_complete=_on_complete,
        )

        return ToolRunOutcome(
            run_id=run_id,
            status=ToolRunStatus.QUEUED,
            error="Exécution asynchrone en cours",
        )

    def _complete_async_run(self, run_id: str, result: ToolResult) -> ToolRunOutcome:
        """Finalize an async run after the worker completes."""
        assert self.run_store is not None

        run = self.run_store.get(run_id)
        if run is None:
            return ToolRunOutcome(
                run_id=run_id,
                status=ToolRunStatus.FAILED,
                result=result,
                error=result.error,
            )

        context = ToolExecutionContext(
            caller=run.caller,
            user=run.user,
            session_id=run.session_id,
            turn_id=run.turn_id,
            execution_mode=run.execution_mode,
        )
        capability = self.catalog.get(run.tool_name)
        cancelled = bool(result.metadata.get("cancelled"))

        if cancelled:
            return self._finalize_run(
                run_id,
                run.tool_name,
                context,
                ToolRunStatus.CANCELLED,
                capability=capability,
                health_state=run.health_state,
                result=result,
                error=result.error,
                audit_event="cancelled",
                error_code="cancelled",
                success=False,
            )

        if not result.success:
            return self._finalize_run(
                run_id,
                run.tool_name,
                context,
                ToolRunStatus.FAILED,
                capability=capability,
                health_state=run.health_state,
                result=result,
                error=result.error,
                audit_event="failed",
                error_code="execution_failed",
                success=False,
            )

        return self._finalize_run(
            run_id,
            run.tool_name,
            context,
            ToolRunStatus.COMPLETED,
            capability=capability,
            health_state=run.health_state,
            result=result,
            audit_event="completed",
            success=True,
        )

    def _preflight(
        self,
        tool_name: str,
        capability: ToolCapability,
        context: ToolExecutionContext,
        params: dict | None = None,
    ) -> None:
        """Run unified permission, quota, dependency, and health gates."""
        assert self.permission_facade is not None

        decision_report = extract_decision_report(context)
        permission = self.permission_facade.evaluate(
            tool_name,
            capability,
            context,
            params,
            decision_report=decision_report,
        )
        if not permission.allowed and not permission.confirmation_required:
            raise ToolPermissionDenied(permission.reason)

        quota_result = self.quota_tracker.check(tool_name, capability.quota)
        if not quota_result.allowed:
            raise ToolQuotaExceeded(quota_result.reason)

        self.dependency_resolver.assert_satisfied(tool_name, registry=self.registry)
        self.health_monitor.assert_ready(tool_name, capability)

    def _evaluate_confirmation(
        self,
        run_id: str,
        tool_name: str,
        capability: ToolCapability,
        context: ToolExecutionContext,
        params: dict,
        *,
        params_digest: str,
        decision_report: ToolDecisionReport | None = None,
    ) -> ToolRunOutcome | None:
        """Run confirmation gate; return pending outcome when approval is required."""
        assert self.confirmation_gate is not None

        action_permission_required = False
        action_permission_reason = ""
        if self.permission_facade is not None:
            action = resolve_tool_action(tool_name, params, decision_report)
            action_permission = self.permission_facade.evaluate_action_only(
                tool_name,
                action,
                params,
                decision_report=decision_report,
                confirmed=context.confirmed,
            )
            if action_permission.level == PermissionLevel.CONFIRMATION_REQUIRED:
                action_permission_required = True
                action_permission_reason = action_permission.reason

        if (
            decision_report is not None
            and not decision_report.confirmation_required
            and not action_permission_required
        ):
            return None

        if action_permission_required and context.confirmed:
            if self.confirmation_gate.validate_confirmation(context, tool_name, params):
                return None

        if action_permission_required and not context.confirmed:
            request = self.confirmation_gate.issue_request(
                tool_name,
                capability,
                context,
                params,
                params_digest,
            )
            if action_permission_reason:
                request = ConfirmationRequest(
                    token=request.token,
                    tool_name=request.tool_name,
                    description=action_permission_reason,
                    params_digest=request.params_digest,
                )
            self._audit(
                event_type="confirmation_requested",
                run_id=run_id,
                tool_name=tool_name,
                context=context,
                capability=capability,
                params_digest=params_digest,
            )
            pending = ToolRun(
                run_id=run_id,
                tool_name=tool_name,
                status=ToolRunStatus.PENDING_CONFIRMATION,
                caller=context.caller,
                user=context.user,
                session_id=context.session_id,
                turn_id=context.turn_id,
                execution_mode=context.execution_mode,
                error=action_permission_reason or "Confirmation requise",
                started_at=_utc_now_iso(),
            )
            assert self.run_store is not None
            self.run_store.upsert(pending)
            return ToolRunOutcome(
                run_id=run_id,
                status=ToolRunStatus.PENDING_CONFIRMATION,
                confirmation_request=request,
                error=action_permission_reason or "Confirmation requise",
            )

        result = self.confirmation_gate.evaluate(
            tool_name,
            capability,
            context,
            params,
        )
        if result.satisfied:
            return None

        if result.request is not None:
            self._audit(
                event_type="confirmation_requested",
                run_id=run_id,
                tool_name=tool_name,
                context=context,
                capability=capability,
                params_digest=params_digest,
            )
            pending = ToolRun(
                run_id=run_id,
                tool_name=tool_name,
                status=ToolRunStatus.PENDING_CONFIRMATION,
                caller=context.caller,
                user=context.user,
                session_id=context.session_id,
                turn_id=context.turn_id,
                execution_mode=context.execution_mode,
                error=result.reason or "Confirmation requise",
                started_at=_utc_now_iso(),
            )
            assert self.run_store is not None
            self.run_store.upsert(pending)
            return ToolRunOutcome(
                run_id=run_id,
                status=ToolRunStatus.PENDING_CONFIRMATION,
                confirmation_request=result.request,
                error=result.reason,
            )

        return self._finalize_failed(
            run_id,
            tool_name,
            context,
            result.reason or "Confirmation requise.",
            params_digest=params_digest,
            capability=capability,
            error_code="confirmation_required",
            audit_event="denied",
        )

    def _execute_with_retries(
        self,
        tool_name: str,
        params: dict,
        capability: ToolCapability,
        *,
        run_id: str,
        context: ToolExecutionContext | None = None,
        decision_report: ToolDecisionReport | None = None,
    ) -> ToolResult:
        """Execute via sync executor with optional retries and cancellation checks."""
        assert self.sync_executor is not None
        assert self.cancellation_registry is not None
        max_retries = capability.max_retries
        attempt = 0
        result = ToolResult(tool_name=tool_name, success=False, error="Aucune tentative")
        tool_params = self._inject_execution_context(
            params,
            run_id=run_id,
            context=context,
            decision_report=decision_report,
        )

        while True:
            if self.cancellation_registry.is_cancelled(run_id):
                reason = self.cancellation_registry.reason(run_id) or "Annulé"
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    error=reason,
                    source="tool_runtime",
                    run_id=run_id,
                    metadata={"cancelled": True},
                )
            attempt += 1
            result = self.sync_executor.execute(
                tool_name,
                tool_params,
                timeout_seconds=capability.timeout_seconds,
            )
            if not self.retry_policy.should_retry(attempt, max_retries, result):
                return result
            time.sleep(self.retry_policy.delay_seconds(attempt))

    @staticmethod
    def _inject_execution_context(
        params: dict,
        *,
        run_id: str,
        context: ToolExecutionContext | None,
        decision_report: ToolDecisionReport | None,
    ) -> dict:
        """Pass runtime/decision correlation into provider-backed tools."""
        tool_params = dict(params)
        fallback_decision = ""
        fallback_policy = ""
        allow_fallback = TITAN_PROVIDER_FALLBACK_ENABLED
        if decision_report is not None:
            fallback_decision = decision_report.fallback_decision
            fallback_policy = decision_report.fallback_policy
            if fallback_decision:
                try:
                    allow_fallback = ProviderFallbackPolicy.allows_fallback(
                        FallbackDecision(fallback_decision),
                    )
                except ValueError:
                    allow_fallback = TITAN_PROVIDER_FALLBACK_ENABLED

        exec_ctx = {
            "runtime_id": run_id,
            "decision_id": decision_report.decision_id if decision_report else "",
            "allow_fallback": allow_fallback,
            "fallback_decision": fallback_decision,
            "fallback_policy": fallback_policy,
            "fallback_timeout": TITAN_FALLBACK_TIMEOUT,
        }
        if decision_report is not None and decision_report.selected_provider:
            exec_ctx["pinned_provider"] = decision_report.selected_provider
            exec_ctx["planned_provider"] = (
                decision_report.planned_provider or decision_report.selected_provider
            )
        if context is not None:
            exec_ctx["execution_mode"] = context.execution_mode.value
        tool_params["_execution_context"] = exec_ctx
        return tool_params

    def _record_provider_telemetry(
        self,
        *,
        run_id: str,
        tool_name: str,
        context: ToolExecutionContext,
        result: ToolResult,
        decision_report: ToolDecisionReport | None,
        duration_ms: float,
    ) -> None:
        """Record provider telemetry after every provider-backed execution (P10B-1005)."""
        provider_id = result.metadata.get("provider_id")
        if not provider_id or self.provider_executor is None:
            return
        from tools.providers.provider_telemetry import ProviderExecutionRecord

        execution_path = result.metadata.get("execution_path", [])
        path_tuple = tuple(execution_path) if isinstance(execution_path, list) else ()
        record = ProviderExecutionRecord(
            provider_selected=str(provider_id),
            duration_ms=float(result.metadata.get("duration_ms", duration_ms)),
            provider_health=str(result.metadata.get("provider_health", "")),
            provider_version=str(result.metadata.get("provider_version", "")),
            success=result.success,
            retry_count=int(result.metadata.get("retry_count", 0)),
            decision_id=(
                decision_report.decision_id if decision_report is not None else ""
            ),
            runtime_id=run_id,
            execution_path=path_tuple,
            tool_name=tool_name,
            action=str(result.metadata.get("action", "")),
            error=result.error or "",
            fallback_used=bool(result.metadata.get("fallback_used", False)),
            fallback_reason=str(result.metadata.get("fallback_reason", "")),
            execution_mode=context.execution_mode.value,
        )
        matching = [
            record
            for record in self.provider_executor.telemetry.list_records()
            if record.runtime_id == run_id and record.provider_selected == str(provider_id)
        ]
        if matching:
            indexed = matching[-1]
        else:
            indexed = self.provider_executor.telemetry.record(record)
        result.metadata["telemetry_record_index"] = indexed.record_index
        snapshot = self.provider_executor.telemetry.snapshot()
        result.metadata["telemetry_snapshot_at"] = snapshot.generated_at
        self._persist_telemetry_snapshot()
        if self.performance_model is not None:
            self.performance_model.invalidate(str(provider_id))

    def _persist_telemetry_snapshot(self) -> None:
        """Write provider telemetry when persistence is enabled (P10B-1101)."""
        if (
            not self.persist_telemetry
            or self.telemetry_persistence is None
            or self.provider_executor is None
        ):
            return
        self.telemetry_persistence.save_snapshot(self.provider_executor.telemetry)

    def _emit_provider_audit(
        self,
        *,
        run_id: str,
        tool_name: str,
        context: ToolExecutionContext,
        capability: ToolCapability,
        result: ToolResult,
        decision_report: ToolDecisionReport | None,
    ) -> None:
        """Emit provider telemetry audit when provider metadata is present."""
        provider_id = result.metadata.get("provider_id")
        if not provider_id:
            return
        assert self.audit_logger is not None
        latency = result.metadata.get("duration_ms")
        if latency is None:
            latency = result.metadata.get("provider_latency_ms")
        event = ToolAuditEvent.build(
            event_type="provider_executed",
            run_id=run_id,
            tool_name=tool_name,
            caller=context.caller,
            user=context.user,
            session_id=context.session_id,
            turn_id=context.turn_id,
            risk_level=capability.risk_level.value,
            success=result.success,
            duration_ms=latency,
            latency_ms=latency,
            execution_mode=context.execution_mode.value,
            health_state=str(result.metadata.get("provider_health", "")),
            provider_version=str(result.metadata.get("provider_version", "")),
            provider_name=str(provider_id),
            provider_health=str(result.metadata.get("provider_health", "")),
            fallback_used=bool(result.metadata.get("fallback_used", False)),
            fallback_reason=str(result.metadata.get("fallback_reason", "")),
            retry_count=int(result.metadata.get("retry_count", 0)),
            decision_id=(
                decision_report.decision_id if decision_report is not None else ""
            ),
            message=str(provider_id),
        )
        self.audit_logger.log(event)

    def _validate_params(self, tool_name: str, params: dict) -> str | None:
        tool = self.registry.get(tool_name)
        if tool is None:
            return f"Outil inconnu : {tool_name}"
        return tool.validate_params(params)

    def _resolve_context(
        self,
        context: ToolExecutionContext,
        capability: ToolCapability,
    ) -> ToolExecutionContext:
        """Apply global default execution mode when context has no explicit override."""
        if context.metadata.get("execution_mode_override"):
            mode = context.execution_mode
        else:
            mode = self.default_execution_mode

        if mode not in capability.supported_execution_modes:
            mode = capability.execution_mode

        if mode == context.execution_mode and context.metadata.get("execution_mode_override"):
            return context

        return ToolExecutionContext(
            caller=context.caller,
            user=context.user,
            session_id=context.session_id,
            turn_id=context.turn_id,
            confirmed=context.confirmed,
            confirmation_token=context.confirmation_token,
            dry_run=context.dry_run,
            execution_mode=mode,
            metadata=dict(context.metadata),
        )

    def _finalize_failed(
        self,
        run_id: str,
        tool_name: str,
        context: ToolExecutionContext,
        error: str,
        *,
        params_digest: str = "",
        capability: ToolCapability | None = None,
        error_code: str = "failed",
        audit_event: str = "failed",
    ) -> ToolRunOutcome:
        """Create a failed outcome with audit and optional persistence."""
        self._audit(
            event_type=audit_event,
            run_id=run_id,
            tool_name=tool_name,
            context=context,
            capability=capability,
            params_digest=params_digest,
            success=False,
            error_code=error_code,
            message=error,
        )
        failed = ToolRun(
            run_id=run_id,
            tool_name=tool_name,
            status=ToolRunStatus.FAILED,
            caller=context.caller,
            user=context.user,
            session_id=context.session_id,
            turn_id=context.turn_id,
            execution_mode=context.execution_mode,
            error=error,
            started_at=_utc_now_iso(),
            finished_at=_utc_now_iso(),
        )
        assert self.run_store is not None
        self.run_store.upsert(failed)
        return ToolRunOutcome(
            run_id=run_id,
            status=ToolRunStatus.FAILED,
            result=ToolResult(
                tool_name=tool_name,
                success=False,
                error=error,
                source="tool_runtime",
                run_id=run_id,
            ),
            error=error,
        )

    def _finalize_run(
        self,
        run_id: str,
        tool_name: str,
        context: ToolExecutionContext,
        status: ToolRunStatus,
        *,
        capability: ToolCapability | None = None,
        params_digest: str = "",
        health_state: ToolHealthState = ToolHealthState.UNKNOWN,
        result: ToolResult | None = None,
        error: str = "",
        duration_ms: float | None = None,
        audit_event: str = "completed",
        error_code: str = "",
        success: bool | None = None,
    ) -> ToolRunOutcome:
        """Persist terminal run state and emit audit."""
        finished = ToolRun(
            run_id=run_id,
            tool_name=tool_name,
            status=status,
            caller=context.caller,
            user=context.user,
            session_id=context.session_id,
            turn_id=context.turn_id,
            execution_mode=context.execution_mode,
            health_state=health_state,
            result=result,
            error=error,
            finished_at=_utc_now_iso(),
        )
        assert self.run_store is not None
        existing = self.run_store.get(run_id)
        if existing is not None and existing.started_at:
            finished.started_at = existing.started_at
        else:
            finished.started_at = _utc_now_iso()
        self.run_store.upsert(finished)

        self._audit(
            event_type=audit_event,
            run_id=run_id,
            tool_name=tool_name,
            context=context,
            capability=capability,
            params_digest=params_digest,
            health_state=health_state,
            success=success if success is not None else (result.success if result else False),
            duration_ms=duration_ms,
            error_code=error_code,
            message=error,
        )
        assert self.cancellation_registry is not None
        self.cancellation_registry.unregister(run_id)

        return ToolRunOutcome(
            run_id=run_id,
            status=status,
            result=result,
            error=error,
        )

    def _run_to_outcome(self, run: ToolRun) -> ToolRunOutcome:
        """Convert a stored ToolRun to a ToolRunOutcome."""
        return ToolRunOutcome(
            run_id=run.run_id,
            status=run.status,
            result=run.result,
            events=list(run.events),
            error=run.error,
        )

    def _audit(
        self,
        *,
        event_type: str,
        run_id: str,
        tool_name: str,
        context: ToolExecutionContext,
        capability: ToolCapability | None = None,
        params_digest: str = "",
        health_state: ToolHealthState | str = "",
        success: bool | None = None,
        duration_ms: float | None = None,
        error_code: str = "",
        message: str = "",
        dependencies_checked: bool = False,
        provider_name: str = "",
        provider_health: str = "",
        fallback_used: bool = False,
        fallback_reason: str = "",
        retry_count: int = 0,
        decision_id: str = "",
        latency_ms: float | None = None,
    ) -> None:
        """Emit a structured audit event."""
        assert self.audit_logger is not None
        health_value = (
            health_state.value
            if isinstance(health_state, ToolHealthState)
            else str(health_state)
        )
        quota_remaining = None
        provider_version = ""
        if capability is not None:
            quota_remaining = self.quota_tracker.remaining_daily(tool_name, capability.quota)
            if capability.provider_name:
                assert self.provider_registry is not None
                provider_version = self.provider_registry.version_for(capability.provider_name)

        event = ToolAuditEvent.build(
            event_type=event_type,
            run_id=run_id,
            tool_name=tool_name,
            caller=context.caller,
            user=context.user,
            session_id=context.session_id,
            turn_id=context.turn_id,
            risk_level=capability.risk_level.value if capability else "",
            success=success,
            duration_ms=duration_ms,
            error_code=error_code,
            params_digest=params_digest,
            execution_mode=context.execution_mode.value,
            health_state=health_value,
            provider_version=provider_version,
            quota_remaining=quota_remaining,
            dependencies_checked=dependencies_checked,
            message=message,
            provider_name=provider_name,
            provider_health=provider_health,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            retry_count=retry_count,
            decision_id=decision_id,
            latency_ms=latency_ms if latency_ms is not None else duration_ms,
        )
        self.audit_logger.log(event)

    def _load_persisted_metrics(self) -> None:
        """Restore metrics and quota counters when persistence is enabled."""
        if not self.persist_metrics:
            return
        metrics, quota_usage = MetricsCollector.load_persisted(self.metrics_path)
        if metrics:
            self.metrics_collector.load_snapshot(metrics)
        if quota_usage:
            self.quota_tracker.load_snapshot(quota_usage)

    def _persist_metrics_snapshot(self) -> None:
        """Write metrics and quota counters when persistence is enabled."""
        if not self.persist_metrics:
            return
        self.metrics_collector.persist(
            self.metrics_path,
            quota_usage=self.quota_tracker.usage_snapshot(),
        )

    @staticmethod
    def _failed(run_id: str, tool_name: str, error: str) -> ToolRunOutcome:
        return ToolRunOutcome(
            run_id=run_id,
            status=ToolRunStatus.FAILED,
            result=ToolResult(
                tool_name=tool_name,
                success=False,
                error=error,
                source="tool_runtime",
                run_id=run_id,
            ),
            error=error,
        )

    def outcome_to_result(self, outcome: ToolRunOutcome) -> ToolResult:
        """Convert a runtime outcome to legacy ToolResult for backward compatibility."""
        if outcome.status == ToolRunStatus.PENDING_CONFIRMATION:
            tool_name = (
                outcome.confirmation_request.tool_name
                if outcome.confirmation_request is not None
                else "unknown"
            )
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=outcome.to_prompt_block(),
                source="confirmation_gate",
                run_id=outcome.run_id,
                metadata={
                    "pending_confirmation": True,
                    "confirmation_token": (
                        outcome.confirmation_request.token
                        if outcome.confirmation_request is not None
                        else None
                    ),
                },
            )
        if outcome.status == ToolRunStatus.QUEUED:
            tool_name = "unknown"
            if self.run_store is not None:
                run = self.run_store.get(outcome.run_id)
                if run is not None:
                    tool_name = run.tool_name
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=outcome.error or "Exécution asynchrone en cours",
                source="async_executor",
                run_id=outcome.run_id,
                metadata={"queued": True},
            )
        if outcome.result is not None:
            return outcome.result
        return ToolResult(
            tool_name="unknown",
            success=False,
            error=outcome.error or "Échec d'exécution",
            source="tool_runtime",
            run_id=outcome.run_id,
        )
