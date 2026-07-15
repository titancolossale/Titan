# =====================================
# Titan Code Modification Planner
# =====================================

"""Code Modification Planner V1 — prepare implementation plans before coding.

Produces structured CodeModificationPlan artifacts describing what must change,
where, dependencies, risk, order, and tests. Never generates patches, never
writes files, and never executes tools.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from brain.code_intelligence import CodeIntelligence
    from brain.developer_workflow import DeveloperWorkflow
    from brain.executive_function import ExecutiveEvaluation, ExecutiveFunction
    from brain.project_intelligence import ProjectIntelligence
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
        "add",
        "new",
        "please",
        "titan",
        "dans",
        "pour",
        "avec",
        "une",
        "des",
        "les",
        "implement",
        "generate",
        "create",
        "make",
        "build",
    }
)


class ChangeType(str, Enum):
    """High-level code-change classification."""

    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    RENAME = "rename"
    REPLACE = "replace"
    UNKNOWN = "unknown"


class ComplexityLevel(str, Enum):
    """Estimated implementation complexity."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskLevel(str, Enum):
    """Architectural / blast-radius risk."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class AffectedModule:
    """A package or layer touched by the requested change."""

    name: str
    path: str
    role: str
    change_nature: str = "modify"
    dependency_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "role": self.role,
            "change_nature": self.change_nature,
            "dependency_notes": self.dependency_notes,
        }


@dataclass(frozen=True)
class AffectedFile:
    """A concrete file (and optional symbols) in scope."""

    path: str
    reason: str
    classes: tuple[str, ...] = ()
    functions: tuple[str, ...] = ()
    priority: str = "primary"
    action: str = "modify"

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "reason": self.reason,
            "classes": list(self.classes),
            "functions": list(self.functions),
            "priority": self.priority,
            "action": self.action,
        }


@dataclass(frozen=True)
class ImplementationStep:
    """Ordered implementation checklist item."""

    order: int
    title: str
    description: str
    target_files: tuple[str, ...] = ()
    depends_on: tuple[int, ...] = ()
    risk_level: RiskLevel = RiskLevel.MEDIUM
    done_when: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "title": self.title,
            "description": self.description,
            "target_files": list(self.target_files),
            "depends_on": list(self.depends_on),
            "risk_level": self.risk_level.value,
            "done_when": self.done_when,
        }


@dataclass(frozen=True)
class RiskAssessment:
    """Structured risk view for a planned change."""

    overall: RiskLevel
    architectural: str = ""
    data_migration: str = ""
    api_breakage: str = ""
    user_impact: str = ""
    mitigations: tuple[str, ...] = ()
    forbidden_shortcuts: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall.value,
            "architectural": self.architectural,
            "data_migration": self.data_migration,
            "api_breakage": self.api_breakage,
            "user_impact": self.user_impact,
            "mitigations": list(self.mitigations),
            "forbidden_shortcuts": list(self.forbidden_shortcuts),
        }


@dataclass(frozen=True)
class TestingPlan:
    """Recommended verification for the planned change."""

    __test__ = False

    unit_tests: tuple[str, ...] = ()
    integration_tests: tuple[str, ...] = ()
    regression_focus: tuple[str, ...] = ()
    manual_checks: tuple[str, ...] = ()
    fixtures_needed: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_tests": list(self.unit_tests),
            "integration_tests": list(self.integration_tests),
            "regression_focus": list(self.regression_focus),
            "manual_checks": list(self.manual_checks),
            "fixtures_needed": list(self.fixtures_needed),
        }


@dataclass(frozen=True)
class CodeModificationPlan:
    """Complete advisory plan for a requested code change — no patches."""

    request: str
    change_type: ChangeType
    summary: str
    affected_modules: tuple[AffectedModule, ...]
    affected_files: tuple[AffectedFile, ...]
    implementation_steps: tuple[ImplementationStep, ...]
    risk: RiskAssessment
    testing: TestingPlan
    complexity: ComplexityLevel
    estimated_impact: str
    checklist: tuple[str, ...]
    confidence: float = 0.0
    clarifications: tuple[str, ...] = ()
    sources: dict[str, Any] = field(default_factory=dict)
    approved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "change_type": self.change_type.value,
            "summary": self.summary,
            "affected_modules": [m.to_dict() for m in self.affected_modules],
            "affected_files": [f.to_dict() for f in self.affected_files],
            "implementation_steps": [s.to_dict() for s in self.implementation_steps],
            "risk": self.risk.to_dict(),
            "testing": self.testing.to_dict(),
            "complexity": self.complexity.value,
            "estimated_impact": self.estimated_impact,
            "checklist": list(self.checklist),
            "confidence": round(self.confidence, 3),
            "clarifications": list(self.clarifications),
            "sources": dict(self.sources),
            "approved": self.approved,
        }

    def with_approval(self, approved: bool = True) -> CodeModificationPlan:
        """Return a copy marked approved for code generation."""
        return CodeModificationPlan(
            request=self.request,
            change_type=self.change_type,
            summary=self.summary,
            affected_modules=self.affected_modules,
            affected_files=self.affected_files,
            implementation_steps=self.implementation_steps,
            risk=self.risk,
            testing=self.testing,
            complexity=self.complexity,
            estimated_impact=self.estimated_impact,
            checklist=self.checklist,
            confidence=self.confidence,
            clarifications=self.clarifications,
            sources=dict(self.sources),
            approved=approved,
        )


class CodeModificationPlanner:
    """Plan code modifications without generating or applying patches."""

    def __init__(
        self,
        *,
        workspace_awareness: WorkspaceAwareness | None = None,
        project_intelligence: ProjectIntelligence | None = None,
        code_intelligence: CodeIntelligence | None = None,
        developer_workflow: DeveloperWorkflow | None = None,
        executive_function: ExecutiveFunction | None = None,
        mission_manager: MissionManager | None = None,
        memory_service: MemoryService | None = None,
        context_manager: ContextManager | None = None,
    ) -> None:
        self._workspace_awareness = workspace_awareness
        self._project_intelligence = project_intelligence
        self._code_intelligence = code_intelligence
        self._developer_workflow = developer_workflow
        self._executive_function = executive_function
        self._mission_manager = mission_manager
        self._memory_service = memory_service
        self._context_manager = context_manager

    def plan(
        self,
        request: str,
        *,
        user: str | None = None,
        project_id: str | None = None,
        workspace: WorkspaceSnapshot | None = None,
        executive_evaluation: ExecutiveEvaluation | None = None,
        approved: bool = False,
    ) -> CodeModificationPlan:
        """Build a CodeModificationPlan for a feature or bug-fix request."""
        text = (request or "").strip()
        resolved_user = user or self._resolve_user()
        resolved_project = project_id or self._resolve_project_id()
        snapshot = self._resolve_workspace(
            workspace,
            user=resolved_user,
            project_id=resolved_project,
        )
        evaluation = self._resolve_executive(
            executive_evaluation,
            text,
            user=resolved_user,
            project_id=resolved_project,
        )

        change_type = self._classify_change_type(text)
        tokens = self._tokens(text)
        entity = self._infer_entity(text, tokens)

        modules, files = self._identify_scope(change_type, text, entity, tokens, snapshot)
        steps = self._build_steps(change_type, entity, files)
        risk = self._assess_risk(change_type, text, files)
        complexity = self._estimate_complexity(change_type, files, risk)
        testing = self._recommend_tests(change_type, entity, files)
        checklist = self._build_checklist(steps, testing)
        confidence = self._estimate_confidence(change_type, files, entity)
        clarifications = self._clarifications(change_type, entity, files)
        summary = self._summarize(change_type, entity, files, risk)
        impact = self._estimate_impact(change_type, files, risk)

        sources: dict[str, Any] = {
            "workspace": snapshot.current_project if snapshot is not None else None,
            "executive_focus": (
                evaluation.recommendation.recommended_mission_id
                if evaluation is not None
                else None
            ),
            "project_intelligence": self._project_intelligence is not None,
            "code_intelligence": self._code_intelligence is not None,
            "developer_workflow": self._developer_workflow is not None,
            "memory": self._memory_service is not None,
            "mission_runtime": self._mission_manager is not None,
        }

        plan = CodeModificationPlan(
            request=text,
            change_type=change_type,
            summary=summary,
            affected_modules=tuple(modules),
            affected_files=tuple(files),
            implementation_steps=tuple(steps),
            risk=risk,
            testing=testing,
            complexity=complexity,
            estimated_impact=impact,
            checklist=tuple(checklist),
            confidence=confidence,
            clarifications=tuple(clarifications),
            sources=sources,
            approved=approved,
        )
        logger.info(
            "code_modification_plan change_type=%s complexity=%s risk=%s "
            "files=%d confidence=%.2f",
            change_type.value,
            complexity.value,
            risk.overall.value,
            len(files),
            confidence,
        )
        return plan

    # --- classification / scope -------------------------------------------------

    def _classify_change_type(self, text: str) -> ChangeType:
        lower = text.lower()
        if any(k in lower for k in ("rename", "renommer")):
            return ChangeType.RENAME
        if any(k in lower for k in ("replace", "remplacer", "swap backend", "migrate")):
            return ChangeType.REPLACE
        if any(
            k in lower
            for k in ("refactor", "restructure", "improve", "cleanup", "améliorer")
        ):
            return ChangeType.REFACTOR
        if any(
            k in lower
            for k in ("fix", "bug", "broken", "error", "corriger", "réparer")
        ):
            return ChangeType.BUGFIX
        if any(
            k in lower
            for k in (
                "add",
                "implement",
                "create",
                "integrate",
                "connector",
                "integration",
                "ajouter",
                "implémenter",
            )
        ):
            return ChangeType.FEATURE
        return ChangeType.UNKNOWN

    def _infer_entity(self, text: str, tokens: list[str]) -> str:
        lower = text.lower()
        known = (
            ("discord", "discord"),
            ("tradingview", "tradingview"),
            ("trading view", "tradingview"),
            ("browser", "browser"),
            ("toolmanager", "tool_manager"),
            ("tool manager", "tool_manager"),
            ("memory", "memory"),
            ("obsidian", "obsidian"),
            ("calendar", "calendar"),
            ("email", "email"),
            ("github", "github"),
        )
        for needle, entity in known:
            if needle in lower:
                return entity
        for token in tokens:
            if token not in _STOPWORDS and len(token) > 3:
                return token.lower().replace("-", "_")
        return "component"

    def _identify_scope(
        self,
        change_type: ChangeType,
        text: str,
        entity: str,
        tokens: list[str],
        snapshot: WorkspaceSnapshot | None,
    ) -> tuple[list[AffectedModule], list[AffectedFile]]:
        lower = text.lower()
        modules: list[AffectedModule] = []
        files: list[AffectedFile] = []

        if entity == "discord" or "discord" in lower:
            modules = [
                AffectedModule(
                    name="tools",
                    path="tools/",
                    role="External Discord connector and tool registration",
                    change_nature="add",
                    dependency_notes="PermissionManager + ToolManager wiring",
                ),
                AffectedModule(
                    name="config",
                    path="config/",
                    role="Non-secret defaults and feature flags",
                    change_nature="extend",
                ),
                AffectedModule(
                    name="tests",
                    path="tests/",
                    role="Unit coverage for new connector",
                    change_nature="add",
                ),
            ]
            files = [
                AffectedFile(
                    path="tools/discord_tool.py",
                    reason="New Discord tool capability",
                    classes=("DiscordTool",),
                    priority="primary",
                    action="create",
                ),
                AffectedFile(
                    path="tools/tool_manager.py",
                    reason="Register DiscordTool in defaults",
                    classes=("ToolManager",),
                    functions=("_register_defaults",),
                    priority="primary",
                    action="modify",
                ),
                AffectedFile(
                    path="tests/test_discord_tool.py",
                    reason="Smoke and permission tests",
                    priority="test",
                    action="create",
                ),
                AffectedFile(
                    path=".env.example",
                    reason="Document Discord secrets without committing them",
                    priority="docs",
                    action="modify",
                ),
            ]
        elif entity == "tradingview" or "tradingview" in lower:
            modules = [
                AffectedModule(
                    name="tools.connectors",
                    path="tools/connectors/",
                    role="TradingView webhook / provider surface",
                    change_nature="extend",
                ),
                AffectedModule(
                    name="tools",
                    path="tools/",
                    role="Trading tool facade and permissions",
                    change_nature="modify",
                ),
                AffectedModule(
                    name="tests",
                    path="tests/",
                    role="Provider and brain-flow coverage",
                    change_nature="add",
                ),
            ]
            files = [
                AffectedFile(
                    path="tools/connectors/tradingview_provider.py",
                    reason="TradingView connector / provider improvements",
                    classes=("TradingViewProvider",),
                    priority="primary",
                    action="modify",
                ),
                AffectedFile(
                    path="tools/connectors/tradingview_models.py",
                    reason="Signal / alert models",
                    classes=("TradingSignal",),
                    priority="secondary",
                    action="modify",
                ),
                AffectedFile(
                    path="tests/test_tradingview_provider.py",
                    reason="Regression for connector behavior",
                    priority="test",
                    action="modify",
                ),
            ]
        elif entity == "browser" or "browser" in lower:
            modules = [
                AffectedModule(
                    name="core.tools.browser",
                    path="core/tools/browser/",
                    role="Browser tool implementation",
                    change_nature="modify",
                ),
                AffectedModule(
                    name="tests",
                    path="tests/",
                    role="Browser tool regression",
                    change_nature="modify",
                ),
            ]
            files = [
                AffectedFile(
                    path="core/tools/browser/browser_tool.py",
                    reason="Primary Browser Tool surface",
                    classes=("BrowserTool",),
                    priority="primary",
                    action="modify",
                ),
                AffectedFile(
                    path="core/tools/browser/browser_client.py",
                    reason="HTTP client behavior",
                    classes=("BrowserClient",),
                    priority="secondary",
                    action="modify",
                ),
                AffectedFile(
                    path="tests/test_core_browser_tool.py",
                    reason="Preserve Browser Tool contracts",
                    priority="test",
                    action="modify",
                ),
            ]
        elif entity == "tool_manager" or "toolmanager" in lower.replace(" ", ""):
            modules = [
                AffectedModule(
                    name="tools",
                    path="tools/",
                    role="ToolManager facade and importers",
                    change_nature="rename" if change_type == ChangeType.RENAME else "modify",
                ),
                AffectedModule(
                    name="brain",
                    path="brain/",
                    role="Brain composition uses ToolManager",
                    change_nature="modify",
                ),
                AffectedModule(
                    name="tests",
                    path="tests/",
                    role="Update imports and assertions",
                    change_nature="modify",
                ),
            ]
            files = [
                AffectedFile(
                    path="tools/tool_manager.py",
                    reason="Primary ToolManager definition",
                    classes=("ToolManager",),
                    priority="primary",
                    action="modify",
                ),
                AffectedFile(
                    path="brain/brain.py",
                    reason="Constructor injection of ToolManager",
                    classes=("Brain",),
                    functions=("__init__",),
                    priority="secondary",
                    action="modify",
                ),
                AffectedFile(
                    path="tests/test_tool_framework.py",
                    reason="Framework tests reference ToolManager",
                    priority="test",
                    action="modify",
                ),
            ]
        elif entity == "memory" and change_type in {ChangeType.REPLACE, ChangeType.REFACTOR}:
            modules = [
                AffectedModule(
                    name="memory",
                    path="memory/",
                    role="Memory persistence backend",
                    change_nature="replace",
                    dependency_notes="User isolation Nolan/Ibrahim must hold",
                ),
                AffectedModule(
                    name="brain",
                    path="brain/",
                    role="Memory read/write via MemoryService",
                    change_nature="modify",
                ),
            ]
            files = [
                AffectedFile(
                    path="memory/long_term_memory.py",
                    reason="Long-term backend boundary",
                    classes=("LongTermMemory",),
                    priority="primary",
                    action="modify",
                ),
                AffectedFile(
                    path="memory/memory_service.py",
                    reason="Facade over short/long-term stores",
                    classes=("MemoryService",),
                    priority="primary",
                    action="modify",
                ),
                AffectedFile(
                    path="tests/test_memory_service.py",
                    reason="Isolation and persistence regressions",
                    priority="test",
                    action="modify",
                ),
            ]
        else:
            modules = [
                AffectedModule(
                    name="tools",
                    path="tools/",
                    role="Likely extension point for new capabilities",
                    change_nature="extend",
                ),
                AffectedModule(
                    name="tests",
                    path="tests/",
                    role="Required tests for new modules",
                    change_nature="add",
                ),
            ]
            tool_path = f"tools/{entity}_tool.py"
            files = [
                AffectedFile(
                    path=tool_path,
                    reason=f"Proposed home for {entity} capability",
                    classes=(self._class_name(entity, "Tool"),),
                    priority="primary",
                    action="create",
                ),
                AffectedFile(
                    path="tools/tool_manager.py",
                    reason="Register new tool",
                    classes=("ToolManager",),
                    priority="primary",
                    action="modify",
                ),
                AffectedFile(
                    path=f"tests/test_{entity}_tool.py",
                    reason="Unit coverage",
                    priority="test",
                    action="create",
                ),
            ]

        # Enrich with code intelligence symbols when available.
        if self._code_intelligence is not None:
            files = self._enrich_files_with_symbols(files)

        # Prefer existing workspace paths when snapshot lists them.
        if snapshot is not None:
            files = self._prefer_existing_paths(files, snapshot)

        return modules, files

    def _enrich_files_with_symbols(
        self,
        files: list[AffectedFile],
    ) -> list[AffectedFile]:
        enriched: list[AffectedFile] = []
        assert self._code_intelligence is not None
        for item in files:
            classes = list(item.classes)
            functions = list(item.functions)
            for name in list(classes):
                try:
                    locs = self._code_intelligence.find_symbol(name)
                except Exception:  # noqa: BLE001 — advisory enrichment only
                    locs = ()
                if locs and not item.classes:
                    classes.append(name)
            enriched.append(
                AffectedFile(
                    path=item.path,
                    reason=item.reason,
                    classes=tuple(dict.fromkeys(classes)),
                    functions=tuple(dict.fromkeys(functions)),
                    priority=item.priority,
                    action=item.action,
                )
            )
        return enriched

    def _prefer_existing_paths(
        self,
        files: list[AffectedFile],
        snapshot: WorkspaceSnapshot,
    ) -> list[AffectedFile]:
        known = {
            p.replace("\\", "/")
            for p in getattr(snapshot, "recently_modified_files", ()) or ()
        }
        modules = {
            p.replace("\\", "/")
            for p in getattr(snapshot, "detected_modules", ()) or ()
        }
        known |= modules
        # Keep planned paths; existence is advisory for create vs modify.
        result: list[AffectedFile] = []
        for item in files:
            normalized = item.path.replace("\\", "/")
            action = item.action
            if action == "modify" and known and normalized not in known:
                # Still keep as modify — generation will treat missing as create.
                pass
            result.append(item)
        return result

    def _build_steps(
        self,
        change_type: ChangeType,
        entity: str,
        files: list[AffectedFile],
    ) -> list[ImplementationStep]:
        creates = [f for f in files if f.action == "create"]
        modifies = [f for f in files if f.action == "modify"]
        tests = [f for f in files if f.priority == "test"]
        steps: list[ImplementationStep] = []
        order = 1

        if change_type == ChangeType.RENAME:
            steps.append(
                ImplementationStep(
                    order=order,
                    title="Inventory references",
                    description=f"Locate all imports and string references for {entity}.",
                    target_files=tuple(f.path for f in modifies),
                    risk_level=RiskLevel.MEDIUM,
                    done_when="Reference list complete",
                )
            )
            order += 1
            steps.append(
                ImplementationStep(
                    order=order,
                    title="Rename primary definition",
                    description="Rename class/module at the source of truth.",
                    target_files=tuple(f.path for f in modifies[:1]),
                    depends_on=(1,),
                    risk_level=RiskLevel.HIGH,
                    done_when="Primary symbol renamed",
                )
            )
            order += 1
            steps.append(
                ImplementationStep(
                    order=order,
                    title="Update callers",
                    description="Update imports and Brain/composition wiring.",
                    target_files=tuple(f.path for f in modifies[1:]),
                    depends_on=(2,),
                    risk_level=RiskLevel.HIGH,
                    done_when="Import graph clean",
                )
            )
            order += 1
        else:
            if creates:
                steps.append(
                    ImplementationStep(
                        order=order,
                        title="Add new modules",
                        description="Create new files with Titan banners and type hints.",
                        target_files=tuple(f.path for f in creates if f.priority != "test"),
                        risk_level=RiskLevel.MEDIUM,
                        done_when="New modules compile/import in isolation",
                    )
                )
                order += 1
            if modifies:
                steps.append(
                    ImplementationStep(
                        order=order,
                        title="Wire existing modules",
                        description="Update registries, facades, and Brain injection points.",
                        target_files=tuple(f.path for f in modifies if f.priority != "test"),
                        depends_on=(order - 1,) if creates else (),
                        risk_level=RiskLevel.MEDIUM,
                        done_when="Registration and imports updated",
                    )
                )
                order += 1

        steps.append(
            ImplementationStep(
                order=order,
                title="Add or update tests",
                description="Cover happy path, permissions, and regressions.",
                target_files=tuple(f.path for f in tests) or tuple(
                    f.path for f in files if f.priority == "test"
                ),
                depends_on=tuple(range(1, order)),
                risk_level=RiskLevel.LOW,
                done_when="Targeted pytest suite green",
            )
        )
        order += 1
        steps.append(
            ImplementationStep(
                order=order,
                title="Document and verify",
                description="Update docs/.env.example as needed; smoke python main.py.",
                target_files=tuple(
                    f.path for f in files if f.priority == "docs"
                ),
                depends_on=(order - 1,),
                risk_level=RiskLevel.LOW,
                done_when="Docs match behavior; REPL starts",
            )
        )
        return steps

    def _assess_risk(
        self,
        change_type: ChangeType,
        text: str,
        files: list[AffectedFile],
    ) -> RiskAssessment:
        lower = text.lower()
        overall = RiskLevel.MEDIUM
        architectural = "Touches modular boundaries; keep Brain as conductor."
        data_migration = "None expected."
        api_breakage = "Public API impact depends on facade stability."
        user_impact = "User-facing behavior may change after approval and apply."
        mitigations = [
            "Generate patches only; apply via separate confirmed path.",
            "Add regression tests before applying high-risk edits.",
        ]
        forbidden = [
            "Never commit secrets.",
            "Never bypass PermissionManager for external connectors.",
            "Never mix Nolan/Ibrahim memory.",
        ]

        if change_type == ChangeType.REPLACE or "memory" in lower:
            overall = RiskLevel.HIGH
            data_migration = "Persistence schema / dual-read cutover required."
            mitigations.append("Dual-read then cutover; backup data/*.json first.")
        if "trading" in lower:
            overall = RiskLevel.HIGH
            mitigations.append("Paper/default; no live order execution in V1 proposals.")
            forbidden.append("Do not enable live trading without explicit risk controls.")
        if change_type == ChangeType.RENAME:
            overall = RiskLevel.HIGH
            api_breakage = "Wide import blast radius; update all callers."
        if any(f.path.startswith("brain/") for f in files):
            if overall == RiskLevel.MEDIUM:
                overall = RiskLevel.HIGH
            architectural = "Brain composition or pipeline touched — preserve think() contract."
        if change_type == ChangeType.BUGFIX and overall == RiskLevel.MEDIUM:
            overall = RiskLevel.LOW
            mitigations.append("Reproduce failing case as a regression test first.")

        return RiskAssessment(
            overall=overall,
            architectural=architectural,
            data_migration=data_migration,
            api_breakage=api_breakage,
            user_impact=user_impact,
            mitigations=tuple(mitigations),
            forbidden_shortcuts=tuple(forbidden),
        )

    def _estimate_complexity(
        self,
        change_type: ChangeType,
        files: list[AffectedFile],
        risk: RiskAssessment,
    ) -> ComplexityLevel:
        score = len(files)
        if change_type in {ChangeType.REPLACE, ChangeType.RENAME}:
            score += 2
        if risk.overall in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            score += 2
        if score <= 3:
            return ComplexityLevel.LOW
        if score <= 5:
            return ComplexityLevel.MEDIUM
        if score <= 8:
            return ComplexityLevel.HIGH
        return ComplexityLevel.CRITICAL

    def _recommend_tests(
        self,
        change_type: ChangeType,
        entity: str,
        files: list[AffectedFile],
    ) -> TestingPlan:
        unit = [f"tests/test_{entity}_tool.py — import and happy-path stubs"]
        if change_type == ChangeType.BUGFIX:
            unit = [f"Regression test reproducing the {entity} failure"]
        integration = [
            "Brain API smoke: plan_code_change → generate_code (no writes)",
        ]
        if any("tool_manager" in f.path for f in files):
            integration.append("ToolManager registration / list_tools smoke")
        regression = [
            "python main.py starts without import errors",
            "User memory isolation (Nolan ≠ Ibrahim) if memory touched",
        ]
        manual = [
            "Review unified diffs before any apply step",
            "Confirm no secrets in proposed content",
        ]
        fixtures = ["tmp_path project root", "mocked LLM if Brain integration"]
        return TestingPlan(
            unit_tests=tuple(unit),
            integration_tests=tuple(integration),
            regression_focus=tuple(regression),
            manual_checks=tuple(manual),
            fixtures_needed=tuple(fixtures),
        )

    def _build_checklist(
        self,
        steps: list[ImplementationStep],
        testing: TestingPlan,
    ) -> list[str]:
        items = [f"{step.order}. {step.title}: {step.description}" for step in steps]
        items.extend(f"Test: {t}" for t in testing.unit_tests[:3])
        items.append("Manual review of every generated patch before apply")
        return items

    def _estimate_confidence(
        self,
        change_type: ChangeType,
        files: list[AffectedFile],
        entity: str,
    ) -> float:
        confidence = 0.55
        if change_type != ChangeType.UNKNOWN:
            confidence += 0.15
        if entity != "component":
            confidence += 0.1
        if files:
            confidence += 0.1
        if self._workspace_awareness is not None:
            confidence += 0.05
        return min(confidence, 0.95)

    def _clarifications(
        self,
        change_type: ChangeType,
        entity: str,
        files: list[AffectedFile],
    ) -> list[str]:
        notes: list[str] = []
        if change_type == ChangeType.UNKNOWN:
            notes.append("Clarify whether this is a feature, bugfix, refactor, or rename.")
        if entity == "component":
            notes.append("Name the target component or module more specifically.")
        if not files:
            notes.append("Could not locate affected files — provide a path hint.")
        return notes

    def _summarize(
        self,
        change_type: ChangeType,
        entity: str,
        files: list[AffectedFile],
        risk: RiskAssessment,
    ) -> str:
        return (
            f"{change_type.value.title()} plan for '{entity}': "
            f"{len(files)} file(s) in scope, overall risk {risk.overall.value}. "
            "Advisory only — no code generated or applied."
        )

    def _estimate_impact(
        self,
        change_type: ChangeType,
        files: list[AffectedFile],
        risk: RiskAssessment,
    ) -> str:
        creates = sum(1 for f in files if f.action == "create")
        modifies = sum(1 for f in files if f.action == "modify")
        return (
            f"{change_type.value}: create={creates}, modify={modifies}, "
            f"risk={risk.overall.value}"
        )

    # --- helpers ----------------------------------------------------------------

    @staticmethod
    def _class_name(entity: str, suffix: str) -> str:
        parts = [p for p in entity.replace("-", "_").split("_") if p]
        return "".join(p.capitalize() for p in parts) + suffix

    def _tokens(self, text: str) -> list[str]:
        return [
            m.group(0).lower()
            for m in _TOKEN_RE.finditer(text)
            if m.group(0).lower() not in _STOPWORDS
        ]

    def _resolve_user(self) -> str | None:
        if self._context_manager is not None:
            return getattr(self._context_manager, "current_user", None)
        return None

    def _resolve_project_id(self) -> str | None:
        if self._context_manager is not None:
            return getattr(self._context_manager, "active_project", None) or None
        return None

    def _resolve_workspace(
        self,
        workspace: WorkspaceSnapshot | None,
        *,
        user: str | None,
        project_id: str | None,
    ) -> WorkspaceSnapshot | None:
        if workspace is not None:
            return workspace
        if self._workspace_awareness is None:
            return None
        return self._workspace_awareness.refresh(user=user, project_id=project_id)

    def _resolve_executive(
        self,
        evaluation: ExecutiveEvaluation | None,
        message: str,
        *,
        user: str | None,
        project_id: str | None,
    ) -> ExecutiveEvaluation | None:
        if evaluation is not None:
            return evaluation
        if self._executive_function is None:
            return None
        return self._executive_function.evaluate_missions(
            message,
            user=user,
            project_id=project_id,
        )
