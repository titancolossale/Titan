# =====================================
# Titan Browser Voice WebSocket Hub
# =====================================

"""Server-side hub for browser ↔ Titan voice WebSocket sessions (Phase 20.8).

Manages connection state, heartbeat liveness, backpressure, stream sync,
and graceful reconnect via recovery_token. Does not redesign the UI —
optional uplink path alongside existing HTTP chunk endpoints.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from voice.diagnostics import emit_voice_diagnostic
from voice.transport.browser_protocol import (
    BrowserBackpressureState,
    BrowserFrame,
    BrowserFrameType,
    BrowserReconnectPolicy,
    BrowserStreamSync,
)

logger = logging.getLogger(__name__)

EmitFn = Callable[[str, dict[str, Any]], None]


class BrowserConnectionState(str, Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DEGRADED = "degraded"
    CLOSING = "closing"
    CLOSED = "closed"
    FAILED = "failed"


@dataclass
class BrowserVoiceConnection:
    """One browser WebSocket attachment bound to a voice session."""

    connection_id: str
    session_id: str | None = None
    recovery_token: str | None = None
    state: BrowserConnectionState = BrowserConnectionState.IDLE
    connected_at: float | None = None
    last_heartbeat_at: float | None = None
    last_message_at: float | None = None
    reconnect_count: int = 0
    bytes_up: int = 0
    bytes_down: int = 0
    sync: BrowserStreamSync = field(default_factory=BrowserStreamSync)
    backpressure: BrowserBackpressureState = field(default_factory=BrowserBackpressureState)
    authenticated_user: str | None = None

    def touch(self) -> None:
        now = time.perf_counter()
        self.last_message_at = now
        if self.last_heartbeat_at is None:
            self.last_heartbeat_at = now

    def note_heartbeat(self) -> None:
        now = time.perf_counter()
        self.last_heartbeat_at = now
        self.last_message_at = now

    def is_alive(self, *, timeout_seconds: float) -> bool:
        if self.state != BrowserConnectionState.CONNECTED:
            return False
        last = self.last_heartbeat_at or self.last_message_at or self.connected_at
        if last is None:
            return False
        return (time.perf_counter() - last) <= timeout_seconds

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "session_id": self.session_id,
            "state": self.state.value,
            "reconnect_count": self.reconnect_count,
            "bytes_up": self.bytes_up,
            "bytes_down": self.bytes_down,
            "authenticated_user": self.authenticated_user,
            "sync": self.sync.to_dict(),
            "backpressure": self.backpressure.to_dict(),
            "alive": self.is_alive(timeout_seconds=40.0),
        }


@dataclass
class BrowserHubConfig:
    heartbeat_interval_seconds: float = 12.0
    heartbeat_timeout_seconds: float = 40.0
    max_queue_frames: int = 64
    max_queue_bytes: int = 512_000
    max_connections: int = 32


class BrowserVoiceHub:
    """Process-scoped registry of browser voice WebSocket connections."""

    def __init__(
        self,
        *,
        config: BrowserHubConfig | None = None,
        reconnect_policy: BrowserReconnectPolicy | None = None,
        emit: EmitFn | None = None,
    ) -> None:
        self._config = config or BrowserHubConfig()
        self._policy = reconnect_policy or BrowserReconnectPolicy(
            heartbeat_interval_seconds=self._config.heartbeat_interval_seconds,
            heartbeat_timeout_seconds=self._config.heartbeat_timeout_seconds,
        )
        self._emit = emit
        self._lock = threading.RLock()
        self._connections: dict[str, BrowserVoiceConnection] = {}
        self._by_session: dict[str, str] = {}

    @property
    def config(self) -> BrowserHubConfig:
        return self._config

    @property
    def reconnect_policy(self) -> BrowserReconnectPolicy:
        return self._policy

    def register(
        self,
        connection_id: str,
        *,
        authenticated_user: str | None = None,
        session_id: str | None = None,
        recovery_token: str | None = None,
    ) -> BrowserVoiceConnection:
        with self._lock:
            if len(self._connections) >= self._config.max_connections:
                raise RuntimeError("Browser voice connection limit reached")
            conn = BrowserVoiceConnection(
                connection_id=connection_id,
                session_id=session_id,
                recovery_token=recovery_token,
                state=BrowserConnectionState.CONNECTING,
                authenticated_user=authenticated_user,
                backpressure=BrowserBackpressureState(
                    max_queue_frames=self._config.max_queue_frames,
                    max_queue_bytes=self._config.max_queue_bytes,
                ),
            )
            self._connections[connection_id] = conn
            if session_id:
                self._by_session[session_id] = connection_id
            self._fire("VOICE_WS_CONNECTING", conn)
            return conn

    def mark_connected(self, connection_id: str) -> BrowserVoiceConnection:
        with self._lock:
            conn = self._require(connection_id)
            now = time.perf_counter()
            conn.state = BrowserConnectionState.CONNECTED
            conn.connected_at = now
            conn.last_heartbeat_at = now
            conn.last_message_at = now
            self._fire("VOICE_WS_CONNECTED", conn)
            return conn

    def bind_session(
        self,
        connection_id: str,
        *,
        session_id: str,
        recovery_token: str | None = None,
    ) -> BrowserVoiceConnection:
        with self._lock:
            conn = self._require(connection_id)
            if conn.session_id and conn.session_id in self._by_session:
                if self._by_session.get(conn.session_id) == connection_id:
                    del self._by_session[conn.session_id]
            conn.session_id = session_id
            if recovery_token:
                conn.recovery_token = recovery_token
            self._by_session[session_id] = connection_id
            return conn

    def recover(
        self,
        connection_id: str,
        *,
        session_id: str,
        recovery_token: str,
        last_client_seq: int = 0,
    ) -> BrowserVoiceConnection:
        """Graceful reconnect — reuse session binding when token matches."""
        with self._lock:
            conn = self._require(connection_id)
            prior_id = self._by_session.get(session_id)
            prior = self._connections.get(prior_id) if prior_id else None
            if prior is not None and prior.recovery_token and prior.recovery_token != recovery_token:
                conn.state = BrowserConnectionState.FAILED
                self._fire("VOICE_WS_RECOVER_FAILED", conn, {"reason": "token_mismatch"})
                raise ValueError("Invalid recovery token")
            conn.session_id = session_id
            conn.recovery_token = recovery_token
            conn.reconnect_count += 1
            conn.state = BrowserConnectionState.CONNECTED
            now = time.perf_counter()
            conn.connected_at = now
            conn.last_heartbeat_at = now
            conn.last_message_at = now
            if last_client_seq > 0:
                conn.sync.last_client_seq = last_client_seq
                conn.sync.expected_client_seq = last_client_seq + 1
            self._by_session[session_id] = connection_id
            self._fire("VOICE_WS_RECOVERED", conn)
            return conn

    def handle_frame(
        self,
        connection_id: str,
        frame: BrowserFrame,
        *,
        binary_bytes: int = 0,
    ) -> list[BrowserFrame]:
        """Process one inbound frame; return outbound reply frames."""
        replies: list[BrowserFrame] = []
        with self._lock:
            conn = self._require(connection_id)
            conn.touch()
            if frame.sequence:
                sync_status = conn.sync.note_client(frame.sequence)
            else:
                sync_status = "ok"

            if frame.type == BrowserFrameType.HEARTBEAT:
                conn.note_heartbeat()
                replies.append(
                    BrowserFrame(
                        type=BrowserFrameType.HEARTBEAT_ACK,
                        sequence=conn.sync.next_server_seq(),
                        session_id=conn.session_id,
                        payload={"ok": True},
                    )
                )
            elif frame.type == BrowserFrameType.HELLO:
                conn.state = BrowserConnectionState.CONNECTED
                now = time.perf_counter()
                conn.connected_at = now
                conn.last_heartbeat_at = now
                replies.append(
                    BrowserFrame(
                        type=BrowserFrameType.HELLO_ACK,
                        sequence=conn.sync.next_server_seq(),
                        session_id=conn.session_id,
                        payload={
                            "ok": True,
                            "policy": self._policy.to_dict(),
                            "backpressure": conn.backpressure.to_dict(),
                        },
                    )
                )
                self._fire("VOICE_WS_CONNECTED", conn)
            elif frame.type == BrowserFrameType.RECOVER:
                session_id = str(frame.payload.get("session_id") or frame.session_id or "")
                token = str(frame.payload.get("recovery_token") or "")
                last_seq = int(frame.payload.get("last_client_seq") or 0)
                try:
                    self.recover(
                        connection_id,
                        session_id=session_id,
                        recovery_token=token,
                        last_client_seq=last_seq,
                    )
                    replies.append(
                        BrowserFrame(
                            type=BrowserFrameType.RECOVER_ACK,
                            sequence=conn.sync.next_server_seq(),
                            session_id=session_id,
                            payload={"ok": True, "sync": conn.sync.to_dict()},
                        )
                    )
                except ValueError as exc:
                    replies.append(
                        BrowserFrame(
                            type=BrowserFrameType.ERROR,
                            sequence=conn.sync.next_server_seq(),
                            payload={"ok": False, "error": str(exc)},
                        )
                    )
            elif frame.type == BrowserFrameType.AUDIO:
                accepted = conn.backpressure.offer(binary_bytes or int(frame.payload.get("bytes") or 0))
                byte_count = binary_bytes or int(frame.payload.get("bytes") or 0)
                conn.bytes_up += byte_count
                if not accepted:
                    self._fire("VOICE_WS_BACKPRESSURE", conn)
                    replies.append(
                        BrowserFrame(
                            type=BrowserFrameType.BACKPRESSURE,
                            sequence=conn.sync.next_server_seq(),
                            session_id=conn.session_id,
                            payload={
                                "slowdown": True,
                                "drop": True,
                                **conn.backpressure.to_dict(),
                            },
                        )
                    )
                elif conn.backpressure.slowdown:
                    replies.append(
                        BrowserFrame(
                            type=BrowserFrameType.BACKPRESSURE,
                            sequence=conn.sync.next_server_seq(),
                            session_id=conn.session_id,
                            payload={"slowdown": True, **conn.backpressure.to_dict()},
                        )
                    )
                else:
                    # Release immediately for protocol-level accounting;
                    # orchestrator owns actual audio processing.
                    conn.backpressure.release(byte_count)
            elif frame.type == BrowserFrameType.SYNC:
                replies.append(
                    BrowserFrame(
                        type=BrowserFrameType.SYNC,
                        sequence=conn.sync.next_server_seq(),
                        session_id=conn.session_id,
                        payload={"sync": conn.sync.to_dict(), "status": sync_status},
                    )
                )
            elif frame.type == BrowserFrameType.CLOSE:
                conn.state = BrowserConnectionState.CLOSING
                self._fire("VOICE_WS_CLOSED", conn, {"reason": "client_close"})

            if sync_status == "gap":
                replies.append(
                    BrowserFrame(
                        type=BrowserFrameType.SYNC,
                        sequence=conn.sync.next_server_seq(),
                        session_id=conn.session_id,
                        payload={"status": "gap", "sync": conn.sync.to_dict()},
                    )
                )
        return replies

    def note_downlink(self, connection_id: str, byte_count: int) -> int:
        with self._lock:
            conn = self._require(connection_id)
            conn.bytes_down += byte_count
            return conn.sync.next_server_seq()

    def mark_reconnecting(self, connection_id: str) -> None:
        with self._lock:
            conn = self._require(connection_id)
            conn.state = BrowserConnectionState.RECONNECTING
            conn.reconnect_count += 1
            self._fire("VOICE_WS_RECONNECTING", conn)

    def close(self, connection_id: str, *, reason: str = "server_close") -> None:
        with self._lock:
            conn = self._connections.pop(connection_id, None)
            if conn is None:
                return
            if conn.session_id and self._by_session.get(conn.session_id) == connection_id:
                del self._by_session[conn.session_id]
            conn.state = BrowserConnectionState.CLOSED
            self._fire("VOICE_WS_CLOSED", conn, {"reason": reason})

    def get(self, connection_id: str) -> BrowserVoiceConnection | None:
        with self._lock:
            return self._connections.get(connection_id)

    def get_by_session(self, session_id: str) -> BrowserVoiceConnection | None:
        with self._lock:
            cid = self._by_session.get(session_id)
            return self._connections.get(cid) if cid else None

    def sweep_stale(self) -> list[str]:
        """Mark / close connections that missed heartbeat timeout."""
        closed: list[str] = []
        with self._lock:
            timeout = self._config.heartbeat_timeout_seconds
            stale = [
                cid
                for cid, conn in self._connections.items()
                if conn.state == BrowserConnectionState.CONNECTED
                and not conn.is_alive(timeout_seconds=timeout)
            ]
            for cid in stale:
                conn = self._connections.get(cid)
                if conn is None:
                    continue
                conn.state = BrowserConnectionState.FAILED
                self._fire("VOICE_WS_TIMEOUT", conn)
                closed.append(cid)
        for cid in closed:
            self.close(cid, reason="heartbeat_timeout")
        return closed

    def diagnostics_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "connection_count": len(self._connections),
                "session_bindings": len(self._by_session),
                "max_connections": self._config.max_connections,
                "policy": self._policy.to_dict(),
                "connections": [c.to_safe_dict() for c in self._connections.values()],
            }

    def _require(self, connection_id: str) -> BrowserVoiceConnection:
        conn = self._connections.get(connection_id)
        if conn is None:
            raise KeyError(f"Unknown browser connection {connection_id}")
        return conn

    def _fire(
        self,
        event: str,
        conn: BrowserVoiceConnection,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "connection_id": conn.connection_id,
            "session_id": conn.session_id,
            "state": conn.state.value,
            "reconnect_count": conn.reconnect_count,
        }
        if extra:
            payload.update(extra)
        if self._emit is not None:
            try:
                self._emit(event, payload)
            except Exception:
                pass
        emit_voice_diagnostic(event, **payload)


_DEFAULT_HUB: BrowserVoiceHub | None = None
_HUB_LOCK = threading.Lock()


def get_browser_voice_hub() -> BrowserVoiceHub:
    global _DEFAULT_HUB
    with _HUB_LOCK:
        if _DEFAULT_HUB is None:
            from config import settings as app_settings

            _DEFAULT_HUB = BrowserVoiceHub(
                config=BrowserHubConfig(
                    heartbeat_interval_seconds=float(
                        getattr(app_settings, "TITAN_VOICE_WS_HEARTBEAT", 12.0)
                    ),
                    heartbeat_timeout_seconds=float(
                        getattr(app_settings, "TITAN_VOICE_WS_HEARTBEAT_TIMEOUT", 40.0)
                    ),
                    max_queue_frames=int(
                        getattr(app_settings, "TITAN_VOICE_WS_BACKPRESSURE_MAX_QUEUE", 64)
                    ),
                    max_queue_bytes=int(
                        getattr(app_settings, "TITAN_VOICE_WS_BACKPRESSURE_MAX_BYTES", 512_000)
                    ),
                    max_connections=int(
                        getattr(app_settings, "TITAN_VOICE_WS_MAX_CONNECTIONS", 32)
                    ),
                )
            )
        return _DEFAULT_HUB


def reset_browser_voice_hub_for_tests() -> None:
    global _DEFAULT_HUB
    with _HUB_LOCK:
        _DEFAULT_HUB = None
