# Titan Web App Conversations (Phase 12.1)

**Status:** Implemented in codebase — production durability requires Railway PostgreSQL + restart verification.

This document describes durable **conversation history** for the Titan Web App. It is **not** long-term Brain memory and **not** Obsidian.

---

## Architecture

| Layer | Role |
|-------|------|
| `core/web_conversations/` | Models, SQLAlchemy store, repository, context trim, titles |
| `api/conversation_routes.py` | Authenticated REST CRUD |
| `api/chat_service.py` | Persist + hydrate on each `/chat/stream` turn |
| `api/stream_service.py` | SSE lifecycle including `text_delta` |
| `web/v2/` | Conversation toolbar, restore, live token paint |

```
Browser (web/v2)
  → POST /chat/stream (SSE) + /api/conversations/*
       ↓
ConversationService (ownership-scoped)
       ↓
SQLAlchemy → PostgreSQL (Railway) or SQLite (local)
       ↓
Hydrate ConversationEngine → Brain / LLM stream
```

---

## Storage

- **Production:** `DATABASE_URL` / `TITAN_DATABASE_URL` → PostgreSQL (Railway plugin).
- **Local/tests:** SQLite file `data/conversations.db` when URL is empty.
- **Not used:** in-memory lists, browser localStorage (cache of active id only), Obsidian, ephemeral container files as source of truth.

### Schema

- `web_conversations` — id, user_id, title, timestamps, archived, metadata_json
- `web_messages` — id, conversation_id, role, content, request_id, status, error_code, sequence, optional model/provider
- `web_conversation_schema_migrations` — applied versions

IDs are non-guessable (`conv_` / `msg_` + `token_urlsafe`).

---

## Migrations

```powershell
cd C:\Users\nolan\OneDrive\Desktop\Titan
python scripts\migrate_web_conversations.py
```

Migrations are idempotent (`CREATE TABLE IF NOT EXISTS`). They never drop production tables.

Startup also calls `bootstrap_conversation_store()` when persistence is enabled.

---

## Ownership

Every endpoint resolves `user_id` from the authenticated session (`titan_username`). Repository queries always filter by `user_id`. Foreign conversation ids return 404 — never another user’s data.

---

## Context window

1. Load conversation messages.
2. Keep recent user/assistant turns (`TITAN_CONVERSATION_WINDOW`, default 10).
3. Trim oldest first under `TITAN_CONVERSATION_CONTEXT_MAX_TOKENS` and `TITAN_MAX_PROMPT_TOKENS`.
4. Hydrate `ConversationEngine` before Brain runs.
5. Fast path may include a clipped recent-history snippet; full Obsidian/memory dumps are not injected for simple chat.

---

## Streaming protocol (SSE on `/chat/stream`)

| Event | Meaning |
|-------|---------|
| `acknowledged` | Request accepted |
| `response_started` | First model output beginning |
| `text_delta` | Progressive text chunk (`data.text`) |
| `response_completed` | Successful finalize |
| `structured_error` | Failed turn |
| `cancelled` | User/server cancel |
| `conversation_finished` | Compatibility final payload (still emitted) |

Frontend creates one assistant placeholder, appends deltas at ≤24 UI updates/sec, and finalizes once. Typewriter is fallback only when no deltas arrive.

---

## Frontend lifecycle

- **New conversation** — `POST /api/conversations`, clear transcript, store id.
- **Refresh** — restore `titan_v2_conversation_id` + `GET /api/conversations/{id}`.
- **Logout** — clears local conversation session keys; server history remains.
- **Stop** — aborts fetch, `POST /api/chat/cancel`, marks generation abandoned (late deltas ignored).
- **Switch conversation** — interrupt active stream, hydrate selected history.

---

## Security

- All conversation routes require auth + CSRF for mutating methods.
- Parameterized SQL via SQLAlchemy.
- Message length capped by `TITAN_WEB_MAX_MESSAGE_LENGTH`.
- No API keys in browser/DB/logs; no chain-of-thought storage; system prompts not stored as user-visible messages.
- UI uses `textContent` for bubbles (XSS-safe).

---

## Observability (safe fields only)

`CONVERSATION_CREATED`, `CONVERSATION_LOADED`, `MESSAGE_PERSISTED`, `CHAT_STREAM_*`, `CONVERSATION_CONTEXT_BUILT`, `CHAT_FIRST_DELTA` — request_id, shortened conversation_id, user hash, char/token counts, durations. Never full message bodies.

---

## Local verification (PowerShell)

```powershell
cd C:\Users\nolan\OneDrive\Desktop\Titan
python -m pip install -r requirements.txt
# Optional explicit SQLite (default when DATABASE_URL empty):
# $env:TITAN_DATABASE_URL = ""
python scripts\migrate_web_conversations.py
$env:TITAN_WEB_ENABLED = "true"
$env:TITAN_WEB_DEV_MODE = "true"
python -m uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Then in the browser: log in → New conversation → send “Mon projet principal s’appelle Titan.” → “Comment s’appelle mon projet principal ?” → confirm “Titan” → confirm progressive tokens → refresh → second conversation → Stop → Retry → restart server and confirm history.

---

## Railway notes

Do not claim production persistence until PostgreSQL is attached, migrations applied, and a **restart** still shows history. See `docs/RAILWAY_DEPLOYMENT.md`.

---

## Known limitations

- Auth sessions remain in-memory (unchanged).
- Title LLM refine is optional/off by default on the hot path (heuristic title only).
- Multi-worker processes share DB history but not in-process Brain conversation windows (hydrated per request).
- Markdown is plain text in bubbles (safe); rich sanitized Markdown can be Step 12.2.
