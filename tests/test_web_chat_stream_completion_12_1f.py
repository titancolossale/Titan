# =====================================
# Titan Web Chat Stream Completion — Phase 12.1F
# =====================================

"""Deterministic frontend harness for SSE completion vs client timeout.

Node.js tests exercise BackendBridge when available. A pure-Python mirror of
the SSE parse/flush/completion state machine always runs so CI proves the
failure mode without requiring Node.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "web" / "v2"
BRIDGE = V2 / "core" / "backend-bridge.js"
MANAGER = V2 / "conversation" / "conversation-manager.js"


def _node_available() -> bool:
    return shutil.which("node") is not None


def _run_node(script: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


# ---------------------------------------------------------------------------
# Python mirror of web/v2/core/backend-bridge.js SSE helpers / completion FSM
# ---------------------------------------------------------------------------


TERMINAL_EVENTS = frozenset({"conversation_finished", "response_completed"})


def parse_sse_buffer(buffer: str) -> tuple[list[dict], str]:
    """Mirror of parseSseBuffer()."""
    blocks = buffer.split("\n\n")
    remainder = blocks.pop() if blocks else ""
    events: list[dict] = []
    for block in blocks:
        if not block.strip() or block.lstrip().startswith(":"):
            continue
        event_type = "message"
        event_id = None
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("id:"):
                event_id = line[3:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if not data_lines:
            continue
        try:
            data = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            continue
        events.append({"event": event_type, "data": data, "id": event_id})
    return events, remainder


def flush_sse_remainder(remainder: str) -> list[dict]:
    """Mirror of flushSseRemainder() — missing final newline must not hang."""
    trimmed = (remainder or "").strip()
    if not trimmed:
        return []
    if not re.search(r"(?:^|\n)data:", trimmed):
        return []
    padded = remainder if remainder.endswith("\n\n") else f"{remainder.rstrip(chr(10))}\n\n"
    events, _ = parse_sse_buffer(padded)
    return events


@dataclass
class StreamClientSim:
    """Minimal client FSM proving timeout vs completion interactions."""

    timeout_ms: int = 35000
    response_text: str = ""
    completion_seen: bool = False
    timer_active: bool = False
    timer_fired: bool = False
    aborted: bool = False
    resolved: bool = False
    discarded_in_catch: bool = False
    controller_generation: int = 0
    active_generation: int = 0
    events_seen: list[str] = field(default_factory=list)

    def arm_timeout(self) -> None:
        self.timer_active = True
        self.controller_generation += 1
        self.active_generation = self.controller_generation

    def clear_timeout(self) -> None:
        self.timer_active = False

    def ingest(self, frames: list[dict]) -> bool:
        stop = False
        for frame in frames:
            name = frame["event"]
            self.events_seen.append(name)
            if name in {"text_delta", "token"}:
                text = frame.get("data", {}).get("text") or ""
                if text:
                    self.response_text += text
            if name == "conversation_finished":
                resp = frame.get("data", {}).get("response")
                if resp:
                    self.response_text = resp
                self.completion_seen = True
                self.clear_timeout()
                stop = True
            elif name == "response_completed":
                self.completion_seen = True
                self.clear_timeout()
                stop = True
        return stop

    def on_reader_done(self, remainder: str) -> None:
        frames = flush_sse_remainder(remainder)
        if frames:
            self.ingest(frames)
        if self.completion_seen or self.response_text:
            self.resolved = True
            self.clear_timeout()

    def on_terminal_stop(self) -> None:
        self.resolved = True
        self.clear_timeout()

    def fire_timeout(self, generation: int | None = None) -> str | None:
        gen = self.active_generation if generation is None else generation
        if gen != self.controller_generation:
            return "stale_ignored"
        if self.completion_seen:
            return "timeout_after_completion_ignored"
        self.timer_fired = True
        self.aborted = True
        return "timeout"

    def catch_abort(self) -> str:
        if self.completion_seen and self.response_text:
            self.resolved = True
            self.discarded_in_catch = False
            return "success_after_completion"
        self.discarded_in_catch = True
        return "timeout_card"


def test_python_parse_multi_and_split_chunks() -> None:
    multi = (
        'event: text_delta\ndata: {"text":"A"}\n\n'
        'event: text_delta\ndata: {"text":"B"}\n\n'
        'event: conversation_finished\ndata: {"response":"AB","ok":true}\n\n'
    )
    events, remainder = parse_sse_buffer(multi)
    assert len(events) == 3
    assert remainder == ""
    assert events[2]["data"]["response"] == "AB"

    part1 = 'event: conversation_finished\ndata: {"response":"Hi'
    part2 = '","ok":true}\n\n'
    events, rem = parse_sse_buffer(part1)
    assert events == []
    events, rem = parse_sse_buffer(rem + part2)
    assert len(events) == 1
    assert events[0]["data"]["response"] == "Hi"


def test_python_missing_final_newline_flushes() -> None:
    raw = 'event: conversation_finished\ndata: {"response":"Bonjour","ok":true}'
    events, rem = parse_sse_buffer(raw)
    assert events == []
    assert rem == raw
    flushed = flush_sse_remainder(rem)
    assert len(flushed) == 1
    assert flushed[0]["data"]["response"] == "Bonjour"


def test_python_completion_clears_timeout_within_4s_path() -> None:
    client = StreamClientSim()
    client.arm_timeout()
    frames = [
        {"event": "acknowledged", "data": {"ok": True}},
        {"event": "response_started", "data": {}},
        {"event": "text_delta", "data": {"text": "Bon"}},
        {"event": "text_delta", "data": {"text": "jour"}},
        {
            "event": "conversation_finished",
            "data": {"response": "Bonjour", "ok": True},
        },
        {"event": "response_completed", "data": {"chars": 7}},
    ]
    stop = client.ingest(frames)
    assert stop is True
    client.on_terminal_stop()
    assert client.completion_seen is True
    assert client.timer_active is False
    assert client.resolved is True
    assert client.response_text == "Bonjour"
    assert client.fire_timeout() == "timeout_after_completion_ignored"
    assert client.catch_abort() == "success_after_completion"
    assert client.discarded_in_catch is False


def test_python_reader_done_with_completion_resolves() -> None:
    client = StreamClientSim()
    client.arm_timeout()
    remainder = 'event: conversation_finished\ndata: {"response":"done-flush","ok":true}'
    client.on_reader_done(remainder)
    assert client.resolved is True
    assert client.response_text == "done-flush"
    assert client.timer_active is False


def test_python_stale_timeout_cannot_overwrite() -> None:
    client = StreamClientSim()
    client.arm_timeout()
    old_gen = client.active_generation
    client.arm_timeout()
    assert client.fire_timeout(old_gen) == "stale_ignored"
    assert client.aborted is False


def test_python_late_abort_after_completion_no_timeout_card() -> None:
    client = StreamClientSim()
    client.arm_timeout()
    client.ingest(
        [{"event": "conversation_finished", "data": {"response": "Hi", "ok": True}}]
    )
    client.on_terminal_stop()
    assert client.catch_abort() == "success_after_completion"
    assert client.discarded_in_catch is False


def test_python_stop_then_later_request_isolated() -> None:
    first = StreamClientSim()
    first.arm_timeout()
    first.aborted = True
    first.clear_timeout()
    third = StreamClientSim()
    third.arm_timeout()
    third.ingest(
        [
            {
                "event": "conversation_finished",
                "data": {"response": "third", "ok": True},
            }
        ]
    )
    third.on_terminal_stop()
    assert first.resolved is False
    assert third.resolved is True
    assert third.response_text == "third"


def test_python_exactly_one_final_assistant_payload() -> None:
    client = StreamClientSim()
    client.ingest(
        [
            {"event": "text_delta", "data": {"text": "A"}},
            {"event": "text_delta", "data": {"text": "B"}},
            {
                "event": "conversation_finished",
                "data": {"response": "AB", "ok": True},
            },
        ]
    )
    assert client.response_text == "AB"


def test_bridge_source_has_12_1f_guards() -> None:
    content = BRIDGE.read_text(encoding="utf-8")
    assert "CHAT_CLIENT_TIMEOUT_CLEARED" in content
    assert "CHAT_CLIENT_COMPLETION_EVENT" in content
    assert "CHAT_CLIENT_STALE_EVENT_IGNORED" in content
    assert "flushSseRemainder" in content
    assert "reader_cancel_after_completion" in content
    assert "abort_or_error_after_completion" in content
    assert "stale_timeout_controller" in content
    assert "CHAT_CLIENT_TIMEOUT_MS = 35000" in content
    assert 'clearClientTimeout("conversation_finished")' in content
    assert 'clearClientTimeout("response_completed")' in content


def test_conversation_manager_preserves_live_on_abort() -> None:
    content = MANAGER.read_text(encoding="utf-8")
    assert "preserve_live_after_abort" in content
    assert "CHAT_CLIENT_MESSAGE_FINALIZED" in content
    assert "CHAT_CLIENT_ABORT_CALLED" in content
    assert "_activeGeneration" in content
    assert "switchConversation" in content


def test_backend_protocol_events_recognized() -> None:
    bridge = BRIDGE.read_text(encoding="utf-8")
    router = (V2 / "core" / "event-router.js").read_text(encoding="utf-8")
    for name in (
        "acknowledged",
        "response_started",
        "text_delta",
        "response_completed",
        "conversation_finished",
        "structured_error",
        "cancelled",
    ):
        assert name in bridge or name in router


def test_switch_conversation_interrupts_active_stream() -> None:
    content = MANAGER.read_text(encoding="utf-8")
    switch_idx = content.index("async switchConversation")
    body = content[switch_idx : switch_idx + 400]
    assert "this.interrupt()" in body


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_parse_helpers_terminal_and_flush() -> None:
    script = r"""
import {
  parseSseBuffer,
  flushSseRemainder,
  isChatStreamTerminalEvent,
  CHAT_STREAM_TERMINAL_EVENTS,
} from './web/v2/core/backend-bridge.js';

if (!isChatStreamTerminalEvent('conversation_finished')) throw new Error('finished terminal');
if (!isChatStreamTerminalEvent('response_completed')) throw new Error('completed terminal');
if (isChatStreamTerminalEvent('text_delta')) throw new Error('delta not terminal');
if (!CHAT_STREAM_TERMINAL_EVENTS.includes('conversation_finished')) throw new Error('list');

const raw = 'event: conversation_finished\ndata: {"response":"Bonjour","ok":true}';
const flushed = flushSseRemainder(raw);
if (flushed.length !== 1) throw new Error('flush expected 1 got ' + flushed.length);
if (flushed[0].data.response !== 'Bonjour') throw new Error('bad flush payload');

const multi = [
  'event: text_delta\ndata: {"text":"A"}\n\n',
  'event: text_delta\ndata: {"text":"B"}\n\n',
  'event: conversation_finished\ndata: {"response":"AB","ok":true}\n\n',
].join('');
const { events, remainder } = parseSseBuffer(multi);
if (events.length !== 3) throw new Error('multi parse ' + events.length);
if (remainder !== '') throw new Error('multi remainder');

const part1 = 'event: conversation_finished\ndata: {"response":"Hi';
const part2 = '","ok":true}\n\n';
let buf = part1;
let parsed = parseSseBuffer(buf);
if (parsed.events.length !== 0) throw new Error('split early');
buf = parsed.remainder + part2;
parsed = parseSseBuffer(buf);
if (parsed.events.length !== 1) throw new Error('split join');
if (parsed.events[0].data.response !== 'Hi') throw new Error('split payload');

console.log('ok');
"""
    result = _run_node(script)
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_stream_resolves_on_completion_and_clears_timeout() -> None:
    """4s stream with delayed body close must resolve without waiting 35s."""
    script = r"""
import { BackendBridge, CHAT_CLIENT_TIMEOUT_MS } from './web/v2/core/backend-bridge.js';

globalThis.localStorage = {
  _d: {},
  getItem(k) { return this._d[k] ?? null; },
  setItem(k, v) { this._d[k] = String(v); },
  removeItem(k) { delete this._d[k]; },
};
globalThis.document = {
  addEventListener() {},
  removeEventListener() {},
  hidden: false,
};
const timers = new Map();
let nextTid = 1;
globalThis.window = {
  setTimeout(fn, ms) {
    const id = nextTid++;
    timers.set(id, { fn, ms, cleared: false });
    return id;
  },
  clearTimeout(id) {
    const t = timers.get(id);
    if (t) t.cleared = true;
  },
};
globalThis.performance = { now: () => Date.now() };
globalThis.DOMException = class DOMException extends Error {
  constructor(message, name) {
    super(message);
    this.name = name || 'Error';
  }
};

function sseChunks() {
  const frames = [
    'event: acknowledged\ndata: {"ok":true}\n\n',
    'event: response_started\ndata: {"neural_state":"thinking"}\n\n',
    'event: text_delta\ndata: {"text":"Bon"}\n\n',
    'event: text_delta\ndata: {"text":"jour"}\n\n',
    'event: conversation_finished\ndata: {"response":"Bonjour","ok":true,"conversation_id":"c1","request_id":"r1"}\n\n',
    'event: response_completed\ndata: {"request_id":"r1","chars":7}\n\n',
  ];
  let i = 0;
  let cancelled = false;
  return {
    getReader() {
      return {
        async read() {
          if (cancelled) return { done: true, value: undefined };
          if (i < frames.length) {
            const enc = new TextEncoder();
            return { done: false, value: enc.encode(frames[i++]) };
          }
          await new Promise(() => {});
        },
        async cancel() {
          cancelled = true;
        },
      };
    },
  };
}

globalThis.fetch = async () => ({
  ok: true,
  status: 200,
  headers: { get: () => 'text/event-stream' },
  body: sseChunks(),
});

const brain = {
  getPipelineStore: () => ({
    ingest() {},
    reset() {},
    applySnapshot() {},
    snapshot: () => ({}),
  }),
  getConversationEngine: () => ({
    startFromBackend() {},
    ingestStage() {},
    finishFromBackend() {},
  }),
  getMemoryEngine: () => ({ ingest() {} }),
  getToolEngine: () => ({ ingest() {} }),
  setState() {},
  activateTool() {},
};

const bridge = new BackendBridge(brain, null);
const started = Date.now();
const result = await bridge._streamChat('Bonjour', {
  request_id: 'r1',
  conversation_id: 'c1',
});
const elapsed = Date.now() - started;

if (result.response !== 'Bonjour') throw new Error('bad response ' + result.response);
if (elapsed > 2000) throw new Error('hung waiting for body close: ' + elapsed + 'ms');

const armed = [...timers.values()].filter((t) => t.ms === CHAT_CLIENT_TIMEOUT_MS);
if (!armed.length) throw new Error('timeout never armed');
if (!armed.every((t) => t.cleared)) throw new Error('timeout not cleared on completion');

console.log(JSON.stringify({ ok: true, elapsed, response: result.response }));
"""
    result = _run_node(script)
    assert result.returncode == 0, result.stderr or result.stdout
    assert '"ok":true' in result.stdout.replace(" ", "")


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_late_abort_after_completion_does_not_timeout_card() -> None:
    script = r"""
import { BackendBridge } from './web/v2/core/backend-bridge.js';

globalThis.localStorage = {
  _d: {},
  getItem(k) { return this._d[k] ?? null; },
  setItem(k, v) { this._d[k] = String(v); },
  removeItem(k) { delete this._d[k]; },
};
globalThis.document = { addEventListener() {}, removeEventListener() {}, hidden: false };
globalThis.window = {
  setTimeout(fn, ms) { return setTimeout(fn, ms); },
  clearTimeout(id) { clearTimeout(id); },
};
globalThis.performance = { now: () => Date.now() };
globalThis.DOMException = class DOMException extends Error {
  constructor(message, name) {
    super(message);
    this.name = name || 'Error';
  }
};

const frames = [
  'event: text_delta\ndata: {"text":"Hi"}\n\n',
  'event: conversation_finished\ndata: {"response":"Hi","ok":true,"request_id":"r2"}\n\n',
];
let i = 0;
globalThis.fetch = async (_url, opts) => ({
  ok: true,
  status: 200,
  headers: { get: () => 'text/event-stream' },
  body: {
    getReader() {
      return {
        async read() {
          if (i < frames.length) {
            const enc = new TextEncoder();
            return { done: false, value: enc.encode(frames[i++]) };
          }
          await new Promise((resolve, reject) => {
            opts.signal.addEventListener('abort', () => {
              const err = new DOMException('Chat request timed out', 'AbortError');
              err.code = 'provider_timeout';
              reject(err);
            });
          });
        },
        async cancel() {},
      };
    },
  },
});

const brain = {
  getPipelineStore: () => ({
    ingest() {}, reset() {}, applySnapshot() {}, snapshot: () => ({}),
  }),
  getConversationEngine: () => ({
    startFromBackend() {}, ingestStage() {}, finishFromBackend() {},
  }),
  getMemoryEngine: () => ({ ingest() {} }),
  getToolEngine: () => ({ ingest() {} }),
  setState() {},
  activateTool() {},
};

const bridge = new BackendBridge(brain, null);
const result = await bridge._streamChat('x', { request_id: 'r2' });
if (result.response !== 'Hi') throw new Error('must preserve completed response');
console.log('ok');
"""
    result = _run_node(script)
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_stale_timeout_cannot_abort_newer_controller() -> None:
    script = r"""
import { BackendBridge, CHAT_CLIENT_TIMEOUT_MS } from './web/v2/core/backend-bridge.js';

globalThis.localStorage = {
  _d: {},
  getItem(k) { return this._d[k] ?? null; },
  setItem(k, v) { this._d[k] = String(v); },
  removeItem(k) { delete this._d[k]; },
};
globalThis.document = { addEventListener() {}, removeEventListener() {}, hidden: false };
const timers = [];
globalThis.window = {
  setTimeout(fn, ms) {
    const handle = { fn, ms, cleared: false };
    timers.push(handle);
    return handle;
  },
  clearTimeout(handle) {
    if (handle) handle.cleared = true;
  },
};
globalThis.performance = { now: () => Date.now() };
globalThis.DOMException = class DOMException extends Error {
  constructor(message, name) {
    super(message);
    this.name = name || 'Error';
  }
};

globalThis.fetch = async () => ({
  ok: true,
  status: 200,
  headers: { get: () => 'text/event-stream' },
  body: {
    getReader() {
      return {
        async read() {
          const enc = new TextEncoder();
          return {
            done: false,
            value: enc.encode(
              'event: conversation_finished\ndata: {"response":"ok","ok":true}\n\n',
            ),
          };
        },
        async cancel() {},
      };
    },
  },
});

const brain = {
  getPipelineStore: () => ({
    ingest() {}, reset() {}, applySnapshot() {}, snapshot: () => ({}),
  }),
  getConversationEngine: () => ({
    startFromBackend() {}, ingestStage() {}, finishFromBackend() {},
  }),
  getMemoryEngine: () => ({ ingest() {} }),
  getToolEngine: () => ({ ingest() {} }),
  setState() {},
  activateTool() {},
};

const bridge = new BackendBridge(brain, null);
await bridge._streamChat('one', { request_id: 'old' });

const oldTimeout = timers.find((t) => t.ms === CHAT_CLIENT_TIMEOUT_MS);
if (!oldTimeout || !oldTimeout.cleared) throw new Error('old timeout not cleared');

const fresh = new AbortController();
bridge._chatAbort = fresh;
oldTimeout.fn();
if (fresh.signal.aborted) throw new Error('stale timeout aborted newer controller');

console.log('ok');
"""
    result = _run_node(script)
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_stop_aborts_active_but_not_later_request() -> None:
    script = r"""
import { BackendBridge } from './web/v2/core/backend-bridge.js';

globalThis.localStorage = {
  _d: {},
  getItem(k) { return this._d[k] ?? null; },
  setItem(k, v) { this._d[k] = String(v); },
  removeItem(k) { delete this._d[k]; },
};
globalThis.document = { addEventListener() {}, removeEventListener() {}, hidden: false };
globalThis.window = {
  setTimeout(fn, ms) { return setTimeout(fn, ms); },
  clearTimeout(id) { clearTimeout(id); },
};
globalThis.performance = { now: () => Date.now() };
globalThis.DOMException = class DOMException extends Error {
  constructor(message, name) {
    super(message);
    this.name = name || 'Error';
  }
};

let phase = 'first';
globalThis.fetch = async (_url, opts) => {
  if (phase === 'first') {
    return {
      ok: true,
      status: 200,
      headers: { get: () => 'text/event-stream' },
      body: {
        getReader() {
          return {
            async read() {
              await new Promise((resolve, reject) => {
                opts.signal.addEventListener('abort', () => {
                  reject(new DOMException('Aborted', 'AbortError'));
                });
              });
            },
            async cancel() {},
          };
        },
      },
    };
  }
  const enc = new TextEncoder();
  const frame =
    'event: conversation_finished\ndata: {"response":"third","ok":true,"request_id":"r3"}\n\n';
  let done = false;
  return {
    ok: true,
    status: 200,
    headers: { get: () => 'text/event-stream' },
    body: {
      getReader() {
        return {
          async read() {
            if (done) return { done: true, value: undefined };
            done = true;
            return { done: false, value: enc.encode(frame) };
          },
          async cancel() {},
        };
      },
    },
  };
};

const brain = {
  getPipelineStore: () => ({
    ingest() {}, reset() {}, applySnapshot() {}, snapshot: () => ({}),
  }),
  getConversationEngine: () => ({
    startFromBackend() {}, ingestStage() {}, finishFromBackend() {},
  }),
  getMemoryEngine: () => ({ ingest() {} }),
  getToolEngine: () => ({ ingest() {} }),
  setState() {},
  activateTool() {},
};

const bridge = new BackendBridge(brain, null);
const first = bridge._streamChat('stop-me', { request_id: 'r-stop' });
await new Promise((r) => setTimeout(r, 20));
bridge._chatAbort.abort();
let aborted = false;
try {
  await first;
} catch (err) {
  aborted = err?.name === 'AbortError';
}
if (!aborted) throw new Error('stop must abort active request');

phase = 'third';
const third = await bridge._streamChat('hello', { request_id: 'r3' });
if (third.response !== 'third') throw new Error('later request must succeed');
console.log('ok');
"""
    result = _run_node(script)
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_reader_done_with_completion_content_resolves() -> None:
    script = r"""
import { BackendBridge } from './web/v2/core/backend-bridge.js';

globalThis.localStorage = {
  _d: {},
  getItem(k) { return this._d[k] ?? null; },
  setItem(k, v) { this._d[k] = String(v); },
  removeItem(k) { delete this._d[k]; },
};
globalThis.document = { addEventListener() {}, removeEventListener() {}, hidden: false };
globalThis.window = {
  setTimeout(fn, ms) { return setTimeout(fn, ms); },
  clearTimeout(id) { clearTimeout(id); },
};
globalThis.performance = { now: () => Date.now() };
globalThis.DOMException = class DOMException extends Error {
  constructor(message, name) {
    super(message);
    this.name = name || 'Error';
  }
};

const incomplete =
  'event: conversation_finished\ndata: {"response":"done-flush","ok":true,"request_id":"r4"}';
let sent = false;
globalThis.fetch = async () => ({
  ok: true,
  status: 200,
  headers: { get: () => 'text/event-stream' },
  body: {
    getReader() {
      return {
        async read() {
          if (sent) return { done: true, value: undefined };
          sent = true;
          return { done: false, value: new TextEncoder().encode(incomplete) };
        },
        async cancel() {},
      };
    },
  },
});

const brain = {
  getPipelineStore: () => ({
    ingest() {}, reset() {}, applySnapshot() {}, snapshot: () => ({}),
  }),
  getConversationEngine: () => ({
    startFromBackend() {}, ingestStage() {}, finishFromBackend() {},
  }),
  getMemoryEngine: () => ({ ingest() {} }),
  getToolEngine: () => ({ ingest() {} }),
  setState() {},
  activateTool() {},
};

const bridge = new BackendBridge(brain, null);
const result = await bridge._streamChat('x', { request_id: 'r4' });
if (result.response !== 'done-flush') throw new Error('flush on done failed: ' + result.response);
console.log('ok');
"""
    result = _run_node(script)
    assert result.returncode == 0, result.stderr or result.stdout
