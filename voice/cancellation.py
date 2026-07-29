# =====================================
# Titan Voice Cancellation Tokens
# =====================================

"""Independently cancellable stage tokens for the real-time voice pipeline."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class CancelToken:
    """Thread-safe cancellation flag for one pipeline stage or an entire turn."""

    name: str = "stage"
    _event: threading.Event = field(default_factory=threading.Event, repr=False)

    def cancel(self) -> None:
        self._event.set()

    def reset(self) -> None:
        self._event.clear()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            from voice.exceptions import VoiceStateError

            raise VoiceStateError(f"Voice stage cancelled: {self.name}")


@dataclass
class TurnCancellation:
    """Bundle of independently cancellable pipeline stages for one turn."""

    stt: CancelToken = field(default_factory=lambda: CancelToken(name="stt"))
    brain: CancelToken = field(default_factory=lambda: CancelToken(name="brain"))
    tts: CancelToken = field(default_factory=lambda: CancelToken(name="tts"))
    turn: CancelToken = field(default_factory=lambda: CancelToken(name="turn"))

    def cancel_all(self) -> None:
        self.stt.cancel()
        self.brain.cancel()
        self.tts.cancel()
        self.turn.cancel()

    def reset(self) -> None:
        self.stt.reset()
        self.brain.reset()
        self.tts.reset()
        self.turn.reset()

    @property
    def cancelled(self) -> bool:
        return self.turn.cancelled
