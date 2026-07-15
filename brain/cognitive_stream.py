# =====================================
# Titan Cognitive Stream
# =====================================

"""Live cognitive event emitter for Frontend V2 — Phase E9."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

COGNITIVE_EVENT_TYPES: tuple[str, ...] = (
    "thinking_started",
    "intent_detected",
    "memory_lookup",
    "memory_hit",
    "memory_miss",
    "obsidian_lookup",
    "tool_selection",
    "tool_execution",
    "reasoning",
    "planning",
    "verification",
    "response_building",
    "response_ready",
    "thinking_finished",
)

CognitiveStreamCallback = Callable[[str, dict[str, Any]], None]

_INTENT_LABELS: dict[str, str] = {
    "general_chat": "Conversation générale",
    "coding": "Développement",
    "web_search": "Recherche web",
    "memory": "Mémoire",
    "file": "Fichiers",
    "file_list": "Liste de fichiers",
    "file_search": "Recherche de fichiers",
    "file_read": "Lecture de fichier",
    "file_metadata": "Métadonnées fichier",
    "document": "Document",
    "trading": "Trading",
    "calendar": "Agenda",
    "email": "E-mail",
    "github": "GitHub",
    "obsidian": "Obsidian",
    "browser": "Navigateur",
    "system": "Système",
    "workspace_explain": "Exploration workspace",
    "workspace_modify": "Modification workspace",
}


def intent_label(raw: str) -> str:
    """Return a sanitized French label for an intent key."""
    key = (raw or "general_chat").lower().replace("-", "_")
    return _INTENT_LABELS.get(key, key.replace("_", " ").capitalize())


class CognitiveStreamEmitter:
    """Tracks pipeline state and emits sanitized cognitive SSE events."""

    def __init__(self, callback: CognitiveStreamCallback | None = None) -> None:
        self._callback = callback
        self._thinking = False
        self._current_stage: str | None = None
        self._stage_history: list[dict[str, Any]] = []
        self._timeline: list[dict[str, Any]] = []
        self._pipeline: list[str] = []
        self._sequence = 0

    @property
    def thinking(self) -> bool:
        """True while a think turn is in progress."""
        return self._thinking

    @property
    def current_stage(self) -> str | None:
        """Most recent cognitive stage id."""
        return self._current_stage

    @property
    def stage_history(self) -> list[dict[str, Any]]:
        """Ordered list of stages emitted this turn."""
        return list(self._stage_history)

    @property
    def timeline(self) -> list[dict[str, Any]]:
        """Chronological event timeline for orchestrator UI."""
        return list(self._timeline)

    @property
    def pipeline(self) -> list[str]:
        """Stage ids executed in order this turn."""
        return list(self._pipeline)

    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        """Emit a cognitive event and record it in stage history."""
        payload = dict(data or {})
        payload.setdefault("stage", event_type)
        payload.setdefault("sequence", self._sequence)
        payload.setdefault("timestamp", time.time())
        self._sequence += 1

        self._current_stage = event_type
        if event_type not in self._pipeline:
            self._pipeline.append(event_type)

        entry = {
            "stage": event_type,
            "label": payload.get("label", event_type),
            "timestamp": payload["timestamp"],
            "sequence": payload["sequence"],
        }
        self._stage_history.append(entry)
        self._timeline.append({"event": event_type, **payload})

        if self._callback is not None:
            self._callback(event_type, payload)

    def start_thinking(self, *, message: str = "", user: str = "") -> None:
        """Mark think turn start."""
        self._thinking = True
        self._stage_history = []
        self._timeline = []
        self._pipeline = []
        self._sequence = 0
        self._current_stage = None
        self.emit(
            "thinking_started",
            {
                "label": "Réflexion en cours…",
                "message": message[:120] if message else "",
                "user": user,
                "neural_state": "thinking",
            },
        )

    def finish_thinking(self) -> None:
        """Mark think turn complete."""
        self.emit(
            "thinking_finished",
            {
                "label": "Réflexion terminée",
                "neural_state": "idle",
            },
        )
        self._thinking = False
        self._current_stage = None

    def snapshot(self) -> dict[str, Any]:
        """Return pipeline state for conversation_finished payload."""
        return {
            "thinking": self._thinking,
            "current_stage": self._current_stage,
            "stage_history": list(self._stage_history),
            "timeline": list(self._timeline),
            "pipeline": list(self._pipeline),
        }
