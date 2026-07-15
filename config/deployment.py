# =====================================
# Titan Deployment Configuration
# =====================================

"""Typed, validated environment configuration for local and cloud deployment."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from config.paths import get_data_directory, get_memory_directory, is_directory_writable
from config.settings import reload_env

_MIN_PRODUCTION_SECRET_LENGTH = 16


class AppEnvironment(str, Enum):
    """Runtime deployment environment."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TEST = "test"


class DeploymentConfigError(ValueError):
    """Raised when deployment configuration is invalid or unsafe."""


def _parse_csv(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _read_app_env() -> AppEnvironment:
    raw = os.getenv("TITAN_APP_ENV", os.getenv("APP_ENV", "development")).strip().lower()
    try:
        return AppEnvironment(raw)
    except ValueError as exc:
        raise DeploymentConfigError(
            f"Invalid APP_ENV/TITAN_APP_ENV={raw!r}. "
            "Expected development, production, or test."
        ) from exc


def _read_port(default: int = 8000) -> int:
    for name in ("PORT", "TITAN_WEB_PORT"):
        raw = os.getenv(name, "").strip()
        if raw:
            try:
                port = int(raw)
            except ValueError as exc:
                raise DeploymentConfigError(f"{name} must be an integer, got {raw!r}.") from exc
            if port < 1 or port > 65535:
                raise DeploymentConfigError(f"{name} must be between 1 and 65535.")
            return port
    return default


def _read_host(*, app_env: AppEnvironment, dev_mode: bool) -> str:
    if dev_mode:
        return "127.0.0.1"
    raw = os.getenv("TITAN_WEB_HOST", os.getenv("HOST", "")).strip()
    if raw:
        return raw
    if app_env is AppEnvironment.PRODUCTION:
        return "0.0.0.0"
    return "127.0.0.1"


def _read_bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() == "true"


@dataclass(frozen=True)
class DeploymentSettings:
    """Validated deployment settings loaded from the environment."""

    app_env: AppEnvironment
    host: str
    port: int
    public_base_url: str
    allowed_hosts: tuple[str, ...]
    cors_allowed_origins: tuple[str, ...]
    auth_required: bool
    session_secret: str
    cookie_secure: bool
    log_level: str
    data_directory: Path
    memory_directory: Path
    database_url: str | None
    obsidian_vault_path: Path | None
    browser_tool_enabled: bool
    voice_runtime_enabled: bool
    trading_runtime_enabled: bool
    web_enabled: bool
    dev_mode: bool

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnvironment.PRODUCTION and not self.dev_mode

    def public_safe_dict(self) -> dict[str, object]:
        """Return a JSON-safe summary without secrets."""
        return {
            "app_env": self.app_env.value,
            "host": self.host,
            "port": self.port,
            "public_base_url": self.public_base_url or None,
            "allowed_hosts": list(self.allowed_hosts),
            "cors_allowed_origins": list(self.cors_allowed_origins),
            "auth_required": self.auth_required,
            "session_secret_configured": bool(self.session_secret),
            "cookie_secure": self.cookie_secure,
            "log_level": self.log_level,
            "data_directory": str(self.data_directory),
            "memory_directory": str(self.memory_directory),
            "database_url_configured": bool(self.database_url),
            "obsidian_vault_path_configured": self.obsidian_vault_path is not None,
            "browser_tool_enabled": self.browser_tool_enabled,
            "voice_runtime_enabled": self.voice_runtime_enabled,
            "trading_runtime_enabled": self.trading_runtime_enabled,
            "web_enabled": self.web_enabled,
            "dev_mode": self.dev_mode,
        }


def load_deployment_settings(
    *,
    dev_mode: bool = False,
    remote_mode: bool = False,
    production_mode: bool = False,
    validate: bool = True,
) -> DeploymentSettings:
    """Load and optionally validate deployment settings from the environment."""
    reload_env()
    app_env = _read_app_env()

    if production_mode:
        app_env = AppEnvironment.PRODUCTION
    elif dev_mode:
        app_env = AppEnvironment.DEVELOPMENT
    elif remote_mode:
        app_env = AppEnvironment.DEVELOPMENT

    dev_mode_active = dev_mode or _read_bool("TITAN_WEB_DEV_MODE", "false")
    if production_mode:
        dev_mode_active = False

    web_enabled = (
        _read_bool("TITAN_WEB_ENABLED", "false") or dev_mode or remote_mode or production_mode
    )

    if remote_mode:
        port = int(os.getenv("TITAN_WEB_REMOTE_PORT", "8765"))
        host = "127.0.0.1"
    elif dev_mode:
        port = 8000
        host = "127.0.0.1"
    elif production_mode:
        port = _read_port(default=8000)
        host = _read_host(app_env=AppEnvironment.PRODUCTION, dev_mode=False)
    else:
        port = _read_port(default=8000 if not dev_mode else 8000)
        host = _read_host(app_env=app_env, dev_mode=dev_mode)

    session_secret = os.getenv("TITAN_WEB_SECRET_KEY", os.getenv("SESSION_SECRET", "")).strip()
    if dev_mode and not session_secret:
        from config.settings import TITAN_WEB_DEV_SECRET

        session_secret = TITAN_WEB_DEV_SECRET

    public_base_url = os.getenv("TITAN_PUBLIC_BASE_URL", os.getenv("PUBLIC_BASE_URL", "")).strip()
    allowed_hosts = _parse_csv(os.getenv("TITAN_ALLOWED_HOSTS", os.getenv("ALLOWED_HOSTS", "")))
    cors_allowed_origins = _parse_csv(
        os.getenv("TITAN_CORS_ALLOWED_ORIGINS", os.getenv("CORS_ALLOWED_ORIGINS", ""))
    )

    auth_required_env = os.getenv("TITAN_AUTH_REQUIRED", os.getenv("AUTH_REQUIRED", "")).strip()
    if auth_required_env:
        auth_required = auth_required_env.lower() == "true"
    else:
        auth_required = not dev_mode_active and bool(session_secret)

    cookie_secure_default = "true" if app_env is AppEnvironment.PRODUCTION else "false"
    cookie_secure = _read_bool("TITAN_COOKIE_SECURE", os.getenv("COOKIE_SECURE", cookie_secure_default))

    log_level = os.getenv("TITAN_LOG_LEVEL", os.getenv("LOG_LEVEL", "INFO")).strip().upper()

    data_directory = get_data_directory()
    memory_directory = get_memory_directory()

    database_url = os.getenv("TITAN_DATABASE_URL", os.getenv("DATABASE_URL", "")).strip() or None

    obsidian_raw = os.getenv("TITAN_OBSIDIAN_VAULT_PATH", os.getenv("OBSIDIAN_VAULT_PATH", "")).strip()
    obsidian_vault_path = Path(obsidian_raw).expanduser() if obsidian_raw else None

    browser_tool_enabled = _read_bool("TITAN_BROWSER_ENABLED", os.getenv("BROWSER_TOOL_ENABLED", "false"))
    voice_runtime_enabled = _read_bool("TITAN_VOICE_ENABLED", os.getenv("VOICE_RUNTIME_ENABLED", "true"))
    trading_runtime_enabled = _read_bool("TITAN_TRADING_ENABLED", os.getenv("TRADING_RUNTIME_ENABLED", "true"))

    settings = DeploymentSettings(
        app_env=app_env,
        host=host,
        port=port,
        public_base_url=public_base_url,
        allowed_hosts=allowed_hosts,
        cors_allowed_origins=cors_allowed_origins,
        auth_required=auth_required,
        session_secret=session_secret,
        cookie_secure=cookie_secure,
        log_level=log_level,
        data_directory=data_directory,
        memory_directory=memory_directory,
        database_url=database_url,
        obsidian_vault_path=obsidian_vault_path,
        browser_tool_enabled=browser_tool_enabled,
        voice_runtime_enabled=voice_runtime_enabled,
        trading_runtime_enabled=trading_runtime_enabled,
        web_enabled=web_enabled,
        dev_mode=dev_mode_active,
    )

    if validate:
        validate_deployment_settings(settings)
    return settings


def validate_deployment_settings(settings: DeploymentSettings) -> None:
    """Reject unsafe or incomplete production configuration."""
    if settings.dev_mode and settings.app_env is AppEnvironment.PRODUCTION:
        raise DeploymentConfigError(
            "TITAN_WEB_DEV_MODE cannot be enabled when TITAN_APP_ENV=production."
        )

    if settings.is_production:
        if not settings.web_enabled:
            raise DeploymentConfigError(
                "TITAN_WEB_ENABLED must be true when TITAN_APP_ENV=production."
            )
        if not settings.session_secret:
            raise DeploymentConfigError(
                "TITAN_WEB_SECRET_KEY (or SESSION_SECRET) is required in production."
            )
        if len(settings.session_secret) < _MIN_PRODUCTION_SECRET_LENGTH:
            raise DeploymentConfigError(
                f"TITAN_WEB_SECRET_KEY must be at least {_MIN_PRODUCTION_SECRET_LENGTH} "
                "characters in production."
            )
        if settings.session_secret == "titan-local-dev-only":
            raise DeploymentConfigError(
                "The development secret cannot be used in production."
            )
        if settings.host in ("127.0.0.1", "localhost", "::1"):
            raise DeploymentConfigError(
                "Production must bind to 0.0.0.0 (set TITAN_WEB_HOST=0.0.0.0)."
            )
        if "*" in settings.allowed_hosts:
            raise DeploymentConfigError("TITAN_ALLOWED_HOSTS must not contain '*' in production.")
        if not settings.cookie_secure:
            raise DeploymentConfigError(
                "TITAN_COOKIE_SECURE must be true in production "
                "(set TITAN_COOKIE_SECURE=true)."
            )

    if settings.public_base_url and not re.match(r"^https?://", settings.public_base_url):
        raise DeploymentConfigError(
            "TITAN_PUBLIC_BASE_URL must start with http:// or https://."
        )


def check_data_directory_ready(data_directory: Path | None = None) -> tuple[bool, str]:
    """Return whether the data directory is writable."""
    directory = data_directory or get_data_directory()
    if not directory.exists():
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return False, f"Cannot create data directory: {exc}"
    if not is_directory_writable(directory):
        return False, f"Data directory is not writable: {directory}"
    return True, "ok"


def apply_deployment_env(settings: DeploymentSettings) -> None:
    """Publish validated deployment settings to os.environ for downstream imports."""
    os.environ["TITAN_APP_ENV"] = settings.app_env.value
    os.environ["APP_ENV"] = settings.app_env.value
    os.environ["TITAN_WEB_ENABLED"] = "true" if settings.web_enabled else "false"
    os.environ["TITAN_WEB_HOST"] = settings.host
    os.environ["TITAN_WEB_PORT"] = str(settings.port)
    os.environ["PORT"] = str(settings.port)
    os.environ["TITAN_WEB_SECRET_KEY"] = settings.session_secret
    os.environ["TITAN_WEB_DEV_MODE"] = "true" if settings.dev_mode else "false"
    os.environ["TITAN_LOG_LEVEL"] = settings.log_level
    os.environ["TITAN_DATA_DIR"] = str(settings.data_directory)
    os.environ["TITAN_MEMORY_DIR"] = str(settings.memory_directory)
    if settings.public_base_url:
        os.environ["TITAN_PUBLIC_BASE_URL"] = settings.public_base_url
    if settings.database_url:
        os.environ["TITAN_DATABASE_URL"] = settings.database_url
    os.environ["TITAN_COOKIE_SECURE"] = "true" if settings.cookie_secure else "false"
