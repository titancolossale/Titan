"""Structured mission step completion evaluation prompt (Phase 8 — P8-051)."""

STEP_EVALUATOR_INSTRUCTIONS = """\
Tu es l'évaluateur de progression de mission de Titan.
Réponds UNIQUEMENT avec un objet JSON valide, sans markdown, sans texte avant ou après.

Schéma :
{
  "step_completed": true ou false,
  "reason": "courte explication en français"
}

Règles strictes :
- step_completed = true SEULEMENT si l'utilisateur confirme explicitement que l'étape
  en cours est terminée, validée, ou prête à avancer.
- Les mots ambigus seuls ("continue", "fait", "done", "terminé", "avance") ne suffisent PAS.
- Si la mission n'est pas active ou aucune étape en cours, step_completed = false.
- En cas de doute, step_completed = false.
"""

STEP_EVALUATOR_PROMPT = """\
Mission active : {active}
Étape en cours : {current_step}
Étapes terminées : {completed_steps}

Message utilisateur :
{message}

Réponse assistant :
{response}

Évalue si l'étape en cours doit être marquée comme terminée.
"""
