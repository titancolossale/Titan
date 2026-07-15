# =====================================
# Titan Project Intelligence
# =====================================

"""Project Intelligence V1 — architectural understanding of the Titan codebase.

Analysis only. Never modifies code, never executes tools, and never mutates
missions or memory. Reuses Workspace Awareness, Mission Runtime, Memory, and
Executive Function for contextual signals.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from config.settings import PROJECT_ROOT, VERSION
from context.workspace_map import (
    WorkspaceArea,
    get_area,
    list_areas,
)

if TYPE_CHECKING:
    from brain.executive_function import ExecutiveEvaluation, ExecutiveFunction
    from brain.workspace_awareness import WorkspaceAwareness, WorkspaceSnapshot
    from context.context_manager import ContextManager
    from core.mission_manager import MissionManager
    from memory.memory_service import MemoryService

logger = logging.getLogger(__name__)

_IGNORE_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".idea",
        ".vscode",
        ".cursor",
        "dist",
        "build",
        "htmlcov",
        ".eggs",
        "data",
        "logs",
        "sample_vault",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9àâäéèêëïîôùûüç_]{2,}", re.IGNORECASE)

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
        "please",
        "titan",
        "dans",
        "pour",
        "avec",
        "quoi",
        "comment",
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
        "is",
        "are",
        "of",
        "in",
        "to",
        "a",
        "an",
        "my",
    }
)

# Top-level packages that may import each other under Titan rules.
_KNOWN_PACKAGES = frozenset(
    {
        "brain",
        "core",
        "memory",
        "agents",
        "tools",
        "context",
        "config",
        "api",
        "voice",
        "prompts",
        "web",
    }
)

# Forbidden dependency edges (from → to) per engineering rulebook §3.5 / §8.3.
_FORBIDDEN_EDGES: frozenset[tuple[str, str]] = frozenset(
    {
        ("memory", "brain"),
        ("memory", "agents"),
        ("tools", "brain"),
        ("tools", "agents"),
        ("agents", "brain"),
        ("config", "brain"),
        ("config", "core"),
        ("config", "memory"),
        ("config", "agents"),
        ("config", "tools"),
        ("config", "context"),
        ("config", "api"),
    }
)

_FOLDER_RESPONSIBILITIES: dict[str, str] = {
    "brain": (
        "Reasoning orchestration, prompt assembly, cognitive loop, and final "
        "response synthesis. Conductor — not the entire orchestra."
    ),
    "core": (
        "Application lifecycle, composition root, mission/state managers, "
        "execution coordination, and session loop."
    ),
    "memory": (
        "Storage, retrieval, and classification of durable knowledge. "
        "Must not call the LLM or import Brain/agents."
    ),
    "agents": (
        "Domain-specific internal specialists. Produce artifacts for the Brain; "
        "never speak as the primary user-facing voice."
    ),
    "tools": (
        "External capabilities, Tool Runtime V2, permissions, and connectors. "
        "Tools extend capability; Brain retains decision authority."
    ),
    "context": (
        "Structured situational metadata (user, project, goal, phase) for prompts."
    ),
    "config": (
        "Non-secret static configuration. Imports nothing project-internal."
    ),
    "api": (
        "HTTP/SSE surface for the web UI — auth, chat, status, streaming."
    ),
    "web": (
        "Frontend assets (v2 production UI). Talks to the API, not Brain directly."
    ),
    "tests": "Automated pytest coverage mirroring production packages.",
    "docs": "Architecture, sprint, and subsystem documentation.",
    "prompts": "Externalized LLM prompt templates (target location).",
    "voice": "Voice identification / multi-modal interaction (foundation).",
    "scripts": "Operational and maintenance scripts — not core runtime.",
    "plugins": "Optional plugin loading surface (loader exists; catalog may be empty).",
}

# Curated feature → ownership map (analysis catalog, not a planner).
_FEATURE_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "name": "authentication",
        "aliases": ("auth", "bearer", "web auth", "api auth", "token"),
        "primary_files": ("api/auth.py",),
        "related_files": ("api/app.py", "config/settings.py"),
        "owner_module": "api",
        "summary": (
            "Bearer-token authentication for the private Titan web API "
            "(require_web_auth / validate_web_token)."
        ),
        "subsystem": "api",
    },
    {
        "name": "tool_manager",
        "aliases": ("toolmanager", "tool manager", "tool registry facade"),
        "primary_files": ("tools/tool_manager.py",),
        "related_files": (
            "tools/tool_runtime.py",
            "tools/capability_catalog.py",
            "tools/default_tools.py",
        ),
        "owner_module": "tools",
        "summary": (
            "Tool registry facade; default path uses Tool Runtime V2. "
            "Does not own strategic planning."
        ),
        "subsystem": "tools",
    },
    {
        "name": "tool_runtime",
        "aliases": ("tool runtime", "runtime v2", "toolruntime"),
        "primary_files": ("tools/tool_runtime.py",),
        "related_files": (
            "tools/tool_executor.py",
            "tools/permission_engine.py",
            "tools/confirmation_gate.py",
        ),
        "owner_module": "tools",
        "summary": "Pre-flight gates, metrics, confirmation, and execution dispatch.",
        "subsystem": "tools",
    },
    {
        "name": "memory",
        "aliases": ("long term memory", "mémoire", "memoire", "memory service"),
        "primary_files": (
            "memory/memory_service.py",
            "memory/long_term_memory.py",
        ),
        "related_files": (
            "memory/memory_retriever.py",
            "memory/memory_decider.py",
            "memory/memory_classifier.py",
            "memory/memory_manager.py",
        ),
        "owner_module": "memory",
        "summary": (
            "Durable and session memory with user isolation (Nolan ≠ Ibrahim)."
        ),
        "subsystem": "memory",
    },
    {
        "name": "mission_runtime",
        "aliases": (
            "mission runtime",
            "missions",
            "mission manager",
            "missionruntime",
        ),
        "primary_files": (
            "core/mission_runtime.py",
            "core/mission_manager.py",
        ),
        "related_files": (
            "core/mission_models.py",
            "core/mission_migrator.py",
        ),
        "owner_module": "core",
        "summary": (
            "Persist and manage multi-step missions across explicit execution turns."
        ),
        "subsystem": "core",
    },
    {
        "name": "browser_tool",
        "aliases": (
            "browser",
            "browser tool",
            "browser connector",
            "web browser",
        ),
        "primary_files": (
            "tools/connectors/browser_connector.py",
            "core/tools/browser/browser_tool.py",
        ),
        "related_files": (
            "core/tools/browser/browser_client.py",
            "core/tools/browser/html_parser.py",
            "core/browser_cli.py",
            "api/status_builders.py",
        ),
        "owner_module": "tools",
        "summary": (
            "Browser exploration capability — connector + core tool + CLI/status."
        ),
        "subsystem": "tools",
    },
    {
        "name": "execution_pipeline",
        "aliases": (
            "execution pipeline",
            "tool execution path",
            "orchestrator pipeline",
            "think pipeline",
        ),
        "primary_files": (
            "brain/pipeline/stages.py",
            "core/execution_coordinator.py",
            "tools/tool_orchestrator.py",
            "tools/tool_runtime.py",
        ),
        "related_files": (
            "tools/natural_language_planner.py",
            "tools/reasoning_loop.py",
            "brain/brain.py",
        ),
        "owner_module": "brain",
        "summary": (
            "Official path: Brain.think → ThinkPipeline → ExecutionCoordinator → "
            "ToolOrchestrator → ToolRuntime → executors."
        ),
        "subsystem": "brain",
    },
    {
        "name": "workspace_awareness",
        "aliases": ("workspace", "workspace snapshot", "workspace awareness"),
        "primary_files": ("brain/workspace_awareness.py",),
        "related_files": ("docs/WORKSPACE_AWARENESS.md", "context/workspace_map.py"),
        "owner_module": "brain",
        "summary": (
            "On-demand development-environment context for the Brain "
            "(no watchers, no tool execution)."
        ),
        "subsystem": "brain",
    },
    {
        "name": "developer_workflow",
        "aliases": ("developer workflow", "dev workflow", "development plan"),
        "primary_files": ("brain/developer_workflow.py",),
        "related_files": ("docs/DEVELOPER_WORKFLOW.md",),
        "owner_module": "brain",
        "summary": (
            "Structured software-development planning — plan only, never executes."
        ),
        "subsystem": "brain",
    },
    {
        "name": "executive_function",
        "aliases": ("executive", "mission focus", "executive function"),
        "primary_files": ("brain/executive_function.py",),
        "related_files": ("brain/executive_brain.py",),
        "owner_module": "brain",
        "summary": (
            "Ranks missions and recommends focus — read-only, no tool execution."
        ),
        "subsystem": "brain",
    },
    {
        "name": "tool_intelligence",
        "aliases": ("tool intelligence", "tool selection", "tool planning"),
        "primary_files": ("brain/tool_intelligence.py",),
        "related_files": ("brain/tool_execution_engine.py",),
        "owner_module": "brain",
        "summary": "Metadata-driven tool selection and execution planning for Brain.",
        "subsystem": "brain",
    },
    {
        "name": "obsidian",
        "aliases": ("obsidian tool", "vault", "notes connector"),
        "primary_files": (
            "tools/obsidian_tool.py",
            "core/tools/obsidian/obsidian_tool.py",
        ),
        "related_files": (
            "tools/decision/obsidian_decision.py",
            "tools/connectors/markdown_editor.py",
        ),
        "owner_module": "tools",
        "summary": (
            "Obsidian vault connector — existing user vault only; never creates vaults."
        ),
        "subsystem": "tools",
    },
    {
        "name": "cognitive_loop",
        "aliases": ("cognitive loop", "generate thoughts", "cognition"),
        "primary_files": ("brain/cognitive_loop.py",),
        "related_files": (
            "brain/cognitive_orchestrator.py",
            "brain/cognitive_models.py",
        ),
        "owner_module": "brain",
        "summary": "Observations, thoughts, and recommendations without tool execution.",
        "subsystem": "brain",
    },
    {
        "name": "project_intelligence",
        "aliases": (
            "project intelligence",
            "architecture analysis",
            "codebase architecture",
        ),
        "primary_files": ("brain/project_intelligence.py",),
        "related_files": ("docs/PROJECT_INTELLIGENCE.md", "context/workspace_map.py"),
        "owner_module": "brain",
        "summary": (
            "Architectural understanding of Titan — structure, dependencies, "
            "features, and change impact (analysis only)."
        ),
        "subsystem": "brain",
    },
    {
        "name": "code_intelligence",
        "aliases": (
            "code intelligence",
            "symbol lookup",
            "explain function",
            "call graph",
            "unused code",
        ),
        "primary_files": ("brain/code_intelligence.py",),
        "related_files": (
            "docs/CODE_INTELLIGENCE.md",
            "brain/project_intelligence.py",
            "brain/workspace_awareness.py",
        ),
        "owner_module": "brain",
        "summary": (
            "Semantic understanding of Python source — functions, classes, "
            "calls, unused candidates (analysis only)."
        ),
        "subsystem": "brain",
    },
    {
        "name": "long_term_planning",
        "aliases": (
            "long term planning",
            "long-term planner",
            "goal plan",
            "plan goal",
            "roadmap",
            "multi project plan",
        ),
        "primary_files": ("brain/long_term_planner.py",),
        "related_files": (
            "docs/LONG_TERM_PLANNER.md",
            "brain/executive_function.py",
            "brain/developer_workflow.py",
            "brain/project_intelligence.py",
            "brain/workspace_awareness.py",
        ),
        "owner_module": "brain",
        "summary": (
            "High-level objective → multi-level GoalPlan (projects, milestones, "
            "tasks, dependencies). Planning only — never executes or starts missions."
        ),
        "subsystem": "brain",
    },
)

_SCAN_FILE_LIMIT = 800
_IMPORT_EDGE_LIMIT = 2000
_DEPENDENT_LIMIT = 40
_DEPENDENCY_LIMIT = 40
_FEATURE_FILE_LIMIT = 20
_MODULE_FILE_SAMPLE = 12
_MEMORY_HINT_LIMIT = 5


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModuleDescription:
    """Description of one top-level module / package."""

    name: str
    path: str
    responsibility: str
    key_files: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    depended_on_by: tuple[str, ...] = ()
    file_count: int = 0
    why_exists: str = ""
    architectural_boundary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "responsibility": self.responsibility,
            "key_files": list(self.key_files),
            "depends_on": list(self.depends_on),
            "depended_on_by": list(self.depended_on_by),
            "file_count": self.file_count,
            "why_exists": self.why_exists,
            "architectural_boundary": self.architectural_boundary,
        }

    def format_for_prompt(self) -> str:
        lines = [
            f"MODULE: {self.name}",
            f"- path: {self.path}",
            f"- responsibility: {self.responsibility}",
            f"- depends on: {', '.join(self.depends_on) or 'none'}",
            f"- depended on by: {', '.join(self.depended_on_by) or 'none'}",
        ]
        if self.why_exists:
            lines.append(f"- why: {self.why_exists}")
        if self.key_files:
            lines.append(f"- key files: {', '.join(self.key_files[:8])}")
        return "\n".join(lines)


@dataclass(frozen=True)
class DependencyGraph:
    """Directed dependency graph between top-level packages (and optional files)."""

    nodes: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]  # (from_module, to_module)
    file_edges: tuple[tuple[str, str], ...] = ()  # (from_file, to_module)
    boundary_violations: tuple[str, ...] = ()
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": list(self.nodes),
            "edges": [{"from": src, "to": dst} for src, dst in self.edges],
            "file_edges": [
                {"from": src, "to": dst} for src, dst in self.file_edges[:200]
            ],
            "boundary_violations": list(self.boundary_violations),
            "summary": self.summary,
        }

    def dependents_of(self, module: str) -> tuple[str, ...]:
        key = module.strip().lower()
        return tuple(sorted({src for src, dst in self.edges if dst == key}))

    def dependencies_of(self, module: str) -> tuple[str, ...]:
        key = module.strip().lower()
        return tuple(sorted({dst for src, dst in self.edges if src == key}))

    def format_for_prompt(self) -> str:
        lines = [
            "DEPENDENCY GRAPH",
            f"- nodes: {', '.join(self.nodes) or 'none'}",
            f"- edges: {len(self.edges)}",
        ]
        if self.summary:
            lines.append(f"- summary: {self.summary}")
        if self.boundary_violations:
            lines.append("- boundary notes:")
            for item in self.boundary_violations[:5]:
                lines.append(f"  - {item}")
        return "\n".join(lines)


@dataclass(frozen=True)
class FeatureLocation:
    """Where a product/feature capability lives in the codebase."""

    feature: str
    owner_module: str
    primary_files: tuple[str, ...]
    related_files: tuple[str, ...] = ()
    summary: str = ""
    confidence: float = 0.0
    subsystem: str = ""
    matched_aliases: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "owner_module": self.owner_module,
            "primary_files": list(self.primary_files),
            "related_files": list(self.related_files),
            "summary": self.summary,
            "confidence": round(self.confidence, 3),
            "subsystem": self.subsystem,
            "matched_aliases": list(self.matched_aliases),
        }

    def format_for_prompt(self) -> str:
        lines = [
            f"FEATURE: {self.feature}",
            f"- owner: {self.owner_module}",
            f"- primary: {', '.join(self.primary_files) or 'unknown'}",
            f"- related: {', '.join(self.related_files[:8]) or 'none'}",
            f"- confidence: {self.confidence:.2f}",
        ]
        if self.summary:
            lines.append(f"- summary: {self.summary}")
        return "\n".join(lines)


@dataclass(frozen=True)
class ImpactAnalysis:
    """Likely blast radius of modifying a file or module (advisory only)."""

    target: str
    target_kind: str  # "file" | "module" | "unknown"
    direct_dependents: tuple[str, ...]
    transitive_modules: tuple[str, ...]
    related_features: tuple[str, ...]
    risk_level: str
    summary: str
    recommendations: tuple[str, ...] = ()
    dependency_chain: tuple[str, ...] = ()
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "target_kind": self.target_kind,
            "direct_dependents": list(self.direct_dependents),
            "transitive_modules": list(self.transitive_modules),
            "related_features": list(self.related_features),
            "risk_level": self.risk_level,
            "summary": self.summary,
            "recommendations": list(self.recommendations),
            "dependency_chain": list(self.dependency_chain),
            "confidence": round(self.confidence, 3),
        }

    def format_for_prompt(self) -> str:
        lines = [
            "IMPACT ANALYSIS",
            f"- target: {self.target} ({self.target_kind})",
            f"- risk: {self.risk_level}",
            f"- direct dependents: {', '.join(self.direct_dependents[:10]) or 'none'}",
            f"- modules in chain: {', '.join(self.transitive_modules) or 'none'}",
            f"- features: {', '.join(self.related_features) or 'none'}",
            f"- summary: {self.summary}",
        ]
        if self.recommendations:
            lines.append("- recommendations:")
            for item in self.recommendations[:5]:
                lines.append(f"  - {item}")
        return "\n".join(lines)


@dataclass(frozen=True)
class ArchitectureSummary:
    """High-level architectural picture of the project."""

    project_name: str
    version: str
    language: str
    modules: tuple[ModuleDescription, ...]
    dependency_graph: DependencyGraph
    folder_responsibilities: dict[str, str]
    subsystems: tuple[str, ...]
    execution_pipeline: tuple[str, ...]
    architectural_boundaries: tuple[str, ...]
    active_missions: tuple[dict[str, Any], ...] = ()
    memory_hints: tuple[str, ...] = ()
    workspace_summary: str = ""
    summary: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "version": self.version,
            "language": self.language,
            "modules": [m.to_dict() for m in self.modules],
            "dependency_graph": self.dependency_graph.to_dict(),
            "folder_responsibilities": dict(self.folder_responsibilities),
            "subsystems": list(self.subsystems),
            "execution_pipeline": list(self.execution_pipeline),
            "architectural_boundaries": list(self.architectural_boundaries),
            "active_missions": list(self.active_missions),
            "memory_hints": list(self.memory_hints),
            "workspace_summary": self.workspace_summary,
            "summary": self.summary,
            "timestamp": self.timestamp.isoformat(),
        }

    def format_for_prompt(self) -> str:
        lines = [
            "PROJECT ARCHITECTURE",
            f"- project: {self.project_name} v{self.version}",
            f"- language: {self.language}",
            f"- modules: {', '.join(m.name for m in self.modules) or 'none'}",
            f"- pipeline: {' → '.join(self.execution_pipeline)}",
        ]
        if self.summary:
            lines.append(f"- summary: {self.summary}")
        if self.workspace_summary:
            lines.append(f"- workspace: {self.workspace_summary}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class ProjectIntelligence:
    """Analyze Titan project architecture without executing or modifying anything."""

    def __init__(
        self,
        *,
        workspace_root: Path | str | None = None,
        workspace_awareness: WorkspaceAwareness | None = None,
        executive_function: ExecutiveFunction | None = None,
        mission_manager: MissionManager | None = None,
        memory_service: MemoryService | None = None,
        context_manager: ContextManager | None = None,
    ) -> None:
        if workspace_awareness is not None:
            root = workspace_awareness.workspace_root
        elif workspace_root is not None:
            root = Path(workspace_root)
        else:
            root = PROJECT_ROOT
        self._workspace_root = root.resolve()
        self._workspace_awareness = workspace_awareness
        self._executive_function = executive_function
        self._mission_manager = mission_manager
        self._memory_service = memory_service
        self._context_manager = context_manager
        self._last_summary: ArchitectureSummary | None = None
        self._cached_graph: DependencyGraph | None = None
        self._cached_file_imports: dict[str, set[str]] | None = None

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    @property
    def last_summary(self) -> ArchitectureSummary | None:
        return self._last_summary

    def analyze_project(
        self,
        *,
        user: str | None = None,
        project_id: str | None = None,
        workspace: WorkspaceSnapshot | None = None,
        executive_evaluation: ExecutiveEvaluation | None = None,
        refresh: bool = True,
    ) -> ArchitectureSummary:
        """Build a full architecture summary (read-only)."""
        snapshot = self._resolve_workspace(
            workspace,
            user=user,
            project_id=project_id,
            refresh=refresh,
        )
        project_root = self._project_root_from_snapshot(snapshot)
        modules = self._describe_modules(project_root, snapshot)
        graph = self._build_dependency_graph(project_root, modules)
        self._cached_graph = graph

        folder_responsibilities = self._folder_responsibilities(modules)
        boundaries = self._architectural_boundaries()
        pipeline = self._execution_pipeline()
        memory_hints = self._memory_hints(
            "project architecture modules dependencies",
            user=user,
            project_id=project_id or (snapshot.current_project if snapshot else None),
        )
        missions = tuple(snapshot.active_missions) if snapshot else ()
        if not missions:
            missions = self._active_mission_summaries()

        focus_note = ""
        if executive_evaluation is not None:
            rec = executive_evaluation.recommendation
            if rec.recommended_title:
                focus_note = f" Executive focus: « {rec.recommended_title} »."
        elif self._executive_function is not None:
            focus = self._executive_function.get_current_focus()
            if focus is not None:
                focus_note = f" Executive focus: « {focus.title} »."

        language = snapshot.project_language if snapshot else "unknown"
        project_name = snapshot.current_project if snapshot else self._workspace_root.name
        workspace_summary = snapshot.summary if snapshot else ""

        summary_text = (
            f"{project_name} ({language}) — {len(modules)} module(s), "
            f"{len(graph.edges)} package dependency edge(s), "
            f"{len(missions)} active mission(s)."
            f"{focus_note}"
        )

        result = ArchitectureSummary(
            project_name=project_name,
            version=VERSION,
            language=language,
            modules=modules,
            dependency_graph=graph,
            folder_responsibilities=folder_responsibilities,
            subsystems=tuple(m.name for m in modules),
            execution_pipeline=pipeline,
            architectural_boundaries=boundaries,
            active_missions=missions,
            memory_hints=memory_hints,
            workspace_summary=workspace_summary,
            summary=summary_text,
            timestamp=datetime.now(timezone.utc),
        )
        self._last_summary = result
        logger.info(
            "Project intelligence: project=%s modules=%d edges=%d missions=%d",
            project_name,
            len(modules),
            len(graph.edges),
            len(missions),
        )
        return result

    def find_feature(self, feature_name: str) -> FeatureLocation:
        """Locate ownership of a named feature (catalog + path heuristics)."""
        query = (feature_name or "").strip()
        if not query:
            return FeatureLocation(
                feature="",
                owner_module="unknown",
                primary_files=(),
                summary="No feature name provided.",
                confidence=0.0,
            )

        catalog_hit = self._match_feature_catalog(query)
        if catalog_hit is not None:
            primary = self._existing_paths(catalog_hit["primary_files"])
            related = self._existing_paths(catalog_hit["related_files"])
            if not primary:
                primary = tuple(catalog_hit["primary_files"])[:_FEATURE_FILE_LIMIT]
            location = FeatureLocation(
                feature=catalog_hit["name"],
                owner_module=catalog_hit["owner_module"],
                primary_files=primary,
                related_files=related,
                summary=catalog_hit["summary"],
                confidence=0.92,
                subsystem=catalog_hit.get("subsystem", catalog_hit["owner_module"]),
                matched_aliases=catalog_hit.get("_matched", ()),
            )
            logger.info(
                "Feature lookup: query=%r feature=%s owner=%s files=%d",
                query,
                location.feature,
                location.owner_module,
                len(location.primary_files),
            )
            return location

        # Heuristic: match against workspace areas / path tokens.
        area = get_area(query)
        if area is not None:
            files = self._existing_paths(area.key_files)
            return FeatureLocation(
                feature=area.key,
                owner_module=area.key,
                primary_files=files or area.key_files,
                related_files=(),
                summary=area.description,
                confidence=0.7,
                subsystem=area.key,
                matched_aliases=(query,),
            )

        heuristic = self._heuristic_feature_search(query)
        logger.info(
            "Feature lookup (heuristic): query=%r feature=%s confidence=%.2f",
            query,
            heuristic.feature,
            heuristic.confidence,
        )
        return heuristic

    def explain_module(self, module_name: str) -> ModuleDescription:
        """Explain a module's responsibility, dependencies, and reason for existing."""
        name = self._normalize_module_name(module_name)
        if not name:
            return ModuleDescription(
                name="",
                path="",
                responsibility="No module name provided.",
                why_exists="",
            )

        summary = self._last_summary
        if summary is None or name not in {m.name for m in summary.modules}:
            summary = self.analyze_project(refresh=False)

        for module in summary.modules:
            if module.name == name:
                logger.info("Module explanation: %s", name)
                return module

        # Unknown / nested path — still provide a useful description.
        area = get_area(name)
        responsibility = _FOLDER_RESPONSIBILITIES.get(
            name,
            area.description if area else f"No curated description for « {name} ».",
        )
        graph = summary.dependency_graph
        path = f"{name}/"
        module_path = self._workspace_root / name
        if not module_path.is_dir() and "/" in module_name.replace("\\", "/"):
            path = module_name.replace("\\", "/")
        return ModuleDescription(
            name=name,
            path=path,
            responsibility=responsibility,
            key_files=tuple(area.key_files[:_MODULE_FILE_SAMPLE]) if area else (),
            depends_on=graph.dependencies_of(name),
            depended_on_by=graph.dependents_of(name),
            why_exists=self._why_exists(name, responsibility),
            architectural_boundary=self._boundary_for(name),
        )

    def analyze_change_impact(self, file_or_module: str) -> ImpactAnalysis:
        """Estimate likely impact of modifying a file or top-level module."""
        target = (file_or_module or "").strip().replace("\\", "/")
        if not target:
            return ImpactAnalysis(
                target="",
                target_kind="unknown",
                direct_dependents=(),
                transitive_modules=(),
                related_features=(),
                risk_level="unknown",
                summary="No file or module provided.",
                confidence=0.0,
            )

        if self._cached_graph is None or self._cached_file_imports is None:
            self.analyze_project(refresh=False)

        graph = self._cached_graph or DependencyGraph(nodes=(), edges=(), summary="")
        file_imports = self._cached_file_imports or {}

        # Resolve class/feature aliases (e.g. ToolManager → tools/tool_manager.py).
        catalog_hit = self._match_feature_catalog(target)
        resolved_target = target
        if catalog_hit is not None and ("/" not in target and not target.endswith(".py")):
            primary = self._existing_paths(catalog_hit["primary_files"])
            if not primary:
                primary = tuple(catalog_hit["primary_files"])
            if len(primary) == 1 and primary[0].endswith(".py"):
                resolved_target = primary[0]
            elif catalog_hit.get("owner_module"):
                resolved_target = catalog_hit["owner_module"]

        kind, module_key, file_key = self._resolve_target(resolved_target)
        direct: list[str] = []
        transitive: set[str] = set()
        chain: list[str] = []

        if kind == "module":
            direct = list(graph.dependents_of(module_key))
            transitive = {module_key, *direct}
            for dep in list(direct):
                transitive.update(graph.dependents_of(dep))
            chain = [module_key, *sorted(direct)]
            related = self._features_touching_module(module_key)
        else:
            package = module_key
            importers = [
                path
                for path, imports in file_imports.items()
                if package in imports and path != file_key
            ]
            package_dependents = list(graph.dependents_of(package))
            direct = sorted(set(importers))[:_DEPENDENT_LIMIT]
            if not direct:
                direct = [f"{dep}/ (package-level)" for dep in package_dependents]
            transitive = {package, *package_dependents}
            chain = [file_key or target, package, *sorted(package_dependents)]
            related = self._features_touching_path(file_key or target)

        if catalog_hit is not None and catalog_hit["name"] not in related:
            related = [catalog_hit["name"], *related]

        risk = self._impact_risk(kind, module_key, len(direct), related)
        recommendations = self._impact_recommendations(
            kind,
            module_key,
            file_key or target,
            related,
            risk,
        )
        summary = (
            f"Modifying « {target} » likely affects {len(direct)} direct dependent(s) "
            f"across module(s): {', '.join(sorted(transitive)) or 'none'}. "
            f"Related features: {', '.join(related) or 'none'}. Risk: {risk}."
        )
        confidence = 0.85 if kind != "unknown" else 0.3
        if catalog_hit is not None:
            confidence = max(confidence, 0.88)
        analysis = ImpactAnalysis(
            target=target,
            target_kind=kind,
            direct_dependents=tuple(direct[:_DEPENDENT_LIMIT]),
            transitive_modules=tuple(sorted(transitive)),
            related_features=tuple(related),
            risk_level=risk,
            summary=summary,
            recommendations=tuple(recommendations),
            dependency_chain=tuple(chain[:20]),
            confidence=confidence,
        )
        logger.info(
            "Impact analysis: target=%s kind=%s risk=%s dependents=%d",
            target,
            kind,
            risk,
            len(analysis.direct_dependents),
        )
        return analysis

    def get_dependency_graph(self, *, refresh: bool = False) -> DependencyGraph:
        """Return the package dependency graph, building it if needed."""
        if refresh or self._cached_graph is None:
            summary = self.analyze_project(refresh=refresh)
            return summary.dependency_graph
        return self._cached_graph

    def modules_depending_on(self, module_name: str) -> tuple[str, ...]:
        """Return top-level modules that import *module_name*."""
        graph = self.get_dependency_graph()
        return graph.dependents_of(self._normalize_module_name(module_name))

    # --- internals ---------------------------------------------------------

    def _resolve_workspace(
        self,
        workspace: WorkspaceSnapshot | None,
        *,
        user: str | None,
        project_id: str | None,
        refresh: bool,
    ) -> WorkspaceSnapshot | None:
        if workspace is not None:
            return workspace
        if self._workspace_awareness is None:
            return None
        if refresh or self._workspace_awareness.last_snapshot is None:
            return self._workspace_awareness.refresh(
                user=user or self._resolve_user(),
                project_id=project_id or self._resolve_project_id(),
            )
        return self._workspace_awareness.get_workspace()

    def _project_root_from_snapshot(
        self,
        snapshot: WorkspaceSnapshot | None,
    ) -> Path:
        if snapshot is None:
            return self._workspace_root
        # Prefer workspace root; nested project dirs are rare for Titan itself.
        root = Path(snapshot.workspace_root)
        if snapshot.current_project and snapshot.current_project != root.name:
            nested = root / snapshot.current_project
            if nested.is_dir() and (
                (nested / "requirements.txt").exists()
                or (nested / "pyproject.toml").exists()
            ):
                return nested
        return root if root.exists() else self._workspace_root

    def _describe_modules(
        self,
        project_root: Path,
        snapshot: WorkspaceSnapshot | None,
    ) -> tuple[ModuleDescription, ...]:
        detected: tuple[str, ...]
        if snapshot and snapshot.detected_modules:
            detected = snapshot.detected_modules
        else:
            detected = self._detect_modules(project_root)

        # Ensure known Titan packages appear even if scan missed them.
        ordered: list[str] = []
        seen: set[str] = set()
        for name in list(detected) + sorted(_KNOWN_PACKAGES):
            if name in seen:
                continue
            if (project_root / name).is_dir() or name in detected:
                seen.add(name)
                ordered.append(name)

        # Build a temporary graph for depends_on fields.
        graph = self._build_dependency_graph(project_root, ())
        # Re-scan with module list for accurate edges — graph built below uses files.
        # We rebuild after collecting file counts.
        descriptions: list[ModuleDescription] = []
        file_map = self._scan_python_files(project_root)

        # Rebuild graph with knowledge of packages present.
        graph = self._graph_from_file_imports(file_map, ordered)
        self._cached_graph = graph
        self._cached_file_imports = {
            path: imports for path, imports in file_map.items()
        }

        for name in ordered:
            area = get_area(name)
            responsibility = _FOLDER_RESPONSIBILITIES.get(
                name,
                area.description if area else f"Top-level package « {name} ».",
            )
            key_files = self._key_files_for(name, area, file_map)
            file_count = sum(
                1
                for path in file_map
                if path == f"{name}.py" or path.startswith(f"{name}/")
            )
            descriptions.append(
                ModuleDescription(
                    name=name,
                    path=f"{name}/",
                    responsibility=responsibility,
                    key_files=key_files,
                    depends_on=graph.dependencies_of(name),
                    depended_on_by=graph.dependents_of(name),
                    file_count=file_count,
                    why_exists=self._why_exists(name, responsibility),
                    architectural_boundary=self._boundary_for(name),
                )
            )
        return tuple(descriptions)

    def _build_dependency_graph(
        self,
        project_root: Path,
        modules: tuple[ModuleDescription, ...] | list[ModuleDescription],
    ) -> DependencyGraph:
        if self._cached_graph is not None and self._cached_file_imports is not None:
            # Refresh when modules list provided with names differing — always rebuild
            # for correctness on first call with empty modules.
            pass
        file_map = self._scan_python_files(project_root)
        nodes = [m.name for m in modules] if modules else self._detect_modules(project_root)
        if not nodes:
            nodes = tuple(
                name
                for name in sorted(_KNOWN_PACKAGES)
                if (project_root / name).is_dir()
            )
        else:
            nodes = tuple(nodes)
        graph = self._graph_from_file_imports(file_map, list(nodes))
        self._cached_file_imports = dict(file_map)
        return graph

    def _graph_from_file_imports(
        self,
        file_map: dict[str, set[str]],
        nodes: list[str],
    ) -> DependencyGraph:
        node_set = {n.lower() for n in nodes} | set(_KNOWN_PACKAGES)
        edge_set: set[tuple[str, str]] = set()
        file_edges: list[tuple[str, str]] = []
        violations: list[str] = []

        for path, imports in file_map.items():
            src_pkg = path.split("/", 1)[0]
            if src_pkg.endswith(".py"):
                src_pkg = src_pkg[:-3]
            src_pkg = src_pkg.lower()
            for dst in imports:
                dst_l = dst.lower()
                if dst_l not in node_set and dst_l not in _KNOWN_PACKAGES:
                    continue
                if src_pkg == dst_l:
                    continue
                edge_set.add((src_pkg, dst_l))
                if len(file_edges) < _IMPORT_EDGE_LIMIT:
                    file_edges.append((path, dst_l))
                if (src_pkg, dst_l) in _FORBIDDEN_EDGES:
                    violations.append(
                        f"Boundary note: {src_pkg} → {dst_l} conflicts with "
                        f"rulebook dependency direction."
                    )

        nodes_out = tuple(sorted({n.lower() for n in nodes} | {s for s, _ in edge_set} | {d for _, d in edge_set}))
        edges = tuple(sorted(edge_set))
        summary = (
            f"{len(nodes_out)} node(s), {len(edges)} directed package edge(s)"
            + (f", {len(violations)} boundary note(s)" if violations else "")
        )
        return DependencyGraph(
            nodes=nodes_out,
            edges=edges,
            file_edges=tuple(file_edges),
            boundary_violations=tuple(dict.fromkeys(violations)),
            summary=summary,
        )

    def _scan_python_files(self, project_root: Path) -> dict[str, set[str]]:
        """Map relative file path → set of top-level Titan packages it imports."""
        results: dict[str, set[str]] = {}
        count = 0
        try:
            for path in project_root.rglob("*.py"):
                if any(part in _IGNORE_DIR_NAMES for part in path.parts):
                    continue
                if count >= _SCAN_FILE_LIMIT:
                    break
                rel = _rel(path, self._workspace_root)
                # Prefer project-relative if under project_root.
                try:
                    rel = path.resolve().relative_to(project_root.resolve()).as_posix()
                except ValueError:
                    pass
                imports = self._parse_imports(path)
                results[rel] = imports
                count += 1
        except OSError:
            logger.exception("Project intelligence file scan failed")
        return results

    def _parse_imports(self, path: Path) -> set[str]:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            return set()
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            return self._parse_imports_regex(source)

        found: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".", 1)[0]
                    if top in _KNOWN_PACKAGES:
                        found.add(top)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top = node.module.split(".", 1)[0]
                    if top in _KNOWN_PACKAGES:
                        found.add(top)
        return found

    @staticmethod
    def _parse_imports_regex(source: str) -> set[str]:
        found: set[str] = set()
        for match in re.finditer(
            r"^\s*(?:from|import)\s+([a-zA-Z_][\w.]*)",
            source,
            re.MULTILINE,
        ):
            top = match.group(1).split(".", 1)[0]
            if top in _KNOWN_PACKAGES:
                found.add(top)
        return found

    def _detect_modules(self, project_root: Path) -> tuple[str, ...]:
        modules: list[str] = []
        try:
            entries = sorted(project_root.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return ()
        skip = _IGNORE_DIR_NAMES | {
            "tests",
            "scripts",
            "docs",
            "plugins",
            "sample_vault",
            "prompts",
        }
        for entry in entries:
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if entry.name in skip:
                continue
            if (entry / "__init__.py").is_file() or any(entry.glob("*.py")):
                modules.append(entry.name)
        return tuple(modules)

    def _folder_responsibilities(
        self,
        modules: tuple[ModuleDescription, ...],
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        for module in modules:
            result[module.name] = module.responsibility
        for key in list_areas():
            if key not in result:
                area = get_area(key)
                if area:
                    result[key] = area.description
        for key, text in _FOLDER_RESPONSIBILITIES.items():
            result.setdefault(key, text)
        return result

    @staticmethod
    def _architectural_boundaries() -> tuple[str, ...]:
        return (
            "Brain orchestrates; tools execute; agents specialize.",
            "memory/* must NOT import brain or agents.",
            "tools/* must NOT import brain or agents.",
            "agents/* must NOT import brain.brain.",
            "config/* imports nothing project-internal.",
            "Users interact with Titan (single intelligence), not raw agents.",
            "Persistence goes through manager classes only.",
            "Project Intelligence is analysis-only — never modifies or executes.",
        )

    @staticmethod
    def _execution_pipeline() -> tuple[str, ...]:
        return (
            "Brain.think()",
            "ThinkPipeline",
            "ExecutionCoordinator",
            "NaturalLanguagePlanner / ReasoningLoop",
            "ToolOrchestrator",
            "ToolManager / ToolRuntime",
            "SyncExecutor / AsyncExecutor",
        )

    def _match_feature_catalog(self, query: str) -> dict[str, Any] | None:
        # Split CamelCase then normalize separators: ToolManager → tool manager
        spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", query or "")
        lowered = re.sub(r"[_\-]+", " ", spaced).lower().strip()
        best: dict[str, Any] | None = None
        best_score = 0
        for entry in _FEATURE_CATALOG:
            names = (entry["name"], *entry.get("aliases", ()))
            for alias in names:
                alias_norm = alias.lower().replace("_", " ")
                score = 0
                compact_q = lowered.replace(" ", "")
                compact_a = alias_norm.replace(" ", "")
                if lowered == alias_norm or lowered == entry["name"].replace("_", " "):
                    score = 100
                elif compact_q == compact_a or compact_q == entry["name"].replace("_", ""):
                    score = 98
                elif alias_norm in lowered or lowered in alias_norm:
                    score = 80 + len(alias_norm)
                elif compact_a and compact_a in compact_q:
                    score = 75 + len(compact_a)
                elif _tokens(lowered) & _tokens(alias_norm):
                    overlap = _tokens(lowered) & _tokens(alias_norm)
                    score = 40 + 10 * len(overlap)
                if score > best_score:
                    best_score = score
                    best = dict(entry)
                    best["_matched"] = (alias,)
        if best is not None and best_score >= 40:
            return best
        return None

    def _heuristic_feature_search(self, query: str) -> FeatureLocation:
        tokens = _tokens(query)
        project_root = self._workspace_root
        scored: list[tuple[int, str]] = []
        for path in self._iter_candidate_paths(project_root):
            path_tokens = _tokens(path.replace("/", " ").replace(".", " ").replace("_", " "))
            overlap = len(tokens & path_tokens)
            if overlap:
                scored.append((overlap, path))
        scored.sort(key=lambda item: (-item[0], item[1]))
        primary = tuple(path for _, path in scored[:6])
        owner = primary[0].split("/", 1)[0] if primary else "unknown"
        confidence = min(0.65, 0.25 + 0.1 * (scored[0][0] if scored else 0))
        return FeatureLocation(
            feature=query.strip(),
            owner_module=owner,
            primary_files=primary,
            related_files=tuple(path for _, path in scored[6:12]),
            summary=(
                f"Heuristic path match for « {query} » "
                f"({len(primary)} candidate file(s))."
                if primary
                else f"No strong location found for « {query} »."
            ),
            confidence=confidence if primary else 0.1,
            subsystem=owner,
            matched_aliases=(),
        )

    def _iter_candidate_paths(self, root: Path) -> list[str]:
        paths: list[str] = []
        try:
            for path in root.rglob("*.py"):
                if any(part in _IGNORE_DIR_NAMES for part in path.parts):
                    continue
                paths.append(_rel(path, self._workspace_root))
                if len(paths) >= _SCAN_FILE_LIMIT:
                    break
        except OSError:
            return paths
        return paths

    def _existing_paths(self, paths: Iterable[str]) -> tuple[str, ...]:
        existing: list[str] = []
        for rel in paths:
            candidate = self._workspace_root / rel
            if candidate.is_file() or candidate.is_dir():
                existing.append(rel.replace("\\", "/"))
            elif (PROJECT_ROOT / rel).exists():
                existing.append(rel.replace("\\", "/"))
        return tuple(existing[:_FEATURE_FILE_LIMIT])

    def _key_files_for(
        self,
        name: str,
        area: WorkspaceArea | None,
        file_map: dict[str, set[str]],
    ) -> tuple[str, ...]:
        if area is not None:
            existing = self._existing_paths(area.key_files)
            if existing:
                return existing[:_MODULE_FILE_SAMPLE]
        files = sorted(
            path
            for path in file_map
            if path.startswith(f"{name}/") and path.endswith(".py")
        )
        # Prefer non-__init__ and shorter paths.
        files.sort(key=lambda p: (p.count("/"), len(p), p))
        return tuple(files[:_MODULE_FILE_SAMPLE])

    def _resolve_target(self, target: str) -> tuple[str, str, str]:
        """Return (kind, module_key, file_key)."""
        cleaned = target.strip().replace("\\", "/").rstrip("/")
        # Strip trailing .py for module-ish names without slash.
        if "/" not in cleaned and cleaned.endswith(".py"):
            # Could be top-level module file.
            stem = cleaned[:-3]
            if (self._workspace_root / cleaned).is_file():
                return "file", stem.lower(), cleaned
            return "module", stem.lower(), ""

        if "/" not in cleaned and "." not in cleaned:
            # Module name.
            if (self._workspace_root / cleaned).is_dir():
                return "module", cleaned.lower(), ""
            # Known package even if missing in tmp fixtures.
            if cleaned.lower() in _KNOWN_PACKAGES or cleaned.lower() in _FOLDER_RESPONSIBILITIES:
                return "module", cleaned.lower(), ""
            # Feature-like — treat as module token.
            return "module", cleaned.lower(), ""

        # File path.
        module_key = cleaned.split("/", 1)[0].lower()
        if module_key.endswith(".py"):
            module_key = module_key[:-3]
        return "file", module_key, cleaned

    def _features_touching_module(self, module_key: str) -> list[str]:
        hits: list[str] = []
        for entry in _FEATURE_CATALOG:
            if entry["owner_module"] == module_key or entry.get("subsystem") == module_key:
                hits.append(entry["name"])
                continue
            for path in (*entry["primary_files"], *entry.get("related_files", ())):
                if path.startswith(f"{module_key}/") or path.startswith(f"{module_key}."):
                    hits.append(entry["name"])
                    break
        return list(dict.fromkeys(hits))

    def _features_touching_path(self, path: str) -> list[str]:
        path_l = path.lower().replace("\\", "/")
        hits: list[str] = []
        for entry in _FEATURE_CATALOG:
            candidates = (*entry["primary_files"], *entry.get("related_files", ()))
            for cand in candidates:
                cand_l = cand.lower()
                if path_l == cand_l or path_l.endswith(cand_l) or cand_l.endswith(path_l):
                    hits.append(entry["name"])
                    break
                # Class name match e.g. ToolManager → tool_manager.py
                base = Path(cand_l).stem.replace("_", "")
                target_base = Path(path_l).stem.replace("_", "")
                if base and base == target_base:
                    hits.append(entry["name"])
                    break
        if not hits:
            module = path_l.split("/", 1)[0]
            hits = self._features_touching_module(module)
        return list(dict.fromkeys(hits))

    @staticmethod
    def _impact_risk(
        kind: str,
        module_key: str,
        dependent_count: int,
        related_features: list[str],
    ) -> str:
        critical_modules = {"brain", "core", "tools", "memory"}
        if module_key in critical_modules and dependent_count >= 3:
            return "high"
        if module_key in critical_modules or len(related_features) >= 2:
            return "medium"
        if kind == "unknown":
            return "unknown"
        if dependent_count == 0:
            return "low"
        return "medium" if dependent_count >= 2 else "low"

    @staticmethod
    def _impact_recommendations(
        kind: str,
        module_key: str,
        target: str,
        related: list[str],
        risk: str,
    ) -> list[str]:
        recs = [
            "Review dependents before changing public APIs.",
            "Run targeted pytest modules covering this area.",
        ]
        if module_key == "memory":
            recs.append("Preserve Nolan/Ibrahim user isolation invariants.")
        if module_key == "tools":
            recs.append("Keep Tool Runtime permission/confirmation gates intact.")
        if module_key == "brain":
            recs.append("Avoid duplicate orchestration paths; Brain remains conductor.")
        if "mission_runtime" in related or module_key == "core":
            recs.append("Mission JSON schema changes need migration notes.")
        if risk in {"high", "medium"}:
            recs.append("Prefer minimal diffs; update docs if behavior shifts.")
        if kind == "file":
            recs.append(f"Inspect importers of « {target} » via dependency graph.")
        return recs

    @staticmethod
    def _why_exists(name: str, responsibility: str) -> str:
        area = get_area(name)
        if area is not None:
            return f"Exists as the « {area.label} » layer: {responsibility}"
        return f"Exists to own: {responsibility}"

    @staticmethod
    def _boundary_for(name: str) -> str:
        rules = {
            "memory": "Must NOT import brain/* or agents/*.",
            "tools": "Must NOT import brain/* or agents/*.",
            "agents": "Must NOT import brain.brain.",
            "config": "Must not import any other Titan module.",
            "brain": "May orchestrate memory/context/agents/tools via injection.",
            "core": "Composition and managers; avoid LLM prompt engineering details.",
        }
        return rules.get(
            name,
            "Follow modular-monolith dependency direction (rulebook §3.5).",
        )

    def _normalize_module_name(self, module_name: str) -> str:
        text = (module_name or "").strip().replace("\\", "/")
        if not text:
            return ""
        # Accept "Mission Runtime", "mission_runtime", "core/mission_runtime.py"
        lowered = text.lower()
        for entry in _FEATURE_CATALOG:
            names = (entry["name"], *entry.get("aliases", ()))
            for alias in names:
                if lowered == alias.lower() or lowered.replace(" ", "_") == entry["name"]:
                    return entry["owner_module"]
        area = get_area(text)
        if area is not None:
            return area.key
        if "/" in text:
            return text.split("/", 1)[0].lower()
        if text.endswith(".py"):
            return text[:-3].lower()
        return text.lower().replace(" ", "_")

    def _memory_hints(
        self,
        query: str,
        *,
        user: str | None,
        project_id: str | None,
    ) -> tuple[str, ...]:
        if self._memory_service is None:
            return ()
        resolved_user = user or self._resolve_user() or "Nolan"
        try:
            retrieval = self._memory_service.retrieve(
                resolved_user,
                query,
                project_id=project_id,
            )
        except Exception:
            logger.exception("Project intelligence memory retrieval failed")
            return ()
        if not retrieval.has_matches:
            return ()
        hints: list[str] = []
        for item in retrieval.items[:_MEMORY_HINT_LIMIT]:
            text = getattr(item, "text", None) or str(item)
            cleaned = text.strip()
            if cleaned:
                hints.append(cleaned[:240])
        return tuple(hints)

    def _active_mission_summaries(self) -> tuple[dict[str, Any], ...]:
        if self._mission_manager is None:
            return ()
        missions = self._mission_manager.runtime.list_active_missions()
        return tuple(
            {
                "id": mission.id,
                "title": mission.title,
                "objective": mission.objective,
                "state": mission.state.value,
                "priority": mission.priority.value,
                "progress_percent": mission.progress_percent,
            }
            for mission in missions
        )

    def _resolve_user(self) -> str | None:
        if self._context_manager is not None:
            return self._context_manager.current_user
        return None

    def _resolve_project_id(self) -> str | None:
        if self._context_manager is not None:
            return self._context_manager.active_project or None
        return None


def _tokens(text: str) -> set[str]:
    return {
        match.group(0).lower()
        for match in _TOKEN_RE.finditer(text or "")
        if match.group(0).lower() not in _STOPWORDS
    }


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
