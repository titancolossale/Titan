# =====================================
# Titan Live Voice Session Lifecycle
# =====================================

"""Explicit live-voice session states and safe transitions (Phase 20.3)."""

from __future__ import annotations

from enum import Enum

from voice.exceptions import VoiceStateError


class LiveSessionState(str, Enum):
    """Production voice-session lifecycle states."""

    IDLE = "IDLE"
    LISTENING = "LISTENING"
    SPEECH_DETECTED = "SPEECH_DETECTED"
    CAPTURING = "CAPTURING"
    TRANSCRIBING = "TRANSCRIBING"
    IDENTIFYING_SPEAKER = "IDENTIFYING_SPEAKER"
    WAITING_FOR_IDENTITY_CONFIRMATION = "WAITING_FOR_IDENTITY_CONFIRMATION"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


# Terminal states that release the turn and allow return to LISTENING/IDLE.
_TERMINAL = frozenset(
    {
        LiveSessionState.CANCELLED,
        LiveSessionState.FAILED,
        LiveSessionState.COMPLETED,
        LiveSessionState.INTERRUPTED,
    }
)

_VALID_TRANSITIONS: dict[LiveSessionState, frozenset[LiveSessionState]] = {
    LiveSessionState.IDLE: frozenset(
        {
            LiveSessionState.LISTENING,
            LiveSessionState.CANCELLED,
            LiveSessionState.FAILED,
        }
    ),
    LiveSessionState.LISTENING: frozenset(
        {
            LiveSessionState.SPEECH_DETECTED,
            LiveSessionState.CAPTURING,
            LiveSessionState.IDLE,
            LiveSessionState.CANCELLED,
            LiveSessionState.FAILED,
            LiveSessionState.COMPLETED,
        }
    ),
    LiveSessionState.SPEECH_DETECTED: frozenset(
        {
            LiveSessionState.CAPTURING,
            LiveSessionState.LISTENING,
            LiveSessionState.CANCELLED,
            LiveSessionState.FAILED,
            LiveSessionState.INTERRUPTED,
        }
    ),
    LiveSessionState.CAPTURING: frozenset(
        {
            LiveSessionState.TRANSCRIBING,
            LiveSessionState.IDENTIFYING_SPEAKER,
            LiveSessionState.LISTENING,
            LiveSessionState.CANCELLED,
            LiveSessionState.FAILED,
            LiveSessionState.INTERRUPTED,
        }
    ),
    LiveSessionState.TRANSCRIBING: frozenset(
        {
            LiveSessionState.IDENTIFYING_SPEAKER,
            LiveSessionState.THINKING,
            LiveSessionState.WAITING_FOR_IDENTITY_CONFIRMATION,
            LiveSessionState.LISTENING,
            LiveSessionState.CANCELLED,
            LiveSessionState.FAILED,
        }
    ),
    LiveSessionState.IDENTIFYING_SPEAKER: frozenset(
        {
            LiveSessionState.TRANSCRIBING,
            LiveSessionState.THINKING,
            LiveSessionState.WAITING_FOR_IDENTITY_CONFIRMATION,
            LiveSessionState.LISTENING,
            LiveSessionState.CANCELLED,
            LiveSessionState.FAILED,
        }
    ),
    LiveSessionState.WAITING_FOR_IDENTITY_CONFIRMATION: frozenset(
        {
            LiveSessionState.THINKING,
            LiveSessionState.LISTENING,
            LiveSessionState.SPEAKING,
            LiveSessionState.CANCELLED,
            LiveSessionState.FAILED,
            LiveSessionState.COMPLETED,
        }
    ),
    LiveSessionState.THINKING: frozenset(
        {
            LiveSessionState.SPEAKING,
            LiveSessionState.LISTENING,
            LiveSessionState.IDLE,
            LiveSessionState.CANCELLED,
            LiveSessionState.FAILED,
            LiveSessionState.INTERRUPTED,
            LiveSessionState.COMPLETED,
        }
    ),
    LiveSessionState.SPEAKING: frozenset(
        {
            LiveSessionState.LISTENING,
            LiveSessionState.IDLE,
            LiveSessionState.INTERRUPTED,
            LiveSessionState.SPEECH_DETECTED,
            LiveSessionState.CAPTURING,
            LiveSessionState.CANCELLED,
            LiveSessionState.FAILED,
            LiveSessionState.COMPLETED,
        }
    ),
    LiveSessionState.INTERRUPTED: frozenset(
        {
            LiveSessionState.LISTENING,
            LiveSessionState.SPEECH_DETECTED,
            LiveSessionState.CAPTURING,
            LiveSessionState.IDLE,
            LiveSessionState.CANCELLED,
            LiveSessionState.FAILED,
        }
    ),
    LiveSessionState.CANCELLED: frozenset({LiveSessionState.IDLE, LiveSessionState.LISTENING}),
    LiveSessionState.FAILED: frozenset({LiveSessionState.IDLE, LiveSessionState.LISTENING}),
    LiveSessionState.COMPLETED: frozenset({LiveSessionState.IDLE, LiveSessionState.LISTENING}),
}


class LiveSessionStateMachine:
    """Enforces explicit live-session state transitions."""

    def __init__(self, initial: LiveSessionState = LiveSessionState.IDLE) -> None:
        self._state = initial

    @property
    def state(self) -> LiveSessionState:
        return self._state

    @property
    def is_terminal(self) -> bool:
        return self._state in _TERMINAL

    def can_transition(self, new_state: LiveSessionState) -> bool:
        if new_state == self._state:
            return True
        return new_state in _VALID_TRANSITIONS.get(self._state, frozenset())

    def transition(self, new_state: LiveSessionState) -> LiveSessionState:
        if new_state == self._state:
            return self._state
        allowed = _VALID_TRANSITIONS.get(self._state, frozenset())
        if new_state not in allowed:
            raise VoiceStateError(
                f"Invalid live voice transition {self._state.value} → {new_state.value}"
            )
        self._state = new_state
        return self._state

    def force(self, new_state: LiveSessionState) -> LiveSessionState:
        """Force a state (recovery paths only — still logged by caller)."""
        self._state = new_state
        return self._state

    def reset_to_listening(self) -> LiveSessionState:
        """Return safely to LISTENING after a turn completes or fails."""
        if self._state == LiveSessionState.LISTENING:
            return self._state
        if self.can_transition(LiveSessionState.LISTENING):
            return self.transition(LiveSessionState.LISTENING)
        self._state = LiveSessionState.LISTENING
        return self._state

    def reset_to_idle(self) -> LiveSessionState:
        if self._state == LiveSessionState.IDLE:
            return self._state
        if self.can_transition(LiveSessionState.IDLE):
            return self.transition(LiveSessionState.IDLE)
        self._state = LiveSessionState.IDLE
        return self._state
