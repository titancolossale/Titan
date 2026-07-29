# Titan Roadmap

**Version:** 0.57.0  
**Last updated:** July 29, 2026

Status reflects the **actual repository** as of the Core Integration & System Validation V1 sprint. Items marked complete have production modules, Brain wiring, documentation, and automated tests unless noted otherwise.

---

## Completed — Core Cognitive Systems

| System | Module | Version shipped | Tests |
|--------|--------|-----------------|-------|
| Brain + ThinkPipeline | `brain/brain.py`, `brain/pipeline/` | Phase 1+ | `test_brain_pipeline.py` |
| Natural Language Orchestrator | `brain/natural_language_orchestrator.py` | 0.36.0+ | `test_natural_language_orchestrator.py` |
| Reasoning Engine | `brain/reasoning_engine.py` | 0.38.0 | `test_reasoning_engine.py` |
| Cognitive Context Builder | `brain/cognitive_context_builder.py` | 0.38.0+ | `test_cognitive_context_builder.py` |
| Executive Function | `brain/executive_function.py` | 0.35.0+ | `test_executive_function.py` |
| Meta-Cognition Engine | `brain/meta_cognition.py` | 0.38.0+ | `test_meta_cognition.py` |
| World Model | `brain/world_model.py` | 0.38.0+ | `test_world_model.py` |
| Knowledge Learning Engine | `brain/knowledge_learning_engine.py` | 0.38.0+ | `test_knowledge_learning_engine.py` |
| Proactive Intelligence | `brain/proactive_intelligence.py` | 0.39.0 | `test_proactive_intelligence.py` |
| Project Intelligence | `brain/project_intelligence.py` | 0.34.0+ | `test_project_intelligence.py` |
| Code Intelligence | `brain/code_intelligence.py` | 0.34.0+ | `test_code_intelligence.py` |
| Developer Workflow | `brain/developer_workflow.py` | 0.35.0+ | `test_developer_workflow.py` |
| Cognitive Loop | `brain/cognitive_loop.py` | 0.37.0+ | `test_cognitive_loop.py` |
| Cognitive Orchestrator | `brain/cognitive_orchestrator.py` | 0.37.0+ | `test_cognitive_orchestrator.py` |
| Autonomous Workflow Engine | `brain/autonomous_workflow_engine.py` | 0.39.0+ | `test_autonomous_workflow_engine.py` |
| Cognitive Operating System | `brain/cognitive_operating_system.py` | 0.39.0+ | `test_cognitive_operating_system.py` |
| Long-Term Planner | `brain/long_term_planner.py` | 0.35.0+ | `test_long_term_planner.py` |
| Workspace Awareness | `brain/workspace_awareness.py` | 0.34.0+ | `test_workspace_awareness.py` |
| Development Session Runtime | `brain/development_session.py` | 0.36.0+ | `test_development_session.py` |
| Code Generation Engine | `brain/code_generation_engine.py` | 0.36.0+ | `test_code_generation_engine.py` |
| Mission Runtime V2 | `core/mission_runtime.py` | 0.33.0+ | `test_mission_runtime.py`, `test_mission_v2.py` |

---

## Completed — Tools and Runtimes

| Capability | Module / path | Tests |
|------------|---------------|-------|
| Tool Runtime V2 (default) | `tools/tool_runtime.py` | `test_tool_runtime.py` |
| Tool Orchestrator + Permission Manager | `tools/tool_orchestrator.py` | `test_tool_orchestrator.py` |
| Natural Language Planner + Reasoning Loop | `tools/natural_language_planner.py` | `test_natural_language_planner.py` |
| Core Tool Runtime + Capability Registry | `core/tools/` | `test_capability_registry.py` |
| Tool Intelligence + Execution Engine | `brain/tool_intelligence.py` | `test_tool_intelligence.py` |
| Execution Coordinator | `core/execution_coordinator.py` | `test_execution_coordinator.py` |
| Obsidian connector | `tools/obsidian_tool.py` | `test_obsidian_tool.py` |
| Browser tool | `core/tools/browser/` | `test_browser_tool.py` |
| Calendar tool | `core/tools/calendar/` | `test_calendar_tool.py` |
| Email tool | `core/tools/email/` | `test_email_tool.py` |
| GitHub tool | `core/tools/github/` | `test_core_github_tool.py` |
| Python runtime tool | `core/tools/python/` | `test_core_python_runtime_tool.py` |
| Terminal tool | `core/tools/terminal/` | `test_core_terminal_tool.py` |
| Code editor / controlled patch | `core/tools/code_editor/` | `test_patch_application.py` |
| Web Runtime V1 (API + v2 frontend) | `api/`, `web/v2/` | `test_web_runtime.py` |
| Voice Runtime V1 (skeleton) | `voice/` | `test_voice_runtime.py` |
| Scheduler + Job Runner | `core/scheduler.py` | `test_scheduler.py` |

Provider backends (Google Calendar, Brave Search, TradingView, Apex/Rithmic, etc.) ship as stubs or optional integrations — see individual `docs/*.md` files for LIVE vs stub status.

---

## Current Sprint — Core Integration & System Validation V1

**Goal:** Validate the complete cognitive architecture as one system; fix integration defects; no new cognitive engines.

**Deliverables (this sprint):**

- [x] Integration audit — composition root, shared orchestrator, approved paths
- [x] `tests/test_core_system_integration.py`
- [x] `tests/test_cognitive_lifecycle_end_to_end.py`
- [x] `tests/test_workflow_safety_end_to_end.py`
- [x] `docs/CORE_SYSTEM_VALIDATION.md`
- [x] `docs/ROADMAP.md`
- [x] Web App readiness assessment — **ready** (see validation doc)

**Out of scope:** New cognitive engines, new orchestrators, new memory systems, major feature work.

---

## Next Major Phase — Titan Web App Finalization

**Objective:** Complete the production Web UI (`web/v2/`) against validated Brain APIs.

Sprint progress:

- [x] **Sprint 1 — Application Foundation & Layout** (`docs/WEB_APP_LAYOUT.md`)
- [x] **Sprint 2 — Living Neural Core V1** (`docs/WEB_APP_NEURAL_CORE.md`): Titan
  Core, organic red neural field, cognitive satellites + neural links, six
  behavior states, pointer parallax, reduced-motion support. Frontend-only;
  reuses the existing canvas engine (no second renderer).
- [x] **Sprint 2.3 / 2.4 — Living Neural Organism** (`docs/LIVING_NEURAL_INTELLIGENCE.md`):
  full-canvas cortical tissue, yarn-ball Titan Core (no star/graph reading),
  depth bands, atmospheric filaments — composition matched to reference artwork.
- [x] **Sprint 2.2 — Premium Command Center** (`docs/WEB_APP_PREMIUM_COMMAND_CENTER.md`):
  darker glass, typography hierarchy, sidebar/topbar/orchestrator/composer
  polish, minimal status cards — CSS-first, no backend changes.
- [x] **Sprint 2.7 — Reference Composition Reconstruction**
  (`docs/WEB_APP_REFERENCE_COMPOSITION.md`): full sidebar + Titan Presence,
  telemetry top bar, permanent Cognitive Orchestrator, subsystem satellites,
  lower floating cards, reference composer, system status strip — density and
  hierarchy matched to the approved reference; neural renderer unchanged.
- [x] **Phase 5 — Reference Layout Reconstruction**
  (`docs/WEB_APP_PHASE5_LAYOUT.md`): complete visual composition rebuild —
  shell hierarchy + `phase5-layout.css` authority layer; sidebar / top bar /
  center workspace / Cognitive Orchestrator / floating dock rematched to
  `sprint-2.7-reference-composition.png`; all features reconnected; neural
  renderer untouched.
- [x] **Phase 5.1 — Immersive Neural Stage** (`docs/WEB_APP_PHASE51_IMMERSIVE.md`)
- [x] **Phase 5.2 — Cinematic Living Intelligence**
- [x] **Phase 5.3 — Reference Scene Reconstruction**
  (`docs/WEB_APP_PHASE53_REFERENCE_SCENE.md`): Titan Core as visual gravity;
  organic satellite orbits; major neural highways; cinematic atmosphere;
  quieter floating UI — command center inside a living mind.
- [x] **Phase 5.4 — Floating Cognitive Workspaces**
  (`docs/WEB_APP_FLOATING_WORKSPACES.md`): reconstruct Recent Memory · Obsidian ·
  Browser · Cognitive State · Presence as living smoked-glass workspaces above
  the composer; real frontend state only; Titan Core untouched.
- [x] **Phase 6 — Living Cognitive Orchestrator**
  (`docs/WEB_APP_LIVING_ORCHESTRATOR.md`): right panel rebuilt as living command
  center (objective · pipeline · tools · neural waveform · runtime status);
  presentation only; reuses existing frontend telemetry.
- [x] **Phase 7 — Living Runtime Experience**
  (`docs/WEB_APP_LIVING_RUNTIME.md`): top bar + floating workspaces + atmosphere
  react subtly to Idle/Thinking/Working/Searching/Remembering/Planning;
  presentation only; no whole-page animation.
- [x] **Phase 8 — Living Presence**
  (`docs/WEB_APP_LIVING_PRESENCE.md`): entity presence — Core heartbeat/energy/waves,
  inter-satellite light packets, atmospheric particles/flashes, workspace wake,
  orchestrator subtle life; presentation only; no layout or neural rewrite.
- [x] **Phase 9 — Cognitive Operating System** (`docs/WEB_APP_COGNITIVE_OS.md`)
- [x] **Phase 10 — Canonical Final Reference**
  (`docs/TITAN_FINAL_REFERENCE_IMPLEMENTATION.md`): production desktop view
  reconstructed against
  `docs/design/screenshots/titan-final-canonical-reference.png`; Titan logo
  branding; French orchestrator/pipeline/workspaces; `canonical-final.css` as
  last visual authority; single `/app` frontend preserved.
- [x] **Neural Core Master Polish (v0.51.0)**
  (`docs/LIVING_NEURAL_INTELLIGENCE.md`): denser microscopic tissue, organic
  colonies, multi-segment curved highways, Core gravity, soft bloom, red fog /
  dust / foreground bokeh — canvas neural renderer only; chrome untouched.

Existing foundation:

- `api/chat_service.py` — thread-safe `Brain.process_request()` delegation
- `POST /api/chat/message` — structured orchestration response
- SSE events — orchestration lifecycle, approval hooks
- Frontend — conversation persistence, approval banner, dev metadata

Remaining work (high level):

1. Production UI polish per `docs/design/TITAN_UI_PRODUCTION_SPEC.md`
2. Settings / capability discovery panel (Capability Registry export)
3. Cognitive cycle + workflow telemetry surfaces (optional v1.1)
4. Remote access hardening (`docs/REMOTE_ACCESS.md`)
5. End-to-end browser validation suite expansion

---

## Phase After Web App — Voice Provider Integration & Speaker Recognition

**Objective:** Voice interaction for Nolan and Ibrahim with speaker identification.

**Status:** Phase 20.13 commit/deploy/validate **in progress**; Phase 20.12 real speaker biometric backend **landed**; Phase 20.12B live ECAPA install/validation **passed on this host**; Phase 20.10B-1 production enrollment activation **ready** (real Nolan/Ibrahim voice collection still deferred to 20.10B-2).

Existing foundation:

- `voice/` runtime skeleton — `docs/VOICE_RUNTIME.md`, `tests/test_voice_runtime.py`
- `tests/test_voice_manager.py`

### Phase 20.1 delivered

1. OpenAI Whisper STT + OpenAI TTS provider adapters (`voice/providers/`)
2. Speaker enrollment / identification with confirm-on-unknown (`voice/speaker_identifier.py`)
3. VoiceRuntime gates Brain personal path until speaker is known or confirmed
4. Session user binding via `ContextManager` / `SessionManager`
5. Tests: `tests/test_speaker_identifier.py`, `tests/test_voice_phase20_1.py`

### Phase 20.2 delivered

1. Guided enrollment service (`voice/voice_enrollment.py`) with FR/EN scripts
2. Sample quality validation + privacy-safe temp audio cleanup
3. Identity profile store (activate / revoke / atomic replace)
4. Verification-before-activation; recognition bands (high/medium/low/ambiguous)
5. Authenticated API: `/voice/enrollment/*` + WorkspaceState enrollment mirrors
6. Tests: `tests/test_voice_phase20_2.py`

### Phase 20.3 delivered

1. Live session orchestrator (`voice/live_session.py`) with full lifecycle states
2. VAD + speech segmentation (`voice/vad.py`, `voice/speech_segmenter.py`)
3. Speaker gate before Brain personalization + identity confirm/reject API
4. Sentence-buffered TTS strategy + barge-in interruption
5. Authenticated API: `/voice/session/*` + WorkspaceState live mirrors
6. Tests: `tests/test_voice_phase20_3.py`

### Phase 20.4 delivered

1. Web App V2 voice module (`web/v2/voice/`) — mic permission, capture, PTT, TTS playback
2. Voice nav + enrollment panel with consent (Nolan / Ibrahim)
3. Composer push-to-talk + barge-in `Interrompre` + identity badge / confirm UI
4. HTTP `tts_audio_chunks` on finish/confirm for browser playback
5. Tests: `tests/test_voice_phase20_4.py`

### Phase 20.5 delivered

1. Real-time conversation engine (`voice/conversation_engine.py`) — multi-turn continuity, idle/conversation timeouts, recovery tokens
2. Incremental STT (`voice/streaming_stt.py`) — partial / stable / final (only stable+final → Brain)
3. Streaming Brain adapter (`voice/streaming_brain.py`) — deltas, sentence completion, cancel, no duplicate turns
4. Streaming TTS engine (`voice/streaming_tts.py`) — sentence streaming, FR/EN voice switch, cancel
5. Latency tracker + stream diagnostics (`VOICE_STREAM_*`, `BRAIN_STREAM_*`, `TTS_STREAM_*`, recovery/idle)
6. API: `/voice/session/recover`, `/heartbeat`, `/events` — auth preserved
7. Web client: session reuse, refresh recovery, heartbeat, progressive TTS enqueue (no UI redesign)
8. Tests: `tests/test_voice_phase20_5.py`

### Phase 20.6 delivered

1. Streaming transport layer (`voice/transport/`) — WebSocket, SSE, HTTP fallback, reconnect, heartbeat, graceful shutdown
2. Realtime provider registry + failover (`voice/providers/realtime_registry.py`, `failover.py`)
3. OpenAI Realtime / Whisper Streaming / Deepgram Streaming / ElevenLabs Streaming adapters
4. Provider-level STT hypotheses + TTS byte chunks wired into Incremental STT / Streaming TTS
5. Latency + stream performance controller (`mic` / `provider` / turnaround; coalesce / buffer caps)
6. Diagnostics: `PROVIDER_*`, `PROVIDER_TRANSPORT_*`
7. Tests: `tests/test_voice_phase20_6.py`

### Phase 20.7 delivered

1. Conversation flow controller (`voice/conversation_flow.py`) — natural pauses, barge-in debounce, resume-after-interrupt, confirmation prompts
2. Mic calibration (`voice/mic_calibration.py`) — noise floor, speech threshold, gain, clipping, low-volume
3. Silence detector (`voice/silence_detector.py`) — end-of-turn, long pause, false-speech rejection
4. Session statistics (`voice/session_stats.py`) + soak harness (`voice/production_soak.py`, `scripts/phase20_7_voice_soak.py`)
5. Authenticated API: `/voice/session/calibrate/*`, `/voice/session/stats`
6. Web helpers only (no redesign): mic metrics/gain, permission flow, calibrate/stats client APIs
7. Tests: `tests/test_voice_phase20_7.py`

### Phase 20.8 delivered

1. Live provider production prep — OpenAI Realtime registry adapters, Deepgram PCM params, ElevenLabs live key/base64, live socket factory (`websocket-client`)
2. Native browser WebSocket transport — persistent connection, reconnect, heartbeat, backpressure, stream sync (`/voice/session/ws` + `voice-socket.js`)
3. Enrollment preparation — embedding provider abstraction, multi-session history/labels, quality scoring, language-independent features, cross-user duplicate detection, safe replace plans
4. Diagnostics — provider health + browser transport snapshots; soak scenarios for browser reconnect / concurrent sessions / provider fallback / Railway readiness
5. Tests: `tests/test_voice_phase20_8.py`; soak CLI: `scripts/phase20_8_voice_soak.py`

### Phase 20.9 delivered

1. Real enrollment readiness — server-side consent gate (`AWAITING_CONSENT`), multi-language scripts/consent (FR/EN/ES + bilingual), session quality scoring, same-user near-duplicate + replace plans, `CANCELLED` status, recovery tokens
2. Embedding pipeline prep — registry with histogram default + ECAPA / Resemblyzer / OpenAI-compatible stubs (unavailable until wired)
3. Live provider soak — voice verification, consent/recovery, live provider recovery, multiple consecutive conversations (+ prior reconnect/fallback/Railway scenarios)
4. Diagnostics — `collect_enrollment_diagnostics` (provider status, embedding quality, speaker/verification confidence, session history, latency, provider health); API `/voice/enrollment/diagnostics`
5. Performance — enrollment processing latency marks, batch embedding extract, faster provider recovery path in soak
6. Tests: `tests/test_voice_phase20_9.py`; soak CLI: `scripts/phase20_9_voice_soak.py`

### Phase 20.10A delivered

1. Production enrollment workflow state machine (`WAITING_CONSENT` … `SUCCESS` / `FAILED` / `CANCELLED` / `RECOVERY`)
2. Enrollment sessions: multi-attempt, resume, cancel, replace, profile versioning, duplicate protection, audit history
3. Production quality validation (signal, noise, duration, language independence, duplicates, clipping, mic quality)
4. Verification pipeline with confidence thresholds + retry (production-embedding ready)
5. Security: no embedding/raw-audio exposure; consent gate; revocation
6. Diagnostics: workflow states, failures, quality metrics, verification confidence
7. Tests: `tests/test_voice_phase20_10a.py`

### Phase 20.11 delivered

1. Production embedding architecture — ECAPA / Resemblyzer / external / local providers; histogram = **dev fallback only** (never silent production trust)
2. Speaker verification engine — cosine/provider similarity, UNKNOWN / AMBIGUOUS, multi-sample aggregation, configurable thresholds
3. Identity security boundary — voice ID may bind user context only; never authorizes high-risk / financial / admin actions
4. Encryption-ready embedding storage (schema v4) — integrity seals, corruption detection, revocation / replacement / migration
5. Anti-spoof / liveness preparation — extensible registry; unavailable never weakens verification
6. Explicit migration — histogram profiles require re-enrollment; Phase 20.10B real Nolan/Ibrahim enrollment still deferred
7. Safe diagnostics — provider/version/verification/confidence/migration/liveness (no raw embeddings)
8. Tests: `tests/test_voice_phase20_11.py`

### Phase 20.12 delivered

1. Real ECAPA-TDNN backend (`voice/ecapa_provider.py`) — SpeechBrain when installed; lazy CPU load; normalized embeddings
2. Resemblyzer fallback (`voice/resemblyzer_provider.py`) — optional dependency; same trust / readiness rules
3. Explicit `DEVELOPMENT` / `PRODUCTION` biometric trust mode — histogram never trusted in production
4. Verification decisions: VERIFIED / UNKNOWN / AMBIGUOUS (+ cross-user rejection)
5. AES-GCM authenticated embedding storage (envelope v2) — key id, nonce safety, legacy XOR migration
6. CLAIMED_IDENTITY vs VERIFIED_IDENTITY — spoken/UI « je suis Nolan » is never biometrically verified
7. Separate biometric readiness on `/ready` — never fails process readiness when model deps missing
8. Tests: `tests/test_voice_phase20_12.py`

### Phase 20.10B-1 delivered (activation — no real voice collection)

1. Host production activation: ECAPA provider + production biometric trust + AES-GCM encryption flags
2. Safe storage-key bootstrap (`scripts/ensure_voice_embedding_storage_key.py`) — never prints/commits the key
3. Enrollment pre-flight (`voice/enrollment_preflight.py` + CLI) covering ECAPA / trust / AES-GCM / storage / mic / consent / Nolan+Ibrahim slots
4. Guided enrollment entry point (`scripts/phase20_10b1_guided_enroll.py`) + Web App Voice panel preflight wiring (no redesign)
5. API `GET /voice/enrollment/preflight`
6. Tests: `tests/test_voice_phase20_10b1.py`

### Remaining (Phase 20.10B-2+)

1. Optional wake-word detector (config hooks exist; not activated)
2. Collect and enroll real Nolan/Ibrahim voice samples (explicit, consented) — **Phase 20.10B-2**
3. ~~Install optional biometric deps (`torch` + `speechbrain`) on target hosts and smoke-test live ECAPA inference~~ — **done on this host (Phase 20.12B)**; Resemblyzer still optional
4. End-to-end live-provider soak on Railway with real API keys
5. Progressive browser WS adoption in the voice controller (HTTP fallback remains)
6. ~~Before enrollment: set `TITAN_VOICE_EMBEDDING_PROVIDER=ecapa`, production biometric trust, and encryption key~~ — **done on this host (Phase 20.10B-1)**

---

## Phase 10 — Cloud Deployment

| Step | Status | Document |
|------|--------|----------|
| 10.1 Deployment readiness audit | **Complete** | [`docs/CLOUD_DEPLOYMENT_READINESS.md`](CLOUD_DEPLOYMENT_READINESS.md) |
| 10.2 Railway production deployment | **Complete (docs + config)** | [`docs/RAILWAY_DEPLOYMENT.md`](RAILWAY_DEPLOYMENT.md) |
| 10.3 TLS + domain + auth hardening | Done | Private Argon2id session auth + `/login` |


**10.1 delivered:** typed env config (`config/deployment.py`), `/ready` endpoint,
`python main.py web-prod`, Dockerfile, path helpers, tests.

**10.2 delivered:** provider fixed to **Railway**; `railway.json`; beginner deploy guide,
env checklist, troubleshooting. Nolan deploys from the Railway dashboard (agent does
not deploy). Public HTTPS URL after Nolan completes the checklist.

---

## Known Technical Debt (cross-phase)

Tracked in `.cursor/rules/titan.mdc` §26.5:

1. Unified memory facade (partial — `MemoryService` stable)
2. Constitution not loaded into LLM prompts
3. Static `ContextManager` not fully synced with state/mission
4. `print()` debug → structured logging (partial)
5. `prompts/` directory not yet populated
6. Installable package entry point pending

---

## Related Documents

- [`docs/CORE_SYSTEM_VALIDATION.md`](CORE_SYSTEM_VALIDATION.md) — integration validation report
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — execution paths
- [`Titan_Blueprint.md`](../Titan_Blueprint.md) — product vision
- [`CHANGELOG.md`](../CHANGELOG.md) — release history
