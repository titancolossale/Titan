# Titan Web App ↔ Brain Integration (Phase 11.1)

**Version:** 0.44.0  
**Last updated:** July 16, 2026

This document describes the **production end-to-end chat path** from the approved Web App (`web/v2` at `/app/`) through the FastAPI layer into Titan’s real Brain.

---

## Architecture flow

```
User (authenticated session)
  → web/v2 composer (ConversationManager.send)
  → BackendBridge._streamChat
  → POST /chat/stream  (primary UI path, SSE)
     optional: POST /api/chat  (Phase 11.1 sync contract)
  → require_web_auth + session/CSRF
  → api.chat_service.process_chat_message()
  → Titan singleton (api.titan_service.get_titan)
  → Brain.process_request()
       → NaturalLanguageOrchestrator
       → conversation/question → Brain.think() pipeline
            (context, memory retrieval, planning, tools, LLM)
  → structured payload + honest runtime
  → SSE conversation_finished / JSON response
  → MessageRenderer (textContent, pre-wrap)
```

**CLI vs Web:** `python main.py` REPL calls `Brain.think()` directly.  
Web chat always enters via `Brain.process_request()`.

---

## Endpoint contract

### Primary UI path — `POST /chat/stream` (SSE)

Request body:

```json
{
  "message": "user text",
  "conversation_id": "optional",
  "request_id": "unique client id",
  "client_request_id": "alias of request_id",
  "user": "Nolan",
  "client_metadata": { "source": "web-v2" }
}
```

Terminal event `conversation_finished` includes `response`, `runtime`, `ok`, `message_id`, activity arrays.

### Sync contract — `POST /api/chat`

Success (`200`):

```json
{
  "ok": true,
  "conversation_id": "…",
  "message_id": "msg-…",
  "request_id": "…",
  "response": "…",
  "runtime": {
    "state": "finished",
    "stages": ["receiving", "understanding", "generating", "finished"],
    "memory_used": false,
    "tools_used": [],
    "model": "gpt-5.2",
    "duration_ms": 120
  }
}
```

Error (`400` / `500` / `503`):

```json
{
  "ok": false,
  "error": {
    "code": "provider_unavailable",
    "message": "Titan ne peut pas joindre son modèle pour le moment.",
    "retryable": true
  },
  "request_id": "…",
  "conversation_id": "…",
  "runtime": { "state": "error", "stages": ["error"] }
}
```

### Legacy (still supported)

| Route | Role |
|-------|------|
| `POST /api/chat/message` | Web Runtime V1 sync JSON (additive `ok` / `runtime`) |
| `POST /chat` | Legacy sync subset |

---

## Authentication behavior

- Chat routes require authenticated production session (or bearer when session auth is off).
- Session mode: cookie + CSRF (`X-CSRF-Token`) on mutating requests.
- Mid-session `401` on chat → frontend `redirectToLogin()` → `/login?next=…`.
- `/health` and `/ready` remain public.
- Secrets never returned to the client.

---

## Runtime telemetry rules

Honest operational stages only:

| Stage | When shown |
|-------|------------|
| `receiving` | Request accepted |
| `understanding` | Intent / NLO understanding ran |
| `retrieving_memory` | Memory retrieval returned matches |
| `planning` | Real planning progress events |
| `selecting_tools` / `executing_tools` | Tools actually executed |
| `generating` | Response generation |
| `finished` | Successful completion |
| `error` | Provider / Brain failure |

Rules:

- Never show a stage that did not happen.
- Never claim tool use unless a tool executed.
- Never claim memory use unless retrieval returned context.
- Idle UI may show presentation catalogs; they are not execution claims.
- No private chain-of-thought — only safe summaries (`reasoning_summary`).

---

## Provider configuration

| Variable | Role |
|----------|------|
| `OPENAI_API_KEY` | Railway Variables only — never frontend |
| `TITAN_LLM_MODEL` | Default `gpt-5.2` |
| `TITAN_LLM_MODEL_*` | Classification / agent / evaluation routing |
| `TITAN_WEB_MAX_MESSAGE_LENGTH` | Default `16000` |

Provider failures: bounded retries in `brain/llm.py` (max 2), then structured `provider_unavailable` (retryable).

---

## Error codes

| Code | HTTP | Retryable | Meaning |
|------|------|-----------|---------|
| `invalid_request` | 400 | no | Empty / invalid message |
| `provider_unavailable` | 503 | yes | LLM unreachable |
| `brain_failure` | 500 | yes | Orchestration exception |
| `internal_error` | 500 | yes | Unexpected API failure |
| `session_expired` | 401 | no | Auth required / expired |

Duplicate `client_request_id` / `request_id`: idempotent replay of the first successful payload (no second Brain call).

---

## Local testing

```powershell
# From repo root, with .env containing OPENAI_API_KEY
$env:TITAN_WEB_ENABLED = "true"
$env:TITAN_WEB_DEV_MODE = "true"   # optional local auth bypass
python main.py web-dev
```

| URL | Purpose |
|-----|---------|
| http://127.0.0.1:8000/login | Login (when session auth configured) |
| http://127.0.0.1:8000/app/ | Canonical Web App |
| http://127.0.0.1:8000/health | Liveness |
| http://127.0.0.1:8000/ready | Readiness |

Test message:

> Titan, confirme que le chat Web App est connecté à ton cerveau et indique seulement les systèmes réellement actifs.

Expected: real Brain French reply; thinking indicator; honest telemetry (no fake tools).

Automated:

```powershell
pytest tests/test_web_brain_integration.py tests/test_web_runtime.py -v
```

---

## Railway testing

Required variables (among existing auth/deploy vars):

- `OPENAI_API_KEY`
- `TITAN_WEB_ENABLED=true`
- `TITAN_APP_ENV=production`
- Auth: `TITAN_AUTH_USERNAME`, `TITAN_AUTH_PASSWORD_HASH`, …
- `PORT` (Railway injects; Titan binds 8080 when provided)

Deploy (do **not** push unless you intend to):

```powershell
git status
git add api/chat_models.py api/chat_service.py api/app.py api/stream_service.py `
  web/v2/core/backend-bridge.js web/v2/core/web-auth.js web/v2/core/state-store.js `
  web/v2/conversation/conversation-manager.js web/v2/conversation/message-renderer.js `
  web/v2/design/ui.css web/v2/design/premium.css `
  tests/test_web_brain_integration.py docs/WEB_APP_BRAIN_INTEGRATION.md
git commit -m "Connect production Web App chat to real Brain with honest runtime telemetry."
git push
```

After redeploy:

1. Open `https://<your-railway-domain>/login`
2. Sign in → land on `/app/`
3. Send the test message above once
4. Confirm one user bubble, thinking state, one Titan reply
5. Confirm telemetry does not invent tools/memory
6. Refresh → send a second message
7. On forced logout / expired session → redirect to `/login`

---

## Known limitations (honest)

| Area | Status |
|------|--------|
| Memory retrieval | Wired in `Brain.think()` for conversation intents |
| Tools | Wired via think pipeline / NLO tool intents; confirmation gates enforced |
| Obsidian on Railway | Not available (no local vault) |
| LLM token streaming | Not in V1 — full response then typewriter UI |
| Conversation history REST | Not yet — in-process + client `conversation_id` |
| Approval submit API | Banner only; submit endpoint deferred |
| Voice / Trading / Gmail | Not part of Step 11.1 chat path |

---

## Next recommended step (11.2)

**Persistent conversation continuity + streaming tokens**

- Durable conversation history API keyed by `conversation_id`
- Optional true token SSE from the LLM gateway
- Approval action endpoint for gated tool/patch flows
- Production smoke checklist automated against Railway staging

---

## Related docs

- `docs/WEB_RUNTIME.md` — Web Runtime V1 architecture
- `docs/TITAN_PRIVATE_AUTHENTICATION.md` — session auth
- `docs/RAILWAY_DEPLOYMENT.md` — deploy / health
