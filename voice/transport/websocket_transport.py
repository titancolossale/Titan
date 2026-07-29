# =====================================
# Titan WebSocket Streaming Transport
# =====================================

"""WebSocket transport with injectable socket backend (Phase 20.6).

Live sockets are injected via ``socket_factory`` so tests never open network
sockets. Production can supply a websocket-client / stdlib wrapper.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Protocol

from voice.exceptions import VoiceProviderError
from voice.transport.base import (
    StreamingTransport,
    TransportConfig,
    TransportEmit,
    TransportKind,
    TransportMessage,
)


class WebSocketBackend(Protocol):
    """Minimal socket surface required by WebSocketTransport."""

    def connect(self, url: str, *, headers: dict[str, str], timeout: float) -> None: ...

    def send(self, data: bytes, *, binary: bool) -> None: ...

    def recv(self, *, timeout: float | None) -> bytes | str | None: ...

    def ping(self) -> None: ...

    def close(self, *, reason: str = "") -> None: ...


SocketFactory = Callable[[], WebSocketBackend]


class _QueueBackend:
    """Default offline backend — duplex queues, no network."""

    def __init__(self) -> None:
        from voice.transport.memory import InMemoryTransport

        self._inner = InMemoryTransport(name="ws-backend")
        self._url = ""

    def connect(self, url: str, *, headers: dict[str, str], timeout: float) -> None:
        del headers, timeout
        self._url = url
        self._inner.connect()

    def send(self, data: bytes, *, binary: bool) -> None:
        self._inner.send(data, binary=binary)

    def recv(self, *, timeout: float | None) -> bytes | str | None:
        message = self._inner.receive(timeout=timeout)
        if message is None:
            return None
        return message.data

    def ping(self) -> None:
        self._inner.send(b"ping", binary=False)

    def close(self, *, reason: str = "") -> None:
        self._inner.disconnect(reason=reason or "close")

    def peer_push(self, data: bytes | str, *, binary: bool | None = None) -> None:
        self._inner.peer_push(data, binary=binary)


class WebSocketTransport(StreamingTransport):
    """Framed bidirectional WebSocket conduit."""

    def __init__(
        self,
        config: TransportConfig | None = None,
        *,
        emit: TransportEmit | None = None,
        socket_factory: SocketFactory | None = None,
        backend: WebSocketBackend | None = None,
    ) -> None:
        super().__init__(config, emit=emit)
        self._socket_factory = socket_factory
        self._backend = backend
        self._owns_backend = backend is None

    @property
    def kind(self) -> TransportKind:
        return TransportKind.WEBSOCKET

    @property
    def backend(self) -> WebSocketBackend | None:
        return self._backend

    def _do_connect(self) -> None:
        if self._backend is None:
            if self._socket_factory is not None:
                self._backend = self._socket_factory()
            else:
                self._backend = _QueueBackend()
        assert self._backend is not None
        url = self._config.url or "ws://localhost/voice"
        safe_headers = (
            {k: "[REDACTED]" for k in self._config.headers}
            if self._config.redact_headers
            else dict(self._config.headers)
        )
        del safe_headers  # used only to document redaction path
        try:
            self._backend.connect(
                url,
                headers=dict(self._config.headers),
                timeout=self._config.connect_timeout_seconds,
            )
        except Exception as exc:
            raise VoiceProviderError(f"WebSocket connect failed: {exc}") from exc

    def _do_send(self, data: bytes, *, binary: bool, sequence: int) -> None:
        del sequence
        if self._backend is None:
            raise VoiceProviderError("WebSocket backend missing")
        self._backend.send(data, binary=binary)

    def _do_receive(self, *, timeout: float | None) -> TransportMessage | None:
        if self._backend is None:
            raise VoiceProviderError("WebSocket backend missing")
        effective = (
            self._config.read_timeout_seconds if timeout is None else timeout
        )
        started = time.perf_counter()
        raw = self._backend.recv(timeout=effective)
        if raw is None:
            return None
        binary = isinstance(raw, (bytes, bytearray))
        return TransportMessage(
            data=raw,
            binary=binary,
            received_at=started,
        )

    def _do_heartbeat(self) -> None:
        if self._backend is None:
            return
        try:
            self._backend.ping()
        except Exception as exc:
            raise VoiceProviderError(f"WebSocket heartbeat failed: {exc}") from exc

    def _do_disconnect(self, *, reason: str) -> None:
        if self._backend is None:
            return
        try:
            self._backend.close(reason=reason)
        finally:
            if self._owns_backend:
                self._backend = None

    def metrics(self) -> dict[str, Any]:
        base = super().metrics()
        base["url_configured"] = bool(self._config.url)
        return base
