# =====================================
# Titan Code Intelligence
# =====================================

"""Code Intelligence V1 — semantic understanding of Python source code.

Analysis only. Never modifies files, never executes code, and never mutates
missions or memory. Complements Project Intelligence (architecture) with
function/class/call-level understanding.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from config.settings import PROJECT_ROOT

if TYPE_CHECKING:
    from brain.executive_function import ExecutiveEvaluation, ExecutiveFunction
    from brain.project_intelligence import ProjectIntelligence
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

_SCAN_FILE_LIMIT = 800
_CALLER_LIMIT = 80
_UNUSED_LIMIT = 60
_SYMBOL_MATCH_LIMIT = 40
_MEMORY_HINT_LIMIT = 5
_METHOD_SAMPLE = 24
_CALL_SAMPLE = 20

_BUILTIN_OR_COMMON = frozenset(
    {
        "print",
        "len",
        "str",
        "int",
        "float",
        "bool",
        "list",
        "dict",
        "set",
        "tuple",
        "range",
        "enumerate",
        "zip",
        "map",
        "filter",
        "sorted",
        "reversed",
        "isinstance",
        "issubclass",
        "getattr",
        "setattr",
        "hasattr",
        "super",
        "type",
        "object",
        "Exception",
        "ValueError",
        "TypeError",
        "KeyError",
        "AttributeError",
        "ImportError",
        "OSError",
        "open",
        "Path",
        "logger",
        "logging",
        "re",
        "json",
        "os",
        "sys",
        "Any",
        "Optional",
        "None",
        "True",
        "False",
    }
)


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SymbolLocation:
    """Where a named symbol is defined or referenced."""

    name: str
    kind: str  # "function" | "method" | "class" | "import" | "reference"
    module: str
    file_path: str
    line: int
    qualified_name: str = ""
    context: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "module": self.module,
            "file_path": self.file_path,
            "line": self.line,
            "qualified_name": self.qualified_name,
            "context": self.context,
        }

    def format_for_prompt(self) -> str:
        qn = self.qualified_name or self.name
        return f"{qn} ({self.kind}) @ {self.file_path}:{self.line}"


@dataclass(frozen=True)
class FunctionSummary:
    """Semantic summary of a function or method."""

    name: str
    qualified_name: str
    module: str
    file_path: str
    line: int
    signature: str
    docstring: str
    purpose: str
    parameters: tuple[str, ...] = ()
    returns: str = ""
    decorators: tuple[str, ...] = ()
    is_method: bool = False
    class_name: str = ""
    calls: tuple[str, ...] = ()
    called_by: tuple[str, ...] = ()
    complexity_hint: str = "low"
    modification_impact: str = "unknown"
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "module": self.module,
            "file_path": self.file_path,
            "line": self.line,
            "signature": self.signature,
            "docstring": self.docstring,
            "purpose": self.purpose,
            "parameters": list(self.parameters),
            "returns": self.returns,
            "decorators": list(self.decorators),
            "is_method": self.is_method,
            "class_name": self.class_name,
            "calls": list(self.calls),
            "called_by": list(self.called_by),
            "complexity_hint": self.complexity_hint,
            "modification_impact": self.modification_impact,
            "confidence": round(self.confidence, 3),
        }

    def format_for_prompt(self) -> str:
        lines = [
            f"FUNCTION: {self.qualified_name}",
            f"- file: {self.file_path}:{self.line}",
            f"- signature: {self.signature}",
            f"- purpose: {self.purpose}",
        ]
        if self.parameters:
            lines.append(f"- params: {', '.join(self.parameters)}")
        if self.returns:
            lines.append(f"- returns: {self.returns}")
        if self.called_by:
            lines.append(f"- callers: {', '.join(self.called_by[:8])}")
        if self.calls:
            lines.append(f"- calls: {', '.join(self.calls[:8])}")
        lines.append(f"- modification impact: {self.modification_impact}")
        return "\n".join(lines)


@dataclass(frozen=True)
class ClassSummary:
    """Semantic summary of a class."""

    name: str
    qualified_name: str
    module: str
    file_path: str
    line: int
    docstring: str
    purpose: str
    bases: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
    method_summaries: tuple[str, ...] = ()
    decorators: tuple[str, ...] = ()
    attributes: tuple[str, ...] = ()
    called_by: tuple[str, ...] = ()
    modification_impact: str = "unknown"
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "module": self.module,
            "file_path": self.file_path,
            "line": self.line,
            "docstring": self.docstring,
            "purpose": self.purpose,
            "bases": list(self.bases),
            "methods": list(self.methods),
            "method_summaries": list(self.method_summaries),
            "decorators": list(self.decorators),
            "attributes": list(self.attributes),
            "called_by": list(self.called_by),
            "modification_impact": self.modification_impact,
            "confidence": round(self.confidence, 3),
        }

    def format_for_prompt(self) -> str:
        lines = [
            f"CLASS: {self.qualified_name}",
            f"- file: {self.file_path}:{self.line}",
            f"- purpose: {self.purpose}",
            f"- bases: {', '.join(self.bases) or 'object'}",
            f"- methods: {', '.join(self.methods[:12]) or 'none'}",
        ]
        if self.attributes:
            lines.append(f"- attributes: {', '.join(self.attributes[:10])}")
        lines.append(f"- modification impact: {self.modification_impact}")
        return "\n".join(lines)


@dataclass(frozen=True)
class ModuleSummary:
    """Semantic summary of a Python module (file or package path)."""

    name: str
    file_path: str
    docstring: str
    purpose: str
    imports: tuple[str, ...] = ()
    classes: tuple[str, ...] = ()
    functions: tuple[str, ...] = ()
    class_count: int = 0
    function_count: int = 0
    inheritance: tuple[str, ...] = ()
    key_symbols: tuple[str, ...] = ()
    memory_hints: tuple[str, ...] = ()
    mission_context: str = ""
    confidence: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "file_path": self.file_path,
            "docstring": self.docstring,
            "purpose": self.purpose,
            "imports": list(self.imports),
            "classes": list(self.classes),
            "functions": list(self.functions),
            "class_count": self.class_count,
            "function_count": self.function_count,
            "inheritance": list(self.inheritance),
            "key_symbols": list(self.key_symbols),
            "memory_hints": list(self.memory_hints),
            "mission_context": self.mission_context,
            "confidence": round(self.confidence, 3),
            "timestamp": self.timestamp.isoformat(),
        }

    def format_for_prompt(self) -> str:
        lines = [
            f"MODULE SUMMARY: {self.name}",
            f"- path: {self.file_path}",
            f"- purpose: {self.purpose}",
            f"- classes ({self.class_count}): {', '.join(self.classes[:10]) or 'none'}",
            f"- functions ({self.function_count}): "
            f"{', '.join(self.functions[:10]) or 'none'}",
            f"- imports: {', '.join(self.imports[:12]) or 'none'}",
        ]
        if self.inheritance:
            lines.append(f"- inheritance: {', '.join(self.inheritance[:8])}")
        return "\n".join(lines)


@dataclass(frozen=True)
class CallGraph:
    """Directed call relationships for a symbol or whole index slice."""

    root: str
    nodes: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]  # (caller, callee)
    callers: tuple[SymbolLocation, ...] = ()
    callees: tuple[str, ...] = ()
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "nodes": list(self.nodes),
            "edges": [{"from": src, "to": dst} for src, dst in self.edges],
            "callers": [c.to_dict() for c in self.callers],
            "callees": list(self.callees),
            "summary": self.summary,
        }

    def format_for_prompt(self) -> str:
        lines = [
            "CALL GRAPH",
            f"- root: {self.root}",
            f"- callers: {len(self.callers)}",
            f"- callees: {', '.join(self.callees[:10]) or 'none'}",
        ]
        if self.summary:
            lines.append(f"- summary: {self.summary}")
        for caller in self.callers[:8]:
            lines.append(f"  - {caller.format_for_prompt()}")
        return "\n".join(lines)


@dataclass(frozen=True)
class UnusedCandidate:
    """Heuristic unused-code candidate (advisory — not proof of dead code)."""

    name: str
    qualified_name: str
    kind: str
    file_path: str
    line: int
    reason: str
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "kind": self.kind,
            "file_path": self.file_path,
            "line": self.line,
            "reason": self.reason,
            "confidence": round(self.confidence, 3),
        }

    def format_for_prompt(self) -> str:
        return (
            f"UNUSED CANDIDATE: {self.qualified_name} ({self.kind}) "
            f"@ {self.file_path}:{self.line} — {self.reason}"
        )


# ---------------------------------------------------------------------------
# Internal index records
# ---------------------------------------------------------------------------


@dataclass
class _FunctionRecord:
    name: str
    qualified_name: str
    module: str
    file_path: str
    line: int
    signature: str
    docstring: str
    parameters: tuple[str, ...]
    returns: str
    decorators: tuple[str, ...]
    is_method: bool
    class_name: str
    calls: tuple[str, ...]
    end_line: int
    is_private: bool
    is_dunder: bool
    is_property: bool
    body_lines: int


@dataclass
class _ClassRecord:
    name: str
    qualified_name: str
    module: str
    file_path: str
    line: int
    docstring: str
    bases: tuple[str, ...]
    methods: tuple[str, ...]
    decorators: tuple[str, ...]
    attributes: tuple[str, ...]
    end_line: int


@dataclass
class _ModuleRecord:
    name: str
    file_path: str
    docstring: str
    imports: tuple[str, ...]
    classes: tuple[str, ...]
    functions: tuple[str, ...]
    inheritance: tuple[str, ...]


@dataclass
class _CodeIndex:
    functions: dict[str, list[_FunctionRecord]] = field(default_factory=dict)
    classes: dict[str, list[_ClassRecord]] = field(default_factory=dict)
    modules: dict[str, _ModuleRecord] = field(default_factory=dict)
    # callee short/qualified name → list of caller qualified names
    callers_of: dict[str, set[str]] = field(default_factory=dict)
    # caller qualified → set of callee names
    callees_of: dict[str, set[str]] = field(default_factory=dict)
    # all defined qualified names
    defined: set[str] = field(default_factory=set)
    # short name → qualified names that reference it (calls + inheritance mentions)
    references: dict[str, set[str]] = field(default_factory=dict)
    file_count: int = 0


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class CodeIntelligence:
    """Analyze Python source for semantic code understanding (read-only)."""

    def __init__(
        self,
        *,
        workspace_root: Path | str | None = None,
        workspace_awareness: WorkspaceAwareness | None = None,
        project_intelligence: ProjectIntelligence | None = None,
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
        self._project_intelligence = project_intelligence
        self._executive_function = executive_function
        self._mission_manager = mission_manager
        self._memory_service = memory_service
        self._context_manager = context_manager
        self._index: _CodeIndex | None = None

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def ensure_index(self, *, refresh: bool = False) -> _CodeIndex:
        """Build or return the cached code index (AST scan only)."""
        if self._index is not None and not refresh:
            return self._index
        self._index = self._build_index()
        return self._index

    def explain_function(self, name: str) -> FunctionSummary:
        """Explain what a function or method does (analysis only)."""
        query = (name or "").strip()
        if not query:
            return FunctionSummary(
                name="",
                qualified_name="",
                module="",
                file_path="",
                line=0,
                signature="",
                docstring="",
                purpose="No function name provided.",
                confidence=0.0,
            )

        index = self.ensure_index()
        record = self._resolve_function(index, query)
        if record is None:
            return FunctionSummary(
                name=query,
                qualified_name=query,
                module="",
                file_path="",
                line=0,
                signature="",
                docstring="",
                purpose=f"No function or method named « {query} » found in the index.",
                confidence=0.1,
            )

        callers = self._caller_names(index, record)
        purpose = self._explain_function_purpose(record)
        impact = self._impact_from_caller_count(len(callers), record.is_private)
        summary = FunctionSummary(
            name=record.name,
            qualified_name=record.qualified_name,
            module=record.module,
            file_path=record.file_path,
            line=record.line,
            signature=record.signature,
            docstring=record.docstring,
            purpose=purpose,
            parameters=record.parameters,
            returns=record.returns,
            decorators=record.decorators,
            is_method=record.is_method,
            class_name=record.class_name,
            calls=record.calls[:_CALL_SAMPLE],
            called_by=tuple(callers[:_CALLER_LIMIT]),
            complexity_hint=self._complexity_hint(record),
            modification_impact=impact,
            confidence=0.9 if record.docstring else 0.75,
        )
        logger.info(
            "Function explanation: %s callers=%d impact=%s",
            summary.qualified_name,
            len(summary.called_by),
            summary.modification_impact,
        )
        return summary

    def explain_class(self, name: str) -> ClassSummary:
        """Explain what a class does (analysis only)."""
        query = (name or "").strip()
        if not query:
            return ClassSummary(
                name="",
                qualified_name="",
                module="",
                file_path="",
                line=0,
                docstring="",
                purpose="No class name provided.",
                confidence=0.0,
            )

        index = self.ensure_index()
        record = self._resolve_class(index, query)
        if record is None:
            return ClassSummary(
                name=query,
                qualified_name=query,
                module="",
                file_path="",
                line=0,
                docstring="",
                purpose=f"No class named « {query} » found in the index.",
                confidence=0.1,
            )

        method_summaries = self._method_purpose_lines(index, record)
        callers = sorted(index.references.get(record.name, set()))[:_CALLER_LIMIT]
        # Also treat instantiation-like references via callers_of
        for key in (record.name, record.qualified_name):
            callers = list(
                dict.fromkeys([*callers, *sorted(index.callers_of.get(key, set()))])
            )[:_CALLER_LIMIT]
        purpose = self._explain_class_purpose(record, method_summaries)
        impact = self._impact_from_caller_count(len(callers), record.name.startswith("_"))
        summary = ClassSummary(
            name=record.name,
            qualified_name=record.qualified_name,
            module=record.module,
            file_path=record.file_path,
            line=record.line,
            docstring=record.docstring,
            purpose=purpose,
            bases=record.bases,
            methods=record.methods,
            method_summaries=tuple(method_summaries[:_METHOD_SAMPLE]),
            decorators=record.decorators,
            attributes=record.attributes,
            called_by=tuple(callers),
            modification_impact=impact,
            confidence=0.9 if record.docstring else 0.75,
        )
        logger.info(
            "Class explanation: %s methods=%d impact=%s",
            summary.qualified_name,
            len(summary.methods),
            summary.modification_impact,
        )
        return summary

    def find_symbol(self, name: str) -> tuple[SymbolLocation, ...]:
        """Locate definitions (and strong references) for a symbol name."""
        query = (name or "").strip()
        if not query:
            return ()

        index = self.ensure_index()
        short, qualified = self._split_symbol_query(query)
        locations: list[SymbolLocation] = []

        for record in self._iter_functions(index):
            if self._name_matches(record.name, record.qualified_name, short, qualified):
                locations.append(
                    SymbolLocation(
                        name=record.name,
                        kind="method" if record.is_method else "function",
                        module=record.module,
                        file_path=record.file_path,
                        line=record.line,
                        qualified_name=record.qualified_name,
                        context=record.signature,
                    )
                )

        for record in self._iter_classes(index):
            if self._name_matches(record.name, record.qualified_name, short, qualified):
                locations.append(
                    SymbolLocation(
                        name=record.name,
                        kind="class",
                        module=record.module,
                        file_path=record.file_path,
                        line=record.line,
                        qualified_name=record.qualified_name,
                        context=", ".join(record.bases) or "object",
                    )
                )

        # Import aliases / imported names appearing in module import lists
        for module in index.modules.values():
            for imported in module.imports:
                leaf = imported.rsplit(".", 1)[-1]
                if leaf == short or imported == qualified or imported.endswith(f".{short}"):
                    locations.append(
                        SymbolLocation(
                            name=leaf,
                            kind="import",
                            module=module.name,
                            file_path=module.file_path,
                            line=1,
                            qualified_name=imported,
                            context="import",
                        )
                    )

        # Deduplicate by file:line:kind
        seen: set[tuple[str, int, str]] = set()
        unique: list[SymbolLocation] = []
        for loc in locations:
            key = (loc.file_path, loc.line, loc.kind)
            if key in seen:
                continue
            seen.add(key)
            unique.append(loc)
            if len(unique) >= _SYMBOL_MATCH_LIMIT:
                break

        logger.info("Symbol lookup: query=%r matches=%d", query, len(unique))
        return tuple(unique)

    def find_callers(self, name: str) -> CallGraph:
        """Build a call graph rooted at *name* (callers + callees)."""
        query = (name or "").strip()
        if not query:
            return CallGraph(
                root="",
                nodes=(),
                edges=(),
                summary="No symbol name provided.",
            )

        index = self.ensure_index()
        short, qualified = self._split_symbol_query(query)
        target_qns: set[str] = set()

        func = self._resolve_function(index, query)
        if func is not None:
            target_qns.add(func.qualified_name)
            callees = list(func.calls)
        else:
            callees = []

        cls = self._resolve_class(index, query)
        if cls is not None:
            target_qns.add(cls.qualified_name)
            for method_qn in (
                f"{cls.qualified_name}.{m}" for m in cls.methods
            ):
                target_qns.add(method_qn)

        # Also match by short name keys in callers_of
        keys = {short, qualified, *target_qns}
        caller_qns: set[str] = set()
        for key in keys:
            if not key:
                continue
            caller_qns.update(index.callers_of.get(key, set()))
            # Match suffix: Foo.bar callers stored under "bar" and "Foo.bar"
            for stored_key, callers in index.callers_of.items():
                if stored_key == key or stored_key.endswith(f".{short}"):
                    if short and (
                        stored_key == short
                        or stored_key.endswith(f".{short}")
                        or stored_key == qualified
                    ):
                        caller_qns.update(callers)

        caller_locations: list[SymbolLocation] = []
        edges: list[tuple[str, str]] = []
        root_label = (
            func.qualified_name
            if func is not None
            else cls.qualified_name
            if cls is not None
            else query
        )

        for caller_qn in sorted(caller_qns)[:_CALLER_LIMIT]:
            edges.append((caller_qn, root_label))
            loc = self._location_for_qualified(index, caller_qn)
            if loc is not None:
                caller_locations.append(loc)
            else:
                caller_locations.append(
                    SymbolLocation(
                        name=caller_qn.rsplit(".", 1)[-1],
                        kind="reference",
                        module=caller_qn.split(".", 1)[0] if "." in caller_qn else "",
                        file_path="",
                        line=0,
                        qualified_name=caller_qn,
                        context="caller",
                    )
                )

        if func is not None:
            for callee in func.calls[:_CALL_SAMPLE]:
                edges.append((root_label, callee))
            callees = list(func.calls[:_CALL_SAMPLE])
        elif not callees:
            callees = sorted(index.callees_of.get(root_label, set()))[:_CALL_SAMPLE]
            for callee in callees:
                edges.append((root_label, callee))

        nodes = tuple(
            sorted(
                {
                    root_label,
                    *[c.qualified_name for c in caller_locations],
                    *callees,
                }
            )
        )
        summary = (
            f"« {root_label} » has {len(caller_locations)} caller(s) and "
            f"{len(callees)} known callee(s) in the static index."
        )
        graph = CallGraph(
            root=root_label,
            nodes=nodes,
            edges=tuple(edges),
            callers=tuple(caller_locations),
            callees=tuple(callees),
            summary=summary,
        )
        logger.info(
            "Call graph: root=%s callers=%d callees=%d",
            root_label,
            len(graph.callers),
            len(graph.callees),
        )
        return graph

    def find_unused_candidates(self) -> tuple[UnusedCandidate, ...]:
        """Heuristic unused definitions — advisory candidates only."""
        index = self.ensure_index()
        candidates: list[UnusedCandidate] = []

        for record in self._iter_functions(index):
            if record.is_dunder or record.is_property:
                continue
            if record.name in {"main", "run", "start", "think", "execute", "plan"}:
                continue
            # Public API entry points often look unused to static call graphs.
            if not record.is_private and record.name in {
                "create_app",
                "get_titan",
                "refresh",
                "analyze_project",
            }:
                continue

            refs = index.callers_of.get(record.name, set()) | index.callers_of.get(
                record.qualified_name,
                set(),
            )
            # Self-module references via short name still count
            external = {c for c in refs if c != record.qualified_name}
            if external:
                continue

            # Private helpers with no callers are stronger candidates
            if record.is_private:
                reason = "Private function/method with no static callers in the index."
                confidence = 0.55
            else:
                # Skip top-level public functions that may be Brain/API surface
                if not record.is_method and not record.name.startswith("_"):
                    # Still flag if never referenced and not a class method
                    reason = (
                        "Public function with no static callers — may be API surface "
                        "or unused; verify before removal."
                    )
                    confidence = 0.35
                else:
                    reason = "Method with no static callers in the index."
                    confidence = 0.4

            candidates.append(
                UnusedCandidate(
                    name=record.name,
                    qualified_name=record.qualified_name,
                    kind="method" if record.is_method else "function",
                    file_path=record.file_path,
                    line=record.line,
                    reason=reason,
                    confidence=confidence,
                )
            )

        for record in self._iter_classes(index):
            if record.name.startswith("_"):
                refs = index.references.get(record.name, set()) | index.callers_of.get(
                    record.name,
                    set(),
                )
                if not refs:
                    candidates.append(
                        UnusedCandidate(
                            name=record.name,
                            qualified_name=record.qualified_name,
                            kind="class",
                            file_path=record.file_path,
                            line=record.line,
                            reason="Private class with no static references.",
                            confidence=0.45,
                        )
                    )

        # Prefer higher confidence, then path
        candidates.sort(key=lambda c: (-c.confidence, c.file_path, c.line))
        result = tuple(candidates[:_UNUSED_LIMIT])
        logger.info("Unused candidates: %d", len(result))
        return result

    def summarize_module(self, module: str) -> ModuleSummary:
        """Summarize a Python module file or package-relative path."""
        query = (module or "").strip().replace("\\", "/")
        if not query:
            return ModuleSummary(
                name="",
                file_path="",
                docstring="",
                purpose="No module path provided.",
                confidence=0.0,
            )

        index = self.ensure_index()
        record = self._resolve_module(index, query)
        if record is None:
            # Fall back to Project Intelligence package description when available
            purpose = f"No Python module matched « {query} » in the code index."
            if self._project_intelligence is not None:
                try:
                    pkg = self._project_intelligence.explain_module(query)
                    if pkg.responsibility:
                        purpose = (
                            f"Package-level note from Project Intelligence: "
                            f"{pkg.responsibility}"
                        )
                except Exception:
                    logger.exception("Project intelligence fallback failed")
            return ModuleSummary(
                name=query,
                file_path="",
                docstring="",
                purpose=purpose,
                confidence=0.2,
            )

        purpose = self._module_purpose(record)
        memory_hints = self._memory_hints(f"code module {record.name}")
        mission_context = self._mission_context()
        summary = ModuleSummary(
            name=record.name,
            file_path=record.file_path,
            docstring=record.docstring,
            purpose=purpose,
            imports=record.imports,
            classes=record.classes,
            functions=record.functions,
            class_count=len(record.classes),
            function_count=len(record.functions),
            inheritance=record.inheritance,
            key_symbols=tuple(
                list(record.classes)[:6] + list(record.functions)[:6]
            ),
            memory_hints=memory_hints,
            mission_context=mission_context,
            confidence=0.88 if record.docstring else 0.7,
        )
        logger.info(
            "Module summary: %s classes=%d functions=%d",
            summary.name,
            summary.class_count,
            summary.function_count,
        )
        return summary

    def estimate_modification_impact(self, name: str) -> dict[str, Any]:
        """Estimate blast radius of modifying a symbol (advisory)."""
        query = (name or "").strip()
        if not query:
            return {
                "target": "",
                "kind": "unknown",
                "caller_count": 0,
                "impact": "unknown",
                "summary": "No symbol provided.",
            }

        func = self.explain_function(query)
        if func.confidence >= 0.5 and func.file_path:
            return {
                "target": func.qualified_name,
                "kind": "method" if func.is_method else "function",
                "caller_count": len(func.called_by),
                "impact": func.modification_impact,
                "callers": list(func.called_by[:20]),
                "file_path": func.file_path,
                "summary": (
                    f"Modifying « {func.qualified_name} » may affect "
                    f"{len(func.called_by)} caller(s). Impact: {func.modification_impact}."
                ),
            }

        cls = self.explain_class(query)
        if cls.confidence >= 0.5 and cls.file_path:
            return {
                "target": cls.qualified_name,
                "kind": "class",
                "caller_count": len(cls.called_by),
                "impact": cls.modification_impact,
                "callers": list(cls.called_by[:20]),
                "methods": list(cls.methods),
                "file_path": cls.file_path,
                "summary": (
                    f"Modifying « {cls.qualified_name} » may affect "
                    f"{len(cls.called_by)} reference(s) and {len(cls.methods)} method(s). "
                    f"Impact: {cls.modification_impact}."
                ),
            }

        return {
            "target": query,
            "kind": "unknown",
            "caller_count": 0,
            "impact": "unknown",
            "summary": f"Symbol « {query} » not found for impact estimation.",
        }

    # --- Index construction -------------------------------------------------

    def _build_index(self) -> _CodeIndex:
        root = self._resolve_project_root()
        index = _CodeIndex()
        count = 0
        try:
            for path in root.rglob("*.py"):
                if any(part in _IGNORE_DIR_NAMES for part in path.parts):
                    continue
                if count >= _SCAN_FILE_LIMIT:
                    break
                self._index_file(index, path, root)
                count += 1
        except OSError:
            logger.exception("Code intelligence scan failed")
        index.file_count = count
        logger.info(
            "Code index built: files=%d functions=%d classes=%d modules=%d",
            index.file_count,
            sum(len(v) for v in index.functions.values()),
            sum(len(v) for v in index.classes.values()),
            len(index.modules),
        )
        return index

    def _resolve_project_root(self) -> Path:
        if self._workspace_awareness is not None:
            snap = self._workspace_awareness.last_snapshot
            if snap is None:
                snap = self._workspace_awareness.get_workspace()
            root = Path(snap.workspace_root)
            if root.exists():
                return root
        return self._workspace_root

    def _index_file(self, index: _CodeIndex, path: Path, root: Path) -> None:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            return
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            return

        rel = _rel(path, root)
        module_name = _module_name_from_path(rel)
        module_doc = ast.get_docstring(tree) or ""
        imports = self._collect_imports(tree)
        class_names: list[str] = []
        function_names: list[str] = []
        inheritance: list[str] = []

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                class_rec = self._index_class(index, node, module_name, rel)
                class_names.append(class_rec.name)
                for base in class_rec.bases:
                    inheritance.append(f"{class_rec.name} → {base}")
                    index.references.setdefault(base, set()).add(class_rec.qualified_name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_rec = self._index_function(
                    index,
                    node,
                    module_name,
                    rel,
                    class_name="",
                )
                function_names.append(func_rec.name)

        index.modules[rel] = _ModuleRecord(
            name=module_name,
            file_path=rel,
            docstring=_first_line(module_doc),
            imports=tuple(imports),
            classes=tuple(class_names),
            functions=tuple(function_names),
            inheritance=tuple(inheritance),
        )
        # Also key by module dotted name and stem
        index.modules[module_name] = index.modules[rel]
        stem = Path(rel).stem
        if stem not in index.modules:
            index.modules[stem] = index.modules[rel]

    def _index_class(
        self,
        index: _CodeIndex,
        node: ast.ClassDef,
        module_name: str,
        rel: str,
    ) -> _ClassRecord:
        qn = f"{module_name}.{node.name}" if module_name else node.name
        bases = tuple(_expr_name(b) for b in node.bases if _expr_name(b))
        decorators = tuple(_expr_name(d) for d in node.decorator_list if _expr_name(d))
        methods: list[str] = []
        attributes: list[str] = []

        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(child.name)
                self._index_function(
                    index,
                    child,
                    module_name,
                    rel,
                    class_name=node.name,
                )
            elif isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        attributes.append(target.id)
            elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                attributes.append(child.target.id)

        record = _ClassRecord(
            name=node.name,
            qualified_name=qn,
            module=module_name,
            file_path=rel,
            line=getattr(node, "lineno", 0) or 0,
            docstring=_first_line(ast.get_docstring(node) or ""),
            bases=bases,
            methods=tuple(methods),
            decorators=decorators,
            attributes=tuple(dict.fromkeys(attributes)),
            end_line=getattr(node, "end_lineno", None) or getattr(node, "lineno", 0) or 0,
        )
        index.classes.setdefault(node.name, []).append(record)
        index.classes.setdefault(qn, []).append(record)
        index.defined.add(qn)
        index.defined.add(node.name)
        return record

    def _index_function(
        self,
        index: _CodeIndex,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        module_name: str,
        rel: str,
        *,
        class_name: str,
    ) -> _FunctionRecord:
        if class_name:
            qn = f"{module_name}.{class_name}.{node.name}" if module_name else f"{class_name}.{node.name}"
            short_qn = f"{class_name}.{node.name}"
        else:
            qn = f"{module_name}.{node.name}" if module_name else node.name
            short_qn = node.name

        params = _function_params(node)
        returns = _annotation_str(node.returns) if node.returns is not None else ""
        decorators = tuple(_expr_name(d) for d in node.decorator_list if _expr_name(d))
        calls = self._collect_calls(node)
        signature = _format_signature(node.name, params, returns)
        is_property = any(d in {"property", "cached_property"} for d in decorators)
        body_lines = max(
            0,
            (getattr(node, "end_lineno", None) or node.lineno) - node.lineno,
        )

        record = _FunctionRecord(
            name=node.name,
            qualified_name=qn,
            module=module_name,
            file_path=rel,
            line=getattr(node, "lineno", 0) or 0,
            signature=signature,
            docstring=_first_line(ast.get_docstring(node) or ""),
            parameters=params,
            returns=returns,
            decorators=decorators,
            is_method=bool(class_name),
            class_name=class_name,
            calls=calls,
            end_line=getattr(node, "end_lineno", None) or getattr(node, "lineno", 0) or 0,
            is_private=node.name.startswith("_") and not node.name.startswith("__"),
            is_dunder=node.name.startswith("__") and node.name.endswith("__"),
            is_property=is_property,
            body_lines=body_lines,
        )

        for key in {node.name, qn, short_qn}:
            index.functions.setdefault(key, []).append(record)
        index.defined.add(qn)
        index.defined.add(short_qn)
        index.defined.add(node.name)

        # Call edges
        index.callees_of.setdefault(qn, set()).update(calls)
        index.callees_of.setdefault(short_qn, set()).update(calls)
        for callee in calls:
            index.callers_of.setdefault(callee, set()).add(qn)
            leaf = callee.rsplit(".", 1)[-1]
            index.callers_of.setdefault(leaf, set()).add(qn)
            index.references.setdefault(leaf, set()).add(qn)
            index.references.setdefault(callee, set()).add(qn)

        return record

    def _collect_imports(self, tree: ast.AST) -> list[str]:
        found: list[str] = []
        for node in tree.body if isinstance(tree, ast.Module) else []:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    if alias.name == "*":
                        found.append(f"{module}.*" if module else "*")
                    elif module:
                        found.append(f"{module}.{alias.name}")
                    else:
                        found.append(alias.name)
        return list(dict.fromkeys(found))

    def _collect_calls(self, node: ast.AST) -> tuple[str, ...]:
        calls: list[str] = []
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            name = _expr_name(child.func)
            if not name or name in _BUILTIN_OR_COMMON:
                continue
            # Skip self./cls. prefix noise but keep method leaf + qualified
            if name.startswith("self.") or name.startswith("cls."):
                leaf = name.split(".", 1)[1]
                calls.append(leaf)
                calls.append(name)
            else:
                calls.append(name)
        # Preserve order, unique
        return tuple(dict.fromkeys(calls))

    # --- Resolution helpers -------------------------------------------------

    def _resolve_function(
        self,
        index: _CodeIndex,
        query: str,
    ) -> _FunctionRecord | None:
        short, qualified = self._split_symbol_query(query)
        candidates = list(index.functions.get(qualified, []))
        if not candidates:
            candidates = list(index.functions.get(short, []))
        if not candidates and "." in query:
            # Brain.think → match short_qn
            candidates = list(index.functions.get(query.replace("/", "."), []))
        if not candidates:
            # Case-insensitive / suffix match
            lowered = query.lower().replace("/", ".")
            for key, records in index.functions.items():
                if key.lower() == lowered or key.lower().endswith(f".{short.lower()}"):
                    candidates.extend(records)
        if not candidates:
            return None
        # Prefer exact qualified match, then shorter path
        candidates.sort(
            key=lambda r: (
                0 if r.qualified_name.lower() == qualified.lower() else 1,
                0 if f"{r.class_name}.{r.name}" == query else 1,
                len(r.file_path),
                r.line,
            )
        )
        return candidates[0]

    def _resolve_class(
        self,
        index: _CodeIndex,
        query: str,
    ) -> _ClassRecord | None:
        short, qualified = self._split_symbol_query(query)
        # Strip trailing () if user wrote ClassName()
        short = short.rstrip("()")
        qualified = qualified.rstrip("()")
        candidates = list(index.classes.get(qualified, []))
        if not candidates:
            candidates = list(index.classes.get(short, []))
        if not candidates:
            lowered = short.lower()
            for key, records in index.classes.items():
                if key.lower() == lowered or key.lower().endswith(f".{lowered}"):
                    candidates.extend(records)
        if not candidates:
            return None
        candidates.sort(
            key=lambda r: (
                0 if r.name.lower() == short.lower() else 1,
                len(r.file_path),
                r.line,
            )
        )
        return candidates[0]

    def _resolve_module(
        self,
        index: _CodeIndex,
        query: str,
    ) -> _ModuleRecord | None:
        cleaned = query.strip().replace("\\", "/")
        if cleaned in index.modules:
            return index.modules[cleaned]
        if cleaned.endswith(".py") and cleaned in index.modules:
            return index.modules[cleaned]
        # Accept package.module or package/module.py
        dotted = cleaned.replace("/", ".")
        if dotted.endswith(".py"):
            dotted = dotted[:-3]
        if dotted in index.modules:
            return index.modules[dotted]
        # Suffix match on file path
        needle = cleaned if cleaned.endswith(".py") else f"{cleaned.replace('.', '/')}.py"
        for path, record in index.modules.items():
            if "/" in path and (path == needle or path.endswith(f"/{needle}") or path.endswith(needle)):
                return record
            if path.replace("\\", "/") == needle:
                return record
        # Stem match (project_intelligence.py)
        stem = Path(cleaned).stem
        if stem in index.modules:
            return index.modules[stem]
        for path, record in index.modules.items():
            if Path(path).name == f"{stem}.py" or Path(path).stem == stem:
                return record
        return None

    @staticmethod
    def _split_symbol_query(query: str) -> tuple[str, str]:
        text = (query or "").strip().replace("\\", "/")
        text = text.rstrip("()")
        # Drop module path prefixes like brain/brain.py::think
        if "::" in text:
            text = text.split("::", 1)[1]
        text = text.replace("/", ".")
        if text.endswith(".py"):
            text = text[:-3]
        parts = [p for p in text.split(".") if p]
        if not parts:
            return "", ""
        short = parts[-1]
        qualified = ".".join(parts)
        return short, qualified

    @staticmethod
    def _name_matches(
        name: str,
        qualified_name: str,
        short: str,
        qualified: str,
    ) -> bool:
        if not short:
            return False
        if name == short or qualified_name == qualified:
            return True
        if qualified_name.endswith(f".{short}"):
            return True
        if name.lower() == short.lower():
            return True
        return False

    def _iter_functions(self, index: _CodeIndex) -> Iterable[_FunctionRecord]:
        seen: set[tuple[str, int]] = set()
        for records in index.functions.values():
            for record in records:
                key = (record.file_path, record.line)
                if key in seen:
                    continue
                seen.add(key)
                yield record

    def _iter_classes(self, index: _CodeIndex) -> Iterable[_ClassRecord]:
        seen: set[tuple[str, int]] = set()
        for records in index.classes.values():
            for record in records:
                key = (record.file_path, record.line)
                if key in seen:
                    continue
                seen.add(key)
                yield record

    def _caller_names(self, index: _CodeIndex, record: _FunctionRecord) -> list[str]:
        keys = {record.name, record.qualified_name}
        if record.class_name:
            keys.add(f"{record.class_name}.{record.name}")
        callers: set[str] = set()
        for key in keys:
            callers.update(index.callers_of.get(key, set()))
        callers.discard(record.qualified_name)
        return sorted(callers)

    def _location_for_qualified(
        self,
        index: _CodeIndex,
        qualified: str,
    ) -> SymbolLocation | None:
        for record in index.functions.get(qualified, []):
            return SymbolLocation(
                name=record.name,
                kind="method" if record.is_method else "function",
                module=record.module,
                file_path=record.file_path,
                line=record.line,
                qualified_name=record.qualified_name,
                context=record.signature,
            )
        # Search all functions for exact qn
        for record in self._iter_functions(index):
            if record.qualified_name == qualified:
                return SymbolLocation(
                    name=record.name,
                    kind="method" if record.is_method else "function",
                    module=record.module,
                    file_path=record.file_path,
                    line=record.line,
                    qualified_name=record.qualified_name,
                    context=record.signature,
                )
        return None

    # --- Purpose / impact text ----------------------------------------------

    def _explain_function_purpose(self, record: _FunctionRecord) -> str:
        if record.docstring:
            base = record.docstring
        else:
            kind = "Method" if record.is_method else "Function"
            owner = f" on {record.class_name}" if record.class_name else ""
            base = f"{kind} « {record.name} »{owner} in {record.file_path}."

        bits: list[str] = [base]
        if record.parameters:
            params = [p for p in record.parameters if p not in {"self", "cls"}]
            if params:
                bits.append(f"Parameters: {', '.join(params)}.")
        if record.returns:
            bits.append(f"Annotated return: {record.returns}.")
        if record.calls:
            bits.append(f"Calls: {', '.join(record.calls[:6])}.")
        if record.decorators:
            bits.append(f"Decorators: {', '.join(record.decorators)}.")
        return " ".join(bits)

    def _explain_class_purpose(
        self,
        record: _ClassRecord,
        method_summaries: list[str],
    ) -> str:
        if record.docstring:
            base = record.docstring
        else:
            base = f"Class « {record.name} » defined in {record.file_path}."
        bits = [base]
        if record.bases:
            bits.append(f"Inherits from: {', '.join(record.bases)}.")
        if record.methods:
            bits.append(f"Methods ({len(record.methods)}): {', '.join(record.methods[:8])}.")
        if method_summaries:
            bits.append("Key methods: " + "; ".join(method_summaries[:3]) + ".")
        return " ".join(bits)

    def _method_purpose_lines(
        self,
        index: _CodeIndex,
        record: _ClassRecord,
    ) -> list[str]:
        lines: list[str] = []
        for method_name in record.methods[:_METHOD_SAMPLE]:
            key = f"{record.qualified_name}.{method_name}"
            alt = f"{record.name}.{method_name}"
            func = None
            for candidate_key in (key, alt, method_name):
                matches = index.functions.get(candidate_key, [])
                for match in matches:
                    if match.class_name == record.name and match.file_path == record.file_path:
                        func = match
                        break
                if func is not None:
                    break
            if func is None:
                lines.append(method_name)
            elif func.docstring:
                lines.append(f"{method_name}: {func.docstring}")
            else:
                lines.append(f"{method_name}{func.signature[len(method_name):]}")
        return lines

    def _module_purpose(self, record: _ModuleRecord) -> str:
        if record.docstring:
            base = record.docstring
        else:
            base = f"Python module « {record.name} » at {record.file_path}."
        bits = [base]
        if record.classes:
            bits.append(f"Defines classes: {', '.join(record.classes[:8])}.")
        if record.functions:
            bits.append(f"Defines functions: {', '.join(record.functions[:8])}.")
        if record.imports:
            bits.append(f"Imports: {', '.join(record.imports[:8])}.")
        if record.inheritance:
            bits.append(f"Inheritance: {', '.join(record.inheritance[:5])}.")
        return " ".join(bits)

    @staticmethod
    def _complexity_hint(record: _FunctionRecord) -> str:
        if record.body_lines >= 80 or len(record.calls) >= 15:
            return "high"
        if record.body_lines >= 35 or len(record.calls) >= 8:
            return "medium"
        return "low"

    @staticmethod
    def _impact_from_caller_count(caller_count: int, is_private: bool) -> str:
        if caller_count >= 8:
            return "high"
        if caller_count >= 3:
            return "medium"
        if caller_count >= 1:
            return "low"
        return "low" if is_private else "unknown"

    def _memory_hints(self, query: str) -> tuple[str, ...]:
        if self._memory_service is None:
            return ()
        user = "Nolan"
        if self._context_manager is not None:
            user = self._context_manager.current_user or user
        project_id = None
        if self._context_manager is not None:
            project_id = self._context_manager.active_project or None
        try:
            retrieval = self._memory_service.retrieve(user, query, project_id=project_id)
        except Exception:
            logger.exception("Code intelligence memory retrieval failed")
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

    def _mission_context(self) -> str:
        if self._executive_function is not None:
            focus = self._executive_function.get_current_focus()
            if focus is not None:
                return f"{focus.title} [{focus.state.value}]"
        if self._mission_manager is not None:
            active = self._mission_manager.runtime.list_active_missions()
            if active:
                first = active[0]
                return f"{first.title} [{first.state.value}]"
        return ""


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _expr_name(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _expr_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _expr_name(node.func)
    if isinstance(node, ast.Subscript):
        return _expr_name(node.value)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def _annotation_str(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return _expr_name(node) or "Any"


def _function_params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    args = node.args
    names: list[str] = []
    for arg in args.posonlyargs:
        names.append(arg.arg)
    for arg in args.args:
        names.append(arg.arg)
    if args.vararg is not None:
        names.append(f"*{args.vararg.arg}")
    for arg in args.kwonlyargs:
        names.append(arg.arg)
    if args.kwarg is not None:
        names.append(f"**{args.kwarg.arg}")
    return tuple(names)


def _format_signature(name: str, params: tuple[str, ...], returns: str) -> str:
    inner = ", ".join(params)
    if returns:
        return f"{name}({inner}) -> {returns}"
    return f"{name}({inner})"


def _first_line(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    return cleaned.splitlines()[0].strip()


def _module_name_from_path(rel: str) -> str:
    path = rel.replace("\\", "/")
    if path.endswith(".py"):
        path = path[:-3]
    if path.endswith("/__init__"):
        path = path[: -len("/__init__")]
    return path.replace("/", ".")


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
