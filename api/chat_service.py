# =====================================
# Titan Web Chat Service
# =====================================

"""Canonical web chat path — shared Brain via ``Brain.process_request()``."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from api.memory_activity import format_memory_activity
from api.orchestrator_progress import (
    current_neural_state_from_context,
    format_orchestrator_progress,
)
from api.tool_activity import collect_audit_events_since, format_tool_activity
from api.titan_service import _audit_start_index, get_titan
from brain.natural_language_orchestrator import DetectedIntent, OrchestrationResult
from config.settings import TITAN_WEB_MAX_MESSAGE_LENGTH

logger = logging.getLogger(__name__)

_brain_lock = threading.Lock()

_CONVERSATION_INTENTS = frozenset({
    DetectedIntent.CONVERSATION.value,
    DetectedIntent.QUESTION.value,
})

_SECRET_SUBSTRINGS = (
    "openai_api_key",
    "titan_web_secret",
    "secret_key",
    "api_key",
    "password",
    "token",
)


def _new_request_id(request_id: str | None) -> str:
    cleaned = (request_id or "").strip()
    return cleaned[:128] if cleaned else uuid.uuid4().hex


def _resolve_conversation_id(titan: Any, conversation_id: str | None) -> str:
    """Map client conversation id to the active session — no second memory store."""
    cleaned = (conversation_id or "").strip()
    if cleaned:
        return cleaned[:128]
    session = getattr(getattr(titan, "context", None), "session", None)
    if session is not None and getattr(session, "session_id", None):
        return str(session.session_id)
    return uuid.uuid4().hex[:12]


def _sanitize_text(value: str, *, max_len: int = 4000) -> str:
    text = str(value or "")
    lowered = text.lower()
    for marker in _SECRET_SUBSTRINGS:
        if marker in lowered:
            return "[redacted]"
    return text[:max_len]


def _safe_artifacts_summary(artifacts: dict[str, Any]) -> dict[str, Any]:
    """Expose only user-safe artifact keys — no filesystem paths or secrets."""
    if not artifacts:
        return {}
    safe: dict[str, Any] = {}
    allowed_keys = (
        "awareness",
        "goal_plan",
        "architecture",
        "code_plan",
        "generated_patch",
        "patch_preview",
        "patch_application",
        "missions",
        "focus",
        "workspace",
        "developer_enrichment",
        "think_response",
        "error",
    )
    for key in allowed_keys:
        if key not in artifacts:
            continue
        value = artifacts[key]
        if key == "error":
            safe[key] = _sanitize_text(str(value), max_len=200)
            continue
        if isinstance(value, dict):
            safe[key] = {k: _sanitize_text(str(v), max_len=300) for k, v in value.items()}
        elif isinstance(value, list):
            safe[key] = [_sanitize_text(str(item), max_len=200) for item in value[:8]]
        elif isinstance(value, bool):
            safe[key] = value
        else:
            safe[key] = _sanitize_text(str(value), max_len=500)
    return safe


def _extract_approval(result: OrchestrationResult) -> dict[str, Any]:
    """Detect approval-required operations from orchestration artifacts."""
    artifacts = result.artifacts or {}
    approval_required = False
    approval_id: str | None = None
    approval_summary: str | None = None
    execution_status = "completed"

    patch = artifacts.get("generated_patch")
    if patch is not None:
        approved = getattr(patch, "approved", False)
        if isinstance(patch, dict):
            approved = bool(patch.get("approved", False))
        if not approved:
            approval_required = True
            execution_status = "awaiting_approval"
            approval_id = (
                getattr(patch, "patch_id", None)
                or getattr(patch, "transaction_id", None)
                or (patch.get("patch_id") if isinstance(patch, dict) else None)
            )
            approval_summary = (
                "Un patch généré est en attente d'approbation avant application."
            )

    if artifacts.get("tool_confirmation_required"):
        approval_required = True
        execution_status = "awaiting_approval"
        approval_id = str(artifacts.get("confirmation_token") or approval_id or "")
        approval_summary = str(
            artifacts.get("tool_confirmation_message")
            or "Une action outil nécessite une confirmation."
        )

    if artifacts.get("error") and not approval_required:
        execution_status = "error"

    return {
        "execution_status": execution_status,
        "approval_required": approval_required,
        "approval_id": approval_id,
        "approval_summary": approval_summary,
    }


def _brain_state_for_result(
    result: OrchestrationResult,
    think_ctx: Any,
    approval: dict[str, Any],
) -> str:
    if approval.get("approval_required"):
        return "awaiting_approval"
    if approval.get("execution_status") == "error":
        return "error"
    if result.detected_intent == DetectedIntent.PLANNING:
        return "planning"
    if result.detected_intent.value in _CONVERSATION_INTENTS and think_ctx is not None:
        return current_neural_state_from_context(think_ctx)
    if result.detected_intent in {
        DetectedIntent.TOOL_REQUEST,
        DetectedIntent.RESEARCH,
    }:
        return "executing"
    return "completed"


def _collect_activity(titan: Any, audit_start: int) -> tuple[list[dict], list[dict], list[dict]]:
    think_ctx = titan.brain.last_think_context
    audit_events = collect_audit_events_since(titan, audit_start)
    tool_activity = format_tool_activity(audit_events, think_ctx)
    memory_activity = format_memory_activity(think_ctx)
    orchestrator_progress = format_orchestrator_progress(think_ctx)
    return tool_activity, memory_activity, orchestrator_progress


def _build_warnings(result: OrchestrationResult) -> list[str]:
    warnings: list[str] = []
    if result.confidence < 0.45:
        warnings.append("Confiance faible sur l'intention détectée.")
    skipped = result.systems_used.skipped if result.systems_used else []
    if skipped:
        warnings.append(f"Systèmes ignorés : {', '.join(skipped[:5])}.")
    return warnings


def _build_errors(result: OrchestrationResult) -> list[str]:
    error = (result.artifacts or {}).get("error")
    if not error:
        return []
    return [_sanitize_text(str(error), max_len=200)]


def build_chat_response(
    *,
    result: OrchestrationResult,
    titan: Any,
    request_id: str,
    conversation_id: str,
    tool_activity: list[dict[str, Any]],
    memory_activity: list[dict[str, Any]],
    orchestrator_progress: list[dict[str, Any]],
) -> dict[str, Any]:
    """Serialize orchestration result into a user-safe API payload."""
    approval = _extract_approval(result)
    think_ctx = titan.brain.last_think_context
    brain_state = _brain_state_for_result(result, think_ctx, approval)
    pipeline_summary = {
        "intent": result.detected_intent.value,
        "systems": result.pipeline_decision.to_dict(),
        "artifacts_summary": _safe_artifacts_summary(result.artifacts),
    }

    return {
        "request_id": request_id,
        "conversation_id": conversation_id,
        "response": result.final_response,
        "user": titan.context.current_user,
        "detected_intent": result.detected_intent.value,
        "confidence": round(result.confidence, 3),
        "systems_used": result.systems_used.to_dict(),
        "pipeline_summary": pipeline_summary,
        "reasoning_summary": _sanitize_text(result.reasoning_summary),
        "brain_state": brain_state,
        "execution_status": approval["execution_status"],
        "approval_required": approval["approval_required"],
        "approval_id": approval["approval_id"],
        "approval_summary": approval["approval_summary"],
        "warnings": _build_warnings(result),
        "errors": _build_errors(result),
        "tool_activity": tool_activity,
        "memory_activity": memory_activity,
        "orchestrator_progress": orchestrator_progress,
        "duration_seconds": round(result.duration_seconds, 4),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def validate_message_size(message: str) -> None:
    """Raise ValueError when message exceeds configured limit."""
    if len(message) > TITAN_WEB_MAX_MESSAGE_LENGTH:
        raise ValueError(
            f"Message exceeds maximum length ({TITAN_WEB_MAX_MESSAGE_LENGTH} characters)."
        )


def process_chat_message(
    message: str,
    *,
    user: str | None = None,
    conversation_id: str | None = None,
    request_id: str | None = None,
    client_metadata: dict[str, str] | None = None,
    stream: Any = None,
) -> dict[str, Any]:
    """Process a web chat message through the shared Brain (thread-safe)."""
    text = (message or "").strip()
    if not text:
        raise ValueError("Message cannot be empty.")
    validate_message_size(text)

    req_id = _new_request_id(request_id)
    if client_metadata:
        logger.debug(
            "Web chat metadata request_id=%s keys=%s",
            req_id,
            list(client_metadata.keys()),
        )

    titan = get_titan()
    conv_id = _resolve_conversation_id(titan, conversation_id)

    with _brain_lock:
        if user:
            titan.context.session.set_user(user)

        speaker = titan.context.current_user
        titan.conversation.add_message(speaker, text)

        audit_start = _audit_start_index(titan)

        try:
            result = titan.brain.process_request(text, stream=stream)
        except Exception:
            logger.exception("Brain.process_request failure during web chat")
            from brain.natural_language_orchestrator import SystemsUsed

            nlo = titan.brain.natural_language_orchestrator
            analysis = nlo._analyze_request(text)
            result = OrchestrationResult(
                request_analysis=analysis,
                detected_intent=DetectedIntent.CONVERSATION,
                pipeline_decision=nlo._build_pipeline(
                    DetectedIntent.CONVERSATION,
                    analysis,
                    "fallback",
                ),
                systems_used=SystemsUsed(),
                reasoning_summary="Erreur interne pendant l'orchestration.",
                confidence=0.0,
                final_response=(
                    "Désolé, une erreur interne s'est produite. On peut réessayer."
                ),
                artifacts={"error": "brain_failure"},
                duration_seconds=0.0,
            )

        response_text = result.final_response
        titan.conversation.add_message("Titan", response_text)

        tool_activity, memory_activity, orchestrator_progress = _collect_activity(
            titan,
            audit_start,
        )

    return build_chat_response(
        result=result,
        titan=titan,
        request_id=req_id,
        conversation_id=conv_id,
        tool_activity=tool_activity,
        memory_activity=memory_activity,
        orchestrator_progress=orchestrator_progress,
    )
