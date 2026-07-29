# =====================================
# Titan Streaming Transport Base
# =====================================

"""Transport abstractions shared by WebSocket / SSE / HTTP fallback (Phase 20.6)."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class TransportKind(str, Enum):
    WEBSOCKET = "websocket"
    SSE = "sse"
    HTTP = "http"
    MEMORY = "memory"


class TransportState(str, Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DEGRADED = "degraded"
    CLOSING = "closing"
    CLOSED = "closed"
    FAILED = "failed"


class TransportEvent(str, Enum):
    CONNECTING = "TRANSPORT_CONNECTING"
    CONNECTED = "TRANSPORT_CONNECTED"
    MESSAGE = "TRANSPORT_MESSAGE"
    HEARTBEAT = "TRANSPORT_HEARTBEAT"
    DISCONNECTED = "TRANSPORT_DISCONNECTED"
    RECONNECTING = "TRANSPORT_RECONNECTING"
    RECOVERED = "TRANSPORT_RECOVERED"
    TIMEOUT = "TRANSPORT_TIMEOUT"
    ERROR = "TRANSPORT_ERROR"
    CLOSED = "TRANSPORT_CLOSED"


@dataclass(frozen=True)
class TransportMessage:
    """One framed message on a streaming transport."""

    data: bytes | str
    binary: bool = False
    sequence: int | None = None
    received_at: float = field(default_factory=time.perf_counter)

    def as_bytes(self) -> bytes:
        if isinstance(self.data, bytes):
            return self.data
        return self.data.encode("utf-8")

    def as_text(self) -> str:
        if isinstance(self.data, str):
            return self.data
        return self.data.decode("utf-8", errors="replace")


@dataclass
class TransportConfig:
    """Shared knobs for reconnect, heartbeat, and graceful shutdown."""

    url: str = ""
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 30.0
    heartbeat_interval_seconds: float = 15.0
    heartbeat_timeout_seconds: float = 45.0
    max_reconnect_attempts: int = 5
    reconnect_base_delay_seconds: float = 0.25
    reconnect_max_delay_seconds: float = 8.0
    reconnect_jitter_ratio: float = 0.15
    headers: dict[str, str] = field(default_factory=dict)
    # Never put secrets into diagnostics — headers may include Authorization.
    redact_headers: bool = True


TransportEmit = Callable[[TransportEvent, dict[str, Any]], None]


class StreamingTransport(ABC):
    """Bidirectional or unidirectional streaming conduit."""

    def __init__(
        self,
        config: TransportConfig | None = None,
        *,
        emit: TransportEmit | None = None,
    ) -> None:
        self._config = config or TransportConfig()
        self._emit = emit
        self._state = TransportState.IDLE
        self._sequence = 0
        self._connected_at: float | None = None
        self._last_message_at: float | None = None
        self._last_heartbeat_at: float | None = None
        self._bytes_sent = 0
        self._bytes_received = 0
        self._reconnect_count = 0

    @property
    @abstractmethod
    def kind(self) -> TransportKind:
        """Transport type identifier."""

    @property
    def state(self) -> TransportState:
        return self._state

    @property
    def config(self) -> TransportConfig:
        return self._config

    @property
    def is_connected(self) -> bool:
        return self._state == TransportState.CONNECTED

    def connect(self) -> None:
        """Open the underlying channel."""
        if self._state in {TransportState.CONNECTED, TransportState.CONNECTING}:
            return
        self._set_state(TransportState.CONNECTING)
        self._fire(TransportEvent.CONNECTING, {"kind": self.kind.value})
        try:
            self._do_connect()
        except Exception as exc:
            self._set_state(TransportState.FAILED)
            self._fire(TransportEvent.ERROR, {"error": type(exc).__name__})
            raise
        self._connected_at = time.perf_counter()
        self._last_message_at = self._connected_at
        self._last_heartbeat_at = self._connected_at
        self._set_state(TransportState.CONNECTED)
        self._fire(
            TransportEvent.CONNECTED,
            {"kind": self.kind.value, "reconnect_count": self._reconnect_count},
        )

    def send(self, data: bytes | str, *, binary: bool | None = None) -> int:
        """Send one frame; returns sequence number."""
        self._ensure_connected()
        is_binary = binary if binary is not None else isinstance(data, (bytes, bytearray))
        payload = data if isinstance(data, (bytes, bytearray)) else data.encode("utf-8")
        seq = self._sequence
        self._sequence += 1
        self._do_send(bytes(payload), binary=is_binary, sequence=seq)
        self._bytes_sent += len(payload)
        return seq

    def receive(self, *, timeout: float | None = None) -> TransportMessage | None:
        """Receive one frame or None on timeout."""
        self._ensure_connected()
        message = self._do_receive(timeout=timeout)
        if message is None:
            return None
        self._last_message_at = time.perf_counter()
        self._bytes_received += len(message.as_bytes())
        self._fire(
            TransportEvent.MESSAGE,
            {"bytes": len(message.as_bytes()), "binary": message.binary},
        )
        return message

    def heartbeat(self) -> None:
        """Send / record a keepalive pulse."""
        if not self.is_connected:
            return
        self._do_heartbeat()
        self._last_heartbeat_at = time.perf_counter()
        self._fire(TransportEvent.HEARTBEAT, {"kind": self.kind.value})

    def check_liveness(self) -> bool:
        """Return False when heartbeat or read window has expired."""
        if not self.is_connected:
            return False
        now = time.perf_counter()
        timeout = self._config.heartbeat_timeout_seconds
        last = self._last_heartbeat_at or self._last_message_at or self._connected_at
        if last is None:
            return False
        if (now - last) > timeout:
            self._fire(TransportEvent.TIMEOUT, {"idle_seconds": round(now - last, 3)})
            return False
        return True

    def disconnect(self, *, reason: str = "client_close") -> None:
        """Graceful shutdown — idempotent."""
        if self._state in {TransportState.CLOSED, TransportState.CLOSING}:
            return
        self._set_state(TransportState.CLOSING)
        try:
            self._do_disconnect(reason=reason)
        finally:
            self._set_state(TransportState.CLOSED)
            self._fire(TransportEvent.CLOSED, {"reason": reason})

    def mark_disconnected(self, *, reason: str = "provider_disconnect") -> None:
        """Signal unexpected disconnect without full teardown."""
        if self._state == TransportState.CLOSED:
            return
        self._set_state(TransportState.FAILED)
        self._fire(TransportEvent.DISCONNECTED, {"reason": reason})

    def mark_reconnecting(self) -> None:
        self._reconnect_count += 1
        self._set_state(TransportState.RECONNECTING)
        self._fire(
            TransportEvent.RECONNECTING,
            {"attempt": self._reconnect_count},
        )

    def mark_recovered(self) -> None:
        self._set_state(TransportState.CONNECTED)
        self._connected_at = time.perf_counter()
        self._last_message_at = self._connected_at
        self._last_heartbeat_at = self._connected_at
        self._fire(
            TransportEvent.RECOVERED,
            {"attempt": self._reconnect_count},
        )

    def metrics(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "state": self._state.value,
            "bytes_sent": self._bytes_sent,
            "bytes_received": self._bytes_received,
            "reconnect_count": self._reconnect_count,
            "sequence": self._sequence,
        }

    def _ensure_connected(self) -> None:
        if not self.is_connected:
            from voice.exceptions import VoiceProviderError

            raise VoiceProviderError(
                f"Transport {self.kind.value} is not connected (state={self._state.value})"
            )

    def _set_state(self, state: TransportState) -> None:
        self._state = state

    def _fire(self, event: TransportEvent, payload: dict[str, Any]) -> None:
        if self._emit is None:
            return
        try:
            self._emit(event, payload)
        except Exception:
            pass

    @abstractmethod
    def _do_connect(self) -> None:
        ...

    @abstractmethod
    def _do_send(self, data: bytes, *, binary: bool, sequence: int) -> None:
        ...

    @abstractmethod
    def _do_receive(self, *, timeout: float | None) -> TransportMessage | None:
        ...

    def _do_heartbeat(self) -> None:
        """Default heartbeat sends a lightweight ping frame."""
        self._do_send(b"ping", binary=False, sequence=self._sequence)
        self._sequence += 1

    @abstractmethod
    def _do_disconnect(self, *, reason: str) -> None:
        ...
