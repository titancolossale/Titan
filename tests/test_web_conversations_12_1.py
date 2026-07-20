# =====================================
# Titan Phase 12.1 Conversation Tests
# =====================================

"""Durable conversations, ownership, context trim, streaming lifecycle."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from core.web_conversations.context import select_recent_messages, estimate_tokens
from core.web_conversations.db import (
    apply_migrations,
    create_conversation_engine,
    reset_engine,
)
from core.web_conversations.models import MessageRecord, MessageStatus, utc_now
from core.web_conversations.repository import ConversationRepository
from core.web_conversations.service import (
    ConversationService,
    reset_conversation_service,
)
from core.web_conversations.title import fallback_title_from_message, schedule_title_update


@pytest.fixture()
def conv_engine(tmp_path: Path) -> Engine:
    reset_engine()
    reset_conversation_service()
    engine = create_conversation_engine(
        force_sqlite=True,
        sqlite_path=tmp_path / "conversations.db",
    )
    apply_migrations(engine)
    yield engine
    engine.dispose()
    reset_engine()
    reset_conversation_service()


@pytest.fixture()
def repo(conv_engine: Engine) -> ConversationRepository:
    return ConversationRepository(engine=conv_engine)


@pytest.fixture()
def service(repo: ConversationRepository) -> ConversationService:
    return ConversationService(repository=repo)


def test_create_conversation(service: ConversationService) -> None:
    conv = service.create_conversation("Nolan", title="Test")
    assert conv.id.startswith("conv_")
    assert conv.user_id == "Nolan"
    assert conv.title == "Test"


def test_ownership_isolation(service: ConversationService) -> None:
    a = service.create_conversation("Nolan")
    service.create_conversation("Ibrahim")
    with pytest.raises(PermissionError):
        service.get_conversation_with_messages(a.id, "Ibrahim")
    listed, total = service.list_conversations("Ibrahim")
    assert total == 1
    assert all(c.user_id == "Ibrahim" for c in listed)


def test_messages_persist_across_reopen(tmp_path: Path) -> None:
    reset_engine()
    reset_conversation_service()
    db_path = tmp_path / "persist.db"
    engine1 = create_conversation_engine(force_sqlite=True, sqlite_path=db_path)
    apply_migrations(engine1)
    svc1 = ConversationService(ConversationRepository(engine=engine1))
    conv = svc1.create_conversation("Nolan")
    svc1.persist_user_message(
        conversation_id=conv.id,
        user_id="Nolan",
        content="Mon projet principal s'appelle Titan.",
        request_id="req-1",
    )
    assistant = svc1.begin_assistant_message(
        conversation_id=conv.id,
        user_id="Nolan",
        request_id="req-1",
    )
    svc1.finalize_assistant_message(
        message_id=assistant.id,
        conversation_id=conv.id,
        user_id="Nolan",
        content="Compris — ton projet principal est Titan.",
        status=MessageStatus.COMPLETED.value,
    )
    engine1.dispose()

    engine2 = create_conversation_engine(force_sqlite=True, sqlite_path=db_path)
    svc2 = ConversationService(ConversationRepository(engine=engine2))
    _conv, messages, total = svc2.get_conversation_with_messages(conv.id, "Nolan")
    assert total == 2
    assert messages[0].content.startswith("Mon projet")
    assert "Titan" in messages[1].content
    engine2.dispose()
    reset_engine()
    reset_conversation_service()


def test_follow_up_context_hydration(service: ConversationService) -> None:
    conv = service.create_conversation("Nolan")
    service.persist_user_message(
        conversation_id=conv.id,
        user_id="Nolan",
        content="Mon projet principal s'appelle Titan.",
        request_id="r1",
    )
    pending = service.begin_assistant_message(
        conversation_id=conv.id,
        user_id="Nolan",
        request_id="r1",
    )
    service.finalize_assistant_message(
        message_id=pending.id,
        conversation_id=conv.id,
        user_id="Nolan",
        content="Noté.",
    )
    engine = MagicMock()
    engine.clear = MagicMock()
    engine.add_user_turn = MagicMock()
    engine.add_titan_turn = MagicMock()
    summary = service.hydrate_engine_history(conv.id, "Nolan", engine)
    assert summary["context_message_count"] == 2
    assert engine.clear.called
    assert engine.add_user_turn.called
    assert engine.add_titan_turn.called


def test_context_trim_oldest_first() -> None:
    now = utc_now()
    messages = [
        MessageRecord(
            id=f"m{i}",
            conversation_id="c1",
            role="user" if i % 2 == 0 else "assistant",
            content=("x" * 200) + str(i),
            created_at=now,
            status=MessageStatus.COMPLETED.value,
            sequence=i,
        )
        for i in range(20)
    ]
    selected = select_recent_messages(messages, max_turns=6, max_tokens=80)
    assert len(selected) <= 6
    assert selected[-1].sequence == messages[-1].sequence
    assert estimate_tokens("abcd") == 1


def test_title_generation_non_blocking() -> None:
    assert fallback_title_from_message("Bonjour Titan") == "Accueil avec Titan"
    assert "Railway" in fallback_title_from_message("On continue le déploiement Railway")
    renamed: list[str] = []

    def rename(_c: str, _u: str, title: str) -> None:
        renamed.append(title)

    started = time.perf_counter()
    title = schedule_title_update(
        conversation_id="c1",
        user_id="Nolan",
        first_message="Bonjour Titan",
        rename=rename,
        llm_ask=None,
    )
    elapsed = time.perf_counter() - started
    assert title == "Accueil avec Titan"
    assert elapsed < 0.2
    assert renamed


def test_retry_does_not_duplicate_user_message(service: ConversationService) -> None:
    conv = service.create_conversation("Nolan")
    first = service.persist_user_message(
        conversation_id=conv.id,
        user_id="Nolan",
        content="Hello",
        request_id="r1",
        allow_duplicate=False,
    )
    pending = service.begin_assistant_message(
        conversation_id=conv.id,
        user_id="Nolan",
        request_id="r1",
    )
    service.finalize_assistant_message(
        message_id=pending.id,
        conversation_id=conv.id,
        user_id="Nolan",
        content="",
        status=MessageStatus.FAILED.value,
        error_code="provider_unavailable",
    )
    second = service.persist_user_message(
        conversation_id=conv.id,
        user_id="Nolan",
        content="Hello",
        request_id="r2",
        allow_duplicate=False,
    )
    assert second.id == first.id
    _c, messages, total = service.get_conversation_with_messages(conv.id, "Nolan")
    assert sum(1 for m in messages if m.role == "user") == 1
    assert total == 2


def test_assistant_idempotent_request(service: ConversationService) -> None:
    conv = service.create_conversation("Nolan")
    a1 = service.begin_assistant_message(
        conversation_id=conv.id,
        user_id="Nolan",
        request_id="same-req",
    )
    a2 = service.begin_assistant_message(
        conversation_id=conv.id,
        user_id="Nolan",
        request_id="same-req",
    )
    assert a1.id == a2.id


def test_stream_delta_emitter() -> None:
    from brain.cognitive_stream import CognitiveStreamEmitter

    events: list[tuple[str, dict]] = []
    stream = CognitiveStreamEmitter(lambda t, d: events.append((t, d)))
    stream.emit_response_started()
    stream.emit_text_delta("Bon")
    stream.emit_text_delta("jour")
    types = [t for t, _ in events]
    assert "response_started" in types
    assert types.count("text_delta") == 2


def test_unauthenticated_conversations_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TITAN_WEB_ENABLED", "true")
    monkeypatch.setenv("TITAN_WEB_DEV_MODE", "false")
    monkeypatch.setenv("TITAN_WEB_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("TITAN_CONVERSATION_PERSISTENCE_REQUIRED", "false")
    from api.app import create_app

    client = TestClient(create_app())
    response = client.get("/api/conversations")
    assert response.status_code in {401, 403}


def test_health_and_ready_include_conversation_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("TITAN_WEB_ENABLED", "true")
    monkeypatch.setenv("TITAN_WEB_DEV_MODE", "true")
    monkeypatch.setenv("TITAN_CONVERSATION_PERSISTENCE_ENABLED", "true")
    monkeypatch.setenv("TITAN_CONVERSATION_PERSISTENCE_REQUIRED", "false")
    monkeypatch.setenv("TITAN_DATA_DIR", str(tmp_path))
    reset_engine()
    reset_conversation_service()
    from api.app import create_app

    client = TestClient(create_app())
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    ready = client.get("/ready")
    assert ready.status_code == 200
    body = ready.json()
    assert "conversation_store" in body.get("checks", {})


def test_authenticated_create_conversation_dev_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("TITAN_WEB_ENABLED", "true")
    monkeypatch.setenv("TITAN_WEB_DEV_MODE", "true")
    monkeypatch.setenv("TITAN_CONVERSATION_PERSISTENCE_ENABLED", "true")
    monkeypatch.setenv("TITAN_CONVERSATION_PERSISTENCE_REQUIRED", "false")
    monkeypatch.setenv("TITAN_DATA_DIR", str(tmp_path / "data"))
    reset_engine()
    reset_conversation_service()
    from api.app import create_app

    client = TestClient(create_app())
    response = client.post("/api/conversations", json={"title": "Accueil"})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["conversation"]["title"] == "Accueil"
    conv_id = data["conversation"]["id"]
    listed = client.get("/api/conversations")
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1
    detail = client.get(f"/api/conversations/{conv_id}")
    assert detail.status_code == 200
    assert detail.json()["conversation"]["id"] == conv_id
