# =====================================
# Titan Web API Auth
# =====================================

"""Bearer-token authentication for the private Titan web API (Phase 17.1)."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.settings import get_web_secret_key, is_web_dev_mode

_bearer_scheme = HTTPBearer(auto_error=False)


def validate_web_token(token: str | None) -> None:
    """Validate bearer or query token against ``TITAN_WEB_SECRET_KEY``."""
    if is_web_dev_mode():
        return

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
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """Reject requests when the secret key is missing or the bearer token is invalid."""
    if is_web_dev_mode():
        return

    token = credentials.credentials if credentials else None
    validate_web_token(token)
