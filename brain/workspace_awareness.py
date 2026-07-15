# =====================================
# Titan Workspace Awareness
# =====================================

"""Workspace Awareness V1 — structured development-environment context for the Brain.

Collects a WorkspaceSnapshot on explicit refresh only. Never executes tools,
never polls the filesystem in the background, and never mutates missions.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from config.settings import PROJECT_ROOT

if TYPE_CHECKING:
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

_DOC_NAMES = frozenset(
    {
        "readme.md",
        "changelog.md",
        "contributing.md",
        "license",
        "license.md",
        "architecture.md",
    }
)

_LANGUAGE_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Python", ("requirements.txt", "pyproject.toml", "setup.py", "Pipfile")),
    ("JavaScript/TypeScript", ("package.json", "tsconfig.json")),
    ("Rust", ("Cargo.toml",)),
    ("Go", ("go.mod",)),
)

_MODULE_SKIP = frozenset(
    {
        "tests",
        "scripts",
        "docs",
        "data",
        "logs",
        "plugins",
        "sample_vault",
        "prompts",
        "__pycache__",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9àâäéèêëïîôùûüç_]{3,}", re.IGNORECASE)

_RECENT_FILE_LIMIT = 25
_DOC_FILE_LIMIT = 40
_MODULE_LIMIT = 40
_OPEN_FILE_LIMIT = 30
_MISSION_RELATED_LIMIT = 15
_LARGE_FEATURE_MIN_FILES = 8
_DOC_STALE_SECONDS = 7 * 24 * 3600
_NEW_MODULE_SECONDS = 3 * 24 * 3600


@dataclass(frozen=True)
class WorkspaceRecommendation:
    """Advisory signal derived from a workspace snapshot (context only)."""

    kind: str
    summary: str
    detail: str
    related_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "detail": self.detail,
            "related_paths": list(self.related_paths),
        }


@dataclass(frozen=True)
class WorkspaceSnapshot:
    """Structured view of the current development workspace."""

    workspace_root: str
    current_project: str
    open_files: tuple[str, ...]
    recently_modified_files: tuple[str, ...]
    git_branch: str | None
    project_language: str
    detected_modules: tuple[str, ...]
    documentation_files: tuple[str, ...]
    active_missions: tuple[dict[str, Any], ...]
    timestamp: datetime
    projects: tuple[str, ...] = ()
    recommendations: tuple[WorkspaceRecommendation, ...] = ()
    summary: str = ""
    memory_hints: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_root": self.workspace_root,
            "current_project": self.current_project,
            "open_files": list(self.open_files),
            "recently_modified_files": list(self.recently_modified_files),
            "git_branch": self.git_branch,
            "project_language": self.project_language,
            "detected_modules": list(self.detected_modules),
            "documentation_files": list(self.documentation_files),
            "active_missions": list(self.active_missions),
            "timestamp": self.timestamp.isoformat(),
            "projects": list(self.projects),
            "recommendations": [item.to_dict() for item in self.recommendations],
            "summary": self.summary,
            "memory_hints": list(self.memory_hints),
        }

    def format_for_prompt(self) -> str:
        """Compact French/English-neutral block for Brain prompt injection."""
        lines = [
            "WORKSPACE",
            f"- root: {self.workspace_root}",
            f"- project: {self.current_project}",
            f"- language: {self.project_language}",
            f"- branch: {self.git_branch or 'n/a'}",
            f"- modules: {', '.join(self.detected_modules[:12]) or 'none'}",
            f"- docs: {len(self.documentation_files)} file(s)",
            f"- recent: {', '.join(self.recently_modified_files[:8]) or 'none'}",
            f"- missions: {len(self.active_missions)} active",
        ]
        if self.summary:
            lines.append(f"- summary: {self.summary}")
        if self.recommendations:
            lines.append("- recommendations:")
            for item in self.recommendations[:5]:
                lines.append(f"  - [{item.kind}] {item.summary}")
        return "\n".join(lines)


class WorkspaceAwareness:
    """Collect and cache workspace context for Brain cognition.

    Refresh is explicit only — no watchers, no polling loops.
    """

    def __init__(
        self,
        *,
        workspace_root: Path | str | None = None,
        mission_manager: MissionManager | None = None,
        memory_service: MemoryService | None = None,
        context_manager: ContextManager | None = None,
    ) -> None:
        root = Path(workspace_root) if workspace_root is not None else PROJECT_ROOT
        self._workspace_root = root.resolve()
        self._mission_manager = mission_manager
        self._memory_service = memory_service
        self._context_manager = context_manager
        self._last_snapshot: WorkspaceSnapshot | None = None

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    @property
    def last_snapshot(self) -> WorkspaceSnapshot | None:
        return self._last_snapshot

    def get_workspace(self) -> WorkspaceSnapshot:
        """Return the cached snapshot, refreshing once if none exists yet."""
        if self._last_snapshot is None:
            return self.refresh()
        return self._last_snapshot

    def refresh(
        self,
        *,
        open_files: Iterable[str] | None = None,
        user: str | None = None,
        project_id: str | None = None,
        now: datetime | None = None,
    ) -> WorkspaceSnapshot:
        """Rebuild workspace context from disk + mission/memory managers."""
        timestamp = now or _utc_now()
        root = self._workspace_root

        if not root.exists():
            snapshot = self._empty_snapshot(
                root=root,
                open_files=tuple(_normalize_rel_paths(open_files or (), root)),
                timestamp=timestamp,
            )
            self._last_snapshot = snapshot
            logger.info(
                "Workspace refresh: empty/missing root=%s project=%s",
                snapshot.workspace_root,
                snapshot.current_project,
            )
            return snapshot

        projects = self._detect_projects(root)
        current_project = self._resolve_current_project(projects, project_id)
        project_root = self._project_root_for(current_project, projects, root)

        detected_modules = self._detect_modules(project_root)
        documentation_files = self._find_documentation(project_root)
        recently_modified = self._recently_modified(project_root)
        git_branch = self._read_git_branch(root)
        project_language = self._detect_language(project_root)
        active_missions = self._active_mission_summaries()
        resolved_open = tuple(_normalize_rel_paths(open_files or (), root))[:_OPEN_FILE_LIMIT]
        memory_hints = self._memory_hints(
            current_project,
            user=user,
            project_id=project_id or current_project,
        )
        recommendations = self._build_recommendations(
            project_root=project_root,
            detected_modules=detected_modules,
            documentation_files=documentation_files,
            recently_modified=recently_modified,
            active_missions=active_missions,
            now=timestamp,
        )
        summary = self._build_summary(
            current_project=current_project,
            project_language=project_language,
            git_branch=git_branch,
            modules=detected_modules,
            docs=documentation_files,
            missions=active_missions,
            recommendations=recommendations,
        )

        snapshot = WorkspaceSnapshot(
            workspace_root=str(root),
            current_project=current_project,
            open_files=resolved_open,
            recently_modified_files=recently_modified,
            git_branch=git_branch,
            project_language=project_language,
            detected_modules=detected_modules,
            documentation_files=documentation_files,
            active_missions=active_missions,
            timestamp=timestamp,
            projects=projects,
            recommendations=recommendations,
            summary=summary,
            memory_hints=memory_hints,
        )
        self._last_snapshot = snapshot

        logger.info(
            "Workspace refresh: root=%s project=%s language=%s branch=%s "
            "modules=%d docs=%d missions=%d recommendations=%d",
            snapshot.workspace_root,
            snapshot.current_project,
            snapshot.project_language,
            snapshot.git_branch or "n/a",
            len(snapshot.detected_modules),
            len(snapshot.documentation_files),
            len(snapshot.active_missions),
            len(snapshot.recommendations),
        )
        logger.info(
            "Detected project=%s modules=%s",
            snapshot.current_project,
            ", ".join(snapshot.detected_modules[:20]) or "(none)",
        )
        logger.info("Workspace summary: %s", snapshot.summary)
        return snapshot

    def mission_related_files(
        self,
        mission_title: str,
        mission_objective: str = "",
        *,
        snapshot: WorkspaceSnapshot | None = None,
    ) -> tuple[str, ...]:
        """Return workspace paths that appear related to a mission (read-only)."""
        snap = snapshot or self._last_snapshot
        if snap is None:
            return ()
        return _correlate_mission_paths(
            mission_title,
            mission_objective,
            modules=snap.detected_modules,
            recently_modified=snap.recently_modified_files,
            documentation_files=snap.documentation_files,
        )

    def _empty_snapshot(
        self,
        *,
        root: Path,
        open_files: tuple[str, ...],
        timestamp: datetime,
    ) -> WorkspaceSnapshot:
        return WorkspaceSnapshot(
            workspace_root=str(root),
            current_project=root.name or "unknown",
            open_files=open_files,
            recently_modified_files=(),
            git_branch=None,
            project_language="unknown",
            detected_modules=(),
            documentation_files=(),
            active_missions=(),
            timestamp=timestamp,
            projects=(),
            recommendations=(),
            summary="Empty or missing workspace — no project context available.",
            memory_hints=(),
        )

    def _resolve_current_project(
        self,
        projects: tuple[str, ...],
        project_id: str | None,
    ) -> str:
        if project_id and project_id.strip():
            return project_id.strip()
        if self._context_manager is not None:
            active = (self._context_manager.active_project or "").strip()
            if active:
                return active
        if projects:
            return projects[0]
        return self._workspace_root.name or "Titan"

    def _project_root_for(
        self,
        current_project: str,
        projects: tuple[str, ...],
        root: Path,
    ) -> Path:
        if current_project in projects and current_project != root.name:
            candidate = root / current_project
            if candidate.is_dir():
                return candidate
        nested = root / current_project
        if nested.is_dir() and current_project != root.name:
            return nested
        return root

    def _detect_projects(self, root: Path) -> tuple[str, ...]:
        """Detect the workspace itself and nested project-like directories."""
        found: list[str] = []
        if _looks_like_project(root):
            found.append(root.name)

        try:
            children = sorted(root.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return tuple(found)

        for child in children:
            if not child.is_dir() or child.name in _IGNORE_DIR_NAMES:
                continue
            if child.name.startswith("."):
                continue
            if _looks_like_project(child):
                found.append(child.name)
        # Deduplicate while preserving order.
        seen: set[str] = set()
        ordered: list[str] = []
        for name in found:
            if name not in seen:
                seen.add(name)
                ordered.append(name)
        return tuple(ordered)

    def _detect_modules(self, project_root: Path) -> tuple[str, ...]:
        modules: list[str] = []
        try:
            entries = sorted(project_root.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return ()

        for entry in entries:
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if entry.name in _IGNORE_DIR_NAMES or entry.name in _MODULE_SKIP:
                continue
            if (entry / "__init__.py").is_file() or any(entry.glob("*.py")):
                modules.append(entry.name)
            elif (entry / "package.json").is_file():
                modules.append(entry.name)
        return tuple(modules[:_MODULE_LIMIT])

    def _find_documentation(self, project_root: Path) -> tuple[str, ...]:
        docs: list[str] = []
        try:
            for path in project_root.iterdir():
                if path.is_file() and path.name.lower() in _DOC_NAMES:
                    docs.append(_rel(path, self._workspace_root))
                elif path.is_file() and path.suffix.lower() == ".md" and path.name.lower().startswith(
                    "readme"
                ):
                    docs.append(_rel(path, self._workspace_root))
        except OSError:
            pass

        docs_dir = project_root / "docs"
        if docs_dir.is_dir():
            for path in sorted(docs_dir.rglob("*.md")):
                if any(part in _IGNORE_DIR_NAMES for part in path.parts):
                    continue
                docs.append(_rel(path, self._workspace_root))
                if len(docs) >= _DOC_FILE_LIMIT:
                    break
        return tuple(docs[:_DOC_FILE_LIMIT])

    def _recently_modified(self, project_root: Path) -> tuple[str, ...]:
        files: list[tuple[float, str]] = []
        for path in _iter_source_files(project_root):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            files.append((mtime, _rel(path, self._workspace_root)))
        files.sort(key=lambda item: item[0], reverse=True)
        return tuple(rel for _, rel in files[:_RECENT_FILE_LIMIT])

    def _read_git_branch(self, root: Path) -> str | None:
        head = root / ".git" / "HEAD"
        if not head.is_file():
            return None
        try:
            content = head.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if content.startswith("ref:"):
            ref = content.split(":", 1)[1].strip()
            if ref.startswith("refs/heads/"):
                return ref[len("refs/heads/") :]
            return ref
        if content:
            return content[:12]
        return None

    def _detect_language(self, project_root: Path) -> str:
        for language, markers in _LANGUAGE_MARKERS:
            if any((project_root / marker).exists() for marker in markers):
                return language

        counts: dict[str, int] = {"Python": 0, "JavaScript/TypeScript": 0, "Other": 0}
        for path in _iter_source_files(project_root, limit=200):
            suffix = path.suffix.lower()
            if suffix == ".py":
                counts["Python"] += 1
            elif suffix in {".js", ".ts", ".tsx", ".jsx"}:
                counts["JavaScript/TypeScript"] += 1
            else:
                counts["Other"] += 1
        best = max(counts.items(), key=lambda item: item[1])
        if best[1] == 0:
            return "unknown"
        return best[0]

    def _active_mission_summaries(self) -> tuple[dict[str, Any], ...]:
        if self._mission_manager is None:
            return ()
        missions = self._mission_manager.runtime.list_active_missions()
        summaries: list[dict[str, Any]] = []
        for mission in missions:
            summaries.append(
                {
                    "id": mission.id,
                    "title": mission.title,
                    "objective": mission.objective,
                    "state": mission.state.value,
                    "priority": mission.priority.value,
                    "progress_percent": mission.progress_percent,
                    "current_step": mission.current_step,
                }
            )
        return tuple(summaries)

    def _memory_hints(
        self,
        current_project: str,
        *,
        user: str | None,
        project_id: str | None,
    ) -> tuple[str, ...]:
        if self._memory_service is None:
            return ()
        resolved_user = user
        if resolved_user is None and self._context_manager is not None:
            resolved_user = self._context_manager.current_user
        if not resolved_user:
            resolved_user = "Nolan"
        query = f"workspace project {current_project} development context"
        try:
            retrieval = self._memory_service.retrieve(
                resolved_user,
                query,
                project_id=project_id,
            )
        except Exception:
            logger.exception("Workspace memory retrieval failed")
            return ()
        if not retrieval.has_matches:
            return ()
        hints: list[str] = []
        for item in retrieval.items[:5]:
            text = getattr(item, "text", None) or str(item)
            cleaned = text.strip()
            if cleaned:
                hints.append(cleaned[:240])
        return tuple(hints)

    def _build_recommendations(
        self,
        *,
        project_root: Path,
        detected_modules: tuple[str, ...],
        documentation_files: tuple[str, ...],
        recently_modified: tuple[str, ...],
        active_missions: tuple[dict[str, Any], ...],
        now: datetime,
    ) -> tuple[WorkspaceRecommendation, ...]:
        recommendations: list[WorkspaceRecommendation] = []
        now_ts = now.timestamp()

        # Missing documentation for detected modules.
        doc_basenames = {Path(path).stem.lower() for path in documentation_files}
        doc_text = " ".join(documentation_files).lower()
        missing_docs = [
            module
            for module in detected_modules
            if module.lower() not in doc_basenames and module.lower() not in doc_text
        ]
        if missing_docs and not any(
            path.lower().endswith("architecture.md") for path in documentation_files
        ):
            recommendations.append(
                WorkspaceRecommendation(
                    kind="missing_documentation",
                    summary="Some modules lack dedicated documentation.",
                    detail=(
                        "No matching docs found for: "
                        + ", ".join(missing_docs[:8])
                    ),
                    related_paths=tuple(f"{m}/" for m in missing_docs[:8]),
                )
            )
        elif missing_docs and len(documentation_files) < 3:
            recommendations.append(
                WorkspaceRecommendation(
                    kind="missing_documentation",
                    summary="Documentation coverage looks thin for this project.",
                    detail=f"Only {len(documentation_files)} documentation file(s) detected.",
                    related_paths=documentation_files[:5],
                )
            )

        # Documentation changed recently relative to code.
        doc_mtimes = _mtimes_for(self._workspace_root, documentation_files)
        code_mtimes = _mtimes_for(self._workspace_root, recently_modified)
        if doc_mtimes and code_mtimes:
            newest_doc = max(doc_mtimes)
            newest_code = max(code_mtimes)
            if newest_code - newest_doc > _DOC_STALE_SECONDS:
                recommendations.append(
                    WorkspaceRecommendation(
                        kind="documentation_changed",
                        summary="Code appears newer than documentation.",
                        detail=(
                            "Recently modified source is significantly newer than "
                            "tracked documentation files — docs may be stale."
                        ),
                        related_paths=recently_modified[:5] + documentation_files[:3],
                    )
                )
            elif newest_doc > newest_code:
                recommendations.append(
                    WorkspaceRecommendation(
                        kind="documentation_changed",
                        summary="Documentation was updated recently.",
                        detail="Docs mtimes are newer than recent source files.",
                        related_paths=documentation_files[:5],
                    )
                )

        # New modules (directory mtime within window).
        new_modules: list[str] = []
        for module in detected_modules:
            module_path = project_root / module
            try:
                age = now_ts - module_path.stat().st_mtime
            except OSError:
                continue
            if age <= _NEW_MODULE_SECONDS:
                new_modules.append(module)
        if new_modules:
            recommendations.append(
                WorkspaceRecommendation(
                    kind="new_modules",
                    summary="Recently added or touched modules detected.",
                    detail="Modules with recent directory activity: "
                    + ", ".join(new_modules[:8]),
                    related_paths=tuple(f"{m}/" for m in new_modules[:8]),
                )
            )

        # Large unfinished feature: many recent files under one module prefix.
        prefix_counts: dict[str, list[str]] = {}
        for rel in recently_modified:
            parts = Path(rel).parts
            if not parts:
                continue
            # Prefer first path segment under project (module-ish).
            key = parts[0]
            if key in {"docs", "tests", "scripts"}:
                continue
            prefix_counts.setdefault(key, []).append(rel)
        for prefix, paths in sorted(
            prefix_counts.items(),
            key=lambda item: len(item[1]),
            reverse=True,
        ):
            if len(paths) >= _LARGE_FEATURE_MIN_FILES:
                recommendations.append(
                    WorkspaceRecommendation(
                        kind="large_unfinished_feature",
                        summary=f"Heavy recent activity under « {prefix} ».",
                        detail=(
                            f"{len(paths)} recently modified files share the "
                            f"« {prefix} » prefix — possible unfinished feature."
                        ),
                        related_paths=tuple(paths[:10]),
                    )
                )
                break

        # Mission-related files.
        for mission in active_missions:
            related = _correlate_mission_paths(
                str(mission.get("title", "")),
                str(mission.get("objective", "")),
                modules=detected_modules,
                recently_modified=recently_modified,
                documentation_files=documentation_files,
            )
            if related:
                recommendations.append(
                    WorkspaceRecommendation(
                        kind="mission_related_files",
                        summary=(
                            f"Files related to mission « {mission.get('title')} »."
                        ),
                        detail=f"Matched paths for active mission {mission.get('id')}.",
                        related_paths=related,
                    )
                )

        return tuple(recommendations)

    @staticmethod
    def _build_summary(
        *,
        current_project: str,
        project_language: str,
        git_branch: str | None,
        modules: tuple[str, ...],
        docs: tuple[str, ...],
        missions: tuple[dict[str, Any], ...],
        recommendations: tuple[WorkspaceRecommendation, ...],
    ) -> str:
        branch = git_branch or "no-git"
        rec_kinds = ", ".join(sorted({item.kind for item in recommendations})) or "none"
        return (
            f"Project « {current_project} » ({project_language}, {branch}) with "
            f"{len(modules)} module(s), {len(docs)} doc file(s), "
            f"{len(missions)} active mission(s); signals: {rec_kinds}."
        )


def _looks_like_project(path: Path) -> bool:
    markers = (
        "requirements.txt",
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "README.md",
        "readme.md",
    )
    if any((path / marker).exists() for marker in markers):
        return True
    # Titan-style package layout: multiple top-level Python packages.
    try:
        py_packages = [
            child
            for child in path.iterdir()
            if child.is_dir() and (child / "__init__.py").is_file()
        ]
    except OSError:
        return False
    return len(py_packages) >= 2


def _iter_source_files(root: Path, *, limit: int = 2000) -> list[Path]:
    results: list[Path] = []
    suffixes = {".py", ".md", ".ts", ".tsx", ".js", ".jsx", ".json", ".toml", ".yml", ".yaml"}
    try:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in _IGNORE_DIR_NAMES for part in path.parts):
                continue
            if path.suffix.lower() not in suffixes and path.name.lower() not in _DOC_NAMES:
                continue
            results.append(path)
            if len(results) >= limit:
                break
    except OSError:
        return results
    return results


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _normalize_rel_paths(paths: Iterable[str], root: Path) -> list[str]:
    normalized: list[str] = []
    for raw in paths:
        text = str(raw).strip()
        if not text:
            continue
        candidate = Path(text)
        if candidate.is_absolute():
            try:
                normalized.append(candidate.resolve().relative_to(root.resolve()).as_posix())
            except ValueError:
                normalized.append(candidate.as_posix())
        else:
            normalized.append(Path(text).as_posix())
    return normalized


def _mtimes_for(root: Path, rel_paths: Iterable[str]) -> list[float]:
    values: list[float] = []
    for rel in rel_paths:
        path = root / rel
        try:
            if path.is_file():
                values.append(path.stat().st_mtime)
        except OSError:
            continue
    return values


def _tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in _TOKEN_RE.finditer(text or "")}


def _correlate_mission_paths(
    mission_title: str,
    mission_objective: str,
    *,
    modules: tuple[str, ...],
    recently_modified: tuple[str, ...],
    documentation_files: tuple[str, ...],
) -> tuple[str, ...]:
    tokens = _tokens(f"{mission_title} {mission_objective}")
    if not tokens:
        return ()
    candidates = list(modules) + list(recently_modified) + list(documentation_files)
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        path_tokens = _tokens(path.replace("/", " ").replace("\\", " ").replace(".", " "))
        overlap = len(tokens & path_tokens)
        if overlap:
            scored.append((overlap, path))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return tuple(path for _, path in scored[:_MISSION_RELATED_LIMIT])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
