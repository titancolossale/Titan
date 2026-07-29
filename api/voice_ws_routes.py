# =====================================
# Titan Browser Voice WebSocket Routes
# =====================================

"""Authenticated native browser ↔ Titan voice WebSocket (Phase 20.8).

Endpoint: ``WS /voice/session/ws``

Persistent connection with heartbeat, backpressure, stream sync, and
graceful reconnect. HTTP chunk endpoints remain the fallback path —
no UI redesign required.
"""

from __future__ import annotations

import base64
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.auth import get_session_from_request, validate_web_token
from api.auth_config import is_session_auth_enabled
from config.settings import is_web_dev_mode
from context.session_manager import SessionManager
from voice.diagnostics import emit_voice_diagnostic
from voice.live_session import LiveVoiceSessionOrchestrator
from voice.transport.browser_hub import get_browser_voice_hub
from voice.transport.browser_protocol import BrowserFrame, BrowserFrameType

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice-websocket"])


def _resolve_ws_user(websocket: WebSocket) -> str | None:
    """Authenticate WebSocket — cookie session, bearer query, or dev mode."""
    if is_session_auth_enabled():
        # Starlette Request-compatible adapter for cookie session.
        class _Req:
            def __init__(self, ws: WebSocket) -> None:
                self.cookies = ws.cookies
                self.headers = ws.headers
                self.state = ws.state

        session = get_session_from_request(_Req(websocket))  # type: ignore[arg-type]
        if session is not None:
            return SessionManager.normalize_user(session.username)

    token = websocket.query_params.get("token") or websocket.query_params.get("access_token")
    if token:
        try:
            if validate_web_token(token):
                # Bearer path — identity still gated by speaker ID downstream.
                return "Nolan" if is_web_dev_mode() else "Nolan"
        except Exception:
            return None

    if is_web_dev_mode() and not is_session_auth_enabled():
        return "Nolan"
    return None


def _get_orchestrator() -> LiveVoiceSessionOrchestrator:
    from api.voice_session_routes import get_live_orchestrator

    return get_live_orchestrator()


@router.websocket("/voice/session/ws")
async def voice_session_websocket(websocket: WebSocket) -> None:
    """Native browser voice uplink with reconnect + heartbeat."""
    from config import settings as app_settings

    if not bool(getattr(app_settings, "TITAN_VOICE_WS_ENABLED", True)):
        await websocket.close(code=1008)
        return

    user = _resolve_ws_user(websocket)
    if user is None:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    hub = get_browser_voice_hub()
    connection_id = str(uuid4())
    conn = hub.register(connection_id, authenticated_user=user)
    hub.mark_connected(connection_id)
    orchestrator = _get_orchestrator()

    emit_voice_diagnostic(
        "VOICE_WS_CONNECTED",
        connection_id=connection_id,
        user=user,
    )

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            replies: list[BrowserFrame] = []
            binary_audio: bytes | None = None

            if "bytes" in message and message["bytes"] is not None:
                raw = bytes(message["bytes"])
                # Binary frames are uplink audio; optional 4-byte seq prefix unused.
                binary_audio = raw
                frame = BrowserFrame(
                    type=BrowserFrameType.AUDIO,
                    sequence=conn.sync.expected_client_seq,
                    session_id=conn.session_id,
                    payload={"bytes": len(raw)},
                    binary=raw,
                )
                replies = hub.handle_frame(connection_id, frame, binary_bytes=len(raw))
            elif "text" in message and message["text"] is not None:
                try:
                    frame = BrowserFrame.from_json(message["text"])
                except Exception:
                    await websocket.send_text(
                        BrowserFrame(
                            type=BrowserFrameType.ERROR,
                            payload={"error": "invalid_frame"},
                        ).to_json_bytes().decode("utf-8")
                    )
                    continue
                replies = hub.handle_frame(connection_id, frame)
                # Handle session start / audio JSON / finish via control payloads.
                await _dispatch_control(
                    websocket,
                    orchestrator,
                    hub,
                    connection_id,
                    frame,
                    user=user,
                )
                # Refresh conn reference after possible bind.
                refreshed = hub.get(connection_id)
                if refreshed is not None:
                    conn = refreshed
            else:
                continue

            # Feed binary audio into live session when bound.
            if binary_audio and conn.session_id:
                try:
                    dropped = any(r.type == BrowserFrameType.BACKPRESSURE and r.payload.get("drop") for r in replies)
                    if not dropped:
                        result = orchestrator.submit_audio_chunk(
                            conn.session_id,
                            audio_bytes=binary_audio,
                        )
                        if isinstance(result, dict) and result.get("tts_audio_chunks"):
                            for chunk_b64 in result["tts_audio_chunks"]:
                                try:
                                    audio_out = base64.b64decode(chunk_b64)
                                except Exception:
                                    continue
                                seq = hub.note_downlink(connection_id, len(audio_out))
                                await websocket.send_bytes(audio_out)
                                await websocket.send_text(
                                    BrowserFrame(
                                        type=BrowserFrameType.TTS_CHUNK,
                                        sequence=seq,
                                        session_id=conn.session_id,
                                        payload={"bytes": len(audio_out)},
                                    ).to_json_bytes().decode("utf-8")
                                )
                except Exception as exc:
                    logger.warning("WS audio ingest failed: %s", type(exc).__name__)

            for reply in replies:
                await websocket.send_text(reply.to_json_bytes().decode("utf-8"))

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("Voice WS closed with error: %s", type(exc).__name__)
        emit_voice_diagnostic(
            "VOICE_WS_ERROR",
            connection_id=connection_id,
            error=type(exc).__name__,
        )
    finally:
        hub.close(connection_id, reason="disconnect")


async def _dispatch_control(
    websocket: WebSocket,
    orchestrator: LiveVoiceSessionOrchestrator,
    hub: Any,
    connection_id: str,
    frame: BrowserFrame,
    *,
    user: str,
) -> None:
    """Map control frames onto existing live session orchestrator APIs."""
    payload = frame.payload or {}
    action = str(payload.get("action") or "").strip().lower()

    if frame.type == BrowserFrameType.HELLO and action in {"", "hello"}:
        return

    if action == "start_session" or payload.get("start_session"):
        result = orchestrator.start_session(
            authenticated_user=user,
            capture_mode=str(payload.get("capture_mode") or "push_to_talk"),
            microphone_enabled=bool(payload.get("microphone_enabled", True)),
            conversation_id=payload.get("conversation_id"),
        )
        session_id = str(result.get("session_id") or "")
        recovery = result.get("recovery_token")
        if session_id:
            hub.bind_session(
                connection_id,
                session_id=session_id,
                recovery_token=str(recovery) if recovery else None,
            )
        await websocket.send_text(
            BrowserFrame(
                type=BrowserFrameType.EVENT,
                sequence=hub.note_downlink(connection_id, 0),
                session_id=session_id or None,
                payload={"event": "session_started", "result": _safe_result(result)},
            ).to_json_bytes().decode("utf-8")
        )
        return

    if action == "finish_turn" and frame.session_id:
        result = orchestrator.finish_utterance(frame.session_id)
        await websocket.send_text(
            BrowserFrame(
                type=BrowserFrameType.EVENT,
                sequence=hub.note_downlink(connection_id, 0),
                session_id=frame.session_id,
                payload={"event": "turn_finished", "result": _safe_result(result)},
            ).to_json_bytes().decode("utf-8")
        )
        # Stream any TTS chunks as binary if present.
        for chunk_b64 in (result or {}).get("tts_audio_chunks") or []:
            try:
                audio_out = base64.b64decode(chunk_b64)
            except Exception:
                continue
            seq = hub.note_downlink(connection_id, len(audio_out))
            await websocket.send_bytes(audio_out)
            await websocket.send_text(
                BrowserFrame(
                    type=BrowserFrameType.TTS_CHUNK,
                    sequence=seq,
                    session_id=frame.session_id,
                    payload={"bytes": len(audio_out)},
                ).to_json_bytes().decode("utf-8")
            )
        return

    if action == "heartbeat" and frame.session_id:
        try:
            orchestrator.heartbeat(frame.session_id)
        except Exception:
            pass
        return

    if action == "interrupt" and frame.session_id:
        try:
            orchestrator.interrupt_playback(frame.session_id)
        except Exception:
            pass
        return


def _safe_result(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    forbidden = {"audio", "audio_bytes", "embedding", "embeddings", "api_key"}
    return {k: v for k, v in result.items() if k not in forbidden and not str(k).startswith("_")}
