# =====================================
# Titan Voice Providers Package
# =====================================

"""Live STT/TTS provider adapters for Voice Runtime (Phase 20.1 + 20.6)."""

from voice.providers.deepgram_streaming import DeepgramStreamingSTT
from voice.providers.elevenlabs_streaming import ElevenLabsStreamingTTS
from voice.providers.failover import FailoverConfig, StreamingProviderFailover
from voice.providers.openai_realtime import OpenAIRealtimeSession
from voice.providers.openai_stt import OpenAIWhisperSpeechToTextProvider
from voice.providers.openai_tts import OpenAITextToSpeechProvider
from voice.providers.openai_whisper_streaming import OpenAIWhisperStreamingSTT
from voice.providers.realtime_registry import (
    RealtimeProviderRegistry,
    get_realtime_registry,
)
from voice.providers.realtime_stt import MockRealtimeSTTProvider, RealtimeSTTProvider
from voice.providers.realtime_tts import (
    AudioBufferConfig,
    MockRealtimeTTSProvider,
    RealtimeTTSProvider,
    SmoothedAudioBuffer,
)
from voice.providers.registry_bootstrap import (
    register_default_voice_providers,
    register_realtime_voice_providers,
)
from voice.providers.streaming_models import (
    AudioStreamChunk,
    HypothesisStability,
    ProviderLatencyMarks,
    StreamCapabilities,
    StreamDirection,
    TranscriptHypothesis,
)

__all__ = [
    "AudioBufferConfig",
    "AudioStreamChunk",
    "DeepgramStreamingSTT",
    "ElevenLabsStreamingTTS",
    "FailoverConfig",
    "HypothesisStability",
    "MockRealtimeSTTProvider",
    "MockRealtimeTTSProvider",
    "OpenAIRealtimeSession",
    "OpenAITextToSpeechProvider",
    "OpenAIWhisperSpeechToTextProvider",
    "OpenAIWhisperStreamingSTT",
    "ProviderLatencyMarks",
    "RealtimeProviderRegistry",
    "RealtimeSTTProvider",
    "RealtimeTTSProvider",
    "SmoothedAudioBuffer",
    "StreamCapabilities",
    "StreamDirection",
    "StreamingProviderFailover",
    "TranscriptHypothesis",
    "get_realtime_registry",
    "register_default_voice_providers",
    "register_realtime_voice_providers",
]
