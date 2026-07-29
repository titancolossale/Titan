# =====================================
# Titan Live Voice Session Orchestrator
# =====================================

"""Real-time voice session lifecycle (Phase 20.3–20.7).

Microphone chunks → VAD / silence → segmentation → incremental STT → speaker
gate → streaming Brain → streaming TTS → playback, with barge-in, mic
calibration, continuity, session recovery, and optional realtime providers.

Reuses Phase 20.1 VoiceRuntime providers and Phase 20.2 speaker profiles.
Does not collect real Nolan/Ibrahim enrollment samples automatically.
Does not enable always-listening.
"""

from __future__ import annotations

import base64
import logging
import struct
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

from config import settings as app_settings
from voice.conversation_engine import (
    ConversationEngineConfig,
    RealtimeConversationEngine,
)
from voice.conversation_flow import (
    ConversationFlowController,
    FlowPhase,
    conversation_flow_config_from_settings,
)
from voice.diagnostics import emit_voice_diagnostic
from voice.exceptions import (
    VoiceConfigurationError,
    VoiceError,
    VoiceProviderError,
    VoiceSessionError,
    VoiceStateError,
)
from voice.mic_calibration import (
    MicCalibrationSnapshot,
    MicCalibrator,
    mic_calibration_config_from_settings,
)
from voice.models import ConversationTurn, LatencyMetrics, VoiceConfig, VoiceSession
from voice.session_lifecycle import LiveSessionState, LiveSessionStateMachine
from voice.session_stats import VoiceSessionStatistics
from voice.silence_detector import (
    SilenceDetector,
    silence_detector_config_from_settings,
)
from voice.speaker_identifier import (
    UNKNOWN_SPEAKER_PROMPT,
    SpeakerIdentificationResult,
    SpeakerIdentifier,
    SpeakerIdentity,
)
from voice.speech_segmenter import SpeechSegmenter
from voice.speech_to_text import SpeechToTextRegistry, get_stt_registry, transcribe_audio
from voice.streaming_brain import StreamingBrainAdapter
from voice.streaming_stt import IncrementalSTTEngine
from voice.streaming_tts import StreamingTTSEngine
from voice.tts_strategy import (
    TTSStrategy,
    TTSStrategyConfig,
    TTSStrategyMode,
    clean_text_for_speech,
)
from voice.vad import VADConfig, VoiceActivityDetector
from voice.voice_runtime import speaker_identifier_from_settings, voice_config_from_settings
from voice.voice_session import VoiceSessionStore
from voice.audio_devices import AudioPlayback, MockAudioPlayback
from voice.enrollment_models import RecognitionBand

if TYPE_CHECKING:
    from brain.brain import Brain
    from core.state_manager import StateManager

logger = logging.getLogger(__name__)

StreamCallback = Callable[[str, dict[str, Any]], None]

RESTRICTED_UNKNOWN_PREFIX = (
    "[VOICE_RESTRICTED] Speaker identity is unknown. "
    "Do not use personal memory, private notes, or private project context. "
    "Respond helpfully but generically.\n\n"
)


def _is_webm_ebml(audio_bytes: bytes) -> bool:
    """True for WebM/Matroska EBML headers (browser MediaRecorder)."""
    return len(audio_bytes) >= 4 and audio_bytes[:4] == b"\x1a\x45\xdf\xa3"


def _reject_malformed_or_unsupported(audio_bytes: bytes) -> None:
    """Raise when a chunk has an unsupported or malformed container.

    WebM/EBML is allowed for browser MediaRecorder → Whisper paths.
    Raw PCM chunks (no container) are also allowed for push-to-talk streaming.
    """
    if not audio_bytes:
        raise VoiceConfigurationError("Utterance rejected: empty_chunk")
    if _is_webm_ebml(audio_bytes):
        return
    head = audio_bytes[:16]
    for magic in (b"ID3", b"fLaC", b"OggS", b"\xff\xfb", b"\xff\xfa"):
        if audio_bytes.startswith(magic) or magic in head:
            raise VoiceConfigurationError(
                "Utterance rejected: unsupported_audio_format"
            )
    if len(audio_bytes) >= 8 and audio_bytes[4:8] == b"ftyp":
        raise VoiceConfigurationError("Utterance rejected: unsupported_audio_format")
    if len(audio_bytes) >= 12 and audio_bytes[:4] == b"RIFF":
        if len(audio_bytes) < 44 or audio_bytes[8:12] != b"WAVE":
            raise VoiceConfigurationError("Utterance rejected: malformed_audio")


def wrap_pcm_as_wav(
    audio_bytes: bytes,
    *,
    sample_rate: int = 16000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """Wrap raw PCM as a minimal WAV when no RIFF/WAVE or WebM container is present.

    Used so browser push-to-talk PCM chunk streams assemble into a Whisper-ready
    utterance without requiring each chunk to carry a WAV header.
    """
    if not audio_bytes:
        return audio_bytes
    if audio_bytes[:4] == b"RIFF" and len(audio_bytes) >= 12 and audio_bytes[8:12] == b"WAVE":
        return audio_bytes
    if _is_webm_ebml(audio_bytes):
        return audio_bytes
    byte_rate = sample_rate * channels * sample_width
    block_align = channels * sample_width
    data_size = len(audio_bytes)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        sample_width * 8,
        b"data",
        data_size,
    )
    return header + audio_bytes


def _tts_chunk_payload(
    session_id: str,
    audio_bytes: bytes,
    *,
    sequence: int,
    mime_type: str = "audio/mpeg",
) -> dict[str, Any]:
    """Build a client-safe TTS audio chunk (base64) with sequence ordering."""
    return {
        "session_id": session_id,
        "sequence": sequence,
        "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
        "mime_type": mime_type,
        "size_bytes": len(audio_bytes),
    }


# Wake-word modes are configurable but never auto-activate always-listening.
class MicCaptureMode:
    PUSH_TO_TALK = "push_to_talk"
    SINGLE_SHOT = "single_shot"
    CONTINUOUS = "continuous"  # Phase 20.5 — VAD multi-turn; not always-listening
    WAKE_WORD = "wake_word"  # prepared, not implemented
    ALWAYS_LISTENING = "always_listening"  # disabled by default; never auto-enable


@dataclass
class LiveSessionLatency:
    """Per-turn latency breakdown (Titan overhead vs provider)."""

    speech_detection_ms: float = 0.0
    utterance_finalization_ms: float = 0.0
    stt_ms: float = 0.0
    speaker_identification_ms: float = 0.0
    brain_first_token_ms: float = 0.0
    tts_first_audio_ms: float = 0.0
    total_voice_turn_ms: float = 0.0
    interruption_recovery_ms: float = 0.0
    titan_overhead_ms: float = 0.0
    provider_latency_ms: float = 0.0
    first_audio_latency_ms: float = 0.0
    first_transcript_latency_ms: float = 0.0
    conversation_idle_delay_ms: float = 0.0
    mic_latency_ms: float = 0.0
    speech_duration_ms: float = 0.0
    turn_duration_ms: float = 0.0
    mic_calibration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "speech_detection_ms": round(self.speech_detection_ms, 2),
            "utterance_finalization_ms": round(self.utterance_finalization_ms, 2),
            "stt_ms": round(self.stt_ms, 2),
            "speaker_identification_ms": round(self.speaker_identification_ms, 2),
            "brain_first_token_ms": round(self.brain_first_token_ms, 2),
            "tts_first_audio_ms": round(self.tts_first_audio_ms, 2),
            "total_voice_turn_ms": round(self.total_voice_turn_ms, 2),
            "interruption_recovery_ms": round(self.interruption_recovery_ms, 2),
            "titan_overhead_ms": round(self.titan_overhead_ms, 2),
            "provider_latency_ms": round(self.provider_latency_ms, 2),
            "first_audio_latency_ms": round(self.first_audio_latency_ms, 2),
            "first_transcript_latency_ms": round(self.first_transcript_latency_ms, 2),
            "conversation_idle_delay_ms": round(self.conversation_idle_delay_ms, 2),
            "mic_latency_ms": round(self.mic_latency_ms, 2),
            "speech_duration_ms": round(self.speech_duration_ms, 2),
            "turn_duration_ms": round(self.turn_duration_ms, 2),
            "mic_calibration_ms": round(self.mic_calibration_ms, 2),
        }


@dataclass
class PendingIdentityConfirmation:
    predicted_user: str | None
    confidence: float
    band: str
    expires_at: float
    reason: str

    @property
    def expired(self) -> bool:
        return time.monotonic() > self.expires_at

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "predicted_user": self.predicted_user,
            "confidence_band": self.band,
            "confidence": round(self.confidence, 4),
            "expires_in_seconds": max(0.0, round(self.expires_at - time.monotonic(), 2)),
            "reason": self.reason,
        }


@dataclass
class LiveVoiceSession:
    """In-memory live session (safe fields only for clients)."""

    session_id: str
    authenticated_user: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    state: LiveSessionState = LiveSessionState.IDLE
    microphone_enabled: bool = True
    capture_mode: str = MicCaptureMode.PUSH_TO_TALK
    wake_word_enabled: bool = False  # never auto-activate
    always_listening: bool = False  # disabled by default
    input_level: float = 0.0
    speech_detected: bool = False
    current_speaker: str | None = None
    identity_confidence_band: str | None = None
    transcription_status: str | None = None
    brain_status: str | None = None
    tts_status: str | None = None
    interrupted: bool = False
    last_transcript: str | None = None
    last_assistant_text: str | None = None
    pending_confirmation: PendingIdentityConfirmation | None = None
    latency: LiveSessionLatency = field(default_factory=LiveSessionLatency)
    conversation_id: str | None = None
    turn_persisted: bool = False
    brain_lock: bool = False
    recovery_token: str | None = None
    continuous_conversation: bool = False
    partial_transcript_preview: str | None = None
    stable_transcript_preview: str | None = None
    stream_events_pending: int = 0
    mic_calibration: dict[str, Any] | None = None
    flow_phase: str | None = None
    session_stats_summary: dict[str, Any] | None = None

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "authenticated_user": self.authenticated_user,
            "conversation_id": self.conversation_id,
            "voice_session_state": self.state.value,
            "voice_input_level": round(self.input_level, 4),
            "voice_speech_detected": self.speech_detected,
            "voice_current_speaker": self.current_speaker,
            "voice_identity_confidence_band": self.identity_confidence_band,
            "voice_transcription_status": self.transcription_status,
            "voice_brain_status": self.brain_status,
            "voice_tts_status": self.tts_status,
            "voice_interrupted": self.interrupted,
            "microphone_enabled": self.microphone_enabled,
            "capture_mode": self.capture_mode,
            "wake_word_enabled": self.wake_word_enabled,
            "always_listening": self.always_listening,
            "continuous_conversation": self.continuous_conversation,
            "recovery_token": self.recovery_token,
            "partial_transcript_preview": self.partial_transcript_preview,
            "stable_transcript_preview": self.stable_transcript_preview,
            "stream_events_pending": self.stream_events_pending,
            "mic_calibration": self.mic_calibration,
            "flow_phase": self.flow_phase,
            "session_stats": self.session_stats_summary,
            "pending_identity_confirmation": (
                self.pending_confirmation.to_safe_dict()
                if self.pending_confirmation
                else None
            ),
            "latency": self.latency.to_dict(),
            "last_transcript_preview": (
                (self.last_transcript[:80] + "…")
                if self.last_transcript and len(self.last_transcript) > 80
                else self.last_transcript
            ),
        }


class LiveVoiceSessionOrchestrator:
    """Authenticated live voice session controller."""

    def __init__(
        self,
        brain: Brain,
        *,
        config: VoiceConfig | None = None,
        vad_config: VADConfig | None = None,
        session_store: VoiceSessionStore | None = None,
        stt_registry: SpeechToTextRegistry | None = None,
        speaker_identifier: SpeakerIdentifier | None = None,
        state_manager: StateManager | None = None,
        audio_playback: AudioPlayback | None = None,
        tts_strategy_config: TTSStrategyConfig | None = None,
        identity_confirmation_timeout_seconds: float | None = None,
        temp_dir: Path | str | None = None,
        provider_timeout_seconds: float | None = None,
        conversation_engine: RealtimeConversationEngine | None = None,
        idle_timeout_seconds: float | None = None,
        conversation_timeout_seconds: float | None = None,
    ) -> None:
        self._brain = brain
        self._config = config or voice_config_from_settings()
        self._vad_config = vad_config or vad_config_from_settings()
        self._session_store = session_store or VoiceSessionStore()
        self._stt_registry = stt_registry or get_stt_registry()
        self._speaker_identifier = speaker_identifier or speaker_identifier_from_settings()
        self._state_manager = state_manager
        self._playback = audio_playback or MockAudioPlayback()
        self._tts_strategy_config = tts_strategy_config or tts_strategy_config_from_settings()
        self._identity_timeout = float(
            identity_confirmation_timeout_seconds
            if identity_confirmation_timeout_seconds is not None
            else getattr(app_settings, "TITAN_VOICE_IDENTITY_CONFIRM_TIMEOUT", 45.0)
        )
        self._provider_timeout = float(
            provider_timeout_seconds
            if provider_timeout_seconds is not None
            else getattr(app_settings, "TITAN_VOICE_PROVIDER_TIMEOUT", 60.0)
        )
        raw_tmp = temp_dir or getattr(
            app_settings, "TITAN_VOICE_LIVE_TEMP_DIR", "data/voice_live_tmp"
        )
        self._temp_dir = Path(raw_tmp)
        self._lock = threading.RLock()
        self._sessions: dict[str, LiveVoiceSession] = {}
        self._segmenters: dict[str, SpeechSegmenter] = {}
        self._machines: dict[str, LiveSessionStateMachine] = {}
        self._tts: dict[str, TTSStrategy] = {}
        self._stream_callbacks: dict[str, StreamCallback] = {}
        self._temp_files: dict[str, list[Path]] = {}
        self._persisted_turn_keys: set[str] = set()
        self._incremental_stt: dict[str, IncrementalSTTEngine] = {}
        self._streaming_tts: dict[str, StreamingTTSEngine] = {}
        self._streaming_brain: dict[str, StreamingBrainAdapter] = {}
        idle_timeout = float(
            idle_timeout_seconds
            if idle_timeout_seconds is not None
            else getattr(app_settings, "TITAN_VOICE_IDLE_TIMEOUT", 90.0)
        )
        conversation_timeout = float(
            conversation_timeout_seconds
            if conversation_timeout_seconds is not None
            else getattr(app_settings, "TITAN_VOICE_CONVERSATION_TIMEOUT", 1800.0)
        )
        recovery_ttl = float(
            getattr(app_settings, "TITAN_VOICE_RECOVERY_TTL", 600.0)
        )
        self._conversation = conversation_engine or RealtimeConversationEngine(
            config=ConversationEngineConfig(
                idle_timeout_seconds=idle_timeout,
                conversation_timeout_seconds=conversation_timeout,
                recovery_ttl_seconds=recovery_ttl,
            ),
            emit=None,
        )
        self._realtime_streaming = bool(
            getattr(app_settings, "TITAN_VOICE_REALTIME_STREAMING", False)
        )
        self._provider_failover: dict[str, Any] = {}
        self._mic_calibrators: dict[str, MicCalibrator] = {}
        self._silence_detectors: dict[str, SilenceDetector] = {}
        self._flow_controllers: dict[str, ConversationFlowController] = {}
        self._session_stats: dict[str, VoiceSessionStatistics] = {}
        self._mic_cal_config = mic_calibration_config_from_settings()
        self._silence_config = silence_detector_config_from_settings()
        self._flow_config = conversation_flow_config_from_settings()
        # Align VAD silence timeout with production silence detector defaults.
        if self._vad_config.silence_timeout_seconds != self._silence_config.end_of_turn_silence_seconds:
            self._vad_config.silence_timeout_seconds = (
                self._silence_config.end_of_turn_silence_seconds
            )

    def _maybe_attach_realtime_providers(
        self,
        session_id: str,
        incremental: IncrementalSTTEngine,
        streaming_tts: StreamingTTSEngine,
    ) -> None:
        """Optionally bind Phase 20.6 realtime STT/TTS providers (config-gated)."""
        if not self._realtime_streaming:
            return
        try:
            from voice.providers.failover import FailoverConfig, StreamingProviderFailover
            from voice.providers.registry_bootstrap import register_realtime_voice_providers

            register_realtime_voice_providers()
            from voice.transport.manager import TransportManager
            from voice.transport.memory import InMemoryTransport

            # Transport manager enables on_network_loss() socket recovery path.
            transport_manager = TransportManager(
                InMemoryTransport(name=f"live-session-{session_id}"),
                emit=lambda e, d, sid=session_id: self._on_stream_event(
                    sid, e if isinstance(e, str) else getattr(e, "value", str(e)), d
                ),
            )
            failover = StreamingProviderFailover(
                preferred_stt=getattr(
                    app_settings,
                    "TITAN_VOICE_REALTIME_STT_PROVIDER",
                    "mock_realtime_stt",
                ),
                preferred_tts=getattr(
                    app_settings,
                    "TITAN_VOICE_REALTIME_TTS_PROVIDER",
                    "mock_realtime_tts",
                ),
                config=FailoverConfig(
                    max_retries=int(
                        getattr(app_settings, "TITAN_VOICE_PROVIDER_RETRY_MAX", 3)
                    ),
                    provider_timeout_seconds=self._provider_timeout,
                    sleep=lambda _s: None,
                ),
                transport_manager=transport_manager,
                emit=lambda e, d, sid=session_id: self._on_stream_event(sid, e, d),
            )
            failover.activate()
            incremental.set_realtime_provider(failover.stt)
            streaming_tts.set_realtime_provider(failover.tts)
            self._provider_failover[session_id] = failover
        except Exception as exc:
            logger.warning(
                "Realtime streaming providers unavailable for %s: %s",
                session_id,
                exc,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_session(
        self,
        *,
        authenticated_user: str,
        capture_mode: str | None = None,
        microphone_enabled: bool = True,
        conversation_id: str | None = None,
        stream_callback: StreamCallback | None = None,
    ) -> dict[str, Any]:
        """Start a live voice session for an authenticated Nolan/Ibrahim user."""
        from context.session_manager import SessionManager

        normalized = SessionManager.normalize_user(authenticated_user)
        if normalized is None:
            raise VoiceSessionError("Authenticated user is not an authorized voice identity")

        mode = (capture_mode or MicCaptureMode.PUSH_TO_TALK).strip().lower()
        if mode == MicCaptureMode.ALWAYS_LISTENING:
            # Hard guard — never activate always-listening automatically.
            mode = MicCaptureMode.PUSH_TO_TALK
            logger.warning("ALWAYS_LISTENING requested — forced to push_to_talk")
        continuous = mode == MicCaptureMode.CONTINUOUS

        with self._lock:
            session_id = str(uuid4())
            live = LiveVoiceSession(
                session_id=session_id,
                authenticated_user=normalized,
                capture_mode=mode,
                microphone_enabled=bool(microphone_enabled),
                wake_word_enabled=False,
                always_listening=False,
                conversation_id=conversation_id,
                continuous_conversation=continuous,
            )
            machine = LiveSessionStateMachine(LiveSessionState.IDLE)
            segmenter = SpeechSegmenter(vad=VoiceActivityDetector(self._vad_config))
            tts = TTSStrategy(
                config=self._tts_strategy_config,
                registry=None,
                provider_id=self._config.tts_provider,
                locale=self._config.language,
                voice=self._config.voice,
                speed=self._config.speed,
                volume=self._config.volume,
            )
            # Persist skeleton via existing VoiceSessionStore.
            persisted = self._session_store.create_session(
                config=self._config,
                conversation_id=conversation_id or session_id,
            )
            live.conversation_id = persisted.conversation_id

            self._sessions[session_id] = live
            self._machines[session_id] = machine
            self._segmenters[session_id] = segmenter
            self._tts[session_id] = tts
            self._temp_files[session_id] = []
            if stream_callback is not None:
                self._stream_callbacks[session_id] = stream_callback

            self._incremental_stt[session_id] = IncrementalSTTEngine(
                locale=self._config.language,
                provider_id=self._config.stt_provider,
                registry=self._stt_registry,
                emit=lambda e, d, sid=session_id: self._on_stream_event(sid, e, d),
            )
            self._streaming_tts[session_id] = StreamingTTSEngine(
                tts,
                strategy_config=self._tts_strategy_config,
                emit=lambda e, d, sid=session_id: self._on_stream_event(sid, e, d),
                default_locale=self._config.language,
            )
            self._maybe_attach_realtime_providers(
                session_id,
                self._incremental_stt[session_id],
                self._streaming_tts[session_id],
            )
            self._streaming_brain[session_id] = StreamingBrainAdapter(
                self._brain,
                emit=lambda e, d, sid=session_id: self._on_stream_event(sid, e, d),
                timeout_seconds=self._provider_timeout,
            )

            bound = self._conversation.bind_session(
                session_id,
                authenticated_user=normalized,
                conversation_id=live.conversation_id or session_id,
                capture_mode=mode,
            )
            live.recovery_token = bound["recovery"]["recovery_token"]

            # Phase 20.7 — mic calibration, silence, conversation flow, stats.
            self._mic_calibrators[session_id] = MicCalibrator(self._mic_cal_config)
            self._silence_detectors[session_id] = SilenceDetector(
                config=self._silence_config,
                vad=segmenter.vad,
            )
            flow = ConversationFlowController(config=self._flow_config)
            flow.bind_continuity(live.recovery_token or session_id)
            flow.on_listening()
            self._flow_controllers[session_id] = flow
            live.flow_phase = flow.phase.value
            stats = VoiceSessionStatistics(session_id=session_id)
            self._session_stats[session_id] = stats
            live.session_stats_summary = {
                "turn_count": 0,
                "session_id": session_id,
            }

            self._set_state(session_id, LiveSessionState.LISTENING)
            live.transcription_status = "idle"
            live.brain_status = "idle"
            live.tts_status = "idle"
            self._sync_workspace(live)
            emit_voice_diagnostic(
                "VOICE_SESSION_STARTED",
                session_id=session_id,
                user=normalized,
                mode=mode,
            )
            emit_voice_diagnostic(
                "VOICE_SESSION_AUTHORIZED",
                session_id=session_id,
                user=normalized,
            )
            self._emit(session_id, "VOICE_SESSION_STARTED", live.to_safe_dict())
            self._emit(session_id, "VOICE_LISTENING", {"session_id": session_id})
            return live.to_safe_dict()

    def submit_audio_chunk(
        self,
        session_id: str,
        *,
        audio_bytes: bytes,
        sequence: int,
        timestamp_ms: float | None = None,
    ) -> dict[str, Any]:
        """Accept one microphone chunk; may auto-finalize on speech end."""
        with self._lock:
            live = self._require_session(session_id)
            if not live.microphone_enabled:
                raise VoiceSessionError("Microphone disabled for this session")
            if live.state in {
                LiveSessionState.CANCELLED,
                LiveSessionState.FAILED,
                LiveSessionState.COMPLETED,
            }:
                raise VoiceSessionError(f"Session is {live.state.value}")

            # Barge-in: speech during SPEAKING stops playback and starts capture.
            if live.state == LiveSessionState.SPEAKING and audio_bytes:
                flow = self._flow_controllers.get(session_id)
                if flow is not None:
                    # Keep flow aligned with live SPEAKING (tests / races).
                    if flow.phase != FlowPhase.ASSISTANT_SPEAKING:
                        flow.on_assistant_speaking()
                        live.flow_phase = flow.phase.value
                    if not flow.can_accept_barge_in():
                        return {
                            "barge_in": False,
                            "debounced": True,
                            **live.to_safe_dict(),
                        }
                self._handle_barge_in(session_id, audio_bytes, sequence)
                return {
                    "barge_in": True,
                    **live.to_safe_dict(),
                }

            if live.state == LiveSessionState.WAITING_FOR_IDENTITY_CONFIRMATION:
                return {
                    "accepted": False,
                    "reason": "awaiting_identity_confirmation",
                    **live.to_safe_dict(),
                }

            segmenter = self._segmenters[session_id]
            detect_started = time.perf_counter()
            # Phase 20.7 — mark mic capture latency from client timestamp when present.
            tracker = self._conversation.get_latency(session_id)
            if timestamp_ms is not None and tracker is not None:
                # Client wall clock is unreliable across machines; treat as relative hint.
                mic_ms = max(0.0, min(5000.0, float(timestamp_ms)))
                if mic_ms > 0:
                    tracker.mark_mic_latency(mic_ms)
                    live.latency.mic_latency_ms = tracker.metrics.mic_latency_ms
            elif tracker is not None and not tracker.metrics.mic_latency_ms:
                # Fallback: local ingest overhead as mic path mark.
                tracker.mark_mic_latency((time.perf_counter() - detect_started) * 1000.0)
                live.latency.mic_latency_ms = tracker.metrics.mic_latency_ms

            # Feed active mic calibration window (non-blocking).
            calibrator = self._mic_calibrators.get(session_id)
            if calibrator is not None and calibrator.active and audio_bytes:
                snap = calibrator.feed(audio_bytes, vad_config=self._vad_config)
                live.mic_calibration = snap.to_dict()
                if snap.calibrated:
                    self._apply_calibration(session_id, snap)

            # Push-to-talk: always buffer accepted chunks; VAD still reports levels.
            if live.capture_mode == MicCaptureMode.PUSH_TO_TALK:
                if not audio_bytes:
                    raise VoiceConfigurationError("Utterance rejected: empty_chunk")
                if sequence in getattr(segmenter, "_seen_sequences", set()):
                    return {
                        "accepted": False,
                        "duplicate": True,
                        "reason": "duplicate_chunk",
                        "sequence": sequence,
                        **live.to_safe_dict(),
                    }
                _reject_malformed_or_unsupported(audio_bytes)
                was_new_speech = live.state == LiveSessionState.LISTENING
                segmenter.force_append(audio_bytes, sequence=sequence)
                vad_result = segmenter.vad.process_chunk(audio_bytes)
                live.input_level = vad_result.energy
                live.speech_detected = True
                if was_new_speech:
                    self._set_state(session_id, LiveSessionState.SPEECH_DETECTED)
                    self._set_state(session_id, LiveSessionState.CAPTURING)
                    flow = self._flow_controllers.get(session_id)
                    if flow is not None:
                        flow.on_speech_start()
                        live.flow_phase = flow.phase.value
                    emit_voice_diagnostic("VOICE_SPEECH_STARTED", session_id=session_id)
                    self._emit(
                        session_id, "VOICE_SPEECH_STARTED", {"session_id": session_id}
                    )
                live.latency.speech_detection_ms = (
                    time.perf_counter() - detect_started
                ) * 1000.0
                self._conversation.touch(session_id)
                self._feed_incremental_stt(session_id, audio_bytes, sequence=sequence)
                emit_voice_diagnostic(
                    "VOICE_AUDIO_CHUNK_RECEIVED",
                    session_id=session_id,
                    sequence=sequence,
                    size_bytes=len(audio_bytes),
                    event=vad_result.event.value,
                )
                self._sync_workspace(live)
                return {
                    "accepted": True,
                    "duplicate": False,
                    "speech_detected": True,
                    "event": vad_result.event.value,
                    **live.to_safe_dict(),
                }

            result = segmenter.ingest_chunk(
                audio_bytes,
                sequence=sequence,
                timestamp_ms=timestamp_ms,
            )
            live.input_level = segmenter.input_level
            live.speech_detected = segmenter.speech_detected
            live.latency.speech_detection_ms = (
                time.perf_counter() - detect_started
            ) * 1000.0
            self._conversation.touch(session_id)
            if result.get("accepted") and not result.get("duplicate"):
                self._feed_incremental_stt(session_id, audio_bytes, sequence=sequence)

            # Phase 20.7 — silence / end-of-turn / long-pause / false-speech.
            silence = self._silence_detectors.get(session_id)
            if silence is not None and audio_bytes and result.get("accepted"):
                event = result.get("event")
                if event == "speech_end" or result.get("speech_ended"):
                    speech_s = float(result.get("utterance_duration_seconds") or 0.0)
                    peak = float(result.get("energy") or live.input_level or 0.0)
                    if silence._is_false_speech(speech_s, peak):
                        stats = self._session_stats.get(session_id)
                        if stats is not None:
                            stats.note_false_speech()
                        emit_voice_diagnostic(
                            "VOICE_FALSE_SPEECH_REJECTED",
                            session_id=session_id,
                            duration_s=round(speech_s, 4),
                        )
                        self._emit(
                            session_id,
                            "VOICE_FALSE_SPEECH_REJECTED",
                            {"session_id": session_id, "reason": "false_speech"},
                        )
                        segmenter.reset()
                        live.speech_detected = False
                        self._set_state(session_id, LiveSessionState.LISTENING)
                        self._sync_workspace(live)
                        return {
                            "accepted": False,
                            "rejected": True,
                            "reject_reason": "false_speech",
                            **live.to_safe_dict(),
                        }
                elif event in {None, "silence"} and live.state == LiveSessionState.LISTENING:
                    pause = float(result.get("silence_duration_seconds") or 0.0)
                    if pause >= self._silence_config.long_pause_timeout_seconds:
                        stats = self._session_stats.get(session_id)
                        if stats is not None:
                            stats.note_long_pause()
                        emit_voice_diagnostic(
                            "VOICE_LONG_PAUSE",
                            session_id=session_id,
                            pause_seconds=round(pause, 3),
                        )
                        self._emit(
                            session_id,
                            "VOICE_LONG_PAUSE",
                            {"session_id": session_id, "pause_seconds": round(pause, 3)},
                        )
                        self._conversation.mark_idle(session_id)

            emit_voice_diagnostic(
                "VOICE_AUDIO_CHUNK_RECEIVED",
                session_id=session_id,
                sequence=sequence,
                size_bytes=len(audio_bytes),
                event=result.get("event"),
            )

            if result.get("duplicate") or not result.get("accepted"):
                self._sync_workspace(live)
                return {**result, **live.to_safe_dict()}

            event = result.get("event")
            if event == "speech_start":
                if live.state == LiveSessionState.LISTENING:
                    self._set_state(session_id, LiveSessionState.SPEECH_DETECTED)
                self._set_state(session_id, LiveSessionState.CAPTURING)
                flow = self._flow_controllers.get(session_id)
                if flow is not None:
                    flow.on_speech_start()
                    live.flow_phase = flow.phase.value
                emit_voice_diagnostic("VOICE_SPEECH_STARTED", session_id=session_id)
                self._emit(session_id, "VOICE_SPEECH_STARTED", {"session_id": session_id})
            elif event == "speech_continue" and live.state in {
                LiveSessionState.SPEECH_DETECTED,
                LiveSessionState.LISTENING,
            }:
                self._set_state(session_id, LiveSessionState.CAPTURING)
            elif result.get("speech_ended"):
                flow = self._flow_controllers.get(session_id)
                if flow is not None:
                    pause_ms = flow.on_natural_pause()
                    flow.on_speech_end()
                    live.flow_phase = flow.phase.value
                    emit_voice_diagnostic(
                        "VOICE_NATURAL_PAUSE",
                        session_id=session_id,
                        pause_ms=pause_ms,
                    )
                    self._emit(
                        session_id,
                        "VOICE_NATURAL_PAUSE",
                        {"session_id": session_id, "pause_ms": pause_ms},
                    )
                stats = self._session_stats.get(session_id)
                if stats is not None:
                    stats.note_end_of_turn()
                emit_voice_diagnostic("VOICE_SPEECH_ENDED", session_id=session_id)
                emit_voice_diagnostic("VOICE_END_OF_TURN", session_id=session_id)
                self._emit(session_id, "VOICE_SPEECH_ENDED", {"session_id": session_id})
                self._emit(session_id, "VOICE_END_OF_TURN", {"session_id": session_id})
                self._sync_workspace(live)
                return self._finalize_and_process(session_id)

            if result.get("rejected") and result.get("reject_reason") == "max_utterance_duration":
                raise VoiceConfigurationError("Utterance rejected: max_utterance_duration")

            self._sync_workspace(live)
            return {**result, **live.to_safe_dict()}

    def finish_utterance(self, session_id: str) -> dict[str, Any]:
        """Explicitly end the current utterance (push-to-talk / client stop)."""
        with self._lock:
            flow = self._flow_controllers.get(session_id)
            if flow is not None:
                flow.on_natural_pause()
                flow.on_speech_end()
                live = self._sessions.get(session_id)
                if live is not None:
                    live.flow_phase = flow.phase.value
            stats = self._session_stats.get(session_id)
            if stats is not None:
                stats.note_end_of_turn()
            emit_voice_diagnostic("VOICE_END_OF_TURN", session_id=session_id, source="client")
            return self._finalize_and_process(session_id)

    def confirm_identity(self, session_id: str, *, user: str | None = None) -> dict[str, Any]:
        """Confirm medium-confidence identity prediction."""
        with self._lock:
            live = self._require_session(session_id)
            pending = live.pending_confirmation
            if pending is None:
                raise VoiceSessionError("No identity confirmation pending")
            if pending.expired:
                live.pending_confirmation = None
                self._set_state(session_id, LiveSessionState.LISTENING)
                raise VoiceSessionError("Identity confirmation expired")
            from voice.identity_security import IdentityAssertionKind
            from context.session_manager import SessionManager

            target = user or pending.predicted_user
            normalized = SessionManager.normalize_user(str(target or ""))
            if normalized is None:
                raise VoiceSessionError("Invalid identity confirmation target")
            result = SpeakerIdentificationResult(
                identity=(
                    SpeakerIdentity.NOLAN
                    if normalized == "Nolan"
                    else SpeakerIdentity.IBRAHIM
                ),
                confidence=1.0,
                requires_confirmation=False,
                reason="ui_confirmation_claimed",
                matched_user=normalized,
                recognition_band=RecognitionBand.MEDIUM,
                threshold=1.0,
                production_trusted=False,
                assertion_kind=IdentityAssertionKind.CLAIMED_IDENTITY,
                decision="claimed",
            )
            self._apply_speaker(session_id, result)
            live.pending_confirmation = None
            flow = self._flow_controllers.get(session_id)
            if flow is not None:
                flow.clear_confirmation()
                live.flow_phase = flow.phase.value
            emit_voice_diagnostic(
                "VOICE_IDENTITY_CONFIRMED",
                session_id=session_id,
                user=normalized,
            )
            self._emit(
                session_id,
                "VOICE_IDENTITY_CONFIRMED",
                {"session_id": session_id, "user": normalized},
            )
            # If we have a held transcript, continue Brain turn.
            if live.last_transcript:
                result = self._run_brain_and_tts(
                    session_id,
                    live.last_transcript,
                    restricted=False,
                )
                self._record_turn_stats(session_id, interrupted=live.interrupted)
                return result
            self._set_state(session_id, LiveSessionState.LISTENING)
            self._sync_workspace(live)
            return live.to_safe_dict()

    def reject_identity(self, session_id: str) -> dict[str, Any]:
        """Reject predicted identity — never persist binding."""
        with self._lock:
            live = self._require_session(session_id)
            live.pending_confirmation = None
            live.current_speaker = None
            live.identity_confidence_band = RecognitionBand.LOW.value
            emit_voice_diagnostic("VOICE_IDENTITY_REJECTED", session_id=session_id)
            self._emit(session_id, "VOICE_IDENTITY_REJECTED", {"session_id": session_id})
            # Continue with restricted unknown path if transcript exists.
            if live.last_transcript:
                return self._run_brain_and_tts(
                    session_id,
                    live.last_transcript,
                    restricted=True,
                )
            self._set_state(session_id, LiveSessionState.LISTENING)
            self._sync_workspace(live)
            return live.to_safe_dict()

    def interrupt_playback(self, session_id: str) -> dict[str, Any]:
        """Stop TTS playback and mark the response interrupted."""
        with self._lock:
            live = self._require_session(session_id)
            started = time.perf_counter()
            prior_state = live.state
            flow = self._flow_controllers.get(session_id)
            # Explicit client interrupt is never debounce-blocked (unlike audio barge-in).
            if flow is not None and prior_state == LiveSessionState.SPEAKING:
                flow.on_barge_in()
                live.flow_phase = flow.phase.value
            self._conversation.cancel_turn(session_id)
            tts = self._tts.get(session_id)
            if tts is not None:
                tts.cancel()
            stream_tts = self._streaming_tts.get(session_id)
            if stream_tts is not None:
                stream_tts.cancel()
            self._playback.stop()
            live.interrupted = True
            live.tts_status = "interrupted"
            live.brain_lock = False
            if prior_state == LiveSessionState.SPEAKING:
                self._set_state(session_id, LiveSessionState.INTERRUPTED)
            recovery_ms = (time.perf_counter() - started) * 1000.0
            live.latency.interruption_recovery_ms = recovery_ms
            tracker = self._conversation.get_latency(session_id)
            if tracker is not None:
                tracker.mark_interruption_recovery(recovery_ms)
            stats = self._session_stats.get(session_id)
            if stats is not None and prior_state in {
                LiveSessionState.SPEAKING,
                LiveSessionState.THINKING,
            }:
                stats.barge_in_count += 1
            emit_voice_diagnostic("VOICE_BARGE_IN", session_id=session_id, source="client")
            self._emit(session_id, "VOICE_BARGE_IN", {"session_id": session_id})
            if flow is not None:
                flow.resume_after_interruption()
                flow.on_listening()
                live.flow_phase = flow.phase.value
                emit_voice_diagnostic(
                    "VOICE_RESUME_AFTER_INTERRUPT",
                    session_id=session_id,
                    grace_ms=flow.config.resume_grace_ms,
                )
                self._emit(
                    session_id,
                    "VOICE_RESUME_AFTER_INTERRUPT",
                    {"session_id": session_id},
                )
            # Client interrupt always returns to listening (idempotent).
            if live.state not in {
                LiveSessionState.CANCELLED,
                LiveSessionState.FAILED,
                LiveSessionState.COMPLETED,
            }:
                self._set_state(session_id, LiveSessionState.LISTENING)
            self._sync_workspace(live)
            return live.to_safe_dict()

    def cancel_session(self, session_id: str) -> dict[str, Any]:
        """Cancel session and release all resources."""
        with self._lock:
            live = self._require_session(session_id)
            self._conversation.cancel_turn(session_id)
            self._release_resources(session_id, final_state=LiveSessionState.CANCELLED)
            emit_voice_diagnostic("VOICE_SESSION_CANCELLED", session_id=session_id)
            self._emit(session_id, "VOICE_SESSION_CANCELLED", {"session_id": session_id})
            self._conversation.close_session(session_id, reason="cancel")
            snapshot = live.to_safe_dict()
            self._drop_session(session_id)
            return snapshot

    def on_client_disconnect(self, session_id: str) -> None:
        """Cleanup buffers and temp audio on client disconnect."""
        with self._lock:
            if session_id not in self._sessions:
                return
            self._conversation.cancel_turn(session_id)
            self._release_resources(session_id, final_state=LiveSessionState.CANCELLED)
            # Soft close — keep recovery token for browser refresh.
            self._conversation.close_session(session_id, reason="client_disconnect")
            self._drop_session(session_id)
            emit_voice_diagnostic(
                "VOICE_SESSION_CANCELLED",
                session_id=session_id,
                reason="client_disconnect",
            )

    def get_safe_state(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            live = self._require_session(session_id)
            timeout = self._conversation.check_timeouts(session_id)
            if timeout == "conversation":
                return self._timeout_close(session_id, reason="conversation_timeout")
            if timeout == "idle":
                return self._timeout_close(session_id, reason="idle_timeout")
            if (
                live.pending_confirmation is not None
                and live.pending_confirmation.expired
            ):
                live.pending_confirmation = None
                if live.state == LiveSessionState.WAITING_FOR_IDENTITY_CONFIRMATION:
                    self._set_state(session_id, LiveSessionState.LISTENING)
            events = self._conversation.drain_events(session_id)
            live.stream_events_pending = 0
            payload = live.to_safe_dict()
            if events:
                payload["stream_events"] = events
            payload["conversation"] = None
            ctx = self._conversation.get_context(session_id)
            if ctx is not None:
                payload["conversation"] = ctx.to_safe_dict()
            return payload

    def heartbeat(self, session_id: str) -> dict[str, Any]:
        """Client keepalive — resets idle timer without starting a turn."""
        with self._lock:
            live = self._require_session(session_id)
            timeout = self._conversation.check_timeouts(session_id)
            if timeout:
                return self._timeout_close(
                    session_id,
                    reason=(
                        "conversation_timeout"
                        if timeout == "conversation"
                        else "idle_timeout"
                    ),
                )
            self._conversation.touch(session_id)
            return live.to_safe_dict()

    def recover_session(
        self,
        *,
        authenticated_user: str,
        recovery_token: str | None = None,
        conversation_id: str | None = None,
        capture_mode: str | None = None,
        microphone_enabled: bool = True,
    ) -> dict[str, Any]:
        """Browser refresh / network reconnect recovery.

        If the prior in-memory session is gone, start a fresh live session bound
        to the same conversation_id for memory continuity.
        """
        recovered = self._conversation.recover(
            recovery_token=recovery_token,
            conversation_id=conversation_id,
            authenticated_user=authenticated_user,
        )
        prior_session_id = recovered["recovery"]["session_id"]
        prior_conversation_id = recovered["recovery"]["conversation_id"]
        prior_mode = recovered["recovery"].get("capture_mode") or capture_mode

        with self._lock:
            if prior_session_id in self._sessions:
                live = self._sessions[prior_session_id]
                self._conversation.touch(prior_session_id)
                payload = live.to_safe_dict()
                payload["recovered"] = True
                payload["session_still_active"] = True
                payload["conversation"] = recovered.get("conversation")
                return payload

        # Rebind a new live session to the same conversation for continuity.
        started = self.start_session(
            authenticated_user=authenticated_user,
            capture_mode=prior_mode or MicCaptureMode.PUSH_TO_TALK,
            microphone_enabled=microphone_enabled,
            conversation_id=prior_conversation_id,
        )
        started["recovered"] = True
        started["session_still_active"] = False
        started["prior_session_id"] = prior_session_id
        emit_voice_diagnostic(
            "VOICE_SESSION_RECOVERED",
            session_id=started["session_id"],
            conversation_id=prior_conversation_id,
            rebound=True,
        )
        return started

    def drain_stream_events(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            live = self._require_session(session_id)
            events = self._conversation.drain_events(session_id)
            live.stream_events_pending = 0
            return {"session_id": session_id, "stream_events": events}

    def set_microphone_enabled(self, session_id: str, enabled: bool) -> dict[str, Any]:
        with self._lock:
            live = self._require_session(session_id)
            live.microphone_enabled = bool(enabled)
            self._sync_workspace(live)
            return live.to_safe_dict()

    def start_mic_calibration(self, session_id: str) -> dict[str, Any]:
        """Begin a short ambient/speech calibration window (explicit client start)."""
        with self._lock:
            live = self._require_session(session_id)
            calibrator = self._mic_calibrators.get(session_id)
            if calibrator is None:
                calibrator = MicCalibrator(self._mic_cal_config)
                self._mic_calibrators[session_id] = calibrator
            calibrator.start()
            live.mic_calibration = calibrator.snapshot.to_dict()
            emit_voice_diagnostic("VOICE_MIC_CALIBRATION_STARTED", session_id=session_id)
            self._emit(
                session_id,
                "VOICE_MIC_CALIBRATION_STARTED",
                {"session_id": session_id},
            )
            self._sync_workspace(live)
            return {
                "calibrating": True,
                "config": self._mic_cal_config.to_dict(),
                **live.to_safe_dict(),
            }

    def feed_mic_calibration(
        self, session_id: str, *, audio_bytes: bytes
    ) -> dict[str, Any]:
        """Feed one calibration chunk; may auto-finalize when window completes."""
        with self._lock:
            live = self._require_session(session_id)
            calibrator = self._mic_calibrators.get(session_id)
            if calibrator is None:
                raise VoiceSessionError("Mic calibration is not active")
            if not calibrator.active:
                # Already finalized (auto or explicit) — return last snapshot.
                live.mic_calibration = calibrator.snapshot.to_dict()
                self._sync_workspace(live)
                return {"calibrating": False, **live.to_safe_dict()}
            started = time.perf_counter()
            snap = calibrator.feed(audio_bytes, vad_config=self._vad_config)
            live.mic_calibration = snap.to_dict()
            if snap.calibrated:
                cal_ms = (time.perf_counter() - started) * 1000.0
                live.latency.mic_calibration_ms = cal_ms
                tracker = self._conversation.get_latency(session_id)
                if tracker is not None:
                    tracker.mark_mic_calibration(cal_ms)
                self._apply_calibration(session_id, snap)
            self._sync_workspace(live)
            return {"calibrating": calibrator.active, **live.to_safe_dict()}

    def finish_mic_calibration(self, session_id: str) -> dict[str, Any]:
        """Force-finalize the active calibration window."""
        with self._lock:
            live = self._require_session(session_id)
            calibrator = self._mic_calibrators.get(session_id)
            if calibrator is None:
                raise VoiceSessionError("Mic calibration is not active")
            if not calibrator.active and calibrator.snapshot.calibrated:
                live.mic_calibration = calibrator.snapshot.to_dict()
                self._sync_workspace(live)
                return live.to_safe_dict()
            started = time.perf_counter()
            snap = calibrator.finalize()
            cal_ms = (time.perf_counter() - started) * 1000.0
            live.latency.mic_calibration_ms = cal_ms
            live.mic_calibration = snap.to_dict()
            tracker = self._conversation.get_latency(session_id)
            if tracker is not None:
                tracker.mark_mic_calibration(cal_ms)
            if snap.calibrated:
                self._apply_calibration(session_id, snap)
            self._sync_workspace(live)
            return live.to_safe_dict()

    def get_session_statistics(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            stats = self._session_stats.get(session_id)
            if stats is None:
                raise VoiceSessionError("Unknown voice session")
            payload = stats.to_dict()
            live = self._sessions.get(session_id)
            if live is not None:
                live.session_stats_summary = {
                    "turn_count": payload["turn_count"],
                    "barge_in_count": payload["barge_in_count"],
                    "averages": payload["averages"],
                }
            emit_voice_diagnostic(
                "VOICE_SESSION_STATS",
                session_id=session_id,
                turn_count=payload["turn_count"],
            )
            return payload

    def note_provider_reconnect(self, session_id: str) -> None:
        with self._lock:
            stats = self._session_stats.get(session_id)
            if stats is not None:
                stats.note_provider_reconnect()

    def note_network_interruption(self, session_id: str) -> None:
        with self._lock:
            stats = self._session_stats.get(session_id)
            if stats is not None:
                stats.note_network_interruption()

    def note_speaker_switch(self, session_id: str) -> None:
        with self._lock:
            stats = self._session_stats.get(session_id)
            if stats is not None:
                stats.note_speaker_switch()

    # ------------------------------------------------------------------
    # Internal turn pipeline
    # ------------------------------------------------------------------

    def _finalize_and_process(self, session_id: str) -> dict[str, Any]:
        live = self._require_session(session_id)
        segmenter = self._segmenters[session_id]
        fin_started = time.perf_counter()
        try:
            audio = segmenter.finalize()
        except VoiceConfigurationError as exc:
            live.speech_detected = False
            self._set_state(session_id, LiveSessionState.LISTENING)
            self._sync_workspace(live)
            raise VoiceConfigurationError(str(exc)) from exc
        # Allow sequence numbers to restart on the next continuous turn.
        segmenter.reset()
        live.latency.utterance_finalization_ms = (
            time.perf_counter() - fin_started
        ) * 1000.0
        live.speech_detected = False

        # Browser PTT may stream raw PCM; wrap once for STT / speaker ID.
        audio = wrap_pcm_as_wav(audio)

        temp_path = self._write_temp_audio(session_id, audio)
        turn_started = time.perf_counter()
        try:
            # Speaker identification BEFORE personal memory / Brain path.
            self._set_state(session_id, LiveSessionState.IDENTIFYING_SPEAKER)
            emit_voice_diagnostic(
                "VOICE_SPEAKER_IDENTIFICATION_STARTED",
                session_id=session_id,
            )
            self._emit(
                session_id,
                "VOICE_SPEAKER_IDENTIFICATION_STARTED",
                {"session_id": session_id},
            )
            id_started = time.perf_counter()
            speaker_result = self._speaker_identifier.identify(audio)
            live.latency.speaker_identification_ms = (
                time.perf_counter() - id_started
            ) * 1000.0
            live.identity_confidence_band = (
                speaker_result.recognition_band.value
                if speaker_result.recognition_band
                else None
            )
            emit_voice_diagnostic(
                "VOICE_SPEAKER_IDENTIFIED",
                session_id=session_id,
                band=live.identity_confidence_band,
                known=speaker_result.is_known,
                reason=speaker_result.reason,
            )
            self._emit(
                session_id,
                "VOICE_SPEAKER_IDENTIFIED",
                {
                    "session_id": session_id,
                    "band": live.identity_confidence_band,
                    "is_known": speaker_result.is_known,
                    "matched_user": speaker_result.matched_user
                    if speaker_result.is_known
                    else None,
                },
            )

            # STT — incremental FINAL (stable/partial already emitted during capture)
            self._set_state(session_id, LiveSessionState.TRANSCRIBING)
            live.transcription_status = "running"
            emit_voice_diagnostic(
                "VOICE_TRANSCRIPTION_STARTED",
                session_id=session_id,
            )
            self._emit(
                session_id,
                "VOICE_TRANSCRIPTION_STARTED",
                {"session_id": session_id},
            )
            stt_started = time.perf_counter()
            try:
                incremental = self._incremental_stt.get(session_id)
                if incremental is None:
                    incremental = IncrementalSTTEngine(
                        locale=self._config.language,
                        provider_id=self._config.stt_provider,
                        registry=self._stt_registry,
                        emit=lambda e, d, sid=session_id: self._on_stream_event(
                            sid, e, d
                        ),
                    )
                    self._incremental_stt[session_id] = incremental

                def _finalize_stt() -> str:
                    result = incremental.finalize(audio)
                    return (result.brain_text or "").strip()

                transcript = self._call_with_timeout(
                    _finalize_stt,
                    timeout=self._provider_timeout,
                    label="stt",
                )
            except Exception as exc:
                return self._fail_session(session_id, f"STT failed: {exc}")
            live.latency.stt_ms = (time.perf_counter() - stt_started) * 1000.0
            tracker = self._conversation.get_latency(session_id)
            if tracker is not None:
                tracker.metrics.stt_ms = live.latency.stt_ms
                if incremental.result.first_partial_ms:
                    live.latency.first_transcript_latency_ms = (
                        incremental.result.first_partial_ms
                    )
                    tracker.mark_first_transcript()
                    tracker.metrics.first_transcript_latency_ms = (
                        incremental.result.first_partial_ms
                    )
            live.last_transcript = transcript
            live.stable_transcript_preview = (
                (incremental.result.stable_text[:80] + "…")
                if incremental.result.stable_text
                and len(incremental.result.stable_text) > 80
                else incremental.result.stable_text
            )
            live.transcription_status = "completed"
            emit_voice_diagnostic(
                "VOICE_TRANSCRIPTION_COMPLETED",
                session_id=session_id,
                chars=len(transcript),
            )
            self._emit(
                session_id,
                "VOICE_TRANSCRIPTION_COMPLETED",
                {"session_id": session_id, "chars": len(transcript)},
            )
            # Reset incremental engine for the next turn (continuity).
            incremental.reset()
            if not transcript:
                self._set_state(session_id, LiveSessionState.LISTENING)
                self._sync_workspace(live)
                raise VoiceConfigurationError("Utterance rejected: empty_transcript")

            band = speaker_result.recognition_band
            if speaker_result.is_known and band == RecognitionBand.HIGH:
                self._apply_speaker(session_id, speaker_result)
                result = self._run_brain_and_tts(
                    session_id, transcript, restricted=False
                )
            elif band == RecognitionBand.MEDIUM:
                live.pending_confirmation = PendingIdentityConfirmation(
                    predicted_user=speaker_result.matched_user,
                    confidence=speaker_result.confidence,
                    band=RecognitionBand.MEDIUM.value,
                    expires_at=time.monotonic() + self._identity_timeout,
                    reason=speaker_result.reason,
                )
                self._set_state(
                    session_id,
                    LiveSessionState.WAITING_FOR_IDENTITY_CONFIRMATION,
                )
                emit_voice_diagnostic(
                    "VOICE_IDENTITY_CONFIRMATION_REQUIRED",
                    session_id=session_id,
                    predicted=speaker_result.matched_user,
                    band=RecognitionBand.MEDIUM.value,
                )
                self._emit(
                    session_id,
                    "VOICE_IDENTITY_CONFIRMATION_REQUIRED",
                    live.pending_confirmation.to_safe_dict(),
                )
                # Speak confirmation prompt without binding identity.
                flow = self._flow_controllers.get(session_id)
                if flow is not None:
                    flow.on_awaiting_confirmation()
                    live.flow_phase = flow.phase.value
                    base_prompt = flow.confirmation_prompt(locale=self._config.language)
                else:
                    base_prompt = UNKNOWN_SPEAKER_PROMPT
                prompt = (
                    f"Je pense que tu es {speaker_result.matched_user}. "
                    "Confirmes-tu ? Dis oui, ou précise ton identité."
                    if speaker_result.matched_user
                    else base_prompt
                )
                prompt_chunks = self._speak_text(session_id, prompt)
                self._sync_workspace(live)
                result = live.to_safe_dict()
                if prompt_chunks:
                    result["tts_audio_chunks"] = prompt_chunks
            elif band == RecognitionBand.AMBIGUOUS:
                live.pending_confirmation = PendingIdentityConfirmation(
                    predicted_user=None,
                    confidence=speaker_result.confidence,
                    band=RecognitionBand.AMBIGUOUS.value,
                    expires_at=time.monotonic() + self._identity_timeout,
                    reason="ambiguous_match",
                )
                live.current_speaker = None
                self._set_state(
                    session_id,
                    LiveSessionState.WAITING_FOR_IDENTITY_CONFIRMATION,
                )
                emit_voice_diagnostic(
                    "VOICE_IDENTITY_CONFIRMATION_REQUIRED",
                    session_id=session_id,
                    band=RecognitionBand.AMBIGUOUS.value,
                )
                self._emit(
                    session_id,
                    "VOICE_IDENTITY_CONFIRMATION_REQUIRED",
                    live.pending_confirmation.to_safe_dict(),
                )
                flow = self._flow_controllers.get(session_id)
                if flow is not None:
                    flow.on_awaiting_confirmation()
                    live.flow_phase = flow.phase.value
                    confirm_prompt = flow.confirmation_prompt(locale=self._config.language)
                else:
                    confirm_prompt = UNKNOWN_SPEAKER_PROMPT
                prompt_chunks = self._speak_text(session_id, confirm_prompt)
                self._sync_workspace(live)
                result = live.to_safe_dict()
                if prompt_chunks:
                    result["tts_audio_chunks"] = prompt_chunks
            else:
                # Low confidence / unknown — restricted generic path.
                live.current_speaker = None
                live.identity_confidence_band = (
                    band.value if band else RecognitionBand.LOW.value
                )
                result = self._run_brain_and_tts(
                    session_id, transcript, restricted=True
                )

            live.latency.total_voice_turn_ms = (
                time.perf_counter() - turn_started
            ) * 1000.0
            live.latency.turn_duration_ms = live.latency.total_voice_turn_ms
            provider = live.latency.stt_ms + live.latency.tts_first_audio_ms
            live.latency.provider_latency_ms = provider
            live.latency.titan_overhead_ms = max(
                0.0, live.latency.total_voice_turn_ms - provider
            )
            if live.pending_confirmation is None:
                self._record_turn_stats(session_id, interrupted=live.interrupted)
            return result
        finally:
            self._delete_temp_audio(session_id, temp_path)

    def _run_brain_and_tts(
        self,
        session_id: str,
        transcript: str,
        *,
        restricted: bool,
    ) -> dict[str, Any]:
        live = self._require_session(session_id)
        tts = self._tts[session_id]
        tts.reset_cancel()
        live.interrupted = False
        live.brain_lock = True
        live.brain_status = "running"
        self._conversation.touch(session_id)
        cancel = self._conversation.reset_turn_cancellation(session_id)
        self._set_state(session_id, LiveSessionState.THINKING)
        emit_voice_diagnostic("VOICE_BRAIN_STARTED", session_id=session_id)
        self._emit(session_id, "VOICE_BRAIN_STARTED", {"session_id": session_id})

        request = (
            f"{RESTRICTED_UNKNOWN_PREFIX}{transcript}" if restricted else transcript
        )
        brain_adapter = self._streaming_brain.get(session_id)
        if brain_adapter is None:
            brain_adapter = StreamingBrainAdapter(
                self._brain,
                emit=lambda e, d, sid=session_id: self._on_stream_event(sid, e, d),
                timeout_seconds=self._provider_timeout,
                cancel_token=cancel.brain,
            )
            self._streaming_brain[session_id] = brain_adapter
        else:
            brain_adapter.reset_cancel()
            brain_adapter._cancel = cancel.brain  # noqa: SLF001

        turn_ctx = self._conversation.get_context(session_id)
        turn_n = turn_ctx.turn_count if turn_ctx else 0
        turn_key = f"{session_id}:{turn_n}:{transcript[:96]}"
        try:
            stream_result = brain_adapter.run(request, turn_key=turn_key)
        except Exception as exc:
            live.brain_lock = False
            live.brain_status = "failed"
            return self._fail_session(session_id, f"Brain failed: {exc}")

        if stream_result.duplicate_prevented:
            live.brain_lock = False
            live.brain_status = "completed"
            self._set_state(session_id, LiveSessionState.LISTENING)
            self._sync_workspace(live)
            return live.to_safe_dict()

        if stream_result.cancelled or cancel.cancelled or live.interrupted:
            live.brain_lock = False
            live.brain_status = "interrupted"
            live.interrupted = True
            self._set_state(session_id, LiveSessionState.INTERRUPTED)
            self._set_state(session_id, LiveSessionState.LISTENING)
            self._sync_workspace(live)
            return live.to_safe_dict()

        response_text = stream_result.final_text
        deltas = stream_result.deltas or ([response_text] if response_text else [])
        live.latency.brain_first_token_ms = stream_result.first_token_ms
        tracker = self._conversation.get_latency(session_id)
        if tracker is not None:
            tracker.mark_first_brain_token(stream_result.first_token_ms)
            tracker.metrics.brain_ms = stream_result.completed_ms

        # Mirror legacy VOICE_RESPONSE_DELTA for clients that still listen for it.
        for delta in deltas:
            self._emit(
                session_id,
                "VOICE_RESPONSE_DELTA",
                {"text": delta[:200], "session_id": session_id},
            )

        live.brain_status = "completed"
        live.last_assistant_text = response_text
        live.brain_lock = False

        # Persist once — interrupted turns still keep completed text safely.
        self._persist_turn(
            session_id,
            user_text=transcript,
            assistant_text=response_text,
            interrupted=False,
        )
        self._conversation.note_turn(
            session_id,
            transcript=transcript,
            assistant_text=response_text,
            speaker_identity=live.current_speaker,
        )
        self._sync_mission_from_brain(session_id)

        return self._run_tts(session_id, response_text, deltas=deltas)

    def _run_tts(
        self,
        session_id: str,
        response_text: str,
        *,
        deltas: list[str] | None = None,
    ) -> dict[str, Any]:
        live = self._require_session(session_id)
        tts = self._tts[session_id]
        stream_tts = self._streaming_tts.get(session_id)
        if stream_tts is None:
            stream_tts = StreamingTTSEngine(
                tts,
                strategy_config=self._tts_strategy_config,
                emit=lambda e, d, sid=session_id: self._on_stream_event(sid, e, d),
                default_locale=self._config.language,
            )
            self._streaming_tts[session_id] = stream_tts
        stream_tts.reset()

        if tts.cancelled or live.interrupted:
            self._set_state(session_id, LiveSessionState.LISTENING)
            self._sync_workspace(live)
            return live.to_safe_dict()

        cleaned = clean_text_for_speech(response_text, config=self._tts_strategy_config)
        if not cleaned:
            self._set_state(session_id, LiveSessionState.COMPLETED)
            self._set_state(session_id, LiveSessionState.LISTENING)
            self._conversation.mark_idle(session_id)
            self._sync_workspace(live)
            return live.to_safe_dict()

        live.tts_status = "running"
        self._set_state(session_id, LiveSessionState.SPEAKING)
        flow = self._flow_controllers.get(session_id)
        if flow is not None:
            flow.on_assistant_speaking()
            live.flow_phase = flow.phase.value
        emit_voice_diagnostic("VOICE_TTS_STARTED", session_id=session_id)
        self._emit(session_id, "VOICE_TTS_STARTED", {"session_id": session_id})

        tts_audio_chunks: list[dict[str, Any]] = []
        try:
            tts_result = stream_tts.synthesize_from_deltas(
                deltas or [cleaned],
                full_text=cleaned,
            )
            live.latency.tts_first_audio_ms = tts_result.first_audio_ms
            tracker = self._conversation.get_latency(session_id)
            if tracker is not None:
                tracker.mark_first_tts_audio(tts_result.first_audio_ms)
                tracker.metrics.tts_ms = tts_result.completed_ms
                if not live.latency.first_audio_latency_ms:
                    live.latency.first_audio_latency_ms = tts_result.first_audio_ms
                    tracker.mark_first_audio()

            for chunk in tts_result.chunks:
                if tts.cancelled or live.interrupted or tts_result.cancelled:
                    break
                payload = chunk.to_client_dict(session_id)
                tts_audio_chunks.append(payload)
                self._emit(session_id, "VOICE_AUDIO_CHUNK", payload)
                self._playback.play(
                    chunk.audio_bytes,
                    device_id=self._config.speaker_device,
                    volume=self._config.volume,
                )
        except Exception as exc:
            live.tts_status = "failed"
            return self._fail_session(session_id, f"TTS failed: {exc}")

        if live.interrupted or tts.cancelled:
            live.tts_status = "interrupted"
            # Mark persistence interrupted without duplicating the turn.
            self._mark_interrupted_turn(session_id)
            self._set_state(session_id, LiveSessionState.INTERRUPTED)
            self._set_state(session_id, LiveSessionState.LISTENING)
        else:
            live.tts_status = "completed"
            emit_voice_diagnostic("VOICE_TTS_COMPLETED", session_id=session_id)
            self._emit(session_id, "VOICE_TTS_COMPLETED", {"session_id": session_id})
            self._set_state(session_id, LiveSessionState.COMPLETED)
            emit_voice_diagnostic("VOICE_SESSION_COMPLETED", session_id=session_id)
            self._emit(
                session_id,
                "VOICE_SESSION_COMPLETED",
                {"session_id": session_id},
            )
            self._set_state(session_id, LiveSessionState.LISTENING)
            self._conversation.mark_idle(session_id)
            tracker = self._conversation.get_latency(session_id)
            if tracker is not None:
                tracker.mark_response_complete()
                live.latency.total_voice_turn_ms = tracker.metrics.total_response_ms
                live.latency.conversation_idle_delay_ms = (
                    tracker.metrics.conversation_idle_delay_ms
                )

        self._sync_workspace(live)
        result = live.to_safe_dict()
        if tts_audio_chunks and not live.interrupted:
            result["tts_audio_chunks"] = tts_audio_chunks
        if live.last_assistant_text:
            preview = live.last_assistant_text
            result["assistant_text_preview"] = (
                (preview[:240] + "…") if len(preview) > 240 else preview
            )
        events = self._conversation.drain_events(session_id)
        if events:
            result["stream_events"] = events
            live.stream_events_pending = 0
        return result

    def _speak_text(self, session_id: str, text: str) -> list[dict[str, Any]]:
        """Synthesize a short prompt; return ordered TTS chunks for web clients."""
        live = self._require_session(session_id)
        tts = self._tts[session_id]
        tts.reset_cancel()
        live.tts_status = "running"
        if live.state not in {
            LiveSessionState.WAITING_FOR_IDENTITY_CONFIRMATION,
            LiveSessionState.SPEAKING,
        }:
            try:
                self._set_state(session_id, LiveSessionState.SPEAKING)
            except VoiceStateError:
                self._machines[session_id].force(LiveSessionState.SPEAKING)
                live.state = LiveSessionState.SPEAKING
        chunks: list[dict[str, Any]] = []
        result = tts.synthesize_full(text)
        if result is not None and not tts.cancelled:
            payload = _tts_chunk_payload(
                session_id, result.audio_bytes, sequence=0
            )
            chunks.append(payload)
            self._emit(session_id, "VOICE_AUDIO_CHUNK", payload)
            self._playback.play(
                result.audio_bytes,
                device_id=self._config.speaker_device,
                volume=self._config.volume,
            )
        live.tts_status = "completed"
        return chunks

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _handle_barge_in(
        self, session_id: str, audio_bytes: bytes, sequence: int
    ) -> None:
        live = self._require_session(session_id)
        started = time.perf_counter()
        flow = self._flow_controllers.get(session_id)
        if flow is not None:
            flow.on_barge_in()
            flow.resume_after_interruption()
            live.flow_phase = flow.phase.value
        self._conversation.cancel_turn(session_id)
        tts = self._tts.get(session_id)
        if tts is not None:
            tts.cancel()
        stream_tts = self._streaming_tts.get(session_id)
        if stream_tts is not None:
            stream_tts.cancel()
        self._playback.stop()
        live.interrupted = True
        live.tts_status = "interrupted"
        live.brain_lock = False
        self._mark_interrupted_turn(session_id)
        self._set_state(session_id, LiveSessionState.INTERRUPTED)
        emit_voice_diagnostic("VOICE_BARGE_IN", session_id=session_id)
        self._emit(session_id, "VOICE_BARGE_IN", {"session_id": session_id})
        emit_voice_diagnostic("VOICE_RESUME_AFTER_INTERRUPT", session_id=session_id)
        self._emit(session_id, "VOICE_RESUME_AFTER_INTERRUPT", {"session_id": session_id})
        # Reset segmenter and start capturing the new utterance.
        segmenter = self._segmenters[session_id]
        segmenter.reset()
        silence = self._silence_detectors.get(session_id)
        if silence is not None:
            silence.reset()
        incremental = self._incremental_stt.get(session_id)
        if incremental is not None:
            incremental.reset()
        self._set_state(session_id, LiveSessionState.SPEECH_DETECTED)
        self._set_state(session_id, LiveSessionState.CAPTURING)
        if flow is not None:
            flow.on_speech_start()
            live.flow_phase = flow.phase.value
        segmenter.force_append(audio_bytes, sequence=sequence)
        self._feed_incremental_stt(session_id, audio_bytes, sequence=sequence)
        live.speech_detected = True
        live.input_level = segmenter.input_level
        recovery_ms = (time.perf_counter() - started) * 1000.0
        live.latency.interruption_recovery_ms = recovery_ms
        tracker = self._conversation.get_latency(session_id)
        if tracker is not None:
            tracker.mark_interruption_recovery(recovery_ms)
        stats = self._session_stats.get(session_id)
        if stats is not None:
            stats.barge_in_count += 1
        self._conversation.touch(session_id)
        self._sync_workspace(live)

    def _apply_speaker(
        self, session_id: str, result: SpeakerIdentificationResult
    ) -> None:
        live = self._require_session(session_id)
        live.current_speaker = result.matched_user
        live.identity_confidence_band = (
            result.recognition_band.value if result.recognition_band else None
        )
        session_mgr = getattr(self._brain.context_manager, "session", None)
        if session_mgr is not None and result.is_known:
            self._speaker_identifier.bind_session_user(session_mgr, result)
        # Mirror onto persisted VoiceSession if present.
        conv_id = live.conversation_id
        if conv_id:
            persisted = self._session_store.get_session(conv_id)
            if persisted is not None:
                persisted.identified_user = result.matched_user
                persisted.speaker_confidence = result.confidence
                persisted.speaker_confirmation_required = False
                self._session_store.update_session(persisted)

    def _persist_turn(
        self,
        session_id: str,
        *,
        user_text: str,
        assistant_text: str,
        interrupted: bool,
    ) -> None:
        live = self._require_session(session_id)
        turn_key = f"{session_id}:{user_text[:64]}:{len(assistant_text)}"
        if turn_key in self._persisted_turn_keys:
            return
        self._persisted_turn_keys.add(turn_key)
        conv_id = live.conversation_id
        if not conv_id:
            return
        session = self._session_store.get_session(conv_id)
        if session is None:
            return
        metrics = LatencyMetrics(
            transcription_seconds=live.latency.stt_ms / 1000.0,
            brain_seconds=live.latency.brain_first_token_ms / 1000.0,
            tts_seconds=live.latency.tts_first_audio_ms / 1000.0,
            total_seconds=live.latency.total_voice_turn_ms / 1000.0,
        )
        # Annotate interrupted responses without creating a duplicate row.
        assistant = assistant_text
        if interrupted and assistant and not assistant.endswith(" [interrupted]"):
            assistant = assistant + " [interrupted]"
        turn = ConversationTurn(
            user_text=user_text,
            assistant_text=assistant,
            brain_duration_seconds=metrics.brain_seconds,
            stt_duration_seconds=metrics.transcription_seconds,
            tts_duration_seconds=metrics.tts_seconds,
            total_latency_seconds=metrics.total_seconds,
        )
        session.add_turn(turn)
        session.identified_user = live.current_speaker
        self._session_store.update_session(session)
        live.turn_persisted = True

    def _mark_interrupted_turn(self, session_id: str) -> None:
        live = self._require_session(session_id)
        if not live.last_transcript or not live.last_assistant_text:
            return
        # Update last persisted turn annotation if present; do not append duplicate.
        conv_id = live.conversation_id
        if not conv_id:
            return
        session = self._session_store.get_session(conv_id)
        if session is None or not session.conversation_history:
            return
        last = session.conversation_history[-1]
        if last.user_text == live.last_transcript and "[interrupted]" not in last.assistant_text:
            last.assistant_text = f"{last.assistant_text} [interrupted]"
            session.last_response = last.assistant_text
            self._session_store.update_session(session)

    def _write_temp_audio(self, session_id: str, audio: bytes) -> Path | None:
        try:
            self._temp_dir.mkdir(parents=True, exist_ok=True)
            path = self._temp_dir / f"{session_id}_{uuid4().hex}.bin"
            path.write_bytes(audio)
            self._temp_files.setdefault(session_id, []).append(path)
            return path
        except OSError as exc:
            logger.warning("Failed to write temp voice audio: %s", exc)
            return None

    def _delete_temp_audio(self, session_id: str, path: Path | None) -> None:
        if path is None:
            return
        try:
            if path.exists():
                path.unlink()
            emit_voice_diagnostic(
                "VOICE_TEMP_AUDIO_DELETED",
                session_id=session_id,
            )
        except OSError as exc:
            logger.warning("Failed to delete temp voice audio: %s", exc)
        files = self._temp_files.get(session_id, [])
        self._temp_files[session_id] = [p for p in files if p != path]

    def _release_resources(
        self, session_id: str, *, final_state: LiveSessionState
    ) -> None:
        live = self._sessions.get(session_id)
        if live is None:
            return
        tts = self._tts.get(session_id)
        if tts is not None:
            tts.cancel()
        self._playback.stop()
        segmenter = self._segmenters.get(session_id)
        if segmenter is not None:
            segmenter.cleanup()
        for path in list(self._temp_files.get(session_id, [])):
            self._delete_temp_audio(session_id, path)
        live.brain_lock = False
        live.speech_detected = False
        live.pending_confirmation = None
        try:
            self._set_state(session_id, final_state)
        except VoiceStateError:
            self._machines[session_id].force(final_state)
            live.state = final_state
        if live.conversation_id:
            try:
                self._session_store.end_session(live.conversation_id)
            except VoiceSessionError:
                pass
        self._sync_workspace_idle(live)

    def _drop_session(self, session_id: str) -> None:
        failover = self._provider_failover.pop(session_id, None)
        if failover is not None:
            try:
                failover.close()
            except Exception:
                pass
        self._sessions.pop(session_id, None)
        self._segmenters.pop(session_id, None)
        self._machines.pop(session_id, None)
        self._tts.pop(session_id, None)
        self._stream_callbacks.pop(session_id, None)
        self._temp_files.pop(session_id, None)
        self._incremental_stt.pop(session_id, None)
        self._streaming_tts.pop(session_id, None)
        self._streaming_brain.pop(session_id, None)
        self._mic_calibrators.pop(session_id, None)
        self._silence_detectors.pop(session_id, None)
        self._flow_controllers.pop(session_id, None)
        self._session_stats.pop(session_id, None)

    def _apply_calibration(
        self, session_id: str, snap: MicCalibrationSnapshot
    ) -> None:
        """Apply calibrated thresholds to VAD / silence detector and emit events."""
        live = self._require_session(session_id)
        segmenter = self._segmenters.get(session_id)
        if segmenter is not None:
            snap.apply_to_vad_config(segmenter.vad.config)
        silence = self._silence_detectors.get(session_id)
        if silence is not None:
            silence.apply_thresholds(
                speech_start=snap.speech_threshold,
                speech_end=snap.end_threshold,
                noise_floor=snap.noise_floor,
            )
        stats = self._session_stats.get(session_id)
        if stats is not None:
            stats.record_calibration(
                noise_floor=snap.noise_floor,
                gain_estimate=snap.gain_estimate,
                clipping=snap.clipping_detected,
                low_volume=snap.low_volume,
            )
        emit_voice_diagnostic(
            "VOICE_MIC_CALIBRATION_COMPLETED",
            session_id=session_id,
            noise_floor=round(snap.noise_floor, 6),
            gain=round(snap.gain_estimate, 4),
            warning=snap.warning,
        )
        self._emit(
            session_id,
            "VOICE_MIC_CALIBRATION_COMPLETED",
            snap.to_dict(),
        )
        if snap.clipping_detected:
            emit_voice_diagnostic("VOICE_MIC_CLIPPING", session_id=session_id)
            self._emit(session_id, "VOICE_MIC_CLIPPING", {"session_id": session_id})
        if snap.low_volume:
            emit_voice_diagnostic("VOICE_MIC_LOW_VOLUME", session_id=session_id)
            self._emit(session_id, "VOICE_MIC_LOW_VOLUME", {"session_id": session_id})
        live.mic_calibration = snap.to_dict()

    def _record_turn_stats(self, session_id: str, *, interrupted: bool) -> None:
        live = self._sessions.get(session_id)
        stats = self._session_stats.get(session_id)
        flow = self._flow_controllers.get(session_id)
        if live is None or stats is None:
            return
        speech_ms = live.latency.speech_duration_ms
        if flow is not None:
            completed = flow.on_turn_complete()
            live.flow_phase = flow.phase.value
            if not speech_ms:
                speech_ms = completed.speech_duration_ms
            live.latency.speech_duration_ms = speech_ms
            live.latency.turn_duration_ms = completed.turn_duration_ms or live.latency.total_voice_turn_ms
            emit_voice_diagnostic(
                "VOICE_TURN_TIMING",
                session_id=session_id,
                **completed.to_dict(),
            )
            self._emit(session_id, "VOICE_TURN_TIMING", completed.to_dict())
        tracker = self._conversation.get_latency(session_id)
        if tracker is not None:
            tracker.mark_speech_duration(speech_ms)
            tracker.mark_turn_duration(live.latency.turn_duration_ms)
            tracker.mark_provider_latency(live.latency.provider_latency_ms)
        stats.record_turn(
            turn_index=len(stats.turns),
            speech_duration_ms=speech_ms,
            turn_duration_ms=live.latency.turn_duration_ms or live.latency.total_voice_turn_ms,
            mic_latency_ms=live.latency.mic_latency_ms,
            provider_latency_ms=live.latency.provider_latency_ms,
            brain_latency_ms=live.latency.brain_first_token_ms,
            tts_latency_ms=live.latency.tts_first_audio_ms,
            interrupted=interrupted,
        )
        live.session_stats_summary = {
            "turn_count": len(stats.turns),
            "barge_in_count": stats.barge_in_count,
            "averages": stats.averages(),
        }

    def _feed_incremental_stt(
        self, session_id: str, audio_bytes: bytes, *, sequence: int
    ) -> None:
        live = self._sessions.get(session_id)
        engine = self._incremental_stt.get(session_id)
        if live is None or engine is None or not audio_bytes:
            return
        result = engine.ingest_chunk(audio_bytes, sequence=sequence)
        live.partial_transcript_preview = (
            (result.partial_text[:80] + "…")
            if result.partial_text and len(result.partial_text) > 80
            else result.partial_text or None
        )
        if result.stable_text:
            live.stable_transcript_preview = (
                (result.stable_text[:80] + "…")
                if len(result.stable_text) > 80
                else result.stable_text
            )
        # Never send partial text to Brain — display only.

    def _on_stream_event(
        self, session_id: str, event: str, data: dict[str, Any]
    ) -> None:
        emit_voice_diagnostic(event, session_id=session_id, **{
            k: v for k, v in data.items() if k not in {"event", "session_id"}
        })
        self._conversation.push_event(session_id, event, data)
        self._emit(session_id, event, {"session_id": session_id, **data})
        live = self._sessions.get(session_id)
        if live is not None:
            live.stream_events_pending = min(
                200, live.stream_events_pending + 1
            )

    def _timeout_close(self, session_id: str, *, reason: str) -> dict[str, Any]:
        live = self._require_session(session_id)
        self._conversation.cancel_turn(session_id)
        self._release_resources(session_id, final_state=LiveSessionState.CANCELLED)
        self._conversation.close_session(session_id, reason=reason)
        snapshot = live.to_safe_dict()
        snapshot["timed_out"] = True
        snapshot["timeout_reason"] = reason
        self._drop_session(session_id)
        return snapshot

    def _sync_mission_from_brain(self, session_id: str) -> None:
        """Mirror active mission/goal into conversation continuity (no Brain reload)."""
        mission_id = None
        goal = None
        workspace_hint = None
        try:
            mission_mgr = getattr(self._brain, "mission_manager", None)
            if mission_mgr is not None and hasattr(mission_mgr, "get_active_mission"):
                mission = mission_mgr.get_active_mission()
                if mission is not None:
                    if isinstance(mission, dict):
                        mission_id = mission.get("id") or mission.get("title")
                        goal = mission.get("goal") or mission.get("title")
                    else:
                        mission_id = getattr(mission, "id", None) or getattr(
                            mission, "title", None
                        )
                        goal = getattr(mission, "goal", None) or getattr(
                            mission, "title", None
                        )
            state_mgr = getattr(self._brain, "state_manager", None) or self._state_manager
            if state_mgr is not None and hasattr(state_mgr, "load"):
                state = state_mgr.load()
                if hasattr(state, "active_project"):
                    workspace_hint = getattr(state, "active_project", None) or getattr(
                        state, "current_step", None
                    )
                elif isinstance(state, dict):
                    workspace_hint = state.get("active_project") or state.get(
                        "current_step"
                    )
        except Exception as exc:  # noqa: BLE001 — continuity is best-effort
            logger.debug("Mission continuity sync skipped: %s", exc)
        self._conversation.sync_mission_goal(
            session_id,
            mission_id=str(mission_id) if mission_id else None,
            goal=str(goal) if goal else None,
            workspace_hint=str(workspace_hint) if workspace_hint else None,
        )

    def _fail_session(self, session_id: str, message: str) -> dict[str, Any]:
        live = self._require_session(session_id)
        live.brain_lock = False
        live.brain_status = "failed"
        emit_voice_diagnostic(
            "VOICE_SESSION_FAILED",
            session_id=session_id,
            error=message[:160],
        )
        self._emit(
            session_id,
            "VOICE_SESSION_FAILED",
            {"session_id": session_id, "error": message[:160]},
        )
        try:
            self._set_state(session_id, LiveSessionState.FAILED)
        except VoiceStateError:
            self._machines[session_id].force(LiveSessionState.FAILED)
            live.state = LiveSessionState.FAILED
        # Recover to LISTENING — never leave Brain lock stuck.
        self._set_state(session_id, LiveSessionState.LISTENING)
        self._sync_workspace(live)
        segmenter = self._segmenters.get(session_id)
        if segmenter is not None:
            segmenter.cleanup()
        return live.to_safe_dict()

    def _call_with_timeout(
        self, fn: Callable[[], Any], *, timeout: float, label: str
    ) -> Any:
        """Run a callable with a soft timeout (thread-based; mock-friendly)."""
        outcome: dict[str, Any] = {}

        def runner() -> None:
            try:
                outcome["value"] = fn()
            except Exception as exc:  # noqa: BLE001 — surfaced to caller
                outcome["error"] = exc

        thread = threading.Thread(target=runner, name=f"voice-{label}", daemon=True)
        thread.start()
        thread.join(timeout=timeout)
        if thread.is_alive():
            raise VoiceProviderError(f"Provider timeout ({label})")
        if "error" in outcome:
            raise outcome["error"]
        return outcome.get("value")

    def _require_session(self, session_id: str) -> LiveVoiceSession:
        live = self._sessions.get(session_id)
        if live is None:
            raise VoiceSessionError(f"Unknown voice session {session_id}")
        return live

    def _set_state(self, session_id: str, new_state: LiveSessionState) -> None:
        machine = self._machines[session_id]
        live = self._sessions[session_id]
        machine.transition(new_state)
        live.state = machine.state

    def _emit(self, session_id: str, event: str, data: dict[str, Any]) -> None:
        callback = self._stream_callbacks.get(session_id)
        if callback is None:
            return
        try:
            callback(event, data)
        except Exception as exc:  # noqa: BLE001 — stream must not crash session
            logger.warning("Voice stream callback failed event=%s err=%s", event, exc)

    def _sync_workspace(self, live: LiveVoiceSession) -> None:
        if self._state_manager is None:
            return
        self._state_manager.update(
            {
                "voice_session_state": live.state.value,
                "voice_input_level": round(live.input_level, 4),
                "voice_speech_detected": live.speech_detected,
                "voice_current_speaker": live.current_speaker,
                "voice_identity_confidence_band": live.identity_confidence_band,
                "voice_transcription_status": live.transcription_status,
                "voice_brain_status": live.brain_status,
                "voice_tts_status": live.tts_status,
                "voice_interrupted": live.interrupted,
            }
        )

    def _sync_workspace_idle(self, live: LiveVoiceSession) -> None:
        if self._state_manager is None:
            return
        self._state_manager.update(
            {
                "voice_session_state": LiveSessionState.IDLE.value,
                "voice_input_level": 0.0,
                "voice_speech_detected": False,
                "voice_current_speaker": live.current_speaker,
                "voice_identity_confidence_band": live.identity_confidence_band,
                "voice_transcription_status": None,
                "voice_brain_status": None,
                "voice_tts_status": None,
                "voice_interrupted": False,
            }
        )


def vad_config_from_settings() -> VADConfig:
    """Build VADConfig from settings with safe defaults."""
    return VADConfig(
        speech_start_threshold=float(
            getattr(app_settings, "TITAN_VOICE_VAD_SPEECH_START", 0.035)
        ),
        speech_end_threshold=float(
            getattr(app_settings, "TITAN_VOICE_VAD_SPEECH_END", 0.018)
        ),
        silence_timeout_seconds=float(
            getattr(
                app_settings,
                "TITAN_VOICE_VAD_SILENCE_TIMEOUT",
                app_settings.TITAN_VOICE_SILENCE_TIMEOUT,
            )
        ),
        min_utterance_duration_seconds=float(
            getattr(app_settings, "TITAN_VOICE_VAD_MIN_UTTERANCE", 0.35)
        ),
        max_utterance_duration_seconds=float(
            getattr(app_settings, "TITAN_VOICE_VAD_MAX_UTTERANCE", 30.0)
        ),
        background_noise_tolerance=float(
            getattr(app_settings, "TITAN_VOICE_VAD_NOISE_TOLERANCE", 0.012)
        ),
        sensitivity=float(getattr(app_settings, "TITAN_VOICE_VAD_SENSITIVITY", 0.55)),
    )


def tts_strategy_config_from_settings() -> TTSStrategyConfig:
    mode_raw = str(
        getattr(app_settings, "TITAN_VOICE_TTS_STRATEGY", "sentence_buffered")
    ).strip().lower()
    try:
        mode = TTSStrategyMode(mode_raw)
    except ValueError:
        mode = TTSStrategyMode.SENTENCE_BUFFERED
    return TTSStrategyConfig(
        mode=mode,
        min_text_chunk_chars=int(
            getattr(app_settings, "TITAN_VOICE_TTS_MIN_CHUNK_CHARS", 24)
        ),
        french_voice=str(getattr(app_settings, "TITAN_VOICE_TTS_VOICE_FR", "alloy")),
        english_voice=str(getattr(app_settings, "TITAN_VOICE_TTS_VOICE_EN", "verse")),
    )
