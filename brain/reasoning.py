# =====================================
# Titan Reasoning System
# =====================================

"""Intent analysis with tool-request heuristics (Phase 6 — P6-032; Phase 10B — P10B bridge)."""

from __future__ import annotations

import re
from pathlib import Path

from config.settings import (
    PROJECT_ROOT,
    TITAN_BROWSER_ENABLED,
    TITAN_BROWSER_TIMEOUT_SECONDS,
    TITAN_CALENDAR_ENABLED,
    TITAN_CALENDAR_TIMEOUT_SECONDS,
    TITAN_EMAIL_ENABLED,
    TITAN_EMAIL_TIMEOUT_SECONDS,
    TITAN_TRADING_ENABLED,
    TITAN_TRADING_TIMEOUT_SECONDS,
    TITAN_OBSIDIAN_ENABLED,
    TITAN_OBSIDIAN_VAULT_PATH,
    TITAN_TOOL_DEFAULT_EXECUTION_MODE,
    TITAN_TOOL_DECISION_ENGINE,
)
from tools.decision.capability_availability import CapabilityAvailabilityResolver
from tools.decision.file_param_parser import (
    FileOperationParams,
    parse_file_params,
    params_to_tool_dict,
)
from tools.decision.intent import Intent
from tools.decision.models import (
    FallbackAction,
    enrich_browser_decision_context,
    enrich_calendar_decision_context,
    enrich_email_decision_context,
    enrich_trading_decision_context,
    enrich_file_decision_context,
    enrich_github_decision_context,
    enrich_modification_decision_context,
    enrich_obsidian_decision_context,
    enrich_patch_application_decision_context,
    enrich_rollback_decision_context,
    enrich_workspace_decision_context,
)
from tools.decision.browser_decision import BrowserDecision, BrowserDecisionEngine
from tools.decision.calendar_decision import CalendarDecision, CalendarDecisionEngine
from tools.decision.email_decision import EmailDecision, EmailDecisionEngine
from tools.decision.trading_decision import TradingDecision, TradingDecisionEngine
from tools.decision.obsidian_decision import ObsidianDecision, ObsidianDecisionEngine
from tools.connectors.browser_connector import BrowserConnector
from tools.connectors.calendar_connector import CalendarConnector
from tools.connectors.email_connector import EmailConnector
from tools.connectors.trading_connector import TradingConnector
from tools.connectors.obsidian_connector import ObsidianConnector
from tools.decision.patch_application_engine import PatchApplicationEngine
from tools.decision.patch_confirmation_gate import (
    get_patch_confirmation_gate,
    is_valid_patch_confirmation,
)
from tools.decision.rollback_command_parser import parse_rollback_command
from tools.decision.rollback_confirmation_gate import (
    get_rollback_confirmation_gate,
    is_valid_rollback_confirmation,
)
from tools.decision.rollback_manager import get_rollback_manager
from tools.decision.tool_decision_engine import ToolDecisionEngine
from tools.decision.workspace_modification_planner import WorkspaceModificationPlanner
from tools.decision.workspace_planner import plan_workspace_operation
from tools.tool_result import ToolRequest

_FILE_INTENTS = frozenset({
    Intent.FILE,
    Intent.FILE_LIST,
    Intent.FILE_SEARCH,
    Intent.FILE_READ,
    Intent.FILE_METADATA,
})

_TIME_KEYWORDS = (
    "heure",
    "quelle heure",
    "what time",
    "current time",
    "datetime",
    "date et heure",
    "quelle date",
)
_READ_KEYWORDS = (
    "lire le fichier",
    "lire fichier",
    "read file",
    "contenu du fichier",
    "affiche le fichier",
    "ouvre le fichier",
    "show file",
    "open file",
)
_WRITE_KEYWORDS = (
    "écris dans",
    "ecrire dans",
    "write file",
    "crée le fichier",
    "cree le fichier",
    "create file",
    "écrire le fichier",
)
_PYTHON_KEYWORDS = (
    "exécute python",
    "execute python",
    "run python",
    "python:",
    "exec python",
    "lance ce code",
)
_WEB_KEYWORDS = (
    "recherche web",
    "web search",
    "cherche sur internet",
    "google ",
)
_PATH_PATTERN = re.compile(
    r"(?:[\w./\\-]+[/\\])?[\w.-]+\.(?:py|txt|md|json|yaml|yml|toml|cfg|ini)",
    re.IGNORECASE,
)
_CODE_BLOCK_PATTERN = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class Reasoning:
    """Analyze user messages and emit structured tool requests when needed."""

    def __init__(
        self,
        *,
        decision_engine: ToolDecisionEngine | None = None,
        use_decision_engine: bool | None = None,
        project_root: Path | None = None,
    ) -> None:
        self.decision_engine = decision_engine or ToolDecisionEngine()
        self._use_decision_engine = (
            TITAN_TOOL_DECISION_ENGINE
            if use_decision_engine is None
            else use_decision_engine
        )
        self._project_root = (project_root or PROJECT_ROOT).resolve()

    def _rollback_manager(self):
        """Return the rollback manager scoped to this reasoning instance."""
        return get_rollback_manager(self._project_root)

    def analyze(
        self,
        message: str,
        *,
        available_tools: frozenset[str] | None = None,
        availability_resolver: CapabilityAvailabilityResolver | None = None,
    ) -> dict:
        """Return analysis dict with tool requests for Brain executor."""
        if self._use_decision_engine:
            return self._analyze_with_decision_engine(
                message,
                available_tools=available_tools,
                availability_resolver=availability_resolver,
            )
        return self._analyze_legacy(message)

    def _analyze_with_decision_engine(
        self,
        message: str,
        *,
        available_tools: frozenset[str] | None = None,
        availability_resolver: CapabilityAvailabilityResolver | None = None,
    ) -> dict:
        report = self.decision_engine.decide(
            message,
            available_tools=available_tools,
            availability_resolver=availability_resolver,
        )

        if is_valid_rollback_confirmation(message):
            return self._analyze_rollback_confirmation(message, report)

        rollback_cmd = parse_rollback_command(message)
        if rollback_cmd is not None:
            return self._analyze_rollback_request(message, rollback_cmd, report)

        if is_valid_patch_confirmation(message):
            return self._analyze_patch_confirmation(message, report)
        file_params = (
            parse_file_params(message, report.intent)
            if report.intent in _FILE_INTENTS
            else None
        )
        if file_params is not None and file_params.ambiguous:
            report = self._ambiguous_file_report(report, file_params)
        elif file_params is not None:
            report = enrich_file_decision_context(
                report,
                target_path=file_params.filename or file_params.directory,
                execution_mode=TITAN_TOOL_DEFAULT_EXECUTION_MODE,
                file_operation=file_params.operation,
                directory=file_params.directory,
                filename=file_params.filename,
                extension=file_params.extension,
                keyword=file_params.keyword,
                recursive=file_params.recursive,
            )
        else:
            path = _extract_path(message)
            report = enrich_file_decision_context(
                report,
                target_path=path,
                execution_mode=TITAN_TOOL_DEFAULT_EXECUTION_MODE,
            )
        report = enrich_github_decision_context(
            report,
            github_operation=_infer_github_operation(message),
            execution_mode=TITAN_TOOL_DEFAULT_EXECUTION_MODE,
        )
        obsidian_result = None
        if report.selected_tool == "obsidian" or report.intent == Intent.OBSIDIAN:
            obsidian_result = self._resolve_obsidian_decision(message)
            report = enrich_obsidian_decision_context(report, obsidian_result)
        browser_result = None
        if report.selected_tool == "browser" or report.intent == Intent.BROWSER:
            browser_result = self._resolve_browser_decision(message)
            report = enrich_browser_decision_context(report, browser_result)
        calendar_result = None
        if report.selected_tool == "calendar" or report.intent == Intent.CALENDAR:
            calendar_result = self._resolve_calendar_decision(message)
            report = enrich_calendar_decision_context(report, calendar_result)
        email_result = None
        if report.selected_tool == "email" or report.intent == Intent.EMAIL:
            email_result = self._resolve_email_decision(message)
            report = enrich_email_decision_context(report, email_result)
        trading_result = None
        if report.selected_tool == "trading" or report.intent == Intent.TRADING:
            trading_result = self._resolve_trading_decision(message)
            report = enrich_trading_decision_context(report, trading_result)
        tool_requests: list[ToolRequest] = []

        if report.intent == Intent.WORKSPACE_EXPLAIN:
            return self._analyze_workspace(message, report, tool_requests)

        if report.intent == Intent.WORKSPACE_MODIFY:
            return self._analyze_modification(message, report)

        if report.fallback_action == FallbackAction.EXECUTE_TOOL and report.selected_tool:
            if report.selected_tool == "obsidian" and obsidian_result is not None:
                if obsidian_result.decision == ObsidianDecision.DO_NOT_USE_OBSIDIAN:
                    report = self._obsidian_direct_answer_report(report, obsidian_result)
                else:
                    tool_requests.append(
                        ToolRequest(
                            "obsidian",
                            obsidian_result.tool_params_dict(),
                        ),
                    )
            elif report.selected_tool == "browser" and browser_result is not None:
                if browser_result.decision == BrowserDecision.DO_NOT_USE_BROWSER:
                    report = self._browser_direct_answer_report(report, browser_result)
                else:
                    tool_requests.append(
                        ToolRequest(
                            "browser",
                            browser_result.tool_params_dict(),
                        ),
                    )
            elif report.selected_tool == "calendar" and calendar_result is not None:
                if calendar_result.decision == CalendarDecision.DO_NOT_USE_CALENDAR:
                    report = self._calendar_direct_answer_report(report, calendar_result)
                else:
                    tool_requests.append(
                        ToolRequest(
                            "calendar",
                            calendar_result.tool_params_dict(),
                        ),
                    )
            elif report.selected_tool == "email" and email_result is not None:
                if email_result.decision == EmailDecision.DO_NOT_USE_EMAIL:
                    report = self._email_direct_answer_report(report, email_result)
                else:
                    tool_requests.append(
                        ToolRequest(
                            "email",
                            email_result.tool_params_dict(),
                        ),
                    )
            elif report.selected_tool == "trading" and trading_result is not None:
                if trading_result.decision == TradingDecision.DO_NOT_USE_TRADING:
                    report = self._trading_direct_answer_report(report, trading_result)
                else:
                    tool_requests.append(
                        ToolRequest(
                            "trading",
                            trading_result.tool_params_dict(),
                        ),
                    )
            else:
                params = _build_tool_params(message, report.selected_tool, file_params)
                tool_requests.append(ToolRequest(report.selected_tool, params))

        needs_clarification = report.fallback_action in {
            FallbackAction.NO_CAPABILITY,
            FallbackAction.CLARIFICATION,
        }

        return {
            "message": message,
            "goal": "Comprendre la demande de l'utilisateur",
            "needs_memory": report.intent.value == "memory",
            "needs_tool": report.tool_required and bool(tool_requests),
            "needs_clarification": needs_clarification,
            "tool_requests": tool_requests,
            "decision_report": report,
            "fallback_action": report.fallback_action.value,
            "confirmation_required": report.confirmation_required,
        }

    def _obsidian_connector(self) -> ObsidianConnector:
        """Build an Obsidian connector from environment settings."""
        configured = TITAN_OBSIDIAN_VAULT_PATH
        resolved = Path(configured).expanduser() if configured else None
        return ObsidianConnector(resolved, enabled=TITAN_OBSIDIAN_ENABLED)

    def _browser_connector(self) -> BrowserConnector:
        """Build a Browser connector from environment settings."""
        return BrowserConnector(
            enabled=TITAN_BROWSER_ENABLED,
            timeout_seconds=TITAN_BROWSER_TIMEOUT_SECONDS,
        )

    def _resolve_obsidian_decision(self, message: str):
        """Run the Obsidian decision layer for a user message (P125-007)."""
        connector = self._obsidian_connector()
        return ObsidianDecisionEngine(connector).decide(message)

    def _resolve_browser_decision(self, message: str):
        """Run the Browser decision layer for a user message (Phase 13.1)."""
        connector = self._browser_connector()
        return BrowserDecisionEngine(connector).decide(message)

    def _calendar_connector(self) -> CalendarConnector:
        """Build a Calendar connector from environment settings."""
        return CalendarConnector(
            enabled=TITAN_CALENDAR_ENABLED,
            timeout_seconds=TITAN_CALENDAR_TIMEOUT_SECONDS,
        )

    def _resolve_calendar_decision(self, message: str):
        """Run the Calendar decision layer for a user message (Phase 14.1)."""
        connector = self._calendar_connector()
        return CalendarDecisionEngine(connector).decide(message)

    def _email_connector(self) -> EmailConnector:
        """Build an Email connector from environment settings."""
        return EmailConnector(
            enabled=TITAN_EMAIL_ENABLED,
            timeout_seconds=TITAN_EMAIL_TIMEOUT_SECONDS,
        )

    def _resolve_email_decision(self, message: str):
        """Run the Email decision layer for a user message (Phase 15.1)."""
        connector = self._email_connector()
        return EmailDecisionEngine(connector).decide(message)

    def _trading_connector(self) -> TradingConnector:
        """Build a Trading connector from environment settings."""
        return TradingConnector(
            enabled=TITAN_TRADING_ENABLED,
            timeout_seconds=TITAN_TRADING_TIMEOUT_SECONDS,
        )

    def _resolve_trading_decision(self, message: str):
        """Run the Trading decision layer for a user message (Phase 16.1)."""
        connector = self._trading_connector()
        return TradingDecisionEngine(connector).decide(message)

    def _obsidian_direct_answer_report(self, report, obsidian_result):
        """Convert a DO_NOT_USE_OBSIDIAN outcome into a direct-answer report."""
        from tools.decision.models import ToolDecisionReport
        from tools.tool_enums import RiskLevel

        return ToolDecisionReport(
            intent=report.intent,
            confidence=report.confidence,
            tool_required=False,
            candidate_tools=report.candidate_tools,
            selected_tool=report.selected_tool,
            decision_reason=obsidian_result.reason,
            risk_level=RiskLevel.SAFE,
            confirmation_required=False,
            fallback_action=FallbackAction.DIRECT_ANSWER,
            classification_reason=report.classification_reason,
            decision_id=report.decision_id,
            reasoning_summary=obsidian_result.reason,
            execution_mode=report.execution_mode,
            obsidian_decision=obsidian_result.decision.value,
        )

    def _browser_direct_answer_report(self, report, browser_result):
        """Convert a DO_NOT_USE_BROWSER outcome into a direct-answer report."""
        from tools.decision.models import ToolDecisionReport
        from tools.tool_enums import RiskLevel

        return ToolDecisionReport(
            intent=report.intent,
            confidence=report.confidence,
            tool_required=False,
            candidate_tools=report.candidate_tools,
            selected_tool=report.selected_tool,
            decision_reason=browser_result.reason,
            risk_level=RiskLevel.SAFE,
            confirmation_required=False,
            fallback_action=FallbackAction.DIRECT_ANSWER,
            classification_reason=report.classification_reason,
            decision_id=report.decision_id,
            reasoning_summary=browser_result.reason,
            execution_mode=report.execution_mode,
            browser_decision=browser_result.decision.value,
        )

    def _calendar_direct_answer_report(self, report, calendar_result):
        """Convert a DO_NOT_USE_CALENDAR outcome into a direct-answer report."""
        from tools.decision.models import ToolDecisionReport
        from tools.tool_enums import RiskLevel

        return ToolDecisionReport(
            intent=report.intent,
            confidence=report.confidence,
            tool_required=False,
            candidate_tools=report.candidate_tools,
            selected_tool=report.selected_tool,
            decision_reason=calendar_result.reason,
            risk_level=RiskLevel.SAFE,
            confirmation_required=False,
            fallback_action=FallbackAction.DIRECT_ANSWER,
            classification_reason=report.classification_reason,
            decision_id=report.decision_id,
            reasoning_summary=calendar_result.reason,
            execution_mode=report.execution_mode,
            calendar_decision=calendar_result.decision.value,
        )

    def _email_direct_answer_report(self, report, email_result):
        """Convert a DO_NOT_USE_EMAIL outcome into a direct-answer report."""
        from tools.decision.models import ToolDecisionReport
        from tools.tool_enums import RiskLevel

        return ToolDecisionReport(
            intent=report.intent,
            confidence=report.confidence,
            tool_required=False,
            candidate_tools=report.candidate_tools,
            selected_tool=report.selected_tool,
            decision_reason=email_result.reason,
            risk_level=RiskLevel.SAFE,
            confirmation_required=False,
            fallback_action=FallbackAction.DIRECT_ANSWER,
            classification_reason=report.classification_reason,
            decision_id=report.decision_id,
            reasoning_summary=email_result.reason,
            execution_mode=report.execution_mode,
            email_decision=email_result.decision.value,
        )

    def _trading_direct_answer_report(self, report, trading_result):
        """Convert a DO_NOT_USE_TRADING outcome into a direct-answer report."""
        from tools.decision.models import ToolDecisionReport
        from tools.tool_enums import RiskLevel

        return ToolDecisionReport(
            intent=report.intent,
            confidence=report.confidence,
            tool_required=False,
            candidate_tools=report.candidate_tools,
            selected_tool=report.selected_tool,
            decision_reason=trading_result.reason,
            risk_level=RiskLevel.SAFE,
            confirmation_required=False,
            fallback_action=FallbackAction.DIRECT_ANSWER,
            classification_reason=report.classification_reason,
            decision_id=report.decision_id,
            reasoning_summary=trading_result.reason,
            execution_mode=report.execution_mode,
            trading_decision=trading_result.decision.value,
        )

    def _analyze_workspace(
        self,
        message: str,
        report,
        tool_requests: list[ToolRequest],
    ) -> dict:
        """Plan workspace intelligence tool requests (P11-001/002)."""
        plan = plan_workspace_operation(
            message,
            project_root=self._project_root,
            confidence=report.confidence,
        )
        if plan.ambiguous:
            report = self._ambiguous_workspace_report(report, plan)
        else:
            report = enrich_workspace_decision_context(
                report,
                plan,
                execution_mode=TITAN_TOOL_DEFAULT_EXECUTION_MODE,
            )
            report = enrich_file_decision_context(
                report,
                target_path=plan.files_considered[0] if plan.files_considered else None,
                execution_mode=TITAN_TOOL_DEFAULT_EXECUTION_MODE,
                file_operation="read_file",
            )
            tool_requests.extend(plan.tool_requests)

        needs_clarification = report.fallback_action in {
            FallbackAction.NO_CAPABILITY,
            FallbackAction.CLARIFICATION,
        }
        return {
            "message": message,
            "goal": "Comprendre et expliquer le workspace",
            "needs_memory": False,
            "needs_tool": report.tool_required and bool(tool_requests),
            "needs_clarification": needs_clarification,
            "tool_requests": tool_requests,
            "decision_report": report,
            "fallback_action": report.fallback_action.value,
            "confirmation_required": report.confirmation_required,
            "workspace_plan": plan,
        }

    def _analyze_modification(self, message: str, report) -> dict:
        """Plan workspace modifications without tool execution or writes (P11-301–P11-306)."""
        from tools.decision.models import ToolDecisionReport
        from tools.tool_enums import RiskLevel

        planner = WorkspaceModificationPlanner(project_root=self._project_root)
        plan = planner.plan(message, confidence=report.confidence)

        if plan.ambiguous:
            report = ToolDecisionReport(
                intent=report.intent,
                confidence=min(report.confidence, plan.confidence),
                tool_required=False,
                candidate_tools=report.candidate_tools,
                selected_tool=None,
                decision_reason=plan.ambiguity_reason,
                risk_level=plan.estimated_risk,
                confirmation_required=True,
                fallback_action=FallbackAction.CLARIFICATION,
                classification_reason=report.classification_reason,
                reasoning_summary=plan.ambiguity_reason,
                workspace_operation="plan_modification",
                explanation_mode="modification_plan",
                modification_plan=plan.to_dict(),
                affected_files=plan.affected_files,
            )
        else:
            report = enrich_modification_decision_context(report, plan)

        gate = get_patch_confirmation_gate()
        confirmation_token = ""
        if not plan.ambiguous:
            confirmation_token = gate.register_plan(plan, session_id="default")
            report = ToolDecisionReport(
                intent=report.intent,
                confidence=report.confidence,
                tool_required=report.tool_required,
                candidate_tools=report.candidate_tools,
                selected_tool=report.selected_tool,
                decision_reason=report.decision_reason,
                risk_level=report.risk_level,
                confirmation_required=True,
                fallback_action=report.fallback_action,
                classification_reason=report.classification_reason,
                decision_id=report.decision_id,
                selected_provider=report.selected_provider,
                provider_score=report.provider_score,
                provider_health=report.provider_health,
                provider_version=report.provider_version,
                execution_path=report.execution_path,
                provider_latency_ms=report.provider_latency_ms,
                fallback_used=report.fallback_used,
                planned_provider=report.planned_provider,
                execution_provider=report.execution_provider,
                provider_changed=report.provider_changed,
                provider_change_reason=report.provider_change_reason,
                fallback_reason=report.fallback_reason,
                fallback_policy=report.fallback_policy,
                fallback_decision=report.fallback_decision,
                original_provider=report.original_provider,
                replacement_provider=report.replacement_provider,
                file_operation=report.file_operation,
                target_path=report.target_path,
                directory=report.directory,
                filename=report.filename,
                extension=report.extension,
                keyword=report.keyword,
                recursive=report.recursive,
                execution_mode=report.execution_mode,
                github_operation=report.github_operation,
                repository=report.repository,
                branch=report.branch,
                candidate_providers=report.candidate_providers,
                ranking_score=report.ranking_score,
                reasoning_summary=report.reasoning_summary,
                retry_count=report.retry_count,
                telemetry_record_index=report.telemetry_record_index,
                telemetry_snapshot_at=report.telemetry_snapshot_at,
                performance_score=report.performance_score,
                ranking_reason=report.ranking_reason,
                historical_confidence=report.historical_confidence,
                workspace_operation=report.workspace_operation,
                files_considered=report.files_considered,
                files_read=report.files_read,
                explanation_mode=report.explanation_mode,
                search_query=report.search_query,
                search_results=report.search_results,
                selected_file=report.selected_file,
                ambiguity_status=report.ambiguity_status,
                modification_plan=report.modification_plan,
                affected_files=report.affected_files,
                patch_application_requested=True,
                confirmation_token=confirmation_token,
            )

        from tools.decision.modification_guidance import format_modification_plan_summary

        return {
            "message": message,
            "goal": "Planifier une modification workspace sans écriture",
            "needs_memory": False,
            "needs_tool": False,
            "needs_clarification": plan.ambiguous,
            "tool_requests": [],
            "decision_report": report,
            "fallback_action": report.fallback_action.value,
            "confirmation_required": True,
            "modification_plan": plan,
            "modification_plan_text": format_modification_plan_summary(plan),
        }

    def _analyze_patch_confirmation(self, message: str, report) -> dict:
        """Apply pending modification plan after explicit user confirmation (P12-001–P12-006)."""
        from tools.decision.models import ToolDecisionReport
        from tools.decision.modification_guidance import format_patch_application_summary
        from tools.tool_enums import RiskLevel

        gate = get_patch_confirmation_gate()
        pending = gate.get_latest(session_id="default")
        if pending is None:
            clarification = ToolDecisionReport(
                intent=report.intent,
                confidence=report.confidence,
                tool_required=False,
                candidate_tools=report.candidate_tools,
                selected_tool=None,
                decision_reason=(
                    "Aucun plan de modification en attente — "
                    "formule d'abord une demande de modification."
                ),
                risk_level=RiskLevel.LOW,
                confirmation_required=True,
                fallback_action=FallbackAction.CLARIFICATION,
                classification_reason=report.classification_reason,
                patch_application_requested=True,
                confirmation_received=False,
            )
            return {
                "message": message,
                "goal": "Confirmer application de patch",
                "needs_memory": False,
                "needs_tool": False,
                "needs_clarification": True,
                "tool_requests": [],
                "decision_report": clarification,
                "fallback_action": FallbackAction.CLARIFICATION.value,
                "confirmation_required": True,
                "patch_application_text": (
                    "Aucun plan en attente. Demande une modification d'abord, "
                    "puis confirme avec : approve, confirm, ou apply patch."
                ),
            }

        engine = PatchApplicationEngine(
            project_root=self._project_root,
            rollback_manager=self._rollback_manager(),
        )
        patch_result = engine.apply(
            pending.plan,
            confirmed=True,
            confirmation_message=message,
            confirmation_token=pending.token,
            patch_id=pending.token,
        )

        if patch_result.applied:
            gate.consume(pending.token)

        rollback_mgr = self._rollback_manager()
        base = ToolDecisionReport(
            intent=Intent.WORKSPACE_MODIFY,
            confidence=pending.plan.confidence,
            tool_required=False,
            candidate_tools=report.candidate_tools,
            selected_tool=None,
            decision_reason="Application de patch workspace",
            risk_level=patch_result.risk_level,
            confirmation_required=False,
            fallback_action=FallbackAction.DIRECT_ANSWER,
            classification_reason=report.classification_reason,
            modification_plan=pending.plan.to_dict(),
            affected_files=pending.plan.affected_files,
            patch_application_requested=True,
            confirmation_token=pending.token,
        )
        enriched = enrich_patch_application_decision_context(
            base,
            patch_result,
            confirmation_received=True,
            rollback_history_size=rollback_mgr.history_size(),
        )

        return {
            "message": message,
            "goal": "Appliquer modification workspace confirmée",
            "needs_memory": False,
            "needs_tool": False,
            "needs_clarification": not patch_result.applied,
            "tool_requests": [],
            "decision_report": enriched,
            "fallback_action": enriched.fallback_action.value,
            "confirmation_required": False,
            "modification_plan": pending.plan,
            "patch_application_result": patch_result,
            "patch_application_text": format_patch_application_summary(patch_result),
        }

    def _analyze_rollback_request(self, message: str, rollback_cmd, report) -> dict:
        """Register pending rollback and request explicit confirmation (P12B2-003)."""
        from tools.decision.models import ToolDecisionReport
        from tools.decision.modification_guidance import format_rollback_request_summary
        from tools.tool_enums import RiskLevel

        rollback_mgr = self._rollback_manager()
        if rollback_cmd.target_rollback_id:
            snapshot = rollback_mgr.get_snapshot(rollback_cmd.target_rollback_id)
        else:
            snapshot = rollback_mgr.get_latest_snapshot()

        if snapshot is None:
            clarification = ToolDecisionReport(
                intent=report.intent,
                confidence=report.confidence,
                tool_required=False,
                candidate_tools=report.candidate_tools,
                selected_tool=None,
                decision_reason="Aucun snapshot rollback disponible.",
                risk_level=RiskLevel.LOW,
                confirmation_required=False,
                fallback_action=FallbackAction.CLARIFICATION,
                classification_reason=report.classification_reason,
                workspace_operation="rollback",
                explanation_mode="rollback",
                rollback_available=False,
                rollback_history_size=rollback_mgr.history_size(),
            )
            return {
                "message": message,
                "goal": "Restaurer un patch précédent",
                "needs_memory": False,
                "needs_tool": False,
                "needs_clarification": True,
                "tool_requests": [],
                "decision_report": clarification,
                "fallback_action": FallbackAction.CLARIFICATION.value,
                "confirmation_required": False,
                "rollback_text": (
                    "Aucun snapshot rollback disponible. "
                    "Applique d'abord un patch confirmé pour créer un point de restauration."
                ),
            }

        gate = get_rollback_confirmation_gate()
        gate.register(snapshot.rollback_id)
        request_text = format_rollback_request_summary(
            rollback_id=snapshot.rollback_id,
            files_modified=snapshot.files_modified,
            files_created=snapshot.files_created,
            timestamp=snapshot.timestamp,
        )
        pending_report = ToolDecisionReport(
            intent=Intent.WORKSPACE_MODIFY,
            confidence=report.confidence,
            tool_required=False,
            candidate_tools=report.candidate_tools,
            selected_tool=None,
            decision_reason="Rollback workspace en attente de confirmation",
            risk_level=snapshot.risk_level,
            confirmation_required=True,
            fallback_action=FallbackAction.CLARIFICATION,
            classification_reason=report.classification_reason,
            workspace_operation="rollback",
            explanation_mode="rollback",
            rollback_available=True,
            rollback_id=snapshot.rollback_id,
            rollback_history_size=rollback_mgr.history_size(),
            affected_files=snapshot.files_modified + snapshot.files_created,
        )
        return {
            "message": message,
            "goal": "Restaurer un patch précédent",
            "needs_memory": False,
            "needs_tool": False,
            "needs_clarification": True,
            "tool_requests": [],
            "decision_report": pending_report,
            "fallback_action": FallbackAction.CLARIFICATION.value,
            "confirmation_required": True,
            "rollback_text": request_text,
        }

    def _analyze_rollback_confirmation(self, message: str, report) -> dict:
        """Apply pending rollback after explicit user confirmation (P12B2-003)."""
        from tools.decision.models import ToolDecisionReport
        from tools.decision.modification_guidance import format_rollback_summary
        from tools.tool_enums import RiskLevel

        gate = get_rollback_confirmation_gate()
        pending = gate.get_latest(session_id="default")
        rollback_mgr = self._rollback_manager()

        if pending is None:
            clarification = ToolDecisionReport(
                intent=report.intent,
                confidence=report.confidence,
                tool_required=False,
                candidate_tools=report.candidate_tools,
                selected_tool=None,
                decision_reason=(
                    "Aucun rollback en attente — "
                    "utilise d'abord undo, rollback, ou restore patch <id>."
                ),
                risk_level=RiskLevel.LOW,
                confirmation_required=True,
                fallback_action=FallbackAction.CLARIFICATION,
                classification_reason=report.classification_reason,
                workspace_operation="rollback",
                explanation_mode="rollback",
                rollback_history_size=rollback_mgr.history_size(),
            )
            return {
                "message": message,
                "goal": "Confirmer rollback workspace",
                "needs_memory": False,
                "needs_tool": False,
                "needs_clarification": True,
                "tool_requests": [],
                "decision_report": clarification,
                "fallback_action": FallbackAction.CLARIFICATION.value,
                "confirmation_required": True,
                "rollback_text": (
                    "Aucun rollback en attente. Commandes : undo, rollback, "
                    "restore previous patch, restore patch <id>."
                ),
            }

        rollback_result = rollback_mgr.restore(
            pending.rollback_id,
            confirmed=True,
        )
        if rollback_result.applied:
            gate.consume(pending.token)

        base = ToolDecisionReport(
            intent=Intent.WORKSPACE_MODIFY,
            confidence=report.confidence,
            tool_required=False,
            candidate_tools=report.candidate_tools,
            selected_tool=None,
            decision_reason="Restauration rollback workspace",
            risk_level=RiskLevel.MEDIUM,
            confirmation_required=False,
            fallback_action=FallbackAction.DIRECT_ANSWER,
            classification_reason=report.classification_reason,
            workspace_operation="rollback",
            explanation_mode="rollback",
            rollback_id=pending.rollback_id,
        )
        enriched = enrich_rollback_decision_context(
            base,
            rollback_result,
            confirmation_received=True,
            rollback_history_size=rollback_mgr.history_size(),
        )
        return {
            "message": message,
            "goal": "Restaurer modification workspace confirmée",
            "needs_memory": False,
            "needs_tool": False,
            "needs_clarification": not rollback_result.applied,
            "tool_requests": [],
            "decision_report": enriched,
            "fallback_action": enriched.fallback_action.value,
            "confirmation_required": False,
            "rollback_result": rollback_result,
            "rollback_text": format_rollback_summary(
                rollback_result,
                target_rollback_id=pending.rollback_id,
            ),
        }

    def _ambiguous_workspace_report(self, report, plan) -> object:
        """Return clarification report for ambiguous workspace requests (P11-005)."""
        from tools.decision.models import ToolDecisionReport
        from tools.tool_enums import RiskLevel

        summary = plan.ambiguity_reason or "Demande workspace ambiguë."
        return ToolDecisionReport(
            intent=report.intent,
            confidence=min(report.confidence, plan.confidence),
            tool_required=True,
            candidate_tools=report.candidate_tools,
            selected_tool=report.selected_tool or "file_read",
            decision_reason=summary,
            risk_level=RiskLevel.LOW,
            confirmation_required=False,
            fallback_action=FallbackAction.CLARIFICATION,
            classification_reason=report.classification_reason,
            selected_provider=report.selected_provider or "file_system",
            candidate_providers=report.candidate_providers,
            ranking_score=report.ranking_score,
            reasoning_summary=summary,
            execution_mode=report.execution_mode,
            workspace_operation=plan.workspace_operation,
            explanation_mode=plan.explanation_mode,
            files_considered=plan.files_considered,
            search_query=plan.search_query or None,
            search_results=plan.search_results,
            selected_file=plan.selected_file,
            ambiguity_status=plan.ambiguity_status or None,
        )

    def _ambiguous_file_report(
        self,
        report,
        file_params: FileOperationParams,
    ):
        """Return clarification report for ambiguous filesystem requests (P10B-1506)."""
        from tools.decision.models import ToolDecisionReport
        from tools.tool_enums import RiskLevel

        summary = (
            f"{file_params.ambiguity_reason} "
            "Précise le répertoire, le nom de fichier, l'extension ou le mot-clé."
        )
        return ToolDecisionReport(
            intent=report.intent,
            confidence=report.confidence,
            tool_required=True,
            candidate_tools=report.candidate_tools,
            selected_tool=report.selected_tool,
            decision_reason=summary,
            risk_level=RiskLevel.SAFE,
            confirmation_required=False,
            fallback_action=FallbackAction.CLARIFICATION,
            classification_reason=report.classification_reason,
            selected_provider=report.selected_provider,
            candidate_providers=report.candidate_providers,
            ranking_score=report.ranking_score,
            reasoning_summary=summary,
            file_operation=file_params.operation,
            directory=file_params.directory,
            filename=file_params.filename,
            extension=file_params.extension,
            keyword=file_params.keyword,
            recursive=file_params.recursive,
            execution_mode=report.execution_mode,
        )

    def _analyze_legacy(self, message: str) -> dict:
        """Phase 6 keyword path preserved for opt-out regression safety."""
        lowered = message.lower()
        tool_requests: list[ToolRequest] = []

        if _matches_any(lowered, _TIME_KEYWORDS):
            tool_requests.append(ToolRequest("time", {}))

        file_path = _extract_path(message)
        if file_path and _matches_any(lowered, _READ_KEYWORDS):
            tool_requests.append(ToolRequest("file_read", {"path": file_path}))

        if file_path and _matches_any(lowered, _WRITE_KEYWORDS):
            content = _extract_write_content(message)
            tool_requests.append(
                ToolRequest(
                    "file_write",
                    {"path": file_path, "content": content},
                ),
            )

        code = _extract_python_code(message)
        if code and _matches_any(lowered, _PYTHON_KEYWORDS):
            tool_requests.append(ToolRequest("python_exec", {"code": code}))

        if _matches_any(lowered, _WEB_KEYWORDS):
            query = message.strip()
            tool_requests.append(ToolRequest("web_search", {"query": query}))

        return {
            "message": message,
            "goal": "Comprendre la demande de l'utilisateur",
            "needs_memory": False,
            "needs_tool": bool(tool_requests),
            "needs_clarification": False,
            "tool_requests": tool_requests,
        }


def _build_tool_params(
    message: str,
    tool_name: str,
    file_params: FileOperationParams | None = None,
) -> dict:
    """Map selected tool name to invocation parameters from the message."""
    if tool_name == "time":
        return {}
    if tool_name == "web_search":
        return {"query": message.strip()}
    if tool_name == "calendar":
        return {"query": message.strip()}
    if tool_name == "email":
        return {"query": message.strip()}
    if tool_name == "trading":
        return {"query": message.strip()}
    if tool_name == "file_read":
        if file_params is not None:
            return params_to_tool_dict(file_params)
        path = _extract_path(message)
        return {"path": path or "", "action": "read_file"}
    if tool_name == "file_write":
        path = _extract_path(message)
        return {"path": path or "", "content": _extract_write_content(message)}
    if tool_name == "python_exec":
        code = _extract_python_code(message)
        return {"code": code or ""}
    if tool_name == "github":
        return {"action": _infer_github_operation(message)}
    return {}


def _infer_github_operation(message: str) -> str:
    """Infer GitHub provider action from natural-language phrasing."""
    lowered = message.lower()
    if "commit" in lowered:
        return "list_commits"
    if "pull request" in lowered or "pull requests" in lowered:
        return "list_pull_requests"
    if "issue" in lowered:
        return "list_issues"
    if "branch" in lowered or "branches" in lowered:
        return "list_branches"
    if "repository" in lowered or "repo" in lowered:
        return "get_repository"
    return "list_commits"


def _matches_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _extract_path(message: str) -> str | None:
    match = _PATH_PATTERN.search(message)
    return match.group(0) if match else None


def _extract_write_content(message: str) -> str:
    marker = "contenu:"
    lowered = message.lower()
    if marker in lowered:
        idx = lowered.index(marker)
        return message[idx + len(marker) :].strip()
    return ""


def _extract_python_code(message: str) -> str | None:
    block = _CODE_BLOCK_PATTERN.search(message)
    if block:
        return block.group(1).strip()
    if "python:" in message.lower():
        _, _, tail = message.partition(":")
        stripped = tail.strip()
        return stripped or None
    return None
