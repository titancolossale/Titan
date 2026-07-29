# =====================================
# Titan Voice Diagnostics
# =====================================

"""Structured voice-session diagnostics (Phase 20.3/20.5/20.6/20.7).

Never logs raw audio, embeddings, secrets, cookies, API keys, or hidden prompts.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("titan.voice.diagnostics")

VOICE_DIAGNOSTIC_EVENTS: tuple[str, ...] = (
    "VOICE_SESSION_STARTED",
    "VOICE_SESSION_AUTHORIZED",
    "VOICE_AUDIO_CHUNK_RECEIVED",
    "VOICE_SPEECH_STARTED",
    "VOICE_SPEECH_ENDED",
    "VOICE_TRANSCRIPTION_STARTED",
    "VOICE_TRANSCRIPTION_COMPLETED",
    "VOICE_SPEAKER_IDENTIFICATION_STARTED",
    "VOICE_SPEAKER_IDENTIFIED",
    "VOICE_IDENTITY_CONFIRMATION_REQUIRED",
    "VOICE_IDENTITY_CONFIRMED",
    "VOICE_IDENTITY_REJECTED",
    "VOICE_BRAIN_STARTED",
    "VOICE_TTS_STARTED",
    "VOICE_TTS_COMPLETED",
    "VOICE_BARGE_IN",
    "VOICE_SESSION_CANCELLED",
    "VOICE_SESSION_FAILED",
    "VOICE_SESSION_COMPLETED",
    "VOICE_TEMP_AUDIO_DELETED",
    # Phase 20.5 — real-time streaming conversation
    "VOICE_STREAM_STARTED",
    "VOICE_STREAM_PARTIAL",
    "VOICE_STREAM_STABLE",
    "VOICE_STREAM_FINAL",
    "BRAIN_STREAM_STARTED",
    "BRAIN_STREAM_DELTA",
    "BRAIN_STREAM_SENTENCE",
    "BRAIN_STREAM_COMPLETED",
    "TTS_STREAM_STARTED",
    "TTS_STREAM_CHUNK",
    "TTS_STREAM_COMPLETED",
    "VOICE_CONVERSATION_IDLE",
    "VOICE_CONVERSATION_RESUMED",
    "VOICE_SESSION_RECOVERED",
    "VOICE_SESSION_CLOSED",
    # Phase 20.6 — provider-level streaming
    "PROVIDER_TRANSPORT_CONNECTED",
    "PROVIDER_TRANSPORT_RECOVERING",
    "PROVIDER_TRANSPORT_RECOVERED",
    "PROVIDER_TRANSPORT_FALLBACK",
    "PROVIDER_TRANSPORT_SWITCHED",
    "PROVIDER_TRANSPORT_FAILED",
    "PROVIDER_TRANSPORT_CLOSED",
    "PROVIDER_STT_STARTED",
    "PROVIDER_STT_AUDIO",
    "PROVIDER_STT_HYPOTHESIS",
    "PROVIDER_STT_LANGUAGE",
    "PROVIDER_STT_FINAL",
    "PROVIDER_STT_CANCELLED",
    "PROVIDER_STT_CLOSED",
    "PROVIDER_TTS_STARTED",
    "PROVIDER_TTS_TEXT",
    "PROVIDER_TTS_CHUNK",
    "PROVIDER_TTS_COMPLETED",
    "PROVIDER_TTS_CANCELLED",
    "PROVIDER_TTS_CLOSED",
    "PROVIDER_REALTIME_STARTED",
    "PROVIDER_REALTIME_CANCELLED",
    "PROVIDER_REALTIME_CLOSED",
    "PROVIDER_FAILOVER_ACTIVATED",
    "PROVIDER_DISCONNECT",
    "PROVIDER_NETWORK_LOSS",
    "PROVIDER_TIMEOUT",
    "PROVIDER_RETRY",
    "PROVIDER_FALLBACK",
    "PROVIDER_FALLBACK_EXHAUSTED",
    "PROVIDER_SWITCHED",
    # Phase 20.7 — live experience / production soak
    "VOICE_MIC_CALIBRATION_STARTED",
    "VOICE_MIC_CALIBRATION_COMPLETED",
    "VOICE_MIC_LOW_VOLUME",
    "VOICE_MIC_CLIPPING",
    "VOICE_END_OF_TURN",
    "VOICE_LONG_PAUSE",
    "VOICE_FALSE_SPEECH_REJECTED",
    "VOICE_NATURAL_PAUSE",
    "VOICE_RESUME_AFTER_INTERRUPT",
    "VOICE_TURN_TIMING",
    "VOICE_SESSION_STATS",
    "VOICE_SOAK_SCENARIO",
    # Phase 20.8 — live providers / browser WS / enrollment prep
    "PROVIDER_HEALTH_SNAPSHOT",
    "VOICE_WS_CONNECTING",
    "VOICE_WS_CONNECTED",
    "VOICE_WS_RECONNECTING",
    "VOICE_WS_RECOVERED",
    "VOICE_WS_RECOVER_FAILED",
    "VOICE_WS_BACKPRESSURE",
    "VOICE_WS_TIMEOUT",
    "VOICE_WS_CLOSED",
    "VOICE_WS_ERROR",
    "VOICE_ENROLLMENT_DUPLICATE_BLOCKED",
    "EMBEDDING_QUALITY",
    # Phase 20.9 — real enrollment prep / live provider soak
    "VOICE_ENROLLMENT_CONSENT_GRANTED",
    "VOICE_ENROLLMENT_CONSENT_DECLINED",
    "VOICE_ENROLLMENT_RECOVERED",
    "ENROLLMENT_DIAGNOSTICS_SNAPSHOT",
    "VOICE_VERIFICATION_CONFIDENCE",
    "LIVE_PROVIDER_RECOVERY",
    # Phase 20.11 — production embeddings / identity security
    "VOICE_EMBEDDING_SECURITY_SNAPSHOT",
    "VOICE_VERIFICATION_DECISION",
    "VOICE_MIGRATION_STATUS",
    "VOICE_LIVENESS_EVALUATED",
    "VOICE_IDENTITY_SECURITY_BOUNDARY",
    # Phase 20.12 — real biometric backend
    "ECAPA_MODEL_READY",
    "ECAPA_MODEL_INIT_FAILED",
    "RESEMBLYZER_MODEL_READY",
    "RESEMBLYZER_MODEL_INIT_FAILED",
    "EMBEDDING_STORAGE_MIGRATED_LEGACY",
    # Phase 20.10B-1 — production enrollment activation
    "VOICE_ENROLLMENT_PREFLIGHT",
)

# Client/stream event names (same vocabulary, used for SSE ordering).
VOICE_STREAM_EVENTS: tuple[str, ...] = (
    "VOICE_SESSION_STARTED",
    "VOICE_LISTENING",
    "VOICE_SPEECH_STARTED",
    "VOICE_SPEECH_ENDED",
    "VOICE_TRANSCRIPTION_STARTED",
    "VOICE_TRANSCRIPTION_COMPLETED",
    "VOICE_SPEAKER_IDENTIFICATION_STARTED",
    "VOICE_SPEAKER_IDENTIFIED",
    "VOICE_BRAIN_STARTED",
    "VOICE_RESPONSE_DELTA",
    "VOICE_TTS_STARTED",
    "VOICE_AUDIO_CHUNK",
    "VOICE_TTS_COMPLETED",
    "VOICE_SESSION_COMPLETED",
    "VOICE_SESSION_CANCELLED",
    "VOICE_SESSION_FAILED",
    "VOICE_IDENTITY_CONFIRMATION_REQUIRED",
    "VOICE_IDENTITY_CONFIRMED",
    "VOICE_IDENTITY_REJECTED",
    "VOICE_BARGE_IN",
    "VOICE_STREAM_STARTED",
    "VOICE_STREAM_PARTIAL",
    "VOICE_STREAM_STABLE",
    "VOICE_STREAM_FINAL",
    "BRAIN_STREAM_STARTED",
    "BRAIN_STREAM_DELTA",
    "BRAIN_STREAM_SENTENCE",
    "BRAIN_STREAM_COMPLETED",
    "TTS_STREAM_STARTED",
    "TTS_STREAM_CHUNK",
    "TTS_STREAM_COMPLETED",
    "VOICE_CONVERSATION_IDLE",
    "VOICE_CONVERSATION_RESUMED",
    "VOICE_SESSION_RECOVERED",
    "VOICE_SESSION_CLOSED",
    "PROVIDER_TRANSPORT_CONNECTED",
    "PROVIDER_TRANSPORT_RECOVERED",
    "PROVIDER_TRANSPORT_FALLBACK",
    "PROVIDER_TRANSPORT_SWITCHED",
    "PROVIDER_STT_HYPOTHESIS",
    "PROVIDER_TTS_CHUNK",
    "PROVIDER_FAILOVER_ACTIVATED",
    "PROVIDER_DISCONNECT",
    "PROVIDER_NETWORK_LOSS",
    "PROVIDER_TIMEOUT",
    "PROVIDER_RETRY",
    "PROVIDER_FALLBACK",
    "PROVIDER_SWITCHED",
    "VOICE_MIC_CALIBRATION_STARTED",
    "VOICE_MIC_CALIBRATION_COMPLETED",
    "VOICE_MIC_LOW_VOLUME",
    "VOICE_MIC_CLIPPING",
    "VOICE_END_OF_TURN",
    "VOICE_LONG_PAUSE",
    "VOICE_FALSE_SPEECH_REJECTED",
    "VOICE_NATURAL_PAUSE",
    "VOICE_RESUME_AFTER_INTERRUPT",
    "VOICE_TURN_TIMING",
    "VOICE_SESSION_STATS",
    "PROVIDER_HEALTH_SNAPSHOT",
    "VOICE_WS_CONNECTED",
    "VOICE_WS_RECOVERED",
    "VOICE_WS_BACKPRESSURE",
    "ENROLLMENT_DIAGNOSTICS_SNAPSHOT",
)

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|password|secret|bearer)\s*[:=]\s*\S+"),
    re.compile(r"(?i)sk-[a-z0-9]{10,}"),
    re.compile(r"(?i)cookie\s*[:=]\s*\S+"),
)

_FORBIDDEN_KEYS = frozenset(
    {
        "audio",
        "audio_bytes",
        "audio_base64",
        "raw_audio",
        "embedding",
        "embeddings",
        "vectors",
        "voiceprint",
        "ciphertext_b64",
        "integrity_hash",
        "api_key",
        "access_token",
        "password",
        "cookie",
        "hidden_prompt",
        "system_prompt",
        "storage_key",
    }
)


def sanitize_diagnostic_payload(data: dict[str, Any] | None) -> dict[str, Any]:
    """Strip forbidden keys and redact secret-looking strings.

    Metadata keys such as ``embedding_provider`` / ``embedding_version`` are
    retained; only raw biometric vector payloads are removed.
    """
    if not data:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        lowered = str(key).lower()
        if lowered in _FORBIDDEN_KEYS:
            continue
        if lowered in {"audio_base64", "raw_audio"} or lowered.endswith(
            ("_embeddings", "_vectors")
        ):
            continue
        if lowered.startswith("raw_") and "embed" in lowered:
            continue
        if isinstance(value, (bytes, bytearray)):
            cleaned[key] = f"<{len(value)} bytes>"
            continue
        if isinstance(value, str):
            text = value
            for pattern in _SECRET_PATTERNS:
                text = pattern.sub("[REDACTED]", text)
            # Never dump long transcripts into diagnostics.
            if lowered in {"transcript", "text", "user_text", "assistant_text"} and len(text) > 120:
                text = text[:120] + "…"
            cleaned[key] = text
            continue
        if isinstance(value, dict):
            cleaned[key] = sanitize_diagnostic_payload(value)
            continue
        cleaned[key] = value
    return cleaned


def emit_voice_diagnostic(event_name: str, **fields: Any) -> dict[str, Any]:
    """Emit one structured diagnostic line; returns the sanitized payload."""
    payload = sanitize_diagnostic_payload(fields)
    payload["event"] = event_name
    # Flatten for log readability without embedding secrets.
    parts = " ".join(f"{k}={v!r}" for k, v in payload.items() if k != "event")
    logger.info("%s %s", event_name, parts)
    return payload
