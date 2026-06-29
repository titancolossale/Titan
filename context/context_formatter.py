# =====================================
# Titan Context Formatter
# =====================================

"""French prompt-ready formatting for context snapshots (Phase 4 — P4-004)."""

from __future__ import annotations

from context.models import ContextSnapshot


class ContextFormatter:
    """Formats a ``ContextSnapshot`` into the canonical CONTEXTE ACTUEL block."""

    def format(self, snapshot: ContextSnapshot) -> str:
        """Return labeled French context text for prompt injection."""
        lines = [
            "============================",
            "TITAN CONTEXT",
            "============================",
            "",
            "Utilisateur :",
            snapshot.current_user,
            "",
            "Projet actif :",
            snapshot.active_project,
            "",
            "Objectif :",
            snapshot.current_goal,
            "",
            "Phase actuelle :",
            snapshot.current_phase,
            "",
            "============================",
        ]
        return "\n".join(lines)
