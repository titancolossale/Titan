# =====================================
# Titan Voice Package
# =====================================

"""Voice interface orchestration — provider-independent STT/TTS (Phase 17.8 + Voice Runtime V1 + Phase 20.1–20.12)."""

from voice.anti_spoof import (
    AntiSpoofProvider,
    HeuristicAntiSpoofProvider,
    LivenessAvailability,
    LivenessResult,
    NullAntiSpoofProvider,
    evaluate_liveness,
    get_anti_spoof_provider,
    get_anti_spoof_registry,
    reset_anti_spoof_registry_for_tests,
)
from voice.cancellation import CancelToken, TurnCancellation
from voice.conversation_engine import (
    ConversationContext,
    ConversationEngineConfig,
    RealtimeConversationEngine,
)
from voice.conversation_flow import (
    ConversationFlowConfig,
    ConversationFlowController,
    FlowPhase,
)
from voice.diagnostics import VOICE_DIAGNOSTIC_EVENTS, VOICE_STREAM_EVENTS, emit_voice_diagnostic
from voice.biometric_trust import (
    BiometricTrustMode,
    biometric_trust_diagnostics,
    resolve_biometric_trust_mode,
)
from voice.ecapa_provider import (
    EcapaEmbeddingProvider,
    ProviderInitStatus,
    normalize_embedding,
    probe_ecapa_dependencies,
)
from voice.embedding_capabilities import (
    EmbeddingBackendFamily,
    EmbeddingCapabilities,
    EmbeddingTrustLevel,
)
from voice.embedding_diagnostics import (
    collect_biometric_readiness,
    collect_embedding_security_diagnostics,
)
from voice.embedding_migration import (
    EmbeddingMigrationReport,
    EmbeddingMigrationService,
    MigrationStatus,
)
from voice.embedding_provider import (
    DeterministicLocalEmbeddingProvider,
    EmbeddingProviderRegistry,
    HistogramEmbeddingProvider,
    LocalEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    get_embedding_provider,
    get_embedding_registry,
    is_dev_fallback_version,
    is_production_trusted_version,
)
from voice.embedding_storage import (
    AesGcmEmbeddingStorage,
    EmbeddingCorruptionError,
    EmbeddingStorageBackend,
    EnvelopeEmbeddingStorage,
    PlaintextEmbeddingStorage,
    build_embedding_storage,
)
from voice.identity_security import (
    IdentityActionClass,
    IdentityAssertionKind,
    IdentitySecurityBoundary,
    IdentitySecurityDecision,
    voice_identity_may_access_personal_memory,
    voice_identity_may_bind_context,
)
from voice.resemblyzer_provider import (
    ResemblyzerEmbeddingProvider,
    probe_resemblyzer_dependencies,
)
from voice.enrollment_consent import (
    CONSENT_VERSION,
    get_consent_prompt,
    list_consent_prompts,
)
from voice.enrollment_diagnostics import collect_enrollment_diagnostics
from voice.enrollment_preflight import (
    PreflightCheck,
    PreflightStatus,
    run_enrollment_preflight,
)
from voice.enrollment_models import (
    EnrollmentConfig,
    EnrollmentStatus,
    EnrollmentVerificationResult,
    RecognitionBand,
    SpeakerIdentityProfile,
    VerificationOutcome,
)
from voice.enrollment_quality import (
    ProductionQualityMetrics,
    analyze_production_quality,
)
from voice.enrollment_scripts import (
    BILINGUAL_ENROLLMENT_SCRIPT,
    ENGLISH_ENROLLMENT_SCRIPT,
    FRENCH_ENROLLMENT_SCRIPT,
    SPANISH_ENROLLMENT_SCRIPT,
    get_enrollment_script,
    list_enrollment_scripts,
)
from voice.enrollment_verification import (
    EnrollmentVerificationPipeline,
    VerificationThresholds,
)
from voice.enrollment_workflow import (
    EnrollmentWorkflowController,
    ProductionEnrollmentState,
)
from voice.exceptions import VoiceEnrollmentError, VoiceLiveSessionError
from voice.latency_tracker import ConversationLatencyMetrics, LatencyTracker
from voice.live_session import (
    LiveVoiceSessionOrchestrator,
    MicCaptureMode,
    RESTRICTED_UNKNOWN_PREFIX,
    tts_strategy_config_from_settings,
    vad_config_from_settings,
)
from voice.mic_calibration import (
    MicCalibrationConfig,
    MicCalibrationSnapshot,
    MicCalibrator,
)
from voice.models import (
    ConversationMode,
    ConversationTurn,
    LatencyMetrics,
    VoiceConfig,
    VoiceSession,
    VoiceState,
    VoiceTurnResult,
)
from voice.production_soak import (
    DEFAULT_SOAK_SCENARIOS,
    SoakScenarioId,
    VoiceProductionSoakRunner,
)
from voice.providers import (
    DeepgramStreamingSTT,
    ElevenLabsStreamingTTS,
    OpenAIRealtimeSession,
    OpenAITextToSpeechProvider,
    OpenAIWhisperSpeechToTextProvider,
    OpenAIWhisperStreamingSTT,
    RealtimeProviderRegistry,
    StreamingProviderFailover,
    get_realtime_registry,
    register_default_voice_providers,
    register_realtime_voice_providers,
)
from voice.sample_validator import validate_enrollment_sample
from voice.session_lifecycle import LiveSessionState, LiveSessionStateMachine
from voice.session_stats import VoiceSessionStatistics
from voice.silence_detector import (
    SilenceDecision,
    SilenceDetector,
    SilenceDetectorConfig,
)
from voice.speaker_identifier import (
    UNKNOWN_SPEAKER_PROMPT,
    SpeakerIdentificationResult,
    SpeakerIdentifier,
    SpeakerIdentity,
    SpeakerProfile,
    extract_voice_features,
    parse_spoken_identity,
)
from voice.speaker_profile_store import SpeakerProfileStore
from voice.speaker_verification import (
    SpeakerVerificationEngine,
    SpeakerVerificationResult,
    VerificationConfig,
    VerificationDecision,
)
from voice.speech_segmenter import SpeechSegmenter
from voice.speech_to_text import (
    MockSpeechToTextProvider,
    SpeechToTextProvider,
    SpeechToTextRegistry,
    TranscriptionResult,
    get_stt_registry,
)
from voice.stream_performance import StreamPerformanceController
from voice.streaming_brain import StreamingBrainAdapter, StreamingBrainResult
from voice.streaming_stt import IncrementalSTTEngine, IncrementalTranscript, TranscriptStage
from voice.streaming_tts import StreamingTTSEngine, detect_response_locale
from voice.text_to_speech import (
    MockTextToSpeechProvider,
    SynthesisResult,
    TextToSpeechProvider,
    TextToSpeechRegistry,
    get_tts_registry,
)
from voice.transport import (
    HttpFallbackTransport,
    InMemoryTransport,
    ReconnectPolicy,
    ServerSentEventsTransport,
    StreamingTransport,
    TransportKind,
    TransportManager,
    WebSocketTransport,
)
from voice.tts_strategy import (
    TTSStrategy,
    TTSStrategyConfig,
    TTSStrategyMode,
    clean_text_for_speech,
    select_voice_for_locale,
)
from voice.vad import VADConfig, VADEvent, VoiceActivityDetector
from voice.voice_enrollment import VoiceEnrollmentService
from voice.voice_manager import VoiceCapabilities, VoiceManager
from voice.voice_runtime import VoiceRuntime, speaker_identifier_from_settings, voice_config_from_settings
from voice.voice_session import VoiceSessionStore

__all__ = [
    "AntiSpoofProvider",
    "AesGcmEmbeddingStorage",
    "BiometricTrustMode",
    "CancelToken",
    "BILINGUAL_ENROLLMENT_SCRIPT",
    "CONSENT_VERSION",
    "ConversationContext",
    "ConversationEngineConfig",
    "ConversationFlowConfig",
    "ConversationFlowController",
    "ConversationLatencyMetrics",
    "ConversationMode",
    "ConversationTurn",
    "DEFAULT_SOAK_SCENARIOS",
    "DeepgramStreamingSTT",
    "DeterministicLocalEmbeddingProvider",
    "EcapaEmbeddingProvider",
    "ElevenLabsStreamingTTS",
    "ENGLISH_ENROLLMENT_SCRIPT",
    "EmbeddingBackendFamily",
    "EmbeddingCapabilities",
    "EmbeddingCorruptionError",
    "EmbeddingMigrationReport",
    "EmbeddingMigrationService",
    "EmbeddingProviderRegistry",
    "EmbeddingStorageBackend",
    "EmbeddingTrustLevel",
    "EnrollmentConfig",
    "EnrollmentStatus",
    "EnrollmentVerificationPipeline",
    "EnrollmentVerificationResult",
    "EnrollmentWorkflowController",
    "EnvelopeEmbeddingStorage",
    "FRENCH_ENROLLMENT_SCRIPT",
    "FlowPhase",
    "HeuristicAntiSpoofProvider",
    "HistogramEmbeddingProvider",
    "HttpFallbackTransport",
    "IdentityActionClass",
    "IdentityAssertionKind",
    "IdentitySecurityBoundary",
    "IdentitySecurityDecision",
    "InMemoryTransport",
    "IncrementalSTTEngine",
    "IncrementalTranscript",
    "LatencyMetrics",
    "LatencyTracker",
    "LiveSessionState",
    "LiveSessionStateMachine",
    "LiveVoiceSessionOrchestrator",
    "LivenessAvailability",
    "LivenessResult",
    "LocalEmbeddingProvider",
    "MicCalibrationConfig",
    "MicCalibrationSnapshot",
    "MicCalibrator",
    "MicCaptureMode",
    "MigrationStatus",
    "MockSpeechToTextProvider",
    "MockTextToSpeechProvider",
    "NullAntiSpoofProvider",
    "OpenAICompatibleEmbeddingProvider",
    "OpenAIRealtimeSession",
    "OpenAITextToSpeechProvider",
    "OpenAIWhisperSpeechToTextProvider",
    "OpenAIWhisperStreamingSTT",
    "PlaintextEmbeddingStorage",
    "ProductionEnrollmentState",
    "ProductionQualityMetrics",
    "ProviderInitStatus",
    "RESTRICTED_UNKNOWN_PREFIX",
    "RealtimeConversationEngine",
    "RealtimeProviderRegistry",
    "RecognitionBand",
    "ReconnectPolicy",
    "ResemblyzerEmbeddingProvider",
    "SPANISH_ENROLLMENT_SCRIPT",
    "ServerSentEventsTransport",
    "SilenceDecision",
    "SilenceDetector",
    "biometric_trust_diagnostics",
    "collect_biometric_readiness",
    "normalize_embedding",
    "probe_ecapa_dependencies",
    "probe_resemblyzer_dependencies",
    "resolve_biometric_trust_mode",
    "voice_identity_may_access_personal_memory",
    "SilenceDetectorConfig",
    "SoakScenarioId",
    "SpeakerIdentificationResult",
    "SpeakerIdentifier",
    "SpeakerIdentity",
    "SpeakerIdentityProfile",
    "SpeakerProfile",
    "SpeakerProfileStore",
    "SpeakerVerificationEngine",
    "SpeakerVerificationResult",
    "SpeechSegmenter",
    "SpeechToTextProvider",
    "SpeechToTextRegistry",
    "StreamPerformanceController",
    "StreamingBrainAdapter",
    "StreamingBrainResult",
    "StreamingProviderFailover",
    "StreamingTTSEngine",
    "StreamingTransport",
    "SynthesisResult",
    "TTSStrategy",
    "TTSStrategyConfig",
    "TTSStrategyMode",
    "TextToSpeechProvider",
    "TextToSpeechRegistry",
    "TranscriptStage",
    "TranscriptionResult",
    "TransportKind",
    "TransportManager",
    "TurnCancellation",
    "UNKNOWN_SPEAKER_PROMPT",
    "VADConfig",
    "VADEvent",
    "VOICE_DIAGNOSTIC_EVENTS",
    "VOICE_STREAM_EVENTS",
    "VerificationConfig",
    "VerificationDecision",
    "VerificationOutcome",
    "VerificationThresholds",
    "VoiceActivityDetector",
    "VoiceCapabilities",
    "VoiceConfig",
    "VoiceEnrollmentError",
    "VoiceEnrollmentService",
    "VoiceLiveSessionError",
    "VoiceManager",
    "VoiceProductionSoakRunner",
    "VoiceRuntime",
    "VoiceSession",
    "VoiceSessionStatistics",
    "VoiceSessionStore",
    "VoiceState",
    "VoiceTurnResult",
    "WebSocketTransport",
    "analyze_production_quality",
    "build_embedding_storage",
    "clean_text_for_speech",
    "collect_biometric_readiness",
    "collect_embedding_security_diagnostics",
    "collect_enrollment_diagnostics",
    "PreflightCheck",
    "PreflightStatus",
    "run_enrollment_preflight",
    "detect_response_locale",
    "emit_voice_diagnostic",
    "evaluate_liveness",
    "extract_voice_features",
    "get_anti_spoof_provider",
    "get_anti_spoof_registry",
    "get_consent_prompt",
    "get_embedding_provider",
    "get_embedding_registry",
    "get_enrollment_script",
    "get_realtime_registry",
    "get_stt_registry",
    "get_tts_registry",
    "is_dev_fallback_version",
    "is_production_trusted_version",
    "list_consent_prompts",
    "list_enrollment_scripts",
    "parse_spoken_identity",
    "register_default_voice_providers",
    "register_realtime_voice_providers",
    "reset_anti_spoof_registry_for_tests",
    "select_voice_for_locale",
    "speaker_identifier_from_settings",
    "tts_strategy_config_from_settings",
    "vad_config_from_settings",
    "validate_enrollment_sample",
    "voice_config_from_settings",
    "voice_identity_may_access_personal_memory",
    "voice_identity_may_bind_context",
]
