# =====================================
# Titan Cancellation Registry
# =====================================

"""Per-run cancellation signals for tool executors (Phase 10A — P10A-025)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class CancellationRegistry:
    """Track cancellation requests keyed by run_id."""

    _events: dict[str, threading.Event] = field(default_factory=dict)
    _reasons: dict[str, str] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def register(self, run_id: str) -> threading.Event:
        """Create or return the cancellation event for a run."""
        with self._lock:
            if run_id not in self._events:
                self._events[run_id] = threading.Event()
            return self._events[run_id]

    def cancel(self, run_id: str, *, reason: str = "") -> bool:
        """Signal cancellation for a run."""
        with self._lock:
            event = self._events.get(run_id)
            if event is None:
                event = threading.Event()
                self._events[run_id] = event
            self._reasons[run_id] = reason or "Annulé"
            event.set()
            return True

    def is_cancelled(self, run_id: str) -> bool:
        """Return True when cancellation was requested."""
        with self._lock:
            event = self._events.get(run_id)
            return event.is_set() if event is not None else False

    def reason(self, run_id: str) -> str:
        """Return cancellation reason when set."""
        with self._lock:
            return self._reasons.get(run_id, "")

    def unregister(self, run_id: str) -> None:
        """Remove cancellation state for a completed run."""
        with self._lock:
            self._events.pop(run_id, None)
            self._reasons.pop(run_id, None)
