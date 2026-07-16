# Titan Web Runtime V1

**Version:** 0.36.0  
**Last updated:** July 10, 2026

This document describes the **production web architecture** for Titan — how `web/v2/` connects to the shared Brain through the existing FastAPI Web API.

---

## Canonical architecture

| Layer | Path | Role |
|-------|------|------|
| **Production frontend** | `web/v2/` at `/app/` | **Canonical** approved final Titan Web App |
| **Legacy frontend** | `web/static/` under `/static/` | **Deprecated** — V1 reference UI; `/` redirects to `/app/` |
| **Web API** | `api/app.py` | FastAPI routes, auth, SSE |
| **Chat service** | `api/chat_service.py` | Thread-safe `Brain.process_request()` delegation |
| **Shared runtime** | `api/titan_service.py` | Lazy singleton `Titan` (same composition root as REPL) |
| **Brain front door** | `brain/brain.py` → `process_request()` | Natural Language Orchestrator routing |

```
web/v2 (BackendBridge)
  → POST /chat/stream  (SSE, primary UI path)
  → POST /api/chat/message  (sync JSON, canonical API)
  → GET /events/stream  (persistent status hub)
       ↓
api/chat_service.process_chat_message()
       ↓
get_titan()  — single shared Titan / Brain instance
       ↓
Brain.process_request(message, stream=?)
       ↓
NaturalLanguageOrchestrator
       ↓
existing Brain systems + tools
       ↓
structured API / SSE response
       ↓
web/v2 conversation interface
```

---

## Canonical API route

### `POST /api/chat` (Phase 11.1 production contract)

Authenticated sync chat with `{ ok, message_id, response, runtime }`.  
See `docs/WEB_APP_BRAIN_INTEGRATION.md` for the full contract, error codes, and Railway verification.

### `POST /api/chat/message` (authenticated)

**Request body:**

```json
{
  "message": "Explique le module Brain",
  "conversation_id": "optional-client-id",
  "request_id": "optional-client-id",
  "user": "Nolan",
  "client_metadata": { "source": "web-v2" }
}
```

**Response (user-safe):**

```json
{
  "request_id": "…",
  "conversation_id": "…",
  "response": "…",
  "user": "Nolan",
  "detected_intent": "conversation",
  "confidence": 0.92,
  "systems_used": { "planned": [], "invoked": ["brain_think"], "skipped": [] },
  "pipeline_summary": { "intent": "conversation", "systems": {}, "artifacts_summary": {} },
  "reasoning_summary": "…",
  "brain_state": "completed",
  "execution_status": "completed",
  "approval_required": false,
  "approval_id": null,
  "approval_summary": null,
  "warnings": [],
  "errors": [],
  "tool_activity": [],
  "memory_activity": [],
  "orchestrator_progress": [],
  "duration_seconds": 0.05,
  "timestamp": "2026-07-10T…"
}
```

**Legacy routes (still supported, same Brain path):**

- `POST /chat` — sync JSON (subset of fields + activity arrays)
- `POST /chat/stream` — SSE cognitive + orchestration events

---

## Shared Brain lifecycle

- **One** `Titan` instance per web server process (`api/titan_service.get_titan()`).
- Lazy initialization on first request; status set to `ONLINE`.
- `threading.Lock` in `api/chat_service.py` serializes `process_request()` access.
- No per-request Brain reconstruction; no duplicate tool registration.
- `set_titan()` / `reset_titan()` are **test-only**.

---

## Authentication

- Bearer token: `TITAN_WEB_SECRET_KEY` (shared secret).
- `GET /auth/status` — public policy probe.
- `POST /auth/verify` — validates token.
- Dev bypass: `TITAN_WEB_DEV_MODE=true` (`python main.py web-dev`).
- SSE hub: `GET /events/stream?token=…` (EventSource cannot set headers).
- User field (`Nolan` / `Ibrahim`) is **context switching**, not cryptographic auth.

---

## Session handling

- `conversation_id` is echoed from the client or defaults to `context.session.session_id`.
- Client persistence: `web/v2/core/conversation-session.js` (`localStorage`).
- Conversation turns recorded via existing `Conversation` / `ConversationEngine` — the web layer is **not** a second memory system.
- No REST history API in V1; persistence uses in-process conversation engine (optional disk via `TITAN_CONVERSATION_PERSIST`).

---

## Streaming (V1)

- **Production path:** `POST /chat/stream` — SSE stage events + orchestration metadata.
- **Persistent hub:** `GET /events/stream` — status, brain_state, telemetry.
- Conversation intents forward `CognitiveStreamEmitter` into `think()` via NLO.
- Non-conversation intents emit synthetic orchestration stages.
- **Not in V1:** LLM token streaming, WebSocket (see Web Runtime V2).

---

## Approval behavior

When `Brain.process_request()` produces an unapproved patch or tool confirmation:

- `approval_required: true` in API / SSE `conversation_finished`
- `approval_id` preserved for a future approval endpoint
- UI shows `approval_required` banner — **never silent execution**
- Actual approval submission: **Web Runtime V2** (unless an existing safe route is wired)

---

## Error behavior

| Case | HTTP | User message |
|------|------|--------------|
| Missing/invalid auth | 401 | Standard FastAPI auth |
| Secret not configured | 503 | Auth unavailable |
| Empty / oversized message | 400 / 422 | Validation error |
| Brain failure | 500 / graceful French fallback | No stack traces |
| Stream failure | SSE `error` event | Sanitized code + message |

Secrets, env vars, and filesystem paths are never returned.

---

## Frontend integration (web/v2)

Reused components (no parallel chat UI):

| Module | Role |
|--------|------|
| `core/backend-bridge.js` | SSE chat, conversation id, duplicate-submit guard |
| `conversation/conversation-manager.js` | Send, thinking state, retry, approval |
| `conversation/message-renderer.js` | Messages, dev metadata, approval banner |
| `core/event-router.js` | Orchestration + approval SSE routing |
| `core/state-store.js` | Orchestration metadata fields |
| `core/conversation-session.js` | `conversation_id` persistence |
| `composer/composer-region.js` | Input + send/stop |
| `orchestrator/orchestrator-region.js` | Pipeline timeline |

Dev metadata: enable with `localStorage.titan_v2_dev_metadata = "true"`.

---

## Legacy `web/static/`

**Deprecated.** Served at `/` for reference only. All new work targets `web/v2/` at `/v2/`.

---

## Local startup

```bash
# Development (auth bypass, localhost)
python main.py web-dev

# Production local (requires .env)
# TITAN_WEB_ENABLED=true
# TITAN_WEB_SECRET_KEY=your-secret
python main.py web
```

Open: **http://127.0.0.1:8000/v2/**

---

## Tests

```bash
pytest tests/test_web_runtime.py tests/test_web_v2_frontend.py tests/test_web_api.py -v
```

---

## Web Runtime V2 roadmap

- Approval submission endpoint wired to Permission Manager
- Conversation history REST API
- LLM token streaming (optional)
- WebSocket alternative to SSE (only if justified)
- Per-user session tokens (beyond shared secret)
- Connection status telemetry wired in status region

---

## Related documents

- `docs/ARCHITECTURE.md` — full execution path
- `docs/NATURAL_LANGUAGE_ORCHESTRATOR.md` — NLO routing
- `CHANGELOG.md` — release notes
