# =====================================
# Titan Voice Latency Tracker
# =====================================

"""End-to-end latency metrics for real-time voice conversations (Phase 20.5–20.7)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationLatencyMetrics:
    """Measured timings for one continuous conversation turn."""

    first_audio_latency_ms: float = 0.0
    first_transcript_latency_ms: float = 0.0
    first_brain_token_ms: float = 0.0
    first_tts_audio_ms: float = 0.0
    total_response_ms: float = 0.0
    conversation_idle_delay_ms: float = 0.0
    stt_ms: float = 0.0
    brain_ms: float = 0.0
    tts_ms: float = 0.0
    interruption_recovery_ms: float = 0.0
    # Phase 20.6 — per-stage optimization marks
    mic_latency_ms: float = 0.0
    provider_latency_ms: float = 0.0
    conversation_turnaround_ms: float = 0.0
    # Phase 20.7 — speech / turn / calibration marks
    speech_duration_ms: float = 0.0
    turn_duration_ms: float = 0.0
    mic_calibration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "first_audio_latency_ms": round(self.first_audio_latency_ms, 2),
            "first_transcript_latency_ms": round(self.first_transcript_latency_ms, 2),
            "first_brain_token_ms": round(self.first_brain_token_ms, 2),
            "first_tts_audio_ms": round(self.first_tts_audio_ms, 2),
            "total_response_ms": round(self.total_response_ms, 2),
            "conversation_idle_delay_ms": round(self.conversation_idle_delay_ms, 2),
            "stt_ms": round(self.stt_ms, 2),
            "brain_ms": round(self.brain_ms, 2),
            "tts_ms": round(self.tts_ms, 2),
            "interruption_recovery_ms": round(self.interruption_recovery_ms, 2),
            "mic_latency_ms": round(self.mic_latency_ms, 2),
            "provider_latency_ms": round(self.provider_latency_ms, 2),
            "conversation_turnaround_ms": round(self.conversation_turnaround_ms, 2),
            "speech_duration_ms": round(self.speech_duration_ms, 2),
            "turn_duration_ms": round(self.turn_duration_ms, 2),
            "mic_calibration_ms": round(self.mic_calibration_ms, 2),
        }


@dataclass
class LatencyTracker:
    """Monotonic clock helper — no polling; marks are event-driven."""

    _origin: float = field(default_factory=time.perf_counter)
    _marks: dict[str, float] = field(default_factory=dict)
    _idle_since: float | None = None
    metrics: ConversationLatencyMetrics = field(
        default_factory=ConversationLatencyMetrics
    )

    def reset(self) -> None:
        self._origin = time.perf_counter()
        self._marks.clear()
        self._idle_since = None
        self.metrics = ConversationLatencyMetrics()

    def mark(self, name: str) -> float:
        elapsed = (time.perf_counter() - self._origin) * 1000.0
        self._marks[name] = elapsed
        return elapsed

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._origin) * 1000.0

    def mark_first_audio(self) -> None:
        if "first_audio" not in self._marks:
            self.metrics.first_audio_latency_ms = self.mark("first_audio")

    def mark_first_transcript(self) -> None:
        if "first_transcript" not in self._marks:
            self.metrics.first_transcript_latency_ms = self.mark("first_transcript")

    def mark_first_brain_token(self, since_brain_start_ms: float | None = None) -> None:
        if "first_brain_token" not in self._marks:
            if since_brain_start_ms is not None:
                self.metrics.first_brain_token_ms = since_brain_start_ms
                self._marks["first_brain_token"] = self.elapsed_ms()
            else:
                self.metrics.first_brain_token_ms = self.mark("first_brain_token")

    def mark_first_tts_audio(self, since_tts_start_ms: float | None = None) -> None:
        if "first_tts_audio" not in self._marks:
            if since_tts_start_ms is not None:
                self.metrics.first_tts_audio_ms = since_tts_start_ms
                self._marks["first_tts_audio"] = self.elapsed_ms()
            else:
                self.metrics.first_tts_audio_ms = self.mark("first_tts_audio")

    def mark_response_complete(self) -> None:
        self.metrics.total_response_ms = self.mark("response_complete")
        self.metrics.conversation_turnaround_ms = self.metrics.total_response_ms

    def mark_mic_latency(self, mic_ms: float) -> None:
        if not self.metrics.mic_latency_ms:
            self.metrics.mic_latency_ms = max(0.0, float(mic_ms))
            self._marks["mic"] = self.metrics.mic_latency_ms

    def mark_provider_latency(self, provider_ms: float) -> None:
        if not self.metrics.provider_latency_ms:
            self.metrics.provider_latency_ms = max(0.0, float(provider_ms))
            self._marks["provider"] = self.metrics.provider_latency_ms

    def mark_stage_durations(
        self,
        *,
        stt_ms: float | None = None,
        brain_ms: float | None = None,
        tts_ms: float | None = None,
    ) -> None:
        if stt_ms is not None:
            self.metrics.stt_ms = stt_ms
        if brain_ms is not None:
            self.metrics.brain_ms = brain_ms
        if tts_ms is not None:
            self.metrics.tts_ms = tts_ms

    def mark_speech_duration(self, speech_ms: float) -> None:
        self.metrics.speech_duration_ms = max(0.0, float(speech_ms))
        self._marks["speech_duration"] = self.metrics.speech_duration_ms

    def mark_turn_duration(self, turn_ms: float) -> None:
        self.metrics.turn_duration_ms = max(0.0, float(turn_ms))
        self._marks["turn_duration"] = self.metrics.turn_duration_ms

    def mark_mic_calibration(self, calibration_ms: float) -> None:
        if not self.metrics.mic_calibration_ms:
            self.metrics.mic_calibration_ms = max(0.0, float(calibration_ms))
            self._marks["mic_calibration"] = self.metrics.mic_calibration_ms

    def mark_interruption_recovery(self, recovery_ms: float) -> None:
        self.metrics.interruption_recovery_ms = max(0.0, float(recovery_ms))
        self._marks["interruption_recovery"] = self.metrics.interruption_recovery_ms

    def enter_idle(self) -> None:
        self._idle_since = time.perf_counter()

    def exit_idle(self) -> float:
        if self._idle_since is None:
            return 0.0
        delay = (time.perf_counter() - self._idle_since) * 1000.0
        self.metrics.conversation_idle_delay_ms = delay
        self._idle_since = None
        return delay

    def to_dict(self) -> dict[str, Any]:
        return self.metrics.to_dict()
