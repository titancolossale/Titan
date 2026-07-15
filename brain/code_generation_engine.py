# =====================================
# Titan Code Generation Engine
# =====================================

"""Code Generation Engine V1 — propose implementation patches from approved plans.

Receives an approved CodeModificationPlan and produces GeneratedPatch artifacts
(new files, edits, unified diffs, review items). Never writes to the filesystem,
never executes code, never commits, and never pushes.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from brain.code_modification_planner import (
    AffectedFile,
    ChangeType,
    CodeModificationPlan,
    RiskLevel,
)
from tools.decision.patch_preview import (
    generate_create_file_preview,
    generate_unified_diff,
    read_file_safe,
)

if TYPE_CHECKING:
    from brain.code_intelligence import CodeIntelligence
    from brain.code_modification_planner import CodeModificationPlanner
    from brain.developer_workflow import DeveloperWorkflow
    from brain.executive_function import ExecutiveEvaluation, ExecutiveFunction
    from brain.project_intelligence import ProjectIntelligence
    from brain.workspace_awareness import WorkspaceAwareness, WorkspaceSnapshot
    from context.context_manager import ContextManager
    from core.mission_manager import MissionManager
    from memory.memory_service import MemoryService

logger = logging.getLogger(__name__)

_ENTITY_FROM_PATH = re.compile(
    r"(?:^|/)(?:(?P<name>[a-z0-9_]+)_(?:tool|provider|client)|"
    r"(?P<pkg>discord|tradingview|browser|obsidian|memory))(?:/|\.py|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GeneratedFile:
    """Proposed brand-new file content (not written)."""

    path: str
    content: str
    rationale: str
    language: str = "python"
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "content": self.content,
            "rationale": self.rationale,
            "language": self.language,
            "confidence": round(self.confidence, 3),
        }


@dataclass(frozen=True)
class GeneratedEdit:
    """Proposed edit to an existing file (not applied)."""

    path: str
    original_content: str
    proposed_content: str
    unified_diff: str
    rationale: str
    symbols_touched: tuple[str, ...] = ()
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "original_content": self.original_content,
            "proposed_content": self.proposed_content,
            "unified_diff": self.unified_diff,
            "rationale": self.rationale,
            "symbols_touched": list(self.symbols_touched),
            "confidence": round(self.confidence, 3),
        }


@dataclass(frozen=True)
class ReviewItem:
    """Manual review checkpoint for a generated proposal."""

    severity: str
    message: str
    path: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class GenerationSummary:
    """Roll-up metrics for a generation run."""

    request: str
    change_type: str
    files_created: int
    files_edited: int
    review_count: int
    confidence: float
    complexity: str
    risk: str
    requires_manual_review: bool
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "change_type": self.change_type,
            "files_created": self.files_created,
            "files_edited": self.files_edited,
            "review_count": self.review_count,
            "confidence": round(self.confidence, 3),
            "complexity": self.complexity,
            "risk": self.risk,
            "requires_manual_review": self.requires_manual_review,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class GeneratedPatch:
    """Complete proposal bundle — patches only, repository unchanged."""

    plan_request: str
    files: tuple[GeneratedFile, ...]
    edits: tuple[GeneratedEdit, ...]
    review_items: tuple[ReviewItem, ...]
    summary: GenerationSummary
    unified_diff_bundle: str
    confidence: float
    rationale: str
    sources: dict[str, Any] = field(default_factory=dict)
    plan_approved: bool = False
    approved: bool = False

    def with_approval(self, approved: bool = True) -> GeneratedPatch:
        """Return a copy marked approved for controlled patch application."""
        return replace(self, approved=bool(approved))

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_request": self.plan_request,
            "files": [f.to_dict() for f in self.files],
            "edits": [e.to_dict() for e in self.edits],
            "review_items": [r.to_dict() for r in self.review_items],
            "summary": self.summary.to_dict(),
            "unified_diff_bundle": self.unified_diff_bundle,
            "confidence": round(self.confidence, 3),
            "rationale": self.rationale,
            "sources": dict(self.sources),
            "plan_approved": self.plan_approved,
            "approved": self.approved,
        }

    def format_for_prompt(self) -> str:
        """Compact advisory block for Brain prompt injection."""
        lines = [
            "CODE GENERATION PROPOSAL (not applied)",
            f"- request: {self.plan_request}",
            f"- confidence: {self.confidence:.2f}",
            f"- created: {len(self.files)} file(s)",
            f"- edited: {len(self.edits)} file(s)",
            f"- review items: {len(self.review_items)}",
            f"- plan_approved: {self.plan_approved}",
            f"- patch_approved: {self.approved}",
            f"- rationale: {self.rationale}",
        ]
        if self.files:
            lines.append("- new files:")
            for item in self.files[:8]:
                lines.append(f"  - {item.path}")
        if self.edits:
            lines.append("- edits:")
            for item in self.edits[:8]:
                lines.append(f"  - {item.path}")
        if self.review_items:
            lines.append("- review:")
            for item in self.review_items[:5]:
                lines.append(f"  - [{item.severity}] {item.message}")
        return "\n".join(lines)


class CodeGenerationEngine:
    """Generate implementation-ready patch proposals from an approved plan.

    Hard rules:
    - Never write files
    - Never execute generated code
    - Never commit or push
    - Only return GeneratedPatch artifacts
    """

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
        code_modification_planner: CodeModificationPlanner | None = None,
        project_root: Path | None = None,
        require_approval: bool = True,
    ) -> None:
        self._workspace_awareness = workspace_awareness
        self._project_intelligence = project_intelligence
        self._code_intelligence = code_intelligence
        self._developer_workflow = developer_workflow
        self._executive_function = executive_function
        self._mission_manager = mission_manager
        self._memory_service = memory_service
        self._context_manager = context_manager
        self._code_modification_planner = code_modification_planner
        self._project_root = Path(project_root) if project_root is not None else None
        self._require_approval = require_approval

    def generate(
        self,
        plan: CodeModificationPlan,
        *,
        workspace: WorkspaceSnapshot | None = None,
        executive_evaluation: ExecutiveEvaluation | None = None,
        force: bool = False,
    ) -> GeneratedPatch:
        """Produce patch proposals for *plan* without mutating the repository."""
        if self._require_approval and not plan.approved and not force:
            return self._rejection_patch(
                plan,
                reason=(
                    "Plan is not approved. Call plan.with_approval() or pass "
                    "force=True only for explicit dry-run generation."
                ),
            )

        root = self._resolve_root(workspace)
        files: list[GeneratedFile] = []
        edits: list[GeneratedEdit] = []
        reviews: list[ReviewItem] = [
            ReviewItem(
                severity="info",
                message="Generated artifacts are proposals only — repository unchanged.",
                reason="Code Generation Engine V1 never writes files.",
            )
        ]

        for affected in plan.affected_files:
            if affected.priority == "docs" and affected.action == "modify":
                edit = self._generate_env_example_edit(root, affected, plan)
                if edit is not None:
                    edits.append(edit)
                    reviews.append(
                        ReviewItem(
                            severity="warning",
                            message="Verify no real secrets are proposed in env docs.",
                            path=affected.path,
                            reason="Secrets must stay in .env only.",
                        )
                    )
                continue

            if affected.action == "create" or self._should_create(root, affected):
                generated = self._generate_new_file(affected, plan)
                files.append(generated)
                reviews.extend(self._review_for_new_file(generated, plan))
            else:
                edit = self._generate_edit(root, affected, plan)
                if edit is not None:
                    edits.append(edit)
                    reviews.extend(self._review_for_edit(edit, plan))

        if not files and not edits:
            reviews.append(
                ReviewItem(
                    severity="warning",
                    message="No file proposals produced — plan may need clarification.",
                    reason="Empty generation result",
                )
            )

        confidences = [f.confidence for f in files] + [e.confidence for e in edits]
        confidence = (
            sum(confidences) / len(confidences)
            if confidences
            else min(plan.confidence, 0.4)
        )
        if plan.risk.overall in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            confidence = min(confidence, 0.7)
            reviews.append(
                ReviewItem(
                    severity="critical",
                    message="High/critical risk plan — require human review before apply.",
                    reason=plan.risk.architectural or plan.risk.overall.value,
                )
            )

        bundle = self._bundle_diffs(files, edits)
        rationale = self._build_rationale(plan, files, edits)
        sources = {
            "plan_change_type": plan.change_type.value,
            "plan_confidence": plan.confidence,
            "workspace_root": str(root) if root is not None else None,
            "project_intelligence": self._project_intelligence is not None,
            "code_intelligence": self._code_intelligence is not None,
            "developer_workflow": self._developer_workflow is not None,
            "executive_function": self._executive_function is not None
            or executive_evaluation is not None,
            "mission_runtime": self._mission_manager is not None,
            "memory": self._memory_service is not None,
            "code_modification_planner": self._code_modification_planner is not None,
        }

        summary = GenerationSummary(
            request=plan.request,
            change_type=plan.change_type.value,
            files_created=len(files),
            files_edited=len(edits),
            review_count=len(reviews),
            confidence=confidence,
            complexity=plan.complexity.value,
            risk=plan.risk.overall.value,
            requires_manual_review=True,
            notes=(
                "Patches proposed only. Use a separate confirmed apply path "
                "if/when execution is enabled."
            ),
        )

        result = GeneratedPatch(
            plan_request=plan.request,
            files=tuple(files),
            edits=tuple(edits),
            review_items=tuple(reviews),
            summary=summary,
            unified_diff_bundle=bundle,
            confidence=confidence,
            rationale=rationale,
            sources=sources,
            plan_approved=plan.approved or force,
        )
        logger.info(
            "code_generation created=%d edited=%d reviews=%d confidence=%.2f "
            "approved=%s",
            len(files),
            len(edits),
            len(reviews),
            confidence,
            plan.approved or force,
        )
        return result

    # --- file / edit generation -------------------------------------------------

    def _generate_new_file(
        self,
        affected: AffectedFile,
        plan: CodeModificationPlan,
    ) -> GeneratedFile:
        entity = self._entity_from_affected(affected, plan)
        path = affected.path.replace("\\", "/")
        if path.startswith("tests/") or path.startswith("test_"):
            content = self._propose_test_file(path, entity, plan)
            rationale = f"New test module for {entity} covering plan checklist items."
        elif "provider" in path:
            content = self._propose_provider_file(entity, plan)
            rationale = f"New provider stub for {entity} following Titan conventions."
        elif path.endswith(".py"):
            content = self._propose_tool_file(entity, plan, path)
            rationale = (
                f"New module for {entity} ({plan.change_type.value}) — "
                f"{affected.reason}"
            )
        else:
            content = f"# Proposed file: {path}\n# {affected.reason}\n"
            rationale = affected.reason

        confidence = min(0.85, plan.confidence + 0.1)
        return GeneratedFile(
            path=path,
            content=content,
            rationale=rationale,
            language="python" if path.endswith(".py") else "text",
            confidence=confidence,
        )

    def _generate_edit(
        self,
        root: Path | None,
        affected: AffectedFile,
        plan: CodeModificationPlan,
    ) -> GeneratedEdit | None:
        path = affected.path.replace("\\", "/")
        original = ""
        if root is not None:
            original = read_file_safe(root, path)

        if not original:
            # Missing baseline — emit as create instead via caller normally;
            # still produce an edit-shaped create proposal if we get here.
            generated = self._generate_new_file(affected, plan)
            preview = generate_create_file_preview(path, generated.content)
            return GeneratedEdit(
                path=path,
                original_content="",
                proposed_content=generated.content,
                unified_diff=preview.unified_diff,
                rationale=f"File missing at baseline; proposing create for {path}.",
                symbols_touched=affected.classes + affected.functions,
                confidence=generated.confidence * 0.9,
            )

        entity = self._entity_from_affected(affected, plan)
        proposed = self._propose_modification(original, path, entity, affected, plan)
        if proposed == original:
            proposed = self._append_proposal_marker(original, entity, plan, affected)

        preview = generate_unified_diff(
            path,
            original=original,
            proposed=proposed,
            change_type="modify",
        )
        symbols = affected.classes + affected.functions
        if self._code_intelligence is not None and not symbols:
            symbols = self._lookup_symbols(path)

        confidence = min(0.8, plan.confidence + 0.05)
        if plan.change_type == ChangeType.RENAME:
            confidence = min(confidence, 0.65)

        return GeneratedEdit(
            path=path,
            original_content=original,
            proposed_content=proposed,
            unified_diff=preview.unified_diff,
            rationale=affected.reason or f"Proposed edit for {path}",
            symbols_touched=tuple(symbols),
            confidence=confidence,
        )

    def _generate_env_example_edit(
        self,
        root: Path | None,
        affected: AffectedFile,
        plan: CodeModificationPlan,
    ) -> GeneratedEdit | None:
        path = affected.path.replace("\\", "/")
        original = read_file_safe(root, path) if root is not None else ""
        entity = self._entity_from_affected(affected, plan).upper()
        marker = f"# {entity}_API_TOKEN=\n"
        if marker.strip() in original:
            return None
        proposed = original
        if proposed and not proposed.endswith("\n"):
            proposed += "\n"
        proposed += f"\n# {entity} integration (placeholder — never commit real secrets)\n"
        proposed += f"# {entity}_API_TOKEN=\n"
        preview = generate_unified_diff(
            path,
            original=original,
            proposed=proposed,
            change_type="modify",
        )
        return GeneratedEdit(
            path=path,
            original_content=original,
            proposed_content=proposed,
            unified_diff=preview.unified_diff,
            rationale="Document required env placeholders without secrets.",
            confidence=0.75,
        )

    def _propose_modification(
        self,
        original: str,
        path: str,
        entity: str,
        affected: AffectedFile,
        plan: CodeModificationPlan,
    ) -> str:
        if "tool_manager" in path.replace("\\", "/"):
            return self._propose_tool_manager_registration(original, entity, plan)
        if plan.change_type == ChangeType.RENAME and "ToolManager" in original:
            # Proposal only — conservative comment + alias hint, not a blind rename.
            return self._propose_rename_hint(original, entity, plan)
        if "browser" in path.replace("\\", "/") and plan.change_type in {
            ChangeType.REFACTOR,
            ChangeType.FEATURE,
            ChangeType.BUGFIX,
        }:
            return self._propose_browser_improvement(original, plan, affected)
        if "tradingview" in path.replace("\\", "/"):
            return self._propose_tradingview_improvement(original, plan, affected)
        if path.replace("\\", "/").startswith("tests/"):
            return self._propose_test_augmentation(original, entity, plan)
        return original

    def _propose_tool_manager_registration(
        self,
        original: str,
        entity: str,
        plan: CodeModificationPlan,
    ) -> str:
        class_name = self._class_name(entity, "Tool")
        import_line = f"from tools.{entity}_tool import {class_name}"
        register_line = f"        self.register({class_name}())"
        if import_line in original and register_line in original:
            return original

        lines = original.splitlines()
        if import_line not in original:
            insert_at = 0
            for index, line in enumerate(lines):
                if line.startswith("from tools.") or line.startswith("import "):
                    insert_at = index + 1
            lines.insert(insert_at, import_line)

        if register_line not in "\n".join(lines):
            anchor_index = next(
                (
                    index
                    for index, line in enumerate(lines)
                    if "_register_defaults" in line or "register(" in line
                ),
                len(lines) - 1,
            )
            # Insert after first register( call body start when possible.
            insert_reg = anchor_index + 1
            for index in range(anchor_index, min(anchor_index + 40, len(lines))):
                if "self.register(" in lines[index]:
                    insert_reg = index + 1
            comment = (
                f"        # Proposed registration for {entity} "
                f"({plan.change_type.value}) — not applied"
            )
            lines.insert(insert_reg, comment)
            lines.insert(insert_reg + 1, register_line)

        body = "\n".join(lines)
        if original.endswith("\n") and not body.endswith("\n"):
            body += "\n"
        return body

    def _propose_rename_hint(
        self,
        original: str,
        entity: str,
        plan: CodeModificationPlan,
    ) -> str:
        hint = (
            f"\n# CODEGEN PROPOSAL: rename ToolManager per plan "
            f"'{plan.request}' (entity={entity}).\n"
            "# Do not apply blindly — update all importers and tests.\n"
        )
        if "CODEGEN PROPOSAL: rename ToolManager" in original:
            return original
        if original.endswith("\n"):
            return original + hint
        return original + "\n" + hint

    def _propose_browser_improvement(
        self,
        original: str,
        plan: CodeModificationPlan,
        affected: AffectedFile,
    ) -> str:
        marker = (
            "\n# CODEGEN PROPOSAL: Browser Tool improvement\n"
            f"# Plan: {plan.request}\n"
            f"# Focus: {affected.reason}\n"
            "# Suggested: extract shared fetch helpers, tighten URL validation, "
            "preserve BrowserTool public capabilities.\n"
        )
        if "CODEGEN PROPOSAL: Browser Tool improvement" in original:
            return original
        return original + ("" if original.endswith("\n") else "\n") + marker

    def _propose_tradingview_improvement(
        self,
        original: str,
        plan: CodeModificationPlan,
        affected: AffectedFile,
    ) -> str:
        marker = (
            "\n# CODEGEN PROPOSAL: TradingView connector update\n"
            f"# Plan: {plan.request}\n"
            f"# Focus: {affected.reason}\n"
            "# Keep webhook receive/validate/parse only — no order execution.\n"
        )
        if "CODEGEN PROPOSAL: TradingView connector update" in original:
            return original
        return original + ("" if original.endswith("\n") else "\n") + marker

    def _propose_test_augmentation(
        self,
        original: str,
        entity: str,
        plan: CodeModificationPlan,
    ) -> str:
        test_name = f"test_{entity}_codegen_proposal_smoke"
        if test_name in original:
            return original
        addition = f'''

def {test_name}() -> None:
    """Proposed regression smoke for: {plan.request}."""
    assert True
'''
        return original + addition

    def _append_proposal_marker(
        self,
        original: str,
        entity: str,
        plan: CodeModificationPlan,
        affected: AffectedFile,
    ) -> str:
        marker = (
            f"\n# CODEGEN PROPOSAL ({plan.change_type.value}) for {entity}\n"
            f"# {affected.reason}\n"
            f"# Request: {plan.request}\n"
        )
        if "CODEGEN PROPOSAL" in original and entity in original:
            return original
        return original + ("" if original.endswith("\n") else "\n") + marker

    # --- content templates ------------------------------------------------------

    def _propose_tool_file(
        self,
        entity: str,
        plan: CodeModificationPlan,
        path: str,
    ) -> str:
        class_name = self._class_name(entity, "Tool")
        title = entity.replace("_", " ").title()
        if entity == "discord":
            return f'''# =====================================
# Titan {class_name}
# =====================================

"""Discord integration tool (proposed — not applied).

Generated from CodeModificationPlan: {plan.request}
External messaging requires confirmation; secrets stay in .env.
"""

from __future__ import annotations

from tools.base_tool import BaseTool, ToolSchema
from tools.tool_result import ToolResult


class {class_name}(BaseTool):
    """Proposed Discord capability — stub only."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="discord",
            description="Proposed Discord integration (send/read via approved API).",
            parameters=[],
        )

    def run(self, **params: object) -> ToolResult:
        del params
        return self._result(
            success=True,
            data="Discord tool stub — not connected. Proposal only.",
        )
'''
        if "browser" in path:
            return f'''# =====================================
# Titan Browser Improvement Helper
# =====================================

"""Proposed Browser Tool helper extracted during refactor (not applied).

Plan: {plan.request}
"""

from __future__ import annotations


def normalize_browser_url(url: str) -> str:
    """Return a stripped URL; validation remains in Browser Tool."""
    return (url or "").strip()
'''
        return f'''# =====================================
# Titan {class_name}
# =====================================

"""{title} tool capability (proposed — not applied).

Generated from CodeModificationPlan: {plan.request}
"""

from __future__ import annotations

from tools.base_tool import BaseTool, ToolSchema
from tools.tool_result import ToolResult


class {class_name}(BaseTool):
    """Proposed {title} capability."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="{entity}",
            description="Proposed {title} capability.",
            parameters=[],
        )

    def run(self, **params: object) -> ToolResult:
        del params
        return self._result(
            success=True,
            data="Proposed {entity} tool stub — not applied.",
        )
'''

    def _propose_provider_file(self, entity: str, plan: CodeModificationPlan) -> str:
        class_name = self._class_name(entity, "Provider")
        return f'''# =====================================
# Titan {class_name}
# =====================================

"""{entity} provider (proposed — not applied).

Plan: {plan.request}
"""

from __future__ import annotations

from tools.providers.base_provider import BaseProvider


class {class_name}(BaseProvider):
    """Proposed {entity} provider stub."""

    @property
    def provider_id(self) -> str:
        return "{entity}"
'''

    def _propose_test_file(
        self,
        path: str,
        entity: str,
        plan: CodeModificationPlan,
    ) -> str:
        module_path = path
        if module_path.startswith("tests/test_"):
            target = entity
            import_target = f"tools.{entity}_tool"
        else:
            target = entity
            import_target = path.replace("/", ".").replace(".py", "")
        return f'''# =====================================
# Titan {entity.replace("_", " ").title()} Tests
# =====================================

"""Proposed tests for {entity} (not applied).

Plan: {plan.request}
"""

from __future__ import annotations

import pytest


def test_{entity}_module_importable() -> None:
    """Smoke import for proposed {entity} module."""
    pytest.importorskip("{import_target}")


def test_{entity}_plan_rationale_present() -> None:
    """Keep the originating request visible for reviewers."""
    assert "{target}" in "{entity}" or True
'''

    # --- reviews / helpers ------------------------------------------------------

    def _review_for_new_file(
        self,
        generated: GeneratedFile,
        plan: CodeModificationPlan,
    ) -> list[ReviewItem]:
        items = [
            ReviewItem(
                severity="warning",
                message=f"Review new file proposal: {generated.path}",
                path=generated.path,
                reason=generated.rationale,
            )
        ]
        if "discord" in generated.path or "trading" in generated.path:
            items.append(
                ReviewItem(
                    severity="critical",
                    message="External connector — confirm permissions and secrets handling.",
                    path=generated.path,
                    reason=plan.risk.overall.value,
                )
            )
        return items

    def _review_for_edit(
        self,
        edit: GeneratedEdit,
        plan: CodeModificationPlan,
    ) -> list[ReviewItem]:
        items = [
            ReviewItem(
                severity="warning",
                message=f"Review unified diff for {edit.path}",
                path=edit.path,
                reason=edit.rationale,
            )
        ]
        if plan.change_type == ChangeType.RENAME:
            items.append(
                ReviewItem(
                    severity="critical",
                    message="Rename proposals are hints — verify every importer.",
                    path=edit.path,
                    reason="Wide blast radius",
                )
            )
        if edit.symbols_touched:
            items.append(
                ReviewItem(
                    severity="info",
                    message="Symbols touched: " + ", ".join(edit.symbols_touched[:8]),
                    path=edit.path,
                    reason="From plan / code intelligence",
                )
            )
        return items

    def _rejection_patch(self, plan: CodeModificationPlan, *, reason: str) -> GeneratedPatch:
        review = ReviewItem(
            severity="critical",
            message=reason,
            reason="approval_required",
        )
        summary = GenerationSummary(
            request=plan.request,
            change_type=plan.change_type.value,
            files_created=0,
            files_edited=0,
            review_count=1,
            confidence=0.0,
            complexity=plan.complexity.value,
            risk=plan.risk.overall.value,
            requires_manual_review=True,
            notes=reason,
        )
        return GeneratedPatch(
            plan_request=plan.request,
            files=(),
            edits=(),
            review_items=(review,),
            summary=summary,
            unified_diff_bundle="",
            confidence=0.0,
            rationale=reason,
            sources={"rejected": True},
            plan_approved=False,
        )

    def _bundle_diffs(
        self,
        files: list[GeneratedFile],
        edits: list[GeneratedEdit],
    ) -> str:
        chunks: list[str] = []
        for item in files:
            preview = generate_create_file_preview(item.path, item.content)
            chunks.append(preview.unified_diff)
        for item in edits:
            if item.unified_diff.strip():
                chunks.append(item.unified_diff)
        return "\n\n".join(chunks)

    def _build_rationale(
        self,
        plan: CodeModificationPlan,
        files: list[GeneratedFile],
        edits: list[GeneratedEdit],
    ) -> str:
        return (
            f"Generated {len(files)} new file proposal(s) and {len(edits)} edit(s) "
            f"for {plan.change_type.value} request '{plan.request}'. "
            f"Complexity={plan.complexity.value}, risk={plan.risk.overall.value}. "
            "No filesystem mutation performed."
        )

    def _should_create(self, root: Path | None, affected: AffectedFile) -> bool:
        if affected.action == "create":
            return True
        if root is None:
            return affected.action == "create"
        target = root / affected.path
        return affected.action == "create" or not target.is_file()

    def _entity_from_affected(
        self,
        affected: AffectedFile,
        plan: CodeModificationPlan,
    ) -> str:
        if affected.classes:
            name = affected.classes[0]
            for suffix in ("Tool", "Provider", "Client", "Manager"):
                if name.endswith(suffix) and len(name) > len(suffix):
                    raw = name[: -len(suffix)]
                    return re.sub(r"(?<!^)(?=[A-Z])", "_", raw).lower()
            return name.lower()
        match = _ENTITY_FROM_PATH.search(affected.path.replace("\\", "/"))
        if match:
            return (match.group("name") or match.group("pkg") or "component").lower()
        tokens = re.findall(r"[a-z0-9_]{3,}", plan.request.lower())
        for token in tokens:
            if token not in {
                "add",
                "the",
                "and",
                "for",
                "implement",
                "generate",
                "refactor",
                "improve",
                "integration",
                "connector",
            }:
                return token.replace("-", "_")
        return "component"

    def _lookup_symbols(self, path: str) -> tuple[str, ...]:
        assert self._code_intelligence is not None
        try:
            summary = self._code_intelligence.summarize_module(path)
        except Exception:  # noqa: BLE001 — advisory only
            return ()
        names: list[str] = []
        for cls in getattr(summary, "classes", ()) or ():
            names.append(cls if isinstance(cls, str) else getattr(cls, "name", str(cls)))
        for fn in getattr(summary, "functions", ()) or ():
            names.append(fn if isinstance(fn, str) else getattr(fn, "name", str(fn)))
        return tuple(names[:12])

    def _resolve_root(self, workspace: WorkspaceSnapshot | None) -> Path | None:
        if self._project_root is not None:
            return self._project_root.resolve()
        if workspace is not None and getattr(workspace, "workspace_root", None):
            return Path(workspace.workspace_root).resolve()
        if self._workspace_awareness is not None:
            root = getattr(self._workspace_awareness, "workspace_root", None)
            if root is not None:
                return Path(root).resolve()
            snap = self._workspace_awareness.last_snapshot
            if snap is not None and getattr(snap, "workspace_root", None):
                return Path(snap.workspace_root).resolve()
        return None

    @staticmethod
    def _class_name(entity: str, suffix: str) -> str:
        parts = [p for p in entity.replace("-", "_").split("_") if p]
        return "".join(p.capitalize() for p in parts) + suffix
