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
    TITAN_TOOL_AUDIT_ENABLED,
    TITAN_TOOL_DEFAULT_EXECUTION_MODE,
    TITAN_TOOL_PERSIST_METRICS,
    TITAN_TOOL_PERSIST_RUNS,
    TITAN_TOOL_POLL_TIMEOUT_SECONDS,
    TITAN_TOOL_QUOTA_ENABLED,
    TOOL_METRICS_PATH,
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
from tools.cancellation_registry import CancellationRegistry
from tools.confirmation_gate import ConfirmationGate
from tools.dependency_resolver import DependencyResolver
from tools.executors.async_executor import AsyncExecutor
from tools.executors.sync_executor import SyncExecutor
from tools.health_monitor import HealthMonitor
from tools.permission_engine import PermissionEngine
from tools.providers.defaults import register_default_providers
from tools.providers.provider_registry import ProviderRegistry
from tools.retry_policy import RetryPolicy
from tools.tool_capability import ToolCapability
from tools.tool_enums import ExecutionMode, InvocationMode, ToolHealthState
from tools.tool_metrics import MetricsCollector
from tools.tool_quota import QuotaTracker
from tools.tool_registry import ToolRegistry
from tools.tool_result import ToolResult
from tools.tool_run_models import ToolExecutionContext, ToolRun, ToolRunOutcome, ToolRunStatus
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
    confirmation_gate: ConfirmationGate | None = None
    sync_executor: SyncExecutor | None = None
    async_executor: AsyncExecutor | None = None
    cancellation_registry: CancellationRegistry | None = None
    run_store: ToolRunStore | None = None
    audit_logger: ToolAuditLogger | None = None
    provider_registry: ProviderRegistry | None = None
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    default_execution_mode: ExecutionMode = field(
        default_factory=lambda: _parse_execution_mode(TITAN_TOOL_DEFAULT_EXECUTION_MODE)
    )
    persist_runs: bool = TITAN_TOOL_PERSIST_RUNS
    persist_metrics: bool = TITAN_TOOL_PERSIST_METRICS
    metrics_path: Path = field(default_factory=lambda: TOOL_METRICS_PATH)
    poll_timeout_seconds: float = float(TITAN_TOOL_POLL_TIMEOUT_SECONDS)

    def __post_init__(self) -> None:
        if self.permission_engine is None:
            self.permission_engine = PermissionEngine(policy=self.policy)
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
            self.provider_registry = ProviderRegistry()
        self.dependency_resolver.health_monitor = self.health_monitor
        register_default_providers(self.provider_registry)
        self._wire_providers()
        self.quota_tracker.enabled = TITAN_TOOL_QUOTA_ENABLED
        self._load_persisted_metrics()
        register_legacy_tools(self.registry, self.catalog, self.dependency_resolver)

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
            self._preflight(tool_name, capability, effective_context)
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
            result = self._execute_with_retries(tool_name, params, capability, run_id=run_id)
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
    ) -> None:
        """Run permission, quota, dependency, and health gates."""
        assert self.permission_engine is not None

        permission = self.permission_engine.evaluate(tool_name, capability, context)
        if not permission.allowed:
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

        if decision_report is not None and not decision_report.confirmation_required:
            return None

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
    ) -> ToolResult:
        """Execute via sync executor with optional retries and cancellation checks."""
        assert self.sync_executor is not None
        assert self.cancellation_registry is not None
        max_retries = capability.max_retries
        attempt = 0
        result = ToolResult(tool_name=tool_name, success=False, error="Aucune tentative")

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
                params,
                timeout_seconds=capability.timeout_seconds,
            )
            if not self.retry_policy.should_retry(attempt, max_retries, result):
                return result
            time.sleep(self.retry_policy.delay_seconds(attempt))

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
