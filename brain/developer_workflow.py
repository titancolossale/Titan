# =====================================
# Titan Developer Workflow
# =====================================

"""Developer Workflow V1 — structured software-development planning for the Brain.

Analyzes development requests and produces a workspace-aware execution plan.
Never executes commands, never mutates missions, and never writes files.
Execution remains the responsibility of Tool Execution Engine after approval.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from tools.tool_enums import RiskLevel

if TYPE_CHECKING:
    from brain.code_intelligence import CodeIntelligence
    from brain.executive_function import ExecutiveEvaluation, ExecutiveFunction
    from brain.tool_intelligence import ToolExecutionPlan, ToolIntelligence
    from brain.workspace_awareness import WorkspaceAwareness, WorkspaceSnapshot
    from context.context_manager import ContextManager
    from core.mission_manager import MissionManager
    from memory.memory_service import MemoryService

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9àâäéèêëïîôùûüç_]{3,}", re.IGNORECASE)

_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "what",
        "when",
        "where",
        "which",
        "have",
        "need",
        "wants",
        "please",
        "titan",
        "dans",
        "pour",
        "avec",
        "quoi",
        "comment",
        "faire",
        "une",
        "des",
        "les",
        "mon",
        "mes",
        "sur",
        "est",
        "pas",
        "que",
        "qui",
    }
)

_RELEVANT_FILE_LIMIT = 20
_NEXT_STEP_LIMIT = 8
_COMMAND_LIMIT = 8
_TEST_LIMIT = 8
_DOC_LIMIT = 6
_TOOL_LIMIT = 8


class WorkflowIntent(str, Enum):
    """High-level development request classification."""

    CONTINUE_DEVELOPMENT = "continue_development"
    FIND_FIXES = "find_fixes"
    RUN_TESTS = "run_tests"
    PREPARE_SPRINT = "prepare_sprint"
    CHECK_CHANGES = "check_changes"
    SUMMARIZE_CODEBASE = "summarize_codebase"
    GENERAL_DEVELOPMENT = "general_development"


@dataclass(frozen=True)
class DeveloperWorkflowPlan:
    """Structured development plan — advisory only, no side effects."""

    goal: str
    context_summary: str
    relevant_files: tuple[str, ...]
    recommended_tools: tuple[str, ...]
    recommended_commands: tuple[str, ...]
    test_plan: tuple[str, ...]
    risk_level: RiskLevel
    next_steps: tuple[str, ...]
    requires_confirmation: bool
    intent: WorkflowIntent = WorkflowIntent.GENERAL_DEVELOPMENT
    documentation_updates: tuple[str, ...] = ()
    mission_context: str | None = None
    reasoning_summary: str = ""
    confidence: float = 0.0
    request: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "context_summary": self.context_summary,
            "relevant_files": list(self.relevant_files),
            "recommended_tools": list(self.recommended_tools),
            "recommended_commands": list(self.recommended_commands),
            "test_plan": list(self.test_plan),
            "risk_level": self.risk_level.value,
            "next_steps": list(self.next_steps),
            "requires_confirmation": self.requires_confirmation,
            "intent": self.intent.value,
            "documentation_updates": list(self.documentation_updates),
            "mission_context": self.mission_context,
            "reasoning_summary": self.reasoning_summary,
            "confidence": round(self.confidence, 3),
            "request": self.request,
        }

    def format_for_prompt(self) -> str:
        """Compact block for Brain prompt injection."""
        lines = [
            "DEVELOPER WORKFLOW PLAN",
            f"- goal: {self.goal}",
            f"- intent: {self.intent.value}",
            f"- risk: {self.risk_level.value}",
            f"- confirmation: {'required' if self.requires_confirmation else 'not required'}",
            f"- context: {self.context_summary}",
            f"- files: {', '.join(self.relevant_files[:10]) or 'none'}",
            f"- tools: {', '.join(self.recommended_tools) or 'none'}",
            f"- commands: {', '.join(self.recommended_commands[:5]) or 'none'}",
            f"- tests: {', '.join(self.test_plan[:5]) or 'none'}",
        ]
        if self.next_steps:
            lines.append("- next steps:")
            for step in self.next_steps[:5]:
                lines.append(f"  - {step}")
        return "\n".join(lines)


class DeveloperWorkflow:
    """Plan software-development workflows without executing anything."""

    def __init__(
        self,
        *,
        workspace_awareness: WorkspaceAwareness | None = None,
        executive_function: ExecutiveFunction | None = None,
        mission_manager: MissionManager | None = None,
        memory_service: MemoryService | None = None,
        context_manager: ContextManager | None = None,
        tool_intelligence: ToolIntelligence | None = None,
        code_intelligence: CodeIntelligence | None = None,
    ) -> None:
        self._workspace_awareness = workspace_awareness
        self._executive_function = executive_function
        self._mission_manager = mission_manager
        self._memory_service = memory_service
        self._context_manager = context_manager
        self._tool_intelligence = tool_intelligence
        self._code_intelligence = code_intelligence

    def plan(
        self,
        message: str,
        *,
        user: str | None = None,
        project_id: str | None = None,
        workspace: WorkspaceSnapshot | None = None,
        executive_evaluation: ExecutiveEvaluation | None = None,
    ) -> DeveloperWorkflowPlan:
        """Analyze a development request and return a structured plan.

        Never executes tools, commands, or mission mutations.
        """
        request = (message or "").strip()
        resolved_user = user or self._resolve_user()
        resolved_project = project_id or self._resolve_project_id()

        snapshot = self._resolve_workspace(
            workspace,
            user=resolved_user,
            project_id=resolved_project,
        )
        evaluation = self._resolve_executive(
            executive_evaluation,
            request,
            user=resolved_user,
            project_id=resolved_project,
            workspace=snapshot,
        )
        memory_hints = self._retrieve_memory(
            request,
            user=resolved_user,
            project_id=resolved_project,
        )
        tool_plan = self._plan_tools(request)

        intent = self._classify_intent(request)
        goal = self._build_goal(request, intent, evaluation)
        context_summary = self._build_context_summary(
            snapshot,
            evaluation,
            memory_hints,
        )
        relevant_files = self._identify_relevant_files(request, snapshot, evaluation)
        recommended_tools = self._recommend_tools(intent, tool_plan, request)
        recommended_commands = self._recommend_commands(
            intent,
            snapshot,
            relevant_files,
            request,
        )
        test_plan = self._recommend_tests(intent, snapshot, relevant_files, request)
        documentation_updates = self._recommend_documentation(
            intent,
            snapshot,
            relevant_files,
        )
        risk_level = self._classify_risk(intent, request, recommended_commands)
        requires_confirmation = self._requires_confirmation(
            risk_level,
            intent,
            recommended_commands,
        )
        next_steps = self._build_next_steps(
            intent,
            goal,
            relevant_files,
            recommended_commands,
            test_plan,
            documentation_updates,
            evaluation,
        )
        mission_context = self._mission_context(evaluation)
        confidence = self._plan_confidence(
            snapshot,
            relevant_files,
            recommended_tools,
            intent,
        )
        reasoning_summary = self._reasoning_summary(
            intent,
            risk_level,
            relevant_files,
            recommended_tools,
            requires_confirmation,
        )

        plan = DeveloperWorkflowPlan(
            goal=goal,
            context_summary=context_summary,
            relevant_files=relevant_files,
            recommended_tools=recommended_tools,
            recommended_commands=recommended_commands,
            test_plan=test_plan,
            risk_level=risk_level,
            next_steps=next_steps,
            requires_confirmation=requires_confirmation,
            intent=intent,
            documentation_updates=documentation_updates,
            mission_context=mission_context,
            reasoning_summary=reasoning_summary,
            confidence=confidence,
            request=request,
        )
        self._log_plan(plan)
        return plan

    # --- Resolution helpers -------------------------------------------------

    def _resolve_user(self) -> str:
        if self._context_manager is not None:
            return self._context_manager.current_user or "Nolan"
        return "Nolan"

    def _resolve_project_id(self) -> str | None:
        if self._context_manager is not None:
            active = (self._context_manager.active_project or "").strip()
            return active or None
        return None

    def _resolve_workspace(
        self,
        workspace: WorkspaceSnapshot | None,
        *,
        user: str,
        project_id: str | None,
    ) -> WorkspaceSnapshot | None:
        if workspace is not None:
            return workspace
        if self._workspace_awareness is None:
            return None
        return self._workspace_awareness.refresh(
            user=user,
            project_id=project_id,
        )

    def _resolve_executive(
        self,
        evaluation: ExecutiveEvaluation | None,
        message: str,
        *,
        user: str,
        project_id: str | None,
        workspace: WorkspaceSnapshot | None,
    ) -> ExecutiveEvaluation | None:
        if evaluation is not None:
            return evaluation
        if self._executive_function is None:
            return None
        return self._executive_function.evaluate_missions(
            message,
            user=user,
            project_id=project_id,
            workspace=workspace,
        )

    def _retrieve_memory(
        self,
        message: str,
        *,
        user: str,
        project_id: str | None,
    ) -> tuple[str, ...]:
        if self._memory_service is None or not message.strip():
            return ()
        try:
            result = self._memory_service.retrieve(
                user,
                message,
                project_id=project_id,
            )
        except Exception:
            logger.exception("DeveloperWorkflow memory retrieval failed")
            return ()
        if result is None or not result.has_matches:
            return ()
        return tuple(item for item in result.items[:5] if item)

    def _plan_tools(self, message: str) -> ToolExecutionPlan | None:
        if self._tool_intelligence is None or not message.strip():
            return None
        try:
            return self._tool_intelligence.plan(message)
        except Exception:
            logger.exception("DeveloperWorkflow tool intelligence planning failed")
            return None

    # --- Intent & goal ------------------------------------------------------

    def _classify_intent(self, message: str) -> WorkflowIntent:
        text = message.lower()
        if not text:
            return WorkflowIntent.GENERAL_DEVELOPMENT

        if any(
            phrase in text
            for phrase in (
                "check what changed",
                "what changed",
                "git status",
                "git diff",
                "voir les changements",
                "ce qui a changé",
                "ce qui a change",
            )
        ):
            return WorkflowIntent.CHECK_CHANGES

        if any(
            phrase in text
            for phrase in (
                "run the relevant tests",
                "run tests",
                "run the tests",
                "pytest",
                "lancer les tests",
                "exécuter les tests",
                "executer les tests",
            )
        ):
            return WorkflowIntent.RUN_TESTS

        if any(
            phrase in text
            for phrase in (
                "find what needs to be fixed",
                "what needs to be fixed",
                "needs fixing",
                "find bugs",
                "fix issues",
                "à corriger",
                "a corriger",
                "bugs",
                "broken",
            )
        ):
            return WorkflowIntent.FIND_FIXES

        if any(
            phrase in text
            for phrase in (
                "prepare the next implementation sprint",
                "prepare sprint",
                "next sprint",
                "implementation sprint",
                "prochain sprint",
                "préparer le sprint",
                "preparer le sprint",
            )
        ):
            return WorkflowIntent.PREPARE_SPRINT

        if any(
            phrase in text
            for phrase in (
                "summarize the current codebase",
                "summarize the codebase",
                "codebase state",
                "summarize codebase",
                "état du code",
                "etat du code",
                "résumer le code",
                "resumer le code",
            )
        ):
            return WorkflowIntent.SUMMARIZE_CODEBASE

        if any(
            phrase in text
            for phrase in (
                "continue titan development",
                "continue development",
                "continue working",
                "keep developing",
                "poursuivre",
                "continuer le développement",
                "continuer le developpement",
            )
        ):
            return WorkflowIntent.CONTINUE_DEVELOPMENT

        return WorkflowIntent.GENERAL_DEVELOPMENT

    def _build_goal(
        self,
        request: str,
        intent: WorkflowIntent,
        evaluation: ExecutiveEvaluation | None,
    ) -> str:
        if request:
            base = request.rstrip(".")
        else:
            base = {
                WorkflowIntent.CONTINUE_DEVELOPMENT: "Continue active development",
                WorkflowIntent.FIND_FIXES: "Identify issues that need fixing",
                WorkflowIntent.RUN_TESTS: "Run relevant tests",
                WorkflowIntent.PREPARE_SPRINT: "Prepare the next implementation sprint",
                WorkflowIntent.CHECK_CHANGES: "Review recent workspace changes",
                WorkflowIntent.SUMMARIZE_CODEBASE: "Summarize current codebase state",
                WorkflowIntent.GENERAL_DEVELOPMENT: "Assist with development workflow",
            }[intent]

        if evaluation is not None and evaluation.recommended_next_mission is not None:
            mission = evaluation.recommended_next_mission
            return f"{base} (mission focus: {mission.title})"
        return base

    # --- Context ------------------------------------------------------------

    def _build_context_summary(
        self,
        snapshot: WorkspaceSnapshot | None,
        evaluation: ExecutiveEvaluation | None,
        memory_hints: tuple[str, ...],
    ) -> str:
        parts: list[str] = []
        if snapshot is not None:
            if snapshot.summary:
                parts.append(snapshot.summary)
            else:
                parts.append(
                    f"Project {snapshot.current_project} "
                    f"({snapshot.project_language}); "
                    f"{len(snapshot.detected_modules)} modules; "
                    f"branch {snapshot.git_branch or 'n/a'}"
                )
        else:
            parts.append("No workspace snapshot available")

        if evaluation is not None:
            if evaluation.recommendation.recommended_title:
                parts.append(
                    f"Recommended mission: {evaluation.recommendation.recommended_title}"
                )
            elif evaluation.current_mission is not None:
                parts.append(f"Current focus: {evaluation.current_mission.title}")
            if evaluation.blocked_missions:
                parts.append(f"{len(evaluation.blocked_missions)} blocked mission(s)")

        if memory_hints:
            parts.append(f"Memory hints: {len(memory_hints)}")

        return "; ".join(parts)

    def _mission_context(self, evaluation: ExecutiveEvaluation | None) -> str | None:
        if evaluation is None:
            return None
        if evaluation.recommended_next_mission is not None:
            mission = evaluation.recommended_next_mission
            return (
                f"{mission.title} [{mission.state.value}] "
                f"progress={mission.progress_percent:.0f}%"
            )
        if evaluation.current_mission is not None:
            current = evaluation.current_mission
            return f"{current.title} [{current.state.value}]"
        if self._mission_manager is not None:
            active = self._mission_manager.runtime.list_active_missions()
            if active:
                first = active[0]
                return f"{first.title} [{first.state.value}]"
        return None

    # --- Relevant files -----------------------------------------------------

    def _identify_relevant_files(
        self,
        message: str,
        snapshot: WorkspaceSnapshot | None,
        evaluation: ExecutiveEvaluation | None,
    ) -> tuple[str, ...]:
        if snapshot is None:
            return ()

        scored: dict[str, float] = {}
        tokens = _tokenize(message)

        def _bump(path: str, score: float) -> None:
            if not path:
                return
            scored[path] = scored.get(path, 0.0) + score

        for path in snapshot.open_files:
            _bump(path, 3.0)
        for path in snapshot.recently_modified_files:
            _bump(path, 2.0)

        for path in snapshot.documentation_files:
            path_tokens = _tokenize(path.replace("/", " ").replace("\\", " ").replace(".", " "))
            overlap = len(tokens & path_tokens)
            if overlap:
                _bump(path, 1.0 + 0.5 * overlap)

        for module in snapshot.detected_modules:
            module_l = module.lower()
            if module_l in tokens or any(module_l in token for token in tokens):
                for path in snapshot.recently_modified_files:
                    if module_l in path.lower().replace("\\", "/"):
                        _bump(path, 2.5)
                for path in snapshot.documentation_files:
                    if module_l in path.lower().replace("\\", "/"):
                        _bump(path, 1.5)

        if evaluation is not None and self._workspace_awareness is not None:
            missions = []
            if evaluation.recommended_next_mission is not None:
                missions.append(evaluation.recommended_next_mission)
            for item in evaluation.ranked_missions[:3]:
                if item not in missions:
                    missions.append(item)
            for mission in missions:
                related = self._workspace_awareness.mission_related_files(
                    mission.title,
                    "",
                    snapshot=snapshot,
                )
                for path in related:
                    _bump(path, 2.0)

        # Explicit path-like tokens in the request
        for token in tokens:
            if "/" in token or "\\" in token or token.endswith(
                (".py", ".md", ".ts", ".js", ".json", ".toml")
            ):
                _bump(token, 4.0)

        # Code Intelligence: resolve symbol names mentioned in the request
        if self._code_intelligence is not None:
            for token in tokens:
                if len(token) < 3 or token in {
                    "the",
                    "and",
                    "for",
                    "what",
                    "does",
                    "explain",
                    "find",
                    "where",
                    "every",
                    "call",
                    "used",
                }:
                    continue
                # Prefer CamelCase / snake_case identifiers
                if not (
                    "_" in token
                    or (token[:1].isupper() and any(c.islower() for c in token[1:]))
                    or token.endswith("()")
                ):
                    continue
                try:
                    locations = self._code_intelligence.find_symbol(token.rstrip("()"))
                except Exception:
                    logger.exception("DeveloperWorkflow code symbol lookup failed")
                    continue
                for loc in locations[:5]:
                    if loc.file_path:
                        _bump(loc.file_path, 3.5)

        ranked = sorted(scored.items(), key=lambda item: (-item[1], item[0]))
        files = tuple(path for path, _ in ranked[:_RELEVANT_FILE_LIMIT])

        if not files and snapshot.recently_modified_files:
            return snapshot.recently_modified_files[: min(8, _RELEVANT_FILE_LIMIT)]
        if not files and snapshot.detected_modules:
            return tuple(f"{module}/" for module in snapshot.detected_modules[:8])
        return files

    # --- Tool / command / test recommendations ------------------------------

    def _recommend_tools(
        self,
        intent: WorkflowIntent,
        tool_plan: ToolExecutionPlan | None,
        request: str,
    ) -> tuple[str, ...]:
        tools: list[str] = []

        if tool_plan is not None and tool_plan.requires_tools:
            for tool_id in tool_plan.execution_order:
                if tool_id not in tools:
                    tools.append(tool_id)

        defaults: dict[WorkflowIntent, tuple[str, ...]] = {
            WorkflowIntent.CHECK_CHANGES: ("terminal", "github"),
            WorkflowIntent.RUN_TESTS: ("terminal", "python"),
            WorkflowIntent.FIND_FIXES: ("terminal", "python", "github"),
            WorkflowIntent.CONTINUE_DEVELOPMENT: ("terminal", "python", "github"),
            WorkflowIntent.PREPARE_SPRINT: ("terminal", "github", "obsidian"),
            WorkflowIntent.SUMMARIZE_CODEBASE: ("terminal", "github"),
            WorkflowIntent.GENERAL_DEVELOPMENT: ("terminal", "python"),
        }
        for tool_id in defaults.get(intent, ()):
            if tool_id not in tools:
                tools.append(tool_id)

        text = request.lower()
        if any(word in text for word in ("note", "obsidian", "vault", "doc")):
            if "obsidian" not in tools:
                tools.append("obsidian")
        if any(word in text for word in ("browser", "web", "url", "docs.python")):
            if "browser" not in tools:
                tools.append("browser")
        if any(word in text for word in ("pr", "pull request", "github", "commit", "branch")):
            if "github" not in tools:
                tools.append("github")

        return tuple(tools[:_TOOL_LIMIT])

    def _recommend_commands(
        self,
        intent: WorkflowIntent,
        snapshot: WorkspaceSnapshot | None,
        relevant_files: tuple[str, ...],
        request: str,
    ) -> tuple[str, ...]:
        commands: list[str] = []
        language = (snapshot.project_language if snapshot else "unknown") or "unknown"
        text = request.lower()

        if intent == WorkflowIntent.CHECK_CHANGES or any(
            word in text for word in ("git", "changed", "diff", "status", "branch")
        ):
            commands.extend(
                [
                    "git status",
                    "git diff --stat",
                    "git log -5 --oneline",
                ]
            )

        if intent == WorkflowIntent.RUN_TESTS or "test" in text:
            commands.append(self._pytest_command(relevant_files))

        if intent in (
            WorkflowIntent.CONTINUE_DEVELOPMENT,
            WorkflowIntent.FIND_FIXES,
            WorkflowIntent.PREPARE_SPRINT,
            WorkflowIntent.GENERAL_DEVELOPMENT,
        ):
            if "git status" not in commands:
                commands.append("git status")
            if language.lower().startswith("python"):
                test_cmd = self._pytest_command(relevant_files)
                if test_cmd not in commands:
                    commands.append(test_cmd)

        if intent == WorkflowIntent.SUMMARIZE_CODEBASE:
            if "git status" not in commands:
                commands.append("git status")
            commands.append("git log -10 --oneline")
            if language.lower().startswith("python"):
                commands.append("python -m pytest tests/ -q --collect-only")

        if intent == WorkflowIntent.FIND_FIXES and language.lower().startswith("python"):
            commands.append("python -m pytest tests/ -q")

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for command in commands:
            if command not in seen:
                seen.add(command)
                unique.append(command)
        return tuple(unique[:_COMMAND_LIMIT])

    def _pytest_command(self, relevant_files: tuple[str, ...]) -> str:
        test_targets: list[str] = []
        for path in relevant_files:
            normalized = path.replace("\\", "/")
            name = normalized.rsplit("/", 1)[-1]
            if normalized.startswith("tests/") or name.startswith("test_"):
                test_targets.append(normalized)
                continue
            if name.endswith(".py") and not name.startswith("__"):
                stem = name[:-3]
                candidate = f"tests/test_{stem}.py"
                if candidate not in test_targets:
                    test_targets.append(candidate)

        if test_targets:
            # Prefer existing-looking targets; still advisory
            joined = " ".join(test_targets[:4])
            return f"python -m pytest {joined} -v"
        return "python -m pytest tests/ -v"

    def _recommend_tests(
        self,
        intent: WorkflowIntent,
        snapshot: WorkspaceSnapshot | None,
        relevant_files: tuple[str, ...],
        request: str,
    ) -> tuple[str, ...]:
        tests: list[str] = []
        text = request.lower()

        for path in relevant_files:
            normalized = path.replace("\\", "/")
            name = normalized.rsplit("/", 1)[-1]
            if normalized.startswith("tests/") or name.startswith("test_"):
                if normalized not in tests:
                    tests.append(normalized)
                continue
            if name.endswith(".py") and not name.startswith("__"):
                stem = name[:-3]
                candidate = f"tests/test_{stem}.py"
                if candidate not in tests:
                    tests.append(candidate)

        if snapshot is not None:
            for module in snapshot.detected_modules[:6]:
                candidate = f"tests/test_{module}.py"
                if candidate not in tests and (
                    intent
                    in (
                        WorkflowIntent.RUN_TESTS,
                        WorkflowIntent.FIND_FIXES,
                        WorkflowIntent.CONTINUE_DEVELOPMENT,
                        WorkflowIntent.PREPARE_SPRINT,
                    )
                    or "test" in text
                ):
                    tests.append(candidate)

        if not tests:
            if intent == WorkflowIntent.RUN_TESTS or "test" in text:
                tests.append("tests/ -v (full suite)")
            elif intent in (
                WorkflowIntent.CONTINUE_DEVELOPMENT,
                WorkflowIntent.FIND_FIXES,
                WorkflowIntent.PREPARE_SPRINT,
            ):
                tests.append("tests/ related to changed modules")

        return tuple(tests[:_TEST_LIMIT])

    def _recommend_documentation(
        self,
        intent: WorkflowIntent,
        snapshot: WorkspaceSnapshot | None,
        relevant_files: tuple[str, ...],
    ) -> tuple[str, ...]:
        docs: list[str] = []

        if intent in (
            WorkflowIntent.PREPARE_SPRINT,
            WorkflowIntent.CONTINUE_DEVELOPMENT,
            WorkflowIntent.SUMMARIZE_CODEBASE,
            WorkflowIntent.GENERAL_DEVELOPMENT,
        ):
            docs.append("Update CHANGELOG.md with the planned or completed work")
            if snapshot is not None and snapshot.documentation_files:
                for path in snapshot.documentation_files[:3]:
                    if path not in docs:
                        docs.append(f"Review {path}")

        modules_touched = {
            part
            for path in relevant_files
            for part in path.replace("\\", "/").split("/")[:1]
            if part and part not in {"tests", "docs", "data", "logs"}
        }
        for module in sorted(modules_touched)[:3]:
            suggestion = f"Consider docs for module '{module}' if behavior changed"
            if suggestion not in docs:
                docs.append(suggestion)

        if intent == WorkflowIntent.PREPARE_SPRINT:
            docs.append("Draft sprint notes (Obsidian or docs/) before implementation")

        return tuple(docs[:_DOC_LIMIT])

    # --- Risk & confirmation ------------------------------------------------

    def _classify_risk(
        self,
        intent: WorkflowIntent,
        request: str,
        commands: tuple[str, ...],
    ) -> RiskLevel:
        text = request.lower()
        joined = " ".join(commands).lower()

        if any(
            phrase in text
            for phrase in (
                "force push",
                "git push --force",
                "rm -rf",
                "delete production",
                "drop database",
                "self-modif",
                "rewrite titan",
            )
        ):
            return RiskLevel.CRITICAL

        if any(
            phrase in text or phrase in joined
            for phrase in (
                "git push",
                "git reset --hard",
                "migrate",
                "deploy",
                "production",
            )
        ):
            return RiskLevel.HIGH

        if intent in (
            WorkflowIntent.CONTINUE_DEVELOPMENT,
            WorkflowIntent.FIND_FIXES,
            WorkflowIntent.PREPARE_SPRINT,
        ):
            return RiskLevel.MEDIUM

        if intent == WorkflowIntent.RUN_TESTS:
            return RiskLevel.LOW

        if intent in (
            WorkflowIntent.CHECK_CHANGES,
            WorkflowIntent.SUMMARIZE_CODEBASE,
        ):
            return RiskLevel.SAFE

        if any(cmd.startswith("git ") for cmd in commands) and not any(
            "push" in cmd for cmd in commands
        ):
            return RiskLevel.LOW

        return RiskLevel.LOW

    def _requires_confirmation(
        self,
        risk_level: RiskLevel,
        intent: WorkflowIntent,
        commands: tuple[str, ...],
    ) -> bool:
        if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return True
        if risk_level == RiskLevel.MEDIUM:
            return True
        if any("push" in cmd or "reset --hard" in cmd for cmd in commands):
            return True
        # Read-only / test intents do not require confirmation to *plan*;
        # execution still goes through Tool Execution Engine gates.
        if intent in (
            WorkflowIntent.CHECK_CHANGES,
            WorkflowIntent.SUMMARIZE_CODEBASE,
            WorkflowIntent.RUN_TESTS,
        ):
            return False
        return False

    # --- Next steps & confidence --------------------------------------------

    def _build_next_steps(
        self,
        intent: WorkflowIntent,
        goal: str,
        relevant_files: tuple[str, ...],
        commands: tuple[str, ...],
        test_plan: tuple[str, ...],
        documentation_updates: tuple[str, ...],
        evaluation: ExecutiveEvaluation | None,
    ) -> tuple[str, ...]:
        steps: list[str] = []

        if evaluation is not None and evaluation.recommendation.should_switch:
            title = evaluation.recommendation.recommended_title or "recommended mission"
            steps.append(f"Confirm mission focus switch to '{title}'")

        if intent == WorkflowIntent.CHECK_CHANGES:
            steps.append("Inspect git status and diff before editing")
            steps.append("Summarize changed files for the user")
        elif intent == WorkflowIntent.RUN_TESTS:
            steps.append("Confirm test targets with the user if ambiguous")
            steps.append("Run recommended tests via Tool Execution Engine after approval")
        elif intent == WorkflowIntent.FIND_FIXES:
            steps.append("Review recent failures and related modules")
            steps.append("Propose minimal fixes — do not apply automatically")
        elif intent == WorkflowIntent.PREPARE_SPRINT:
            steps.append("List unfinished missions and blocked work")
            steps.append("Define sprint goals and acceptance criteria")
            steps.append("Identify files and tests for the first sprint task")
        elif intent == WorkflowIntent.SUMMARIZE_CODEBASE:
            steps.append("Summarize modules, recent changes, and active missions")
            steps.append("Highlight documentation gaps and risks")
        elif intent == WorkflowIntent.CONTINUE_DEVELOPMENT:
            steps.append("Align on the active mission step")
            steps.append("Inspect relevant files before proposing edits")
        else:
            steps.append(f"Clarify scope for: {goal}")

        if relevant_files:
            preview = ", ".join(relevant_files[:3])
            steps.append(f"Inspect relevant files: {preview}")

        if commands:
            steps.append(
                "Request approval before running: "
                + ", ".join(commands[:2])
            )

        if test_plan:
            steps.append(f"Execute test plan after approval: {test_plan[0]}")

        if documentation_updates:
            steps.append(documentation_updates[0])

        steps.append("Do not execute tools until Tool Execution Engine approval")
        return tuple(steps[:_NEXT_STEP_LIMIT])

    def _plan_confidence(
        self,
        snapshot: WorkspaceSnapshot | None,
        relevant_files: tuple[str, ...],
        recommended_tools: tuple[str, ...],
        intent: WorkflowIntent,
    ) -> float:
        score = 0.45
        if snapshot is not None:
            score += 0.2
            if snapshot.detected_modules:
                score += 0.05
            if snapshot.git_branch:
                score += 0.05
        if relevant_files:
            score += 0.15
        if recommended_tools:
            score += 0.1
        if intent != WorkflowIntent.GENERAL_DEVELOPMENT:
            score += 0.05
        return round(min(score, 0.95), 3)

    def _reasoning_summary(
        self,
        intent: WorkflowIntent,
        risk_level: RiskLevel,
        relevant_files: tuple[str, ...],
        recommended_tools: tuple[str, ...],
        requires_confirmation: bool,
    ) -> str:
        return (
            f"intent={intent.value}; risk={risk_level.value}; "
            f"files={len(relevant_files)}; tools={','.join(recommended_tools) or 'none'}; "
            f"confirmation={'yes' if requires_confirmation else 'no'}"
        )

    def _log_plan(self, plan: DeveloperWorkflowPlan) -> None:
        logger.info(
            "DeveloperWorkflow plan: intent=%s risk=%s confirmation=%s files=%d tools=%s",
            plan.intent.value,
            plan.risk_level.value,
            plan.requires_confirmation,
            len(plan.relevant_files),
            ",".join(plan.recommended_tools) or "none",
        )
        logger.debug("DeveloperWorkflow goal: %s", plan.goal)
        logger.debug("DeveloperWorkflow reasoning: %s", plan.reasoning_summary)


def _tokenize(text: str) -> frozenset[str]:
    tokens = {
        match.group(0).lower()
        for match in _TOKEN_RE.finditer(text or "")
    }
    return frozenset(token for token in tokens if token not in _STOPWORDS)
