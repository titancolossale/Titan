# Web App Brain Latency — Phase 11.4

## Root cause (measured)

For the production-style greeting **“Bonjour Titan”**, local instrumentation with a live OpenAI-backed agent path showed:

| Stage | Approx. duration | Notes |
|-------|------------------|-------|
| NLO `_run_reasoning` | ~0.6s | Always ran before conversation |
| Think `_stage_execution_coordinate` | **~15–18s** | Dominant |
| → `_run_agents` | **~15–18s** | Default pipeline |
| → reasoning agent | ~7–8s | Real OpenAI call |
| → planning agent | ~7–8s | Real OpenAI call |
| Think `_stage_llm_call` | 10–45s (provider) | Third OpenAI call |
| Prompt size (complex path) | ~6 200 chars | Oversized for a greeting |

**Exact slow stage:** `_stage_execution_coordinate` → `_run_agents` → default `reasoning` + `planning` agents (two extra provider calls) before the conversational model reply.

**Cause class:** multiple causes — agent loops (primary) + stacked provider latency/retries (secondary) + oversized context (contributing). Not a frontend freeze (addressed in 11.1B / 11.P2 / 11.P3).

With three sequential OpenAI calls and `TITAN_LLM_TIMEOUT_SECONDS` previously at 45s, wall time easily exceeded two minutes under slow/retrying provider conditions.

## Simple-request fast path

`brain/chat_fast_path.py` + `NaturalLanguageOrchestrator.process()`:

Selected for clearly simple conversational messages, e.g.:

- Bonjour Titan / Salut / Hello
- Comment vas-tu ?
- Qui es-tu ?
- Merci / OK

Behavior:

- Skip multi-step planner, tools, agents, missions, large memory bundles
- Keep Titan system instructions / identity / constitution summary
- One call to the primary conversational model via `LLM.ask` / `ask_with_budget`
- Compact prompt (no agent results, no tool schemas, no full architecture dump)
- Output capped by `TITAN_FAST_PATH_MAX_OUTPUT_TOKENS` (default 400)

Logs: `CHAT_FAST_PATH_SELECTED`

## Complex-path limits

When the fast path is not selected:

| Limit | Default | Setting |
|-------|---------|---------|
| Global wall-clock deadline | 30s | `TITAN_CHAT_DEADLINE_SECONDS` |
| Provider HTTP timeout (per attempt) | 20s (capped by remaining budget) | `TITAN_LLM_TIMEOUT_SECONDS` |
| Provider retries | 1 (2 attempts total) | `TITAN_LLM_MAX_RETRIES` |
| Max planning iterations | 3 | `TITAN_MAX_PLANNING_ITERATIONS` |
| Max reasoning iterations | 3 | `TITAN_MAX_REASONING_ITERATIONS` |
| Max agent handoffs | 2 | `TITAN_MAX_AGENT_HANDOFFS` |
| Max tool-decision slice | 5s | `TITAN_MAX_TOOL_DECISION_SECONDS` |

Logs: `CHAT_COMPLEX_PATH_SELECTED`

Think pipeline also sets `skip_agents` for simple greetings as a safety net if they ever reach `think()`.

## Global deadline

`brain/request_deadline.py` — one `RequestDeadline` per chat turn, bound via contextvars:

- Created in `api/chat_service.process_chat_message`
- Propagated to Brain / NLO / LLM / pipeline stages
- Provider timeout = `min(configured, remaining_budget)`
- Exhaustion → structured `brain_timeout` (never infinite pending)

## Structured timeout

```json
{
  "ok": false,
  "error": {
    "code": "brain_timeout",
    "message": "Titan n’a pas pu terminer sa réponse dans le délai prévu.",
    "retryable": true,
    "request_id": "...",
    "last_completed_stage": "provider_start"
  }
}
```

Frontend: clear thinking state, show error card, re-enable composer, keep user message, Retry with a new `request_id`.

## Cancellation

- Stop aborts the browser `AbortController`
- POST `/api/chat/cancel` signals the in-flight deadline
- Stream generator disconnect also calls `cancel_chat_request`
- Generation counter discards late results after Stop
- Cancelled turns are not written as Titan replies

## Provider configuration

- Model: `TITAN_LLM_MODEL` (default `gpt-5.2`)
- Key: `OPENAI_API_KEY` (Railway) — never logged
- Client: sync OpenAI Responses API via `LLM`
- Retries bounded; timeouts do not nest beyond the global deadline
- Safe logs: model, prompt char/token estimate, attempt, elapsed, remaining budget, error category

## Prompt size (greeting)

| Path | Approx. user prompt |
|------|---------------------|
| Before (full think) | ~6 200 chars + agent artifacts |
| After (fast path) | typically &lt; 500 chars (+ system instructions unchanged) |

## Known limitations

- Fast path is pattern-based; borderline questions still use the complex path
- In-flight OpenAI HTTP calls cannot always be hard-killed mid-socket; cancel prevents further stages and abandons the UI result
- Railway verification with a real authenticated greeting is still required after deploy
- AgentManager still constructs its own `AgentLLM`/`LLM` for complex paths (shared gateway cleanup is a follow-up)

## Recommended next step

Deploy to Railway, hard-refresh, send **Bonjour Titan**, confirm `CHAT_FAST_PATH_SELECTED` + `CHAT_PROVIDER_END` in logs and a real reply under 30s.
