# =====================================
# Titan Cognitive Progress Presentation
# =====================================

"""Sanitized high-level progress labels for UI — Phase 24.0."""

from __future__ import annotations

from brain.cognitive_models import CognitivePhase, ProgressEvent, TaskGraphNode

# Tool name fragments → cognitive phase (longest match wins via ordered scan).
_TOOL_PHASE_RULES: tuple[tuple[str, CognitivePhase], ...] = (
    ("obsidian", CognitivePhase.MEMORY),
    ("memory", CognitivePhase.MEMORY),
    ("browser", CognitivePhase.RESEARCH),
    ("web_search", CognitivePhase.RESEARCH),
    ("web", CognitivePhase.RESEARCH),
    ("calendar", CognitivePhase.PLANNING),
    ("email", CognitivePhase.WRITING),
    ("trading", CognitivePhase.RESEARCH),
    ("tradingview", CognitivePhase.RESEARCH),
    ("voice", CognitivePhase.WRITING),
    ("file_read", CognitivePhase.RESEARCH),
    ("file_write", CognitivePhase.WRITING),
    ("github", CognitivePhase.RESEARCH),
    ("time", CognitivePhase.PLANNING),
)

# User-facing progress labels — never expose internal reasoning or chain-of-thought.
_PHASE_LABELS: dict[CognitivePhase, str] = {
    CognitivePhase.UNDERSTANDING: "Compréhension de la demande…",
    CognitivePhase.PLANNING: "Planification…",
    CognitivePhase.MEMORY: "Consultation de la mémoire…",
    CognitivePhase.RESEARCH: "Exploration…",
    CognitivePhase.WRITING: "Rédaction de la réponse…",
    CognitivePhase.VERIFICATION: "Vérification…",
    CognitivePhase.IDLE: "Prêt.",
}

_TOOL_LABELS: dict[str, str] = {
    "memory": "Consultation de la mémoire…",
    "obsidian": "Consultation d'Obsidian…",
    "browser": "Exploration web…",
    "web_search": "Recherche web…",
    "calendar": "Consultation de l'agenda…",
    "email": "Traitement des e-mails…",
    "trading": "Analyse des marchés…",
    "tradingview": "Consultation de TradingView…",
    "voice": "Interface vocale…",
    "file_read": "Lecture des fichiers…",
    "file_write": "Mise à jour des fichiers…",
    "time": "Vérification de l'heure…",
}

# Maps cognitive phase → brain_cognitive.js neural state alias.
PHASE_NEURAL_STATE: dict[CognitivePhase, str] = {
    CognitivePhase.UNDERSTANDING: "thinking",
    CognitivePhase.PLANNING: "planning",
    CognitivePhase.MEMORY: "memory_retrieval",
    CognitivePhase.RESEARCH: "browser_research",
    CognitivePhase.WRITING: "tool_usage",
    CognitivePhase.VERIFICATION: "deep_analysis",
    CognitivePhase.IDLE: "idle",
}

_TOOL_NEURAL_STATE: dict[str, str] = {
    "memory": "memory_retrieval",
    "obsidian": "memory_retrieval",
    "browser": "browser_research",
    "web_search": "browser_research",
    "calendar": "calendar_planning",
    "email": "email_processing",
    "trading": "trading_analysis",
    "tradingview": "trading_analysis",
    "voice": "voice_speaking",
}


def normalize_tool_key(raw_name: str) -> str:
    """Normalize internal tool names for registry lookup."""
    return raw_name.lower().replace("-", "_").strip()


def resolve_tool_phase(tool_name: str | None) -> CognitivePhase:
    """Map a tool name to a cognitive phase; unknown tools default to research."""
    if not tool_name:
        return CognitivePhase.PLANNING
    key = normalize_tool_key(tool_name)
    if key in _DYNAMIC_TOOL_PHASES:
        return _DYNAMIC_TOOL_PHASES[key]
    for fragment, phase in _TOOL_PHASE_RULES:
        if fragment in key or key.startswith(fragment):
            return phase
    return CognitivePhase.RESEARCH


def resolve_neural_state(
    phase: CognitivePhase,
    tool_name: str | None = None,
) -> str:
    """Resolve brain_cognitive.js state id from phase and optional tool."""
    if tool_name:
        key = normalize_tool_key(tool_name)
        if key in _TOOL_NEURAL_STATE:
            return _TOOL_NEURAL_STATE[key]
        for fragment, state in _TOOL_NEURAL_STATE.items():
            if fragment in key:
                return state
    return PHASE_NEURAL_STATE.get(phase, "idle")


def progress_label_for_phase(phase: CognitivePhase) -> str:
    """Return user-facing label for a cognitive phase."""
    return _PHASE_LABELS.get(phase, "Action en cours…")


def progress_label_for_tool(tool_name: str | None) -> str:
    """Return user-facing label for a tool invocation."""
    if not tool_name:
        return progress_label_for_phase(CognitivePhase.PLANNING)
    key = normalize_tool_key(tool_name)
    if key in _TOOL_LABELS:
        return _TOOL_LABELS[key]
    for fragment, label in _TOOL_LABELS.items():
        if fragment in key:
            return label
    return "Action en cours…"


def progress_event(
    phase: CognitivePhase,
    *,
    tool_name: str | None = None,
    node_id: str | None = None,
) -> ProgressEvent:
    """Build a sanitized progress event."""
    label = (
        progress_label_for_tool(tool_name)
        if tool_name and phase not in {CognitivePhase.UNDERSTANDING, CognitivePhase.VERIFICATION}
        else progress_label_for_phase(phase)
    )
    return ProgressEvent(
        phase=phase,
        label=label,
        node_id=node_id,
        tool=normalize_tool_key(tool_name) if tool_name else None,
    )


def task_node_from_plan_step(step) -> TaskGraphNode:
    """Convert a PlanStep into a TaskGraphNode with sanitized objective."""
    tool = step.required_tool or None
    phase = resolve_tool_phase(tool)
    objective = _sanitize_objective(step.objective, tool)
    return TaskGraphNode(
        node_id=step.step_id,
        objective=objective,
        tool=tool,
        dependencies=tuple(step.dependencies),
        cognitive_phase=phase,
        step_kind=step.step_kind,
        selected_action=step.selected_action,
    )


def _sanitize_objective(objective: str, tool: str | None) -> str:
    """Strip reasoning-like content from objectives shown in UI."""
    if tool:
        return progress_label_for_tool(tool).rstrip("…")
    text = (objective or "").strip()
    if not text or len(text) > 80:
        return progress_label_for_phase(CognitivePhase.PLANNING).rstrip("…")
    return text


_DYNAMIC_TOOL_PHASES: dict[str, CognitivePhase] = {}


def register_tool_presentation(
    tool_name: str,
    *,
    phase: CognitivePhase | None = None,
    label: str | None = None,
    neural_state: str | None = None,
) -> None:
    """Register presentation for a future tool at runtime (auto-registration hook)."""
    key = normalize_tool_key(tool_name)
    if label:
        _TOOL_LABELS[key] = label
    if phase is not None:
        _DYNAMIC_TOOL_PHASES[key] = phase
    if neural_state:
        _TOOL_NEURAL_STATE[key] = neural_state


def sync_registered_tools(tool_names: list[str]) -> None:
    """Ensure all registered tools have a presentation entry (future-tool hook)."""
    for name in tool_names:
        key = normalize_tool_key(name)
        if key not in _TOOL_LABELS:
            phase = resolve_tool_phase(key)
            _TOOL_LABELS[key] = progress_label_for_phase(phase)
