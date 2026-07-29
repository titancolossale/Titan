# =====================================
# Titan Voice Enrollment API Routes
# =====================================

"""Authenticated voice enrollment endpoints (Phase 20.2).

All mutating routes require ``require_web_auth`` (and CSRF via middleware).
Never accepts unauthenticated enrollment. Never returns embeddings or raw audio.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from api.auth import get_session_from_request, require_web_auth
from api.auth_config import is_session_auth_enabled
from config import settings as app_settings
from config.settings import is_web_dev_mode
from context.session_manager import SessionManager
from core.state_manager import StateManager
from voice.enrollment_models import EnrollmentConfig
from voice.exceptions import VoiceEnrollmentError
from voice.speaker_profile_store import SpeakerProfileStore
from voice.voice_enrollment import VoiceEnrollmentService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/voice/enrollment",
    tags=["voice-enrollment"],
    dependencies=[Depends(require_web_auth)],
)

_enrollment_service: VoiceEnrollmentService | None = None


def resolve_enrollment_user(request: Request) -> str:
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
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
    )


def get_enrollment_service() -> VoiceEnrollmentService:
    """Process-scoped enrollment service (shared profile store path)."""
    global _enrollment_service
    if _enrollment_service is None:
        config = EnrollmentConfig(
            min_sample_count=app_settings.TITAN_VOICE_ENROLLMENT_MIN_SAMPLES,
            max_sample_count=app_settings.TITAN_VOICE_ENROLLMENT_MAX_SAMPLES,
            min_sample_duration_seconds=app_settings.TITAN_VOICE_ENROLLMENT_MIN_DURATION,
            max_sample_duration_seconds=app_settings.TITAN_VOICE_ENROLLMENT_MAX_DURATION,
            min_quality_score=app_settings.TITAN_VOICE_ENROLLMENT_MIN_QUALITY,
            min_enrollment_confidence=app_settings.TITAN_VOICE_ENROLLMENT_MIN_CONFIDENCE,
            high_confidence=app_settings.TITAN_VOICE_SPEAKER_MIN_CONFIDENCE,
            medium_confidence=app_settings.TITAN_VOICE_SPEAKER_MEDIUM_CONFIDENCE,
            ambiguity_delta=app_settings.TITAN_VOICE_SPEAKER_AMBIGUITY_DELTA,
            max_verification_retries=app_settings.TITAN_VOICE_ENROLLMENT_MAX_VERIFY_RETRIES,
            require_consent=app_settings.TITAN_VOICE_ENROLLMENT_REQUIRE_CONSENT,
            recovery_ttl_seconds=app_settings.TITAN_VOICE_ENROLLMENT_RECOVERY_TTL,
            same_user_duplicate_threshold=app_settings.TITAN_VOICE_ENROLLMENT_SAME_USER_DUP_THRESHOLD,
            consent_version=app_settings.TITAN_VOICE_ENROLLMENT_CONSENT_VERSION,
        )
        store = SpeakerProfileStore(
            file_path=app_settings.TITAN_VOICE_SPEAKER_PROFILES_PATH
        )
        state_manager = StateManager(file_path=app_settings.TITAN_STATE_PATH)
        _enrollment_service = VoiceEnrollmentService(
            store=store,
            config=config,
            state_manager=state_manager,
            temp_dir=app_settings.TITAN_VOICE_ENROLLMENT_TEMP_DIR,
        )
    return _enrollment_service


def _decode_audio(payload: "AudioPayload") -> bytes:
    if payload.audio_base64:
        try:
            return base64.b64decode(payload.audio_base64, validate=True)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid audio_base64 payload",
            ) from exc
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="audio_base64 is required",
    )


def _http_error(exc: VoiceEnrollmentError) -> HTTPException:
    code = getattr(exc, "code", "enrollment_error")
    status_code = status.HTTP_400_BAD_REQUEST
    if code in {"unauthorized", "unauthorized_target", "unauthorized_target_mismatch"}:
        status_code = status.HTTP_403_FORBIDDEN
    elif code == "not_found":
        status_code = status.HTTP_404_NOT_FOUND
    return HTTPException(status_code=status_code, detail={"message": str(exc), "code": code})


class StartEnrollmentRequest(BaseModel):
    user: str = Field(..., description="Authorized identity: Nolan or Ibrahim")
    locale: str | None = "fr-FR"
    replace_existing: bool = False
    session_label: str | None = None
    consent_accepted: bool = False


class AudioPayload(BaseModel):
    session_id: str
    audio_base64: str


class SessionOnlyRequest(BaseModel):
    session_id: str


class ConsentRequest(BaseModel):
    session_id: str
    accepted: bool = True
    locale: str | None = None


class RecoverEnrollmentRequest(BaseModel):
    session_id: str
    recovery_token: str


class RevokeRequest(BaseModel):
    user: str
    profile_id: str | None = None


class ValidateSampleRequest(BaseModel):
    audio_base64: str


@router.post("/start")
def start_enrollment(
    body: StartEnrollmentRequest,
    request: Request,
    service: VoiceEnrollmentService = Depends(get_enrollment_service),
) -> dict[str, Any]:
    auth_user = resolve_enrollment_user(request)
    try:
        return service.start_enrollment(
            target_user=body.user,
            authenticated_user=auth_user,
            locale=body.locale,
            replace_existing=body.replace_existing,
            session_label=body.session_label,
            consent_accepted=body.consent_accepted,
        )
    except VoiceEnrollmentError as exc:
        raise _http_error(exc) from exc


@router.post("/consent")
def grant_consent(
    body: ConsentRequest,
    request: Request,
    service: VoiceEnrollmentService = Depends(get_enrollment_service),
) -> dict[str, Any]:
    auth_user = resolve_enrollment_user(request)
    try:
        return service.grant_consent(
            session_id=body.session_id,
            authenticated_user=auth_user,
            accepted=body.accepted,
            locale=body.locale,
        )
    except VoiceEnrollmentError as exc:
        raise _http_error(exc) from exc


@router.post("/recover")
def recover_enrollment(
    body: RecoverEnrollmentRequest,
    request: Request,
    service: VoiceEnrollmentService = Depends(get_enrollment_service),
) -> dict[str, Any]:
    auth_user = resolve_enrollment_user(request)
    try:
        return service.recover_enrollment(
            session_id=body.session_id,
            recovery_token=body.recovery_token,
            authenticated_user=auth_user,
        )
    except VoiceEnrollmentError as exc:
        raise _http_error(exc) from exc


@router.post("/sample")
def submit_sample(
    body: AudioPayload,
    request: Request,
    service: VoiceEnrollmentService = Depends(get_enrollment_service),
) -> dict[str, Any]:
    auth_user = resolve_enrollment_user(request)
    audio = _decode_audio(body)
    try:
        return service.submit_sample(
            session_id=body.session_id,
            audio_bytes=audio,
            authenticated_user=auth_user,
        )
    except VoiceEnrollmentError as exc:
        raise _http_error(exc) from exc


@router.post("/validate-sample")
def validate_sample(
    body: ValidateSampleRequest,
    service: VoiceEnrollmentService = Depends(get_enrollment_service),
) -> dict[str, Any]:
    try:
        audio = base64.b64decode(body.audio_base64, validate=True)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid audio_base64 payload",
        ) from exc
    return {"ok": True, "validation": service.validate_sample(audio_bytes=audio)}


@router.post("/finish")
def finish_enrollment(
    body: SessionOnlyRequest,
    request: Request,
    service: VoiceEnrollmentService = Depends(get_enrollment_service),
) -> dict[str, Any]:
    auth_user = resolve_enrollment_user(request)
    try:
        return service.finish_enrollment(
            session_id=body.session_id,
            authenticated_user=auth_user,
        )
    except VoiceEnrollmentError as exc:
        raise _http_error(exc) from exc


@router.post("/verify")
def verify_enrollment(
    body: AudioPayload,
    request: Request,
    service: VoiceEnrollmentService = Depends(get_enrollment_service),
) -> dict[str, Any]:
    auth_user = resolve_enrollment_user(request)
    audio = _decode_audio(body)
    try:
        return service.verify_enrollment(
            session_id=body.session_id,
            audio_bytes=audio,
            authenticated_user=auth_user,
        )
    except VoiceEnrollmentError as exc:
        raise _http_error(exc) from exc


@router.post("/cancel")
def cancel_enrollment(
    body: SessionOnlyRequest,
    request: Request,
    service: VoiceEnrollmentService = Depends(get_enrollment_service),
) -> dict[str, Any]:
    auth_user = resolve_enrollment_user(request)
    try:
        return service.cancel_enrollment(
            session_id=body.session_id,
            authenticated_user=auth_user,
        )
    except VoiceEnrollmentError as exc:
        raise _http_error(exc) from exc


@router.post("/revoke")
def revoke_profile(
    body: RevokeRequest,
    request: Request,
    service: VoiceEnrollmentService = Depends(get_enrollment_service),
) -> dict[str, Any]:
    auth_user = resolve_enrollment_user(request)
    try:
        return service.revoke_profile(
            user_id=body.user,
            authenticated_user=auth_user,
            profile_id=body.profile_id,
        )
    except VoiceEnrollmentError as exc:
        raise _http_error(exc) from exc


@router.get("/status")
def enrollment_status(
    request: Request,
    session_id: str | None = None,
    user: str | None = None,
    service: VoiceEnrollmentService = Depends(get_enrollment_service),
) -> dict[str, Any]:
    auth_user = resolve_enrollment_user(request)
    target = user or auth_user
    try:
        return service.get_status(
            user_id=target,
            session_id=session_id,
            authenticated_user=auth_user,
        )
    except VoiceEnrollmentError as exc:
        raise _http_error(exc) from exc


@router.get("/scripts")
def enrollment_scripts() -> dict[str, Any]:
    from voice.enrollment_consent import list_consent_prompts
    from voice.enrollment_scripts import list_enrollment_scripts

    return {
        "ok": True,
        "scripts": list_enrollment_scripts(),
        "consent_prompts": list_consent_prompts(),
    }


@router.get("/preflight")
def enrollment_preflight(
    request: Request,
    service: VoiceEnrollmentService = Depends(get_enrollment_service),
) -> dict[str, Any]:
    """Production enrollment pre-flight — never records biometric samples."""
    from voice.enrollment_preflight import run_enrollment_preflight

    # Auth required by router dependency; user identity not needed for host checks.
    _ = resolve_enrollment_user(request)
    return run_enrollment_preflight(store=service.store, force_ecapa_load=False)


@router.get("/diagnostics")
def enrollment_diagnostics(
    request: Request,
    user: str | None = None,
    service: VoiceEnrollmentService = Depends(get_enrollment_service),
) -> dict[str, Any]:
    from voice.enrollment_diagnostics import collect_enrollment_diagnostics

    auth_user = resolve_enrollment_user(request)
    target = user or auth_user
    return collect_enrollment_diagnostics(store=service.store, user_id=target)


@router.get("/audit")
def enrollment_audit(
    request: Request,
    user: str | None = None,
    session_id: str | None = None,
    limit: int = 50,
    service: VoiceEnrollmentService = Depends(get_enrollment_service),
) -> dict[str, Any]:
    """Safe enrollment audit history — never returns embeddings or audio."""
    auth_user = resolve_enrollment_user(request)
    target = user or auth_user
    return {
        "ok": True,
        "user_id": target,
        "audit_history": service.store.list_audit_history(
            user_id=target,
            session_id=session_id,
            limit=max(1, min(limit, 200)),
        ),
    }


@router.get("/workflow")
def enrollment_workflow_status(
    request: Request,
    session_id: str | None = None,
    user: str | None = None,
    service: VoiceEnrollmentService = Depends(get_enrollment_service),
) -> dict[str, Any]:
    """Production enrollment workflow snapshot for an in-flight or last session."""
    auth_user = resolve_enrollment_user(request)
    target = user or auth_user
    try:
        status = service.get_status(
            user_id=target,
            session_id=session_id,
            authenticated_user=auth_user,
        )
    except VoiceEnrollmentError as exc:
        raise _http_error(exc) from exc
    return {
        "ok": True,
        "workflow": status.get("workflow"),
        "session": status.get("session"),
        "verification_thresholds": status.get("verification_thresholds"),
    }