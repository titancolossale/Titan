# =====================================
# Titan Voice Models
# =====================================

"""Data models for Voice Runtime V1."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


class VoiceState(str, Enum):
    """Runtime voice activity state."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    PAUSED = "paused"
    ERROR = "error"


class ConversationMode(str, Enum):
    """How the runtime captures user speech."""

    CONTINUOUS = "continuous"
    SINGLE_SHOT = "single_shot"
    PUSH_TO_TALK = "push_to_talk"
    WAKE_WORD = "wake_word"  # reserved — not active in V1


@dataclass
class VoiceConfig:
    """Runtime voice configuration (settings + per-session overrides)."""

    language: str = "fr-FR"
    voice: str = "default"
    speed: float = 0.95
    volume: float = 1.0
    stt_provider: str = "mock"
    tts_provider: str = "mock"
    microphone_device: str = "default"
    speaker_device: str = "default"
    silence_timeout_seconds: float = 2.0
    conversation_mode: ConversationMode = ConversationMode.SINGLE_SHOT

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["conversation_mode"] = self.conversation_mode.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VoiceConfig:
        mode_raw = data.get("conversation_mode", ConversationMode.SINGLE_SHOT.value)
        mode = ConversationMode(mode_raw) if isinstance(mode_raw, str) else ConversationMode.SINGLE_SHOT
        return cls(
            language=str(data.get("language", "fr-FR")),
            voice=str(data.get("voice", "default")),
            speed=float(data.get("speed", 0.95)),
            volume=float(data.get("volume", 1.0)),
            stt_provider=str(data.get("stt_provider", "mock")),
            tts_provider=str(data.get("tts_provider", "mock")),
            microphone_device=str(data.get("microphone_device", "default")),
            speaker_device=str(data.get("speaker_device", "default")),
            silence_timeout_seconds=float(data.get("silence_timeout_seconds", 2.0)),
            conversation_mode=mode,
        )


@dataclass
class ConversationTurn:
    """Single user/assistant exchange in a voice session."""

    user_text: str
    assistant_text: str
    timestamp: datetime = field(default_factory=_utc_now)
    brain_duration_seconds: float = 0.0
    stt_duration_seconds: float = 0.0
    tts_duration_seconds: float = 0.0
    total_latency_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_text": self.user_text,
            "assistant_text": self.assistant_text,
            "timestamp": _iso(self.timestamp),
            "brain_duration_seconds": round(self.brain_duration_seconds, 4),
            "stt_duration_seconds": round(self.stt_duration_seconds, 4),
            "tts_duration_seconds": round(self.tts_duration_seconds, 4),
            "total_latency_seconds": round(self.total_latency_seconds, 4),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationTurn:
        ts_raw = data.get("timestamp")
        timestamp = datetime.fromisoformat(ts_raw) if ts_raw else _utc_now()
        return cls(
            user_text=str(data.get("user_text", "")),
            assistant_text=str(data.get("assistant_text", "")),
            timestamp=timestamp,
            brain_duration_seconds=float(data.get("brain_duration_seconds", 0.0)),
            stt_duration_seconds=float(data.get("stt_duration_seconds", 0.0)),
            tts_duration_seconds=float(data.get("tts_duration_seconds", 0.0)),
            total_latency_seconds=float(data.get("total_latency_seconds", 0.0)),
        )


@dataclass
class LatencyMetrics:
    """Per-turn timing breakdown for logging and diagnostics."""

    speech_start: datetime | None = None
    speech_end: datetime | None = None
    transcription_seconds: float = 0.0
    brain_seconds: float = 0.0
    tts_seconds: float = 0.0
    total_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "speech_start": _iso(self.speech_start),
            "speech_end": _iso(self.speech_end),
            "transcription_seconds": round(self.transcription_seconds, 4),
            "brain_seconds": round(self.brain_seconds, 4),
            "tts_seconds": round(self.tts_seconds, 4),
            "total_seconds": round(self.total_seconds, 4),
        }


@dataclass
class VoiceSession:
    """Persistent voice conversation session."""

    conversation_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    ended_at: datetime | None = None
    microphone_device: str = "default"
    speaker_device: str = "default"
    language: str = "fr-FR"
    last_response: str = ""
    conversation_history: list[ConversationTurn] = field(default_factory=list)
    config: VoiceConfig = field(default_factory=VoiceConfig)
    state: VoiceState = VoiceState.IDLE
    active: bool = True

    @property
    def session_duration_seconds(self) -> float:
        end = self.ended_at or _utc_now()
        return max(0.0, (end - self.created_at).total_seconds())

    def add_turn(self, turn: ConversationTurn) -> None:
        self.conversation_history.append(turn)
        self.last_response = turn.assistant_text
        self.updated_at = _utc_now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "ended_at": _iso(self.ended_at),
            "microphone_device": self.microphone_device,
            "speaker_device": self.speaker_device,
            "language": self.language,
            "last_response": self.last_response,
            "conversation_history": [t.to_dict() for t in self.conversation_history],
            "config": self.config.to_dict(),
            "state": self.state.value,
            "active": self.active,
            "session_duration_seconds": round(self.session_duration_seconds, 3),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VoiceSession:
        created = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else _utc_now()
        updated = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else created
        ended_raw = data.get("ended_at")
        ended = datetime.fromisoformat(ended_raw) if ended_raw else None
        history = [
            ConversationTurn.from_dict(item)
            for item in data.get("conversation_history", [])
        ]
        config = VoiceConfig.from_dict(data.get("config", {}))
        state_raw = data.get("state", VoiceState.IDLE.value)
        state = VoiceState(state_raw) if isinstance(state_raw, str) else VoiceState.IDLE
        return cls(
            conversation_id=str(data.get("conversation_id", str(uuid4()))),
            created_at=created,
            updated_at=updated,
            ended_at=ended,
            microphone_device=str(data.get("microphone_device", "default")),
            speaker_device=str(data.get("speaker_device", "default")),
            language=str(data.get("language", "fr-FR")),
            last_response=str(data.get("last_response", "")),
            conversation_history=history,
            config=config,
            state=state,
            active=bool(data.get("active", True)),
        )


@dataclass
class VoiceTurnResult:
    """Structured outcome of one voice turn (STT → Brain → TTS)."""

    session_id: str
    user_text: str
    assistant_text: str
    state: VoiceState
    metrics: LatencyMetrics
    interrupted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_text": self.user_text,
            "assistant_text": self.assistant_text,
            "state": self.state.value,
            "metrics": self.metrics.to_dict(),
            "interrupted": self.interrupted,
        }
