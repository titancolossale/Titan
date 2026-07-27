# =====================================
# Titan Phase 12.2 Conversation Intelligence Tests
# =====================================

"""Long conversations, summaries, reconstruction, project continuity, references."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from brain.pipeline.context_bundle import ThinkContext
from brain.prompt_builder import PromptBuilder
from core.conversation_engine import ConversationEngine
from core.web_conversations.context import (
    ConversationContextBuilder,
    PinnedFacts,
    load_intelligence_metadata,
)
from core.web_conversations.db import (
    apply_migrations,
    create_conversation_engine,
    reset_engine,
)
from core.web_conversations.models import MessageRecord, MessageStatus
from core.web_conversations.repository import ConversationRepository
from core.web_conversations.service import (
    ConversationService,
    reset_conversation_service,
)


def _msg(
    role: str,
    content: str,
    *,
    sequence: int = 0,
    conversation_id: str = "conv_test",
) -> MessageRecord:
    return MessageRecord(
        id=f"msg_{sequence}_{role}",
        conversation_id=conversation_id,
        role=role,
        content=content,
        created_at=datetime.now(timezone.utc),
        status=MessageStatus.COMPLETED.value,
        sequence=sequence,
    )


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
def service(conv_engine: Engine) -> ConversationService:
    return ConversationService(repository=ConversationRepository(engine=conv_engine))


def test_long_conversation_creates_summary_instead_of_discard(caplog: pytest.LogCaptureFixture) -> None:
    builder = ConversationContextBuilder(
        max_recent_turns=4,
        summarize_threshold=6,
        max_tokens=2000,
    )
    messages: list[MessageRecord] = []
    seq = 0
    for i in range(10):
        messages.append(_msg("user", f"My project is Titan. Note {i} about architecture.", sequence=seq))
        seq += 1
        messages.append(
            _msg("assistant", f"Understood note {i}. We continue on Titan.", sequence=seq)
        )
        seq += 1

    with caplog.at_level(logging.INFO):
        bundle = builder.build(messages, conversation_id="conv_long", request_id="req_long")

    assert bundle.summary
    assert bundle.summary_created
    assert "Titan" in (bundle.summary or "")
    assert len(bundle.recent_messages) <= 4
    assert "SUMMARY_CREATED" in caplog.text
    assert "CONTEXT_BUILD_STARTED" in caplog.text
    assert "CONTEXT_BUILD_FINISHED" in caplog.text
    assert "CONTEXT_TOKEN_COUNT" in caplog.text


def test_summary_loaded_and_pinned_facts_preserved(caplog: pytest.LogCaptureFixture) -> None:
    builder = ConversationContextBuilder(max_recent_turns=4, summarize_threshold=50)
    existing = PinnedFacts(
        active_project="Titan",
        important_decisions=["We decided to use Obsidian"],
        user_goals=["Ship Phase 12.2"],
        unfinished_tasks=["Wire context builder"],
        current_topic="conversation intelligence",
    )
    messages = [
        _msg("user", "Continue.", sequence=1),
        _msg("assistant", "Poursuivons sur conversation intelligence.", sequence=2),
    ]
    with caplog.at_level(logging.INFO):
        bundle = builder.build(
            messages,
            existing_summary="Earlier: project Titan; decided Obsidian.",
            existing_pinned=existing,
            current_message="Continue.",
            conversation_id="conv_pin",
            request_id="req_pin",
        )

    assert bundle.summary_loaded
    assert bundle.pinned_facts.active_project == "Titan"
    assert any("Obsidian" in d for d in bundle.pinned_facts.important_decisions)
    assert "SUMMARY_LOADED" in caplog.text
    assert "PINNED_FACTS_LOADED" in caplog.text
    assert bundle.reference_resolution
    assert "Titan" in bundle.reference_resolution
    assert "Obsidian" in bundle.reference_resolution


def test_context_reconstruction_layers_and_prompt() -> None:
    builder = ConversationContextBuilder(max_recent_turns=6, summarize_threshold=50)
    messages = [
        _msg("user", "My project is Titan.", sequence=1),
        _msg("assistant", "OK, on avance sur Titan.", sequence=2),
        _msg("user", "We decided to use Obsidian.", sequence=3),
        _msg("assistant", "Noté — Obsidian comme outil de notes.", sequence=4),
    ]
    bundle = builder.build(
        messages,
        current_message="What should I do next?",
        active_project="Titan",
    )
    layers = bundle.prompt_layers()
    labels = [label for label, _ in layers]
    assert "CONVERSATION RÉCENTE" in labels
    assert "FAITS ÉPINGLÉS" in labels
    assert bundle.pinned_facts.active_project == "Titan"

    ctx = ThinkContext(
        user_message="What should I do next?",
        conversation_window=bundle.recent_lines,
        conversation_summary=bundle.summary or "Prior work on Titan continuity.",
        pinned_facts_text=bundle.pinned_facts.format_text(),
        reference_resolution=bundle.reference_resolution or "",
    )
    prompt = PromptBuilder().build(ctx)
    assert "CONVERSATION RÉCENTE" in prompt
    assert "FAITS ÉPINGLÉS" in prompt
    assert "Titan" in prompt
    assert "What should I do next?" in prompt


def test_project_continuity_across_followups() -> None:
    builder = ConversationContextBuilder(max_recent_turns=4, summarize_threshold=50)
    first = builder.build(
        [
            _msg("user", "My project is Titan.", sequence=1),
            _msg("assistant", "Parfait, Titan est le projet actif.", sequence=2),
        ],
        active_project="Titan",
    )
    second = builder.build(
        [
            _msg("user", "My project is Titan.", sequence=1),
            _msg("assistant", "Parfait, Titan est le projet actif.", sequence=2),
            _msg("user", "What should I do next?", sequence=3),
        ],
        existing_summary=first.summary,
        existing_pinned=first.pinned_facts,
        current_message="What should I do next?",
        active_project="Titan",
    )
    assert second.pinned_facts.active_project == "Titan"
    assert "Titan" in second.pinned_facts.format_text()
    # Follow-up should not require restating the project name in the question.
    assert "What should I do next?" not in (second.pinned_facts.active_project or "")


def test_reference_resolution_continue_and_do_that() -> None:
    builder = ConversationContextBuilder()
    pinned = PinnedFacts(
        active_project="Titan",
        important_decisions=["We decided to use Obsidian"],
        current_topic="Obsidian vault organization",
        unfinished_tasks=["Continue vault health review"],
    )
    for phrase in ("Continue.", "same as before", "again", "do that", "this project", "that strategy"):
        resolved = builder.resolve_reference(
            phrase,
            pinned_facts=pinned,
            summary="Discussed Obsidian for Titan notes.",
            recent_lines=["User : We decided to use Obsidian."],
        )
        assert resolved, f"expected resolution for {phrase!r}"
        assert "Titan" in resolved or "Obsidian" in resolved


def test_token_budget_truncates_oldest_recent(caplog: pytest.LogCaptureFixture) -> None:
    builder = ConversationContextBuilder(
        max_recent_turns=20,
        summarize_threshold=100,
        max_tokens=40,
    )
    messages = [
        _msg("user", "AAAA " * 40, sequence=1),
        _msg("assistant", "BBBB " * 40, sequence=2),
        _msg("user", "CCCC " * 40, sequence=3),
        _msg("assistant", "DDDD " * 40, sequence=4),
    ]
    with caplog.at_level(logging.INFO):
        bundle = builder.build(messages, conversation_id="conv_trim", request_id="req_trim")
    assert bundle.truncated
    assert "CONTEXT_TRUNCATED" in caplog.text
    assert bundle.estimated_tokens <= 40 + 5  # small slack for remaining stubs


def test_service_persists_intelligence_metadata(service: ConversationService) -> None:
    conv = service.create_conversation("Nolan", title="Intel")
    for i in range(12):
        service.persist_user_message(
            conversation_id=conv.id,
            user_id="Nolan",
            content=f"My project is Titan. Detail number {i} about the roadmap.",
            request_id=f"u{i}",
        )
        service._repo.add_message(
            conversation_id=conv.id,
            user_id="Nolan",
            role="assistant",
            content=f"Noted Titan detail {i}.",
            request_id=f"a{i}",
            status=MessageStatus.COMPLETED.value,
        )

    summary = service.load_history_for_hydration(
        conv.id,
        "Nolan",
        request_id="hydrate1",
        current_message="Continue.",
        active_project="Titan",
    )
    assert summary["pinned_facts"]["active_project"] == "Titan"
    assert summary.get("summary") or summary["context_message_count"] > 0

    refreshed = service._repo.get_conversation(conv.id, "Nolan")
    assert refreshed is not None
    intel = load_intelligence_metadata(refreshed.metadata)
    assert intel.get("pinned_facts", {}).get("active_project") == "Titan"

    engine = ConversationEngine(session_id="web", window_size=10, summarize_threshold=100)
    service.apply_history_to_engine(summary, engine, "Nolan")
    assert engine.get_pinned_facts_payload().get("active_project") == "Titan"
    if summary.get("summary"):
        assert engine._archived_summary  # noqa: SLF001 — intentional continuity check


def test_build_from_engine_reconstructs_continuity() -> None:
    engine = ConversationEngine(session_id="cli", window_size=10, summarize_threshold=100)
    engine.add_user_turn("Nolan", "My project is Titan.")
    engine.add_titan_turn("Understood — Titan is active.", user="Nolan")
    engine.add_user_turn("Nolan", "We decided to use Obsidian.")
    engine.add_titan_turn("OK, Obsidian for notes.", user="Nolan")
    engine.set_continuity_context(
        archived_summary="Earlier planning for Titan.",
        archived_turn_count=4,
        pinned_facts={"active_project": "Titan", "important_decisions": ["Obsidian"]},
    )

    bundle = ConversationContextBuilder().build_from_engine(
        engine,
        current_message="Continue.",
        active_project="Titan",
    )
    assert bundle.pinned_facts.active_project == "Titan"
    assert bundle.reference_resolution
    assert "Continue" not in (bundle.recent_lines[-1] if bundle.recent_lines else "")


def test_obsidian_not_used_as_conversation_memory_source() -> None:
    """Guard: builder must not import Obsidian / vault connectors as memory."""
    from pathlib import Path

    import core.web_conversations.context as ctx_mod

    source = Path(ctx_mod.__file__).read_text(encoding="utf-8")
    import_lines = [
        line
        for line in source.splitlines()
        if line.lstrip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines).lower()
    for name in (
        "tools.obsidian",
        "obsidian_tool",
        "obsidian_decision",
        "vault_analyzer",
        "connectors.markdown",
    ):
        assert name not in joined
    assert not any("obsidian" in key.lower() for key in dir(ctx_mod))
