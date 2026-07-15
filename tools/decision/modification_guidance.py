# =====================================
# Titan Modification Guidance
# =====================================

"""User-facing modification plan formatting (Phase 11 — P11-306)."""

from __future__ import annotations

from tools.decision.modification_models import ModificationPlan


def format_modification_plan_summary(plan: ModificationPlan) -> str:
    """Format a French user-facing modification plan summary."""
    if plan.ambiguous:
        return (
            "[Plan de modification workspace — clarification requise]\n"
            f"{plan.ambiguity_reason}\n"
            "Aucun fichier ne sera modifié automatiquement."
        )

    modify_lines = [
        f"- {item.path} — {item.reason}"
        for item in plan.files_to_modify
    ]
    create_lines = [
        f"- {item.path} — {item.reason}"
        for item in plan.files_to_create
    ]
    step_lines = [f"{index}. {step}" for index, step in enumerate(plan.implementation_steps, 1)]
    side_effect_lines = [f"- {item}" for item in plan.side_effects]

    blocks = [
        "[Plan de modification workspace — proposition uniquement, aucune écriture]",
        f"Objectif : {plan.objective}",
        "",
        "Je recommande de modifier ces fichiers :",
        *(modify_lines or ["- (aucun)"]),
    ]
    if create_lines:
        blocks.extend(["", "Et de créer ces fichiers :", *create_lines])

    blocks.extend(
        [
            "",
            "Parce que :",
            f"- Type de changement : {plan.modification_type}",
            f"- Confiance estimée : {plan.confidence:.0%}",
            f"- Risque estimé : {plan.estimated_risk.value.upper()}",
        ],
    )

    if side_effect_lines:
        blocks.extend(["", "Effets de bord possibles :", *side_effect_lines])

    blocks.extend(
        [
            "",
            f"Complexité estimée : {plan.estimated_risk.value.upper()} "
            f"({len(plan.affected_files)} fichier(s) concerné(s))",
            "",
            "Plan d'implémentation :",
            *step_lines,
        ],
    )

    if plan.patch_previews:
        blocks.extend(["", "Aperçu de patch proposé :"])
        for preview in plan.patch_previews[:3]:
            blocks.append(f"\n--- {preview.path} ({preview.change_type}) ---")
            snippet = preview.unified_diff.strip()
            if len(snippet) > 1200:
                snippet = snippet[:1200] + "\n... (aperçu tronqué)"
            blocks.append(snippet)

    blocks.append(
        "\nConfirmation requise avant toute application — Titan n'a écrit aucun fichier."
        "\nPour appliquer le patch, répondez exactement : approve, confirm, apply patch, "
        "applique le patch, ou vas-y applique."
    )
    return "\n".join(blocks)


def format_patch_application_summary(result: object) -> str:
    """Format patch application outcome for user-facing output (P12-006)."""
    from tools.decision.patch_models import PatchApplicationResult

    if not isinstance(result, PatchApplicationResult):
        return ""

    if not result.applied:
        error_lines = "\n".join(f"- {item}" for item in result.errors)
        return (
            "[Application de patch — refusée ou échouée]\n"
            f"{error_lines}\n"
            "Aucun changement persistant n'a été laissé en place."
        )

    modified = [f"- {path}" for path in result.files_modified]
    created = [f"- {path}" for path in result.files_created]
    skipped = [f"- {path}" for path in result.files_skipped]
    warning_lines = [f"- {item}" for item in result.warnings]

    blocks = [
        "[Application de patch — confirmée et appliquée]",
        f"Risque : {result.risk_level.value.upper()}",
    ]
    if modified:
        blocks.extend(["", "Fichiers modifiés :", *modified])
    if created:
        blocks.extend(["", "Fichiers créés :", *created])
    if skipped:
        blocks.extend(["", "Fichiers ignorés (inchangés) :", *skipped])
    if warning_lines:
        blocks.extend(["", "Avertissements :", *warning_lines])
    if result.rollback_available:
        if result.rollback_id:
            blocks.append(
                f"\nRollback disponible — id: {result.rollback_id} "
                f"(commandes: undo, rollback, restore patch {result.rollback_id})"
            )
        else:
            blocks.append("\nSauvegarde rollback disponible pour cette session.")
    return "\n".join(blocks)


def format_rollback_summary(result: object, *, target_rollback_id: str = "") -> str:
    """Format rollback restore outcome for user-facing output (P12B2-005)."""
    from tools.decision.rollback_models import RollbackResult

    if not isinstance(result, RollbackResult):
        return ""

    if not result.applied:
        error_lines = "\n".join(f"- {item}" for item in result.errors)
        return (
            "[Rollback — refusé ou échoué]\n"
            f"{error_lines}\n"
            "Aucun changement n'a été restauré."
        )

    restored = [f"- {path}" for path in result.files_restored]
    removed = [f"- {path}" for path in result.files_removed]
    blocks = [
        "[Rollback — confirmé et appliqué]",
        f"Snapshot restauré : {result.rollback_id}",
        f"Historique rollback : {result.rollback_history_size} snapshot(s)",
    ]
    if restored:
        blocks.extend(["", "Fichiers restaurés :", *restored])
    if removed:
        blocks.extend(["", "Fichiers supprimés (créations annulées) :", *removed])
    if target_rollback_id and target_rollback_id != result.rollback_id:
        blocks.append(f"\nCible demandée : {target_rollback_id}")
    return "\n".join(blocks)


def format_rollback_request_summary(
    *,
    rollback_id: str,
    files_modified: tuple[str, ...],
    files_created: tuple[str, ...],
    timestamp: str,
) -> str:
    """Format pending rollback confirmation prompt (P12B2-003)."""
    modified = [f"- {path}" for path in files_modified]
    created = [f"- {path}" for path in files_created]
    blocks = [
        "[Rollback workspace — confirmation requise]",
        f"Snapshot : {rollback_id}",
        f"Horodatage : {timestamp}",
    ]
    if modified:
        blocks.extend(["", "Fichiers à restaurer :", *modified])
    if created:
        blocks.extend(["", "Fichiers créés à supprimer :", *created])
    blocks.append(
        "\nPour confirmer le rollback, répondez exactement : confirm rollback, "
        "confirme rollback, approve rollback, rollback confirm, "
        "confirmer le rollback, ou confirme le rollback."
    )
    return "\n".join(blocks)
