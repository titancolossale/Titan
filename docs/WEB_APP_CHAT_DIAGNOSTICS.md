# Web App Chat Diagnostics — Phase 11.1B + 11.P2

## Previous failure symptoms

On Railway production (multiple computers):

- Titan Web App felt very slow / frozen after submit
- User message did not appear in the conversation panel (fixed in 11.1B)
- Composer did not clearly confirm send (fixed in 11.1B)
- No Titan response appeared / “Titan réfléchit…” stayed indefinitely
- No useful recoverable error was shown
- UI remained visually overloaded (~20 FPS) while waiting (addressed in 11.P2)

## Root cause (ranked)

1. **Primary (11.1B) — frontend message container race**  
   `ConversationManager.bindDom()` ran before the chat panel was mounted.  
   Fixed with lazy `ensureContainer()` + bind-after-navigate.

2. **Secondary (11.P2) — renderer overload during wait**  
   Thinking / pending chat previously increased decorative neural work.  
   Fixed: Auto/Emergency budgets, static cache, thinking lighten, visual Hz cap.

3. **Contributing — provider / Brain latency**  
   OpenAI calls can take tens of seconds. UI must show elapsed feedback and timeout cleanly.

4. **Contributing — incomplete server timing trail**  
   Hard to see whether a hang was before Brain, inside Brain, or in the provider.

## Exact frontend / backend path

```
Composer Enter/click
  → ConversationManager.send()
      → ensureContainer() + append user message (optimistic)
      → clear composer
      → show “Titan réfléchit…” + elapsed timer (10s / 30s copy)
      → yieldForPaint()
      → brain.emit("send_message")
          → BackendBridge._streamChat
              → POST /chat/stream { message, request_id, client_request_id, conversation_id }
                  → PrivateAuthMiddleware (session + CSRF)
                  → asyncio.to_thread(handle_chat_stream)
                      → process_chat_message → Brain.process_request → LLM (timeout-bounded)
                  ← SSE conversation_finished
          ← response
      → render Titan message / error card
      → always clear pending / re-enable composer
```

Chat does **not** depend on `GET /events/stream`. SSE is a presence bus only.

## Correlation lifecycle (request_id)

Every submit uses a `client_request_id` / `request_id` (same value).

Safe structured logs (no message body, no secrets, no chain-of-thought):

| Event | Where | Fields |
|-------|--------|--------|
| `CHAT_SUBMIT_START` | frontend ConversationManager | message_length |
| `CHAT_HTTP_SENT` | frontend BackendBridge | request_id |
| `CHAT_API_RECEIVED` | `api/chat_service.py` | request_id, elapsed_ms, stage |
| `CHAT_BRAIN_START` | `api/chat_service.py` | request_id, elapsed_ms, model |
| `CHAT_PROVIDER_START` | `brain/llm.py` | request_id, model |
| `CHAT_PROVIDER_END` | `brain/llm.py` | request_id, status, duration_ms, model |
| `CHAT_BRAIN_END` | `api/chat_service.py` | request_id, elapsed_ms, status |
| `CHAT_RESPONSE_SERIALIZED` | `api/chat_service.py` | request_id, elapsed_ms |
| `CHAT_RESPONSE_SENT` | `api/chat_service.py` | request_id, elapsed_ms |
| `CHAT_REQUEST_TIMEOUT` | `api/chat_service.py` | request_id, code |
| `CHAT_REQUEST_ERROR` | `api/chat_service.py` | request_id, code |
| `CHAT_API_RESPONSE` | backend + frontend | status, duration_ms |
| `CHAT_UI_RENDERED` | frontend | request_id |
| `CHAT_ERROR` | any failure | code, request_id |

Gate backend logs with `TITAN_CHAT_DIAGNOSTICS` (default `true`).  
Gate frontend console logs with `localStorage.titan_chat_diag !== "0"`.

Railway: filter Deploy Logs by `CHAT_` and the `request_id` from the debug overlay / Network tab.

## Timeout and user feedback

| Layer | Default | Env / constant |
|-------|---------|----------------|
| OpenAI client | 45s | `TITAN_LLM_TIMEOUT_SECONDS` |
| Browser AbortController | 55s | `CHAT_CLIENT_TIMEOUT_MS` |
| Soft chat budget | 50s | `TITAN_CHAT_TIMEOUT_SECONDS` (reserved) |

Progressive French copy (never invents a Titan reply):

| Elapsed | Message |
|---------|---------|
| 0–9s | `Titan réfléchit…` (+ seconds after 3s) |
| ≥10s | `Titan traite ta demande… (Ns)` |
| ≥30s | `Le traitement prend plus de temps que prévu… (Ns)` |
| Timeout / abort | `Titan n’a pas pu répondre dans le délai prévu. Réessaie.` |

On timeout / error:

- Structured error card
- Retry button (new `request_id`)
- Pending state cleared
- Composer re-enabled
- Abort supported via Stop

## How to identify where a request stopped

1. Note `request_id` from Network POST body or debug overlay.
2. Search Railway logs for that id.
3. Interpret last completed stage:

| Last log seen | Meaning |
|---|---|
| `CHAT_API_RECEIVED` only | Blocked before Brain (auth/queue/lock) |
| `CHAT_BRAIN_START` then silence | Inside Brain / orchestration |
| `CHAT_PROVIDER_START` then silence | Waiting on OpenAI |
| `CHAT_PROVIDER_END status=timeout` | Provider deadline |
| `CHAT_BRAIN_END` + `CHAT_RESPONSE_SENT` | Server finished — check frontend parse/render |
| No `CHAT_API_RECEIVED` | Request never reached API (client/network/auth) |

## SSE behavior

- `connect()` only after authenticated boot
- Auth probe via `/auth/status` before EventSource
- Unauthorized → hard stop reconnect
- SSE failure **never** blocks `/chat/stream`

## Diagnostics endpoint

`GET /api/chat/diagnostics` (authenticated):

- chat endpoint ready, Brain adapter, provider configured (boolean), model name
- last safe error code / request id
- **no** API keys, **no** message content

## Browser diagnostic overlay (debug only)

Enable with `?debug=1` or `localStorage.titan_debug_perf=1`:

- FPS / quality tier / DPR
- particle/edge budgets
- `request_id`, chat stage, elapsed time
- last HTTP status / provider duration when known

Not shown in normal production.

## Local diagnostics (PowerShell)

```powershell
cd $env:USERPROFILE\OneDrive\Desktop\Titan
python main.py web-dev
```

1. Open `http://127.0.0.1:8000/app/?debug=1`
2. Log in
3. Confirm Auto quality (top-right select)
4. Send `Bonjour Titan`
5. Confirm optimistic user bubble + elapsed thinking copy
6. Confirm exactly one `POST /chat/stream`
7. Confirm reply **or** structured timeout/error + retry
8. Search console / server logs for `CHAT_` + `request_id`

## Railway verification

1. Deploy only after Nolan approves push
2. Hard refresh
3. Confirm Auto mode loads; Emergency activates if FPS stays low
4. Send `Bonjour Titan`
5. Confirm UI remains responsive during wait
6. Confirm reply or timeout/error card (no permanent pending)
7. Railway Deploy Logs → `CHAT_` + `request_id` → note final stage
8. Test Performance via top-right select and `?quality=performance`
9. `GET /health` and `GET /ready`
10. Repeat on both computers

## Known limitations

- In-memory sessions: deploy/restart invalidates cookies → re-login
- Global `_brain_lock` serializes concurrent Brain turns
- Full authenticated E2E against live OpenAI is not claimed green until manually verified on Railway
- FPS and provider latency are independent failure modes — diagnose with the tables above

## Files touched (11.P2 chat trace)

Frontend: `conversation-manager.js`, `backend-bridge.js`, `chat-diagnostics.js`, settings/topbar quality wiring  
Backend: `api/chat_service.py`, `brain/llm.py`  
Tests: `tests/test_web_v2_emergency_fluidity_11_p2.py`  
Docs: this file + `docs/WEB_APP_PERFORMANCE.md`
