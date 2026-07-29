# =====================================
# Titan HTTP Fallback Streaming Transport
# =====================================

"""Chunked HTTP POST/GET fallback when WebSocket/SSE are unavailable (Phase 20.6)."""

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


HttpPost = Callable[[str, bytes, dict[str, str]], bytes]
HttpGet = Callable[[str, dict[str, str]], bytes]


class HttpFallbackTransport(StreamingTransport):
    """Request/response batching that preserves the StreamingTransport API."""

    def __init__(
        self,
        config: TransportConfig | None = None,
        *,
        emit: TransportEmit | None = None,
        http_post: HttpPost | None = None,
        http_get: HttpGet | None = None,
    ) -> None:
        super().__init__(config, emit=emit)
        self._http_post = http_post
        self._http_get = http_get
        self._pending: queue.Queue[TransportMessage] = queue.Queue()
        self._closed = False

    @property
    def kind(self) -> TransportKind:
        return TransportKind.HTTP

    def inject_response(self, data: bytes | str, *, binary: bool = False) -> None:
        """Test / mock helper to enqueue a provider response."""
        self._pending.put(TransportMessage(data=data, binary=binary))

    def _do_connect(self) -> None:
        if not (self._config.url or self._http_post or self._http_get):
            # Offline-safe: allow connect with inject_response path.
            self._closed = False
            return
        self._closed = False

    def _do_send(self, data: bytes, *, binary: bool, sequence: int) -> None:
        del binary, sequence
        if self._closed:
            raise VoiceProviderError("HTTP fallback transport is closed")
        if self._http_post is None:
            # Offline mode — no network; peer responses arrive via inject_response.
            return
        url = self._config.url or ""
        try:
            response = self._http_post(url, data, dict(self._config.headers))
        except Exception as exc:
            raise VoiceProviderError(f"HTTP fallback send failed: {exc}") from exc
        if response:
            self._pending.put(TransportMessage(data=response, binary=True))

    def _do_receive(self, *, timeout: float | None) -> TransportMessage | None:
        if self._closed:
            return None
        # Optionally poll via GET when queue empty.
        if self._pending.empty() and self._http_get is not None:
            try:
                payload = self._http_get(
                    self._config.url or "", dict(self._config.headers)
                )
            except Exception as exc:
                raise VoiceProviderError(f"HTTP fallback poll failed: {exc}") from exc
            if payload:
                return TransportMessage(
                    data=payload, binary=True, received_at=time.perf_counter()
                )
        try:
            return self._pending.get(timeout=timeout if timeout is not None else 0.0)
        except queue.Empty:
            return None

    def _do_heartbeat(self) -> None:
        if self._http_get is None:
            return
        try:
            self._http_get(self._config.url or "", dict(self._config.headers))
        except Exception as exc:
            raise VoiceProviderError(f"HTTP fallback heartbeat failed: {exc}") from exc

    def _do_disconnect(self, *, reason: str) -> None:
        del reason
        self._closed = True

    def metrics(self) -> dict[str, Any]:
        base = super().metrics()
        base["pending"] = self._pending.qsize()
        base["has_post"] = self._http_post is not None
        base["has_get"] = self._http_get is not None
        return base
