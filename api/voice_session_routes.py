# =====================================
# Titan Live Voice Session API Routes
# =====================================

"""Authenticated live voice session endpoints (Phase 20.3).

All routes require ``require_web_auth`` (and CSRF via middleware on mutating
methods). No unauthenticated microphone or voice endpoints.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from api.auth import get_session_from_request, require_web_auth
from api.auth_config import is_session_auth_enabled
from api.titan_service import get_titan
from config import settings as app_settings
from config.settings import is_web_dev_mode
from context.session_manager import SessionManager
from core.state_manager import StateManager
from voice.exceptions import (
    VoiceConfigurationError,
    VoiceError,
    VoiceLiveSessionError,
    VoiceProviderError,
    VoiceSessionError,
)
from voice.live_session import LiveVoiceSessionOrchestrator
from voice.speaker_identifier import SpeakerIdentifier
from voice.speaker_profile_store import SpeakerProfileStore
from voice.voice_session import VoiceSessionStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/voice/session",
    tags=["voice-session"],
    dependencies=[Depends(require_web_auth)],
)

_orchestrator: LiveVoiceSessionOrchestrator | None = None


def resolve_voice_user(request: Request) -> str:
    """Map web session / dev mode to a cognitive authorized user."""
    username = getattr(request.state, "titan_username", None)
    if username:
        normalized = SessionManager.normalize_user(str(username))
        if normalized:
            return normalized
    if is_session_auth_enabled():
        session = get_session_from_request(request)
        if session is not None:
            normalized = SessionManager.normalize_user(session.username)
            if normalized:
                return normalized
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authenticated user is not an authorized voice identity.",
            )
    if is_web_dev_mode():
        return "Nolan"
    # Bearer-token path (session auth disabled): require_web_auth already passed.
    # Speaker identification still gates personal memory independently.
    return "Nolan"


def get_live_orchestrator() -> LiveVoiceSessionOrchestrator:
    """Process-scoped live voice orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        titan = get_titan()
        store = SpeakerProfileStore(
            file_path=app_settings.TITAN_VOICE_SPEAKER_PROFILES_PATH
        )
        identifier = SpeakerIdentifier(
            file_path=app_settings.TITAN_VOICE_SPEAKER_PROFILES_PATH,
            min_confidence=app_settings.TITAN_VOICE_SPEAKER_MIN_CONFIDENCE,
            medium_confidence=app_settings.TITAN_VOICE_SPEAKER_MEDIUM_CONFIDENCE,
            ambiguity_delta=app_settings.TITAN_VOICE_SPEAKER_AMBIGUITY_DELTA,
            enabled=app_settings.TITAN_VOICE_SPEAKER_ID_ENABLED,
            profile_store=store,
        )
        state_manager = StateManager(file_path=app_settings.TITAN_STATE_PATH)
        _orchestrator = LiveVoiceSessionOrchestrator(
            titan.brain,
            session_store=VoiceSessionStore(
                file_path=app_settings.TITAN_VOICE_SESSIONS_PATH
            ),
            speaker_identifier=identifier,
            state_manager=state_manager,
            temp_dir=app_settings.TITAN_VOICE_LIVE_TEMP_DIR,
        )
    return _orchestrator


def reset_live_orchestrator_for_tests() -> None:
    """Test helper — clear process-scoped orchestrator."""
    global _orchestrator
    _orchestrator = None


class StartSessionRequest(BaseModel):
    capture_mode: str = Field(default="push_to_talk")
    microphone_enabled: bool = True
    conversation_id: str | None = None


class AudioChunkRequest(BaseModel):
    session_id: str
    audio_base64: str
    sequence: int = Field(ge=0)
    timestamp_ms: float | None = None


class SessionOnlyRequest(BaseModel):
    session_id: str


class ConfirmIdentityRequest(BaseModel):
    session_id: str
    user: str | None = None


class MicrophoneRequest(BaseModel):
    session_id: str
    enabled: bool


class RecoverSessionRequest(BaseModel):
    recovery_token: str | None = None
    conversation_id: str | None = None
    capture_mode: str | None = None
    microphone_enabled: bool = True


class HeartbeatRequest(BaseModel):
    session_id: str


class CalibrateChunkRequest(BaseModel):
    session_id: str
    audio_base64: str
    sequence: int = Field(default=0, ge=0)


def _decode_audio(audio_base64: str) -> bytes:
    try:
        return base64.b64decode(audio_base64, validate=True)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid audio_base64 payload",
        ) from exc


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, VoiceConfigurationError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(exc), "code": "rejected_audio"},
        )
    if isinstance(exc, VoiceLiveSessionError):
        code = getattr(exc, "code", "live_session_error")
        status_code = status.HTTP_400_BAD_REQUEST
        if code in {"unauthorized", "unauthorized_target"}:
            status_code = status.HTTP_403_FORBIDDEN
        return HTTPException(
            status_code=status_code,
            detail={"message": str(exc), "code": code},
        )
    if isinstance(exc, VoiceSessionError):
        msg = str(exc).lower()
        status_code = status.HTTP_404_NOT_FOUND if "unknown" in msg else status.HTTP_400_BAD_REQUEST
        return HTTPException(
            status_code=status_code,
            detail={"message": str(exc), "code": "session_error"},
        )
    if isinstance(exc, VoiceProviderError):
        return HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"message": str(exc), "code": "provider_timeout"},
        )
    if isinstance(exc, VoiceError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(exc), "code": "voice_error"},
        )
    logger.exception("Unexpected voice session error")
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"message": "Internal voice session error", "code": "internal"},
    )


@router.post("/start")
def start_voice_session(
    payload: StartSessionRequest,
    request: Request,
) -> dict[str, Any]:
    user = resolve_voice_user(request)
    try:
        return get_live_orchestrator().start_session(
            authenticated_user=user,
            capture_mode=payload.capture_mode,
            microphone_enabled=payload.microphone_enabled,
            conversation_id=payload.conversation_id,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/chunk")
def submit_audio_chunk(payload: AudioChunkRequest, request: Request) -> dict[str, Any]:
    resolve_voice_user(request)
    audio = _decode_audio(payload.audio_base64)
    try:
        return get_live_orchestrator().submit_audio_chunk(
            payload.session_id,
            audio_bytes=audio,
            sequence=payload.sequence,
            timestamp_ms=payload.timestamp_ms,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/finish")
def finish_utterance(payload: SessionOnlyRequest, request: Request) -> dict[str, Any]:
    resolve_voice_user(request)
    try:
        return get_live_orchestrator().finish_utterance(payload.session_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/confirm-identity")
def confirm_identity(
    payload: ConfirmIdentityRequest, request: Request
) -> dict[str, Any]:
    resolve_voice_user(request)
    try:
        return get_live_orchestrator().confirm_identity(
            payload.session_id, user=payload.user
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/reject-identity")
def reject_identity(payload: SessionOnlyRequest, request: Request) -> dict[str, Any]:
    resolve_voice_user(request)
    try:
        return get_live_orchestrator().reject_identity(payload.session_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/interrupt")
def interrupt_playback(payload: SessionOnlyRequest, request: Request) -> dict[str, Any]:
    resolve_voice_user(request)
    try:
        return get_live_orchestrator().interrupt_playback(payload.session_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/cancel")
def cancel_session(payload: SessionOnlyRequest, request: Request) -> dict[str, Any]:
    resolve_voice_user(request)
    try:
        return get_live_orchestrator().cancel_session(payload.session_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/microphone")
def set_microphone(payload: MicrophoneRequest, request: Request) -> dict[str, Any]:
    resolve_voice_user(request)
    try:
        return get_live_orchestrator().set_microphone_enabled(
            payload.session_id, payload.enabled
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/state")
def query_session_state(session_id: str, request: Request) -> dict[str, Any]:
    resolve_voice_user(request)
    try:
        return get_live_orchestrator().get_safe_state(session_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/heartbeat")
def heartbeat_session(payload: HeartbeatRequest, request: Request) -> dict[str, Any]:
    """Keep continuous conversation alive — resets idle timeout."""
    resolve_voice_user(request)
    try:
        return get_live_orchestrator().heartbeat(payload.session_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/recover")
def recover_voice_session(
    payload: RecoverSessionRequest, request: Request
) -> dict[str, Any]:
    """Browser refresh / network reconnect recovery."""
    user = resolve_voice_user(request)
    try:
        return get_live_orchestrator().recover_session(
            authenticated_user=user,
            recovery_token=payload.recovery_token,
            conversation_id=payload.conversation_id,
            capture_mode=payload.capture_mode,
            microphone_enabled=payload.microphone_enabled,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/events")
def drain_voice_events(session_id: str, request: Request) -> dict[str, Any]:
    """Drain buffered stream diagnostics for the session (no polling loop)."""
    resolve_voice_user(request)
    try:
        return get_live_orchestrator().drain_stream_events(session_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/calibrate/start")
def start_mic_calibration(payload: SessionOnlyRequest, request: Request) -> dict[str, Any]:
    """Start mic calibration window (explicit gesture; no always-listening)."""
    resolve_voice_user(request)
    try:
        return get_live_orchestrator().start_mic_calibration(payload.session_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/calibrate/chunk")
def feed_mic_calibration(payload: CalibrateChunkRequest, request: Request) -> dict[str, Any]:
    resolve_voice_user(request)
    audio = _decode_audio(payload.audio_base64)
    try:
        return get_live_orchestrator().feed_mic_calibration(
            payload.session_id, audio_bytes=audio
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/calibrate/finish")
def finish_mic_calibration(payload: SessionOnlyRequest, request: Request) -> dict[str, Any]:
    resolve_voice_user(request)
    try:
        return get_live_orchestrator().finish_mic_calibration(payload.session_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/stats")
def voice_session_stats(session_id: str, request: Request) -> dict[str, Any]:
    """Return session statistics (latency / speech / barge-in aggregates)."""
    resolve_voice_user(request)
    try:
        return get_live_orchestrator().get_session_statistics(session_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/diagnostics/providers")
def voice_provider_diagnostics(request: Request) -> dict[str, Any]:
    """Fleet-wide provider + browser transport health (Phase 20.8)."""
    resolve_voice_user(request)
    from voice.provider_health import collect_provider_health

    return collect_provider_health()


@router.get("/diagnostics/transport")
def voice_transport_diagnostics(request: Request) -> dict[str, Any]:
    """Browser WebSocket hub connection-state snapshot (Phase 20.8)."""
    resolve_voice_user(request)
    from voice.transport.browser_hub import get_browser_voice_hub

    hub = get_browser_voice_hub()
    return {"ok": True, "browser_transport": hub.diagnostics_snapshot()}
