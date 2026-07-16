# Web App Chat Diagnostics — Phase 11.1B

## Previous failure symptoms

On Railway production (multiple computers):

- Titan Web App felt very slow / frozen after submit
- User message did not appear in the conversation panel
- Composer did not clearly confirm send
- No Titan response appeared
- No useful recoverable error was shown
- Railway logs previously showed repeated `GET /events/stream → 401`

## Root cause (ranked)

1. **Primary — frontend message container race (highest impact)**  
   `ConversationManager.bindDom()` ran **before** the chat panel was mounted into the center slot.  
   `MessageRenderer` kept a **null** `_container`. On submit, `appendMessage()` threw  
   `MessageRenderer: container not mounted` **before** the network call.  
   The catch path also tried to append an error into the same null container and failed.  
   Result: no visible user message, no request, no error card — perceived freeze.

2. **Secondary — boot order**  
   Render pipeline subscribed after router sync in some paths; first chat panel mount  
   could be delayed by transition animation. Lazy `ensureContainer()` + bind-after-navigate  
   eliminate this class of failure.

3. **Contributing — no client timeout**  
   Hung provider calls left the UI waiting indefinitely.

4. **Contributing — SSE unauthorized reconnects**  
   EventSource 401s cannot expose status; reconnect needed earlier auth probe + hard stop.

5. **Contributing — busy cleared early on FINISHED**  
   Opened a double-submit window during typewriter; fixed to keep busy until render completes.

## Exact frontend / backend path

```
Composer Enter/click
  → ConversationManager.send()
      → ensureContainer() + append user message (optimistic)
      → clear composer
      → show “Titan réfléchit…”
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
```

Chat does **not** depend on `GET /events/stream`. SSE is a presence bus only.

## Correlation lifecycle

Every submit uses a `client_request_id` / `request_id` (same value).

Safe structured logs (no message body, no secrets):

| Event | Where |
|-------|--------|
| `CHAT_SUBMIT_START` | frontend ConversationManager |
| `CHAT_HTTP_SENT` | frontend BackendBridge |
| `CHAT_API_RECEIVED` | `api/chat_service.py` |
| `CHAT_BRAIN_START` | `api/chat_service.py` |
| `CHAT_PROVIDER_START` / `CHAT_PROVIDER_END` | `brain/llm.py` |
| `CHAT_API_RESPONSE` | backend + frontend |
| `CHAT_UI_RENDERED` | frontend |
| `CHAT_ERROR` | any failure |

Gate backend logs with `TITAN_CHAT_DIAGNOSTICS` (default `true`).  
Gate frontend console logs with `localStorage.titan_chat_diag !== "0"`.

## Timeout behavior

| Layer | Default | Env |
|-------|---------|-----|
| OpenAI client | 45s | `TITAN_LLM_TIMEOUT_SECONDS` |
| Browser AbortController | 55s | `CHAT_CLIENT_TIMEOUT_MS` in bridge |
| Soft chat budget | 50s | `TITAN_CHAT_TIMEOUT_SECONDS` (config reserved) |

Timeout surfaces as:

```json
{
  "ok": false,
  "error": {
    "code": "provider_timeout",
    "message": "Titan met trop de temps à répondre. Réessaie.",
    "retryable": true
  },
  "request_id": "..."
}
```

Pending state is always cleared in `finally` / `_clearBusyState()`.

## SSE behavior

- `connect()` only after authenticated boot (`ensureAuthenticated` → `app.start` → delayed `brain.connect`)
- Auth probe via `/auth/status` before opening EventSource
- On repeated errors: probe auth; on 401/403 equivalent → `_authBlocked`, stop reconnect
- Bounded exponential backoff (1.5s → 30s, hard max 12)
- Logout disconnects EventSource before clearing session
- SSE failure never blocks `/chat/stream` submit

## Error codes

| Code | Meaning | Retryable |
|------|---------|-----------|
| `unauthenticated` | 401 / session expired | false (redirect `/login`) |
| `invalid_request` | bad body / CSRF | often true after reload |
| `duplicate_request` | in-flight guard / idempotent replay | — |
| `provider_timeout` | LLM or client deadline | true |
| `provider_unavailable` | provider down | true |
| `brain_failure` | Brain exception | true |
| `response_parse_error` | bad SSE body | true |
| `network_error` | fetch failure | true |
| `unexpected_error` | catch-all | true |

## Diagnostics endpoint

`GET /api/chat/diagnostics` (authenticated only):

- chat endpoint ready
- Brain adapter available
- provider configured (boolean)
- model name
- event stream enabled
- last safe error code / request id
- **no** API keys, **no** message content

## Local diagnostics (PowerShell)

```powershell
cd $env:USERPROFILE\OneDrive\Desktop\Titan
python main.py web-dev
```

1. Open `http://127.0.0.1:8000/app/`
2. Log in
3. DevTools → Network + Console
4. Send `Bonjour Titan`
5. Confirm user bubble appears immediately; composer clears; “Titan réfléchit…” shows
6. Confirm **exactly one** `POST /chat/stream`
7. Confirm Titan reply or inline error card
8. Confirm UI remains clickable (sidebar, settings)
9. Simulate timeout: temporarily set a low `TITAN_LLM_TIMEOUT_SECONDS` or abort in Network
10. Confirm retry button resubmits with a **new** request id

Search logs for `CHAT_` + the request id.

## Railway diagnostics

1. Commit/push only after Nolan approves
2. Wait for Railway **Active**
3. Incognito → log in → DevTools
4. Send `Bonjour Titan`
5. Record `POST /chat/stream` status + duration
6. Confirm optimistic user message
7. Confirm response or structured error
8. Railway Deploy Logs → filter `CHAT_` + `request_id`
9. `GET /health` and `GET /ready`
10. Confirm no unauthorized SSE retry storm
11. Repeat on both computers

## Known limitations

- In-memory sessions: deploy/restart invalidates cookies → re-login required
- Global `_brain_lock` serializes concurrent Brain turns
- Typewriter animation is cosmetic; reduced-motion skips it
- SSE still cannot send custom headers (cookies / `?token=` only)
- Full authenticated E2E against live OpenAI is not claimed green until manually verified on Railway

## Files touched (11.1B)

Frontend: `conversation-manager.js`, `message-renderer.js`, `backend-bridge.js`, `app.js`,
`composer-region.js`, `state-store.js`, `panel-mount.js`, `web-auth.js`, neural engine/stage,
`chat-diagnostics.js`, `ui.css`

Backend: `api/app.py`, `api/chat_service.py`, `brain/llm.py`, `config/settings.py`

Tests: `tests/test_web_chat_freeze_11_1b.py`
