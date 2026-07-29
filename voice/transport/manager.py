# =====================================
# Titan Streaming Transport Manager
# =====================================

"""Reconnect, heartbeat, graceful shutdown, and automatic recovery (Phase 20.6)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from voice.exceptions import VoiceProviderError
from voice.transport.base import (
    StreamingTransport,
    TransportEvent,
    TransportKind,
    TransportMessage,
    TransportState,
)
from voice.transport.http_fallback import HttpFallbackTransport
from voice.transport.reconnect import ReconnectPolicy

logger = logging.getLogger(__name__)

ManagerEmit = Callable[[str, dict[str, Any]], None]


@dataclass
class TransportManagerConfig:
    prefer: tuple[TransportKind, ...] = (
        TransportKind.WEBSOCKET,
        TransportKind.SSE,
        TransportKind.HTTP,
    )
    auto_heartbeat: bool = False  # no background threads by default
    auto_recover: bool = True
    sleep: Callable[[float], None] = field(default=time.sleep)


class TransportManager:
    """Owns primary + fallback transports with recovery orchestration.

    Heartbeat and recovery are event-driven (``tick`` / ``ensure_connected``) —
    no always-on polling loops unless the caller opts into ``run_heartbeat_once``.
    """

    def __init__(
        self,
        primary: StreamingTransport,
        *,
        fallbacks: list[StreamingTransport] | None = None,
        config: TransportManagerConfig | None = None,
        reconnect: ReconnectPolicy | None = None,
        emit: ManagerEmit | None = None,
    ) -> None:
        self._primary = primary
        self._fallbacks = list(fallbacks or [])
        self._config = config or TransportManagerConfig()
        self._reconnect = reconnect or ReconnectPolicy.from_config(primary.config)
        self._emit = emit
        self._active: StreamingTransport = primary
        self._lock = threading.RLock()
        self._shutting_down = False
        self._recovery_attempts = 0
        self._last_error: str | None = None

    @property
    def active(self) -> StreamingTransport:
        return self._active

    @property
    def kind(self) -> TransportKind:
        return self._active.kind

    @property
    def state(self) -> TransportState:
        return self._active.state

    @property
    def is_connected(self) -> bool:
        return self._active.is_connected

    def connect(self) -> StreamingTransport:
        """Connect preferred transport, falling back on failure."""
        with self._lock:
            self._shutting_down = False
            candidates = [self._primary, *self._fallbacks]
            last_exc: Exception | None = None
            for transport in candidates:
                try:
                    transport.connect()
                    self._active = transport
                    self._recovery_attempts = 0
                    self._last_error = None
                    self._fire(
                        "PROVIDER_TRANSPORT_CONNECTED",
                        {"kind": transport.kind.value},
                    )
                    return transport
                except Exception as exc:
                    last_exc = exc
                    self._last_error = type(exc).__name__
                    logger.warning(
                        "Transport %s connect failed: %s",
                        transport.kind.value,
                        exc,
                    )
                    try:
                        transport.disconnect(reason="connect_failed")
                    except Exception:
                        pass
            raise VoiceProviderError(
                f"All transports failed to connect: {last_exc}"
            ) from last_exc

    def send(self, data: bytes | str, *, binary: bool | None = None) -> int:
        with self._lock:
            self._ensure_live()
            try:
                return self._active.send(data, binary=binary)
            except Exception as exc:
                self._last_error = type(exc).__name__
                if self._config.auto_recover:
                    self.recover(reason="send_failure")
                    return self._active.send(data, binary=binary)
                raise

    def receive(self, *, timeout: float | None = None) -> TransportMessage | None:
        with self._lock:
            self._ensure_live()
            try:
                return self._active.receive(timeout=timeout)
            except Exception as exc:
                self._last_error = type(exc).__name__
                if self._config.auto_recover:
                    self.recover(reason="receive_failure")
                    return self._active.receive(timeout=timeout)
                raise

    def heartbeat(self) -> None:
        with self._lock:
            if not self._active.is_connected:
                return
            self._active.heartbeat()

    def tick(self) -> bool:
        """Event-driven liveness check — recovers when heartbeat window expires."""
        with self._lock:
            if self._shutting_down:
                return False
            if self._active.is_connected and self._active.check_liveness():
                if self._config.auto_heartbeat:
                    self._active.heartbeat()
                return True
            if self._config.auto_recover:
                return self.recover(reason="liveness_timeout")
            return False

    def recover(self, *, reason: str = "unknown") -> bool:
        """Automatic reconnect with fallback chain."""
        with self._lock:
            if self._shutting_down:
                return False
            self._fire(
                "PROVIDER_TRANSPORT_RECOVERING",
                {"reason": reason, "attempt": self._recovery_attempts},
            )
            try:
                self._active.disconnect(reason=f"recover:{reason}")
            except Exception:
                pass

            attempt = 0
            while self._reconnect.should_retry(attempt):
                delay = self._reconnect.delay_for_attempt(attempt)
                if delay > 0:
                    self._config.sleep(delay)
                self._active.mark_reconnecting()
                try:
                    self._active.connect()
                    self._active.mark_recovered()
                    self._recovery_attempts += 1
                    self._fire(
                        "PROVIDER_TRANSPORT_RECOVERED",
                        {
                            "reason": reason,
                            "kind": self._active.kind.value,
                            "attempt": attempt + 1,
                        },
                    )
                    return True
                except Exception as exc:
                    self._last_error = type(exc).__name__
                    attempt += 1
                    logger.warning(
                        "Transport recover attempt %s failed: %s", attempt, exc
                    )

            # Try fallback transports.
            for fallback in self._fallbacks:
                if fallback is self._active:
                    continue
                try:
                    fallback.connect()
                    self._active = fallback
                    self._recovery_attempts += 1
                    self._fire(
                        "PROVIDER_TRANSPORT_FALLBACK",
                        {"kind": fallback.kind.value, "reason": reason},
                    )
                    return True
                except Exception as exc:
                    self._last_error = type(exc).__name__
                    logger.warning(
                        "Fallback transport %s failed: %s",
                        fallback.kind.value,
                        exc,
                    )

            self._fire(
                "PROVIDER_TRANSPORT_FAILED",
                {"reason": reason, "error": self._last_error},
            )
            return False

    def switch_to(self, kind: TransportKind) -> StreamingTransport:
        """Manual provider/transport switching."""
        with self._lock:
            candidates = [self._primary, *self._fallbacks]
            for transport in candidates:
                if transport.kind != kind:
                    continue
                if self._active is not transport and self._active.is_connected:
                    try:
                        self._active.disconnect(reason="manual_switch")
                    except Exception:
                        pass
                if not transport.is_connected:
                    transport.connect()
                self._active = transport
                self._fire(
                    "PROVIDER_TRANSPORT_SWITCHED",
                    {"kind": kind.value},
                )
                return transport
            raise VoiceProviderError(f"No transport registered for kind={kind.value}")

    def shutdown(self) -> None:
        """Graceful shutdown of all transports."""
        with self._lock:
            self._shutting_down = True
            for transport in [self._active, self._primary, *self._fallbacks]:
                try:
                    transport.disconnect(reason="graceful_shutdown")
                except Exception as exc:
                    logger.debug("Transport shutdown error: %s", exc)
            self._fire("PROVIDER_TRANSPORT_CLOSED", {"reason": "graceful_shutdown"})

    def metrics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active_kind": self._active.kind.value,
                "active_state": self._active.state.value,
                "recovery_attempts": self._recovery_attempts,
                "last_error": self._last_error,
                "shutting_down": self._shutting_down,
                "active": self._active.metrics(),
                "fallback_kinds": [t.kind.value for t in self._fallbacks],
            }

    def ensure_http_fallback(self) -> HttpFallbackTransport:
        """Attach an HTTP fallback if none exists (idempotent helper)."""
        with self._lock:
            for transport in self._fallbacks:
                if isinstance(transport, HttpFallbackTransport):
                    return transport
            http = HttpFallbackTransport(self._primary.config)
            self._fallbacks.append(http)
            return http

    def _ensure_live(self) -> None:
        if self._shutting_down:
            raise VoiceProviderError("Transport manager is shut down")
        if not self._active.is_connected:
            if self._config.auto_recover:
                if not self.recover(reason="not_connected"):
                    raise VoiceProviderError("Transport recovery failed")
            else:
                raise VoiceProviderError("Transport is not connected")

    def _fire(self, event: str, payload: dict[str, Any]) -> None:
        if self._emit is None:
            return
        try:
            self._emit(event, payload)
        except Exception:
            pass
