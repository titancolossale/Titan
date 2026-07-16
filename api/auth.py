# =====================================
# Titan Web API Auth
# =====================================

"""Authentication for the private Titan web API.

Phase 10.3 adds username/password session authentication for production.
Legacy Bearer-token auth remains available when session auth is not configured
(local development / existing integrations).
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.auth_config import find_auth_user, is_session_auth_enabled
from api.password_security import verify_password
from api.session_manager import SESSION_COOKIE_NAME, get_session_manager
from config.settings import get_web_secret_key, is_web_dev_mode

_bearer_scheme = HTTPBearer(auto_error=False)

INVALID_CREDENTIALS_MESSAGE = "Identifiants invalides."

# Fixed dummy Argon2id hash for unknown-username timing parity (not a real credential).
_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=2$SIHfq4HGVGiM2ia/g4teug$"
    "gYFsi7DyWo+2pZmMWS10YbOZPccH/X0WI4CKZ47umes"
)

def authenticate_user(username: str, password: str) -> str | None:
    """Verify credentials. Returns username on success, else None.

    Always uses a generic failure path — never discloses which field failed.
    """
    user = find_auth_user(username)
    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user.username


def get_session_from_request(request: Request):
    """Return the authenticated session for ``request``, if any."""
    session = getattr(request.state, "titan_session", None)
    if session is not None:
        return session
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    return get_session_manager().get_session(session_id)


def validate_web_token(token: str | None, request: Request | None = None) -> None:
    """Validate bearer/query token or an active session cookie."""
    if is_web_dev_mode():
        return

    if is_session_auth_enabled():
        if request is not None:
            session = get_session_from_request(request)
            if session is not None:
                return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Session"},
        )

    secret_key = get_web_secret_key()
    if not secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Web API authentication is not configured (TITAN_WEB_SECRET_KEY).",
        )
    if not token or token != secret_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_web_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """Reject requests when authentication is missing or invalid."""
    if is_web_dev_mode():
        return

    if is_session_auth_enabled():
        session = get_session_from_request(request)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized",
                headers={"WWW-Authenticate": "Session"},
            )
        request.state.titan_session = session
        request.state.titan_username = session.username
        return

    token = credentials.credentials if credentials else None
    validate_web_token(token, request=request)
