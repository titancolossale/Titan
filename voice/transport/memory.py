# =====================================
# Titan In-Memory Streaming Transport
# =====================================

"""Deterministic duplex transport for tests and offline simulation (Phase 20.6)."""

from __future__ import annotations

import queue
import threading
from typing import Any

from voice.transport.base import (
    StreamingTransport,
    TransportConfig,
    TransportEmit,
    TransportKind,
    TransportMessage,
)


class InMemoryTransport(StreamingTransport):
    """Thread-safe queue pair — peer can inject remote frames via ``peer_push``."""

    def __init__(
        self,
        config: TransportConfig | None = None,
        *,
        emit: TransportEmit | None = None,
        name: str = "memory",
    ) -> None:
        super().__init__(config, emit=emit)
        self._name = name
        self._inbound: queue.Queue[TransportMessage | None] = queue.Queue()
        self._outbound: list[TransportMessage] = []
        self._lock = threading.Lock()
        self._closed = False

    @property
    def kind(self) -> TransportKind:
        return TransportKind.MEMORY

    @property
    def outbound_frames(self) -> list[TransportMessage]:
        with self._lock:
            return list(self._outbound)

    def peer_push(self, data: bytes | str, *, binary: bool | None = None) -> None:
        """Simulate a remote peer sending a frame to this transport."""
        is_binary = binary if binary is not None else isinstance(data, (bytes, bytearray))
        self._inbound.put(
            TransportMessage(data=data, binary=is_binary, sequence=None)
        )

    def peer_close(self) -> None:
        self._inbound.put(None)

    def _do_connect(self) -> None:
        self._closed = False

    def _do_send(self, data: bytes, *, binary: bool, sequence: int) -> None:
        with self._lock:
            if self._closed:
                from voice.exceptions import VoiceProviderError

                raise VoiceProviderError("InMemoryTransport is closed")
            self._outbound.append(
                TransportMessage(data=data, binary=binary, sequence=sequence)
            )

    def _do_receive(self, *, timeout: float | None) -> TransportMessage | None:
        try:
            item = self._inbound.get(timeout=timeout if timeout is not None else 0.0)
        except queue.Empty:
            return None
        if item is None:
            self.mark_disconnected(reason="peer_close")
            return None
        return item

    def _do_disconnect(self, *, reason: str) -> None:
        del reason
        with self._lock:
            self._closed = True
        # Unblock any waiting receivers.
        try:
            self._inbound.put_nowait(None)
        except Exception:
            pass

    def metrics(self) -> dict[str, Any]:
        base = super().metrics()
        base["name"] = self._name
        base["outbound_count"] = len(self.outbound_frames)
        return base
