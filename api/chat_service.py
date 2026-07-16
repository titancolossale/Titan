# =====================================
# Titan Web Chat Service
# =====================================

"""Canonical web chat path — shared Brain via ``Brain.process_request()``."""

from __future__ import annotations

import copy
import logging
import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

from api.memory_activity import format_memory_activity
from api.orchestrator_progress import (
    current_neural_state_from_context,
    format_orchestrator_progress,
)
from api.tool_activity import collect_audit_events_since, format_tool_activity
from api.titan_service import _audit_start_index, get_titan
from brain.llm import LLM_ERROR_MESSAGE, LLM_TIMEOUT_MESSAGE
from brain.natural_language_orchestrator import DetectedIntent, OrchestrationResult
from config.settings import (
    LLM_MODEL,
    TITAN_CHAT_DIAGNOSTICS,
    TITAN_WEB_MAX_MESSAGE_LENGTH,
)

logger = logging.getLogger(__name__)

_brain_lock = threading.Lock()

# Idempotency: duplicate client request_id returns the cached payload (same turn).
_IDEMPOTENCY_MAX = 256
_idempotency_lock = threading.Lock()
_idempotency_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()

# Safe last-error for authenticated diagnostics (no message content / secrets).
_last_diag_lock = threading.Lock()
_last_diag: dict[str, Any] = {
    "error_code": None,
    "request_id": None,
    "at": None,
}

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

# Map real orchestrator phases → safe operational stage ids for telemetry.
_PHASE_TO_STAGE: dict[str, str] = {
    "understanding": "understanding",
    "planning": "planning",
    "memory": "retrieving_memory",
    "research": "selecting_tools",
    "writing": "generating",
    "verification": "finished",
}

PROVIDER_UNAVAILABLE_CODE = "provider_unavailable"
PROVIDER_UNAVAILABLE_MESSAGE = (
    "Titan ne peut pas joindre son modèle pour le moment."
)
PROVIDER_TIMEOUT_CODE = "provider_timeout"
PROVIDER_TIMEOUT_MESSAGE = (
    "Titan n’a pas pu répondre dans le délai prévu. Réessaie."
)
BRAIN_FAILURE_CODE = "brain_failure"
BRAIN_FAILURE_MESSAGE = (
    "Désolé, une erreur interne s'est produite. On peut réessayer."
)
DUPLICATE_REQUEST_CODE = "duplicate_request"


def _chat_log(event: str, **fields: Any) -> None:
    """Concise correlation logs — gated; never logs message content."""
    if not TITAN_CHAT_DIAGNOSTICS:
        return
    parts = [f"{key}={value}" for key, value in fields.items() if value is not None]
    logger.info("%s %s", event, " ".join(parts))


def _elapsed_ms(started: datetime) -> int:
    return int((datetime.now(timezone.utc) - started).total_seconds() * 1000)


def _record_diag_error(code: str | None, request_id: str | None = None) -> None:
    with _last_diag_lock:
        _last_diag["error_code"] = code
        _last_diag["request_id"] = request_id
        _last_diag["at"] = datetime.now(timezone.utc).isoformat()


def get_last_chat_diag() -> dict[str, Any]:
    """Return last safe chat diagnostic snapshot (no secrets / message bodies)."""
    with _last_diag_lock:
        return dict(_last_diag)


def _new_request_id(request_id: str | None) -> str:
    cleaned = (request_id or "").strip()
    return cleaned[:128] if cleaned else uuid.uuid4().hex


def _new_message_id() -> str:
    return f"msg-{uuid.uuid4().hex[:16]}"


def _cache_get(request_id: str) -> dict[str, Any] | None:
    with _idempotency_lock:
        cached = _idempotency_cache.get(request_id)
        if cached is None:
            return None
        _idempotency_cache.move_to_end(request_id)
        return copy.deepcopy(cached)


def _cache_put(request_id: str, payload: dict[str, Any]) -> None:
    with _idempotency_lock:
        _idempotency_cache[request_id] = copy.deepcopy(payload)
        _idempotency_cache.move_to_end(request_id)
        while len(_idempotency_cache) > _IDEMPOTENCY_MAX:
            _idempotency_cache.popitem(last=False)


def clear_idempotency_cache() -> None:
    """Test helper — clear duplicate-request cache."""
    with _idempotency_lock:
        _idempotency_cache.clear()


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


def _is_provider_timeout(result: OrchestrationResult) -> bool:
    artifacts = result.artifacts or {}
    if artifacts.get("error") == PROVIDER_TIMEOUT_CODE:
        return True
    response = (result.final_response or "").strip()
    return response == LLM_TIMEOUT_MESSAGE.strip()


def _is_provider_failure(result: OrchestrationResult) -> bool:
    """Detect LLM provider failure without inventing a successful answer."""
    if _is_provider_timeout(result):
        return True
    artifacts = result.artifacts or {}
    if artifacts.get("error") in {PROVIDER_UNAVAILABLE_CODE, "llm_unavailable"}:
        return True
    response = (result.final_response or "").strip()
    return response == LLM_ERROR_MESSAGE.strip()


def _memory_was_used(memory_activity: list[dict[str, Any]]) -> bool:
    """True only when retrieval returned usable context — never invent hits."""
    for record in memory_activity:
        if record.get("has_matches") is True:
            return True
        if int(record.get("match_count") or 0) > 0:
            return True
        if record.get("phase") == "recall" and record.get("state") != "empty":
            return True
    return False


def _tools_used(tool_activity: list[dict[str, Any]]) -> list[str]:
    """Tool names that actually executed — never invent catalog entries."""
    names: list[str] = []
    seen: set[str] = set()
    for record in tool_activity:
        tool = str(record.get("tool") or "").strip()
        if not tool or tool in seen:
            continue
        if record.get("state") in {"blocked", "skipped", "cancelled"}:
            continue
        seen.add(tool)
        names.append(tool)
    return names


def _runtime_stages(
    *,
    orchestrator_progress: list[dict[str, Any]],
    memory_used: bool,
    tools_used: list[str],
    execution_status: str,
    provider_failure: bool,
) -> list[str]:
    """Build honest stage list from real progress only."""
    stages: list[str] = ["receiving"]
    seen: set[str] = set(stages)

    def _add(stage: str) -> None:
        if stage and stage not in seen:
            seen.add(stage)
            stages.append(stage)

    for record in orchestrator_progress:
        phase = str(record.get("phase") or "").lower()
        mapped = _PHASE_TO_STAGE.get(phase)
        if mapped:
            _add(mapped)
        if record.get("tool") and "selecting_tools" not in seen:
            _add("selecting_tools")
            _add("executing_tools")

    if memory_used:
        _add("retrieving_memory")
    if tools_used:
        _add("selecting_tools")
        _add("executing_tools")

    if provider_failure or execution_status == "error":
        _add("error")
    else:
        _add("generating")
        _add("finished")

    return stages


def build_runtime_summary(
    *,
    tool_activity: list[dict[str, Any]],
    memory_activity: list[dict[str, Any]],
    orchestrator_progress: list[dict[str, Any]],
    duration_seconds: float,
    execution_status: str,
    provider_failure: bool = False,
) -> dict[str, Any]:
    """Honest runtime object for Phase 11.1 contract."""
    memory_used = _memory_was_used(memory_activity)
    tools = _tools_used(tool_activity)
    state = "error" if provider_failure or execution_status == "error" else "finished"
    if execution_status == "awaiting_approval":
        state = "awaiting_approval"
    return {
        "state": state,
        "stages": _runtime_stages(
            orchestrator_progress=orchestrator_progress,
            memory_used=memory_used,
            tools_used=tools,
            execution_status=execution_status,
            provider_failure=provider_failure,
        ),
        "memory_used": memory_used,
        "tools_used": tools,
        "model": LLM_MODEL,
        "duration_ms": int(round(max(duration_seconds, 0.0) * 1000)),
    }


def build_chat_response(
    *,
    result: OrchestrationResult,
    titan: Any,
    request_id: str,
    conversation_id: str,
    tool_activity: list[dict[str, Any]],
    memory_activity: list[dict[str, Any]],
    orchestrator_progress: list[dict[str, Any]],
    message_id: str | None = None,
) -> dict[str, Any]:
    """Serialize orchestration result into a user-safe API payload."""
    approval = _extract_approval(result)
    think_ctx = titan.brain.last_think_context
    timed_out = _is_provider_timeout(result)
    provider_failure = _is_provider_failure(result)
    if provider_failure:
        approval["execution_status"] = "error"

    brain_state = _brain_state_for_result(result, think_ctx, approval)
    if provider_failure:
        brain_state = "error"

    artifacts = dict(result.artifacts or {})
    if timed_out:
        artifacts.setdefault("error", PROVIDER_TIMEOUT_CODE)
    elif provider_failure:
        artifacts.setdefault("error", PROVIDER_UNAVAILABLE_CODE)

    pipeline_summary = {
        "intent": result.detected_intent.value,
        "systems": result.pipeline_decision.to_dict(),
        "artifacts_summary": _safe_artifacts_summary(artifacts),
    }

    errors = _build_errors(result)
    error_code = None
    if timed_out:
        error_code = PROVIDER_TIMEOUT_CODE
        if PROVIDER_TIMEOUT_CODE not in errors:
            errors.append(PROVIDER_TIMEOUT_CODE)
    elif provider_failure:
        error_code = PROVIDER_UNAVAILABLE_CODE
        if PROVIDER_UNAVAILABLE_CODE not in errors:
            errors.append(PROVIDER_UNAVAILABLE_CODE)
    elif BRAIN_FAILURE_CODE in errors:
        error_code = BRAIN_FAILURE_CODE

    ok = not provider_failure and approval["execution_status"] != "error"
    runtime = build_runtime_summary(
        tool_activity=tool_activity,
        memory_activity=memory_activity,
        orchestrator_progress=orchestrator_progress,
        duration_seconds=result.duration_seconds,
        execution_status=approval["execution_status"],
        provider_failure=provider_failure,
    )

    response_text = result.final_response
    if timed_out:
        response_text = PROVIDER_TIMEOUT_MESSAGE
    elif provider_failure:
        response_text = PROVIDER_UNAVAILABLE_MESSAGE

    return {
        "ok": ok,
        "message_id": message_id or _new_message_id(),
        "request_id": request_id,
        "conversation_id": conversation_id,
        "response": response_text,
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
        "errors": errors,
        "tool_activity": tool_activity,
        "memory_activity": memory_activity,
        "orchestrator_progress": orchestrator_progress,
        "duration_seconds": round(result.duration_seconds, 4),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "runtime": runtime,
        "error_code": error_code,
        "retryable": bool(error_code),
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

    client_provided_id = bool((request_id or "").strip())
    req_id = _new_request_id(request_id)
    started = datetime.now(timezone.utc)

    if client_provided_id:
        cached = _cache_get(req_id)
        if cached is not None:
            _chat_log(
                "CHAT_API_RECEIVED",
                request_id=req_id,
                code=DUPLICATE_REQUEST_CODE,
                message_length=len(text),
            )
            cached = copy.deepcopy(cached)
            cached["duplicate"] = True
            return cached

    _chat_log(
        "CHAT_API_RECEIVED",
        request_id=req_id,
        message_length=len(text),
        conversation_id=(conversation_id or "")[:32] or None,
        elapsed_ms=0,
        stage="received",
    )

    if client_metadata:
        logger.debug(
            "Web chat metadata request_id=%s keys=%s",
            req_id,
            list(client_metadata.keys()),
        )

    titan = get_titan()
    conv_id = _resolve_conversation_id(titan, conversation_id)
    message_id = _new_message_id()
    llm = getattr(getattr(titan, "brain", None), "llm", None)
    model_name = getattr(llm, "model", None) or LLM_MODEL

    with _brain_lock:
        if user:
            titan.context.session.set_user(user)

        speaker = titan.context.current_user
        titan.conversation.add_message(speaker, text)

        audit_start = _audit_start_index(titan)

        # Thread request_id into LLM for CHAT_PROVIDER_* correlation.
        if llm is not None:
            setattr(llm, "_active_request_id", req_id)

        _chat_log(
            "CHAT_BRAIN_START",
            request_id=req_id,
            conversation_id=conv_id,
            elapsed_ms=_elapsed_ms(started),
            stage="brain",
            model=model_name,
        )
        brain_error = False
        try:
            # Provider timeout is enforced by OpenAI client (TITAN_LLM_TIMEOUT_SECONDS).
            # This call is sync and must run off the FastAPI event loop (threadpool / to_thread).
            result = titan.brain.process_request(text, stream=stream)
        except Exception:
            brain_error = True
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
                final_response=BRAIN_FAILURE_MESSAGE,
                artifacts={"error": BRAIN_FAILURE_CODE},
                duration_seconds=0.0,
            )
            _record_diag_error(BRAIN_FAILURE_CODE, req_id)
            _chat_log(
                "CHAT_REQUEST_ERROR",
                request_id=req_id,
                elapsed_ms=_elapsed_ms(started),
                stage="brain",
                status="error",
                code=BRAIN_FAILURE_CODE,
                model=model_name,
            )
        finally:
            if llm is not None:
                setattr(llm, "_active_request_id", None)

        _chat_log(
            "CHAT_BRAIN_END",
            request_id=req_id,
            elapsed_ms=_elapsed_ms(started),
            stage="brain",
            status="error" if brain_error else "ok",
            model=model_name,
        )

        response_text = result.final_response
        if _is_provider_timeout(result):
            response_text = PROVIDER_TIMEOUT_MESSAGE
            _record_diag_error(PROVIDER_TIMEOUT_CODE, req_id)
            _chat_log(
                "CHAT_REQUEST_TIMEOUT",
                request_id=req_id,
                elapsed_ms=_elapsed_ms(started),
                stage="provider",
                status="timeout",
                code=PROVIDER_TIMEOUT_CODE,
                model=model_name,
            )
        elif _is_provider_failure(result):
            response_text = PROVIDER_UNAVAILABLE_MESSAGE
            _record_diag_error(PROVIDER_UNAVAILABLE_CODE, req_id)
            _chat_log(
                "CHAT_REQUEST_ERROR",
                request_id=req_id,
                elapsed_ms=_elapsed_ms(started),
                stage="provider",
                status="error",
                code=PROVIDER_UNAVAILABLE_CODE,
                model=model_name,
            )
        titan.conversation.add_message("Titan", response_text)

        tool_activity, memory_activity, orchestrator_progress = _collect_activity(
            titan,
            audit_start,
        )

    payload = build_chat_response(
        result=result,
        titan=titan,
        request_id=req_id,
        conversation_id=conv_id,
        tool_activity=tool_activity,
        memory_activity=memory_activity,
        orchestrator_progress=orchestrator_progress,
        message_id=message_id,
    )

    duration_ms = _elapsed_ms(started)
    _chat_log(
        "CHAT_RESPONSE_SERIALIZED",
        request_id=req_id,
        elapsed_ms=duration_ms,
        stage="serialize",
        status="ok" if payload.get("ok") else "error",
        code=payload.get("error_code"),
        model=model_name,
    )
    _chat_log(
        "CHAT_API_RESPONSE",
        request_id=req_id,
        status="ok" if payload.get("ok") else "error",
        code=payload.get("error_code"),
        duration_ms=duration_ms,
        elapsed_ms=duration_ms,
        stage="response",
        model=model_name,
    )
    _chat_log(
        "CHAT_RESPONSE_SENT",
        request_id=req_id,
        elapsed_ms=duration_ms,
        stage="sent",
        status="ok" if payload.get("ok") else "error",
        model=model_name,
    )

    if client_provided_id:
        _cache_put(req_id, payload)

    return payload

