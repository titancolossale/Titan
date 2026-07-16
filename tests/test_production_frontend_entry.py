# =====================================
# Titan Production Frontend Entry Tests
# =====================================

"""Prove FastAPI serves the approved final web/v2 UI as the default Titan Web App.

Canonical frontend: web/v2/ (served at /app/)
Legacy frontend: web/static/ (available only under /static/ — never default)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.app import CANONICAL_APP_PATH, STATIC_DIR, V2_DIR, create_app
from api.login_rate_limit import reset_login_rate_limiter
from api.password_security import hash_password
from api.session_manager import (
    SESSION_COOKIE_NAME,
    SessionConfig,
    SessionManager,
    reset_session_manager,
)
from api.titan_service import reset_titan

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "Dockerfile"
DOCKERIGNORE = ROOT / ".dockerignore"
V2_INDEX = V2_DIR / "index.html"
LEGACY_INDEX = STATIC_DIR / "index.html"

# Markers that identify the deprecated Interface V1 shell.
LEGACY_MARKERS = (
    "tdl-page--app",
    "tdl-workspace--reference",
    "Titan — Intelligence",
    "/static/app.js",
    "tdl-ref-orchestrator",
)

TEST_USERNAME = "nolan"
TEST_PASSWORD = "CorrectHorseBattery1!"


@pytest.fixture()
def password_hash() -> str:
    return hash_password(TEST_PASSWORD)


@pytest.fixture()
def web_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Dev-mode client (session auth off) — mirrors local web-dev."""
    monkeypatch.setenv("TITAN_WEB_DEV_MODE", "true")
    monkeypatch.setenv("TITAN_WEB_SECRET_KEY", "titan-local-dev-only")
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setenv("TITAN_AUTH_REQUIRED", "false")
    reset_titan()
    reset_session_manager()
    reset_login_rate_limiter()
    with patch("config.settings.is_web_dev_mode", return_value=True), patch(
        "api.auth.is_web_dev_mode", return_value=True
    ):
        yield TestClient(create_app())


@pytest.fixture()
def auth_client(monkeypatch: pytest.MonkeyPatch, password_hash: str) -> TestClient:
    """Session-auth client — mirrors Railway production gate."""
    monkeypatch.setenv("TITAN_WEB_ENABLED", "true")
    monkeypatch.setenv("TITAN_WEB_SECRET_KEY", "test-session-signing-secret-32")
    monkeypatch.setenv("TITAN_WEB_DEV_MODE", "false")
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("TITAN_AUTH_REQUIRED", "true")
    monkeypatch.setenv("TITAN_AUTH_USERNAME", TEST_USERNAME)
    monkeypatch.setenv("TITAN_AUTH_PASSWORD_HASH", password_hash)
    monkeypatch.setenv("TITAN_COOKIE_SECURE", "true")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("TITAN_PUBLIC_BASE_URL", "https://titan.test")
    monkeypatch.setenv("TITAN_ALLOWED_HOSTS", "titan.test")
    reset_titan()
    reset_session_manager(
        SessionManager(SessionConfig(idle_minutes=60, max_hours=24, cookie_secure=True))
    )
    reset_login_rate_limiter()
    with patch("config.settings.is_web_dev_mode", return_value=False), patch(
        "api.auth.is_web_dev_mode", return_value=False
    ):
        yield TestClient(create_app(), base_url="https://titan.test")


def _login(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"username": TEST_USERNAME, "password": TEST_PASSWORD, "next": "/app/"},
    )
    assert response.status_code == 200
    assert SESSION_COOKIE_NAME in response.cookies


def test_canonical_paths_exist() -> None:
    assert V2_INDEX.is_file()
    assert LEGACY_INDEX.is_file()
    assert CANONICAL_APP_PATH == "/app/"
    html = V2_INDEX.read_text(encoding="utf-8")
    assert 'titan-canonical-reference" content="final"' in html
    assert "canonical-final.css" in html
    assert "titan-v2-root" in html


def test_authenticated_app_serves_final_frontend(auth_client: TestClient) -> None:
    _login(auth_client)
    response = auth_client.get("/app/", follow_redirects=False)
    assert response.status_code == 200
    body = response.text
    assert "titan-v2-root" in body
    assert 'titan-canonical-reference" content="final"' in body
    assert "./design/canonical-final.css" in body
    assert "./main.js" in body
    for marker in LEGACY_MARKERS:
        assert marker not in body, f"legacy marker leaked into /app/: {marker}"


def test_app_assets_contain_final_ui_markers(auth_client: TestClient) -> None:
    """Final UI copy lives in modules; HTML shell + assets must prove the right tree."""
    _login(auth_client)
    html = auth_client.get("/app/").text
    assert "titan-v2-root" in html

    satellites = auth_client.get("/app/center/cognitive-satellites.js")
    status = auth_client.get("/app/status/status-region.js")
    orch_css = auth_client.get("/app/design/orchestrator.css")
    presence_css = auth_client.get("/app/design/presence.css")
    shell = auth_client.get("/app/layout/shell.js")
    css = auth_client.get("/app/design/canonical-final.css")
    main_js = auth_client.get("/app/main.js")

    for response in (satellites, status, orch_css, presence_css, shell, css, main_js):
        assert response.status_code == 200

    bundle = "\n".join(
        [
            satellites.text,
            status.text,
            orch_css.text,
            presence_css.text,
            shell.text,
        ]
    )
    assert "TITAN CORE" in bundle
    assert "COGNITIVE ORCHESTRATOR" in bundle.upper()
    assert "Obsidian Vault" in bundle
    assert "Mémoire Récente" in bundle


def test_unauthenticated_app_redirects_to_login(auth_client: TestClient) -> None:
    response = auth_client.get("/app/", follow_redirects=False)
    assert response.status_code in {302, 303}
    assert "/login" in response.headers["location"]


def test_unauthenticated_root_redirects_to_login(auth_client: TestClient) -> None:
    response = auth_client.get("/", follow_redirects=False)
    assert response.status_code in {302, 303}
    assert "/login" in response.headers["location"]


def test_authenticated_root_redirects_to_app(auth_client: TestClient) -> None:
    _login(auth_client)
    response = auth_client.get("/", follow_redirects=False)
    assert response.status_code in {302, 303}
    assert response.headers["location"].rstrip("/") == "/app"


def test_app_refresh_serves_html(auth_client: TestClient) -> None:
    """Browser refresh on /app/ must still return the SPA shell (StaticFiles html=True)."""
    _login(auth_client)
    first = auth_client.get("/app/")
    second = auth_client.get("/app/")
    assert first.status_code == 200
    assert second.status_code == 200
    assert "titan-v2-root" in second.text
    assert second.headers.get("content-type", "").startswith("text/html")


def test_web_dev_serves_canonical_frontend(web_client: TestClient) -> None:
    body = web_client.get("/app/").text
    assert 'titan-canonical-reference" content="final"' in body
    assert "./design/canonical-final.css" in body
    assert "tdl-page--app" not in body


def test_production_serves_canonical_frontend(auth_client: TestClient) -> None:
    _login(auth_client)
    body = auth_client.get("/app/").text
    assert 'titan-canonical-reference" content="final"' in body
    assert "./design/canonical-final.css" in body
    assert "tdl-page--app" not in body


def test_web_dev_and_production_share_same_canonical_index() -> None:
    """Same on-disk web/v2 index is the single canonical frontend for both modes."""
    html = V2_INDEX.read_text(encoding="utf-8")
    assert 'titan-canonical-reference" content="final"' in html
    assert "./design/canonical-final.css" in html
    assert "titan-v2-root" in html
    api = (ROOT / "api" / "app.py").read_text(encoding="utf-8")
    assert 'mount("/app"' in api
    assert "V2_DIR" in api
    assert "RedirectResponse" in api


def test_web_dev_root_redirects_to_app(web_client: TestClient) -> None:
    response = web_client.get("/", follow_redirects=False)
    assert response.status_code in {302, 303}
    assert response.headers["location"].rstrip("/") == "/app"
    followed = web_client.get("/")
    assert followed.status_code == 200
    assert "titan-v2-root" in followed.text
    assert "Titan — Intelligence" not in followed.text


def test_dockerfile_includes_canonical_frontend() -> None:
    """Railway/Docker image must ship web/v2 (COPY . .) and must not ignore it."""
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY . ." in dockerfile
    assert 'CMD ["python", "main.py", "web-prod"]' in dockerfile

    dockerignore = DOCKERIGNORE.read_text(encoding="utf-8")
    lines = [
        line.strip()
        for line in dockerignore.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    for banned in ("web/", "web/v2", "web/v2/", "*.html"):
        assert banned not in lines, f".dockerignore excludes {banned}"

    assert V2_INDEX.is_file()
    assert (V2_DIR / "design" / "canonical-final.css").is_file()
    assert (V2_DIR / "main.js").is_file()
    assert (V2_DIR / "center" / "cognitive-satellites.js").is_file()


def test_api_module_documents_canonical_frontend() -> None:
    api = (ROOT / "api" / "app.py").read_text(encoding="utf-8")
    assert "Canonical production frontend" in api
    assert 'mount("/app"' in api
    assert "RedirectResponse" in api
    assert "CANONICAL_APP_PATH" in api
