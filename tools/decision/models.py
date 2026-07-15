# =====================================
# Titan Tool Decision — Models
# =====================================

"""Structured decision artifacts for the Tool Decision Engine (Phase 10B — P10B-005)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum

from tools.decision.intent import Intent
from tools.tool_enums import RiskLevel


class FallbackAction(str, Enum):
    """Outcome when no tool execution should proceed."""

    DIRECT_ANSWER = "direct_answer"
    NO_CAPABILITY = "no_capability"
    CLARIFICATION = "clarification"
    EXECUTE_TOOL = "execute_tool"


@dataclass(frozen=True)
class IntentClassification:
    """Result of intent classification (P10B-001, P10B-002)."""

    intent: Intent
    confidence: float
    reason: str


@dataclass(frozen=True)
class CandidateTool:
    """Ranked tool candidate with relevance score (P10B-004)."""

    tool_name: str
    score: float
    reason: str = ""


@dataclass(frozen=True)
class CandidateProvider:
    """Ranked provider candidate with composite score (P10B-702)."""

    provider_id: str
    score: float
    reason: str = ""
    capability: str = ""
    health_state: str = ""


@dataclass(frozen=True)
class ToolDecisionReport:
    """Canonical internal decision output for tool selection (P10B-005)."""

    intent: Intent
    confidence: float
    tool_required: bool
    candidate_tools: tuple[CandidateTool, ...]
    selected_tool: str | None
    decision_reason: str
    risk_level: RiskLevel
    confirmation_required: bool
    fallback_action: FallbackAction = FallbackAction.DIRECT_ANSWER
    classification_reason: str = ""
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    selected_provider: str | None = None
    provider_score: float | None = None
    provider_health: str | None = None
    provider_version: str | None = None
    execution_path: tuple[str, ...] = ()
    provider_latency_ms: float | None = None
    fallback_used: bool = False
    planned_provider: str | None = None
    execution_provider: str | None = None
    provider_changed: bool = False
    provider_change_reason: str = ""
    fallback_reason: str = ""
    fallback_policy: str = ""
    fallback_decision: str = ""
    original_provider: str | None = None
    replacement_provider: str | None = None
    file_operation: str | None = None
    target_path: str | None = None
    directory: str | None = None
    filename: str | None = None
    extension: str | None = None
    keyword: str | None = None
    recursive: bool | None = None
    execution_mode: str | None = None
    github_operation: str | None = None
    repository: str | None = None
    branch: str | None = None
    candidate_providers: tuple[CandidateProvider, ...] = ()
    ranking_score: float | None = None
    reasoning_summary: str = ""
    retry_count: int = 0
    telemetry_record_index: int | None = None
    telemetry_snapshot_at: str = ""
    performance_score: float | None = None
    ranking_reason: str = ""
    historical_confidence: float | None = None
    workspace_operation: str | None = None
    files_considered: tuple[str, ...] = ()
    files_read: tuple[str, ...] = ()
    explanation_mode: str | None = None
    search_query: str | None = None
    search_results: tuple[str, ...] = ()
    selected_file: str | None = None
    ambiguity_status: str | None = None
    modification_plan: dict | None = None
    affected_files: tuple[str, ...] = ()
    patch_application_requested: bool = False
    confirmation_received: bool = False
    patch_applied: bool = False
    files_modified: tuple[str, ...] = ()
    rollback_available: bool = False
    confirmation_token: str | None = None
    patch_application_result: dict | None = None
    rollback_id: str | None = None
    rollback_history_size: int = 0
    rollback_applied: bool = False
    multi_step_execution: bool = False
    steps_completed: int = 0
    steps_failed: int = 0
    total_duration: float | None = None
    execution_summary: str = ""
    task_execution_result: dict | None = None
    obsidian_decision: str | None = None
    obsidian_action: str | None = None
    obsidian_search_mode: str | None = None
    browser_decision: str | None = None
    browser_action: str | None = None
    calendar_decision: str | None = None
    calendar_action: str | None = None
    email_decision: str | None = None
    email_action: str | None = None
    trading_decision: str | None = None
    trading_action: str | None = None

    @property
    def intent_reason(self) -> str:
        """Alias for classification reason (backward-compatible accessor)."""
        return self.classification_reason

    def to_dict(self) -> dict:
        """Serialize for logging, tests, and future pipeline stages."""
        return {
            "intent": self.intent.value,
            "confidence": self.confidence,
            "tool_required": self.tool_required,
            "candidate_tools": [
                {"tool_name": c.tool_name, "score": c.score, "reason": c.reason}
                for c in self.candidate_tools
            ],
            "selected_tool": self.selected_tool,
            "decision_reason": self.decision_reason,
            "risk_level": self.risk_level.value,
            "confirmation_required": self.confirmation_required,
            "fallback_action": self.fallback_action.value,
            "classification_reason": self.classification_reason,
            "decision_id": self.decision_id,
            "selected_provider": self.selected_provider,
            "provider_score": self.provider_score,
            "provider_health": self.provider_health,
            "provider_version": self.provider_version,
            "execution_path": list(self.execution_path),
            "provider_latency_ms": self.provider_latency_ms,
            "fallback_used": self.fallback_used,
            "planned_provider": self.planned_provider,
            "execution_provider": self.execution_provider,
            "provider_changed": self.provider_changed,
            "provider_change_reason": self.provider_change_reason,
            "fallback_reason": self.fallback_reason,
            "fallback_policy": self.fallback_policy,
            "fallback_decision": self.fallback_decision,
            "original_provider": self.original_provider,
            "replacement_provider": self.replacement_provider,
            "file_operation": self.file_operation,
            "target_path": self.target_path,
            "directory": self.directory,
            "filename": self.filename,
            "extension": self.extension,
            "keyword": self.keyword,
            "recursive": self.recursive,
            "execution_mode": self.execution_mode,
            "github_operation": self.github_operation,
            "repository": self.repository,
            "branch": self.branch,
            "candidate_providers": [
                {
                    "provider_id": c.provider_id,
                    "score": c.score,
                    "reason": c.reason,
                    "capability": c.capability,
                    "health_state": c.health_state,
                }
                for c in self.candidate_providers
            ],
            "ranking_score": self.ranking_score,
            "reasoning_summary": self.reasoning_summary,
            "retry_count": self.retry_count,
            "telemetry_record_index": self.telemetry_record_index,
            "telemetry_snapshot_at": self.telemetry_snapshot_at,
            "performance_score": self.performance_score,
            "ranking_reason": self.ranking_reason,
            "historical_confidence": self.historical_confidence,
            "workspace_operation": self.workspace_operation,
            "files_considered": list(self.files_considered),
            "files_read": list(self.files_read),
            "explanation_mode": self.explanation_mode,
            "search_query": self.search_query,
            "search_results": list(self.search_results),
            "selected_file": self.selected_file,
            "ambiguity_status": self.ambiguity_status,
            "modification_plan": self.modification_plan,
            "affected_files": list(self.affected_files),
            "patch_application_requested": self.patch_application_requested,
            "confirmation_received": self.confirmation_received,
            "patch_applied": self.patch_applied,
            "files_modified": list(self.files_modified),
            "rollback_available": self.rollback_available,
            "confirmation_token": self.confirmation_token,
            "patch_application_result": self.patch_application_result,
            "rollback_id": self.rollback_id,
            "rollback_history_size": self.rollback_history_size,
            "rollback_applied": self.rollback_applied,
            "multi_step_execution": self.multi_step_execution,
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "total_duration": self.total_duration,
            "execution_summary": self.execution_summary,
            "task_execution_result": self.task_execution_result,
            "obsidian_decision": self.obsidian_decision,
            "obsidian_action": self.obsidian_action,
            "obsidian_search_mode": self.obsidian_search_mode,
            "browser_decision": self.browser_decision,
            "browser_action": self.browser_action,
            "calendar_decision": self.calendar_decision,
            "calendar_action": self.calendar_action,
            "email_decision": self.email_decision,
            "email_action": self.email_action,
            "trading_decision": self.trading_decision,
            "trading_action": self.trading_action,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ToolDecisionReport:
        """Deserialize a report stored in execution context metadata."""
        raw_path = data.get("execution_path", [])
        execution_path = tuple(raw_path) if isinstance(raw_path, list) else ()
        return cls(
            intent=Intent(data["intent"]),
            confidence=float(data["confidence"]),
            tool_required=bool(data["tool_required"]),
            candidate_tools=tuple(
                CandidateTool(
                    tool_name=item["tool_name"],
                    score=float(item["score"]),
                    reason=item.get("reason", ""),
                )
                for item in data.get("candidate_tools", [])
            ),
            selected_tool=data.get("selected_tool"),
            decision_reason=str(data.get("decision_reason", "")),
            risk_level=RiskLevel(data.get("risk_level", RiskLevel.SAFE.value)),
            confirmation_required=bool(data.get("confirmation_required", False)),
            fallback_action=FallbackAction(
                data.get("fallback_action", FallbackAction.DIRECT_ANSWER.value),
            ),
            classification_reason=str(data.get("classification_reason", "")),
            decision_id=str(data.get("decision_id", str(uuid.uuid4()))),
            selected_provider=data.get("selected_provider"),
            provider_score=(
                float(data["provider_score"])
                if data.get("provider_score") is not None
                else None
            ),
            provider_health=data.get("provider_health"),
            provider_version=data.get("provider_version"),
            execution_path=execution_path,
            provider_latency_ms=(
                float(data["provider_latency_ms"])
                if data.get("provider_latency_ms") is not None
                else None
            ),
            fallback_used=bool(data.get("fallback_used", False)),
            planned_provider=data.get("planned_provider"),
            execution_provider=data.get("execution_provider"),
            provider_changed=bool(data.get("provider_changed", False)),
            provider_change_reason=str(data.get("provider_change_reason", "")),
            fallback_reason=str(data.get("fallback_reason", "")),
            fallback_policy=str(data.get("fallback_policy", "")),
            fallback_decision=str(data.get("fallback_decision", "")),
            original_provider=data.get("original_provider"),
            replacement_provider=data.get("replacement_provider"),
            file_operation=data.get("file_operation"),
            target_path=data.get("target_path"),
            directory=data.get("directory"),
            filename=data.get("filename"),
            extension=data.get("extension"),
            keyword=data.get("keyword"),
            recursive=(
                bool(data["recursive"])
                if data.get("recursive") is not None
                else None
            ),
            execution_mode=data.get("execution_mode"),
            github_operation=data.get("github_operation"),
            repository=data.get("repository"),
            branch=data.get("branch"),
            candidate_providers=tuple(
                CandidateProvider(
                    provider_id=item["provider_id"],
                    score=float(item["score"]),
                    reason=item.get("reason", ""),
                    capability=item.get("capability", ""),
                    health_state=item.get("health_state", ""),
                )
                for item in data.get("candidate_providers", [])
            ),
            ranking_score=(
                float(data["ranking_score"])
                if data.get("ranking_score") is not None
                else None
            ),
            reasoning_summary=str(data.get("reasoning_summary", "")),
            retry_count=int(data.get("retry_count", 0)),
            telemetry_record_index=(
                int(data["telemetry_record_index"])
                if data.get("telemetry_record_index") is not None
                else None
            ),
            telemetry_snapshot_at=str(data.get("telemetry_snapshot_at", "")),
            performance_score=(
                float(data["performance_score"])
                if data.get("performance_score") is not None
                else None
            ),
            ranking_reason=str(data.get("ranking_reason", "")),
            historical_confidence=(
                float(data["historical_confidence"])
                if data.get("historical_confidence") is not None
                else None
            ),
            workspace_operation=data.get("workspace_operation"),
            files_considered=tuple(data.get("files_considered", [])),
            files_read=tuple(data.get("files_read", [])),
            explanation_mode=data.get("explanation_mode"),
            search_query=data.get("search_query"),
            search_results=tuple(data.get("search_results", [])),
            selected_file=data.get("selected_file"),
            ambiguity_status=data.get("ambiguity_status"),
            modification_plan=data.get("modification_plan"),
            affected_files=tuple(data.get("affected_files", [])),
            patch_application_requested=bool(
                data.get("patch_application_requested", False),
            ),
            confirmation_received=bool(data.get("confirmation_received", False)),
            patch_applied=bool(data.get("patch_applied", False)),
            files_modified=tuple(data.get("files_modified", [])),
            rollback_available=bool(data.get("rollback_available", False)),
            confirmation_token=data.get("confirmation_token"),
            patch_application_result=data.get("patch_application_result"),
            rollback_id=data.get("rollback_id"),
            rollback_history_size=int(data.get("rollback_history_size", 0)),
            rollback_applied=bool(data.get("rollback_applied", False)),
            multi_step_execution=bool(data.get("multi_step_execution", False)),
            steps_completed=int(data.get("steps_completed", 0)),
            steps_failed=int(data.get("steps_failed", 0)),
            total_duration=(
                float(data["total_duration"])
                if data.get("total_duration") is not None
                else None
            ),
            execution_summary=str(data.get("execution_summary", "")),
            task_execution_result=data.get("task_execution_result"),
            obsidian_decision=data.get("obsidian_decision"),
            obsidian_action=data.get("obsidian_action"),
            obsidian_search_mode=data.get("obsidian_search_mode"),
            browser_decision=data.get("browser_decision"),
            browser_action=data.get("browser_action"),
            calendar_decision=data.get("calendar_decision"),
            calendar_action=data.get("calendar_action"),
            email_decision=data.get("email_decision"),
            email_action=data.get("email_action"),
            trading_decision=data.get("trading_decision"),
            trading_action=data.get("trading_action"),
        )

    def with_provider_execution(
        self,
        *,
        selected_provider: str | None,
        provider_score: float | None,
        provider_health: str | None,
        provider_version: str | None,
        execution_path: tuple[str, ...],
        provider_latency_ms: float | None = None,
        fallback_used: bool = False,
        execution_provider: str | None = None,
        planned_provider: str | None = None,
        provider_changed: bool = False,
        provider_change_reason: str = "",
        fallback_reason: str = "",
        fallback_policy: str = "",
        fallback_decision: str = "",
        original_provider: str | None = None,
        replacement_provider: str | None = None,
        retry_count: int = 0,
        telemetry_record_index: int | None = None,
        telemetry_snapshot_at: str = "",
    ) -> ToolDecisionReport:
        """Return a copy enriched with provider execution metadata (P10B-205, P10B-805, P10B-1004)."""
        return ToolDecisionReport(
            intent=self.intent,
            confidence=self.confidence,
            tool_required=self.tool_required,
            candidate_tools=self.candidate_tools,
            selected_tool=self.selected_tool,
            decision_reason=self.decision_reason,
            risk_level=self.risk_level,
            confirmation_required=self.confirmation_required,
            fallback_action=self.fallback_action,
            classification_reason=self.classification_reason,
            decision_id=self.decision_id,
            selected_provider=selected_provider,
            provider_score=provider_score,
            provider_health=provider_health,
            provider_version=provider_version,
            execution_path=execution_path,
            provider_latency_ms=provider_latency_ms,
            fallback_used=fallback_used,
            planned_provider=planned_provider or self.planned_provider or self.selected_provider,
            execution_provider=execution_provider,
            provider_changed=provider_changed,
            provider_change_reason=provider_change_reason,
            fallback_reason=fallback_reason,
            fallback_policy=fallback_policy or self.fallback_policy,
            fallback_decision=fallback_decision or self.fallback_decision,
            original_provider=original_provider,
            replacement_provider=replacement_provider,
            file_operation=self.file_operation,
            target_path=self.target_path,
            directory=self.directory,
            filename=self.filename,
            extension=self.extension,
            keyword=self.keyword,
            recursive=self.recursive,
            execution_mode=self.execution_mode,
            github_operation=self.github_operation,
            repository=self.repository,
            branch=self.branch,
            candidate_providers=self.candidate_providers,
            ranking_score=self.ranking_score,
            reasoning_summary=self.reasoning_summary,
            retry_count=retry_count if retry_count else self.retry_count,
            telemetry_record_index=(
                telemetry_record_index
                if telemetry_record_index is not None
                else self.telemetry_record_index
            ),
            telemetry_snapshot_at=telemetry_snapshot_at or self.telemetry_snapshot_at,
            performance_score=self.performance_score,
            ranking_reason=self.ranking_reason,
            historical_confidence=self.historical_confidence,
            workspace_operation=self.workspace_operation,
            files_considered=self.files_considered,
            files_read=self.files_read,
            explanation_mode=self.explanation_mode,
            search_query=self.search_query,
            search_results=self.search_results,
            selected_file=self.selected_file,
            ambiguity_status=self.ambiguity_status,
        )

    def with_performance_metrics(
        self,
        *,
        performance_score: float | None,
        ranking_reason: str,
        historical_confidence: float | None,
    ) -> ToolDecisionReport:
        """Return a copy enriched with telemetry-driven performance metadata (P10B-1205)."""
        return ToolDecisionReport(
            intent=self.intent,
            confidence=self.confidence,
            tool_required=self.tool_required,
            candidate_tools=self.candidate_tools,
            selected_tool=self.selected_tool,
            decision_reason=self.decision_reason,
            risk_level=self.risk_level,
            confirmation_required=self.confirmation_required,
            fallback_action=self.fallback_action,
            classification_reason=self.classification_reason,
            decision_id=self.decision_id,
            selected_provider=self.selected_provider,
            provider_score=self.provider_score,
            provider_health=self.provider_health,
            provider_version=self.provider_version,
            execution_path=self.execution_path,
            provider_latency_ms=self.provider_latency_ms,
            fallback_used=self.fallback_used,
            planned_provider=self.planned_provider,
            execution_provider=self.execution_provider,
            provider_changed=self.provider_changed,
            provider_change_reason=self.provider_change_reason,
            fallback_reason=self.fallback_reason,
            fallback_policy=self.fallback_policy,
            fallback_decision=self.fallback_decision,
            original_provider=self.original_provider,
            replacement_provider=self.replacement_provider,
            file_operation=self.file_operation,
            target_path=self.target_path,
            directory=self.directory,
            filename=self.filename,
            extension=self.extension,
            keyword=self.keyword,
            recursive=self.recursive,
            execution_mode=self.execution_mode,
            github_operation=self.github_operation,
            repository=self.repository,
            branch=self.branch,
            candidate_providers=self.candidate_providers,
            ranking_score=self.ranking_score,
            reasoning_summary=self.reasoning_summary,
            retry_count=self.retry_count,
            telemetry_record_index=self.telemetry_record_index,
            telemetry_snapshot_at=self.telemetry_snapshot_at,
            performance_score=performance_score,
            ranking_reason=ranking_reason,
            historical_confidence=historical_confidence,
        )

    def with_fallback_policy(
        self,
        *,
        fallback_policy: str,
        fallback_decision: str,
        fallback_reason: str,
    ) -> ToolDecisionReport:
        """Return a copy enriched with Brain fallback policy metadata (P10B-903)."""
        return ToolDecisionReport(
            intent=self.intent,
            confidence=self.confidence,
            tool_required=self.tool_required,
            candidate_tools=self.candidate_tools,
            selected_tool=self.selected_tool,
            decision_reason=self.decision_reason,
            risk_level=self.risk_level,
            confirmation_required=self.confirmation_required,
            fallback_action=self.fallback_action,
            classification_reason=self.classification_reason,
            decision_id=self.decision_id,
            selected_provider=self.selected_provider,
            provider_score=self.provider_score,
            provider_health=self.provider_health,
            provider_version=self.provider_version,
            execution_path=self.execution_path,
            provider_latency_ms=self.provider_latency_ms,
            fallback_used=self.fallback_used,
            planned_provider=self.planned_provider,
            execution_provider=self.execution_provider,
            provider_changed=self.provider_changed,
            provider_change_reason=self.provider_change_reason,
            fallback_reason=fallback_reason,
            fallback_policy=fallback_policy,
            fallback_decision=fallback_decision,
            original_provider=self.original_provider,
            replacement_provider=self.replacement_provider,
            file_operation=self.file_operation,
            target_path=self.target_path,
            directory=self.directory,
            filename=self.filename,
            extension=self.extension,
            keyword=self.keyword,
            recursive=self.recursive,
            execution_mode=self.execution_mode,
            github_operation=self.github_operation,
            repository=self.repository,
            branch=self.branch,
            candidate_providers=self.candidate_providers,
            ranking_score=self.ranking_score,
            reasoning_summary=self.reasoning_summary,
            retry_count=self.retry_count,
            telemetry_record_index=self.telemetry_record_index,
            telemetry_snapshot_at=self.telemetry_snapshot_at,
            performance_score=self.performance_score,
            ranking_reason=self.ranking_reason,
            historical_confidence=self.historical_confidence,
            workspace_operation=self.workspace_operation,
            files_considered=self.files_considered,
            files_read=self.files_read,
            explanation_mode=self.explanation_mode,
            search_query=self.search_query,
            search_results=self.search_results,
            selected_file=self.selected_file,
            ambiguity_status=self.ambiguity_status,
        )

    def with_file_context(
        self,
        *,
        file_operation: str | None,
        target_path: str | None,
        execution_mode: str | None,
        selected_provider: str | None = None,
        directory: str | None = None,
        filename: str | None = None,
        extension: str | None = None,
        keyword: str | None = None,
        recursive: bool | None = None,
    ) -> ToolDecisionReport:
        """Return a copy enriched with filesystem decision metadata (P10B-505, P10B-1504)."""
        return ToolDecisionReport(
            intent=self.intent,
            confidence=self.confidence,
            tool_required=self.tool_required,
            candidate_tools=self.candidate_tools,
            selected_tool=self.selected_tool,
            decision_reason=self.decision_reason,
            risk_level=self.risk_level,
            confirmation_required=self.confirmation_required,
            fallback_action=self.fallback_action,
            classification_reason=self.classification_reason,
            decision_id=self.decision_id,
            selected_provider=selected_provider or self.selected_provider,
            provider_score=self.provider_score,
            provider_health=self.provider_health,
            provider_version=self.provider_version,
            execution_path=self.execution_path,
            provider_latency_ms=self.provider_latency_ms,
            fallback_used=self.fallback_used,
            planned_provider=self.planned_provider or self.selected_provider,
            execution_provider=self.execution_provider,
            provider_changed=self.provider_changed,
            provider_change_reason=self.provider_change_reason,
            fallback_reason=self.fallback_reason,
            fallback_policy=self.fallback_policy,
            fallback_decision=self.fallback_decision,
            original_provider=self.original_provider,
            replacement_provider=self.replacement_provider,
            file_operation=file_operation,
            target_path=target_path,
            directory=directory if directory is not None else self.directory,
            filename=filename if filename is not None else self.filename,
            extension=extension if extension is not None else self.extension,
            keyword=keyword if keyword is not None else self.keyword,
            recursive=recursive if recursive is not None else self.recursive,
            execution_mode=execution_mode,
            github_operation=self.github_operation,
            repository=self.repository,
            branch=self.branch,
            candidate_providers=self.candidate_providers,
            ranking_score=self.ranking_score,
            reasoning_summary=self.reasoning_summary,
            retry_count=self.retry_count,
            telemetry_record_index=self.telemetry_record_index,
            telemetry_snapshot_at=self.telemetry_snapshot_at,
            performance_score=self.performance_score,
            ranking_reason=self.ranking_reason,
            historical_confidence=self.historical_confidence,
            workspace_operation=self.workspace_operation,
            files_considered=self.files_considered,
            files_read=self.files_read,
            explanation_mode=self.explanation_mode,
            search_query=self.search_query,
            search_results=self.search_results,
            selected_file=self.selected_file,
            ambiguity_status=self.ambiguity_status,
        )

    def with_github_context(
        self,
        *,
        github_operation: str | None,
        repository: str | None,
        branch: str | None,
        target_path: str | None,
        execution_mode: str | None,
        selected_provider: str | None = None,
    ) -> ToolDecisionReport:
        """Return a copy enriched with GitHub decision metadata (P10B-605)."""
        return ToolDecisionReport(
            intent=self.intent,
            confidence=self.confidence,
            tool_required=self.tool_required,
            candidate_tools=self.candidate_tools,
            selected_tool=self.selected_tool,
            decision_reason=self.decision_reason,
            risk_level=RiskLevel.LOW,
            confirmation_required=False,
            fallback_action=self.fallback_action,
            classification_reason=self.classification_reason,
            decision_id=self.decision_id,
            selected_provider=selected_provider or self.selected_provider or "github",
            provider_score=self.provider_score,
            provider_health=self.provider_health,
            provider_version=self.provider_version,
            execution_path=self.execution_path,
            provider_latency_ms=self.provider_latency_ms,
            fallback_used=self.fallback_used,
            planned_provider=(
                self.planned_provider or self.selected_provider or "github"
            ),
            execution_provider=self.execution_provider,
            provider_changed=self.provider_changed,
            provider_change_reason=self.provider_change_reason,
            fallback_reason=self.fallback_reason,
            fallback_policy=self.fallback_policy,
            fallback_decision=self.fallback_decision,
            original_provider=self.original_provider,
            replacement_provider=self.replacement_provider,
            file_operation=self.file_operation,
            target_path=target_path,
            directory=self.directory,
            filename=self.filename,
            extension=self.extension,
            keyword=self.keyword,
            recursive=self.recursive,
            execution_mode=execution_mode,
            github_operation=github_operation,
            repository=repository,
            branch=branch,
            candidate_providers=self.candidate_providers,
            ranking_score=self.ranking_score,
            reasoning_summary=self.reasoning_summary,
            retry_count=self.retry_count,
            telemetry_record_index=self.telemetry_record_index,
            telemetry_snapshot_at=self.telemetry_snapshot_at,
            performance_score=self.performance_score,
            ranking_reason=self.ranking_reason,
            historical_confidence=self.historical_confidence,
            workspace_operation=self.workspace_operation,
            files_considered=self.files_considered,
            files_read=self.files_read,
            explanation_mode=self.explanation_mode,
            search_query=self.search_query,
            search_results=self.search_results,
            selected_file=self.selected_file,
            ambiguity_status=self.ambiguity_status,
        )

    def with_obsidian_context(
        self,
        *,
        obsidian_decision: str | None,
        obsidian_action: str | None,
        obsidian_search_mode: str | None,
        target_path: str | None,
        keyword: str | None,
        directory: str | None,
        reasoning_summary: str,
    ) -> ToolDecisionReport:
        """Return a copy enriched with Obsidian decision metadata (P125-007)."""
        return ToolDecisionReport(
            intent=self.intent,
            confidence=self.confidence,
            tool_required=self.tool_required,
            candidate_tools=self.candidate_tools,
            selected_tool=self.selected_tool,
            decision_reason=self.decision_reason,
            risk_level=RiskLevel.LOW,
            confirmation_required=False,
            fallback_action=self.fallback_action,
            classification_reason=self.classification_reason,
            decision_id=self.decision_id,
            selected_provider=self.selected_provider or "obsidian",
            provider_score=self.provider_score,
            provider_health=self.provider_health,
            provider_version=self.provider_version,
            execution_path=self.execution_path,
            provider_latency_ms=self.provider_latency_ms,
            fallback_used=self.fallback_used,
            planned_provider=self.planned_provider or self.selected_provider or "obsidian",
            execution_provider=self.execution_provider,
            provider_changed=self.provider_changed,
            provider_change_reason=self.provider_change_reason,
            fallback_reason=self.fallback_reason,
            fallback_policy=self.fallback_policy,
            fallback_decision=self.fallback_decision,
            original_provider=self.original_provider,
            replacement_provider=self.replacement_provider,
            file_operation=self.file_operation,
            target_path=target_path,
            directory=directory,
            filename=self.filename,
            extension=self.extension,
            keyword=keyword,
            recursive=self.recursive,
            execution_mode=self.execution_mode,
            github_operation=self.github_operation,
            repository=self.repository,
            branch=self.branch,
            candidate_providers=self.candidate_providers,
            ranking_score=self.ranking_score,
            reasoning_summary=reasoning_summary,
            retry_count=self.retry_count,
            telemetry_record_index=self.telemetry_record_index,
            telemetry_snapshot_at=self.telemetry_snapshot_at,
            performance_score=self.performance_score,
            ranking_reason=self.ranking_reason,
            historical_confidence=self.historical_confidence,
            workspace_operation=self.workspace_operation,
            files_considered=self.files_considered,
            files_read=self.files_read,
            explanation_mode=self.explanation_mode,
            search_query=self.search_query,
            search_results=self.search_results,
            selected_file=self.selected_file,
            ambiguity_status=self.ambiguity_status,
            modification_plan=self.modification_plan,
            affected_files=self.affected_files,
            patch_application_requested=self.patch_application_requested,
            confirmation_received=self.confirmation_received,
            patch_applied=self.patch_applied,
            files_modified=self.files_modified,
            rollback_available=self.rollback_available,
            confirmation_token=self.confirmation_token,
            patch_application_result=self.patch_application_result,
            rollback_id=self.rollback_id,
            rollback_history_size=self.rollback_history_size,
            rollback_applied=self.rollback_applied,
            multi_step_execution=self.multi_step_execution,
            steps_completed=self.steps_completed,
            steps_failed=self.steps_failed,
            total_duration=self.total_duration,
            execution_summary=self.execution_summary,
            task_execution_result=self.task_execution_result,
            obsidian_decision=obsidian_decision,
            obsidian_action=obsidian_action,
            obsidian_search_mode=obsidian_search_mode,
        )

    def with_browser_context(
        self,
        *,
        browser_decision: str | None,
        browser_action: str | None,
        target_path: str | None,
        reasoning_summary: str,
    ) -> ToolDecisionReport:
        """Return a copy enriched with Browser decision metadata (Phase 13.1)."""
        return ToolDecisionReport(
            intent=self.intent,
            confidence=self.confidence,
            tool_required=self.tool_required,
            candidate_tools=self.candidate_tools,
            selected_tool=self.selected_tool,
            decision_reason=self.decision_reason,
            risk_level=RiskLevel.LOW,
            confirmation_required=False,
            fallback_action=self.fallback_action,
            classification_reason=self.classification_reason,
            decision_id=self.decision_id,
            selected_provider=self.selected_provider or "browser",
            provider_score=self.provider_score,
            provider_health=self.provider_health,
            provider_version=self.provider_version,
            execution_path=self.execution_path,
            provider_latency_ms=self.provider_latency_ms,
            fallback_used=self.fallback_used,
            planned_provider=self.planned_provider or self.selected_provider or "browser",
            execution_provider=self.execution_provider,
            provider_changed=self.provider_changed,
            provider_change_reason=self.provider_change_reason,
            fallback_reason=self.fallback_reason,
            fallback_policy=self.fallback_policy,
            fallback_decision=self.fallback_decision,
            original_provider=self.original_provider,
            replacement_provider=self.replacement_provider,
            file_operation=self.file_operation,
            target_path=target_path,
            directory=self.directory,
            filename=self.filename,
            extension=self.extension,
            keyword=self.keyword,
            recursive=self.recursive,
            execution_mode=self.execution_mode,
            github_operation=self.github_operation,
            repository=self.repository,
            branch=self.branch,
            candidate_providers=self.candidate_providers,
            ranking_score=self.ranking_score,
            reasoning_summary=reasoning_summary,
            retry_count=self.retry_count,
            telemetry_record_index=self.telemetry_record_index,
            telemetry_snapshot_at=self.telemetry_snapshot_at,
            performance_score=self.performance_score,
            ranking_reason=self.ranking_reason,
            historical_confidence=self.historical_confidence,
            workspace_operation=self.workspace_operation,
            files_considered=self.files_considered,
            files_read=self.files_read,
            explanation_mode=self.explanation_mode,
            search_query=self.search_query,
            search_results=self.search_results,
            selected_file=self.selected_file,
            ambiguity_status=self.ambiguity_status,
            modification_plan=self.modification_plan,
            affected_files=self.affected_files,
            patch_application_requested=self.patch_application_requested,
            confirmation_received=self.confirmation_received,
            patch_applied=self.patch_applied,
            files_modified=self.files_modified,
            rollback_available=self.rollback_available,
            confirmation_token=self.confirmation_token,
            patch_application_result=self.patch_application_result,
            rollback_id=self.rollback_id,
            rollback_history_size=self.rollback_history_size,
            rollback_applied=self.rollback_applied,
            multi_step_execution=self.multi_step_execution,
            steps_completed=self.steps_completed,
            steps_failed=self.steps_failed,
            total_duration=self.total_duration,
            execution_summary=self.execution_summary,
            task_execution_result=self.task_execution_result,
            obsidian_decision=self.obsidian_decision,
            obsidian_action=self.obsidian_action,
            obsidian_search_mode=self.obsidian_search_mode,
            browser_decision=browser_decision,
            browser_action=browser_action,
        )

    def with_calendar_context(
        self,
        *,
        calendar_decision: str | None,
        calendar_action: str | None,
        reasoning_summary: str,
    ) -> ToolDecisionReport:
        """Return a copy enriched with Calendar decision metadata (Phase 14.1)."""
        return ToolDecisionReport(
            intent=self.intent,
            confidence=self.confidence,
            tool_required=self.tool_required,
            candidate_tools=self.candidate_tools,
            selected_tool=self.selected_tool,
            decision_reason=self.decision_reason,
            risk_level=RiskLevel.LOW,
            confirmation_required=False,
            fallback_action=self.fallback_action,
            classification_reason=self.classification_reason,
            decision_id=self.decision_id,
            selected_provider=self.selected_provider or "calendar",
            provider_score=self.provider_score,
            provider_health=self.provider_health,
            provider_version=self.provider_version,
            execution_path=self.execution_path,
            provider_latency_ms=self.provider_latency_ms,
            fallback_used=self.fallback_used,
            planned_provider=self.planned_provider or self.selected_provider or "calendar",
            execution_provider=self.execution_provider,
            provider_changed=self.provider_changed,
            provider_change_reason=self.provider_change_reason,
            fallback_reason=self.fallback_reason,
            fallback_policy=self.fallback_policy,
            fallback_decision=self.fallback_decision,
            original_provider=self.original_provider,
            replacement_provider=self.replacement_provider,
            file_operation=self.file_operation,
            target_path=self.target_path,
            directory=self.directory,
            filename=self.filename,
            extension=self.extension,
            keyword=self.keyword,
            recursive=self.recursive,
            execution_mode=self.execution_mode,
            github_operation=self.github_operation,
            repository=self.repository,
            branch=self.branch,
            candidate_providers=self.candidate_providers,
            ranking_score=self.ranking_score,
            reasoning_summary=reasoning_summary,
            retry_count=self.retry_count,
            telemetry_record_index=self.telemetry_record_index,
            telemetry_snapshot_at=self.telemetry_snapshot_at,
            performance_score=self.performance_score,
            ranking_reason=self.ranking_reason,
            historical_confidence=self.historical_confidence,
            workspace_operation=self.workspace_operation,
            files_considered=self.files_considered,
            files_read=self.files_read,
            explanation_mode=self.explanation_mode,
            search_query=self.search_query,
            search_results=self.search_results,
            selected_file=self.selected_file,
            ambiguity_status=self.ambiguity_status,
            modification_plan=self.modification_plan,
            affected_files=self.affected_files,
            patch_application_requested=self.patch_application_requested,
            confirmation_received=self.confirmation_received,
            patch_applied=self.patch_applied,
            files_modified=self.files_modified,
            rollback_available=self.rollback_available,
            confirmation_token=self.confirmation_token,
            patch_application_result=self.patch_application_result,
            rollback_id=self.rollback_id,
            rollback_history_size=self.rollback_history_size,
            rollback_applied=self.rollback_applied,
            multi_step_execution=self.multi_step_execution,
            steps_completed=self.steps_completed,
            steps_failed=self.steps_failed,
            total_duration=self.total_duration,
            execution_summary=self.execution_summary,
            task_execution_result=self.task_execution_result,
            obsidian_decision=self.obsidian_decision,
            obsidian_action=self.obsidian_action,
            obsidian_search_mode=self.obsidian_search_mode,
            browser_decision=self.browser_decision,
            browser_action=self.browser_action,
            calendar_decision=calendar_decision,
            calendar_action=calendar_action,
        )

    def with_email_context(
        self,
        *,
        email_decision: str | None,
        email_action: str | None,
        reasoning_summary: str,
    ) -> ToolDecisionReport:
        """Return a copy enriched with Email decision metadata (Phase 15.1)."""
        return ToolDecisionReport(
            intent=self.intent,
            confidence=self.confidence,
            tool_required=self.tool_required,
            candidate_tools=self.candidate_tools,
            selected_tool=self.selected_tool,
            decision_reason=self.decision_reason,
            risk_level=RiskLevel.LOW,
            confirmation_required=False,
            fallback_action=self.fallback_action,
            classification_reason=self.classification_reason,
            decision_id=self.decision_id,
            selected_provider=self.selected_provider or "email",
            provider_score=self.provider_score,
            provider_health=self.provider_health,
            provider_version=self.provider_version,
            execution_path=self.execution_path,
            provider_latency_ms=self.provider_latency_ms,
            fallback_used=self.fallback_used,
            planned_provider=self.planned_provider or self.selected_provider or "email",
            execution_provider=self.execution_provider,
            provider_changed=self.provider_changed,
            provider_change_reason=self.provider_change_reason,
            fallback_reason=self.fallback_reason,
            fallback_policy=self.fallback_policy,
            fallback_decision=self.fallback_decision,
            original_provider=self.original_provider,
            replacement_provider=self.replacement_provider,
            file_operation=self.file_operation,
            target_path=self.target_path,
            directory=self.directory,
            filename=self.filename,
            extension=self.extension,
            keyword=self.keyword,
            recursive=self.recursive,
            execution_mode=self.execution_mode,
            github_operation=self.github_operation,
            repository=self.repository,
            branch=self.branch,
            candidate_providers=self.candidate_providers,
            ranking_score=self.ranking_score,
            reasoning_summary=reasoning_summary,
            retry_count=self.retry_count,
            telemetry_record_index=self.telemetry_record_index,
            telemetry_snapshot_at=self.telemetry_snapshot_at,
            performance_score=self.performance_score,
            ranking_reason=self.ranking_reason,
            historical_confidence=self.historical_confidence,
            workspace_operation=self.workspace_operation,
            files_considered=self.files_considered,
            files_read=self.files_read,
            explanation_mode=self.explanation_mode,
            search_query=self.search_query,
            search_results=self.search_results,
            selected_file=self.selected_file,
            ambiguity_status=self.ambiguity_status,
            modification_plan=self.modification_plan,
            affected_files=self.affected_files,
            patch_application_requested=self.patch_application_requested,
            confirmation_received=self.confirmation_received,
            patch_applied=self.patch_applied,
            files_modified=self.files_modified,
            rollback_available=self.rollback_available,
            confirmation_token=self.confirmation_token,
            patch_application_result=self.patch_application_result,
            rollback_id=self.rollback_id,
            rollback_history_size=self.rollback_history_size,
            rollback_applied=self.rollback_applied,
            multi_step_execution=self.multi_step_execution,
            steps_completed=self.steps_completed,
            steps_failed=self.steps_failed,
            total_duration=self.total_duration,
            execution_summary=self.execution_summary,
            task_execution_result=self.task_execution_result,
            obsidian_decision=self.obsidian_decision,
            obsidian_action=self.obsidian_action,
            obsidian_search_mode=self.obsidian_search_mode,
            browser_decision=self.browser_decision,
            browser_action=self.browser_action,
            calendar_decision=self.calendar_decision,
            calendar_action=self.calendar_action,
            email_decision=email_decision,
            email_action=email_action,
        )

    def with_trading_context(
        self,
        *,
        trading_decision: str | None,
        trading_action: str | None,
        reasoning_summary: str,
    ) -> ToolDecisionReport:
        """Return a copy enriched with Trading decision metadata (Phase 16.1)."""
        return ToolDecisionReport(
            intent=self.intent,
            confidence=self.confidence,
            tool_required=self.tool_required,
            candidate_tools=self.candidate_tools,
            selected_tool=self.selected_tool,
            decision_reason=self.decision_reason,
            risk_level=RiskLevel.LOW,
            confirmation_required=False,
            fallback_action=self.fallback_action,
            classification_reason=self.classification_reason,
            decision_id=self.decision_id,
            selected_provider=self.selected_provider or "trading",
            provider_score=self.provider_score,
            provider_health=self.provider_health,
            provider_version=self.provider_version,
            execution_path=self.execution_path,
            provider_latency_ms=self.provider_latency_ms,
            fallback_used=self.fallback_used,
            planned_provider=self.planned_provider or self.selected_provider or "trading",
            execution_provider=self.execution_provider,
            provider_changed=self.provider_changed,
            provider_change_reason=self.provider_change_reason,
            fallback_reason=self.fallback_reason,
            fallback_policy=self.fallback_policy,
            fallback_decision=self.fallback_decision,
            original_provider=self.original_provider,
            replacement_provider=self.replacement_provider,
            file_operation=self.file_operation,
            target_path=self.target_path,
            directory=self.directory,
            filename=self.filename,
            extension=self.extension,
            keyword=self.keyword,
            recursive=self.recursive,
            execution_mode=self.execution_mode,
            github_operation=self.github_operation,
            repository=self.repository,
            branch=self.branch,
            candidate_providers=self.candidate_providers,
            ranking_score=self.ranking_score,
            reasoning_summary=reasoning_summary,
            retry_count=self.retry_count,
            telemetry_record_index=self.telemetry_record_index,
            telemetry_snapshot_at=self.telemetry_snapshot_at,
            performance_score=self.performance_score,
            ranking_reason=self.ranking_reason,
            historical_confidence=self.historical_confidence,
            workspace_operation=self.workspace_operation,
            files_considered=self.files_considered,
            files_read=self.files_read,
            explanation_mode=self.explanation_mode,
            search_query=self.search_query,
            search_results=self.search_results,
            selected_file=self.selected_file,
            ambiguity_status=self.ambiguity_status,
            modification_plan=self.modification_plan,
            affected_files=self.affected_files,
            patch_application_requested=self.patch_application_requested,
            confirmation_received=self.confirmation_received,
            patch_applied=self.patch_applied,
            files_modified=self.files_modified,
            rollback_available=self.rollback_available,
            confirmation_token=self.confirmation_token,
            patch_application_result=self.patch_application_result,
            rollback_id=self.rollback_id,
            rollback_history_size=self.rollback_history_size,
            rollback_applied=self.rollback_applied,
            multi_step_execution=self.multi_step_execution,
            steps_completed=self.steps_completed,
            steps_failed=self.steps_failed,
            total_duration=self.total_duration,
            execution_summary=self.execution_summary,
            task_execution_result=self.task_execution_result,
            obsidian_decision=self.obsidian_decision,
            obsidian_action=self.obsidian_action,
            obsidian_search_mode=self.obsidian_search_mode,
            browser_decision=self.browser_decision,
            browser_action=self.browser_action,
            calendar_decision=self.calendar_decision,
            calendar_action=self.calendar_action,
            email_decision=self.email_decision,
            email_action=self.email_action,
            trading_decision=trading_decision,
            trading_action=trading_action,
        )

    def with_workspace_context(
        self,
        *,
        workspace_operation: str | None,
        explanation_mode: str | None,
        files_considered: tuple[str, ...] | None = None,
        files_read: tuple[str, ...] | None = None,
        confidence: float | None = None,
        reasoning_summary: str | None = None,
        selected_provider: str | None = None,
        execution_mode: str | None = None,
        search_query: str | None = None,
        search_results: tuple[str, ...] | None = None,
        selected_file: str | None = None,
        ambiguity_status: str | None = None,
    ) -> ToolDecisionReport:
        """Return a copy enriched with workspace intelligence metadata (P11-004/P11-105)."""
        return ToolDecisionReport(
            intent=self.intent,
            confidence=confidence if confidence is not None else self.confidence,
            tool_required=self.tool_required,
            candidate_tools=self.candidate_tools,
            selected_tool=self.selected_tool,
            decision_reason=self.decision_reason,
            risk_level=RiskLevel.LOW,
            confirmation_required=False,
            fallback_action=self.fallback_action,
            classification_reason=self.classification_reason,
            decision_id=self.decision_id,
            selected_provider=selected_provider or self.selected_provider or "file_system",
            provider_score=self.provider_score,
            provider_health=self.provider_health,
            provider_version=self.provider_version,
            execution_path=self.execution_path,
            provider_latency_ms=self.provider_latency_ms,
            fallback_used=self.fallback_used,
            planned_provider=self.planned_provider or self.selected_provider or "file_system",
            execution_provider=self.execution_provider,
            provider_changed=self.provider_changed,
            provider_change_reason=self.provider_change_reason,
            fallback_reason=self.fallback_reason,
            fallback_policy=self.fallback_policy,
            fallback_decision=self.fallback_decision,
            original_provider=self.original_provider,
            replacement_provider=self.replacement_provider,
            file_operation=self.file_operation,
            target_path=self.target_path,
            directory=self.directory,
            filename=self.filename,
            extension=self.extension,
            keyword=self.keyword,
            recursive=self.recursive,
            execution_mode=execution_mode or self.execution_mode,
            github_operation=self.github_operation,
            repository=self.repository,
            branch=self.branch,
            candidate_providers=self.candidate_providers,
            ranking_score=self.ranking_score,
            reasoning_summary=reasoning_summary or self.reasoning_summary,
            retry_count=self.retry_count,
            telemetry_record_index=self.telemetry_record_index,
            telemetry_snapshot_at=self.telemetry_snapshot_at,
            performance_score=self.performance_score,
            ranking_reason=self.ranking_reason,
            historical_confidence=self.historical_confidence,
            workspace_operation=workspace_operation,
            files_considered=files_considered if files_considered is not None else self.files_considered,
            files_read=files_read if files_read is not None else self.files_read,
            explanation_mode=explanation_mode,
            search_query=search_query if search_query is not None else self.search_query,
            search_results=(
                search_results if search_results is not None else self.search_results
            ),
            selected_file=selected_file if selected_file is not None else self.selected_file,
            ambiguity_status=(
                ambiguity_status if ambiguity_status is not None else self.ambiguity_status
            ),
        )

    def with_modification_context(
        self,
        *,
        modification_plan: dict | None,
        affected_files: tuple[str, ...],
        confidence: float | None = None,
        reasoning_summary: str | None = None,
        risk_level: RiskLevel | None = None,
    ) -> ToolDecisionReport:
        """Return a copy enriched with modification planning metadata (P11-304)."""
        return ToolDecisionReport(
            intent=self.intent,
            confidence=confidence if confidence is not None else self.confidence,
            tool_required=False,
            candidate_tools=self.candidate_tools,
            selected_tool=None,
            decision_reason=self.decision_reason,
            risk_level=risk_level if risk_level is not None else self.risk_level,
            confirmation_required=True,
            fallback_action=self.fallback_action,
            classification_reason=self.classification_reason,
            decision_id=self.decision_id,
            selected_provider=self.selected_provider,
            provider_score=self.provider_score,
            provider_health=self.provider_health,
            provider_version=self.provider_version,
            execution_path=self.execution_path,
            provider_latency_ms=self.provider_latency_ms,
            fallback_used=self.fallback_used,
            planned_provider=self.planned_provider,
            execution_provider=self.execution_provider,
            provider_changed=self.provider_changed,
            provider_change_reason=self.provider_change_reason,
            fallback_reason=self.fallback_reason,
            fallback_policy=self.fallback_policy,
            fallback_decision=self.fallback_decision,
            original_provider=self.original_provider,
            replacement_provider=self.replacement_provider,
            file_operation=self.file_operation,
            target_path=self.target_path,
            directory=self.directory,
            filename=self.filename,
            extension=self.extension,
            keyword=self.keyword,
            recursive=self.recursive,
            execution_mode=self.execution_mode,
            github_operation=self.github_operation,
            repository=self.repository,
            branch=self.branch,
            candidate_providers=self.candidate_providers,
            ranking_score=self.ranking_score,
            reasoning_summary=reasoning_summary or self.reasoning_summary,
            retry_count=self.retry_count,
            telemetry_record_index=self.telemetry_record_index,
            telemetry_snapshot_at=self.telemetry_snapshot_at,
            performance_score=self.performance_score,
            ranking_reason=self.ranking_reason,
            historical_confidence=self.historical_confidence,
            workspace_operation="plan_modification",
            files_considered=affected_files,
            files_read=self.files_read,
            explanation_mode="modification_plan",
            search_query=self.search_query,
            search_results=self.search_results,
            selected_file=self.selected_file,
            ambiguity_status=self.ambiguity_status,
            modification_plan=modification_plan,
            affected_files=affected_files,
            patch_application_requested=True,
        )

    def with_patch_application_context(
        self,
        *,
        patch_result: object,
        confirmation_received: bool,
        rollback_history_size: int = 0,
    ) -> ToolDecisionReport:
        """Return a copy enriched with patch application outcome (P12-006)."""
        from tools.decision.patch_models import PatchApplicationResult

        if not isinstance(patch_result, PatchApplicationResult):
            return self
        return ToolDecisionReport(
            intent=self.intent,
            confidence=self.confidence,
            tool_required=self.tool_required,
            candidate_tools=self.candidate_tools,
            selected_tool=self.selected_tool,
            decision_reason=self.decision_reason,
            risk_level=patch_result.risk_level,
            confirmation_required=self.confirmation_required,
            fallback_action=self.fallback_action,
            classification_reason=self.classification_reason,
            decision_id=self.decision_id,
            selected_provider=self.selected_provider,
            provider_score=self.provider_score,
            provider_health=self.provider_health,
            provider_version=self.provider_version,
            execution_path=self.execution_path,
            provider_latency_ms=self.provider_latency_ms,
            fallback_used=self.fallback_used,
            planned_provider=self.planned_provider,
            execution_provider=self.execution_provider,
            provider_changed=self.provider_changed,
            provider_change_reason=self.provider_change_reason,
            fallback_reason=self.fallback_reason,
            fallback_policy=self.fallback_policy,
            fallback_decision=self.fallback_decision,
            original_provider=self.original_provider,
            replacement_provider=self.replacement_provider,
            file_operation=self.file_operation,
            target_path=self.target_path,
            directory=self.directory,
            filename=self.filename,
            extension=self.extension,
            keyword=self.keyword,
            recursive=self.recursive,
            execution_mode=self.execution_mode,
            github_operation=self.github_operation,
            repository=self.repository,
            branch=self.branch,
            candidate_providers=self.candidate_providers,
            ranking_score=self.ranking_score,
            reasoning_summary=self.reasoning_summary,
            retry_count=self.retry_count,
            telemetry_record_index=self.telemetry_record_index,
            telemetry_snapshot_at=self.telemetry_snapshot_at,
            performance_score=self.performance_score,
            ranking_reason=self.ranking_reason,
            historical_confidence=self.historical_confidence,
            workspace_operation=self.workspace_operation or "apply_modification",
            files_considered=self.files_considered,
            files_read=self.files_read,
            explanation_mode="patch_application",
            search_query=self.search_query,
            search_results=self.search_results,
            selected_file=self.selected_file,
            ambiguity_status=self.ambiguity_status,
            modification_plan=self.modification_plan,
            affected_files=self.affected_files,
            patch_application_requested=True,
            confirmation_received=confirmation_received,
            patch_applied=patch_result.applied,
            files_modified=patch_result.files_modified,
            rollback_available=patch_result.rollback_available,
            confirmation_token=patch_result.confirmation_token,
            patch_application_result=patch_result.to_dict(),
            rollback_id=patch_result.rollback_id,
            rollback_history_size=rollback_history_size,
            rollback_applied=False,
        )

    def with_rollback_context(
        self,
        *,
        rollback_result: object,
        confirmation_received: bool,
        rollback_history_size: int = 0,
    ) -> ToolDecisionReport:
        """Return a copy enriched with rollback restore outcome (P12B2-005)."""
        from tools.decision.rollback_models import RollbackResult

        if not isinstance(rollback_result, RollbackResult):
            return self
        return ToolDecisionReport(
            intent=self.intent,
            confidence=self.confidence,
            tool_required=self.tool_required,
            candidate_tools=self.candidate_tools,
            selected_tool=self.selected_tool,
            decision_reason=self.decision_reason,
            risk_level=self.risk_level,
            confirmation_required=self.confirmation_required,
            fallback_action=self.fallback_action,
            classification_reason=self.classification_reason,
            decision_id=self.decision_id,
            selected_provider=self.selected_provider,
            provider_score=self.provider_score,
            provider_health=self.provider_health,
            provider_version=self.provider_version,
            execution_path=self.execution_path,
            provider_latency_ms=self.provider_latency_ms,
            fallback_used=self.fallback_used,
            planned_provider=self.planned_provider,
            execution_provider=self.execution_provider,
            provider_changed=self.provider_changed,
            provider_change_reason=self.provider_change_reason,
            fallback_reason=self.fallback_reason,
            fallback_policy=self.fallback_policy,
            fallback_decision=self.fallback_decision,
            original_provider=self.original_provider,
            replacement_provider=self.replacement_provider,
            file_operation=self.file_operation,
            target_path=self.target_path,
            directory=self.directory,
            filename=self.filename,
            extension=self.extension,
            keyword=self.keyword,
            recursive=self.recursive,
            execution_mode=self.execution_mode,
            github_operation=self.github_operation,
            repository=self.repository,
            branch=self.branch,
            candidate_providers=self.candidate_providers,
            ranking_score=self.ranking_score,
            reasoning_summary=self.reasoning_summary,
            retry_count=self.retry_count,
            telemetry_record_index=self.telemetry_record_index,
            telemetry_snapshot_at=self.telemetry_snapshot_at,
            performance_score=self.performance_score,
            ranking_reason=self.ranking_reason,
            historical_confidence=self.historical_confidence,
            workspace_operation="rollback",
            files_considered=self.files_considered,
            files_read=self.files_read,
            explanation_mode="rollback",
            search_query=self.search_query,
            search_results=self.search_results,
            selected_file=self.selected_file,
            ambiguity_status=self.ambiguity_status,
            modification_plan=self.modification_plan,
            affected_files=self.affected_files,
            patch_application_requested=self.patch_application_requested,
            confirmation_received=confirmation_received,
            patch_applied=self.patch_applied,
            files_modified=rollback_result.files_restored,
            rollback_available=rollback_history_size > 0,
            confirmation_token=self.confirmation_token,
            patch_application_result=self.patch_application_result,
            rollback_id=rollback_result.rollback_id,
            rollback_history_size=rollback_history_size,
            rollback_applied=rollback_result.applied,
        )

    def with_multi_step_context(
        self,
        *,
        execution_report: object,
    ) -> ToolDecisionReport:
        """Return a copy enriched with multi-step execution outcome (P12B3-006)."""
        from tools.decision.task_execution_models import TaskExecutionReport

        if not isinstance(execution_report, TaskExecutionReport):
            return self
        return ToolDecisionReport(
            intent=self.intent,
            confidence=self.confidence,
            tool_required=self.tool_required,
            candidate_tools=self.candidate_tools,
            selected_tool=self.selected_tool,
            decision_reason=self.decision_reason,
            risk_level=self.risk_level,
            confirmation_required=self.confirmation_required,
            fallback_action=self.fallback_action,
            classification_reason=self.classification_reason,
            decision_id=self.decision_id,
            selected_provider=self.selected_provider,
            provider_score=self.provider_score,
            provider_health=self.provider_health,
            provider_version=self.provider_version,
            execution_path=self.execution_path,
            provider_latency_ms=self.provider_latency_ms,
            fallback_used=self.fallback_used,
            planned_provider=self.planned_provider,
            execution_provider=self.execution_provider,
            provider_changed=self.provider_changed,
            provider_change_reason=self.provider_change_reason,
            fallback_reason=self.fallback_reason,
            fallback_policy=self.fallback_policy,
            fallback_decision=self.fallback_decision,
            original_provider=self.original_provider,
            replacement_provider=self.replacement_provider,
            file_operation=self.file_operation,
            target_path=self.target_path,
            directory=self.directory,
            filename=self.filename,
            extension=self.extension,
            keyword=self.keyword,
            recursive=self.recursive,
            execution_mode=self.execution_mode,
            github_operation=self.github_operation,
            repository=self.repository,
            branch=self.branch,
            candidate_providers=self.candidate_providers,
            ranking_score=self.ranking_score,
            reasoning_summary=self.reasoning_summary,
            retry_count=self.retry_count,
            telemetry_record_index=self.telemetry_record_index,
            telemetry_snapshot_at=self.telemetry_snapshot_at,
            performance_score=self.performance_score,
            ranking_reason=self.ranking_reason,
            historical_confidence=self.historical_confidence,
            workspace_operation=self.workspace_operation or "multi_step_task",
            files_considered=self.files_considered,
            files_read=self.files_read,
            explanation_mode="multi_step_execution",
            search_query=self.search_query,
            search_results=self.search_results,
            selected_file=self.selected_file,
            ambiguity_status=self.ambiguity_status,
            modification_plan=self.modification_plan,
            affected_files=self.affected_files,
            patch_application_requested=self.patch_application_requested,
            confirmation_received=self.confirmation_received,
            patch_applied=self.patch_applied,
            files_modified=self.files_modified,
            rollback_available=self.rollback_available,
            confirmation_token=self.confirmation_token,
            patch_application_result=self.patch_application_result,
            rollback_id=self.rollback_id,
            rollback_history_size=self.rollback_history_size,
            rollback_applied=self.rollback_applied,
            multi_step_execution=True,
            steps_completed=execution_report.steps_completed,
            steps_failed=execution_report.steps_failed,
            total_duration=execution_report.total_duration_ms,
            execution_summary=execution_report.execution_summary,
            task_execution_result=execution_report.to_dict(),
        )


_INTENT_FILE_OPERATIONS: dict[Intent, str] = {
    Intent.FILE_LIST: "list_directory",
    Intent.FILE_SEARCH: "search_files",
    Intent.FILE_READ: "read_file",
    Intent.FILE_METADATA: "get_metadata",
}

_TOOL_FILE_OPERATIONS: dict[str, str] = {
    "file_read": "read_file",
    "file_write": "write_file",
}


def enrich_file_decision_context(
    report: ToolDecisionReport,
    *,
    target_path: str | None = None,
    execution_mode: str | None = None,
    file_operation: str | None = None,
    directory: str | None = None,
    filename: str | None = None,
    extension: str | None = None,
    keyword: str | None = None,
    recursive: bool | None = None,
) -> ToolDecisionReport:
    """Attach filesystem fields to a decision report when a file tool is selected (P10B-505, P10B-1504)."""
    if report.selected_tool not in _TOOL_FILE_OPERATIONS and report.selected_tool != "file_write":
        return report
    operation = file_operation or _INTENT_FILE_OPERATIONS.get(
        report.intent,
        _TOOL_FILE_OPERATIONS.get(report.selected_tool or "", "read_file"),
    )
    return report.with_file_context(
        file_operation=operation,
        target_path=target_path or directory or filename,
        execution_mode=execution_mode,
        selected_provider=report.selected_provider or "file_system",
        directory=directory,
        filename=filename,
        extension=extension,
        keyword=keyword,
        recursive=recursive,
    )


def enrich_github_decision_context(
    report: ToolDecisionReport,
    *,
    github_operation: str | None = None,
    repository: str | None = None,
    branch: str | None = None,
    target_path: str | None = None,
    execution_mode: str | None = None,
) -> ToolDecisionReport:
    """Attach GitHub fields to a decision report when the github tool is selected (P10B-605)."""
    if report.selected_tool != "github":
        return report
    operation = github_operation or str(
        report.github_operation or "get_repository",
    )
    return report.with_github_context(
        github_operation=operation,
        repository=repository,
        branch=branch,
        target_path=target_path,
        execution_mode=execution_mode,
        selected_provider="github",
    )


def enrich_calendar_decision_context(
    report: ToolDecisionReport,
    result: object,
) -> ToolDecisionReport:
    """Attach Calendar decision metadata when the calendar tool is selected (Phase 14.1)."""
    from tools.decision.calendar_decision import CalendarDecisionResult

    if report.selected_tool != "calendar" and report.intent.value != "calendar":
        return report
    if not isinstance(result, CalendarDecisionResult):
        return report
    action = ""
    if result.tool_params:
        action = str(dict(result.tool_params).get("action", ""))
    summary = f"Calendar {result.decision.value}: {result.reason}"
    return report.with_calendar_context(
        calendar_decision=result.decision.value,
        calendar_action=action or None,
        reasoning_summary=summary,
    )


def enrich_email_decision_context(
    report: ToolDecisionReport,
    result: object,
) -> ToolDecisionReport:
    """Attach Email decision metadata when the email tool is selected (Phase 15.1)."""
    from tools.decision.email_decision import EmailDecisionResult

    if report.selected_tool != "email" and report.intent.value != "email":
        return report
    if not isinstance(result, EmailDecisionResult):
        return report
    action = ""
    if result.tool_params:
        action = str(dict(result.tool_params).get("action", ""))
    summary = f"Email {result.decision.value}: {result.reason}"
    return report.with_email_context(
        email_decision=result.decision.value,
        email_action=action or None,
        reasoning_summary=summary,
    )


def enrich_trading_decision_context(
    report: ToolDecisionReport,
    result: object,
) -> ToolDecisionReport:
    """Attach Trading decision metadata when the trading tool is selected (Phase 16.1)."""
    from tools.decision.trading_decision import TradingDecisionResult

    if report.selected_tool != "trading" and report.intent.value != "trading":
        return report
    if not isinstance(result, TradingDecisionResult):
        return report
    action = ""
    if result.tool_params:
        action = str(dict(result.tool_params).get("action", ""))
    summary = f"Trading {result.decision.value}: {result.reason}"
    return report.with_trading_context(
        trading_decision=result.decision.value,
        trading_action=action or None,
        reasoning_summary=summary,
    )


def enrich_browser_decision_context(
    report: ToolDecisionReport,
    result: object,
) -> ToolDecisionReport:
    """Attach Browser decision metadata when the browser tool is selected (Phase 13.1)."""
    from tools.decision.browser_decision import BrowserDecisionResult

    if report.selected_tool != "browser" and report.intent.value != "browser":
        return report
    if not isinstance(result, BrowserDecisionResult):
        return report
    action = ""
    if result.tool_params:
        action = str(dict(result.tool_params).get("action", ""))
    summary = f"Browser {result.decision.value}: {result.reason}"
    return report.with_browser_context(
        browser_decision=result.decision.value,
        browser_action=action or None,
        target_path=result.url or None,
        reasoning_summary=summary,
    )


def enrich_obsidian_decision_context(
    report: ToolDecisionReport,
    result: object,
) -> ToolDecisionReport:
    """Attach Obsidian decision metadata when the obsidian tool is selected (P125-007)."""
    from tools.decision.obsidian_decision import ObsidianDecisionResult

    if report.selected_tool != "obsidian" and report.intent.value != "obsidian":
        return report
    if not isinstance(result, ObsidianDecisionResult):
        return report
    action = ""
    if result.tool_params:
        action = str(dict(result.tool_params).get("action", ""))
    summary = f"Obsidian {result.decision.value}: {result.reason}"
    return report.with_obsidian_context(
        obsidian_decision=result.decision.value,
        obsidian_action=action or None,
        obsidian_search_mode=(
            result.search_mode.value if result.search_mode is not None else None
        ),
        target_path=result.target_path,
        keyword=result.query,
        directory=result.folder,
        reasoning_summary=summary,
    )


def enrich_workspace_decision_context(
    report: ToolDecisionReport,
    plan: object,
    *,
    execution_mode: str | None = None,
) -> ToolDecisionReport:
    """Attach workspace intelligence fields from a WorkspacePlan (P11-004)."""
    from tools.decision.workspace_planner import WorkspacePlan

    if not isinstance(plan, WorkspacePlan):
        return report
    summary = plan.area_summary or report.reasoning_summary
    if plan.workspace_operation:
        summary = (
            f"Workspace {plan.workspace_operation} "
            f"(mode={plan.explanation_mode}); "
            f"{len(plan.files_considered)} fichier(s) considéré(s)."
        )
        if plan.area_summary:
            summary = f"{summary} {plan.area_summary}"
    return report.with_workspace_context(
        workspace_operation=plan.workspace_operation,
        explanation_mode=plan.explanation_mode,
        files_considered=plan.files_considered,
        confidence=plan.confidence,
        reasoning_summary=summary,
        selected_provider=report.selected_provider or "file_system",
        execution_mode=execution_mode,
        search_query=plan.search_query or None,
        search_results=plan.search_results,
        selected_file=plan.selected_file,
        ambiguity_status=plan.ambiguity_status or None,
    )


def enrich_rollback_decision_context(
    report: ToolDecisionReport,
    rollback_result: object,
    *,
    confirmation_received: bool,
    rollback_history_size: int = 0,
) -> ToolDecisionReport:
    """Attach rollback fields to a decision report (P12B2-005)."""
    return report.with_rollback_context(
        rollback_result=rollback_result,
        confirmation_received=confirmation_received,
        rollback_history_size=rollback_history_size,
    )


def enrich_patch_application_decision_context(
    report: ToolDecisionReport,
    patch_result: object,
    *,
    confirmation_received: bool,
    rollback_history_size: int = 0,
) -> ToolDecisionReport:
    """Attach patch application fields to a decision report (P12-006)."""
    return report.with_patch_application_context(
        patch_result=patch_result,
        confirmation_received=confirmation_received,
        rollback_history_size=rollback_history_size,
    )


def enrich_task_execution_decision_context(
    report: ToolDecisionReport,
    execution_report: object,
) -> ToolDecisionReport:
    """Attach multi-step execution fields to a decision report (P12B3-006)."""
    return report.with_multi_step_context(execution_report=execution_report)


def enrich_modification_decision_context(
    report: ToolDecisionReport,
    plan: object,
) -> ToolDecisionReport:
    """Attach modification planning fields from a ModificationPlan (P11-304)."""
    from tools.decision.modification_models import ModificationPlan

    if not isinstance(plan, ModificationPlan):
        return report
    summary = (
        f"Plan de modification ({plan.modification_type}) — "
        f"{len(plan.affected_files)} fichier(s); "
        f"risque {plan.estimated_risk.value}."
    )
    if plan.ambiguous:
        summary = plan.ambiguity_reason or summary
    return report.with_modification_context(
        modification_plan=plan.to_dict(),
        affected_files=plan.affected_files,
        confidence=plan.confidence,
        reasoning_summary=summary,
        risk_level=plan.estimated_risk,
    )


@dataclass
class ToolNeedAssessment:
    """Output of the tool-needed detector (P10B-003)."""

    tool_required: bool
    reason: str


@dataclass
class IntentRule:
    """Keyword rule contributing to intent classification."""

    intent: Intent
    keywords: tuple[str, ...]
    weight: float
    reason: str

    def score(self, lowered: str) -> float:
        """Return weighted score when any keyword matches."""
        if not self.keywords:
            return 0.0
        hits = sum(1 for kw in self.keywords if kw in lowered)
        if hits == 0:
            return 0.0
        return self.weight * min(1.0 + (hits - 1) * 0.1, 1.5)


DEFAULT_AVAILABLE_TOOLS: frozenset[str] = frozenset(
    {
        "time",
        "file_read",
        "file_write",
        "python_exec",
        "web_search",
        "calendar",
        "email",
        "trading",
        "github",
        "obsidian",
        "browser",
    },
)
