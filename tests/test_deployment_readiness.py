# =====================================
# Titan Deployment Readiness Tests
# =====================================

"""Tests for Phase 10.1 cloud deployment preparation."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from config.deployment import (
    DeploymentConfigError,
    check_data_directory_ready,
    load_deployment_settings,
    validate_deployment_settings,
)
from api.password_security import hash_password
from config.paths import get_data_directory, is_directory_writable, resolve_under_data


@pytest.fixture
def prod_secret() -> str:
    return "production-secret-key-32chars-min"


def test_load_deployment_settings_development_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TITAN_APP_ENV", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("TITAN_WEB_HOST", raising=False)
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("TITAN_WEB_DEV_MODE", raising=False)
    monkeypatch.setenv("TITAN_APP_ENV", "development")
    settings = load_deployment_settings(validate=False)
    assert settings.app_env.value == "development"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.cookie_secure is False
    assert settings.dev_mode is False


def test_production_rejects_missing_secret(prod_secret: str) -> None:
    settings = load_deployment_settings(production_mode=True, validate=False)
    settings = settings.__class__(
        **{**settings.__dict__, "session_secret": "", "dev_mode": False}
    )
    with pytest.raises(DeploymentConfigError, match="TITAN_WEB_SECRET_KEY"):
        validate_deployment_settings(settings)


def test_production_rejects_short_secret(prod_secret: str) -> None:
    settings = load_deployment_settings(production_mode=True, validate=False)
    settings = settings.__class__(
        **{**settings.__dict__, "session_secret": "short", "dev_mode": False}
    )
    with pytest.raises(DeploymentConfigError, match="at least"):
        validate_deployment_settings(settings)


def test_production_rejects_dev_secret(prod_secret: str) -> None:
    settings = load_deployment_settings(production_mode=True, validate=False)
    settings = settings.__class__(
        **{**settings.__dict__, "session_secret": "titan-local-dev-only", "dev_mode": False}
    )
    with pytest.raises(DeploymentConfigError, match="development secret"):
        validate_deployment_settings(settings)


def test_production_rejects_localhost_bind(prod_secret: str) -> None:
    settings = load_deployment_settings(production_mode=True, validate=False)
    settings = settings.__class__(
        **{
            **settings.__dict__,
            "session_secret": prod_secret,
            "host": "127.0.0.1",
            "cookie_secure": True,
            "dev_mode": False,
            "web_enabled": True,
        }
    )
    with pytest.raises(DeploymentConfigError, match="0.0.0.0"):
        validate_deployment_settings(settings)


def test_production_accepts_valid_settings(
    monkeypatch: pytest.MonkeyPatch,
    prod_secret: str,
) -> None:
    monkeypatch.setenv("TITAN_WEB_SECRET_KEY", prod_secret)
    monkeypatch.setenv("TITAN_COOKIE_SECURE", "true")
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("TITAN_AUTH_USERNAME", "nolan")
    # Synthetic test hash only — not a real credential.
    from api.password_security import hash_password

    monkeypatch.setenv("TITAN_AUTH_PASSWORD_HASH", hash_password("ValidTestPass1!xx"))
    monkeypatch.setenv("TITAN_WEB_HOST", "0.0.0.0")
    settings = load_deployment_settings(production_mode=True, validate=True)
    assert settings.host == "0.0.0.0"
    assert settings.is_production is True
    assert settings.auth_required is True


def test_custom_port_from_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "9090")
    settings = load_deployment_settings(validate=False)
    assert settings.port == 9090


def test_cross_platform_data_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TITAN_DATA_DIR", str(tmp_path / "runtime-data"))
    data_dir = get_data_directory()
    assert data_dir == (tmp_path / "runtime-data").resolve()
    note_path = resolve_under_data("long_term_memory.json")
    assert note_path.parent == data_dir


def test_data_directory_writable(tmp_path: Path) -> None:
    ok, message = check_data_directory_ready(tmp_path / "data")
    assert ok is True
    assert message == "ok"
    assert is_directory_writable(tmp_path / "data") is True


def test_ready_endpoint_reports_core_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prod_secret: str,
) -> None:
    monkeypatch.setenv("TITAN_WEB_ENABLED", "true")
    monkeypatch.setenv("TITAN_WEB_SECRET_KEY", prod_secret)
    monkeypatch.setenv("TITAN_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TITAN_WEB_DEV_MODE", "false")

    with patch("api.auth.is_web_dev_mode", return_value=False), patch(
        "api.auth.get_web_secret_key",
        return_value=prod_secret,
    ):
        client = TestClient(create_app())
        response = client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["web_enabled"]["ok"] is True
    assert payload["checks"]["data_directory"]["ok"] is True
    assert "optional_subsystems" in payload
    obsidian = next(s for s in payload["optional_subsystems"] if s["name"] == "obsidian")
    assert obsidian["status"] in {"disabled", "available", "unavailable"}


def test_ready_not_ready_when_web_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TITAN_WEB_ENABLED", "false")
    monkeypatch.setenv("TITAN_DATA_DIR", str(tmp_path / "data"))

    client = TestClient(create_app())
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_health_endpoint_still_public(
    monkeypatch: pytest.MonkeyPatch,
    prod_secret: str,
) -> None:
    monkeypatch.setenv("TITAN_WEB_ENABLED", "true")
    monkeypatch.setenv("TITAN_WEB_SECRET_KEY", prod_secret)
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_app_route_serves_frontend(
    monkeypatch: pytest.MonkeyPatch,
    prod_secret: str,
) -> None:
    monkeypatch.setenv("TITAN_WEB_ENABLED", "true")
    monkeypatch.setenv("TITAN_WEB_SECRET_KEY", prod_secret)
    client = TestClient(create_app())
    response = client.get("/app/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_web_prod_starts_uvicorn_on_custom_port(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    prod_secret: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "TITAN_WEB_ENABLED=true",
                f"TITAN_WEB_SECRET_KEY={prod_secret}",
                "TITAN_COOKIE_SECURE=true",
                "AUTH_REQUIRED=true",
                "TITAN_AUTH_USERNAME=nolan",
                f"TITAN_AUTH_PASSWORD_HASH={hash_password('ValidTestPass1!xx')}",
                "PORT=9876",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("config.settings.ENV_FILE_PATH", env_file)
    monkeypatch.setenv("TITAN_WEB_SECRET_KEY", prod_secret)
    monkeypatch.setenv("TITAN_COOKIE_SECURE", "true")
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("TITAN_AUTH_USERNAME", "nolan")
    monkeypatch.setenv("TITAN_AUTH_PASSWORD_HASH", hash_password("ValidTestPass1!xx"))
    monkeypatch.setenv("TITAN_WEB_HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "9876")

    fake_uvicorn = MagicMock()
    with patch.dict(sys.modules, {"uvicorn": fake_uvicorn}):
        from core.web_cli import run_web_server

        assert run_web_server(production_mode=True) == 0

    fake_uvicorn.run.assert_called_once()
    _, kwargs = fake_uvicorn.run.call_args
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 9876
    assert kwargs["reload"] is False

    captured = capsys.readouterr().out
    assert "Mode production" in captured
    assert "webbrowser" not in captured.lower()


def test_web_dev_still_uses_localhost(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("TITAN_WEB_ENABLED=false\n", encoding="utf-8")
    monkeypatch.setattr("config.settings.ENV_FILE_PATH", env_file)

    from core.web_cli import _read_web_config

    config = _read_web_config(dev_mode=True)
    assert config.host == "127.0.0.1"
    assert config.port == 8000
    assert config.dev_mode is True


def test_web_prod_rejects_invalid_config(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("TITAN_WEB_SECRET_KEY", "short")
    monkeypatch.setenv("TITAN_COOKIE_SECURE", "false")

    from core.web_cli import run_web_server

    assert run_web_server(production_mode=True) == 1
    assert "Configuration de déploiement invalide" in capsys.readouterr().out


def test_public_safe_dict_never_includes_secret(prod_secret: str) -> None:
    settings = load_deployment_settings(production_mode=True, validate=False)
    settings = settings.__class__(
        **{**settings.__dict__, "session_secret": prod_secret}
    )
    safe = settings.public_safe_dict()
    assert prod_secret not in str(safe)
    assert safe["session_secret_configured"] is True


def test_dispatch_web_prod_command(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.web_cli import dispatch_web_command

    with patch("core.web_cli.run_web_server", return_value=0) as run_mock:
        with pytest.raises(SystemExit) as exc:
            dispatch_web_command("web-prod")
    assert exc.value.code == 0
    run_mock.assert_called_once_with(production_mode=True)
