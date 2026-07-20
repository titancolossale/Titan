# =====================================
# Titan Stream Service
# =====================================

"""Streaming chat and event emission for Frontend V2 — Phase E8 + E9 + Web Runtime V1."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from api.chat_service import process_chat_message
from api.event_hub import event_hub
from api.memory_activity import format_memory_activity
from api.orchestrator_progress import (
    current_neural_state_from_context,
    format_orchestrator_progress,
)
from api.tool_activity import collect_audit_events_since, format_tool_activity
from api.titan_service import _audit_start_index, get_titan
from brain.cognitive_models import CognitivePhase, ProgressEvent
from brain.cognitive_progress import resolve_neural_state
from brain.cognitive_stream import CognitiveStreamEmitter
from brain.natural_language_orchestrator import DetectedIntent

logger = logging.getLogger(__name__)

EmitCallback = Callable[[str, dict[str, Any]], None]

_LEGACY_EVENT_MAP: dict[str, str] = {
    "thinking_started": "thinking",
    "planning": "planning",
    "reasoning": "reasoning",
    "verification": "reasoning",
}

_INTENT_NEURAL_STATE: dict[str, str] = {
    DetectedIntent.PLANNING.value: "planning",
    DetectedIntent.TOOL_REQUEST.value: "tool_usage",
    DetectedIntent.RESEARCH.value: "tool_usage",
    DetectedIntent.CODE_PLANNING.value: "planning",
    DetectedIntent.CODE_GENERATION.value: "planning",
    DetectedIntent.PATCH_PREVIEW.value: "deep_analysis",
    DetectedIntent.PATCH_APPLICATION.value: "tool_usage",
    DetectedIntent.MISSION_MANAGEMENT.value: "planning",
    DetectedIntent.MEMORY.value: "memory_retrieval",
    DetectedIntent.ARCHITECTURE.value: "deep_analysis",
    DetectedIntent.PROJECT_ANALYSIS.value: "deep_analysis",
}


def _default_emit(event_type: str, data: dict[str, Any]) -> None:
    event_hub.publish(event_type, data)


def _emit_brain_state(emit: EmitCallback, think_ctx: Any = None) -> None:
    neural = current_neural_state_from_context(think_ctx)
    emit("brain_state", {"state": neural})


def _emit_presence(emit: EmitCallback, state: str) -> None:
    emit("presence", {"state": state})


def _emit_legacy_alias(emit: EmitCallback, event_type: str, data: dict[str, Any]) -> None:
    legacy = _LEGACY_EVENT_MAP.get(event_type)
    if legacy:
        emit(legacy, data)
    if event_type in {
        "thinking_started",
        "intent_detected",
        "memory_lookup",
        "memory_hit",
        "memory_miss",
        "obsidian_lookup",
        "tool_selection",
        "tool_execution",
        "reasoning",
        "planning",
        "verification",
        "response_building",
        "response_ready",
        "thinking_finished",
        "orchestration_started",
        "orchestration_finished",
    }:
        emit("conversation_stage", {
            "phase": data.get("phase", event_type),
            "label": data.get("label", event_type),
            "neural_state": data.get("neural_state", "thinking"),
            "tool": data.get("tool"),
            "stage": event_type,
        })


def _map_progress_to_e9(event: ProgressEvent) -> tuple[str, dict[str, Any]]:
    phase = event.phase
    neural = resolve_neural_state(event.phase, event.tool)
    payload: dict[str, Any] = {
        "label": event.label,
        "neural_state": neural,
        "tool": event.tool,
        "phase": phase.value,
        "node_id": event.node_id,
    }

    if phase == CognitivePhase.UNDERSTANDING:
        return "intent_detected", payload
    if phase == CognitivePhase.PLANNING:
        return "planning", payload
    if phase == CognitivePhase.MEMORY:
        if event.tool and "obsidian" in (event.tool or "").lower():
            return "obsidian_lookup", payload
        return "memory_lookup", payload
    if phase == CognitivePhase.RESEARCH:
        if event.tool:
            return "tool_execution", payload
        return "tool_selection", payload
    if phase == CognitivePhase.WRITING:
        return "response_building", payload
    if phase == CognitivePhase.VERIFICATION:
        return "verification", payload
    return "reasoning", payload


def _emit_progress_event(emit: EmitCallback, event: ProgressEvent) -> None:
    e9_type, payload = _map_progress_to_e9(event)
    emit(e9_type, payload)
    _emit_legacy_alias(emit, e9_type, payload)
    _emit_brain_state(emit)


def _build_telemetry(titan: Any) -> dict[str, Any]:
    tools = getattr(titan, "tools", None)
    dashboard = tools.export_provider_dashboard() if tools else {}
    return {
        "status": titan.status,
        "version": titan.version,
        "user": titan.context.current_user,
        "provider_dashboard": dashboard,
    }


def _emit_honest_post_stages(
    emit: EmitCallback,
    *,
    tool_activity: list[dict[str, Any]],
    memory_activity: list[dict[str, Any]],
    orchestrator_progress: list[dict[str, Any]],
) -> None:
    """Emit stages only from real Brain activity — never invent tool/memory use."""
    for record in orchestrator_progress:
        phase = str(record.get("phase") or "understanding")
        emit("conversation_stage", {
            "phase": phase,
            "label": record.get("label", phase),
            "neural_state": record.get("neural_state", "thinking"),
            "tool": record.get("tool"),
            "stage": phase,
        })

    for record in memory_activity:
        if not (
            record.get("has_matches") is True
            or int(record.get("match_count") or 0) > 0
            or record.get("phase") == "recall"
        ):
            continue
        emit("memory_activity", record)
        emit("conversation_stage", {
            "phase": "memory",
            "label": record.get("title") or record.get("status_line") or "Mémoire",
            "neural_state": "memory_retrieval",
            "stage": "retrieving_memory",
        })

    for record in tool_activity:
        if record.get("state") in {"blocked", "skipped", "cancelled"}:
            continue
        tool_name = record.get("tool")
        if not tool_name:
            continue
        emit("tool_activity", record)
        emit("conversation_stage", {
            "phase": "research",
            "label": record.get("status_line") or tool_name,
            "neural_state": "tool_usage",
            "tool": tool_name,
            "stage": "executing_tools",
        })


def emit_initial_status(emit: EmitCallback | None = None) -> list[tuple[str, dict[str, Any]]]:
    """Emit status, brain_state, and telemetry on SSE connect."""
    emitted: list[tuple[str, dict[str, Any]]] = []

    def publisher(event_type: str, data: dict[str, Any]) -> None:
        emitted.append((event_type, data))
        if emit is not None:
            emit(event_type, data)
        else:
            event_hub.publish(event_type, data)

    titan = get_titan()
    titan.context.refresh()
    publisher("status", {
        "name": titan.name,
        "version": titan.version,
        "status": titan.status,
        "user": titan.context.current_user,
    })
    _emit_brain_state(publisher)
    _emit_presence(publisher, "idle")
    publisher("telemetry", _build_telemetry(titan))
    return emitted


def _emit_non_conversation_stages(
    emit: EmitCallback,
    *,
    intent: str,
    label: str,
) -> None:
    """Deprecated — kept for import compatibility; does not emit synthetic stages.

    Phase 11.1: never claim planning/tool/memory stages that did not execute.
    Real stages are emitted after Brain completes via ``_emit_honest_post_stages``.
    """
    del emit, intent, label


def handle_chat_stream(
    message: str,
    *,
    user: str | None = None,
    conversation_id: str | None = None,
    request_id: str | None = None,
    client_metadata: dict[str, str] | None = None,
    emit: EmitCallback | None = None,
) -> str:
    """Run Brain.process_request() while emitting live sanitized SSE events."""
    publisher = emit or _default_emit
    titan = get_titan()

    publisher("conversation_started", {
        "message": message,
        "user": user,
        "conversation_id": conversation_id,
    })
    _emit_presence(publisher, "thinking")
    publisher("brain_state", {"state": "thinking"})

    seen_labels: set[str] = set()
    seen_audit_index = _audit_start_index(titan)
    audit_lock = threading.Lock()
    stop_audit_poll = threading.Event()

    def cognitive_callback(event_type: str, data: dict[str, Any]) -> None:
        label = data.get("label", event_type)
        # Progressive token deltas must never be deduplicated.
        if event_type in {"text_delta", "token", "response_started", "acknowledged"}:
            publisher(event_type, data)
            if event_type == "response_started":
                _emit_legacy_alias(publisher, event_type, data)
                neural = data.get("neural_state")
                if neural:
                    publisher("brain_state", {"state": neural})
            return
        if label in seen_labels and event_type not in {
            "tool_execution",
            "memory_hit",
            "memory_miss",
        }:
            return
        seen_labels.add(label)
        publisher(event_type, data)
        _emit_legacy_alias(publisher, event_type, data)
        neural = data.get("neural_state")
        if neural:
            publisher("brain_state", {"state": neural})

        if event_type in {"memory_lookup", "memory_hit", "memory_miss", "obsidian_lookup"}:
            source = data.get("source", "long_term")
            publisher("memory_activity", {
                "run_id": f"live-{event_type}-{source}",
                "source": source,
                "phase": "search" if "lookup" in event_type else "recall",
                "title": data.get("label", event_type),
                "status_line": data.get("label", ""),
                "has_matches": data.get("has_matches", event_type == "memory_hit"),
                "match_count": data.get("match_count", 0),
                "state": "running",
            })

        if event_type == "tool_execution" and data.get("tool"):
            publisher("tool_activity", {
                "run_id": f"live-tool-{data['tool']}",
                "tool": data["tool"],
                "title": data.get("label", data["tool"]),
                "status_line": data.get("label", "Exécution…"),
                "state": "running",
            })

    stream = CognitiveStreamEmitter(cognitive_callback)
    stream.start_thinking(message=message, user=user or titan.context.current_user)

    orchestrator = titan.brain.execution_coordinator.cognitive_orchestrator
    previous_callback = orchestrator.on_progress

    def on_progress(event: ProgressEvent) -> None:
        if event.label in seen_labels:
            return
        seen_labels.add(event.label)
        e9_type, payload = _map_progress_to_e9(event)
        stream.emit(e9_type, payload)

    orchestrator.on_progress = on_progress

    def poll_audit() -> None:
        nonlocal seen_audit_index
        while not stop_audit_poll.is_set():
            with audit_lock:
                events = collect_audit_events_since(titan, seen_audit_index)
                if events:
                    seen_audit_index += len(events)
            for audit_event in events:
                records = format_tool_activity([audit_event], None)
                for record in records:
                    tool_name = record.get("tool", "default")
                    payload = {
                        "label": record.get("status_line", "Exécution…"),
                        "tool": tool_name,
                        "neural_state": "tool_usage",
                        "phase": "research",
                        **record,
                    }
                    publisher("tool_execution", payload)
                    publisher("tool_activity", record)
                    stream.emit("tool_execution", payload)
            time.sleep(0.05)

    audit_thread = threading.Thread(target=poll_audit, daemon=True)
    audit_thread.start()

    nlo = titan.brain.natural_language_orchestrator
    preview_analysis = nlo._analyze_request(message.strip())
    preview_intent, _, _ = nlo._detect_intent(preview_analysis)
    is_conversation = preview_intent in {
        DetectedIntent.CONVERSATION,
        DetectedIntent.QUESTION,
    }

    publisher("orchestration_started", {
        "label": f"Intent: {preview_intent.value}",
        "intent": preview_intent.value,
        "neural_state": "thinking",
        "phase": "understanding",
    })
    _emit_legacy_alias(publisher, "orchestration_started", {
        "label": f"Intent: {preview_intent.value}",
        "neural_state": "thinking",
        "phase": "understanding",
    })

    if not is_conversation:
        # Phase 11.1: do not emit synthetic planning/tool stages before Brain runs.
        publisher("conversation_stage", {
            "phase": "understanding",
            "label": f"Routage: {preview_intent.value}",
            "neural_state": "thinking",
            "stage": "understanding",
        })

    try:
        payload = process_chat_message(
            message,
            user=user,
            conversation_id=conversation_id,
            request_id=request_id,
            client_metadata=client_metadata,
            stream=stream if is_conversation else None,
        )
        response = payload["response"]
        speaker = payload.get("user", titan.context.current_user)
    except Exception:
        logger.exception("Brain failure during streaming chat")
        response = "Désolé, une erreur interne s'est produite. On peut réessayer."
        speaker = titan.context.current_user
        payload = {
            "response": response,
            "user": speaker,
            "detected_intent": preview_intent.value,
            "confidence": 0.0,
            "systems_used": {},
            "pipeline_summary": {},
            "reasoning_summary": "Erreur interne.",
            "brain_state": "error",
            "execution_status": "error",
            "approval_required": False,
            "approval_id": None,
            "approval_summary": None,
            "warnings": [],
            "errors": ["brain_failure"],
            "tool_activity": [],
            "memory_activity": [],
            "orchestrator_progress": [],
            "duration_seconds": 0.0,
            "conversation_id": conversation_id,
            "request_id": request_id,
        }
        publisher("error", {
            "code": "brain_failure",
            "message": response,
        })
    finally:
        stop_audit_poll.set()
        audit_thread.join(timeout=0.5)
        orchestrator.on_progress = previous_callback

    think_ctx = titan.brain.last_think_context
    tool_activity = payload.get("tool_activity") or format_tool_activity(
        collect_audit_events_since(titan, _audit_start_index(titan)),
        think_ctx,
    )
    memory_activity = payload.get("memory_activity") or format_memory_activity(think_ctx)
    orchestrator_progress = payload.get("orchestrator_progress") or format_orchestrator_progress(
        think_ctx,
    )
    pipeline_snapshot = stream.snapshot()

    if is_conversation:
        stream.finish_thinking()
        for record in memory_activity:
            publisher("memory_activity", record)
        for record in tool_activity:
            publisher("tool_activity", record)
    else:
        # Honest post-Brain stages only (no pre-claimed tool/planning animation).
        _emit_honest_post_stages(
            publisher,
            tool_activity=tool_activity,
            memory_activity=memory_activity,
            orchestrator_progress=orchestrator_progress,
        )
        publisher("response_ready", {
            "label": "Réponse prête",
            "neural_state": payload.get("brain_state", "completed"),
            "phase": "writing",
        })
        publisher("thinking_finished", {
            "label": "Orchestration terminée",
            "neural_state": "idle",
            "phase": "verification",
        })

    brain_state = payload.get("brain_state", "idle")
    if payload.get("approval_required"):
        brain_state = "awaiting_approval"
        publisher("brain_state", {"state": brain_state})
        publisher("approval_required", {
            "approval_id": payload.get("approval_id"),
            "summary": payload.get("approval_summary"),
            "intent": payload.get("detected_intent"),
        })

    _emit_brain_state(publisher, think_ctx)

    orchestration_meta = {
        "detected_intent": payload.get("detected_intent"),
        "confidence": payload.get("confidence"),
        "systems_used": payload.get("systems_used"),
        "reasoning_summary": payload.get("reasoning_summary"),
        "duration_seconds": payload.get("duration_seconds"),
        "execution_status": payload.get("execution_status"),
        "approval_required": payload.get("approval_required"),
    }

    publisher("orchestration_finished", orchestration_meta)
    _emit_legacy_alias(publisher, "orchestration_finished", {
        "label": "Orchestration terminée",
        "neural_state": brain_state,
        "phase": "verification",
    })

    publisher("conversation_finished", {
        "response": response,
        "user": speaker,
        "conversation_id": payload.get("conversation_id"),
        "request_id": payload.get("request_id"),
        "message_id": payload.get("message_id"),
        "assistant_message_id": payload.get("assistant_message_id"),
        "user_message_id": payload.get("user_message_id"),
        "ok": payload.get("ok", True),
        "orchestrator_progress": orchestrator_progress,
        "tool_activity": tool_activity,
        "memory_activity": memory_activity,
        "pipeline": pipeline_snapshot,
        "stage_history": pipeline_snapshot.get("stage_history", []),
        "timeline": pipeline_snapshot.get("timeline", []),
        "orchestration": orchestration_meta,
        "runtime": payload.get("runtime"),
        "approval_required": payload.get("approval_required", False),
        "approval_id": payload.get("approval_id"),
        "approval_summary": payload.get("approval_summary"),
        "brain_state": brain_state,
        "detected_intent": payload.get("detected_intent"),
        "duration_seconds": payload.get("duration_seconds"),
        "retryable": payload.get("retryable", False),
        "error_code": payload.get("error_code"),
        "ttft_ms": payload.get("ttft_ms"),
        "delta_count": payload.get("delta_count"),
    })
    if payload.get("error_code"):
        publisher("structured_error", {
            "code": payload.get("error_code"),
            "message": response,
            "request_id": payload.get("request_id"),
            "conversation_id": payload.get("conversation_id"),
            "retryable": payload.get("retryable", False),
        })
    elif payload.get("ok", True):
        publisher("response_completed", {
            "request_id": payload.get("request_id"),
            "conversation_id": payload.get("conversation_id"),
            "message_id": payload.get("message_id"),
            "chars": len(response or ""),
        })
    if payload.get("error_code") == "cancelled":
        publisher("cancelled", {
            "request_id": payload.get("request_id"),
            "conversation_id": payload.get("conversation_id"),
        })
    _emit_presence(publisher, "idle")
    publisher("brain_state", {"state": "idle"})
    publisher("telemetry", _build_telemetry(titan))

    return response
