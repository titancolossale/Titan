# =====================================
# Titan Private Auth Configuration
# =====================================

"""Environment-backed settings for Phase 10.3 private authentication."""

from __future__ import annotations

import os
from dataclasses import dataclass

from api.session_manager import SessionConfig


@dataclass(frozen=True)
class AuthUser:
    """Authorized Titan user (password hash only — never plaintext)."""

    username: str
    password_hash: str


@dataclass(frozen=True)
class PrivateAuthSettings:
    """Resolved private-auth policy from environment variables."""

    auth_required: bool
    users: tuple[AuthUser, ...]
    cookie_secure: bool
    idle_minutes: int
    max_hours: int
    public_base_url: str
    allowed_hosts: tuple[str, ...]

    @property
    def session_auth_enabled(self) -> bool:
        """True when private username/password session auth is active."""
        return self.auth_required and bool(self.users)


def _parse_csv(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _read_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() == "true"


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def load_auth_users() -> tuple[AuthUser, ...]:
    """Load authorized users from environment.

    Primary user (Nolan)::
        TITAN_AUTH_USERNAME + TITAN_AUTH_PASSWORD_HASH

    Optional second user (Ibrahim) without rewrite::
        TITAN_AUTH_USERNAME_2 + TITAN_AUTH_PASSWORD_HASH_2
    """
    users: list[AuthUser] = []

    primary_user = os.getenv("TITAN_AUTH_USERNAME", "").strip()
    primary_hash = os.getenv("TITAN_AUTH_PASSWORD_HASH", "").strip()
    if primary_user and primary_hash:
        users.append(AuthUser(username=primary_user, password_hash=primary_hash))

    second_user = os.getenv("TITAN_AUTH_USERNAME_2", "").strip()
    second_hash = os.getenv("TITAN_AUTH_PASSWORD_HASH_2", "").strip()
    if second_user and second_hash:
        users.append(AuthUser(username=second_user, password_hash=second_hash))

    return tuple(users)


def load_private_auth_settings() -> PrivateAuthSettings:
    """Load private auth settings from the current environment."""
    auth_required_env = os.getenv("TITAN_AUTH_REQUIRED", os.getenv("AUTH_REQUIRED", "")).strip()
    if auth_required_env:
        auth_required = auth_required_env.lower() == "true"
    else:
        # Default: require auth when password users are configured.
        auth_required = bool(load_auth_users())

    app_env = os.getenv("TITAN_APP_ENV", os.getenv("APP_ENV", "development")).strip().lower()
    cookie_default = "true" if app_env == "production" else "false"
    cookie_secure = _read_bool(
        "TITAN_COOKIE_SECURE",
        os.getenv("COOKIE_SECURE", cookie_default),
    )

    return PrivateAuthSettings(
        auth_required=auth_required,
        users=load_auth_users(),
        cookie_secure=cookie_secure,
        idle_minutes=_read_int("TITAN_SESSION_IDLE_MINUTES", 60),
        max_hours=_read_int("TITAN_SESSION_MAX_HOURS", 24),
        public_base_url=os.getenv(
            "TITAN_PUBLIC_BASE_URL",
            os.getenv("PUBLIC_BASE_URL", ""),
        ).strip(),
        allowed_hosts=_parse_csv(
            os.getenv("TITAN_ALLOWED_HOSTS", os.getenv("ALLOWED_HOSTS", ""))
        ),
    )


def load_session_config() -> SessionConfig:
    """Build session lifetime config from environment."""
    settings = load_private_auth_settings()
    return SessionConfig(
        idle_minutes=settings.idle_minutes,
        max_hours=settings.max_hours,
        cookie_secure=settings.cookie_secure,
        cookie_samesite="lax",
    )


def find_auth_user(username: str) -> AuthUser | None:
    """Look up an authorized user by username (case-sensitive)."""
    if not username:
        return None
    for user in load_auth_users():
        if user.username == username:
            return user
    return None


def is_session_auth_enabled() -> bool:
    """True when production private session authentication is configured."""
    from config.settings import is_web_dev_mode

    if is_web_dev_mode():
        return False
    return load_private_auth_settings().session_auth_enabled
