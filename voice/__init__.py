# =====================================
# Titan Voice Package
# =====================================

"""Voice interface orchestration — provider-independent STT/TTS (Phase 17.8 + Voice Runtime V1)."""

from voice.models import (
    ConversationMode,
    ConversationTurn,
    LatencyMetrics,
    VoiceConfig,
    VoiceSession,
    VoiceState,
    VoiceTurnResult,
)
from voice.speech_to_text import (
    MockSpeechToTextProvider,
    SpeechToTextProvider,
    SpeechToTextRegistry,
    TranscriptionResult,
    get_stt_registry,
)
from voice.text_to_speech import (
    MockTextToSpeechProvider,
    SynthesisResult,
    TextToSpeechProvider,
    TextToSpeechRegistry,
    get_tts_registry,
)
from voice.voice_manager import VoiceCapabilities, VoiceManager
from voice.voice_runtime import VoiceRuntime, voice_config_from_settings
from voice.voice_session import VoiceSessionStore

__all__ = [
    "ConversationMode",
    "ConversationTurn",
    "LatencyMetrics",
    "MockSpeechToTextProvider",
    "MockTextToSpeechProvider",
    "SpeechToTextProvider",
    "SpeechToTextRegistry",
    "SynthesisResult",
    "TextToSpeechProvider",
    "TextToSpeechRegistry",
    "TranscriptionResult",
    "VoiceCapabilities",
    "VoiceConfig",
    "VoiceManager",
    "VoiceRuntime",
    "VoiceSession",
    "VoiceSessionStore",
    "VoiceState",
    "VoiceTurnResult",
    "get_stt_registry",
    "get_tts_registry",
    "voice_config_from_settings",
]
