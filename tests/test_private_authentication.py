# =====================================
# Titan Private Authentication Tests
# =====================================

"""Phase 10.3 — private production session authentication."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.login_rate_limit import reset_login_rate_limiter
from api.password_security import hash_password, validate_password_strength, verify_password
from api.session_manager import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    SessionConfig,
    SessionManager,
    reset_session_manager,
)
from api.titan_service import reset_titan, set_titan
from core.titan import Titan
from tools.tool_manager import ToolManager

TEST_USERNAME = "nolan"
TEST_PASSWORD = "CorrectHorseBattery1!"


@pytest.fixture
def password_hash() -> str:
    return hash_password(TEST_PASSWORD)


@pytest.fixture
def session_auth_env(
    monkeypatch: pytest.MonkeyPatch,
    password_hash: str,
) -> None:
    """Enable Phase 10.3 session authentication for tests."""
    monkeypatch.setenv("TITAN_WEB_ENABLED", "true")
    monkeypatch.setenv("TITAN_WEB_SECRET_KEY", "test-session-signing-secret-32")
    monkeypatch.setenv("TITAN_WEB_DEV_MODE", "false")
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("TITAN_AUTH_REQUIRED", "true")
    monkeypatch.setenv("TITAN_AUTH_USERNAME", TEST_USERNAME)
    monkeypatch.setenv("TITAN_AUTH_PASSWORD_HASH", password_hash)
    monkeypatch.setenv("TITAN_COOKIE_SECURE", "true")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("TITAN_SESSION_IDLE_MINUTES", "60")
    monkeypatch.setenv("TITAN_SESSION_MAX_HOURS", "24")
    monkeypatch.setenv("TITAN_PUBLIC_BASE_URL", "https://titan.test")
    monkeypatch.setenv("TITAN_ALLOWED_HOSTS", "titan.test")
    reset_session_manager(SessionManager(SessionConfig(idle_minutes=60, max_hours=24, cookie_secure=True)))
    reset_login_rate_limiter()


@pytest.fixture
def auth_client(session_auth_env, tmp_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Authenticated-capable TestClient with isolated Titan Core."""
    reset_titan()
    tool_manager = ToolManager(project_root=tmp_path)
    titan = Titan()
    titan.tools = tool_manager
    titan.brain.tool_manager = tool_manager
    titan.status = "ONLINE"
    monkeypatch.setattr(
        titan.brain,
        "process_request",
        MagicMock(
            return_value=__import__(
                "brain.natural_language_orchestrator",
                fromlist=["OrchestrationResult"],
            ).OrchestrationResult(
                request_analysis=__import__(
                    "brain.natural_language_orchestrator",
                    fromlist=["RequestAnalysis"],
                ).RequestAnalysis(
                    request="test",
                    normalized="test",
                    tokens=("test",),
                ),
                detected_intent=__import__(
                    "brain.natural_language_orchestrator",
                    fromlist=["DetectedIntent"],
                ).DetectedIntent.CONVERSATION,
                pipeline_decision=__import__(
                    "brain.natural_language_orchestrator",
                    fromlist=["PipelineDecision"],
                ).PipelineDecision(
                    intent=__import__(
                        "brain.natural_language_orchestrator",
                        fromlist=["DetectedIntent"],
                    ).DetectedIntent.CONVERSATION,
                    systems=(),
                    awareness_systems=(),
                ),
                systems_used=__import__(
                    "brain.natural_language_orchestrator",
                    fromlist=["SystemsUsed"],
                ).SystemsUsed(),
                reasoning_summary="Test",
                confidence=0.9,
                final_response="Réponse de test depuis Brain.",
                artifacts={},
                duration_seconds=0.01,
            )
        ),
    )
    set_titan(titan)

    with patch("config.settings.is_web_dev_mode", return_value=False), patch(
        "api.auth.is_web_dev_mode", return_value=False
    ):
        client = TestClient(create_app(), base_url="https://titan.test")
        yield client

    reset_titan()
    reset_session_manager()
    reset_login_rate_limiter()


def _login(client: TestClient, *, username: str = TEST_USERNAME, password: str = TEST_PASSWORD):
    return client.post(
        "/auth/login",
        json={"username": username, "password": password, "next": "/app/"},
    )


def test_health_public_without_auth(auth_client: TestClient) -> None:
    response = auth_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["session_auth"] is True


def test_ready_public_without_auth(auth_client: TestClient) -> None:
    response = auth_client.get("/ready")
    assert response.status_code in {200, 503}


def test_app_redirects_unauthenticated_to_login(auth_client: TestClient) -> None:
    response = auth_client.get("/app/", follow_redirects=False)
    assert response.status_code in {302, 303}
    assert "/login" in response.headers["location"]


def test_root_redirects_unauthenticated_to_login(auth_client: TestClient) -> None:
    response = auth_client.get("/", follow_redirects=False)
    assert response.status_code in {302, 303}
    assert "/login" in response.headers["location"]


def test_protected_api_returns_401_without_auth(auth_client: TestClient) -> None:
    response = auth_client.get("/status", headers={"Accept": "application/json"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_chat_api_returns_401_without_auth(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/chat/message",
        json={"message": "bonjour"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 401


def test_events_stream_requires_auth(auth_client: TestClient) -> None:
    response = auth_client.get("/events/stream?snapshot=true", headers={"Accept": "text/event-stream"})
    assert response.status_code == 401


def test_login_success_sets_httponly_secure_cookie(auth_client: TestClient) -> None:
    response = _login(auth_client)
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["username"] == TEST_USERNAME
    assert "password" not in payload
    assert "password_hash" not in str(payload).lower()
    assert "TITAN_AUTH_PASSWORD_HASH" not in str(payload)

    session_cookie = response.cookies.get(SESSION_COOKIE_NAME)
    assert session_cookie
    # Starlette TestClient exposes Set-Cookie headers for flag inspection.
    set_cookie_headers = response.headers.get_list("set-cookie") if hasattr(response.headers, "get_list") else []
    if not set_cookie_headers:
        # httpx / starlette may flatten; fall back to raw header string.
        raw = response.headers.get("set-cookie", "")
        set_cookie_headers = [raw] if raw else []
    joined = " | ".join(set_cookie_headers).lower()
    assert "httponly" in joined
    assert "secure" in joined
    assert "samesite=lax" in joined


def test_login_failure_generic_message(auth_client: TestClient) -> None:
    response = _login(auth_client, password="WrongPassword999!")
    assert response.status_code == 401
    assert response.json()["detail"] == "Identifiants invalides."
    assert SESSION_COOKIE_NAME not in response.cookies


def test_login_unknown_user_same_message(auth_client: TestClient) -> None:
    response = _login(auth_client, username="nobody", password="WrongPassword999!")
    assert response.status_code == 401
    assert response.json()["detail"] == "Identifiants invalides."


def test_authenticated_reload_remains_authenticated(auth_client: TestClient) -> None:
    login = _login(auth_client)
    assert login.status_code == 200
    status = auth_client.get("/auth/status")
    assert status.status_code == 200
    assert status.json()["authenticated"] is True
    app_page = auth_client.get("/app/", follow_redirects=False)
    assert app_page.status_code == 200


def test_logout_invalidates_session(auth_client: TestClient) -> None:
    assert _login(auth_client).status_code == 200
    logout = auth_client.post("/auth/logout")
    assert logout.status_code == 200
    assert logout.json()["ok"] is True
    protected = auth_client.get("/status", headers={"Accept": "application/json"})
    assert protected.status_code == 401


def test_expired_session_rejected(auth_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = SessionManager(
        SessionConfig(idle_minutes=60, max_hours=24, cookie_secure=True)
    )
    reset_session_manager(manager)
    login = _login(auth_client)
    assert login.status_code == 200
    session_id = login.cookies.get(SESSION_COOKIE_NAME)
    record = manager.get_session(session_id)
    assert record is not None
    # Force absolute expiry.
    record.created_at -= 25 * 3600
    record.last_activity -= 25 * 3600
    denied = auth_client.get("/status", headers={"Accept": "application/json"})
    assert denied.status_code == 401


def test_login_rate_limiting(auth_client: TestClient) -> None:
    for _ in range(5):
        response = _login(auth_client, password="WrongPassword999!")
        assert response.status_code == 401
    locked = _login(auth_client, password="WrongPassword999!")
    assert locked.status_code == 429


def test_password_hash_never_returned_to_frontend(
    auth_client: TestClient,
    password_hash: str,
) -> None:
    login = _login(auth_client)
    assert password_hash not in login.text
    status = auth_client.get("/auth/status")
    assert password_hash not in status.text
    assert "argon2" not in status.text.lower()


def test_alternate_paths_cannot_bypass_auth(auth_client: TestClient) -> None:
    for path in ("/v2/", "/static/index.html", "/design", "/docs", "/memory/status"):
        response = auth_client.get(path, headers={"Accept": "application/json"}, follow_redirects=False)
        assert response.status_code in {401, 303, 302, 404}, path


def test_open_redirect_blocked_on_login(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/auth/login",
        json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD,
            "next": "https://evil.example/phish",
        },
    )
    assert response.status_code == 200
    assert response.json()["next"] == "/app/"


def test_authenticated_functionality_still_works(auth_client: TestClient) -> None:
    assert _login(auth_client).status_code == 200
    status = auth_client.get("/status")
    assert status.status_code == 200
    assert "name" in status.json() or "status" in status.json() or isinstance(status.json(), dict)

    chat = auth_client.post(
        "/api/chat/message",
        json={"message": "bonjour Titan"},
        headers={"X-CSRF-Token": auth_client.cookies.get(CSRF_COOKIE_NAME, "")},
    )
    assert chat.status_code == 200
    body = chat.json()
    assert "response" in body or "final_response" in body or "message" in body or body


def test_login_page_is_french_and_public(auth_client: TestClient) -> None:
    response = auth_client.get("/login")
    assert response.status_code == 200
    assert "ACCÈS PRIVÉ" in response.text
    assert "ENTRER DANS TITAN" in response.text
    assert "Identifiant" in response.text
    assert TEST_PASSWORD not in response.text


def test_authenticated_user_redirected_from_login(auth_client: TestClient) -> None:
    assert _login(auth_client).status_code == 200
    response = auth_client.get("/login", follow_redirects=False)
    assert response.status_code in {302, 303}
    assert "/app" in response.headers["location"]


def test_password_strength_rules() -> None:
    assert validate_password_strength("short")[0] is False
    assert validate_password_strength("alllowercase1!")[0] is False
    assert validate_password_strength("ALLUPPERCASE1!")[0] is False
    assert validate_password_strength("NoDigitsHere!!")[0] is False
    assert validate_password_strength("NoSpecialChar12")[0] is False
    assert validate_password_strength(TEST_PASSWORD)[0] is True


def test_argon2_and_bcrypt_verify() -> None:
    argon_hash = hash_password(TEST_PASSWORD)
    assert verify_password(TEST_PASSWORD, argon_hash) is True
    assert verify_password("wrong", argon_hash) is False

    import bcrypt

    bcrypt_hash = bcrypt.hashpw(TEST_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    assert verify_password(TEST_PASSWORD, bcrypt_hash) is True
    assert verify_password("wrong", bcrypt_hash) is False
