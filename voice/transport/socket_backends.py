# =====================================
# Titan Live WebSocket Socket Backends
# =====================================

"""Production WebSocket backends for outbound provider streams (Phase 20.8).

Uses ``websocket-client`` when installed. Tests and offline mode keep the
in-memory queue backend from ``WebSocketTransport``. Secrets never enter
diagnostics — only connection metadata is exposed.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from voice.exceptions import VoiceProviderError

logger = logging.getLogger(__name__)


def websocket_client_available() -> bool:
    """Return True when the optional websocket-client package is importable."""
    try:
        import websocket  # noqa: F401

        return True
    except ImportError:
        return False


class SyncWebSocketBackend:
    """Thread-safe sync wrapper around websocket-client create_connection."""

    def __init__(self, *, recv_queue_max: int = 256) -> None:
        self._ws: Any | None = None
        self._lock = threading.RLock()
        self._incoming: deque[bytes | str] = deque(maxlen=max(8, recv_queue_max))
        self._connected = False
        self._url = ""
        self._recv_thread: threading.Thread | None = None
        self._stop = threading.Event()

    def connect(self, url: str, *, headers: dict[str, str], timeout: float) -> None:
        try:
            import websocket
        except ImportError as exc:
            raise VoiceProviderError(
                "websocket-client is required for live provider sockets. "
                "Install with: pip install websocket-client"
            ) from exc
        with self._lock:
            if self._connected:
                return
            header_list = [f"{k}: {v}" for k, v in (headers or {}).items()]
            try:
                self._ws = websocket.create_connection(
                    url,
                    header=header_list,
                    timeout=timeout,
                    enable_multithread=True,
                )
            except Exception as exc:
                raise VoiceProviderError(f"Live WebSocket connect failed: {exc}") from exc
            self._url = url
            self._connected = True
            self._stop.clear()
            self._recv_thread = threading.Thread(
                target=self._recv_loop,
                name="titan-ws-recv",
                daemon=True,
            )
            self._recv_thread.start()

    def send(self, data: bytes, *, binary: bool) -> None:
        with self._lock:
            if self._ws is None or not self._connected:
                raise VoiceProviderError("WebSocket backend not connected")
            try:
                if binary:
                    self._ws.send(data, opcode=0x2)  # BINARY
                else:
                    text = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)
                    self._ws.send(text, opcode=0x1)  # TEXT
            except Exception as exc:
                raise VoiceProviderError(f"WebSocket send failed: {exc}") from exc

    def recv(self, *, timeout: float | None) -> bytes | str | None:
        deadline = None if timeout is None else time.perf_counter() + max(0.0, timeout)
        while True:
            with self._lock:
                if self._incoming:
                    return self._incoming.popleft()
                if not self._connected:
                    return None
            if deadline is not None and time.perf_counter() >= deadline:
                return None
            time.sleep(0.005)

    def ping(self) -> None:
        with self._lock:
            if self._ws is None or not self._connected:
                raise VoiceProviderError("WebSocket backend not connected")
            try:
                self._ws.ping()
            except Exception as exc:
                raise VoiceProviderError(f"WebSocket ping failed: {exc}") from exc

    def close(self, *, reason: str = "") -> None:
        del reason
        self._stop.set()
        with self._lock:
            ws = self._ws
            self._ws = None
            self._connected = False
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        thread = self._recv_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        self._recv_thread = None

    def metrics(self) -> dict[str, Any]:
        return {
            "connected": self._connected,
            "url_configured": bool(self._url),
            "queued_frames": len(self._incoming),
            "backend": "websocket-client",
        }

    def _recv_loop(self) -> None:
        while not self._stop.is_set():
            ws = self._ws
            if ws is None:
                break
            try:
                # Short timeout so close can interrupt.
                ws.settimeout(0.25)
                raw = ws.recv()
            except Exception:
                if self._stop.is_set() or not self._connected:
                    break
                continue
            if raw is None or raw == "":
                continue
            with self._lock:
                self._incoming.append(raw)


def create_live_socket_factory(*, recv_queue_max: int = 256):
    """Return a socket_factory for WebSocketTransport when client lib is present."""

    def _factory() -> SyncWebSocketBackend:
        if not websocket_client_available():
            raise VoiceProviderError(
                "Live socket factory requires websocket-client package"
            )
        return SyncWebSocketBackend(recv_queue_max=recv_queue_max)

    return _factory


def prefer_live_transport(
    *,
    url: str,
    headers: dict[str, str] | None = None,
    heartbeat_interval: float = 15.0,
    max_reconnect: int = 5,
    use_live: bool = True,
):
    """Build a WebSocketTransport — live backend when keys+package available."""
    from voice.transport.base import TransportConfig
    from voice.transport.websocket_transport import WebSocketTransport

    config = TransportConfig(
        url=url,
        headers=dict(headers or {}),
        heartbeat_interval_seconds=heartbeat_interval,
        max_reconnect_attempts=max_reconnect,
        redact_headers=True,
    )
    if use_live and websocket_client_available():
        return WebSocketTransport(
            config,
            socket_factory=create_live_socket_factory(),
        )
    return WebSocketTransport(config)
