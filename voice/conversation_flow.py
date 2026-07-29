# =====================================
# Titan Conversation Flow Controller
# =====================================

"""Conversational timing, barge-in resume, and confirmation prompts (Phase 20.7).

Polishes live voice turn flow without redesigning the Web UI:
- natural pause / turn-gap timing
- barge-in debounce + resume-after-interruption
- identity confirmation prompt selection (FR/EN)
- session continuity markers
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


CONFIRMATION_PROMPT_FR = (
    "Je ne suis pas certain de te reconnaître. Es-tu Nolan ou Ibrahim ?"
)
CONFIRMATION_PROMPT_EN = (
    "I'm not sure I recognize you. Are you Nolan or Ibrahim?"
)


class FlowPhase(str, Enum):
    """Lightweight conversation-flow phases (orthogonal to LiveSessionState)."""

    IDLE = "idle"
    LISTENING = "listening"
    USER_SPEAKING = "user_speaking"
    NATURAL_PAUSE = "natural_pause"
    PROCESSING = "processing"
    ASSISTANT_SPEAKING = "assistant_speaking"
    INTERRUPTED = "interrupted"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    RESUMING = "resuming"


@dataclass
class ConversationFlowConfig:
    """Turn-timing and barge-in polish knobs."""

    natural_pause_ms: float = 280.0
    min_turn_gap_ms: float = 180.0
    barge_in_debounce_ms: float = 120.0
    resume_grace_ms: float = 200.0
    max_confirmation_retries: int = 2
    confirmation_prompt_fr: str = CONFIRMATION_PROMPT_FR
    confirmation_prompt_en: str = CONFIRMATION_PROMPT_EN

    def to_dict(self) -> dict[str, Any]:
        return {
            "natural_pause_ms": self.natural_pause_ms,
            "min_turn_gap_ms": self.min_turn_gap_ms,
            "barge_in_debounce_ms": self.barge_in_debounce_ms,
            "resume_grace_ms": self.resume_grace_ms,
            "max_confirmation_retries": self.max_confirmation_retries,
        }


@dataclass
class TurnTimingRecord:
    """Per-turn timing bookkeeping (no audio)."""

    turn_index: int = 0
    speech_started_at: float | None = None
    speech_ended_at: float | None = None
    processing_started_at: float | None = None
    speaking_started_at: float | None = None
    speaking_ended_at: float | None = None
    interrupted: bool = False
    barge_in_count: int = 0
    speech_duration_ms: float = 0.0
    turn_duration_ms: float = 0.0
    natural_pause_applied_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "interrupted": self.interrupted,
            "barge_in_count": self.barge_in_count,
            "speech_duration_ms": round(self.speech_duration_ms, 2),
            "turn_duration_ms": round(self.turn_duration_ms, 2),
            "natural_pause_applied_ms": round(self.natural_pause_applied_ms, 2),
        }


@dataclass
class ConversationFlowController:
    """Tracks conversational timing and interruption resume for one session."""

    config: ConversationFlowConfig = field(default_factory=ConversationFlowConfig)
    phase: FlowPhase = FlowPhase.IDLE
    turn: TurnTimingRecord = field(default_factory=TurnTimingRecord)
    continuity_token: str | None = None
    confirmation_retries: int = 0
    last_barge_in_at: float | None = None
    resume_ready_at: float | None = None
    _last_turn_completed_at: float | None = None
    _history: list[TurnTimingRecord] = field(default_factory=list)

    def reset(self) -> None:
        self.phase = FlowPhase.IDLE
        self.turn = TurnTimingRecord()
        self.confirmation_retries = 0
        self.last_barge_in_at = None
        self.resume_ready_at = None
        self._last_turn_completed_at = None
        self._history.clear()

    def bind_continuity(self, token: str) -> None:
        self.continuity_token = token

    def on_listening(self) -> None:
        self.phase = FlowPhase.LISTENING

    def on_speech_start(self) -> None:
        now = time.monotonic()
        if self.turn.speech_started_at is None:
            self.turn.speech_started_at = now
        self.phase = FlowPhase.USER_SPEAKING

    def on_natural_pause(self) -> float:
        """Enter natural pause; returns suggested wait ms before end-of-turn."""
        self.phase = FlowPhase.NATURAL_PAUSE
        self.turn.natural_pause_applied_ms = self.config.natural_pause_ms
        return self.config.natural_pause_ms

    def on_speech_end(self) -> None:
        now = time.monotonic()
        self.turn.speech_ended_at = now
        if self.turn.speech_started_at is not None:
            self.turn.speech_duration_ms = (
                now - self.turn.speech_started_at
            ) * 1000.0
        self.phase = FlowPhase.PROCESSING
        self.turn.processing_started_at = now

    def on_assistant_speaking(self) -> None:
        self.phase = FlowPhase.ASSISTANT_SPEAKING
        self.turn.speaking_started_at = time.monotonic()

    def on_turn_complete(self) -> TurnTimingRecord:
        now = time.monotonic()
        self.turn.speaking_ended_at = now
        started = self.turn.speech_started_at or self.turn.processing_started_at or now
        self.turn.turn_duration_ms = (now - started) * 1000.0
        completed = TurnTimingRecord(
            turn_index=self.turn.turn_index,
            speech_started_at=self.turn.speech_started_at,
            speech_ended_at=self.turn.speech_ended_at,
            processing_started_at=self.turn.processing_started_at,
            speaking_started_at=self.turn.speaking_started_at,
            speaking_ended_at=self.turn.speaking_ended_at,
            interrupted=self.turn.interrupted,
            barge_in_count=self.turn.barge_in_count,
            speech_duration_ms=self.turn.speech_duration_ms,
            turn_duration_ms=self.turn.turn_duration_ms,
            natural_pause_applied_ms=self.turn.natural_pause_applied_ms,
        )
        self._history.append(completed)
        self._last_turn_completed_at = now
        next_index = completed.turn_index + 1
        self.turn = TurnTimingRecord(turn_index=next_index)
        self.phase = FlowPhase.LISTENING
        return completed

    def can_accept_barge_in(self) -> bool:
        """Debounce rapid double barge-in attempts."""
        now = time.monotonic()
        if self.last_barge_in_at is None:
            return True
        elapsed_ms = (now - self.last_barge_in_at) * 1000.0
        return elapsed_ms >= self.config.barge_in_debounce_ms

    def on_barge_in(self) -> dict[str, Any]:
        """Record barge-in and schedule resume-after-interruption."""
        now = time.monotonic()
        self.last_barge_in_at = now
        self.turn.interrupted = True
        self.turn.barge_in_count += 1
        self.phase = FlowPhase.INTERRUPTED
        self.resume_ready_at = now + (self.config.resume_grace_ms / 1000.0)
        return {
            "interrupted": True,
            "resume_grace_ms": self.config.resume_grace_ms,
            "barge_in_count": self.turn.barge_in_count,
        }

    def resume_after_interruption(self) -> bool:
        """Return True when grace elapsed and capture may resume."""
        now = time.monotonic()
        if self.resume_ready_at is not None and now < self.resume_ready_at:
            self.phase = FlowPhase.RESUMING
            return False
        self.phase = FlowPhase.USER_SPEAKING
        if self.turn.speech_started_at is None:
            self.turn.speech_started_at = now
        self.resume_ready_at = None
        return True

    def turn_gap_elapsed(self) -> bool:
        """True when minimum gap since last turn completion has elapsed."""
        if self._last_turn_completed_at is None:
            return True
        elapsed_ms = (time.monotonic() - self._last_turn_completed_at) * 1000.0
        return elapsed_ms >= self.config.min_turn_gap_ms

    def on_awaiting_confirmation(self) -> None:
        self.phase = FlowPhase.AWAITING_CONFIRMATION

    def confirmation_prompt(self, *, locale: str = "fr-FR") -> str:
        lowered = (locale or "fr-FR").lower()
        if lowered.startswith("en"):
            return self.config.confirmation_prompt_en
        return self.config.confirmation_prompt_fr

    def note_confirmation_retry(self) -> bool:
        """Increment confirmation retries; return False when exhausted."""
        self.confirmation_retries += 1
        return self.confirmation_retries <= self.config.max_confirmation_retries

    def clear_confirmation(self) -> None:
        self.confirmation_retries = 0
        if self.phase == FlowPhase.AWAITING_CONFIRMATION:
            self.phase = FlowPhase.LISTENING

    def history(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self._history]

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "continuity_token": self.continuity_token,
            "confirmation_retries": self.confirmation_retries,
            "current_turn": self.turn.to_dict(),
            "turn_count": len(self._history),
            "config": self.config.to_dict(),
        }


def conversation_flow_config_from_settings() -> ConversationFlowConfig:
    try:
        from config import settings as app_settings
    except Exception:
        return ConversationFlowConfig()
    return ConversationFlowConfig(
        natural_pause_ms=float(
            getattr(app_settings, "TITAN_VOICE_NATURAL_PAUSE_MS", 280.0)
        ),
        min_turn_gap_ms=float(
            getattr(app_settings, "TITAN_VOICE_MIN_TURN_GAP_MS", 180.0)
        ),
        barge_in_debounce_ms=float(
            getattr(app_settings, "TITAN_VOICE_BARGE_IN_DEBOUNCE_MS", 120.0)
        ),
        resume_grace_ms=float(
            getattr(app_settings, "TITAN_VOICE_RESUME_GRACE_MS", 200.0)
        ),
    )
