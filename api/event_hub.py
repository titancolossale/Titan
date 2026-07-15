# =====================================
# Titan Event Hub
# =====================================

"""Thread-safe event bus for SSE clients — Phase E8 Backend Bridge."""

from __future__ import annotations

import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass(frozen=True)
class TitanStreamEvent:
    """Single server-sent event with monotonic id for replay."""

    id: str
    event: str
    data: dict[str, Any]
    created_at: float = field(default_factory=time.time)


class EventHub:
    """Broadcast events to SSE subscribers with bounded replay buffer."""

    def __init__(self, *, buffer_size: int = 256) -> None:
        self._buffer_size = buffer_size
        self._lock = threading.Lock()
        self._counter = 0
        self._buffer: deque[TitanStreamEvent] = deque(maxlen=buffer_size)
        self._subscribers: list[queue.Queue[TitanStreamEvent | None]] = []

    def publish(self, event_type: str, data: dict[str, Any] | None = None) -> str:
        """Publish an event to all subscribers and the replay buffer."""
        payload = data if data is not None else {}
        with self._lock:
            self._counter += 1
            event_id = str(self._counter)
            event = TitanStreamEvent(id=event_id, event=event_type, data=payload)
            self._buffer.append(event)
            for subscriber in self._subscribers:
                subscriber.put(event)
            return event_id

    def replay_after(self, last_event_id: str | None) -> list[TitanStreamEvent]:
        """Return buffered events after ``last_event_id`` (exclusive)."""
        with self._lock:
            if not self._buffer:
                return []
            if not last_event_id:
                return list(self._buffer)
            try:
                last_num = int(last_event_id)
            except ValueError:
                return list(self._buffer)
            return [event for event in self._buffer if int(event.id) > last_num]

    def subscribe(self, *, last_event_id: str | None = None) -> Iterator[TitanStreamEvent]:
        """Yield replayed then live events until ``None`` sentinel (disconnect)."""
        subscriber: queue.Queue[TitanStreamEvent | None] = queue.Queue()
        with self._lock:
            self._subscribers.append(subscriber)

        try:
            for event in self.replay_after(last_event_id):
                yield event
            while True:
                item = subscriber.get()
                if item is None:
                    break
                yield item
        finally:
            with self._lock:
                if subscriber in self._subscribers:
                    self._subscribers.remove(subscriber)

    def disconnect_subscriber(self, subscriber: queue.Queue[TitanStreamEvent | None]) -> None:
        """Signal a subscriber queue to stop."""
        subscriber.put(None)

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


# Shared hub for status/telemetry and cross-request fan-out.
event_hub = EventHub()
