# Changelog

All notable changes to the Titan project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Version policy

- **Semver:** `MAJOR.MINOR.PATCH` — breaking changes, new features, and bug fixes respectively.
- **Current codebase version:** `0.59.4` (see `config/settings.py`).
- **Phase 1 target release:** `0.1.0` — Titan V2 Phase 1 (Architecture Cleanup). **Shipped 2026-06-27.**
- **Phase 10A release:** `0.10.0` — Tool Runtime V2 default. **Shipped 2026-06-28.**
- **Future milestone:** `2.0.0` — full Titan V2 release after all planned phases.

## [0.59.4] — 2026-08-02

### Added

- **Phase 20.13 — Persistent voice biometric storage (Railway Volume)**
  - `voice/biometric_persistence.py` — create biometric dirs, writability probe, volume/persistence detection; never silent ephemeral fallback
  - `/ready` check `biometric_storage` (required in production when persistence required)
  - Startup bootstrap in `api/app.py` validates biometric storage on boot
  - `SpeakerProfileStore` schema v5: AES-GCM envelopes on save; empty plaintext `embeddings` when encryption enabled; encrypted enrollment sample envelopes
  - Dockerfile defaults: `TITAN_DATA_DIR=/app/data`, `TITAN_BIOMETRIC_PERSISTENCE_REQUIRED=true`
  - Tests: `tests/test_voice_phase20_13_persistence.py` (enrollment restart, redeploy simulation, multi-user, encryption)
  - Docs: Railway volume **required** for voice; biometrics stay on volume JSON (not Postgres)

### Notes

- Does **not** change `TITAN_VOICE_EMBEDDING_STORAGE_KEY`
- Does **not** perform new voice enrollment
- Postgres remains conversation store only

## [0.59.1] — 2026-07-29

### Added

- **Phase 20.13 — Railway ECAPA production dependencies**
  - `requirements-prod.txt` — pinned CPU wheels `torch==2.11.0+cpu`, `torchaudio==2.11.0+cpu`, `speechbrain==1.1.0` (PyTorch CPU index) for Docker/Railway
  - Dockerfile installs prod requirements + `libgomp1` / `libsndfile1`; sets non-secret production enrollment ENV defaults (ECAPA, trust, AES-GCM flags, wake-word off)
  - `/ready` voice_biometric check exposes safe `ecapa_deps` flag (never storage keys / embeddings)
  - `probe_ecapa_dependencies()` also reports `torchaudio`
  - Does **not** commit `TITAN_VOICE_EMBEDDING_STORAGE_KEY` — still requires manual Railway Variables setup

## [0.59.0] — 2026-07-29

### Added

- **Phase 20.13 — Commit, Deploy & Validate Voice Production**
  - Ship Phase 20.x voice stack to `origin/main` for Railway deployment
  - Harden `.gitignore` for voice models, enrollment temps, speaker profiles, soak dumps, local conversation DB
  - Production validation checklist: `/health`, `/ready`, auth, Postgres, text chat, Voice panel, enrollment UI
  - Does **not** collect Nolan/Ibrahim real voices; wake-word / always-listening remain off
  - Railway production ECAPA/AES-GCM requires manual Variables (names only — never commit secrets)

## [0.58.0] — 2026-07-29

### Added

- **Phase 20.10B-1 — Production Enrollment Activation**
  - Activate host ECAPA production biometric path (`TITAN_VOICE_EMBEDDING_PROVIDER=ecapa`) with production trust + AES-GCM
  - Enrollment pre-flight (`voice/enrollment_preflight.py`) — ECAPA / trust / AES-GCM / storage / mic / consent / Nolan+Ibrahim slots — **no recording**
  - Safe key bootstrap: `scripts/ensure_voice_embedding_storage_key.py` (never prints the key)
  - Production env activation: `scripts/activate_production_enrollment_env.py`
  - Preflight CLI: `scripts/phase20_10b1_enrollment_preflight.py`
  - Guided enrollment entry (instructions + Web App path): `scripts/phase20_10b1_guided_enroll.py`
  - API `GET /voice/enrollment/preflight` + Voice panel preflight status (no UI redesign)
  - Tests: `tests/test_voice_phase20_10b1.py`

### Notes

- Does **not** collect Nolan/Ibrahim real voices yet (Phase 20.10B-2). Wake-word / always-listening remain off. Trading/Obsidian untouched. No commit of encryption secrets.

## [0.57.0] — 2026-07-29

### Added

- **Phase 20.12 — Real Speaker Biometric Backend**
  - Real ECAPA-TDNN provider (`voice/ecapa_provider.py`) — SpeechBrain `spkrec-ecapa-voxceleb` when deps installed; lazy CPU load; L2-normalized embeddings; graceful unavailable
  - Resemblyzer fallback (`voice/resemblyzer_provider.py`) — optional GE2E VoiceEncoder
  - Explicit biometric trust modes: `DEVELOPMENT` / `PRODUCTION` (`voice/biometric_trust.py`) — histogram never trusted in production
  - Verification decision `VERIFIED` (+ UNKNOWN / AMBIGUOUS); production rejects histogram identity
  - AES-GCM authenticated embedding storage (envelope v2, key id, nonce, legacy XOR migration) (`voice/embedding_storage.py`)
  - CLAIMED_IDENTITY vs VERIFIED_IDENTITY — spoken/UI confirmation never auto-verifies biometrics
  - Separate biometric readiness on `/ready` — missing model deps never fail process readiness
  - Optional deps documented in `requirements.txt` (`torch` / `speechbrain` / `resemblyzer`); `cryptography` required for AES-GCM
  - Config: `TITAN_VOICE_BIOMETRIC_TRUST_MODE`, `TITAN_VOICE_EMBEDDING_KEY_ID`, `TITAN_VOICE_ECAPA_*`
  - Tests: `tests/test_voice_phase20_12.py`

### Notes

- Does **not** collect Nolan/Ibrahim real voices (Phase 20.10B still deferred); wake-word remains disabled; Trading/Obsidian untouched; no UI redesign; authentication not weakened.
- Phase 20.12B (this host): installed `torch==2.11.0`, `torchaudio==2.11.0`, `speechbrain==1.1.0`; live ECAPA model load + synthetic inference validated. Windows uses SpeechBrain `LocalStrategy.COPY` by default (`TITAN_VOICE_ECAPA_LOCAL_STRATEGY`) to avoid symlink privilege errors.

## [0.56.0] — 2026-07-29

### Added

- **Phase 20.11 — Production Speaker Embeddings & Identity Security**
  - Production embedding abstraction: ECAPA-TDNN / Resemblyzer / external / local providers with capability detection, trust levels, and versioning (`voice/embedding_provider.py`, `voice/embedding_capabilities.py`)
  - Histogram remains **development/test fallback only** — never silently production-trusted
  - Deterministic local provider for production-path drills (`local_deterministic` / `local_det_v1`)
  - Speaker verification engine: cosine/provider similarity, configurable thresholds, UNKNOWN / AMBIGUOUS, multi-sample aggregation, prefer UNKNOWN over false ID (`voice/speaker_verification.py`)
  - Identity security boundary: voice ID selects user context only; never authorizes destructive/financial/admin/high-risk actions (`voice/identity_security.py`)
  - Encryption-ready embedding storage + integrity seals, corruption detection, duplicate-user protection (`voice/embedding_storage.py`; profile store schema v4)
  - Extensible anti-spoof / liveness layer (null + heuristic stub) — unavailable never weakens verification (`voice/anti_spoof.py`)
  - Explicit migration path: histogram profiles blocked from auto-trust; re-enrollment required (`voice/embedding_migration.py`)
  - Safe diagnostics: provider/version/verification/confidence/threshold/profile/migration/liveness — never raw embeddings (`voice/embedding_diagnostics.py`)
  - Config: `TITAN_VOICE_EMBEDDING_REQUIRE_PRODUCTION_TRUST`, `TITAN_VOICE_EMBEDDING_ALLOW_DEV_IDENTITY`, `TITAN_VOICE_EMBEDDING_ENCRYPTION`, `TITAN_VOICE_EMBEDDING_RETAIN_RAW_AUDIO`, `TITAN_VOICE_ANTI_SPOOF_PROVIDER`, `TITAN_VOICE_EMBEDDING_AGGREGATION`
  - Tests: `tests/test_voice_phase20_11.py`

### Notes

- Does **not** collect Nolan/Ibrahim real voices (Phase 20.10B still deferred); wake-word remains disabled; Trading/Obsidian untouched; no UI redesign; authentication not weakened.

## [0.55.0] — 2026-07-29

### Added

- **Phase 20.10A — Production Voice Enrollment System**
  - Production enrollment state machine: `WAITING_CONSENT` → `CONSENT_GRANTED` → `READY_TO_RECORD` → `RECORDING` → `VERIFYING` → `SUCCESS` / `FAILED` / `CANCELLED` / `RECOVERY` (`voice/enrollment_workflow.py`)
  - Session features: multiple attempts, resume after interruption, safe cancellation, replacement enrollment, profile versioning, duplicate protection, append-only audit history
  - Production quality metrics: signal level, background noise, speech duration, language independence, duplicate recordings, clipping, microphone quality
  - Verification pipeline with confidence thresholds + retry workflow (`voice/enrollment_verification.py`) — ready for future production embedding backends
  - Security: embeddings/raw audio never exposed; explicit consent required; enrollment revocation supported
  - Diagnostics: workflow state counts, failures, quality metrics, verification confidence, audit trail
  - API: `/voice/enrollment/workflow`, `/voice/enrollment/audit` (+ enriched `/diagnostics` / `/status`)
  - Tests: `tests/test_voice_phase20_10a.py`

### Notes

- Does **not** collect Nolan/Ibrahim real voices; wake-word remains disabled; Trading/Obsidian untouched; no UI redesign.

## [0.54.0] — 2026-07-28

### Added

- **Phase 20.9 — Real Speaker Enrollment & Live Provider Soak**
  - Server-side enrollment consent gate (`AWAITING_CONSENT`), multi-language consent (FR/EN/ES), recovery tokens, `CANCELLED` status, session quality scoring, same-user near-duplicate + replace plans
  - Embedding provider registry: histogram default + ECAPA / Resemblyzer / OpenAI-compatible stubs (not enabled)
  - Multi-language enrollment scripts: Spanish + bilingual FR/EN
  - Enrollment diagnostics aggregator + APIs: `/voice/enrollment/consent`, `/recover`, `/scripts`, `/diagnostics`
  - Live provider soak scenarios: voice verification, consent/recovery, live provider recovery, multiple consecutive conversations
  - Performance: enrollment processing latency marks, batch embedding extract
  - Config: `TITAN_VOICE_EMBEDDING_PROVIDER`, `TITAN_VOICE_ENROLLMENT_REQUIRE_CONSENT`, `TITAN_VOICE_ENROLLMENT_CONSENT_VERSION`, `TITAN_VOICE_ENROLLMENT_RECOVERY_TTL`, `TITAN_VOICE_ENROLLMENT_SAME_USER_DUP_THRESHOLD`
  - Tests: `tests/test_voice_phase20_9.py`; soak CLI: `scripts/phase20_9_voice_soak.py`

### Notes

- Does **not** collect Nolan/Ibrahim real voices; wake-word remains disabled; Trading/Obsidian untouched; no UI redesign.

## [0.53.0] — 2026-07-28

### Added

- **Phase 20.8 — Live Providers & Real Voice Preparation**
  - Live provider readiness: OpenAI Realtime (registry STT/TTS adapters + base64 wire framing), Deepgram PCM query params, ElevenLabs live key + base64 audio decode, Whisper streaming retained
  - Optional `websocket-client` outbound sockets via `voice/transport/socket_backends.py` (offline InMemory fallback preserved)
  - Native browser ↔ Titan WebSocket: `api/voice_ws_routes.py`, `voice/transport/browser_hub.py` / `browser_protocol.py`, `web/v2/voice/voice-socket.js` (reconnect, heartbeat, backpressure, sync) — HTTP remains fallback; no UI redesign
  - Enrollment prep: pluggable `voice/embedding_provider.py`, multi-session history + labels, embedding quality scoring, language-independent features, cross-user duplicate detection, safe profile replacement plans
  - Provider health aggregator + diagnostics API: `/voice/session/diagnostics/providers`, `/voice/session/diagnostics/transport`
  - Production soak scenarios: browser reconnect, concurrent sessions, provider fallback, Railway config readiness (`scripts/phase20_8_voice_soak.py`)
  - Performance: reused failover reconnect policy; live session wires `TransportManager` into provider failover
  - Config: `TITAN_VOICE_LIVE_SOCKETS`, `TITAN_VOICE_WS_*`, `TITAN_VOICE_ENROLLMENT_DUPLICATE_THRESHOLD`, `TITAN_VOICE_EMBEDDING_VERSION`
  - Tests: `tests/test_voice_phase20_8.py`

### Notes

- Does **not** collect Nolan/Ibrahim real voices; wake-word remains disabled; Trading/Obsidian untouched.

## [0.52.0] — 2026-07-28

### Added

- **Phase 20.7 — Live Voice Experience & Production Soak**
  - Conversation flow polish: natural pauses, turn timing, barge-in debounce, resume-after-interrupt, confirmation prompts
  - Mic calibration: noise floor, speech threshold, gain estimate, clipping / low-volume warnings
  - Silence detection: automatic end-of-turn, long-pause timeout, background noise tolerance, false-speech rejection
  - Session statistics: speech / turn / mic / provider / brain / TTS latency aggregates
  - Production soak harness: long conversation, provider reconnect, network drop, rapid start/stop, consecutive sessions, enrollment persistence, speaker switching
  - Authenticated API: `/voice/session/calibrate/*`, `/voice/session/stats`
  - Web helpers (no UI redesign): mic metrics/gain, permission flow, calibrate/stats client APIs
  - Diagnostics: `VOICE_MIC_*`, `VOICE_END_OF_TURN`, `VOICE_LONG_PAUSE`, `VOICE_FALSE_SPEECH_REJECTED`, `VOICE_NATURAL_PAUSE`, `VOICE_RESUME_AFTER_INTERRUPT`, `VOICE_TURN_TIMING`, `VOICE_SESSION_STATS`, `VOICE_SOAK_SCENARIO`
  - Config: `TITAN_VOICE_MIC_*`, `TITAN_VOICE_LONG_PAUSE_TIMEOUT`, `TITAN_VOICE_FALSE_SPEECH_MAX`, `TITAN_VOICE_NATURAL_PAUSE_MS`, barge-in / resume grace
  - Tests: `tests/test_voice_phase20_7.py`; soak CLI: `scripts/phase20_7_voice_soak.py`
  - Always-listening remains hard-disabled; wake-word not activated; Trading/Obsidian untouched

## [0.51.0] — 2026-07-28

### Added

- **Phase 20.6 — True Real-Time Streaming Providers**
  - Generic streaming transport: WebSocket, SSE, HTTP fallback, reconnect, heartbeat, graceful shutdown
  - Realtime provider abstraction + registry (configurable selection / fallback chains)
  - Providers: OpenAI Realtime (bidirectional), OpenAI Whisper Streaming, Deepgram Streaming, ElevenLabs Streaming, mocks
  - Realtime STT: partial / stable / final hypotheses, confidence, language switch, timestamps, speaker tracking
  - Realtime TTS: audio chunks, incremental synthesis, buffer smoothing, provider cancellation
  - Failover: disconnect / network loss / timeout / retry / fallback / manual switch
  - Latency marks: mic, provider, brain, TTS, first audio, conversation turnaround
  - Stream performance controller: coalesce, buffer caps, bandwidth, sync skew
  - Diagnostics: `PROVIDER_*` / `PROVIDER_TRANSPORT_*` events
  - Config: `TITAN_VOICE_REALTIME_*`, transport / retry / Deepgram / ElevenLabs settings
  - Tests: `tests/test_voice_phase20_6.py`
  - Always-listening remains hard-disabled; UI unchanged; Trading/Obsidian untouched

## [0.50.0] — 2026-07-28

### Added

- **Phase 20.5 — Real-Time Voice Conversation Engine**
  - Continuous multi-turn conversation with idle / conversation timeouts + recovery tokens
  - Incremental STT stages: partial (UI-only) → stable → final (Brain-safe)
  - Streaming Brain adapter: response deltas, sentence completion, cancel, no duplicate turns
  - Streaming TTS: sentence streaming, FR/EN voice selection, barge-in cancel
  - Latency tracker: first audio / transcript / Brain token / TTS audio / idle delay
  - Stream diagnostics: `VOICE_STREAM_*`, `BRAIN_STREAM_*`, `TTS_STREAM_*`, idle/resume/recover/closed
  - Authenticated API: `/voice/session/recover`, `/heartbeat`, `/events`
  - Web client continuity: session reuse, refresh recovery, heartbeat, progressive TTS enqueue
  - Always-listening remains hard-disabled; text chat unchanged
  - Tests: `tests/test_voice_phase20_5.py`

## [0.49.0] — 2026-07-28

### Added

- **Phase 20.4 — Web App Voice UI & Real Microphone Integration**
  - Browser mic permission, PCM/MediaRecorder capture, push-to-talk composer control
  - Guided enrollment UI (consent, Nolan/Ibrahim, verify, revoke) in Voice panel
  - TTS playback queue + barge-in (`Interrompre`) wired to `/voice/session/*`
  - Safe identity badge + medium-confidence confirm/reject UI
  - Client diagnostics `VOICE_UI_*` (no raw audio / secrets)
  - Live session HTTP responses include ordered `tts_audio_chunks` for web playback
  - Tests: `tests/test_voice_phase20_4.py`

## [0.43.1] — 2026-07-15

### Added

- **Phase 10.2 — Railway production deployment packaging**
  - `railway.json` — Dockerfile builder, `/health` healthcheck, restart policy
  - `docs/RAILWAY_DEPLOYMENT.md` — beginner guide, env checklist, troubleshooting,
    final deploy checklist (Nolan deploys; agent does not)
  - Provider fixed to Railway; no app/Brain/UI/API behavior changes

### Changed

- Roadmap / README / `.env.example` / Phase 10.1 readiness doc point to Railway guide

## [0.43.0] — 2026-07-14

### Added

- **Web App Phase 9 — Cognitive Operating System** (frontend only)
  - Top-bar modules expose Idle · Reading · Searching · Planning · Reasoning ·
    Writing · Waiting · Finished from honest StateStore telemetry
  - Floating workspaces gain OS surfaces (confidence, scan, sync, network,
    attention, depth, engagement, focus, availability)
  - Cognitive Orchestrator gains Runtime Monitor (reasoning stage, queues,
    connected systems, tools, memory access, latency, model state)
  - `web/v2/core/cognitive-os-telemetry.js` — pure frontend resolver
  - `web/v2/design/cognitive-os.css` — visual authority (loaded last)
  - No redesign / new colors / neural rewrite; no fake backend execution
  - Docs: `docs/WEB_APP_COGNITIVE_OS.md`; tests: `tests/test_web_v2_cognitive_os.py`
  - Screenshots under `docs/design/screenshots/phase-9-cognitive-os-*.png`
  - UI version `0.48.0`

## [0.42.0] — 2026-07-14

### Added

- **Web App Phase 8 — Living Presence** (frontend only)
  - Titan Core: soft heartbeat, energy breathing, neural wave rings, micro attention
  - Satellite nodes: occasional slow light packets on non-repeating paths
  - Atmosphere: tiny particles, distant flashes, ambient brightness variation
  - Workspaces: calm idle + local wake on honest runtime activity
  - Orchestrator: pipeline pulses, objective breath, tiny activity markers
  - Presentation only — no layout/color/neural-renderer redesign; no fake execution
  - `web/v2/design/living-presence.css` — visual authority (loaded last)
  - Docs: `docs/WEB_APP_LIVING_PRESENCE.md`; tests: `tests/test_web_v2_living_presence.py`
  - Screenshots under `docs/design/screenshots/phase-8-living-presence-*.png`
  - UI version `0.47.0`

## [0.41.0] — 2026-07-14

### Added

- **Web App Phase 7 — Living Runtime Experience** (frontend only)
  - Top telemetry reacts to Idle · Thinking · Working · Searching · Remembering · Planning
  - Floating workspaces gain restrained living cues (scan, vault glow, shimmer, breath)
  - Global atmosphere: subtle ambient shift + quiet neural communication markers
  - Local UI only — reuses StateStore / CognitiveStateEngine; no fake backend
  - `web/v2/design/living-runtime.css` — visual authority (loaded last)
  - Docs: `docs/WEB_APP_LIVING_RUNTIME.md`; tests: `tests/test_web_v2_living_runtime.py`
  - Screenshots under `docs/design/screenshots/phase-7-living-runtime-*.png`
  - UI version `0.46.0`

## [0.40.0] — 2026-07-14

### Added

- **Web App Phase 6 — Living Cognitive Orchestrator** (frontend only)
  - Right panel rebuilt as living command center: Current Objective · Execution
    Pipeline · Active Tools (incl. Voice) · Neural Activity · Runtime Status
  - Deep smoked glass · quiet separators · breathing LIVE · restrained waveform
  - Footer reuses existing telemetry (`orchestrationDuration`, `connectionState`,
    `systemsUsed`, UI version) — no fabricated backend execution
  - `web/v2/design/living-orchestrator.css` — visual authority (loaded last)
  - Docs: `docs/WEB_APP_LIVING_ORCHESTRATOR.md`; tests: `tests/test_web_v2_living_orchestrator.py`
  - Screenshots under `docs/design/screenshots/phase-6-orchestrator-*.png`
  - UI version `0.45.0`

## [Unreleased]

### Added

- **Phase 20.3 — Live Voice Session Orchestration:**
  production session lifecycle connecting mic chunks → VAD → segmentation →
  speaker gate → STT → Brain → streamed response → TTS → playback.
  - `voice/live_session.py` — `LiveVoiceSessionOrchestrator`
  - `voice/vad.py` — configurable voice activity detection
  - `voice/speech_segmenter.py` — ordered utterance assembly + bounded buffers
  - `voice/session_lifecycle.py` — explicit IDLE…COMPLETED state machine
  - `voice/tts_strategy.py` — full-response / sentence-buffered TTS + markdown cleanup
  - `voice/diagnostics.py` — structured VOICE_* diagnostics (no raw audio/embeddings)
  - `api/voice_session_routes.py` — authenticated `/voice/session/*` API
  - WorkspaceState safe mirrors: `voice_session_state`, input level, speech detected,
    speaker, confidence band, transcription/brain/tts status, interrupted
  - Barge-in, identity confirm/reject with timeout, restricted unknown-speaker path
  - Wake-word / always-listening prepared but disabled by default
  - Settings: `TITAN_VOICE_VAD_*`, `TITAN_VOICE_TTS_STRATEGY`, identity/provider timeouts
  - Tests: `tests/test_voice_phase20_3.py`

- **Phase 20.2 — Voice Enrollment & Identity Profiles:**
  guided enrollment architecture for Nolan/Ibrahim without requiring real
  recordings in this phase.
  - `voice/voice_enrollment.py` — start/submit/validate/finish/verify/cancel/revoke
  - `voice/speaker_profile_store.py` — durable profiles (activate/deactivate/revoke/replace)
  - `voice/sample_validator.py` + `voice/enrollment_scripts.py` (FR/EN)
  - Recognition policy bands (high/medium/low/ambiguous); revoked profiles blocked
  - Authenticated API `/voice/enrollment/*`; WorkspaceState enrollment mirrors
  - Privacy: transient temp audio only; no embeddings in logs/LLM/Obsidian/memory
  - Settings: `TITAN_VOICE_ENROLLMENT_*`, medium confidence + ambiguity delta
  - Tests: `tests/test_voice_phase20_2.py` (Phase 20.1 suite still green)
  - Version `0.47.0`

- **Phase 20.1 — Voice Provider Integration & Speaker Recognition (foundation):**
  first architecture phase after production validation 19.7.
  - `voice/speaker_identifier.py` — Nolan/Ibrahim enrollment, voiceprint match,
    confirm-on-unknown before personal memory (Constitution Art. 1.5).
  - `voice/providers/` — OpenAI Whisper STT + OpenAI TTS adapters; registry bootstrap.
  - `VoiceRuntime` binds `SessionManager.current_user` on known speakers; unknown
    speakers receive a French confirmation prompt without `Brain.process_request()`.
  - Settings: `TITAN_VOICE_SPEAKER_ID_*`, `TITAN_VOICE_OPENAI_*_MODEL`.
  - Docs: `docs/VOICE_RUNTIME.md`, `docs/ROADMAP.md`.
  - Tests: `tests/test_speaker_identifier.py`, `tests/test_voice_phase20_1.py`.

- **Web App Phase 5.3 — Reference Scene Reconstruction** (frontend only)
  - Entire composition rebuilt around Titan Core as visual gravity (not a background)
  - Organic satellite orbits · major/secondary/synapse neural highways (SVG presentation)
  - Stronger cinematic atmosphere: volumetric fog, near/far particles, bloom, deep void
  - Quieter floating chrome so the mind reads before the interface
  - `web/v2/design/reference-scene.css` — visual authority (loaded last)
  - Docs: `docs/WEB_APP_PHASE53_REFERENCE_SCENE.md`; tests: `tests/test_web_v2_reference_scene.py`
  - UI version `0.43.0` — no Brain/API/neural engine logic changes

- **Web App Phase 4.3 — Pixel-Perfect Cognitive Orchestrator** (frontend only)
  - Right panel fidelity pass: large mission block, numbered pipeline with green completed /
    red active marks, elegant tool list (no oversized cards), restrained neural waveform
  - Deep smoked glass · heavier blur · larger padding · lighter type · soft dividers
  - Docs: `docs/WEB_APP_ORCHESTRATOR_PHASE43.md`; tests: `tests/test_web_v2_orchestrator_phase43.py`
  - Screenshots under `docs/design/screenshots/phase-4.3-orchestrator-*.png`
  - UI version `0.30.0` — no Brain/API/neural/sidebar/dock/composer changes

- **Web App Phase 4.2 — Cognitive Orchestrator Reconstruction** (frontend only)
  - `web/v2/design/orchestrator.css` — deep-glass command-center layer (loaded last)
  - Right panel rebuilt: Current Objective · Execution Pipeline · Active Tools · Neural Activity
  - Floating instrument cards (Obsidian, Memory, Browser, Trading, Calendar)
  - Soft neural waveform + pulses; honest idle (no fake busy execution)
  - Docs: `docs/WEB_APP_ORCHESTRATOR_PHASE4.md`; tests: `tests/test_web_v2_orchestrator_phase42.py`
  - Screenshots under `docs/design/screenshots/phase-4.2-orchestrator-*.png`
  - UI version `0.29.0` — no Brain/API/neural/sidebar/dock changes

- **Web App Sprint 2.9 — Living Cognitive OS** (frontend only)
  - `web/v2/design/presence.css` — calm presence layer (breathing glass, telemetry, composer console)
  - Cognitive Orchestrator **System Presence** idle richness (honest passive monitoring)
  - Top telemetry pills: Mémoire · Réflexion · Présence · Outils · Mode · Runtime
  - Floating glass workspace cards + premium command composer
  - Docs: `docs/WEB_APP_LIVING_COGNITIVE_OS.md`; tests: `tests/test_web_v2_presence_os.py`
  - Screenshots under `docs/design/screenshots/sprint-2.9-*.png`
  - UI version `0.26.0` — no Brain/API/neural renderer changes

## [0.39.0] — 2026-07-12

### Added

- **Proactive Intelligence V1** — ranked attention recommendations from existing context.
  - `brain/proactive_intelligence.py` — `ProactiveSignal`, `ProactiveRecommendation`,
    `ProactiveDigest`, `AttentionItem`, lifecycle persistence.
  - Brain APIs: `evaluate_proactive_context`, `get_proactive_digest`,
    `get_attention_items`, `acknowledge_recommendation`, `dismiss_recommendation`,
    `snooze_recommendation`, `complete_recommendation`.
  - NLO intent `PROACTIVE_ATTENTION` for "what needs my attention?" style queries.
  - Cognitive Loop read-only observation of proactive signals.
  - Reuses Executive Function, Workspace Awareness, Development Session, Memory,
    Reasoning Engine, Confirmation Gate — no parallel cognitive system.
  - Advisory only: never executes tools, never mutates missions or files.
  - Docs: `docs/PROACTIVE_INTELLIGENCE.md`; architecture updated.
  - Tests: `tests/test_proactive_intelligence.py`.

## [0.38.0] — 2026-07-10

### Added

- **Reasoning Engine V1** — dedicated multi-step structured thinking before planning or execution.
  - `brain/reasoning_models.py` — `ReasoningResult`, `ReasoningStep`, `ReasoningAlternative`, `ReasoningRisk`, `ReasoningAssumption`, `ReasoningQuestion`, `ReasoningRecommendation`, `ReasoningSummary`.
  - `brain/reasoning_engine.py` — six-stage pipeline (understand, context, decompose, alternatives, evaluate, recommend); never executes tools.
  - Brain APIs: `reason`, `compare_options`, `evaluate_request`, `detect_missing_information`, `recommend_strategy`, `reason_about_project`.
  - NLO awareness phase runs reasoning before Executive Function; artifacts include serialized `ReasoningResult`.
  - Executive Function consumes `ReasoningResult` instead of duplicating general analysis.
  - Long-Term Planner optionally enriches plans from `ReasoningResult`.
  - Reuses Workspace Awareness, Memory, Mission Runtime, Development Session, Project Intelligence, Code Intelligence, Capability Registry.
  - Docs: `docs/REASONING_ENGINE.md`; architecture updated.
  - Tests: `tests/test_reasoning_engine.py`.

## [0.37.0] — 2026-07-10

### Added

- **Capability Registry & Dynamic Tool Discovery V1** — shared self-describing tool metadata for the core tool runtime.
  - `core/tools/capability_models.py` — `CapabilityRecord`, `ActionDescriptor`, validation.
  - `core/tools/capability_registry.py` — register/search/summarize/export; no second loader or runtime.
  - Extended `BaseTool` with author, tags, risk, execution traits, schemas, and status defaults.
  - `ToolRegistry` syncs capability metadata on register/unregister via attached `CapabilityRegistry`.
  - `ToolLoader` discovery automatically publishes metadata — new `core/tools/<name>/` folders need no Brain changes.
  - Brain APIs: `list_capabilities`, `search_capabilities`, `find_tools_for_task`, `describe_tool`, `summarize_installed_tools`.
  - `ToolIntelligence` consumes the shared registry for discovery queries.
  - `CoreToolRuntime` includes `capability_registry` for composition-root wiring.
  - Serializable `export()` payload prepared for future Settings UI.
  - Docs: `docs/CAPABILITY_REGISTRY.md`; architecture updated.
  - Tests: `tests/test_capability_registry.py`.

## [0.36.0] — 2026-07-10

### Added

- **Web Runtime V1** — end-to-end integration of `web/v2/` with `Brain.process_request()`.
  - Canonical authenticated endpoint: `POST /api/chat/message` with structured orchestration response.
  - `api/chat_service.py` — thread-safe shared Brain delegation, approval detection, safe serialization.
  - `api/chat_models.py` — request/response schemas with size validation (`TITAN_WEB_MAX_MESSAGE_LENGTH`).
  - Legacy routes `/chat` and `/chat/stream` now route through NLO (not raw `think()`).
  - SSE enrichment: `orchestration_started`, `orchestration_finished`, `approval_required` events.
  - Frontend: conversation id persistence, retry, approval banner, dev metadata, duplicate-submit guard.
  - `Brain.process_request(stream=)` and NLO stream forwarding for conversation intents.
  - Docs: `docs/WEB_RUNTIME.md`; architecture updated; tests: `tests/test_web_runtime.py`, `tests/test_web_v2_frontend.py`.

### Changed

- `web/static/` documented as legacy/deprecated — `web/v2/` remains sole production frontend.

## [0.35.0] — 2026-07-10

### Added

- **Voice Runtime V1** — real-time spoken conversation as an external Brain interface (never bypasses `Brain.process_request()`).
  - New `voice/` modules: `voice_runtime.py`, `speech_to_text.py`, `text_to_speech.py`, `voice_session.py`, `audio_devices.py`, `models.py`, `exceptions.py`.
  - Provider-agnostic STT/TTS registries with mock providers for CI; future OpenAI, Whisper, Deepgram, ElevenLabs, Azure, Piper via registration.
  - Persistent voice sessions (`data/voice_sessions.json`): conversation id, devices, language, history, latency metrics, duration.
  - Conversation modes: single-shot, continuous, push-to-talk; wake-word mode reserved.
  - Interruptions: cancel speech, stop playback, queue/flush responses.
  - Voice state machine: idle, listening, thinking, speaking, paused, error.
  - Settings: `TITAN_VOICE_STT_PROVIDER`, `TITAN_VOICE_TTS_PROVIDER`, `TITAN_VOICE_MICROPHONE`, `TITAN_VOICE_SPEAKER`, `TITAN_VOICE_SILENCE_TIMEOUT`, `TITAN_VOICE_CONVERSATION_MODE`, `TITAN_VOICE_SESSIONS_PATH`, `TITAN_VOICE_VOLUME`, `TITAN_VOICE_VOICE`.
  - Docs: `docs/VOICE_RUNTIME.md`; architecture updated; tests: `tests/test_voice_runtime.py`.

## [0.34.0] — 2026-07-10

### Added

- **Natural Language Orchestrator V1** — Brain front door that turns natural language into the correct sequence of existing Brain systems (orchestration only; zero direct tool/code execution).
  - New `brain/natural_language_orchestrator.py` with `NaturalLanguageOrchestrator`, `DetectedIntent`, `RequestAnalysis`, `PipelineDecision`, `SystemsUsed`, `OrchestrationResult`.
  - Brain API: `process_request(message)` — primary high-level entry point; `think()` remains the cognitive pipeline for conversation.
  - Intent routing: conversation, question, research, planning, architecture, project analysis, code explanation/planning/generation, patch preview/application, workspace, mission, memory, tool request, development continuation.
  - Conversation awareness on every request (context, workspace, memory, missions, development session, executive function); developer-mode enrichment when relevant.
  - Delegates only — never edits code, never bypasses permissions, never mutates the repo itself.
  - Docs: `docs/NATURAL_LANGUAGE_ORCHESTRATOR.md`; architecture diagram updated; tests: `tests/test_natural_language_orchestrator.py`.

## [0.33.0] — 2026-07-10

### Added

- **Long-Term Planning Engine V1** — transform a high-level objective into a structured multi-level project plan (planning only; zero execution).
  - New `brain/long_term_planner.py` with `LongTermPlanner`, `GoalPlan`, `ProjectPlan`, `Milestone`, `Task`, `SubTask`, `Dependency`, `PlanningRisk`, `PlanningRecommendation`, `PlanningSummary`, `MissionProposal`.
  - Brain API: `plan_goal()`, `expand_goal()`, `review_plan()`, `recalculate_plan()`.
  - Detects parallel/sequential work, critical path, quick wins, high/low risk, and task kinds (research, implementation, testing, documentation, deployment).
  - Executive Function: `recommend_next_from_goal_plan()` — recommends next work from a `GoalPlan` without modifying it.
  - Mission Runtime: emits compatible `MissionProposal`s only — never auto-creates missions.
  - Reuses Workspace Awareness, Project Intelligence, Developer Workflow, Memory, and Context.
  - Docs: `docs/LONG_TERM_PLANNER.md`; tests: `tests/test_long_term_planner.py`.

## [0.32.0] — 2026-07-10

### Added

- **Controlled Patch Application V1** — apply a previously generated `GeneratedPatch` only after explicit human approval, with atomic backups and rollback.
  - New `core/tools/code_editor/` package: `CodeEditorTool`, `PatchValidator`, `PatchApplier`, serializable models.
  - Actions: `validate_patch`, `preview_patch`, `apply_patch`, `rollback_patch`.
  - Permissions: `code_editor.validate` / `preview` (SAFE); `code_editor.apply` / `rollback` (CONFIRMATION_REQUIRED).
  - Backups under `.titan/backups/<transaction_id>/` with transaction manifests (paths/hashes only — no secrets).
  - Brain API: `validate_generated_patch()`, `preview_generated_patch()`, `apply_generated_patch(confirmed=...)`, `rollback_patch(confirmed=...)`.
  - `GeneratedPatch.approved` + `with_approval()` for patch-level human approval.
  - Development Session records validation / application / rollback without ending the session.
  - Docs: `docs/CONTROLLED_PATCH_APPLICATION.md`; tests: `tests/test_controlled_patch_application.py`.

## [0.31.0] — 2026-07-10

### Added

- **Development Session Runtime V1** — persistent coding-session context tracker (track only; never executes tools, never writes repo files, never applies patches).
  - New `brain/development_session.py` with `DevelopmentSessionRuntime`, `DevelopmentSession`, `SessionSummary`, `SessionDecision`, `PendingTask`, `CompletedTask`, `SessionState`.
  - Brain API: `start_development_session()`, `update_development_session()`, `pause_development_session()`, `resume_development_session()`, `end_development_session()`, `summarize_development_session()`, `get_development_session()`.
  - Optional `record_to_session=True` hooks on workflow / code-plan / generate / workspace / explain APIs.
  - Persistence: `data/development_sessions.json`.
  - Reuses Workspace Awareness, Executive Function, Mission Runtime, Developer Workflow, Code Modification Planner, Code Generation Engine, Memory, and Context.
  - Docs: `docs/DEVELOPMENT_SESSION.md`; tests: `tests/test_development_session.py`.

## [0.30.0] — 2026-07-10

### Added

- **Project Intelligence V1** — architectural understanding of Titan’s own codebase (analysis only; never modifies code or executes tools).
  - New `brain/project_intelligence.py` with `ArchitectureSummary`, `DependencyGraph`, `FeatureLocation`, `ImpactAnalysis`, `ModuleDescription`.
  - Brain API: `analyze_project()`, `find_feature()`, `explain_module()`, `analyze_change_impact()`.
  - Reuses Workspace Awareness, Executive Function, Mission Runtime, Memory, and `context/workspace_map` — does not create a second planner.
  - Docs: `docs/PROJECT_INTELLIGENCE.md`; tests: `tests/test_project_intelligence.py`.

## [0.29.0] — 2026-07-09

### Added

- **Developer Workflow V1** — structured, workspace-aware software-development planning for the Brain (plan only; no autonomous coding or command execution).
  - `brain/developer_workflow.py` — `DeveloperWorkflow` + `DeveloperWorkflowPlan` (goal, context, relevant files, tools/commands, test plan, risk, next steps, confirmation).
  - Brain API: `plan_development_workflow(message)`.
  - Integrates Workspace Awareness, Executive Function, Mission Runtime, Tool Intelligence, and Memory without calling Tool Execution Engine.
  - `docs/DEVELOPER_WORKFLOW.md` and `tests/test_developer_workflow.py`.

## [0.28.0] — 2026-07-09

### Added

- **Workspace Awareness V1** — explicit, on-demand development-environment context for the Brain (no watchers, no polling, no tool execution).
  - `brain/workspace_awareness.py` — `WorkspaceAwareness` + `WorkspaceSnapshot` (project, modules, docs, git branch, recent files, active missions, advisory recommendations).
  - Brain API: `get_workspace()`, `refresh_workspace()`.
  - Wired into Executive Function (mission relevance) and Cognitive Loop (`workspace` observations/thoughts).
  - `docs/WORKSPACE_AWARENESS.md` and `tests/test_workspace_awareness.py`.

## [0.27.0] — 2026-07-09

### Added

- **Executive Function V1** — read-only mission attention layer that ranks active missions and recommends focus before cognition/execution.
  - `brain/executive_function.py` — priority scoring (priority, age, progress, state, request relevance, blocked duration), blocked/idle detection, switch recommendations.
  - Brain API: `get_current_focus()`, `evaluate_missions()`, `recommend_focus()`.
  - Cognitive Loop observes executive recommendations (`executive_function` source) without mutating missions or executing tools.
  - `docs/EXECUTIVE_FUNCTION.md` and `tests/test_executive_function.py`.

### Changed

- `Brain.generate_thoughts()` evaluates missions via Executive Function before running the Cognitive Loop.

## [0.26.0] — 2026-07-07

### Added

- **Mission Runtime V1** — long-running objective state management (explicit execution only; no background workers).
  - `core/mission_models.py` — `Mission`, `Goal`, `Task`, `MissionState`, `MissionProgress`, history entries.
  - `core/mission_runtime.py` — lifecycle engine: create, resume, update, complete, fail, cancel, tool-execution hooks.
  - Schema v3 migration in `core/mission_migrator.py` — multi-mission `missions` map with v2 backward-compatible flat view.
  - Brain API: `create_mission()`, `resume_mission()`, `update_mission()`, `complete_mission()`, `list_active_missions()`, `get_mission_progress()`.
  - Cognitive Loop mission observations and step-focus thoughts.
  - Automatic mission progress recording on `Brain.execute_request()` completion.
  - `docs/MISSION_RUNTIME.md` and `tests/test_mission_runtime.py`.

### Changed

- `MissionManager` delegates to `MissionRuntime` while preserving REPL commands and Brain pipeline compatibility.
- `brain/brain.py` — fixed `MissionManager` import; cognitive loop receives mission manager after DI fix.

## [0.25.0] — 2026-07-06

### Added

- **Phase E10 — Titan Frontend V2 Production Release:** polish, stabilize, and prepare `web/v2` for long-term evolution without redesign or architecture changes.
  - `web/v2/core/version.js` — single frontend version source aligned with backend `VERSION`.
  - `web/v2/core/extension-registry.js` — reserved extension hooks for Voice, Trading, Browser, Obsidian, Calendar, Projects, Agents, Plugins, Multi-user, Mobile.
  - Live sidebar telemetry (FPS, cognition label, active tool chips) wired to `CognitiveStateEngine` and `StateStore`.
  - Live presence ring in status dock driven by `presenceLevel` from cognitive state.

### Changed

- Dev globals (`window.__TITAN_*`) gated behind `?dev=1` or `localStorage titan-v2-dev=1`.
- Neural stage resize delegated to `NeuralEngine` only (removed duplicate window listener).
- `bootComplete` set once via render pipeline stagger completion.
- Sidebar version label syncs from backend SSE `systemVersion` when available.

### Removed

- Deprecated simulation APIs: `startSimulation`, `startToolSimulation`, `startMemorySimulation`, `runPipeline`, `cycleDemoState`.
- Dead modules: `panels/stubs/`, unused hooks (`use-brain`, `use-app-state`, `use-router`, `use-subscription`), `components/panel-slot`, `components/region-host`, `animation/presence-transitions.js`.
- Unused `CONVERSATION_PIPELINE_DELAYS` constant.

## [Unreleased]

### Added

- **Phase 24.0 — Cognitive Orchestrator:** Titan's decision engine — plan before execute.
  - `brain/cognitive_orchestrator.py` — `CognitiveOrchestrator` with `create_plan`, `execute_plan`, `verify_plan`, `retry_step`, `cancel_plan`, `resume_plan` (camelCase aliases for external bridges).
  - `brain/cognitive_models.py` — `TaskGraph`, `CognitivePlan`, `PlanRuntimeState`, `CognitiveExecutionResult`.
  - `brain/cognitive_progress.py` — sanitized high-level progress labels; auto-registration hook for future tools.
  - Architecture: Intent Analysis → Planner → Task Graph → Tool Selection → Execution → Verification → Response.
  - `ToolManager` remains execution layer; `CognitiveOrchestrator` is intelligence layer — Brain no longer dispatches tools directly.
  - `core/execution_coordinator.py` — routes all tool execution through cognitive orchestrator.
  - `api/orchestrator_progress.py` — high-level progress timeline for web UI (no chain-of-thought).
  - `/chat` response includes `orchestrator_progress`; neural activity maps to Planning, Memory, Research, Writing, Verification, Idle.
  - Future-ready: parallel node detection, suspend/resume, cancel, retry.
  - Tests: `tests/test_cognitive_orchestrator.py`.

- **Phase 23.0 — Browser Intelligence:** Browser as Titan's second real external tool — a cognitive web exploration capability, not a browser UI.
  - `tools/browser_intelligence.py` — `BrowserIntelligenceService` orchestrates search, page reading, multi-source comparison, structured excerpts, and numbered citations; Brain retains synthesis authority.
  - `tools/connectors/browser_models.py` — `BrowserSource`, `BrowserResearchResult` for structured research payloads.
  - `tools/decision/browser_decision.py` — routes `research_web`, `compare_sources`, `read_article` from natural language.
  - `tools/browser_tool.py` — intelligence actions wired through connector boundary; web search bridged via `default_tools.register_default_tools()`.
  - Brain pipeline tracks `browser_exploring` / `browser_source_labels` in `ThinkContext` for Exploration UI (mirror Obsidian Phase 22 pattern).
  - `api/tool_activity.py` — Exploration timeline: Navigation web → Recherche → Analyse → Synthèse; sanitized source cards.
  - Web UI — Exploration cognitive state (`browser_research` neural signature), distributed exploration waves, subtle floating source cards, Exploration nav view.
  - Tests: `tests/test_browser_phase23.py`.

- **Phase 20.1 — Living Workspace:** spatial reorganization of the web interface — Titan as a neural headquarters, not a dashboard.
  - Full-viewport neural field (`tdl-neural-stage--viewport`) remains visible behind all panels; Canvas2D only, 60 FPS target preserved.
  - Orbital floating panels with glass surfaces, subtle depth shadows, no hard borders, smooth transitions.
  - Visual hierarchy: Neural Brain → Titan Presence → Conversation → Projects → Memory → Tools.
  - `web/static/index.html` — Living Workspace shell; context rail decomposed into independent orbital panels.
  - `web/static/design/tokens.css` — workspace spacing, orbit panel shadows, lighter glass surfaces.
  - `web/static/design/titan-ui.css` — Phase 20.1 orbital layout, presence strip, responsive panel stacking.
  - `web/static/neural/brain_engine.js` — viewport-aware resize for full-screen neural stage.
  - `web/static/neural/brain_renderer.js` — soft radial panel occlusion (replaces sidebar/rail hard masks).
  - `web/static/app.js` — orbit panel focus on view change; workspace root for presence/launch.
  - Tests: Living Workspace markers in `tests/test_web_api.py`.

- **Phase 18.0 — Titan Final Polish:** unified premium experience across the web interface — no new features, polish only.
  - `web/static/design/motion.js` — single easing source (CSS + JS), reduced-motion detection, accessibility prefs, neural color sync from tokens.
  - `web/static/design/sound_hooks.js` — optional audio architecture (startup, thinking, notification, voice fade) — hooks only, no sounds.
  - `web/static/design/launch_sequence.js` — sub-2s startup: brain wake, ambient glow, « Bonjour Nolan. » → « Je suis prêt. »
  - Visual consistency: unified panel surfaces, transitions, micro-interactions, depth haze, panel occlusion on neural canvas.
  - Neural heartbeat: presence profile drives brain intensity; frame pacing and hidden-tab pause; reduced-motion throttling.
  - Accessibility: keyboard nav for sidebar, high-contrast mode, font scaling, reduced-motion toggle in Settings.
  - French status bar labels; responsive tokens for ultra-wide viewports.
  - Tests: Phase 18 asset coverage in `tests/test_web_api.py`.

- **Phase 17.9 — Titan Memory Visualization:** living memory recall in the web interface.
  - `web/static/memory/` — event-driven memory experience (`memory_events.js`, `memory_activity.js`, `memory_cards.js`, `memory_visualizer.js`).
  - `api/memory_activity.py` — sanitized `memory_activity` on `/chat` (no raw note text or internals).
  - Per-source neural wave patterns; floating memory cards; ambient idle consolidation.
- **Phase 17.8 — Titan Voice Interface V1:** first integrated voice layer for the web interface.
  - `voice/voice_manager.py` — provider-independent voice configuration facade.
  - `web/static/voice/` — `voice_events.js`, `speech_input.js`, `speech_output.js`, `voice_controller.js`.
  - Push-to-talk mic in composer; optional continuous listening in Settings.
  - Streaming TTS synced with chat text; interrupt stops speech and generation.
  - Presence `speaking` state; neural rhythm pulses during speech; listening ripple on brain stage.
  - API: `GET /voice/status`; config via `TITAN_VOICE_*` settings.
  - Tests: `tests/test_voice_manager.py`, voice route coverage in `tests/test_web_api.py`.

- **Phase 17.3 — Titan Interface V1:** first living web interface using Titan Design Language.
  - `web/static/index.html` — three-column layout: navigation, neural center, context panels, status bar.
  - `web/static/neural-network.js` — canvas neural network (drift, pulse, connections, thinking mode).
  - `web/static/app.js` — chat, auth (localStorage), view switching, status polling, context panels.
  - `web/static/design/titan-ui.css` — Phase 17.3 app layout components (nav, chat, context rail, status bar).
  - `web/static/design/tokens.css` — layout tokens for context width and status bar.
  - Placeholders only: Browser, Calendar, Trading views (no voice, no trading UI).
  - Tests: `test_index_serves_titan_interface_v1` in `tests/test_web_api.py`.
  - Docs: `docs/TITAN_DESIGN_LANGUAGE.md`, `docs/WEB_APP.md` updated.

- **Phase 17.1 — Titan Private Web App Foundation:** local FastAPI layer over Titan Core with optional web UI.
  - `api/app.py` — FastAPI routes: `/health`, `/chat`, `/status`, `/tools`, connector status endpoints.
  - `api/auth.py` — Bearer token auth via `TITAN_WEB_SECRET_KEY`; `/health` public.
  - `api/titan_service.py` — shared Titan instance; chat routes through `Brain.think()`.
  - `core/web_cli.py` — `python main.py web` starts uvicorn on localhost.
  - `web/static/` — minimal HTML/JS placeholder (name, status, chat, tool list).
  - Config: `TITAN_WEB_ENABLED=false`, `TITAN_WEB_HOST=127.0.0.1`, `TITAN_WEB_PORT=8000`, `TITAN_WEB_SECRET_KEY=`.
  - Dependencies: `fastapi`, `uvicorn`, `httpx`.
  - Tests: `tests/test_web_api.py`.
  - Docs: `docs/WEB_APP.md`; README updated.

- **Phase 16.5 — Apex/Rithmic Read-Only Adapter Foundation:** credential validation scaffold for future Apex/Rithmic trading environment in read-only mode.
  - `ApexRithmicProvider` (`tools/connectors/apex_rithmic_provider.py`) — extends `ReadOnlyBrokerProvider`; no Rithmic SDK imports, no live connections.
  - Read operations scaffolded: `list_accounts`, `account_status`, `get_positions`, `get_orders`, `get_balance`, `get_market_status`, `get_pnl`, `get_margin` (unavailable until SDK phase).
  - Write operations always blocked: `place_order`, `modify_order`, `cancel_order`, `flatten_position` — even with `confirmed=true`.
  - Config: `TITAN_BROKER_PROVIDER`, `TITAN_RITHMIC_ENABLED`, `TITAN_RITHMIC_USERNAME`, `TITAN_RITHMIC_PASSWORD`, `TITAN_RITHMIC_SYSTEM`, `TITAN_RITHMIC_SERVER`, `TITAN_RITHMIC_APP_NAME`, `TITAN_RITHMIC_APP_VERSION`.
  - Readiness reports: `provider_disabled`, `credentials_missing`, `scaffold_ready`, read-only active, execution disabled.
  - Broker health CLI extended with `TITAN_BROKER_PROVIDER`, `TITAN_RITHMIC_ENABLED` flags.
  - Tests: `tests/test_apex_rithmic_provider.py`.
  - `docs/TRADING.md` updated for Phase 16.5.

- **Phase 16.4 — Broker Provider Read-Only Foundation:** read-only base and real broker stubs.
  - `ReadOnlyBrokerProvider` — blocks all write operations on real providers.
  - `real_broker_stubs.py` — Apex, Rithmic, Tradovate, NinjaTrader credential readiness stubs.
  - `TITAN_BROKER_READ_ONLY=true` — required for real broker provider selection.
  - `python main.py broker-health` — safety and readiness CLI.
  - Tests: `tests/test_broker_read_only.py`.

- **Phase 16.3 — Broker Connector V1 (Paper Trading):** dedicated broker execution architecture with paper-only provider.
  - `BrokerConnector` / `BrokerProvider` abstraction — `TradingSignal → TradingConnector → BrokerConnector → BrokerProvider`.
  - `PaperBrokerProvider` — in-memory paper trading with simulated fills (list accounts, positions, orders, balance, market status; place/modify/cancel/flatten).
  - `BrokerOrder` model — `order_id`, `account_id`, `symbol`, `market`, `side`, `order_type`, `quantity`, `entry_price`, `stop_loss`, `take_profit`, `status`, `timestamp`, `source_signal_id`, `warnings`.
  - `signal_to_order.py` — `draft_order_from_signal()` converts `TradingSignal` to order draft without execution.
  - Actions: `draft_order_from_signal`, `execute_signal_order` (confirmation required for all write ops, even in paper mode).
  - Live mode blocked — `TITAN_TRADING_MODE=paper`, `TITAN_TRADING_LIVE_ENABLED=false`; Apex/Rithmic/Tradovate/NinjaTrader rejected at factory.
  - `MockTradingProvider` refactored as adapter over `PaperBrokerProvider`.
  - Tests: `tests/test_broker_connector.py` (19 tests).
  - `docs/TRADING.md` updated for Phase 16.3 architecture.

- **Phase 14.2 — Google Calendar Backend:** real Google Calendar integration via provider-independent backend injection.
  - `GoogleCalendarProvider` — list/read/search/create/update/delete events, detect conflicts, find free time.
  - `google_oauth.py` — local OAuth setup flow; token stored at `TITAN_GOOGLE_TOKEN_PATH`.
  - `calendar_backend_factory.py` — selects mock or Google backend from config.
  - Config: `TITAN_CALENDAR_PROVIDER`, `TITAN_GOOGLE_CALENDAR_ENABLED`, `TITAN_GOOGLE_CLIENT_SECRET_PATH`, `TITAN_GOOGLE_TOKEN_PATH`.
  - CLI: `calendar-health`, `calendar-auth`, `calendar-list`, `calendar-smoke-test`.
  - `google-api-python-client`, `google-auth`, `google-auth-oauthlib` in `requirements.txt`.
  - Tests with mocked Google Calendar API: `tests/test_google_calendar_provider.py`, `tests/test_calendar_cli.py`.
  - `docs/CALENDAR.md` and README updated for OAuth setup.

- **Phase 14.1 — Calendar Connector Foundation:** provider-independent calendar connector on in-memory mock backend.
  - `CalendarConnector`, `CalendarTool`, `CalendarDecisionEngine`, permission tiers, Brain routing.
  - `docs/CALENDAR.md` architecture documentation.

- **Phase 13.3 — Browser Interaction V1:** controlled browser actions on Playwright backend via `BrowserConnector` only.
  - New actions: `click_element`, `type_text`, `select_option`, `scroll_page`, `go_back`, `open_new_tab`, `close_tab`, `wait_for_element`, `take_screenshot`.
  - `BrowserActionResult` structured outcome (action, selector, status, permission_level, executed, confirmation_required, message, current_url, page_title, warnings).
  - `tools/connectors/browser_permissions.py` — shared permission tiers for connector and `PermissionManager`.
  - Permission gating: auto-allowed scroll/back/wait/screenshot; confirmation-required click/type/select/tabs; blocked unsafe/hidden clicks and credential entry without approval.
  - `tests/test_browser_interactions.py` — action routing, permissions, mocked interactions, confirmation gate.
  - `docs/BROWSER.md` updated for Phase 13.3.

- **Phase 13.2 — Playwright Browser Backend:** replaces HTTP fetch with Playwright Chromium while preserving `BrowserConnector` API.
  - `tools/connectors/browser_session.py` — `BrowserSession` (launch, close, new page, navigate, read title/URL/text).
  - `tools/connectors/browser_backend.py` — `PlaywrightBrowserBackend`, `FetchBrowserBackend` (test injection).
  - `TITAN_BROWSER_HEADLESS` configuration; Playwright in `requirements.txt`.
  - `python main.py browser-health` validates Playwright launch and permissions.
  - `tests/test_browser_session.py` — session and backend unit tests.
  - `docs/BROWSER.md` updated for Phase 13.2.

- **Phase 12.8 — Core Consolidation Sprint:** architecture cleanup before Browser and other external tools.
  - `core/execution_context.py` — neutral `ExecutionDispatchContext` and `build_tool_execution_context` (breaks `tools/` → `brain/` import cycle).
  - `tools/tool_executor.py` — single tool invocation path shared by orchestrator and dispatcher.
  - `tools/permission_facade.py` — unified caller + action permission evaluation (replaces triple evaluation in runtime preflight).
  - `tools/default_tools.py` — central built-in tool registration (`register_default_tools`).
  - `docs/ARCHITECTURE.md` — official execution path and layer responsibilities.
  - `tests/test_consolidation.py` — regression guards for unified paths and layer boundaries.

### Changed

- **Phase 12.8 — execution path unification:**
  - `ExecutionCoordinator._run_agents()` delegates to `TaskOrchestrator.orchestrate(max_agents=…)` — single agent dispatch source.
  - `ExecutionCoordinator._run_multi_step_task()` routes each step through `ToolOrchestrator` (not raw `ToolDispatcher`).
  - `ToolOrchestrator._execute_via_manager()` uses `tools/tool_executor.execute_tool()`.
  - `ToolDispatcher` simplified to formatting + unified executor (production tools flow through orchestrator).
  - `ToolRuntime._preflight()` uses `PermissionFacade.evaluate()` once per invocation.
  - `ToolManager._register_defaults()` delegates to `tools/default_tools.py`.
  - `brain/tool_execution_bridge.py` re-exports from `core/execution_context` for backward compatibility.
  - `ExecutionCoordinator` defers reasoning-loop clarification when decision engine or workspace routing is authoritative.

- **Obsidian production readiness sprint:** vault validation, CLI health/smoke commands, and Brain-flow regression tests.
  - `tools/connectors/obsidian_validator.py` — validates `TITAN_OBSIDIAN_ENABLED`, `TITAN_OBSIDIAN_VAULT_PATH`, vault existence, readability, writability, and safe path; never creates a vault.
  - `core/obsidian_cli.py` — `python main.py obsidian-health` and `python main.py obsidian-smoke-test` manual test modes.
  - Smoke test exercises list → create → read → patch → search → delete on a temporary note; confirms vault unchanged afterward.
  - Clear French errors for: Obsidian disabled, missing path, invalid path, vault not found, read-only vault, unsafe system path, delete requiring confirmation.
  - `config/settings.py` loads `.env` via `load_dotenv()` before reading `TITAN_*` variables.
  - Natural-language routing improvements for vault health and note search phrasing.
  - Regression tests: `tests/test_obsidian_validator.py`, `tests/test_obsidian_cli.py`, `tests/test_obsidian_brain_flow.py`.
  - README Obsidian setup section with exact `.env` and validation commands.

- **Phase 12.6 Batch 3 — Reasoning Loop:** Titan critically reviews structured execution plans before tool orchestration and applies safe optimizations.
  - `ReasoningLoop` evaluates missing steps, redundant steps, execution order, tool selection, dependency consistency, permission consistency, simplification opportunities, and clarification needs.
  - `ReviewedPlannerResult` wraps `PlannerResult` with `confidence_score`, `reasoning_summary`, `clarification_required`, and `optimization_count`.
  - Safe improvements applied automatically (duplicate removal, dependency cleanup, order correction, permission resync, Obsidian search-before-create when query is known); clarification requested when required parameters are missing — never inventing missing facts.
  - `ExecutionCoordinator` flow: Brain reasoning → NaturalLanguagePlanner → ReasoningLoop → ToolOrchestrator → PermissionManager → ToolManager → ToolRuntime.
  - Regression tests in `tests/test_reasoning_loop.py`.

- **Phase 12.6 Batch 2 — Natural Language Planner:** Titan transforms complex user requests into structured multi-step execution plans before tool orchestration.
  - `NaturalLanguagePlanner` breaks requests into ordered steps with objectives, reasoning, tool mapping, permission estimates, dependencies, conditional steps, and fallback steps.
  - `planner_models.py` — `PlanStep`, `PlanStepKind`, `ExecutionPlan` (reusable plan object), `PlannerResult` with `overall_goal`, `plan_summary`, `total_steps`, `estimated_tools`, `requires_confirmation`, and `execution_order`.
  - `ToolOrchestrator.orchestrate_plan()` executes plans in dependency order with fallback support.
  - `ExecutionCoordinator` flow: Brain reasoning → Planner → ReasoningLoop → ToolOrchestrator → PermissionManager → ToolManager → ToolRuntime.
  - Regression tests in `tests/test_natural_language_planner.py`.

- **Phase 12.6 Batch 1 — Tool Orchestrator and Permission Manager foundation:** Titan now evaluates action safety and coordinates tool execution before dispatch.
  - `PermissionManager` with levels `AUTO_ALLOWED`, `CONFIRMATION_REQUIRED`, and `BLOCKED`; default rules for read/search/update, Obsidian-gated create, delete, bulk, external communication, trading, and unsafe filesystem actions.
  - `ToolOrchestrator` receives interpreted requests, resolves actions, checks permissions, routes through `ToolManager`/`ToolRuntime`, and returns structured `ToolOrchestrationResult`.
  - `orchestration_models.py` — `InterpretedToolRequest`, `OrchestrationStatus`, `ToolOrchestrationResult`.
  - `ToolRuntime` pre-flight and confirmation gates integrate `PermissionManager` before execution.
  - `ExecutionCoordinator` routes tool dispatch through `ToolOrchestrator`.
  - Regression tests in `tests/test_permission_manager.py` and `tests/test_tool_orchestrator.py`.

- **Phase 12.5 Batch 3 — Intelligent vault maintenance:** Titan maintains the user's existing Obsidian vault as a knowledge assistant, not a blunt file editor.
  - `markdown_parser.py` — structural awareness: headings, lists, checklists, code blocks, callouts, wikilinks, tags, YAML frontmatter.
  - `markdown_editor.py` — formatting-preserving updates: `append`, `prepend`, `insert_under_heading`, `replace_section`, `update_checklist`, `update_table`, plus full `replace`.
  - `vault_analyzer.py` — organization analysis and structured `VaultHealthReport`: duplicated topics, merge suggestions, orphan/empty/abandoned notes, missing tags, folder placement, naming inconsistencies.
  - Connector actions: `patch_note`, `vault_health`; `update_note` delegates to patch when `update_mode` is set.
  - `ObsidianDecisionEngine` prefers `patch_note` (append by default) over full replace; new `VAULT_HEALTH` and `PATCH_EXISTING_NOTE` decisions.
  - Recommendations only — no automatic deletion or merging.
  - Regression tests in `tests/test_obsidian_vault_maintenance.py` (29 cases).

- **Phase 12.5 Batch 2 — Obsidian decision layer:** Titan now decides when and how to use the user's existing Obsidian vault.
  - `ObsidianDecisionEngine` with decisions: `DO_NOT_USE_OBSIDIAN`, `READ_EXISTING_NOTE`, `UPDATE_EXISTING_NOTE`, `CREATE_NEW_NOTE`, `SEARCH_NOTES`.
  - Cleanliness rules block casual, ephemeral, and joke content from vault writes; allow projects, goals, documentation, procedures, and durable knowledge.
  - Search-before-create: existing relevant notes are updated instead of duplicated.
  - `search_notes` connector action with modes: `filename`, `keyword`, `tag`, `folder`.
  - `Intent.OBSIDIAN` routing through Tool Decision Engine and Brain reasoning pipeline.
  - Regression tests in `tests/test_obsidian_decision.py`.

- **Phase 12.5 Batch 1 — Obsidian external connector:** first official user-owned external tool connector pattern under `tools/connectors/`.
  - `BaseExternalConnector` reusable base for bounded vault roots.
  - `ObsidianConnector` with safe vault operations: `read_note`, `create_note`, `update_note`, `delete_note`, `create_folder`, `list_notes`.
  - `ObsidianTool` registered in `ToolManager` with policy allowlists for Brain, coding, and research agents.
  - `vault_path_guard` blocks path traversal outside the configured vault.
  - Configuration: `TITAN_OBSIDIAN_ENABLED`, `TITAN_OBSIDIAN_VAULT_PATH` in `config/settings.py` and `.env.example`.
  - Regression tests in `tests/test_obsidian_tool.py`.

### Changed

- **Obsidian smart updates (Batch 3):** existing-note writes default to `patch_note` append mode; decision layer routes vault health requests to `vault_health`.
- **Obsidian usage policy:** tool schema, connector errors, system instructions, and rulebook now state that Titan connects only to the user's existing vault (`TITAN_OBSIDIAN_VAULT_PATH`, e.g. « Titan AI »), never creates a vault, and prefers `patch_note` / smart updates over full replace.
- **Obsidian decision policy (Batch 2):** Brain reasoning invokes `ObsidianDecisionEngine` before vault tool execution; casual conversation never triggers note creation.

## [0.22.0] - 2026-07-06

### Added

- **Phase 22.0 — Obsidian Brain Extension:** Titan's first real external tool integration — Obsidian as the user's personal knowledge vault, independent from Titan Memory.
  - Extended `ObsidianConnector` actions: `rename_note`, `move_note`, `list_folders`, `get_backlinks`, `get_outlinks`, `read_frontmatter`, `update_frontmatter`, `list_tags`.
  - `tools/connectors/vault_link_index.py` — backlink indexing, wikilink rewrite on rename, sanitized note display names (no filesystem paths in UI).
  - `ObsidianTool` future-ready facade: `read()`, `write()`, `create()`, `delete()`, `move()`, `search()`, `list_folders()`, `list_notes()`.
  - `ObsidianDecisionEngine` — NL routing for rename, move, delete, backlinks, frontmatter, folder/tag listing.
  - Brain pipeline tracks `obsidian_consulted` / `obsidian_note_titles` in `ThinkContext` for memory visualization.
  - Web UI: tool timeline shows **Consultation d'Obsidian**; presence enters memory state; `memory_activity` emits Obsidian recall cards when vault tools run.
  - Tests: `tests/test_obsidian_phase22.py`.

### Changed

- Version `0.22.0` — Obsidian becomes the first external tool fully integrated into Brain + web UI memory state.

## [0.10.0] - 2026-06-28

Titan V3 **Phase 10A — Real Tool Integration Framework** closure release. Tool Runtime V2 is the default execution path; legacy Phase 6 direct-registry dispatch remains available via opt-out.

### Added

- **Tool Runtime Layer (`tools/tool_runtime.py`):** pre-flight gates for health, dependencies, quotas, permissions, and confirmation before execution.
- **Provider framework (`tools/providers/`):** `BaseProvider`, `ProviderRegistry`, version compatibility checks, stub providers for `web_search` and `calendar` (no external APIs).
- **Confirmation gate (`tools/confirmation_gate.py`):** capability-first gating with `/confirm` flow wired through Brain pipeline (`brain/tool_confirmation_handler.py`).
- **Audit logging (`tools/audit/`):** append-only JSONL structured events with params digest (no secrets).
- **Persistence foundation:** `ToolRunStore`, optional metrics/quota snapshots (`TITAN_TOOL_PERSIST_RUNS`, `TITAN_TOOL_PERSIST_METRICS`).
- **Async execution foundation:** thread-pool `AsyncExecutor` with poll/cancel support.
- **Brain integration:** `tool_execution_bridge.py`, provider health in prompts (`SANTÉ OUTILS ET PROVIDERS`), `ExecutionCoordinator` → `ToolDispatcher` → `ToolRuntime`.
- **96 Phase 10A regression tests** across `test_tool_runtime*.py`, `test_confirmation_gate.py`, `test_tool_audit.py`, `test_tool_persistence_async.py`, `test_provider_framework.py`, `test_brain_tool_integration.py`.

### Changed

- **`TITAN_TOOL_RUNTIME_V2` default:** `true` — composition root `ToolManager` uses `ToolRuntime` by default.
- **`VERSION`:** `0.9.0` → `0.10.0`.
- **`ToolManager.run()`:** routes through runtime when v2 enabled; returns `run_id` on outcomes.
- **`.env.example`:** documents Phase 10A tool runtime settings.

### Backward compatibility

- Set `TITAN_TOOL_RUNTIME_V2=false` or `ToolManager(use_runtime_v2=False)` to restore Phase 6 direct-registry path.
- Phase 6 `ToolResult` contract preserved via `outcome_to_result()`.
- External API integrations deferred to Phase 10B; provider stubs only.

## [0.1.0] - 2026-06-27

Titan V2 **Phase 1 — Architecture Cleanup** foundation release. Resolves Brain Audit P0 items (double agent execution, TaskEvaluator false positives, missing REPL/LLM error handling) and establishes a single composition root with regression tests and structured logging.

### Added

- `tests/` scaffold and **110** regression tests: imports, managers, composition/DI guards, single agent path, REPL behavior, TaskEvaluator, mission gating, LLM error handling, REPL error handling, orchestrator hardening, logging, dead-module guards, `MemoryFacade`.
- `logs/` directory and `core/logging_config.py` — rotating file + console handlers (`P1-020`–`P1-024`).
- `LOG_LEVEL`, `LOG_DIR`, `DEBUG_BRAIN` feature flags in `config/settings.py` (`P1-022`).
- Package `__init__.py` files for all seven top-level packages (`P1-030`).
- `.env.example`, `README.md` (Windows setup/run/test), `pyproject.toml` pytest config (`P1-031`–`P1-033`).
- `tests/conftest.py` `brain` fixture with mocked LLM and temp JSON paths (`P1-060`).
- `memory/memory_facade.py` stub wired at composition root (`P1-120`–`P1-122`).
- Phase 1 data backup procedure (`data/backups/YYYYMMDD/`) documented below for manual testing.

### Changed

- **Dependency injection (Track E, `P1-050`–`P1-062`):** `Brain` requires keyword-injected shared managers from `Titan`; one instance each of `AgentManager`, `ContextManager`, `StateManager`, `MissionManager`, `LongTermMemory`.
- **Single agent orchestration path (Track F, `P1-070`–`P1-073`):** `Titan.start()` no longer calls `AgentManager.auto_execute()`. Agent work runs only via `Brain.think()` → `TaskOrchestrator.orchestrate()`.
- **TaskEvaluator (Track G, `P1-080`–`P1-082`):** mission steps advance only on explicit completion phrases when a mission is active. Casual words like `continue`, `done`, and bare `fait`/`terminé` no longer corrupt mission progress.
- **Mission gating (`P1-090`–`P1-092`):** missions created only on explicit intent (`nouvelle mission`, `créer une mission`, etc.). Greetings and casual keyword mentions no longer auto-start missions.
- **LLM error handling (`P1-100`–`P1-102`):** `LLM.ask()` catches API failures, retries transient errors (max 3 attempts, backoff), returns a French fallback message; never raises to callers.
- **REPL error handling (`P1-110`–`P1-112`):** `Titan.start()` wraps `brain.think()` in try/except; session continues after internal failures; orchestrator agent errors are logged and do not abort the turn.
- **Logging migration (`P1-130`–`P1-132`):** `print()` debug replaced with `logging` in `core/titan.py`, `brain/brain.py`, and `core/task_orchestrator.py` (guarded by `DEBUG_BRAIN` where applicable).

### Removed

- `core/action_manager.py` (`P1-042`) — unwired placeholder; Brain uses `TaskOrchestrator` / agents instead.
- `core/context.py` (`P1-043`) — duplicate legacy context; active context is `context/context_manager.py`.

### Fixed — Brain Audit P0

| P0 item | Resolution |
|---------|------------|
| Double agent execution (TD-1) | Single path: `Brain.think()` → `TaskOrchestrator` only (`P1-070`–`P1-073`) |
| TaskEvaluator false positives | Explicit-phrase-only completion policy; inactive-mission guard (`P1-080`–`P1-082`) |
| No REPL + LLM error handling | `LLM.ask()` try/retry/fallback (`P1-100`–`P1-102`); REPL try/except (`P1-110`–`P1-111`) |

### Migration — upgrading from 0.0.1

Before running `0.1.0` against live runtime data, **back up** `data/titan_mission.json`, `data/titan_state.json`, and `data/long_term_memory.json`. Mission gating and TaskEvaluator fixes change when missions are created and when steps advance; existing mission JSON from `0.0.1` may behave differently under the new rules.

See **Phase 1 testing — data backup procedure** below for PowerShell/Bash copy and restore steps.

---
### Phase 1 testing — data backup procedure (P1-002)

Before **manual testing** of tasks **P1-080 and later** (TaskEvaluator, mission gating, and related Brain changes), back up live runtime JSON so mission and memory state can be restored if a test corrupts or resets files.

#### When to back up

- Before the first manual REPL or integration test session for **P1-080+**
- Before any experiment that runs `python main.py` against real `data/` files after mission-gating or TaskEvaluator code changes
- Automated tests must use temporary directories (`tmp_path` / injected paths) and **must not** rely on this procedure — see P1-010+

#### Files to back up

Copy these three files from `data/`:

| File | Purpose |
|------|---------|
| `data/titan_mission.json` | Active mission and step progress |
| `data/titan_state.json` | Operational session/project state |
| `data/long_term_memory.json` | Durable user notes (Nolan / Ibrahim — sensitive) |

Do not commit backup contents or paste personal notes into the changelog.

#### Backup directory convention

Use a dated folder under `data/backups/`:

```text
data/backups/YYYYMMDD/
├── titan_mission.json
├── titan_state.json
└── long_term_memory.json
```

Replace `YYYYMMDD` with the backup date (e.g. `20260623` for 23 June 2026). One folder per backup session; create a new dated folder before each risky manual test run if you need a fresh restore point.

#### Backup steps

**PowerShell (Windows — project root):**

```powershell
$date = Get-Date -Format "yyyyMMdd"
$dest = "data/backups/$date"
New-Item -ItemType Directory -Force -Path $dest
Copy-Item "data/titan_mission.json" $dest
Copy-Item "data/titan_state.json" $dest
Copy-Item "data/long_term_memory.json" $dest
Write-Host "Backup written to $dest"
```

**Bash (Linux / macOS — project root):**

```bash
DATE=$(date +%Y%m%d)
DEST="data/backups/${DATE}"
mkdir -p "$DEST"
cp data/titan_mission.json data/titan_state.json data/long_term_memory.json "$DEST"
echo "Backup written to $DEST"
```

#### Restore steps

If manual testing corrupts or unwantedly resets runtime data, restore from the chosen backup folder (replace `YYYYMMDD` with the backup date):

**PowerShell (Windows):**

```powershell
$src = "data/backups/YYYYMMDD"
Copy-Item "$src/titan_mission.json" "data/titan_mission.json" -Force
Copy-Item "$src/titan_state.json" "data/titan_state.json" -Force
Copy-Item "$src/long_term_memory.json" "data/long_term_memory.json" -Force
Write-Host "Restored from $src"
```

**Bash:**

```bash
SRC="data/backups/YYYYMMDD"
cp "$SRC/titan_mission.json" data/titan_mission.json
cp "$SRC/titan_state.json" data/titan_state.json
cp "$SRC/long_term_memory.json" data/long_term_memory.json
echo "Restored from $SRC"
```

Verify restore: start Titan (`python main.py`) and confirm mission step, state, and memory match expectations before continuing Phase 1 testing.

#### Rollback of this procedure

Documentation only — remove or edit this section in `CHANGELOG.md` if the process changes in a later phase.

### Phase 1 baseline — manager instantiation audit (P1-003)

**Date:** 2026-06-23  
**Purpose:** Capture pre-Phase-1 duplicate instantiation locations before dependency injection (Track E, P1-050+). Used to verify P1-152 grep sign-off: after DI, each manager class should instantiate only in `core/titan.py`.

**Grep patterns run (repo root, all files):**

```text
AgentManager\(
ContextManager\(
StateManager\(
MissionManager\(
LongTermMemory\(
```

**Production Python instantiations (`*.py` only — authoritative baseline):**

| Manager | File | Line | Attribute |
|---------|------|------|-----------|
| `ContextManager()` | `core/titan.py` | 24 | `self.context` |
| `ContextManager()` | `brain/brain.py` | 35 | `self.context_manager` |
| `AgentManager()` | `core/titan.py` | 26 | `self.agents` |
| `AgentManager()` | `brain/brain.py` | 40 | `self.agent_manager` |
| `LongTermMemory()` | `brain/brain.py` | 36 | `self.long_memory` |
| `StateManager()` | `brain/brain.py` | 46 | `self.state_manager` |
| `MissionManager()` | `brain/brain.py` | 47 | `self.mission_manager` |

**Summary counts (production `*.py`):**

| Pattern | Total | `core/titan.py` | `brain/brain.py` | Other `.py` |
|---------|-------|-----------------|------------------|-------------|
| `ContextManager()` | 2 | 1 | 1 | 0 |
| `AgentManager()` | 2 | 1 | 1 | 0 |
| `LongTermMemory()` | 1 | 0 | 1 | 0 |
| `StateManager()` | 1 | 0 | 1 | 0 |
| `MissionManager()` | 1 | 0 | 1 | 0 |

**Known duplicates (pre-DI):**

- `ContextManager` — Titan and Brain each construct one (2 instances per process).
- `AgentManager` — Titan and Brain each construct one (2 instances per process; Brain also wires `TaskManager` / `TaskOrchestrator` against its own copy).

**Titan-only today:** `ContextManager`, `AgentManager` (Brain additionally owns `StateManager`, `MissionManager`, `LongTermMemory` — not yet constructed in Titan).

**Non-code matches (documentation only — not runtime instantiations):**

- `Phase1_Implementation_Plan.md`, `Titan_V2_Roadmap.md`, `.cursor/rules/titan.mdc` — describe target state or examples; no executable calls.

**Target state (P1-152 sign-off):**

| Pattern | Expected location after DI |
|---------|----------------------------|
| `AgentManager()` | `core/titan.py` only |
| `ContextManager()` | `core/titan.py` only |
| `StateManager()` | `core/titan.py` only |
| `MissionManager()` | `core/titan.py` only |
| `LongTermMemory()` | `core/titan.py` only |

**Verification checklist (P1-003):**

- [x] Grep run: `AgentManager\(`, `ContextManager\(`, `StateManager\(`, `MissionManager\(`, `LongTermMemory\(`
- [x] Results recorded for comparison at P1-152

#### Rollback of this audit

Documentation only — delete or edit this section in `CHANGELOG.md` if the baseline must be re-captured.

### Phase 1 gate — full test suite (P1-150)

**Date:** 2026-06-27  
**Purpose:** Roadmap Phase 1 definition of done — minimum 15 passing tests; no writes to live `data/`.

**Command run (project root):**

```text
python -m pytest tests/ -v
```

**Result (2026-06-27):**

| Metric | Count |
|--------|-------|
| Tests collected | 110 |
| Passed | 110 |
| Failed | 0 |

**Gate threshold:** ≥ 15 passing tests; all pass; no test writes to real `data/`. **Gate status: PASS.**

**Test inventory by file:**

| File | Tests collected |
|------|-----------------|
| `tests/test_imports.py` | 36 |
| `tests/test_state_manager.py` | 3 |
| `tests/test_mission_manager.py` | 16 |
| `tests/test_task_evaluator.py` | 19 |
| `tests/test_memory_retriever.py` | 5 |
| `tests/test_agent_selector.py` | 5 |
| `tests/test_composition.py` | 9 |
| `tests/test_single_agent_path.py` | 1 |
| `tests/test_mission_gating.py` | 2 |
| `tests/test_llm.py` | 4 |
| `tests/test_logging_config.py` | 1 |
| `tests/test_no_dead_modules.py` | 2 |
| `tests/test_titan_repl.py` | 1 |
| `tests/test_titan_error_handling.py` | 2 |
| `tests/test_orchestrator_errors.py` | 2 |
| `tests/test_memory_facade.py` | 3 |

**Verification checklist (P1-150):**

- [x] `pytest tests/ -v` all pass
- [x] Count ≥ 15 (110 collected)
- [x] No test writes to real `data/` (fixtures use `tmp_path` / injected paths)

### Phase 1 sign-off — manual Windows smoke test (P1-151)

**Date:** 2026-06-27  
**Environment:** Windows 10, Python 3.14, project root  
**Procedure:** Mission JSON backed up to `data/backups/20260627/`; inactive mission seeded; `python main.py` with piped input `bonjour` → `continue` → `exit`; mission restored from backup after test.

| Step | Expected | Result |
|------|----------|--------|
| 1. Startup | Banner `Titan AI v0.1.0`, greeting, `Toi :` prompt | PASS |
| 2. `bonjour` | Response received; mission stays inactive | PASS |
| 3. `continue` | Mission step does not auto-advance | PASS |
| 4. `exit` | Clean shutdown message | PASS |
| 5. `logs/titan.log` | File exists with entries | PASS |

**Additional checks:** No unhandled traceback in session output.

**Verification checklist (P1-151):**

- [x] All 5 steps recorded
- [x] No unhandled traceback

### Phase 1 sign-off — DI grep audit (P1-152)

**Date:** 2026-06-27  
**Purpose:** Confirm duplicate manager constructors eliminated vs P1-003 baseline.

**Production instantiations (`*.py` excluding `tests/`):**

| Pattern | Location | Line | Notes |
|---------|----------|------|-------|
| `AgentManager()` | `core/titan.py` | 32 | Composition root |
| `ContextManager()` | `core/titan.py` | 33 | Composition root |
| `StateManager()` | `core/titan.py` | 34 | Composition root |
| `MissionManager()` | `core/titan.py` | 35 | Composition root |
| `LongTermMemory()` | `core/titan.py` | 36 | Composition root |

**`auto_execute`:** Not present in `core/titan.py`. Method remains on `AgentManager` for legacy API; REPL uses Brain orchestrator only (`tests/test_titan_repl.py` guard).

**Delta from P1-003 baseline:**

| Manager | Pre-DI (P1-003) | Post-DI (P1-152) |
|---------|-----------------|------------------|
| `ContextManager()` | 2 (`titan.py`, `brain.py` impl) | 1 (`titan.py` only; `brain.py` docstring examples excluded) |
| `AgentManager()` | 2 (`titan.py`, `brain.py` impl) | 1 (`titan.py` only) |
| `LongTermMemory()` | 1 (`brain.py` impl) | 1 (`titan.py` only) |
| `StateManager()` | 1 (`brain.py` impl) | 1 (`titan.py` only) |
| `MissionManager()` | 1 (`brain.py` impl) | 1 (`titan.py` only) |

**Verification checklist (P1-152):**

- [x] Grep results match allowed-locations table
- [x] Delta from P1-003 baseline documented

### Phase 1 definition of done (P1-154)

**Date:** 2026-06-27  
**Sign-off:** Titan V2 Phase 1 (Architecture Cleanup) — **COMPLETE**

| Criterion | Status | Evidence |
|-----------|--------|----------|
| One `AgentManager`, one `ContextManager`, one orchestration path per turn | PASS | P1-052–P1-058, P1-070–P1-073, P1-152 |
| `Brain.__init__` receives all shared dependencies via constructor injection | PASS | P1-059, `tests/test_composition.py` |
| Dead modules removed with zero orphan imports | PASS | P1-042–P1-044 |
| REPL survives LLM and Brain exceptions | PASS | P1-100–P1-111, `tests/test_titan_error_handling.py` |
| TaskEvaluator no longer advances mission on `"continue"` alone | PASS | P1-080–P1-082, `tests/test_task_evaluator.py` |
| Casual greeting does not create mission | PASS | P1-090–P1-092, P1-151 step 2 |
| `tests/` exists with ≥15 tests covering P0 fixes | PASS | P1-150 — 110 tests |
| Structured logging replaces prints in modified files | PASS | P1-020–P1-024, P1-130–P1-132 |
| `Brain_Audit.md` P0 items addressed | PASS | See **Fixed — Brain Audit P0** above |
| `python main.py` verified manually on Windows | PASS | P1-151 |

**Verification checklist (P1-154):**

- [x] All criteria checked and passing

### Phase 1 gate — baseline test count (P1-019)

**Date:** 2026-06-24  
**Purpose:** Gate before Track E dependency injection (P1-050+). Do not refactor wiring without this test safety net.

**Command run (project root):**

```text
pytest tests/ -v
```

**Result (2026-06-24):**

| Metric | Count |
|--------|-------|
| Tests collected | 71 |
| Passed | 64 |
| Xfailed (documented P0 — P1-016 TaskEvaluator) | 7 |
| Failed | 0 |

**Gate threshold:** ≥ 10 passing tests (xfail allowed for documented P0 cases). **Gate status: PASS** — 64 passed; Track E (DI) may proceed.

**Test inventory by file:**

| File | Tests collected | Notes |
|------|-----------------|-------|
| `tests/test_imports.py` | 36 | Production module import smoke (P1-013) |
| `tests/test_state_manager.py` | 3 | Load/save round-trip (P1-014) |
| `tests/test_mission_manager.py` | 6 | Mission lifecycle (P1-015) |
| `tests/test_task_evaluator.py` | 16 | 9 pass + 7 xfail snapshot (P1-016) |
| `tests/test_memory_retriever.py` | 5 | Keyword relevance (P1-017) |
| `tests/test_agent_selector.py` | 5 | Routing smoke (P1-018) |

**Xfail documentation:** Seven cases in `tests/test_task_evaluator.py` assert desired post-P1-080 behavior (`continue`, `fait`, `done`, etc. must not complete steps). Marked `# P0: must become False in P1-080`; expected to flip to pass when P1-080 lands.

**Verification checklist (P1-019):**

- [x] Full suite green (64 passed, 7 xfail documented, 0 failed)
- [x] Test count recorded in CHANGELOG

#### Rollback of this gate

Documentation only — re-run `pytest tests/ -v` after any test changes to refresh counts in this section.

### Phase 1 deletion gates — dead module import verification (P1-040, P1-041)

**Date:** 2026-06-27  
**Purpose:** Confirm safe deletion gates before / after removing `core/action_manager.py` and `core/context.py`.

**Grep patterns (all `*.py` under repo root):**

```text
from core.action_manager
import action_manager
from core.context
from core import context
```

**Result:** No production Python imports found. Modules deleted in P1-042 / P1-043; guarded by `tests/test_no_dead_modules.py` (P1-044).

**Verification checklist (P1-040, P1-041):**

- [x] Grep empty for production imports of `core/action_manager`
- [x] Grep empty for production imports of `core/context`
- [x] Documented in CHANGELOG
