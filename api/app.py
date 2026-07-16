# =====================================
# Titan Web API Application
# =====================================

"""FastAPI application for Titan's private local web interface (Phase 17.1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import asyncio

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from api.auth import require_web_auth, validate_web_token
from api.auth_config import is_session_auth_enabled
from api.auth_middleware import PrivateAuthMiddleware
from api.auth_routes import router as auth_router
from api.chat_models import ChatErrorResponse, ChatMessageRequest, ChatMessageResponse
from api.chat_service import (
    BRAIN_FAILURE_CODE,
    PROVIDER_UNAVAILABLE_CODE,
    PROVIDER_UNAVAILABLE_MESSAGE,
    process_chat_message,
    validate_message_size,
)
from api.event_hub import event_hub
from api.sse import format_sse_event, format_stream_event, sse_comment
from api.stream_service import emit_initial_status, handle_chat_stream
from api.readiness import build_readiness_payload
from api.status_builders import (
    build_browser_status,
    build_calendar_status,
    build_email_status,
    build_memory_status,
    build_obsidian_status,
    build_system_status,
    build_tools_status,
    build_trading_status,
)
from api.titan_service import get_titan, handle_chat
from config.settings import (
    TITAN_ALLOWED_HOSTS,
    TITAN_CORS_ALLOWED_ORIGINS,
    TITAN_NAME,
    VERSION,
    env_bool,
    get_web_secret_key,
    is_web_dev_mode,
)
from voice.voice_manager import VoiceManager

# Canonical production frontend: web/v2/ (approved final Titan Web App).
# Legacy V1 UI remains under web/static/ for compatibility only — never the default.
WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
STATIC_DIR = WEB_ROOT / "static"
V2_DIR = WEB_ROOT / "v2"
CANONICAL_APP_PATH = "/app/"


class ChatRequest(BaseModel):
    """Incoming chat message for Titan Brain (legacy + stream endpoints)."""

    message: str = Field(..., min_length=1)
    user: str | None = None
    conversation_id: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)
    client_request_id: str | None = Field(default=None, max_length=128)
    client_metadata: dict[str, str] | None = None

    def resolved_request_id(self) -> str | None:
        """Prefer request_id; accept client_request_id as Phase 11.1 alias."""
        if self.request_id and self.request_id.strip():
            return self.request_id.strip()[:128]
        if self.client_request_id and self.client_request_id.strip():
            return self.client_request_id.strip()[:128]
        return None


class ChatResponse(BaseModel):
    """Titan response from Brain.process_request() with activity metadata."""

    response: str
    user: str
    tool_activity: list[dict[str, Any]] = Field(default_factory=list)
    memory_activity: list[dict[str, Any]] = Field(default_factory=list)
    orchestrator_progress: list[dict[str, Any]] = Field(default_factory=list)
    conversation_id: str | None = None
    request_id: str | None = None
    detected_intent: str | None = None
    confidence: float | None = None
    brain_state: str | None = None
    approval_required: bool = False


def _parse_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def create_app() -> FastAPI:
    """Build the FastAPI application with routes and static frontend."""
    app = FastAPI(
        title=f"{TITAN_NAME} Private Web API",
        version=VERSION,
        docs_url="/docs" if (env_bool("TITAN_WEB_ENABLED") or is_web_dev_mode()) else None,
        redoc_url=None,
    )

    # Outermost: honor X-Forwarded-Proto/For from Railway's reverse proxy.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

    cors_origins = _parse_csv(TITAN_CORS_ALLOWED_ORIGINS)
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "Last-Event-ID",
                "X-CSRF-Token",
            ],
        )

    allowed_hosts = _parse_csv(TITAN_ALLOWED_HOSTS)
    if allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    # Private session gate (no-op when session auth is not configured).
    app.add_middleware(PrivateAuthMiddleware)

    app.include_router(auth_router)

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    if V2_DIR.is_dir():
        # Canonical Titan Web App (approved final UI). /app is the production entry;
        # /v2 is a same-source alias. Do not remount web/static as the default app.
        app.mount("/v2", StaticFiles(directory=str(V2_DIR), html=True), name="v2")
        app.mount("/app", StaticFiles(directory=str(V2_DIR), html=True), name="app")

    @app.get("/health")
    def health() -> dict[str, Any]:
        """Public liveness probe — no authentication required."""
        dev_mode = is_web_dev_mode()
        secret_configured = bool(get_web_secret_key())
        session_auth = is_session_auth_enabled()
        return {
            "status": "ok",
            "name": TITAN_NAME,
            "version": VERSION,
            "web_enabled": env_bool("TITAN_WEB_ENABLED"),
            "dev_mode": dev_mode,
            "auth_required": (not dev_mode) and (session_auth or secret_configured),
            "session_auth": session_auth,
        }

    @app.get("/ready")
    def ready() -> JSONResponse:
        """Readiness probe — core subsystems required; optional tools may be unavailable."""
        payload = build_readiness_payload()
        http_status = int(payload.pop("http_status", 200))
        return JSONResponse(status_code=http_status, content=payload)

    @app.post("/auth/verify", dependencies=[Depends(require_web_auth)])
    def auth_verify() -> dict[str, bool]:
        """Validate the active session or bearer token without exposing secrets."""
        return {"ok": True}

    @app.get("/")
    def index() -> RedirectResponse:
        """Redirect to the canonical Titan Web App at /app/.

        Unauthenticated browsers are redirected to /login by PrivateAuthMiddleware
        before this handler runs. Authenticated (and web-dev) traffic lands on
        web/v2 — never the legacy web/static Interface V1.
        """
        return RedirectResponse(url=CANONICAL_APP_PATH, status_code=303)

    @app.get("/design")
    def design_preview() -> FileResponse:
        """Serve the Titan Design Language preview (legacy — not the default app)."""
        design_path = STATIC_DIR / "design.html"
        return FileResponse(design_path)

    def _chat_contract_error(
        *,
        code: str,
        message: str,
        retryable: bool,
        request_id: str | None = None,
        conversation_id: str | None = None,
        message_id: str | None = None,
        http_status: int = 400,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=http_status,
            content=ChatErrorResponse.from_parts(
                code=code,
                message=message,
                retryable=retryable,
                request_id=request_id,
                conversation_id=conversation_id,
                message_id=message_id,
            ).model_dump(),
        )

    @app.post(
        "/api/chat",
        dependencies=[Depends(require_web_auth)],
        response_model=None,
    )
    def chat_contract(body: ChatMessageRequest) -> dict[str, Any] | JSONResponse:
        """Phase 11.1 production chat contract — Brain.process_request()."""
        try:
            payload = process_chat_message(
                body.message,
                user=body.user,
                conversation_id=body.conversation_id,
                request_id=body.request_id,
                client_metadata=body.client_metadata,
            )
        except ValueError as exc:
            return _chat_contract_error(
                code="invalid_request",
                message=str(exc),
                retryable=False,
                request_id=body.request_id,
                conversation_id=body.conversation_id,
                http_status=400,
            )
        except Exception:
            return _chat_contract_error(
                code="internal_error",
                message="Erreur interne pendant le traitement du message.",
                retryable=True,
                request_id=body.request_id,
                conversation_id=body.conversation_id,
                http_status=500,
            )

        if payload.get("error_code") == PROVIDER_UNAVAILABLE_CODE or (
            not payload.get("ok", True)
            and PROVIDER_UNAVAILABLE_CODE in (payload.get("errors") or [])
        ):
            return _chat_contract_error(
                code=PROVIDER_UNAVAILABLE_CODE,
                message=PROVIDER_UNAVAILABLE_MESSAGE,
                retryable=True,
                request_id=payload.get("request_id"),
                conversation_id=payload.get("conversation_id"),
                message_id=payload.get("message_id"),
                http_status=503,
            )

        if BRAIN_FAILURE_CODE in (payload.get("errors") or []):
            return _chat_contract_error(
                code=BRAIN_FAILURE_CODE,
                message=payload.get("response")
                or "Désolé, une erreur interne s'est produite. On peut réessayer.",
                retryable=True,
                request_id=payload.get("request_id"),
                conversation_id=payload.get("conversation_id"),
                message_id=payload.get("message_id"),
                http_status=500,
            )

        return payload

    @app.post(
        "/api/chat/message",
        dependencies=[Depends(require_web_auth)],
        response_model=ChatMessageResponse,
    )
    def chat_message(body: ChatMessageRequest) -> ChatMessageResponse | JSONResponse:
        """Authenticated chat endpoint — Brain.process_request() (Web Runtime V1)."""
        try:
            payload = process_chat_message(
                body.message,
                user=body.user,
                conversation_id=body.conversation_id,
                request_id=body.request_id,
                client_metadata=body.client_metadata,
            )
            model_fields = set(ChatMessageResponse.model_fields)
            trimmed = {k: v for k, v in payload.items() if k in model_fields}
            return ChatMessageResponse(**trimmed)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content=ChatErrorResponse.from_parts(
                    code="invalid_request",
                    message=str(exc),
                    retryable=False,
                    request_id=body.request_id,
                    conversation_id=body.conversation_id,
                ).model_dump(),
            )
        except Exception:
            return JSONResponse(
                status_code=500,
                content=ChatErrorResponse.from_parts(
                    code="internal_error",
                    message="Erreur interne pendant le traitement du message.",
                    retryable=True,
                    request_id=body.request_id,
                    conversation_id=body.conversation_id,
                ).model_dump(),
            )

    @app.post("/chat", dependencies=[Depends(require_web_auth)])
    def chat(body: ChatRequest) -> ChatResponse:
        """Legacy sync chat — delegates to Brain.process_request()."""
        try:
            validate_message_size(body.message)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        response, tool_activity, memory_activity, orchestrator_progress, payload = handle_chat(
            body.message,
            user=body.user,
            conversation_id=body.conversation_id,
            request_id=body.resolved_request_id(),
            client_metadata=body.client_metadata,
        )
        return ChatResponse(
            response=response,
            user=payload.get("user", get_titan().context.current_user),
            tool_activity=tool_activity,
            memory_activity=memory_activity,
            orchestrator_progress=orchestrator_progress,
            conversation_id=payload.get("conversation_id"),
            request_id=payload.get("request_id"),
            detected_intent=payload.get("detected_intent"),
            confidence=payload.get("confidence"),
            brain_state=payload.get("brain_state"),
            approval_required=payload.get("approval_required", False),
        )

    @app.get("/events/stream")
    def events_stream(
        request: Request,
        token: str | None = Query(default=None),
        snapshot: bool = Query(default=False),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        """Persistent SSE stream — status, brain_state, telemetry, and hub events."""
        # Session cookies are preferred (EventSource cannot set Authorization).
        # Legacy ?token= remains only when session auth is disabled.
        validate_web_token(token, request=request)

        def generate():
            for event_type, data in emit_initial_status():
                yield format_sse_event(event_type, data)
            if snapshot:
                return
            for event in event_hub.subscribe(last_event_id=last_event_id):
                yield format_stream_event(event)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/chat/stream", dependencies=[Depends(require_web_auth)])
    async def chat_stream(body: ChatRequest) -> StreamingResponse:
        """Stream sanitized cognitive events during Brain.process_request() via SSE."""
        if not (body.message or "").strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty.")
        try:
            validate_message_size(body.message)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        queue: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def emit(event_type: str, data: dict) -> None:
            frame = format_sse_event(event_type, data)
            loop.call_soon_threadsafe(queue.put_nowait, frame)

        def run_chat() -> None:
            try:
                handle_chat_stream(
                    body.message,
                    user=body.user,
                    conversation_id=body.conversation_id,
                    request_id=body.resolved_request_id(),
                    client_metadata=body.client_metadata,
                    emit=emit,
                )
            except Exception:
                error_frame = format_sse_event(
                    "error",
                    {"code": "stream_failure", "message": "Erreur interne du flux."},
                )
                loop.call_soon_threadsafe(queue.put_nowait, error_frame)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        async def generate():
            task = asyncio.create_task(asyncio.to_thread(run_chat))
            try:
                while True:
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        yield sse_comment("keepalive")
                        continue
                    if item is None:
                        break
                    yield item
            finally:
                if not task.done():
                    task.cancel()

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/status", dependencies=[Depends(require_web_auth)])
    def status() -> dict[str, Any]:
        """Return Titan system status."""
        return build_system_status(get_titan())

    @app.get("/tools", dependencies=[Depends(require_web_auth)])
    def tools() -> dict[str, Any]:
        """Return registered tools and provider health dashboard."""
        return build_tools_status(get_titan())

    @app.get("/memory/status", dependencies=[Depends(require_web_auth)])
    def memory_status() -> dict[str, Any]:
        """Return memory subsystem status."""
        return build_memory_status(get_titan())

    @app.get("/obsidian/status", dependencies=[Depends(require_web_auth)])
    def obsidian_status() -> dict[str, Any]:
        """Return Obsidian connector status."""
        return build_obsidian_status()

    @app.get("/browser/status", dependencies=[Depends(require_web_auth)])
    def browser_status() -> dict[str, Any]:
        """Return Browser connector status."""
        return build_browser_status()

    @app.get("/calendar/status", dependencies=[Depends(require_web_auth)])
    def calendar_status() -> dict[str, Any]:
        """Return Calendar connector status."""
        return build_calendar_status()

    @app.get("/email/status", dependencies=[Depends(require_web_auth)])
    def email_status() -> dict[str, Any]:
        """Return Email connector status."""
        return build_email_status()

    @app.get("/trading/status", dependencies=[Depends(require_web_auth)])
    def trading_status() -> dict[str, Any]:
        """Return Trading connector status."""
        return build_trading_status()

    voice_manager = VoiceManager()

    @app.get("/voice/status", dependencies=[Depends(require_web_auth)])
    def voice_status() -> dict[str, Any]:
        """Return voice interface capabilities and configuration (Phase 17.8)."""
        return voice_manager.get_config()

    return app


app = create_app()
