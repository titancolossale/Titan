# =====================================
# Titan Web Tool Activity Formatter
# =====================================

"""Sanitize tool audit events into user-facing activity records (Phase 17.7)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tools.audit.tool_audit_models import ToolAuditEvent

if TYPE_CHECKING:
    from brain.pipeline.context_bundle import ThinkContext

# User-facing registry — never expose raw capability names or JSON internals.
_TOOL_PRESENTATION: dict[str, dict[str, Any]] = {
    "browser": {
        "category": "browser",
        "title": "Exploration web",
        "icon": "◎",
        "status_line": "Navigation web…",
        "steps": ["Navigation web", "Recherche", "Analyse", "Synthèse"],
        "cognitive_state": "exploration",
    },
    "memory": {
        "category": "memory",
        "title": "Mémoire",
        "icon": "◈",
        "status_line": "Recherche en mémoire…",
        "steps": ["Recherche…", "Correspondances trouvées…", "Lecture des souvenirs…", "Terminé."],
    },
    "obsidian": {
        "category": "memory",
        "title": "Consultation d'Obsidian",
        "icon": "◈",
        "status_line": "Consultation d'Obsidian…",
        "steps": ["Recherche…", "Lecture…", "Mise à jour…", "Terminé."],
    },
    "calendar": {
        "category": "calendar",
        "title": "Agenda",
        "icon": "◷",
        "status_line": "Lecture de l'agenda…",
        "steps": ["Ouverture…", "Lecture des événements…", "Analyse…", "Terminé."],
    },
    "trading": {
        "category": "trading",
        "title": "Marchés",
        "icon": "◆",
        "status_line": "Analyse des marchés…",
        "steps": ["Connexion…", "Lecture des données…", "Analyse…", "Terminé."],
    },
    "tradingview": {
        "category": "trading",
        "title": "TradingView",
        "icon": "◆",
        "status_line": "Consultation de TradingView…",
        "steps": ["Chargement…", "Lecture du graphique…", "Analyse…", "Terminé."],
    },
    "email": {
        "category": "email",
        "title": "E-mail",
        "icon": "◇",
        "status_line": "Lecture des e-mails…",
        "steps": ["Connexion…", "Lecture…", "Tri…", "Terminé."],
    },
    "time": {
        "category": "default",
        "title": "Horloge",
        "icon": "◉",
        "status_line": "Vérification de l'heure…",
        "steps": ["Lecture…", "Terminé."],
    },
    "planning": {
        "category": "planning",
        "title": "Planification",
        "icon": "◐",
        "status_line": "Planification en cours…",
        "steps": ["Analyse…", "Structuration…", "Terminé."],
    },
    "default": {
        "category": "default",
        "title": "Outil",
        "icon": "◉",
        "status_line": "Action en cours…",
        "steps": ["Préparation…", "Exécution…", "Terminé."],
    },
}

_LIFECYCLE_START = frozenset({"invoked", "queued", "started"})
_LIFECYCLE_END = frozenset({"completed", "failed", "cancelled", "degraded"})


def normalize_tool_key(raw_name: str) -> str:
    """Map internal tool names to presentation registry keys."""
    if not raw_name:
        return "default"

    key = raw_name.lower().replace("-", "_")
    if key in _TOOL_PRESENTATION:
        return key

    if "obsidian" in key or "vault" in key or "note" in key:
        return "obsidian"
    if "browser" in key or "web" in key:
        return "browser"
    if "calendar" in key or "agenda" in key:
        return "calendar"
    if "trad" in key or "market" in key:
        return "trading"
    if "mail" in key or "email" in key:
        return "email"
    if "memory" in key or "memo" in key:
        return "memory"
    if "time" in key:
        return "time"
    if "plan" in key:
        return "planning"
    return "default"


def _presentation_for(tool_name: str) -> dict[str, Any]:
    return _TOOL_PRESENTATION.get(normalize_tool_key(tool_name), _TOOL_PRESENTATION["default"])


def format_tool_activity(
    events: list[ToolAuditEvent],
    ctx: ThinkContext | None = None,
) -> list[dict[str, Any]]:
    """
    Convert audit events into sanitized activity records for the web UI.

    Returns user-facing dicts only — no digests, params, or internal codes.
    """
    if not events:
        return []

    runs: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for event in events:
        run_id = event.run_id or f"run-{event.tool_name}-{len(order)}"
        if run_id not in runs:
            presentation = _presentation_for(event.tool_name)
            runs[run_id] = {
                "run_id": run_id,
                "tool": normalize_tool_key(event.tool_name),
                "category": presentation["category"],
                "title": presentation["title"],
                "icon": presentation["icon"],
                "status_line": presentation["status_line"],
                "steps": list(presentation["steps"]),
                "state": "running",
                "success": None,
            }
            order.append(run_id)

        record = runs[run_id]

        if event.event_type in _LIFECYCLE_START and record["state"] == "running":
            record["status_line"] = record["status_line"]

        if event.event_type in _LIFECYCLE_END:
            record["state"] = "complete" if event.event_type == "completed" else "error"
            record["success"] = event.event_type == "completed" and event.success is not False
            if event.event_type == "failed":
                record["steps"] = record["steps"][:-1] + ["Interrompu."]
            elif record["steps"][-1] not in {"Terminé.", "Synthèse"}:
                record["steps"] = record["steps"][:-1] + ["Terminé."]

    results: list[dict[str, Any]] = []
    for run_id in order:
        record = runs[run_id]
        if record["state"] == "running":
            record["state"] = "complete"
            record["success"] = True
            if record["tool"] == "browser":
                if record["steps"][-1] != "Synthèse":
                    record["steps"] = record["steps"][:-1] + ["Synthèse"]
            elif record["steps"][-1] != "Terminé.":
                record["steps"] = record["steps"][:-1] + ["Terminé."]
        results.append(
            {
                "run_id": record["run_id"],
                "tool": record["tool"],
                "title": record["title"],
                "icon": record["icon"],
                "status_line": record["status_line"],
                "steps": record["steps"],
                "state": record["state"],
                "success": record["success"],
            }
        )

    if ctx is not None:
        _enrich_browser_exploration(results, ctx)

    return results


def _enrich_browser_exploration(
    records: list[dict[str, Any]],
    ctx: ThinkContext,
) -> None:
    """Attach Exploration state and sanitized source cards to browser activity."""
    if not getattr(ctx, "browser_exploring", False):
        return

    source_labels = list(getattr(ctx, "browser_source_labels", []) or [])
    source_cards = [f"Source · {label}" for label in source_labels[:4]]

    for record in records:
        if record.get("tool") != "browser":
            continue
        record["cognitive_state"] = "exploration"
        record["exploration"] = True
        if source_cards:
            record["sources"] = source_cards
        presentation = _TOOL_PRESENTATION.get("browser", {})
        record["steps"] = list(presentation.get("steps", record.get("steps", [])))
        record["title"] = presentation.get("title", record.get("title"))
        record["status_line"] = presentation.get("status_line", record.get("status_line"))


def collect_audit_events_since(titan: Any, start_index: int) -> list[ToolAuditEvent]:
    """Return audit events recorded after start_index for the shared tool runtime."""
    tool_manager = getattr(titan, "tools", None)
    if tool_manager is None:
        return []

    runtime = tool_manager.runtime
    if runtime is None or runtime.audit_logger is None:
        return []

    all_events = runtime.audit_logger.events()
    if start_index >= len(all_events):
        return []
    return all_events[start_index:]
