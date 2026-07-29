# =====================================
# Titan Voice Session Statistics
# =====================================

"""Aggregate live-session diagnostics for production soak (Phase 20.7).

Tracks mic calibration, speech duration, provider / brain / TTS latency,
turn duration, and session-level counters — never raw audio or secrets.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TurnStat:
    """One completed (or interrupted) turn summary."""

    turn_index: int
    speech_duration_ms: float = 0.0
    turn_duration_ms: float = 0.0
    mic_latency_ms: float = 0.0
    provider_latency_ms: float = 0.0
    brain_latency_ms: float = 0.0
    tts_latency_ms: float = 0.0
    interrupted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "speech_duration_ms": round(self.speech_duration_ms, 2),
            "turn_duration_ms": round(self.turn_duration_ms, 2),
            "mic_latency_ms": round(self.mic_latency_ms, 2),
            "provider_latency_ms": round(self.provider_latency_ms, 2),
            "brain_latency_ms": round(self.brain_latency_ms, 2),
            "tts_latency_ms": round(self.tts_latency_ms, 2),
            "interrupted": self.interrupted,
        }


@dataclass
class VoiceSessionStatistics:
    """Rolling session statistics for diagnostics and soak reports."""

    session_id: str
    started_at: float = field(default_factory=time.monotonic)
    turns: list[TurnStat] = field(default_factory=list)
    total_speech_ms: float = 0.0
    total_turn_ms: float = 0.0
    barge_in_count: int = 0
    calibration_count: int = 0
    last_noise_floor: float = 0.0
    last_gain_estimate: float = 1.0
    clipping_warnings: int = 0
    low_volume_warnings: int = 0
    end_of_turn_count: int = 0
    long_pause_count: int = 0
    false_speech_rejections: int = 0
    provider_reconnects: int = 0
    network_interruptions: int = 0
    speaker_switches: int = 0

    def record_calibration(
        self,
        *,
        noise_floor: float,
        gain_estimate: float,
        clipping: bool = False,
        low_volume: bool = False,
    ) -> None:
        self.calibration_count += 1
        self.last_noise_floor = noise_floor
        self.last_gain_estimate = gain_estimate
        if clipping:
            self.clipping_warnings += 1
        if low_volume:
            self.low_volume_warnings += 1

    def record_turn(
        self,
        *,
        turn_index: int,
        speech_duration_ms: float = 0.0,
        turn_duration_ms: float = 0.0,
        mic_latency_ms: float = 0.0,
        provider_latency_ms: float = 0.0,
        brain_latency_ms: float = 0.0,
        tts_latency_ms: float = 0.0,
        interrupted: bool = False,
    ) -> TurnStat:
        stat = TurnStat(
            turn_index=turn_index,
            speech_duration_ms=speech_duration_ms,
            turn_duration_ms=turn_duration_ms,
            mic_latency_ms=mic_latency_ms,
            provider_latency_ms=provider_latency_ms,
            brain_latency_ms=brain_latency_ms,
            tts_latency_ms=tts_latency_ms,
            interrupted=interrupted,
        )
        self.turns.append(stat)
        self.total_speech_ms += speech_duration_ms
        self.total_turn_ms += turn_duration_ms
        if interrupted:
            self.barge_in_count += 1
        # Cap history to keep memory bounded during long soaks.
        if len(self.turns) > 500:
            self.turns = self.turns[-250:]
        return stat

    def note_end_of_turn(self) -> None:
        self.end_of_turn_count += 1

    def note_long_pause(self) -> None:
        self.long_pause_count += 1

    def note_false_speech(self) -> None:
        self.false_speech_rejections += 1

    def note_provider_reconnect(self) -> None:
        self.provider_reconnects += 1

    def note_network_interruption(self) -> None:
        self.network_interruptions += 1

    def note_speaker_switch(self) -> None:
        self.speaker_switches += 1

    def averages(self) -> dict[str, float]:
        if not self.turns:
            return {
                "avg_speech_duration_ms": 0.0,
                "avg_turn_duration_ms": 0.0,
                "avg_mic_latency_ms": 0.0,
                "avg_provider_latency_ms": 0.0,
                "avg_brain_latency_ms": 0.0,
                "avg_tts_latency_ms": 0.0,
            }
        n = float(len(self.turns))
        return {
            "avg_speech_duration_ms": round(self.total_speech_ms / n, 2),
            "avg_turn_duration_ms": round(self.total_turn_ms / n, 2),
            "avg_mic_latency_ms": round(
                sum(t.mic_latency_ms for t in self.turns) / n, 2
            ),
            "avg_provider_latency_ms": round(
                sum(t.provider_latency_ms for t in self.turns) / n, 2
            ),
            "avg_brain_latency_ms": round(
                sum(t.brain_latency_ms for t in self.turns) / n, 2
            ),
            "avg_tts_latency_ms": round(
                sum(t.tts_latency_ms for t in self.turns) / n, 2
            ),
        }

    def session_duration_ms(self) -> float:
        return (time.monotonic() - self.started_at) * 1000.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "session_duration_ms": round(self.session_duration_ms(), 2),
            "turn_count": len(self.turns),
            "total_speech_ms": round(self.total_speech_ms, 2),
            "total_turn_ms": round(self.total_turn_ms, 2),
            "barge_in_count": self.barge_in_count,
            "calibration_count": self.calibration_count,
            "last_noise_floor": round(self.last_noise_floor, 6),
            "last_gain_estimate": round(self.last_gain_estimate, 4),
            "clipping_warnings": self.clipping_warnings,
            "low_volume_warnings": self.low_volume_warnings,
            "end_of_turn_count": self.end_of_turn_count,
            "long_pause_count": self.long_pause_count,
            "false_speech_rejections": self.false_speech_rejections,
            "provider_reconnects": self.provider_reconnects,
            "network_interruptions": self.network_interruptions,
            "speaker_switches": self.speaker_switches,
            "averages": self.averages(),
            "recent_turns": [t.to_dict() for t in self.turns[-10:]],
        }
