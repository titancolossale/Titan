# =====================================
# Titan Silence / End-of-Turn Detection
# =====================================

"""Production silence detection for automatic end-of-turn (Phase 20.7).

Builds on VAD energy with:
- automatic end-of-turn after speech + silence
- long-pause timeout (session idle hint)
- background noise tolerance
- false speech rejection (clicks / short bursts)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from voice.vad import (
    VADConfig,
    VADEvent,
    VADResult,
    VoiceActivityDetector,
    estimate_chunk_duration_seconds,
    estimate_chunk_energy,
)


class SilenceDecision(str, Enum):
    """High-level silence / turn decisions for live capture."""

    CONTINUE = "continue"
    END_OF_TURN = "end_of_turn"
    LONG_PAUSE = "long_pause"
    FALSE_SPEECH = "false_speech"
    NOISE_ONLY = "noise_only"


@dataclass
class SilenceDetectorConfig:
    """Silence / end-of-turn tunables."""

    end_of_turn_silence_seconds: float = 1.2
    long_pause_timeout_seconds: float = 8.0
    false_speech_max_seconds: float = 0.22
    false_speech_max_energy: float = 0.08
    background_noise_tolerance: float = 0.012
    require_min_utterance: bool = True
    min_utterance_duration_seconds: float = 0.35

    def to_dict(self) -> dict[str, Any]:
        return {
            "end_of_turn_silence_seconds": self.end_of_turn_silence_seconds,
            "long_pause_timeout_seconds": self.long_pause_timeout_seconds,
            "false_speech_max_seconds": self.false_speech_max_seconds,
            "false_speech_max_energy": self.false_speech_max_energy,
            "background_noise_tolerance": self.background_noise_tolerance,
            "require_min_utterance": self.require_min_utterance,
            "min_utterance_duration_seconds": self.min_utterance_duration_seconds,
        }


@dataclass(frozen=True)
class SilenceResult:
    """Result of one silence-detector step."""

    decision: SilenceDecision
    vad: VADResult
    pause_seconds: float
    speech_seconds: float
    noise_floor: float
    rejected: bool = False
    reject_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "vad": self.vad.to_dict(),
            "pause_seconds": round(self.pause_seconds, 4),
            "speech_seconds": round(self.speech_seconds, 4),
            "noise_floor": round(self.noise_floor, 6),
            "rejected": self.rejected,
            "reject_reason": self.reject_reason,
        }


class SilenceDetector:
    """Stateful silence / end-of-turn detector over streaming chunks."""

    def __init__(
        self,
        *,
        config: SilenceDetectorConfig | None = None,
        vad: VoiceActivityDetector | None = None,
        vad_config: VADConfig | None = None,
    ) -> None:
        self.config = config or SilenceDetectorConfig()
        if vad is not None:
            self._vad = vad
        else:
            cfg = vad_config or VADConfig(
                silence_timeout_seconds=self.config.end_of_turn_silence_seconds,
                background_noise_tolerance=self.config.background_noise_tolerance,
                min_utterance_duration_seconds=self.config.min_utterance_duration_seconds,
            )
            # Keep VAD silence aligned with end-of-turn config.
            cfg.silence_timeout_seconds = self.config.end_of_turn_silence_seconds
            cfg.background_noise_tolerance = max(
                cfg.background_noise_tolerance,
                self.config.background_noise_tolerance,
            )
            self._vad = VoiceActivityDetector(cfg)
        self._pause_seconds = 0.0
        self._speech_seconds = 0.0
        self._peak_speech_energy = 0.0
        self._had_speech = False

    @property
    def vad(self) -> VoiceActivityDetector:
        return self._vad

    @property
    def noise_floor(self) -> float:
        return float(getattr(self._vad, "_noise_floor", self.config.background_noise_tolerance))

    def reset(self) -> None:
        self._vad.reset()
        self._pause_seconds = 0.0
        self._speech_seconds = 0.0
        self._peak_speech_energy = 0.0
        self._had_speech = False

    def apply_thresholds(
        self,
        *,
        speech_start: float | None = None,
        speech_end: float | None = None,
        noise_floor: float | None = None,
    ) -> None:
        """Apply mic-calibration thresholds without resetting speech state."""
        if speech_start is not None:
            self._vad.config.speech_start_threshold = max(0.005, speech_start)
        if speech_end is not None:
            self._vad.config.speech_end_threshold = max(0.003, speech_end)
        if noise_floor is not None:
            self._vad.config.background_noise_tolerance = max(0.002, noise_floor)
            self._vad._noise_floor = max(self._vad._noise_floor, noise_floor)

    def process_chunk(self, audio_bytes: bytes) -> SilenceResult:
        """Process one audio chunk and return silence / turn decision."""
        vad_result = self._vad.process_chunk(audio_bytes)
        duration = estimate_chunk_duration_seconds(audio_bytes, self._vad.config)
        if duration <= 0:
            duration = self._vad.config.frame_duration_seconds
        energy = vad_result.energy

        if vad_result.event == VADEvent.SPEECH_START:
            self._had_speech = True
            self._speech_seconds = vad_result.utterance_duration_seconds
            self._peak_speech_energy = energy
            self._pause_seconds = 0.0
            return SilenceResult(
                decision=SilenceDecision.CONTINUE,
                vad=vad_result,
                pause_seconds=0.0,
                speech_seconds=self._speech_seconds,
                noise_floor=self.noise_floor,
            )

        if vad_result.event in {VADEvent.SPEECH_CONTINUE, VADEvent.SPEECH_END}:
            self._had_speech = True
            self._speech_seconds = max(
                self._speech_seconds, vad_result.utterance_duration_seconds
            )
            self._peak_speech_energy = max(self._peak_speech_energy, energy)

        if vad_result.event == VADEvent.SPEECH_END:
            # VAD already applied silence_timeout — check false speech.
            if self._is_false_speech(self._speech_seconds, self._peak_speech_energy):
                result = SilenceResult(
                    decision=SilenceDecision.FALSE_SPEECH,
                    vad=vad_result,
                    pause_seconds=0.0,
                    speech_seconds=self._speech_seconds,
                    noise_floor=self.noise_floor,
                    rejected=True,
                    reject_reason="false_speech",
                )
                self._speech_seconds = 0.0
                self._peak_speech_energy = 0.0
                self._had_speech = False
                self._pause_seconds = 0.0
                return result
            if (
                self.config.require_min_utterance
                and self._speech_seconds < self.config.min_utterance_duration_seconds
            ):
                result = SilenceResult(
                    decision=SilenceDecision.FALSE_SPEECH,
                    vad=vad_result,
                    pause_seconds=0.0,
                    speech_seconds=self._speech_seconds,
                    noise_floor=self.noise_floor,
                    rejected=True,
                    reject_reason="too_short",
                )
                self._speech_seconds = 0.0
                self._peak_speech_energy = 0.0
                self._had_speech = False
                return result
            speech = self._speech_seconds
            self._speech_seconds = 0.0
            self._peak_speech_energy = 0.0
            self._pause_seconds = 0.0
            return SilenceResult(
                decision=SilenceDecision.END_OF_TURN,
                vad=vad_result,
                pause_seconds=0.0,
                speech_seconds=speech,
                noise_floor=self.noise_floor,
                rejected=vad_result.rejected,
                reject_reason=vad_result.reject_reason,
            )

        # Silence path.
        if energy <= self.noise_floor + self.config.background_noise_tolerance:
            self._pause_seconds += duration
        else:
            # Residual noise above floor but below speech — tolerate.
            self._pause_seconds += duration * 0.5

        if not self._had_speech and self._pause_seconds >= self.config.long_pause_timeout_seconds:
            return SilenceResult(
                decision=SilenceDecision.LONG_PAUSE,
                vad=vad_result,
                pause_seconds=self._pause_seconds,
                speech_seconds=0.0,
                noise_floor=self.noise_floor,
            )

        if (
            not self._had_speech
            and energy > self.noise_floor + self.config.background_noise_tolerance
            and energy < self._vad.config.effective_start_threshold()
        ):
            return SilenceResult(
                decision=SilenceDecision.NOISE_ONLY,
                vad=vad_result,
                pause_seconds=self._pause_seconds,
                speech_seconds=0.0,
                noise_floor=self.noise_floor,
            )

        return SilenceResult(
            decision=SilenceDecision.CONTINUE,
            vad=vad_result,
            pause_seconds=self._pause_seconds,
            speech_seconds=self._speech_seconds,
            noise_floor=self.noise_floor,
        )

    def reject_false_speech(self, audio_bytes: bytes) -> tuple[bool, str | None]:
        """Post-hoc reject clicks / short bursts after assembly."""
        ok, reason = self._vad.validate_utterance(audio_bytes)
        if not ok:
            return True, reason
        duration = estimate_chunk_duration_seconds(audio_bytes, self._vad.config)
        energy = estimate_chunk_energy(
            audio_bytes,
            sample_width=self._vad.config.assumed_sample_width_bytes,
        )
        if self._is_false_speech(duration, energy):
            return True, "false_speech"
        return False, None

    def _is_false_speech(self, duration: float, peak_energy: float) -> bool:
        return (
            duration > 0
            and duration <= self.config.false_speech_max_seconds
            and peak_energy <= self.config.false_speech_max_energy
        )


def silence_detector_config_from_settings() -> SilenceDetectorConfig:
    """Build silence config from settings with VAD-aligned defaults."""
    try:
        from config import settings as app_settings
    except Exception:
        return SilenceDetectorConfig()
    end = float(
        getattr(
            app_settings,
            "TITAN_VOICE_VAD_SILENCE_TIMEOUT",
            getattr(app_settings, "TITAN_VOICE_SILENCE_TIMEOUT", 1.2),
        )
    )
    return SilenceDetectorConfig(
        end_of_turn_silence_seconds=end,
        long_pause_timeout_seconds=float(
            getattr(app_settings, "TITAN_VOICE_LONG_PAUSE_TIMEOUT", 8.0)
        ),
        false_speech_max_seconds=float(
            getattr(app_settings, "TITAN_VOICE_FALSE_SPEECH_MAX", 0.22)
        ),
        background_noise_tolerance=float(
            getattr(app_settings, "TITAN_VOICE_VAD_NOISE_TOLERANCE", 0.012)
        ),
        min_utterance_duration_seconds=float(
            getattr(app_settings, "TITAN_VOICE_VAD_MIN_UTTERANCE", 0.35)
        ),
    )
