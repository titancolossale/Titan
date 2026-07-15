# =====================================
# Titan Provider Executor
# =====================================

"""Central provider execution layer — registry-authoritative dispatch (P10B-201, P10B-801)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from tools.health_monitor import HealthMonitor
from tools.providers.provider_fallback_policy import (
    FallbackDecision,
    ProviderFallbackPolicy,
    format_fallback_user_notice,
)
from tools.provider_version import ProviderHealth
from tools.providers.provider_performance_model import ProviderPerformanceModel
from tools.providers.base_provider import BaseProvider
from tools.providers.calendar_provider import CalendarProvider
from tools.providers.file_system_provider import FileSystemProvider, FileSystemResponse
from tools.providers.github_provider import GitHubProvider, GitHubResponse
from tools.providers.provider_registry import ProviderRegistry
from tools.providers.provider_telemetry import ProviderExecutionRecord, ProviderTelemetryCollector
from tools.providers.provider_failure import ProviderFailureReason, health_state_for_failure
from tools.providers.web_search_provider import SearchResponse, WebSearchProvider
from tools.tool_enums import ExecutionMode, ToolHealthState

_BLOCKED_STATES = frozenset({
    ToolHealthState.OFFLINE,
    ToolHealthState.DISABLED,
    ToolHealthState.MISCONFIGURED,
    ToolHealthState.MISSING_CREDENTIALS,
})

_HEALTH_SCORE: dict[ToolHealthState, float] = {
    ToolHealthState.ONLINE: 100.0,
    ToolHealthState.DEGRADED: 50.0,
    ToolHealthState.UNKNOWN: 25.0,
    ToolHealthState.OFFLINE: 0.0,
    ToolHealthState.DISABLED: 0.0,
    ToolHealthState.MISCONFIGURED: 0.0,
    ToolHealthState.MISSING_CREDENTIALS: 0.0,
}


@dataclass
class ProviderExecutionContext:
    """Context passed to provider execution for telemetry correlation."""

    action: str
    params: dict
    execution_mode: ExecutionMode
    tool_name: str = ""
    runtime_id: str = ""
    decision_id: str = ""
    pinned_provider: str | None = None
    planned_provider: str | None = None
    allow_fallback: bool = False
    fallback_decision: str = ""
    fallback_policy: str = ""
    fallback_timeout: float = 30.0

    @classmethod
    def from_tool_metadata(
        cls,
        *,
        action: str,
        params: dict,
        tool_name: str,
        ctx_meta: dict,
    ) -> ProviderExecutionContext:
        """Build execution context from ToolRuntime _execution_context metadata."""
        execution_mode = ExecutionMode(
            str(ctx_meta.get("execution_mode", ExecutionMode.LIVE.value)),
        )
        return cls(
            action=action,
            params=params,
            execution_mode=execution_mode,
            tool_name=tool_name,
            runtime_id=str(ctx_meta.get("runtime_id", "")),
            decision_id=str(ctx_meta.get("decision_id", "")),
            pinned_provider=(
                str(ctx_meta["pinned_provider"])
                if ctx_meta.get("pinned_provider")
                else None
            ),
            planned_provider=(
                str(ctx_meta["planned_provider"])
                if ctx_meta.get("planned_provider")
                else None
            ),
            allow_fallback=bool(ctx_meta.get("allow_fallback", False)),
            fallback_decision=str(ctx_meta.get("fallback_decision", "")),
            fallback_policy=str(ctx_meta.get("fallback_policy", "")),
            fallback_timeout=float(ctx_meta.get("fallback_timeout", 30.0)),
        )


@dataclass
class ProviderExecutionResult:
    """Outcome of provider execution including fallback path."""

    success: bool
    provider_id: str = ""
    data: object = None
    error: str = ""
    execution_path: tuple[str, ...] = ()
    no_capability: bool = False
    duration_ms: float = 0.0
    retry_count: int = 0
    provider_health: ToolHealthState = ToolHealthState.UNKNOWN
    provider_version: str = ""
    provider_score: float = 0.0
    fallback_used: bool = False
    provider_unavailable: bool = False
    planned_provider: str | None = None
    execution_provider: str | None = None
    provider_changed: bool = False
    provider_change_reason: str = ""
    fallback_reason: str = ""
    original_provider: str | None = None
    replacement_provider: str | None = None


def provider_outcome_metadata(outcome: ProviderExecutionResult) -> dict:
    """Serialize provider execution outcome for ToolResult metadata (P10B-805)."""
    metadata = {
        "provider_id": outcome.provider_id,
        "provider_version": outcome.provider_version,
        "provider_health": outcome.provider_health.value,
        "provider_score": outcome.provider_score,
        "execution_path": list(outcome.execution_path),
        "duration_ms": outcome.duration_ms,
        "provider_latency_ms": outcome.duration_ms,
        "retry_count": outcome.retry_count,
        "fallback_used": outcome.fallback_used,
        "provider_unavailable": outcome.provider_unavailable,
        "planned_provider": outcome.planned_provider,
        "execution_provider": outcome.execution_provider or outcome.provider_id,
        "provider_changed": outcome.provider_changed,
        "provider_change_reason": outcome.provider_change_reason,
        "fallback_reason": outcome.fallback_reason,
        "original_provider": outcome.original_provider,
        "replacement_provider": outcome.replacement_provider,
    }
    if outcome.no_capability:
        metadata["no_capability"] = True
    return metadata


@dataclass
class ProviderExecutor:
    """Execute provider actions exclusively through ProviderRegistry."""

    registry: ProviderRegistry
    health_monitor: HealthMonitor
    telemetry: ProviderTelemetryCollector = field(default_factory=ProviderTelemetryCollector)
    performance_model: ProviderPerformanceModel | None = None

    def execute(
        self,
        action: str,
        params: dict,
        *,
        capability: str | None = None,
        context: ProviderExecutionContext | None = None,
        execution_mode: ExecutionMode | None = None,
    ) -> ProviderExecutionResult:
        """Execute via pinned provider when set; otherwise legacy ranked routing."""
        ctx = context or ProviderExecutionContext(
            action=action,
            params=params,
            execution_mode=execution_mode or ExecutionMode.LIVE,
        )
        mode = execution_mode or ctx.execution_mode

        if ctx.pinned_provider:
            return self._execute_pinned(
                ctx.pinned_provider,
                action,
                params,
                capability=capability,
                context=ctx,
                mode=mode,
            )

        return self._execute_ranked(
            action,
            params,
            capability=capability,
            context=ctx,
            mode=mode,
        )

    def _execute_pinned(
        self,
        pinned_id: str,
        action: str,
        params: dict,
        *,
        capability: str | None,
        context: ProviderExecutionContext,
        mode: ExecutionMode,
    ) -> ProviderExecutionResult:
        """Execute the Brain-selected provider without independent re-ranking (P10B-802)."""
        perf_start = time.perf_counter()
        planned = context.planned_provider or pinned_id
        unavailable_reason = self._provider_unavailable_reason(
            pinned_id,
            action,
            capability=capability,
            mode=mode,
        )

        if unavailable_reason is not None:
            decision = self._resolve_fallback_decision(context)
            if decision == FallbackDecision.ABORT:
                return self._policy_abort_result(
                    pinned_id, planned, unavailable_reason, perf_start, context, action,
                )
            if decision == FallbackDecision.REQUEST_CONFIRMATION:
                return self._policy_confirmation_result(
                    pinned_id, planned, unavailable_reason, perf_start, context, action,
                )
            if decision == FallbackDecision.RETRY_ORIGINAL:
                retry_result = self._try_provider(
                    pinned_id,
                    action,
                    params,
                    mode,
                    score=self._score_for_provider(pinned_id, action, mode),
                    context=context,
                    execution_path=[pinned_id],
                    retry_count=1,
                    perf_start=perf_start,
                )
                if retry_result.success:
                    return self._finalize_pinned_result(
                        retry_result,
                        planned_provider=planned,
                        pinned_id=pinned_id,
                    )
                unavailable_reason = (
                    retry_result.error or unavailable_reason
                )
                if (
                    self._resolve_fallback_decision(context)
                    == FallbackDecision.ALLOW_FALLBACK
                    or context.allow_fallback
                ):
                    return self._execute_fallback_routing(
                        action,
                        params,
                        capability=capability,
                        context=context,
                        mode=mode,
                        original_provider=pinned_id,
                        planned_provider=planned,
                        fallback_reason=unavailable_reason,
                        perf_start=perf_start,
                    )
                return self._pinned_unavailable_result(
                    pinned_id,
                    planned,
                    unavailable_reason,
                    perf_start,
                    context,
                    action,
                )

            if decision == FallbackDecision.ALLOW_FALLBACK:
                return self._execute_fallback_routing(
                    action,
                    params,
                    capability=capability,
                    context=context,
                    mode=mode,
                    original_provider=pinned_id,
                    planned_provider=planned,
                    fallback_reason=unavailable_reason,
                    perf_start=perf_start,
                )
            return self._pinned_unavailable_result(
                pinned_id,
                planned,
                unavailable_reason,
                perf_start,
                context,
                action,
            )

        score = self._score_for_provider(pinned_id, action, mode)
        result = self._try_provider(
            pinned_id,
            action,
            params,
            mode,
            score=score,
            context=context,
            execution_path=[pinned_id],
            retry_count=0,
            perf_start=perf_start,
        )
        return self._finalize_pinned_result(
            result,
            planned_provider=planned,
            pinned_id=pinned_id,
        )

    def _execute_fallback_routing(
        self,
        action: str,
        params: dict,
        *,
        capability: str | None,
        context: ProviderExecutionContext,
        mode: ExecutionMode,
        original_provider: str,
        planned_provider: str,
        fallback_reason: str,
        perf_start: float,
    ) -> ProviderExecutionResult:
        """Second routing pass when policy allows fallback (P10B-804)."""
        candidates = self.registry.select_providers(
            action,
            mode,
            capability=capability,
            health_monitor=self.health_monitor,
            performance_model=self.performance_model,
        )
        candidates = [
            (provider_id, score)
            for provider_id, score in candidates
            if provider_id != original_provider
        ]
        if not candidates:
            return self._pinned_unavailable_result(
                original_provider,
                planned_provider,
                fallback_reason,
                perf_start,
                context,
                action,
            )

        execution_path = [original_provider]
        retry_count = 0
        for provider_id, score in candidates:
            execution_path.append(provider_id)
            result = self._try_provider(
                provider_id,
                action,
                params,
                mode,
                score=score,
                context=context,
                execution_path=list(execution_path),
                retry_count=retry_count,
                perf_start=perf_start,
            )
            if result.success or self._is_terminal_failure(result):
                result.fallback_used = True
                result.fallback_reason = fallback_reason
                result.original_provider = original_provider
                result.replacement_provider = provider_id
                result.planned_provider = planned_provider
                result.execution_provider = provider_id
                result.provider_changed = provider_id != planned_provider
                if result.provider_changed:
                    result.provider_change_reason = fallback_reason
                return result
            retry_count += 1

        duration_ms = (time.perf_counter() - perf_start) * 1000.0
        last_id = execution_path[-1] if execution_path else original_provider
        return ProviderExecutionResult(
            success=False,
            provider_id=last_id,
            error=(
                f"Provider planifié {original_provider!r} indisponible "
                f"({fallback_reason}) et aucun remplacement n'a réussi."
            ),
            execution_path=tuple(execution_path),
            no_capability=True,
            duration_ms=duration_ms,
            retry_count=retry_count,
            provider_health=self.registry.probe(last_id).state,
            provider_version=self.registry.version_for(last_id) if last_id else "",
            provider_unavailable=True,
            planned_provider=planned_provider,
            execution_provider=last_id,
            provider_changed=last_id != planned_provider,
            provider_change_reason=fallback_reason,
            fallback_used=True,
            fallback_reason=fallback_reason,
            original_provider=original_provider,
            replacement_provider=last_id if last_id != original_provider else None,
        )

    def _execute_ranked(
        self,
        action: str,
        params: dict,
        *,
        capability: str | None,
        context: ProviderExecutionContext,
        mode: ExecutionMode,
    ) -> ProviderExecutionResult:
        """Legacy ranked provider selection when no Brain pin is present."""
        candidates = self.registry.select_providers(
            action,
            mode,
            capability=capability,
            health_monitor=self.health_monitor,
            performance_model=self.performance_model,
        )
        if not candidates:
            return self._no_capability_result(action, capability)

        execution_path: list[str] = []
        retry_count = 0
        perf_start = time.perf_counter()

        for provider_id, score in candidates:
            execution_path.append(provider_id)
            result = self._try_provider(
                provider_id,
                action,
                params,
                mode,
                score=score,
                context=context,
                execution_path=list(execution_path),
                retry_count=retry_count,
                perf_start=perf_start,
            )
            if result.success:
                result.fallback_used = len(execution_path) > 1
                result.execution_provider = provider_id
                return result
            if self._is_terminal_failure(result):
                return result
            retry_count += 1

        duration_ms = (time.perf_counter() - perf_start) * 1000.0
        last_id = execution_path[-1] if execution_path else ""
        last_health = self.registry.probe(last_id) if last_id else ProviderHealth(
            state=ToolHealthState.OFFLINE,
            message="Aucun provider disponible",
        )
        record = self._telemetry_record(
            provider_id=last_id,
            duration_ms=duration_ms,
            health=last_health.state,
            success=False,
            retry_count=retry_count,
            context=context,
            action=action,
            execution_path=list(execution_path),
            error="Tous les providers compatibles ont échoué ou sont indisponibles.",
            fallback_used=len(execution_path) > 1,
        )
        self.telemetry.record(record)
        return ProviderExecutionResult(
            success=False,
            provider_id=last_id,
            error=record.error,
            execution_path=tuple(execution_path),
            no_capability=True,
            duration_ms=duration_ms,
            retry_count=retry_count,
            provider_health=last_health.state,
            provider_version=self.registry.version_for(last_id) if last_id else "",
            provider_score=0.0,
            execution_provider=last_id or None,
        )

    def _try_provider(
        self,
        provider_id: str,
        action: str,
        params: dict,
        mode: ExecutionMode,
        *,
        score: float,
        context: ProviderExecutionContext,
        execution_path: list[str],
        retry_count: int,
        perf_start: float,
    ) -> ProviderExecutionResult:
        """Attempt a single provider invocation."""
        provider = self.registry.get(provider_id)
        if provider is None:
            return ProviderExecutionResult(
                success=False,
                provider_id=provider_id,
                error=f"Provider {provider_id!r} introuvable.",
                execution_path=tuple(execution_path),
            )

        health = self.registry.probe(provider_id)
        monitor_state = self.health_monitor.get_provider_health(provider_id)
        if monitor_state in _BLOCKED_STATES:
            return ProviderExecutionResult(
                success=False,
                provider_id=provider_id,
                error=(
                    f"Provider {provider_id!r} indisponible "
                    f"(health monitor {monitor_state.value})."
                ),
                execution_path=tuple(execution_path),
                provider_health=monitor_state,
                provider_unavailable=True,
            )
        if health.state in _BLOCKED_STATES:
            return ProviderExecutionResult(
                success=False,
                provider_id=provider_id,
                error=f"Provider {provider_id!r} indisponible ({health.state.value}).",
                execution_path=tuple(execution_path),
                provider_health=health.state,
                provider_unavailable=True,
            )
        if not provider.supports_execution_mode(mode):
            return ProviderExecutionResult(
                success=False,
                provider_id=provider_id,
                error=f"Provider {provider_id!r} ne supporte pas le mode {mode.value}.",
                execution_path=tuple(execution_path),
                provider_health=health.state,
                provider_unavailable=True,
            )

        invoke_ok, data, error = self._invoke(provider, action, params)
        duration_ms = (time.perf_counter() - perf_start) * 1000.0

        if invoke_ok:
            self.health_monitor.set_provider_health(provider_id, ToolHealthState.ONLINE)
            self.telemetry.observe_health(provider_id, ToolHealthState.ONLINE.value)
            record = self._telemetry_record(
                provider_id=provider_id,
                duration_ms=duration_ms,
                health=health,
                success=True,
                retry_count=retry_count,
                context=context,
                action=action,
                execution_path=execution_path,
            )
            self.telemetry.record(record)
            return ProviderExecutionResult(
                success=True,
                provider_id=provider_id,
                data=data,
                execution_path=tuple(execution_path),
                duration_ms=duration_ms,
                retry_count=retry_count,
                provider_health=health.state,
                provider_version=self.registry.version_for(provider_id),
                provider_score=score,
                execution_provider=provider_id,
            )

        if isinstance(data, FileSystemResponse):
            record = self._telemetry_record(
                provider_id=provider_id,
                duration_ms=duration_ms,
                health=health,
                success=False,
                retry_count=retry_count,
                context=context,
                action=action,
                execution_path=execution_path,
                error=data.error or error,
            )
            self.telemetry.record(record)
            return ProviderExecutionResult(
                success=False,
                provider_id=provider_id,
                data=data,
                error=data.error or error,
                execution_path=tuple(execution_path),
                duration_ms=duration_ms,
                retry_count=retry_count,
                provider_health=health.state,
                provider_version=self.registry.version_for(provider_id),
                provider_score=score,
                execution_provider=provider_id,
            )

        if isinstance(data, GitHubResponse):
            self._apply_failure_health(provider_id, data, error)
            record = self._telemetry_record(
                provider_id=provider_id,
                duration_ms=duration_ms,
                health=health,
                success=False,
                retry_count=retry_count,
                context=context,
                action=action,
                execution_path=execution_path,
                error=data.error or error,
            )
            self.telemetry.record(record)
            return ProviderExecutionResult(
                success=False,
                provider_id=provider_id,
                data=data,
                error=data.error or error,
                execution_path=tuple(execution_path),
                duration_ms=duration_ms,
                retry_count=retry_count,
                provider_health=health.state,
                provider_version=self.registry.version_for(provider_id),
                provider_score=score,
                execution_provider=provider_id,
            )

        self._apply_failure_health(provider_id, data, error)
        record = self._telemetry_record(
            provider_id=provider_id,
            duration_ms=duration_ms,
            health=health,
            success=False,
            retry_count=retry_count,
            context=context,
            action=action,
            execution_path=execution_path,
            error=error,
        )
        self.telemetry.record(record)
        return ProviderExecutionResult(
            success=False,
            provider_id=provider_id,
            error=error,
            execution_path=tuple(execution_path),
            duration_ms=duration_ms,
            retry_count=retry_count,
            provider_health=health.state,
            provider_version=self.registry.version_for(provider_id),
            provider_score=score,
            execution_provider=provider_id,
        )

    def _resolve_fallback_decision(
        self,
        context: ProviderExecutionContext,
        *,
        after_retry: bool = False,
    ) -> FallbackDecision:
        """Resolve effective fallback decision from Brain policy context (P10B-904)."""
        raw = context.fallback_decision
        if raw:
            try:
                return FallbackDecision(raw)
            except ValueError:
                pass
        if context.allow_fallback:
            return FallbackDecision.ALLOW_FALLBACK
        if after_retry:
            return FallbackDecision.DENY_FALLBACK
        return FallbackDecision.DENY_FALLBACK

    def _policy_abort_result(
        self,
        pinned_id: str,
        planned: str,
        reason: str,
        perf_start: float,
        context: ProviderExecutionContext,
        action: str,
    ) -> ProviderExecutionResult:
        """Return structured abort when policy forbids retry and fallback."""
        result = self._pinned_unavailable_result(
            pinned_id, planned, reason, perf_start, context, action,
        )
        result.error = (
            f"Exécution interrompue — provider {pinned_id!r} indisponible "
            f"({reason}) et repli/refessai interdits par la politique."
        )
        return result

    def _policy_confirmation_result(
        self,
        pinned_id: str,
        planned: str,
        reason: str,
        perf_start: float,
        context: ProviderExecutionContext,
        action: str,
    ) -> ProviderExecutionResult:
        """Return structured confirmation request before cross-provider fallback."""
        duration_ms = (time.perf_counter() - perf_start) * 1000.0
        health = self.registry.probe(pinned_id)
        error = (
            f"Confirmation requise — provider {pinned_id!r} indisponible ({reason}). "
            "Confirme le repli cross-provider avant exécution."
        )
        return ProviderExecutionResult(
            success=False,
            provider_id=pinned_id,
            error=error,
            execution_path=(pinned_id,),
            no_capability=True,
            duration_ms=duration_ms,
            provider_health=health.state,
            provider_version=self.registry.version_for(pinned_id),
            provider_unavailable=True,
            planned_provider=planned,
            execution_provider=None,
            original_provider=pinned_id,
            fallback_reason=reason,
        )

    def _pinned_unavailable_result(
        self,
        pinned_id: str,
        planned: str,
        reason: str,
        perf_start: float,
        context: ProviderExecutionContext,
        action: str,
    ) -> ProviderExecutionResult:
        """Return structured unavailable response without silent replacement (P10B-803)."""
        duration_ms = (time.perf_counter() - perf_start) * 1000.0
        health = self.registry.probe(pinned_id)
        error = (
            f"Provider sélectionné {pinned_id!r} indisponible avant exécution : {reason}"
        )
        record = self._telemetry_record(
            provider_id=pinned_id,
            duration_ms=duration_ms,
            health=health.state,
            success=False,
            retry_count=0,
            context=context,
            action=action,
            execution_path=[pinned_id],
            error=error,
            fallback_reason=reason,
        )
        self.telemetry.record(record)
        return ProviderExecutionResult(
            success=False,
            provider_id=pinned_id,
            error=error,
            execution_path=(pinned_id,),
            no_capability=True,
            duration_ms=duration_ms,
            provider_health=health.state,
            provider_version=self.registry.version_for(pinned_id),
            provider_unavailable=True,
            planned_provider=planned,
            execution_provider=None,
            original_provider=pinned_id,
            fallback_reason=reason,
        )

    @staticmethod
    def _finalize_pinned_result(
        result: ProviderExecutionResult,
        *,
        planned_provider: str,
        pinned_id: str,
    ) -> ProviderExecutionResult:
        """Attach pinning metadata to a direct provider execution result."""
        result.planned_provider = planned_provider
        result.execution_provider = result.provider_id or pinned_id
        result.provider_changed = result.execution_provider != planned_provider
        if result.provider_changed:
            result.provider_change_reason = (
                f"Exécution sur {result.execution_provider!r} "
                f"au lieu du provider planifié {planned_provider!r}."
            )
        return result

    def _provider_unavailable_reason(
        self,
        provider_id: str,
        action: str,
        *,
        capability: str | None,
        mode: ExecutionMode,
    ) -> str | None:
        """Return reason when pinned provider cannot run (P10B-806)."""
        provider = self.registry.get(provider_id)
        if provider is None:
            return "provider not registered"
        if capability and capability not in provider.capabilities():
            return f"capability {capability!r} not supported"
        if action not in provider.supported_actions():
            return f"action {action!r} not supported"
        if not provider.supports_execution_mode(mode):
            return f"execution mode {mode.value} not supported"
        monitor_state = self.health_monitor.get_provider_health(provider_id)
        if monitor_state in _BLOCKED_STATES:
            return f"health monitor state {monitor_state.value}"
        health = self.registry.probe(provider_id)
        if health.state in _BLOCKED_STATES:
            return f"probe state {health.state.value}"
        return None

    def _score_for_provider(
        self,
        provider_id: str,
        action: str,
        mode: ExecutionMode,
    ) -> float:
        """Score pinned provider for telemetry without re-ranking."""
        provider = self.registry.get(provider_id)
        if provider is None:
            return 0.0
        health = self.registry.probe(provider_id)
        score = _HEALTH_SCORE.get(health.state, 0.0)
        if action in provider.supported_actions():
            score += 10.0
        if provider.supports_execution_mode(mode):
            score += 5.0
        return score

    @staticmethod
    def _is_terminal_failure(result: ProviderExecutionResult) -> bool:
        """Failures that must not trigger ranked retry in pinned mode."""
        return isinstance(result.data, (FileSystemResponse, GitHubResponse))

    def score_provider(self, provider_id: str) -> float:
        """Return selection score for a provider based on health."""
        health = self.registry.probe(provider_id)
        return _HEALTH_SCORE.get(health.state, 0.0)

    @staticmethod
    def _invoke(
        provider: BaseProvider,
        action: str,
        params: dict,
    ) -> tuple[bool, object, str]:
        """Dispatch action to provider without direct instantiation."""
        if isinstance(provider, WebSearchProvider):
            query = str(params.get("query", "")).strip()
            search_kwargs = ProviderExecutor._search_kwargs(params)
            if action == "search":
                response = provider.search(query, **search_kwargs)
                return response.success, response, response.error
            if action == "news":
                response = provider.news(query, **search_kwargs)
                return response.success, response, response.error
        elif isinstance(provider, CalendarProvider):
            cal_action = str(params.get("action", action or "list"))
            response = provider.execute(cal_action, **params)
            return response.success, response, response.error
        elif isinstance(provider, FileSystemProvider):
            fs_action = action or str(params.get("action", ""))
            fs_params = {key: value for key, value in params.items() if key != "action"}
            response = provider.execute(fs_action, **fs_params)
            return response.success, response, response.error
        elif isinstance(provider, GitHubProvider):
            gh_action = action or str(params.get("action", ""))
            gh_params = {key: value for key, value in params.items() if key != "action"}
            response = provider.execute(gh_action, **gh_params)
            return response.success, response, response.error
        return False, None, f"Action non supportée : {action!r}"

    @staticmethod
    def _search_kwargs(params: dict) -> dict:
        """Extract optional search parameters for provider dispatch."""
        kwargs: dict = {"max_results": int(params.get("max_results", params.get("top_k", 5)))}
        if params.get("top_k") is not None:
            kwargs["top_k"] = int(params["top_k"])
        if params.get("freshness") is not None:
            kwargs["freshness"] = str(params["freshness"])
        if params.get("safe_search") is not None:
            kwargs["safe_search"] = str(params["safe_search"])
        if params.get("timeout") is not None:
            kwargs["timeout"] = float(params["timeout"])
        return kwargs

    def _telemetry_record(
        self,
        *,
        provider_id: str,
        duration_ms: float,
        health: ToolHealthState | ProviderHealth,
        success: bool,
        retry_count: int,
        context: ProviderExecutionContext,
        action: str,
        execution_path: list[str],
        error: str = "",
        fallback_used: bool = False,
        fallback_reason: str = "",
    ) -> ProviderExecutionRecord:
        """Build a provider telemetry record with fallback metadata (P10B-1002)."""
        health_state = health.state if isinstance(health, ProviderHealth) else health
        path_tuple = tuple(execution_path)
        used_fallback = fallback_used or len(path_tuple) > 1
        return ProviderExecutionRecord(
            provider_selected=provider_id,
            duration_ms=duration_ms,
            provider_health=health_state.value,
            provider_version=self.registry.version_for(provider_id) if provider_id else "",
            success=success,
            retry_count=retry_count,
            decision_id=context.decision_id,
            runtime_id=context.runtime_id,
            execution_path=path_tuple,
            tool_name=context.tool_name,
            action=action,
            error=error,
            fallback_used=used_fallback,
            fallback_reason=fallback_reason,
            execution_mode=context.execution_mode.value,
        )

    def _apply_failure_health(
        self,
        provider_id: str,
        data: object,
        error: str,
    ) -> None:
        """Update HealthMonitor after a provider failure (P10B-404)."""
        reason: ProviderFailureReason | None = None
        if isinstance(data, SearchResponse) and data.failure_reason:
            try:
                reason = ProviderFailureReason(data.failure_reason)
            except ValueError:
                reason = ProviderFailureReason.UNKNOWN
        elif isinstance(data, GitHubResponse) and data.failure_reason:
            try:
                reason = ProviderFailureReason(data.failure_reason)
            except ValueError:
                reason = ProviderFailureReason.UNKNOWN
        if reason is None:
            lowered = error.lower()
            if "rate" in lowered:
                reason = ProviderFailureReason.RATE_LIMIT
            elif "timeout" in lowered or "délai" in lowered:
                reason = ProviderFailureReason.TIMEOUT
            elif "clé" in lowered or "key" in lowered or "credential" in lowered:
                reason = ProviderFailureReason.INVALID_KEY
            elif "offline" in lowered or "503" in lowered:
                reason = ProviderFailureReason.OFFLINE
            elif "network" in lowered or "réseau" in lowered:
                reason = ProviderFailureReason.NETWORK_ERROR
            else:
                reason = ProviderFailureReason.UNKNOWN
        state = health_state_for_failure(reason)
        previous = self.health_monitor.get_provider_health(provider_id)
        self.health_monitor.set_provider_health(provider_id, state)
        self.telemetry.record_health_transition(
            provider_id,
            previous.value,
            state.value,
            reason=reason.value,
        )
        self.telemetry.observe_health(provider_id, state.value)

    @staticmethod
    def _no_capability_result(action: str, capability: str | None) -> ProviderExecutionResult:
        cap_label = capability or action
        return ProviderExecutionResult(
            success=False,
            no_capability=True,
            error=(
                f"Capacité indisponible — aucun provider compatible pour "
                f"{cap_label!r}."
            ),
            execution_path=(),
        )
