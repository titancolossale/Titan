# =====================================
# Titan Web V2 Frontend Tests
# =====================================

"""Frontend integration tests for Web Runtime V1 (vanilla ES modules)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "web" / "v2"


def _node_available() -> bool:
    return shutil.which("node") is not None


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_parse_sse_buffer_module() -> None:
    script = """
import { parseSseBuffer } from './web/v2/core/backend-bridge.js';
const frame = 'event: conversation_finished\\ndata: {"response":"ok"}\\n\\n';
const { events, remainder } = parseSseBuffer(frame);
if (events.length !== 1) throw new Error('expected 1 event');
if (events[0].event !== 'conversation_finished') throw new Error('wrong event');
if (events[0].data.response !== 'ok') throw new Error('wrong payload');
if (remainder !== '') throw new Error('unexpected remainder');
console.log('ok');
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_conversation_session_module_exports() -> None:
    content = (V2 / "core" / "conversation-session.js").read_text(encoding="utf-8")
    assert "CONVERSATION_STORAGE_KEY" in content
    assert "getStoredConversationId" in content
    assert "createClientRequestId" in content


def test_backend_bridge_sends_conversation_id() -> None:
    content = (V2 / "core" / "backend-bridge.js").read_text(encoding="utf-8")
    assert "conversation_id" in content
    assert "request_id" in content
    assert "_submitting" in content
    assert "saveConversationId" in content


def test_conversation_manager_retry_support() -> None:
    content = (V2 / "conversation" / "conversation-manager.js").read_text(encoding="utf-8")
    assert "retryLast" in content
    assert "_lastFailedMessage" in content
    assert "tdl-v2-chat-retry" in content


def test_message_renderer_dev_metadata() -> None:
    content = (V2 / "conversation" / "message-renderer.js").read_text(encoding="utf-8")
    assert "attachDevMetadata" in content
    assert "showApprovalBanner" in content


def test_event_router_orchestration_handlers() -> None:
    content = (V2 / "core" / "event-router.js").read_text(encoding="utf-8")
    assert "orchestration_started" in content
    assert "approval_required" in content


def test_state_store_orchestration_fields() -> None:
    content = (V2 / "core" / "state-store.js").read_text(encoding="utf-8")
    for field in (
        "detectedIntent",
        "orchestrationConfidence",
        "approvalRequired",
        "conversationId",
    ):
        assert field in content


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_frontend_integration_parse_and_persist() -> None:
    """Simulate SSE finish frame → conversation id persistence helpers."""
    script = """
import { parseSseBuffer } from './web/v2/core/backend-bridge.js';
const payload = {
  response: 'Bonjour Nolan',
  conversation_id: 'conv-node-test',
  request_id: 'req-node-test',
  orchestration: { detected_intent: 'conversation', confidence: 0.9 },
};
const sse = `event: conversation_finished\\ndata: ${JSON.stringify(payload)}\\n\\n`;
const { events } = parseSseBuffer(sse);
const data = events[0].data;
if (data.response !== 'Bonjour Nolan') throw new Error('bad response');
if (data.conversation_id !== 'conv-node-test') throw new Error('bad conversation');
console.log(JSON.stringify({ ok: true, intent: data.orchestration.detected_intent }));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["intent"] == "conversation"
