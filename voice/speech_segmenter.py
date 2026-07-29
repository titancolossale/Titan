# =====================================
# Titan Speech Segmenter
# =====================================

"""Build ordered utterances from streaming audio chunks (Phase 20.3).

Guarantees: no chunk duplication, ordered assembly, bounded buffering,
and cleanup after completion / cancellation / disconnect / failure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from voice.exceptions import VoiceConfigurationError
from voice.vad import VADConfig, VADEvent, VoiceActivityDetector

logger = logging.getLogger(__name__)


@dataclass
class AudioChunk:
    """One ordered microphone chunk."""

    sequence: int
    data: bytes
    timestamp_ms: float | None = None


@dataclass
class UtteranceBuffer:
    """In-progress or finalized utterance."""

    chunks: list[bytes] = field(default_factory=list)
    sequences: list[int] = field(default_factory=list)
    started: bool = False
    finalized: bool = False
    reject_reason: str | None = None

    @property
    def size_bytes(self) -> int:
        return sum(len(c) for c in self.chunks)

    def assemble(self) -> bytes:
        return b"".join(self.chunks)

    def clear(self) -> None:
        self.chunks.clear()
        self.sequences.clear()
        self.started = False
        self.finalized = False
        self.reject_reason = None


class SpeechSegmenter:
    """Streaming speech segmentation with VAD and bounded buffering."""

    def __init__(
        self,
        *,
        vad: VoiceActivityDetector | None = None,
        max_buffer_bytes: int = 2_000_000,
    ) -> None:
        self._vad = vad or VoiceActivityDetector()
        self._max_buffer_bytes = max(64_000, int(max_buffer_bytes))
        self._buffer = UtteranceBuffer()
        self._seen_sequences: set[int] = set()
        self._last_sequence: int | None = None
        self._speech_started = False
        self._input_level = 0.0

    @property
    def vad(self) -> VoiceActivityDetector:
        return self._vad

    @property
    def config(self) -> VADConfig:
        return self._vad.config

    @property
    def speech_detected(self) -> bool:
        return self._speech_started or self._vad.in_speech

    @property
    def input_level(self) -> float:
        return self._input_level

    @property
    def buffered_bytes(self) -> int:
        return self._buffer.size_bytes

    def reset(self) -> None:
        """Cleanup buffers and VAD state."""
        self._buffer.clear()
        self._seen_sequences.clear()
        self._last_sequence = None
        self._speech_started = False
        self._input_level = 0.0
        self._vad.reset()

    def cleanup(self) -> None:
        """Alias for reset — used on cancel / disconnect / failure."""
        self.reset()

    def ingest_chunk(
        self,
        data: bytes,
        *,
        sequence: int,
        timestamp_ms: float | None = None,
    ) -> dict[str, Any]:
        """Ingest one chunk; returns VAD/segment status (never logs audio)."""
        del timestamp_ms  # reserved for future latency metrics
        if sequence in self._seen_sequences:
            return {
                "accepted": False,
                "duplicate": True,
                "reason": "duplicate_chunk",
                "sequence": sequence,
                "speech_detected": self.speech_detected,
                "event": VADEvent.SILENCE.value,
            }
        if self._last_sequence is not None and sequence < self._last_sequence:
            return {
                "accepted": False,
                "duplicate": False,
                "reason": "out_of_order_chunk",
                "sequence": sequence,
                "speech_detected": self.speech_detected,
                "event": VADEvent.SILENCE.value,
            }
        if not isinstance(data, (bytes, bytearray)):
            raise VoiceConfigurationError("Audio chunk must be bytes")
        payload = bytes(data)
        if not payload:
            return {
                "accepted": False,
                "duplicate": False,
                "reason": "empty_chunk",
                "sequence": sequence,
                "speech_detected": self.speech_detected,
                "event": VADEvent.SILENCE.value,
            }

        self._seen_sequences.add(sequence)
        self._last_sequence = sequence
        vad_result = self._vad.process_chunk(payload)
        self._input_level = vad_result.energy

        if vad_result.event == VADEvent.SPEECH_START:
            self._speech_started = True
            self._buffer.started = True
            self._buffer.chunks.append(payload)
            self._buffer.sequences.append(sequence)
        elif vad_result.event == VADEvent.SPEECH_CONTINUE and self._buffer.started:
            self._buffer.chunks.append(payload)
            self._buffer.sequences.append(sequence)
        elif vad_result.event == VADEvent.SPEECH_END:
            if self._buffer.started and not vad_result.rejected:
                self._buffer.chunks.append(payload)
                self._buffer.sequences.append(sequence)
            elif vad_result.rejected:
                self._buffer.reject_reason = vad_result.reject_reason
                self._buffer.clear()
                self._speech_started = False

        if self._buffer.size_bytes > self._max_buffer_bytes:
            logger.warning(
                "Speech buffer overflow size=%d max=%d — truncating oldest",
                self._buffer.size_bytes,
                self._max_buffer_bytes,
            )
            # Drop oldest chunks until under budget (preserve order of remainder).
            while (
                self._buffer.chunks
                and self._buffer.size_bytes > self._max_buffer_bytes
            ):
                self._buffer.chunks.pop(0)
                if self._buffer.sequences:
                    self._buffer.sequences.pop(0)

        return {
            "accepted": True,
            "duplicate": False,
            "reason": None,
            "sequence": sequence,
            "speech_detected": self.speech_detected,
            "event": vad_result.event.value,
            "energy": vad_result.energy,
            "utterance_duration_seconds": vad_result.utterance_duration_seconds,
            "silence_duration_seconds": vad_result.silence_duration_seconds,
            "rejected": vad_result.rejected,
            "reject_reason": vad_result.reject_reason,
            "speech_ended": vad_result.event == VADEvent.SPEECH_END and not vad_result.rejected,
        }

    def force_append(self, data: bytes, *, sequence: int) -> None:
        """Append chunk without VAD (explicit finish / push-to-talk)."""
        if sequence in self._seen_sequences:
            return
        self._seen_sequences.add(sequence)
        self._last_sequence = sequence
        payload = bytes(data)
        if not payload:
            return
        self._buffer.started = True
        self._buffer.chunks.append(payload)
        self._buffer.sequences.append(sequence)
        self._speech_started = True

    def finalize(self) -> bytes:
        """Assemble utterance bytes and clear the active buffer."""
        audio = self._buffer.assemble()
        reason = self._buffer.reject_reason
        sequences = list(self._buffer.sequences)
        self._buffer.clear()
        self._speech_started = False
        self._vad.reset()
        if reason:
            raise VoiceConfigurationError(f"Utterance rejected: {reason}")
        if not audio:
            raise VoiceConfigurationError("Utterance rejected: empty")
        ok, reject = self._vad.validate_utterance(audio)
        if not ok:
            raise VoiceConfigurationError(f"Utterance rejected: {reject}")
        logger.debug(
            "Utterance finalized chunks=%d bytes=%d",
            len(sequences),
            len(audio),
        )
        return audio

    def peek_assemble(self) -> bytes:
        return self._buffer.assemble()
