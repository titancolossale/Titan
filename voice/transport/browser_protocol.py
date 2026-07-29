# =====================================
# Titan Browser ↔ Voice WebSocket Protocol
# =====================================

"""Framed protocol for browser ↔ Titan native voice WebSocket (Phase 20.8).

Supports persistent connection, heartbeat, sequence sync, backpressure
signals, and graceful reconnect via recovery_token. No raw audio is logged.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BrowserFrameType(str, Enum):
    HELLO = "hello"
    HELLO_ACK = "hello_ack"
    AUDIO = "audio"
    EVENT = "event"
    TTS_CHUNK = "tts_chunk"
    HEARTBEAT = "heartbeat"
    HEARTBEAT_ACK = "heartbeat_ack"
    BACKPRESSURE = "backpressure"
    RECOVER = "recover"
    RECOVER_ACK = "recover_ack"
    ERROR = "error"
    CLOSE = "close"
    SYNC = "sync"


@dataclass(frozen=True)
class BrowserFrame:
    """One protocol frame (JSON control or binary audio with header)."""

    type: BrowserFrameType
    sequence: int = 0
    session_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    binary: bytes | None = None

    def to_json_bytes(self) -> bytes:
        body = {
            "type": self.type.value,
            "seq": self.sequence,
            "ts": time.time(),
        }
        if self.session_id:
            body["session_id"] = self.session_id
        if self.payload:
            # Never embed raw audio bytes in JSON control frames.
            safe = {
                k: v
                for k, v in self.payload.items()
                if k not in {"audio", "audio_bytes", "embedding", "embeddings"}
            }
            body["payload"] = safe
        return json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    @classmethod
    def from_json(cls, raw: str | bytes) -> BrowserFrame:
        text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
        data = json.loads(text)
        ftype = BrowserFrameType(str(data.get("type") or "event"))
        return cls(
            type=ftype,
            sequence=int(data.get("seq") or 0),
            session_id=data.get("session_id"),
            payload=dict(data.get("payload") or {}),
        )


@dataclass
class BrowserBackpressureState:
    """Server-side backpressure tracker for uplink audio."""

    max_queue_frames: int = 64
    max_queue_bytes: int = 512_000
    queued_frames: int = 0
    queued_bytes: int = 0
    drop_count: int = 0
    slowdown: bool = False

    def offer(self, byte_count: int) -> bool:
        """Return False when frame should be dropped under backpressure."""
        if (
            self.queued_frames >= self.max_queue_frames
            or self.queued_bytes + byte_count > self.max_queue_bytes
        ):
            self.drop_count += 1
            self.slowdown = True
            return False
        self.queued_frames += 1
        self.queued_bytes += byte_count
        self.slowdown = self.queued_frames > (self.max_queue_frames // 2)
        return True

    def release(self, byte_count: int) -> None:
        self.queued_frames = max(0, self.queued_frames - 1)
        self.queued_bytes = max(0, self.queued_bytes - byte_count)
        if self.queued_frames < (self.max_queue_frames // 4):
            self.slowdown = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "queued_frames": self.queued_frames,
            "queued_bytes": self.queued_bytes,
            "drop_count": self.drop_count,
            "slowdown": self.slowdown,
            "max_queue_frames": self.max_queue_frames,
            "max_queue_bytes": self.max_queue_bytes,
        }


@dataclass
class BrowserStreamSync:
    """Sequence tracking for stream synchronization across reconnects."""

    last_client_seq: int = 0
    last_server_seq: int = 0
    expected_client_seq: int = 0
    gaps: int = 0
    duplicates: int = 0

    def note_client(self, seq: int) -> str:
        """Return 'ok' | 'gap' | 'duplicate'."""
        if seq < self.expected_client_seq:
            self.duplicates += 1
            return "duplicate"
        if seq > self.expected_client_seq and self.expected_client_seq > 0:
            self.gaps += 1
            self.last_client_seq = seq
            self.expected_client_seq = seq + 1
            return "gap"
        self.last_client_seq = seq
        self.expected_client_seq = seq + 1
        return "ok"

    def next_server_seq(self) -> int:
        self.last_server_seq += 1
        return self.last_server_seq

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_client_seq": self.last_client_seq,
            "last_server_seq": self.last_server_seq,
            "expected_client_seq": self.expected_client_seq,
            "gaps": self.gaps,
            "duplicates": self.duplicates,
        }


@dataclass
class BrowserReconnectPolicy:
    """Mirrors voice.transport.reconnect semantics for the browser client."""

    max_attempts: int = 8
    base_delay_seconds: float = 0.3
    max_delay_seconds: float = 10.0
    jitter_ratio: float = 0.2
    heartbeat_interval_seconds: float = 12.0
    heartbeat_timeout_seconds: float = 40.0

    def delay_for_attempt(self, attempt: int) -> float:
        from voice.transport.reconnect import compute_backoff_seconds

        return compute_backoff_seconds(
            attempt,
            base_delay_seconds=self.base_delay_seconds,
            max_delay_seconds=self.max_delay_seconds,
            jitter_ratio=self.jitter_ratio,
        )

    def should_retry(self, attempt: int) -> bool:
        return 0 <= attempt < self.max_attempts

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "base_delay_seconds": self.base_delay_seconds,
            "max_delay_seconds": self.max_delay_seconds,
            "jitter_ratio": self.jitter_ratio,
            "heartbeat_interval_seconds": self.heartbeat_interval_seconds,
            "heartbeat_timeout_seconds": self.heartbeat_timeout_seconds,
        }
