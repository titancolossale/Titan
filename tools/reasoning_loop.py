# =====================================
# Titan Reasoning Loop
# =====================================

"""Critical plan review and safe optimization before tool orchestration (Phase 12.6 Batch 3 — P126-021)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from tools.decision.models import ToolDecisionReport
from tools.natural_language_planner import compute_execution_order
from tools.permission_manager import (
    PermissionLevel,
    PermissionManager,
    resolve_tool_action,
)
from tools.planner_models import (
    ExecutionPlan,
    PlannerResult,
    PlanStep,
    PlanStepKind,
    ReviewedPlannerResult,
)
from tools.tool_result import ToolResult

_CREATE_ACTIONS = frozenset({"create_note", "create_folder"})
_SEARCH_ACTIONS = frozenset({
    "search_files",
    "search_notes",
    "search",
})
_PARAM_KEYS_BY_ACTION: dict[str, tuple[str, ...]] = {
    "read_file": ("path",),
    "write_file": ("path",),
    "read_note": ("note", "path", "title", "name"),
    "update_note": ("note", "path", "title", "name"),
    "patch_note": ("note", "path", "title", "name"),
    "delete_note": ("note", "path", "title", "name"),
    "delete_file": ("path",),
    "search_files": ("keyword", "query", "pattern"),
    "search_notes": ("query", "keyword", "tag", "folder", "filename"),
    "search": ("query", "keyword"),
}


def reasoning_clarification_tool_result(reviewed: ReviewedPlannerResult) -> ToolResult:
    """Surface ReasoningLoop clarification to the user-facing execution flow."""
    message = reviewed.clarification_message or reviewed.reasoning_summary
    return ToolResult(
        tool_name="reasoning_loop",
        success=False,
        error=f"[Raisonnement] Clarification requise — {message}",
        source="reasoning_loop",
        metadata={
            "clarification_required": True,
            "confidence_score": reviewed.confidence_score,
            "reasoning_summary": reviewed.reasoning_summary,
            "reviewed_planner_result": reviewed.to_dict(),
        },
    )


@dataclass
class ReasoningLoop:
    """Review and improve structured plans before orchestration."""

    permission_manager: PermissionManager = field(default_factory=PermissionManager)

    def review(
        self,
        planner_result: PlannerResult,
        *,
        message: str = "",
        decision_report: ToolDecisionReport | None = None,
        analysis: dict[str, Any] | None = None,
    ) -> ReviewedPlannerResult:
        """Critically review a planner result and apply safe improvements."""
        analysis = analysis or {}
        issues: list[str] = []
        optimizations = 0
        clarification_messages: list[str] = []

        if analysis.get("needs_clarification"):
            return ReviewedPlannerResult.from_planner_result(
                planner_result,
                confidence_score=0.2,
                reasoning_summary="Clarification requise avant exécution du plan.",
                clarification_required=True,
                clarification_message=(
                    "Informations insuffisantes pour construire un plan fiable."
                ),
                review_issues=("needs_clarification",),
            )

        if planner_result.total_steps == 0:
            return ReviewedPlannerResult.from_planner_result(
                planner_result,
                confidence_score=0.9,
                reasoning_summary=planner_result.plan_summary or "Plan vide — aucune action.",
            )

        steps = list(planner_result.steps)
        step_ids = {step.step_id for step in steps}

        steps, removed_redundant = self._remove_redundant_steps(steps)
        if removed_redundant:
            optimizations += removed_redundant
            issues.append(f"{removed_redundant} étape(s) redondante(s) supprimée(s).")

        steps, fixed_deps = self._fix_dependency_consistency(steps, step_ids)
        if fixed_deps:
            optimizations += fixed_deps
            issues.append("Dépendances invalides corrigées.")

        steps, perm_fixes = self._sync_permissions(
            steps,
            decision_report=decision_report,
        )
        if perm_fixes:
            optimizations += perm_fixes
            issues.append("Permissions des étapes resynchronisées.")

        missing_param_messages = self._check_missing_params(steps)
        clarification_messages.extend(missing_param_messages)

        blocked_messages = self._check_blocked_steps(steps)
        clarification_messages.extend(blocked_messages)

        steps, added_search = self._insert_search_before_create(steps, message)
        if added_search:
            optimizations += 1
            issues.append("Étape de recherche ajoutée avant création Obsidian.")

        computed_order = compute_execution_order(tuple(steps))
        current_order = tuple(step.step_id for step in steps)
        if computed_order != current_order:
            optimizations += 1
            issues.append("Ordre d'exécution recalculé selon les dépendances.")

        requires_confirmation = any(
            step.required_permission == PermissionLevel.CONFIRMATION_REQUIRED
            for step in steps
        ) or planner_result.requires_confirmation

        improved_plan = ExecutionPlan(
            overall_goal=planner_result.overall_goal,
            plan_summary=self._build_plan_summary(planner_result.plan_summary, issues),
            steps=tuple(steps),
            execution_order=computed_order,
        )
        improved_result = PlannerResult.from_execution_plan(
            improved_plan,
            requires_confirmation=requires_confirmation,
        )

        clarification_required = bool(clarification_messages)
        clarification_message = "; ".join(clarification_messages)
        confidence = self._compute_confidence(
            step_count=improved_result.total_steps,
            issue_count=len(issues),
            clarification_required=clarification_required,
            blocked_count=len(blocked_messages),
        )
        reasoning_summary = self._build_reasoning_summary(
            optimizations=optimizations,
            issues=issues,
            clarification_required=clarification_required,
            clarification_message=clarification_message,
        )

        return ReviewedPlannerResult(
            planner_result=improved_result,
            confidence_score=confidence,
            reasoning_summary=reasoning_summary,
            clarification_required=clarification_required,
            optimization_count=optimizations,
            clarification_message=clarification_message,
            review_issues=tuple(issues),
        )

    @staticmethod
    def _step_signature(step: PlanStep) -> tuple[str, str, tuple[tuple[str, Any], ...]]:
        """Hashable signature for duplicate detection."""
        params = tuple(sorted((step.tool_params or {}).items()))
        action = str((step.tool_params or {}).get("action", ""))
        return step.required_tool, action, params

    def _remove_redundant_steps(self, steps: list[PlanStep]) -> tuple[list[PlanStep], int]:
        """Remove duplicate standard steps with identical tool and params."""
        seen: set[tuple[str, str, tuple[tuple[str, Any], ...]]] = set()
        kept: list[PlanStep] = []
        removed = 0

        for step in steps:
            if step.step_kind != PlanStepKind.STANDARD:
                kept.append(step)
                continue
            signature = self._step_signature(step)
            if signature in seen:
                removed += 1
                continue
            seen.add(signature)
            kept.append(step)
        return kept, removed

    @staticmethod
    def _fix_dependency_consistency(
        steps: list[PlanStep],
        original_step_ids: set[str],
    ) -> tuple[list[PlanStep], int]:
        """Drop references to unknown dependencies; keep valid ones."""
        valid_ids = {step.step_id for step in steps}
        fixed_steps: list[PlanStep] = []
        fixes = 0

        for step in steps:
            cleaned = tuple(dep for dep in step.dependencies if dep in valid_ids)
            if cleaned != step.dependencies:
                fixes += 1
                step = replace(step, dependencies=cleaned)
            if step.fallback_step_id and step.fallback_step_id not in valid_ids:
                fixes += 1
                step = replace(step, fallback_step_id=None)
            fixed_steps.append(step)

        _ = original_step_ids
        return fixed_steps, fixes

    def _sync_permissions(
        self,
        steps: list[PlanStep],
        *,
        decision_report: ToolDecisionReport | None,
    ) -> tuple[list[PlanStep], int]:
        """Re-evaluate permissions and align step metadata when drift is detected."""
        synced: list[PlanStep] = []
        fixes = 0

        for step in steps:
            action = resolve_tool_action(
                step.required_tool,
                step.tool_params,
                decision_report,
            )
            evaluated = self.permission_manager.evaluate(
                step.required_tool,
                action,
                step.tool_params,
                decision_report=decision_report,
            )
            if evaluated.level != step.required_permission:
                fixes += 1
                step = replace(
                    step,
                    required_permission=evaluated.level,
                    selected_action=action,
                )
            synced.append(step)
        return synced, fixes

    @staticmethod
    def _action_for_step(step: PlanStep) -> str:
        return str((step.tool_params or {}).get("action", "")).strip()

    @staticmethod
    def _has_required_param(params: dict[str, Any], keys: tuple[str, ...]) -> bool:
        for key in keys:
            value = params.get(key)
            if value is None:
                continue
            if isinstance(value, str) and value.strip():
                return True
            if value not in ("", None):
                return True
        return False

    def _check_missing_params(self, steps: list[PlanStep]) -> list[str]:
        """Return clarification messages for steps missing required parameters."""
        messages: list[str] = []

        for step in steps:
            if step.step_kind == PlanStepKind.FALLBACK:
                continue
            action = self._action_for_step(step) or step.selected_action or ""
            if not action:
                if step.required_tool in {"file_read", "file_write"}:
                    action = "read_file" if step.required_tool == "file_read" else "write_file"
                else:
                    continue

            required_keys = _PARAM_KEYS_BY_ACTION.get(action)
            if required_keys is None:
                continue
            if self._has_required_param(step.tool_params, required_keys):
                continue

            messages.append(
                f"Étape « {step.step_id} » ({action}) : paramètre requis manquant "
                f"({', '.join(required_keys)}).",
            )
        return messages

    @staticmethod
    def _check_blocked_steps(steps: list[PlanStep]) -> list[str]:
        """Flag steps that cannot execute without user intervention."""
        messages: list[str] = []
        for step in steps:
            if step.required_permission == PermissionLevel.BLOCKED:
                action = str((step.tool_params or {}).get("action", step.required_tool))
                messages.append(
                    f"Étape « {step.step_id} » bloquée pour l'action « {action} ».",
                )
        return messages

    @staticmethod
    def _extract_create_search_query(step: PlanStep, message: str) -> str:
        """Extract a search query from create params or message — never invent."""
        params = step.tool_params or {}
        for key in ("title", "name", "note", "path", "query", "keyword"):
            value = params.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        stripped = message.strip()
        return stripped if stripped else ""

    def _insert_search_before_create(
        self,
        steps: list[PlanStep],
        message: str,
    ) -> tuple[list[PlanStep], bool]:
        """Add search_notes before Obsidian create when query is known (safe policy)."""
        has_search = any(
            self._action_for_step(step) in _SEARCH_ACTIONS
            or step.required_tool == "obsidian"
            and self._action_for_step(step) == "search_notes"
            for step in steps
        )
        if has_search:
            return steps, False

        create_indices = [
            index
            for index, step in enumerate(steps)
            if self._action_for_step(step) in _CREATE_ACTIONS
            or (
                step.required_tool == "obsidian"
                and self._action_for_step(step) in _CREATE_ACTIONS
            )
        ]
        if not create_indices:
            return steps, False

        first_create = steps[create_indices[0]]
        query = self._extract_create_search_query(first_create, message)
        if not query:
            return steps, False

        search_id = "reasoning_search_before_create"
        existing_ids = {step.step_id for step in steps}
        suffix = 1
        while search_id in existing_ids:
            suffix += 1
            search_id = f"reasoning_search_before_create_{suffix}"

        search_step = PlanStep(
            step_id=search_id,
            objective="Rechercher une note existante avant création",
            reasoning="Politique Obsidian : rechercher avant de créer.",
            required_tool="obsidian",
            required_permission=PermissionLevel.AUTO_ALLOWED,
            expected_output="Résultats de recherche de notes",
            tool_params={"action": "search_notes", "query": query, "mode": "keyword"},
            selected_action="search_notes",
        )

        updated_steps: list[PlanStep] = []
        inserted = False
        for index, step in enumerate(steps):
            if index == create_indices[0] and not inserted:
                updated_steps.append(search_step)
                inserted = True
            if self._action_for_step(step) in _CREATE_ACTIONS or (
                step.required_tool == "obsidian"
                and self._action_for_step(step) in _CREATE_ACTIONS
            ):
                new_deps = tuple(dict.fromkeys((*step.dependencies, search_id)))
                step = replace(step, dependencies=new_deps)
            updated_steps.append(step)

        return updated_steps, inserted

    @staticmethod
    def _build_plan_summary(original: str, issues: list[str]) -> str:
        if not issues:
            return original
        return f"{original} (revu : {len(issues)} ajustement(s))."

    @staticmethod
    def _compute_confidence(
        *,
        step_count: int,
        issue_count: int,
        clarification_required: bool,
        blocked_count: int,
    ) -> float:
        score = 1.0
        if clarification_required:
            score -= 0.5
        score -= min(0.3, issue_count * 0.05)
        score -= min(0.3, blocked_count * 0.15)
        if step_count == 0:
            score = min(score, 0.4)
        return max(0.0, min(1.0, round(score, 2)))

    @staticmethod
    def _build_reasoning_summary(
        *,
        optimizations: int,
        issues: list[str],
        clarification_required: bool,
        clarification_message: str,
    ) -> str:
        if clarification_required:
            return (
                f"Plan revu — clarification requise : {clarification_message}"
            )
        if optimizations == 0 and not issues:
            return "Plan validé : ordre, outils, dépendances et permissions cohérents."
        parts = [f"Plan optimisé ({optimizations} amélioration(s))."]
        if issues:
            parts.append(" ".join(issues))
        return " ".join(parts)
