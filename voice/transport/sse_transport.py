# =====================================
# Titan SSE Streaming Transport
# =====================================

"""Server-Sent Events (unidirectional receive + HTTP post send) (Phase 20.6)."""

from __future__ import annotations

import queue
import time
from typing import Any, Callable

from voice.exceptions import VoiceProviderError
from voice.transport.base import (
    StreamingTransport,
    TransportConfig,
    TransportEmit,
    TransportKind,
    TransportMessage,
)


EventSourceFactory = Callable[[str, dict[str, str]], "EventSourceBackend"]


class EventSourceBackend:
    """Minimal SSE source — inject for tests / HTTP clients."""

    def open(self, url: str, *, headers: dict[str, str], timeout: float) -> None:
        del url, headers, timeout

    def read_event(self, *, timeout: float | None) -> str | None:
        del timeout
        return None

    def close(self) -> None:
        return None


class _QueueEventSource(EventSourceBackend):
    def __init__(self) -> None:
        self._events: queue.Queue[str | None] = queue.Queue()
        self._open = False

    def open(self, url: str, *, headers: dict[str, str], timeout: float) -> None:
        del url, headers, timeout
        self._open = True

    def read_event(self, *, timeout: float | None) -> str | None:
        if not self._open:
            return None
        try:
            return self._events.get(timeout=timeout if timeout is not None else 0.0)
        except queue.Empty:
            return None

    def close(self) -> None:
        self._open = False
        try:
            self._events.put_nowait(None)
        except Exception:
            pass

    def push(self, event: str) -> None:
        self._events.put(event)


class ServerSentEventsTransport(StreamingTransport):
    """SSE receive path with optional HTTP post callback for uplink."""

    def __init__(
        self,
        config: TransportConfig | None = None,
        *,
        emit: TransportEmit | None = None,
        event_source: EventSourceBackend | None = None,
        event_source_factory: EventSourceFactory | None = None,
        send_callback: Callable[[bytes], None] | None = None,
    ) -> None:
        super().__init__(config, emit=emit)
        self._event_source = event_source
        self._event_source_factory = event_source_factory
        self._send_callback = send_callback
        self._owns_source = event_source is None

    @property
    def kind(self) -> TransportKind:
        return TransportKind.SSE

    def push_event(self, event: str) -> None:
        """Test helper — inject an SSE event when using the queue backend."""
        source = self._event_source
        if isinstance(source, _QueueEventSource):
            source.push(event)

    def _do_connect(self) -> None:
        if self._event_source is None:
            if self._event_source_factory is not None:
                self._event_source = self._event_source_factory(
                    self._config.url or "", dict(self._config.headers)
                )
            else:
                self._event_source = _QueueEventSource()
        assert self._event_source is not None
        try:
            self._event_source.open(
                self._config.url or "https://localhost/voice/events",
                headers=dict(self._config.headers),
                timeout=self._config.connect_timeout_seconds,
            )
        except Exception as exc:
            raise VoiceProviderError(f"SSE connect failed: {exc}") from exc

    def _do_send(self, data: bytes, *, binary: bool, sequence: int) -> None:
        del binary, sequence
        if self._send_callback is None:
            # SSE is primarily downlink; uplink may be absent in pure SSE mode.
            return
        self._send_callback(data)

    def _do_receive(self, *, timeout: float | None) -> TransportMessage | None:
        if self._event_source is None:
            raise VoiceProviderError("SSE event source missing")
        effective = (
            self._config.read_timeout_seconds if timeout is None else timeout
        )
        started = time.perf_counter()
        event = self._event_source.read_event(timeout=effective)
        if event is None:
            return None
        return TransportMessage(data=event, binary=False, received_at=started)

    def _do_heartbeat(self) -> None:
        # SSE heartbeats are typically server-driven comments; record locally.
        return None

    def _do_disconnect(self, *, reason: str) -> None:
        del reason
        if self._event_source is None:
            return
        try:
            self._event_source.close()
        finally:
            if self._owns_source:
                self._event_source = None

    def metrics(self) -> dict[str, Any]:
        base = super().metrics()
        base["uplink_enabled"] = self._send_callback is not None
        return base
