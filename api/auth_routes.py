# =====================================
# Titan Auth Routes
# =====================================

"""Login, logout, and auth-status endpoints for private production auth."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from api.auth import INVALID_CREDENTIALS_MESSAGE, authenticate_user, get_session_from_request
from api.auth_config import is_session_auth_enabled, load_private_auth_settings
from api.auth_middleware import get_request_client_key, safe_redirect_target
from api.login_rate_limit import get_login_rate_limiter
from api.session_manager import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    get_session_manager,
)
from config.settings import get_web_secret_key, is_web_dev_mode

LOGIN_DIR = Path(__file__).resolve().parent.parent / "web" / "login"

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    """Credentials submitted by the login form (never logged)."""

    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)
    next: str | None = Field(default=None, max_length=512)


def _cookie_common() -> dict[str, Any]:
    settings = load_private_auth_settings()
    return {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "path": "/",
        "max_age": settings.max_hours * 3600,
    }


def _set_session_cookies(response: Response, session) -> None:
    common = _cookie_common()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.session_id,
        **common,
    )
    # CSRF cookie is readable by JS (double-submit / header mirror).
    csrf_kwargs = {**common, "httponly": False}
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=session.csrf_token,
        **csrf_kwargs,
    )


def _clear_session_cookies(response: Response) -> None:
    settings = load_private_auth_settings()
    for name in (SESSION_COOKIE_NAME, CSRF_COOKIE_NAME):
        response.delete_cookie(
            key=name,
            path="/",
            secure=settings.cookie_secure,
            httponly=(name == SESSION_COOKIE_NAME),
            samesite="lax",
        )


@router.get("/login")
def login_page(request: Request) -> Response:
    """Serve the Titan private login screen."""
    if is_session_auth_enabled():
        session = get_session_from_request(request)
        if session is not None:
            next_target = safe_redirect_target(
                request.query_params.get("next"),
                default="/app/",
            )
            return RedirectResponse(url=next_target, status_code=303)

    index_path = LOGIN_DIR / "index.html"
    if not index_path.is_file():
        return JSONResponse(
            status_code=503,
            content={"detail": "Login page unavailable."},
        )
    return FileResponse(index_path)


@router.get("/login/login.css")
def login_css() -> FileResponse:
    """Public login stylesheet."""
    return FileResponse(LOGIN_DIR / "login.css", media_type="text/css")


@router.get("/login/login.js")
def login_js() -> FileResponse:
    """Public login script (no secrets)."""
    return FileResponse(LOGIN_DIR / "login.js", media_type="application/javascript")


@router.get("/login/titan-logo.svg")
def login_logo() -> FileResponse:
    """Titan shield/logo for the login panel."""
    logo = Path(__file__).resolve().parent.parent / "web" / "v2" / "assets" / "titan-logo.svg"
    return FileResponse(logo, media_type="image/svg+xml")


@router.get("/auth/status")
def auth_status(request: Request) -> dict[str, Any]:
    """Public auth policy — never includes secrets or password hashes."""
    dev_mode = is_web_dev_mode()
    session_enabled = is_session_auth_enabled()
    secret_configured = bool(get_web_secret_key())
    session = get_session_from_request(request) if session_enabled else None

    if session_enabled:
        auth_mode = "session"
        auth_required = True
    elif not dev_mode and secret_configured:
        auth_mode = "bearer"
        auth_required = True
    else:
        auth_mode = "none"
        auth_required = False

    return {
        "auth_required": auth_required and not dev_mode,
        "auth_mode": auth_mode,
        "dev_mode": dev_mode,
        "secret_configured": secret_configured,
        "session_auth": session_enabled,
        "authenticated": session is not None,
        "username": session.username if session is not None else None,
    }


@router.post("/auth/login")
def auth_login(body: LoginRequest, request: Request) -> Response:
    """Authenticate with username/password and create a secure session."""
    if not is_session_auth_enabled():
        return JSONResponse(
            status_code=503,
            content={"detail": "Session authentication is not configured."},
        )

    client_key = get_request_client_key(request)
    limiter = get_login_rate_limiter()
    if limiter.is_locked(client_key):
        return JSONResponse(
            status_code=429,
            content={"detail": "Trop de tentatives. Réessaie plus tard."},
        )

    username = body.username.strip()
    # Never log password or hash.
    authenticated = authenticate_user(username, body.password)
    if authenticated is None:
        limiter.register_failure(client_key)
        return JSONResponse(
            status_code=401,
            content={"detail": INVALID_CREDENTIALS_MESSAGE},
        )

    limiter.register_success(client_key)
    session = get_session_manager().create_session(authenticated)
    next_target = safe_redirect_target(body.next, default="/app/")

    response = JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "username": authenticated,
            "next": next_target,
            "csrf_token": session.csrf_token,
        },
    )
    _set_session_cookies(response, session)
    return response


@router.post("/auth/logout")
def auth_logout(request: Request) -> Response:
    """Destroy the current session and clear auth cookies."""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    get_session_manager().revoke_session(session_id)
    response = JSONResponse(status_code=200, content={"ok": True})
    _clear_session_cookies(response)
    return response


@router.get("/auth/session")
def auth_session(request: Request) -> Response:
    """Return the current session summary (authenticated routes use middleware)."""
    if not is_session_auth_enabled():
        return JSONResponse(
            status_code=200,
            content={"authenticated": False, "auth_mode": "bearer"},
        )
    session = get_session_from_request(request)
    if session is None:
        return JSONResponse(
            status_code=401,
            content={"authenticated": False, "detail": "Unauthorized"},
        )
    return JSONResponse(
        status_code=200,
        content={
            "authenticated": True,
            "username": session.username,
            "csrf_token": session.csrf_token,
        },
    )
