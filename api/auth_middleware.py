# =====================================
# Titan Auth Middleware
# =====================================

"""Request gate for Phase 10.3 private session authentication."""

from __future__ import annotations

from urllib.parse import quote, urlparse

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from api.auth_config import is_session_auth_enabled, load_private_auth_settings
from api.session_manager import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    get_session_manager,
)

logger = logging.getLogger(__name__)

# Exact public paths (no authentication).
_PUBLIC_EXACT = frozenset(
    {
        "/health",
        "/ready",
        "/login",
        "/auth/status",
        "/auth/login",
        "/auth/logout",
        "/favicon.ico",
    }
)

# Public path prefixes (login static assets only).
_PUBLIC_PREFIXES = (
    "/login/",
)


def is_public_path(path: str) -> bool:
    """Return True when ``path`` may be accessed without authentication."""
    if path in _PUBLIC_EXACT:
        return True
    normalized = path if path.endswith("/") or "." in path.rsplit("/", 1)[-1] else path
    if normalized.rstrip("/") == "/login":
        return True
    return any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)


def safe_redirect_target(raw: str | None, *, default: str = "/app/") -> str:
    """Prevent open redirects — allow only same-origin relative paths."""
    if not raw:
        return default
    candidate = raw.strip()
    if not candidate.startswith("/"):
        return default
    if candidate.startswith("//"):
        return default
    if "\\" in candidate:
        return default
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc:
        return default
    if not parsed.path.startswith("/"):
        return default
    return candidate


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return True
    path = request.url.path
    if path == "/" or path.startswith(("/app", "/v2", "/static", "/design", "/docs")):
        if "application/json" not in accept:
            return True
    return False


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _origin_allowed(request: Request) -> bool:
    """Validate Origin/Referer for state-changing authenticated requests."""
    settings = load_private_auth_settings()
    origin = request.headers.get("origin", "").strip()
    referer = request.headers.get("referer", "").strip()

    allowed_origins: set[str] = set()
    if settings.public_base_url:
        allowed_origins.add(settings.public_base_url.rstrip("/"))

    host = request.headers.get("host", "").strip()
    if host:
        # Prefer forwarded proto when behind Railway's reverse proxy.
        proto = (
            request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
            or request.url.scheme
            or "https"
        )
        allowed_origins.add(f"{proto}://{host}")

    for allowed_host in settings.allowed_hosts:
        allowed_origins.add(f"https://{allowed_host}")
        allowed_origins.add(f"http://{allowed_host}")

    def _matches(value: str) -> bool:
        if not value:
            return False
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            return False
        base = f"{parsed.scheme}://{parsed.netloc}"
        return base in allowed_origins

    # Same-origin navigations may omit Origin; require at least one signal when present.
    if origin:
        return _matches(origin)
    if referer:
        return _matches(referer)
    # No Origin/Referer — allow same-site cookie requests (EventSource, some browsers).
    return True


class PrivateAuthMiddleware(BaseHTTPMiddleware):
    """Enforce session authentication when private auth is enabled."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # TEMP production path trace — remove after Railway confirmation.
        if request.method == "POST" and (
            path.startswith("/chat") or path.startswith("/api/chat")
        ):
            logger.info(
                "REQUEST_RECEIVED ROUTE_NAME=PrivateAuthMiddleware REQUEST_ID=- "
                "method=%s path=%s",
                request.method,
                path,
            )

        if not is_session_auth_enabled():
            return await call_next(request)

        # CORS preflight must remain reachable.
        if request.method == "OPTIONS":
            return await call_next(request)

        if is_public_path(path):
            return await call_next(request)

        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        session = get_session_manager().get_session(session_id)
        if session is None:
            if request.method == "POST" and (
                path.startswith("/chat") or path.startswith("/api/chat")
            ):
                logger.info(
                    "ROUTE_EXIT ROUTE_NAME=PrivateAuthMiddleware REQUEST_ID=- "
                    "status=unauthenticated path=%s",
                    path,
                )
            return self._reject_unauthenticated(request)

        request.state.titan_session = session
        request.state.titan_username = session.username

        # CSRF protection for cookie-authenticated state changes.
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if not _origin_allowed(request):
                if path.startswith("/chat") or path.startswith("/api/chat"):
                    logger.info(
                        "ROUTE_EXIT ROUTE_NAME=PrivateAuthMiddleware REQUEST_ID=- "
                        "status=origin_forbidden path=%s",
                        path,
                    )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Forbidden"},
                )
            csrf_header = request.headers.get(CSRF_HEADER_NAME)
            csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
            token = csrf_header or csrf_cookie
            if not get_session_manager().validate_csrf(session, token):
                if path.startswith("/chat") or path.startswith("/api/chat"):
                    logger.info(
                        "ROUTE_EXIT ROUTE_NAME=PrivateAuthMiddleware REQUEST_ID=- "
                        "status=csrf_invalid path=%s",
                        path,
                    )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token invalide."},
                )

        return await call_next(request)

    def _reject_unauthenticated(self, request: Request) -> Response:
        if _wants_html(request):
            next_target = safe_redirect_target(
                request.url.path
                + (("?" + request.url.query) if request.url.query else ""),
                default="/app/",
            )
            return RedirectResponse(
                url=f"/login?next={quote(next_target, safe='/')}",
                status_code=303,
            )
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized"},
            headers={"WWW-Authenticate": "Session"},
        )


def get_request_client_key(request: Request) -> str:
    """Expose client key helper for login rate limiting."""
    return _client_key(request)
