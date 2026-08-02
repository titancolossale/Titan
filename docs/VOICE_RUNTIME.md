# Voice Runtime V1

Voice Runtime gives Titan **real-time spoken conversation** while keeping the
Brain architecture unchanged. It is an **external interface** — capture speech,
transcribe, delegate to `Brain.process_request()`, synthesize the reply, play audio.

> Voice Runtime never bypasses the Brain. It never calls planners, orchestrators,
> or tool runtimes directly.

## Architecture

```
Microphone
    ↓
Speech-To-Text (provider abstraction)
    ↓
Brain.process_request(message)     ← canonical Brain front door
    ↓
Natural Language Orchestrator → existing Brain systems
    ↓
final_response (text)
    ↓
Text-To-Speech (provider abstraction)
    ↓
Speaker
```

### Package layout

| Module | Role |
|--------|------|
| `voice/voice_runtime.py` | Main orchestrator — sessions, state, interruptions, speaker gate |
| `voice/speech_to_text.py` | STT provider ABC, registry, mock provider |
| `voice/text_to_speech.py` | TTS provider ABC, registry, mock provider |
| `voice/speaker_identifier.py` | Phase 20.1/20.2 — recognition + confirm-on-unknown |
| `voice/voice_enrollment.py` | Phase 20.2 — guided enrollment lifecycle |
| `voice/speaker_profile_store.py` | Phase 20.2 — identity profile persistence |
| `voice/sample_validator.py` | Phase 20.2 — enrollment sample quality gates |
| `voice/enrollment_scripts.py` | Phase 20.2 — FR/EN enrollment phrases |
| `voice/live_session.py` | Phase 20.3 — live session orchestration lifecycle |
| `voice/vad.py` | Phase 20.3 — voice activity detection |
| `voice/speech_segmenter.py` | Phase 20.3 — streaming utterance assembly |
| `voice/session_lifecycle.py` | Phase 20.3 — explicit live session states |
| `voice/tts_strategy.py` | Phase 20.3 — sentence-buffered / full-response TTS |
| `voice/diagnostics.py` | Phase 20.3/20.5 — structured VOICE_* / stream diagnostics |
| `voice/conversation_engine.py` | Phase 20.5 — continuous conversation continuity + recovery |
| `voice/streaming_stt.py` | Phase 20.5 — incremental partial/stable/final STT |
| `voice/streaming_brain.py` | Phase 20.5 — streaming Brain deltas + cancel |
| `voice/streaming_tts.py` | Phase 20.5 — sentence-streamed TTS |
| `voice/latency_tracker.py` | Phase 20.5/20.6 — end-to-end + mic/provider/turnaround latency metrics |
| `voice/cancellation.py` | Phase 20.5 — per-stage cancel tokens |
| `voice/transport/` | Phase 20.6 — WebSocket / SSE / HTTP transport + reconnect manager |
| `voice/stream_performance.py` | Phase 20.6 — coalesce, buffer caps, bandwidth, sync skew |
| `voice/providers/` | Phase 20.1 + 20.6 — batch OpenAI + realtime streaming adapters |
| `voice/mic_calibration.py` | Phase 20.7 — noise floor / gain / clipping / low-volume |
| `voice/silence_detector.py` | Phase 20.7 — end-of-turn / long pause / false speech |
| `voice/conversation_flow.py` | Phase 20.7 — turn timing / barge-in resume / confirm prompts |
| `voice/session_stats.py` | Phase 20.7 — session statistics aggregates |
| `voice/production_soak.py` | Phase 20.7/20.8 — production soak scenarios |
| `voice/embedding_provider.py` | Phase 20.8/20.9 — pluggable speaker embeddings + registry stubs |
| `voice/enrollment_quality.py` | Phase 20.8/20.9 — quality / duplicate / replace / session scoring |
| `voice/enrollment_consent.py` | Phase 20.9 — multi-language consent prompts + records |
| `voice/enrollment_diagnostics.py` | Phase 20.9 — enrollment + provider diagnostic snapshot |
| `voice/provider_health.py` | Phase 20.8 — provider + transport health |
| `voice/transport/browser_hub.py` | Phase 20.8 — browser WebSocket hub |
| `voice/voice_session.py` | Persistent session store (`data/voice_sessions.json`) |
| `voice/audio_devices.py` | Device discovery + capture/playback abstractions |
| `voice/models.py` | `VoiceState`, `VoiceConfig`, `VoiceSession`, metrics |
| `voice/exceptions.py` | Voice error hierarchy |
| `voice/voice_manager.py` | Web API capability/config facade (Phase 17.8 + 20.1) |

### Reused Brain systems (unchanged)

Voice Runtime calls **only** `Brain.process_request()`. That entry point already
routes through:

- Natural Language Orchestrator
- Memory, Mission Runtime, Workspace Awareness
- Executive Function, Development Session
- Tool Runtime / Tool Execution Engine (when intents require tools)

No second Brain. No parallel planner.

## Voice states

| State | Meaning |
|-------|---------|
| `idle` | Ready for next utterance |
| `listening` | Microphone capture active |
| `thinking` | `Brain.process_request()` in progress |
| `speaking` | TTS playback active |
| `paused` | User paused listen/speak |
| `error` | Recoverable failure |

## Conversation modes

| Mode | V1 support | Description |
|------|------------|-------------|
| `single_shot` | Yes | One utterance → one response (`listen_once`) |
| `continuous` | Yes | Multiple turns (`listen_continuous`) |
| `push_to_talk` | Yes | `push_to_talk_start` / `push_to_talk_stop` |
| `wake_word` | Reserved | Hook points only — no detector in V1 |

## Session lifecycle

Sessions persist to `data/voice_sessions.json` (override with `TITAN_VOICE_SESSIONS_PATH`).

Each session stores:

- `conversation_id`
- timestamps (`created_at`, `updated_at`, `ended_at`)
- microphone / speaker device ids
- language
- `last_response`
- `conversation_history` (turns with latency metrics)
- `session_duration_seconds`
- embedded `VoiceConfig`

```python
from brain.brain import Brain
from voice import VoiceRuntime, voice_config_from_settings

runtime = VoiceRuntime(brain, config=voice_config_from_settings())
session = runtime.start_session()

result = runtime.process_text_turn("Bonjour Titan")
print(result.assistant_text, result.metrics.total_seconds)

runtime.end_session()
```

### Audio pipeline (hardware or mock)

```python
# Single-shot with mock capture (tests / offline)
result = runtime.listen_once()

# Push-to-talk
runtime.push_to_talk_start()
result = runtime.push_to_talk_stop()

# Continuous (max_turns bounds the loop in V1)
results = runtime.listen_continuous(max_turns=3)
```

## Provider abstraction

### Speech-To-Text

Implement `SpeechToTextProvider` and register on `SpeechToTextRegistry`:

```python
class OpenAIWhisperProvider(SpeechToTextProvider):
    @property
    def provider_id(self) -> str:
        return "openai_whisper"

    def transcribe(self, audio_bytes: bytes, *, locale: str, **kwargs) -> TranscriptionResult:
        ...
```

Future providers: OpenAI Whisper, Deepgram, Azure, local Whisper — register without
changing `VoiceRuntime`.

### Text-To-Speech

Implement `TextToSpeechProvider` and register on `TextToSpeechRegistry`:

```python
class ElevenLabsProvider(TextToSpeechProvider):
    @property
    def provider_id(self) -> str:
        return "elevenlabs"

    def synthesize(self, text, *, locale, voice="default", speed=1.0, volume=1.0, **kwargs):
        ...
```

Future providers: OpenAI, ElevenLabs, Azure, Piper.

V1 ships with `mock` providers for CI and offline development.

## Interruptions

| API | Effect |
|-----|--------|
| `interrupt_speaking()` | Cancel current TTS / stop playback |
| `cancel_current_speech()` | Alias for `interrupt_speaking` |
| `stop_playback()` | Stop speaker output immediately |
| `queue_response(text)` | Hold response for later |
| `flush_response_queue()` | Speak queued responses |

## Configuration

Environment variables (`config/settings.py`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `TITAN_VOICE_ENABLED` | `true` | Feature flag |
| `TITAN_VOICE_LOCALE` | `fr-FR` | STT/TTS language |
| `TITAN_VOICE_VOICE` | `default` | TTS voice id |
| `TITAN_VOICE_TTS_RATE` | `0.95` | Speech speed |
| `TITAN_VOICE_VOLUME` | `1.0` | Playback volume |
| `TITAN_VOICE_STT_PROVIDER` | `mock` | STT provider id |
| `TITAN_VOICE_TTS_PROVIDER` | `mock` | TTS provider id |
| `TITAN_VOICE_MICROPHONE` | `default` | Input device id |
| `TITAN_VOICE_SPEAKER` | `default` | Output device id |
| `TITAN_VOICE_SILENCE_TIMEOUT` | `2.0` | End-of-utterance silence (seconds) |
| `TITAN_VOICE_CONVERSATION_MODE` | `single_shot` | Default mode |
| `TITAN_VOICE_SESSIONS_PATH` | `data/voice_sessions.json` | Session persistence |

## Logging

Per turn, Voice Runtime logs (no secrets):

- speech start / end
- transcription duration
- brain (`process_request`) duration
- TTS duration
- total latency

## Future compatibility

Designed for later phases without API breaks:

| Feature | V1 / 20.1 hook |
|---------|----------------|
| Streaming STT | Provider interface returns `TranscriptionResult`; stream adapter can wrap |
| Streaming TTS | `AudioPlayback` can accept chunked audio |
| Wake word | `ConversationMode.WAKE_WORD` reserved |
| Emotion detection | Post-STT enrichment hook |
| Speaker identification | **Phase 20.1** — `SpeakerIdentifier` + session binding |
| Guided voice enrollment | **Phase 20.2** — `VoiceEnrollmentService` + verification |
| Live session orchestration | **Phase 20.3** — `LiveVoiceSessionOrchestrator` + VAD |
| Voice memory | Session `conversation_history` + Memory integration via Brain |
| Multi-user recognition | **Phase 20.1/20.2/20.3** — confirm-on-unknown; high/medium/low bands |

## Phase 20.1 — Provider Integration & Speaker Recognition

Architecture additions after production Phase 19.7:

```
Microphone
    ↓
Speech-To-Text (mock | openai_whisper)
    ↓
SpeakerIdentifier.identify(audio)
    ↓  known → SessionManager.set_user(Nolan|Ibrahim)
    ↓  unknown → ask confirmation (no Brain personal memory)
    ↓
Brain.process_request(message)
    ↓
Text-To-Speech (mock | openai_tts)
    ↓
Speaker
```

| Module | Role |
|--------|------|
| `voice/speaker_identifier.py` | Enrollment, voiceprint match, confirm-on-unknown |
| `voice/providers/openai_stt.py` | OpenAI Whisper adapter |
| `voice/providers/openai_tts.py` | OpenAI TTS adapter |
| `voice/providers/registry_bootstrap.py` | Register live providers on demand |

New settings:

| Variable | Default | Purpose |
|----------|---------|---------|
| `TITAN_VOICE_SPEAKER_ID_ENABLED` | `true` | Enforce speaker gate on audio turns |
| `TITAN_VOICE_SPEAKER_MIN_CONFIDENCE` | `0.72` | High-confidence match threshold |
| `TITAN_VOICE_SPEAKER_PROFILES_PATH` | `data/voice_speaker_profiles.json` | Enrollment store |
| `TITAN_VOICE_OPENAI_STT_MODEL` | `whisper-1` | Whisper model |
| `TITAN_VOICE_OPENAI_TTS_MODEL` | `gpt-4o-mini-tts` | TTS model |

Set `TITAN_VOICE_STT_PROVIDER=openai_whisper` and
`TITAN_VOICE_TTS_PROVIDER=openai_tts` with `OPENAI_API_KEY` for live audio.
Call `register_default_voice_providers()` before resolving those provider ids.

## Phase 20.2 — Voice Enrollment & Identity Profiles

Guided enrollment builds durable speaker identity profiles **without** storing raw
audio by default. Profiles activate only after a fresh verification sample passes.

```
Authenticated user (Nolan | Ibrahim)
    ↓
POST /voice/enrollment/start
    ↓
Collect ≥ N validated samples (+ FR/EN script phrases)
    ↓
POST /voice/enrollment/finish → inactive pending profile
    ↓
POST /voice/enrollment/verify (fresh sample, not from enrollment set)
    ↓  pass → activate atomically (replace/revoke old if re-enrolling)
    ↓  fail → no partial active profile; bounded retry
```

| Module | Role |
|--------|------|
| `voice/voice_enrollment.py` | Lifecycle orchestration |
| `voice/speaker_profile_store.py` | Create/load/update/activate/deactivate/revoke/replace |
| `voice/sample_validator.py` | Empty/short/unsupported/silence/clipping/duplicate/multi-speaker |
| `voice/enrollment_scripts.py` | French + English guided phrases |
| `api/voice_enrollment_routes.py` | Auth + CSRF protected enrollment API |

Recognition policy (runtime):

- **High** confidence → bind identity
- **Medium** → confirmation required (never auto-bind)
- **Low** → unknown
- **Ambiguous** Nolan/Ibrahim → never auto-select
- Revoked / inactive profiles never authenticate

Privacy defaults: transient temp audio under `data/voice_enrollment_tmp/`,
embeddings never logged / never in WorkspaceState / never sent to the LLM /
never stored in Obsidian or conversation memory.

Enrollment settings:

| Variable | Default |
|----------|---------|
| `TITAN_VOICE_ENROLLMENT_MIN_SAMPLES` | `3` |
| `TITAN_VOICE_ENROLLMENT_MAX_SAMPLES` | `8` |
| `TITAN_VOICE_ENROLLMENT_MIN_DURATION` | `1.0` |
| `TITAN_VOICE_ENROLLMENT_MAX_DURATION` | `30.0` |
| `TITAN_VOICE_ENROLLMENT_MIN_QUALITY` | `0.45` |
| `TITAN_VOICE_ENROLLMENT_MIN_CONFIDENCE` | `0.72` |
| `TITAN_VOICE_SPEAKER_MEDIUM_CONFIDENCE` | `0.55` |
| `TITAN_VOICE_SPEAKER_AMBIGUITY_DELTA` | `0.05` |
| `TITAN_VOICE_ENROLLMENT_TEMP_DIR` | `data/voice_enrollment_tmp` |

## Phase 20.3 — Live Voice Session Orchestration

Production session lifecycle for authenticated clients:

```
Authenticated start → LISTENING
    ↓ audio chunks
VAD (speech start/end) + SpeechSegmenter
    ↓ clean utterance
SpeakerIdentifier (before personal memory)
    ↓ high → bind | medium/ambiguous → confirm | low → restricted
STT → Brain.process_request() (stream deltas)
    ↓
TTS strategy (sentence-buffered or full) → VOICE_AUDIO_CHUNK
    ↓ barge-in supported
LISTENING / IDLE
```

| Module / API | Role |
|--------------|------|
| `voice/live_session.py` | Session controller, barge-in, identity confirm, Brain lock recovery |
| `voice/vad.py` | Configurable thresholds, silence/max duration rejection |
| `voice/speech_segmenter.py` | Ordered chunks, duplicate ignore, buffer cleanup |
| `voice/tts_strategy.py` | Markdown/code cleanup, FR/EN voices, sentence buffering |
| `api/voice_session_routes.py` | `/voice/session/start\|chunk\|finish\|confirm-identity\|reject-identity\|interrupt\|cancel\|state` |

Live session states: `IDLE`, `LISTENING`, `SPEECH_DETECTED`, `CAPTURING`,
`TRANSCRIBING`, `IDENTIFYING_SPEAKER`, `WAITING_FOR_IDENTITY_CONFIRMATION`,
`THINKING`, `SPEAKING`, `INTERRUPTED`, `CANCELLED`, `FAILED`, `COMPLETED`.

Always-listening and wake-word modes are **config hooks only** — never auto-enabled.
Voice recognition alone never authorizes destructive actions.

Live settings:

| Variable | Default |
|----------|---------|
| `TITAN_VOICE_VAD_SPEECH_START` | `0.035` |
| `TITAN_VOICE_VAD_SPEECH_END` | `0.018` |
| `TITAN_VOICE_VAD_SILENCE_TIMEOUT` | `1.2` |
| `TITAN_VOICE_VAD_MIN_UTTERANCE` | `0.35` |
| `TITAN_VOICE_VAD_MAX_UTTERANCE` | `30.0` |
| `TITAN_VOICE_VAD_SENSITIVITY` | `0.55` |
| `TITAN_VOICE_TTS_STRATEGY` | `sentence_buffered` |
| `TITAN_VOICE_IDENTITY_CONFIRM_TIMEOUT` | `45.0` |
| `TITAN_VOICE_PROVIDER_TIMEOUT` | `60.0` |
| `TITAN_VOICE_LIVE_TEMP_DIR` | `data/voice_live_tmp` |
| `TITAN_VOICE_ALWAYS_LISTENING` | `false` |
| `TITAN_VOICE_WAKE_WORD_ENABLED` | `false` |

## Phase 20.4 — Web App Voice UI & Microphone Integration

Browser UI under `web/v2/voice/` connects authenticated clients to the Phase 20.2–20.3 APIs
without always-listening and without redesigning the black/red Titan shell.

| Module | Role |
|--------|------|
| `web/v2/voice/microphone.js` | Explicit-gesture mic permission + track release |
| `web/v2/voice/audio-capture.js` | PCM (preferred) / MediaRecorder capture, sequenced chunks |
| `web/v2/voice/voice-controller.js` | Push-to-talk state machine + barge-in |
| `web/v2/voice/tts-playback.js` | Ordered TTS queue (no overlap) |
| `web/v2/voice/enrollment-ui.js` | Consent + guided enrollment / verify / revoke |
| `web/v2/voice/voice-api.js` | CSRF/session-authenticated `/voice/*` client |
| `web/v2/voice/diagnostics.js` | `VOICE_UI_*` client diagnostics (privacy-safe) |

Playback path: `POST /voice/session/finish` (and confirm/reject) may include ordered
`tts_audio_chunks` (`sequence`, `audio_base64`, `mime_type`) for browser playback.
Raw PCM chunk streams are wrapped as WAV server-side via `wrap_pcm_as_wav` before
STT / speaker identification.

Always-listening remains disabled. Microphone activates only after an explicit user
gesture and releases on cancel, logout, navigation, and page hide.

## Phase 20.5 — Real-Time Voice Conversation Engine

Transforms push-to-talk turns into a continuous, low-latency conversation while
preserving Brain as the only cognitive entry point.

```
Microphone
    ↓
Voice Activity / Segmentation
    ↓
Incremental STT (partial → stable → final)
    ↓  only stable/final → Brain
Streaming Brain (deltas / sentences / cancel)
    ↓
Streaming TTS (sentence chunks / FR·EN)
    ↓
Playback (ordered, no overlap)
```

| Module | Role |
|--------|------|
| `voice/conversation_engine.py` | Multi-turn continuity, idle/conversation timeouts, recovery |
| `voice/streaming_stt.py` | Partial / stable / final transcript stages |
| `voice/streaming_brain.py` | Single `process_request` with deltas + duplicate prevention |
| `voice/streaming_tts.py` | Sentence-streamed TTS + locale-aware voices |
| `voice/latency_tracker.py` | First-audio / transcript / Brain / TTS / idle metrics |
| `voice/cancellation.py` | Independently cancellable STT / Brain / TTS tokens |

New authenticated endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/voice/session/recover` | Browser refresh / reconnect recovery |
| POST | `/voice/session/heartbeat` | Reset idle timeout |
| GET | `/voice/session/events` | Drain buffered stream diagnostics |

New settings: `TITAN_VOICE_IDLE_TIMEOUT`, `TITAN_VOICE_CONVERSATION_TIMEOUT`,
`TITAN_VOICE_RECOVERY_TTL`, `TITAN_VOICE_STREAMING_STT`, `TITAN_VOICE_STREAMING_TTS`.

Safety unchanged: web auth, speaker verification, permission/confirmation systems,
Brain safety. Always-listening stays hard-disabled.

## Phase 20.6 — True Real-Time Streaming Providers

Upgrades sentence-based streaming to provider-level incremental STT/TTS with a
generic transport layer.

```
Mic frames
    ↓
StreamPerformanceController (coalesce / backpressure)
    ↓
TransportManager (WebSocket → SSE → HTTP fallback)
    ↓
Realtime STT provider (partial / stable / final + confidence / language / speaker)
    ↓  stable+final only → Brain
Streaming Brain
    ↓
Realtime TTS provider (byte chunks + buffer smoothing + cancel)
    ↓
Playback
```

| Module | Role |
|--------|------|
| `voice/transport/` | WebSocket, SSE, HTTP, reconnect, heartbeat, graceful shutdown |
| `voice/providers/realtime_stt.py` | Incremental STT provider interface + mock |
| `voice/providers/realtime_tts.py` | Incremental TTS + smoothed audio buffer |
| `voice/providers/openai_realtime.py` | Bidirectional OpenAI Realtime session |
| `voice/providers/openai_whisper_streaming.py` | Chunked Whisper streaming wrapper |
| `voice/providers/deepgram_streaming.py` | Deepgram live STT |
| `voice/providers/elevenlabs_streaming.py` | ElevenLabs streaming TTS |
| `voice/providers/failover.py` | Retry / fallback / manual provider switch |
| `voice/stream_performance.py` | CPU/RAM/bandwidth/buffer/sync controls |

Realtime streaming is **off by default** (`TITAN_VOICE_REALTIME_STREAMING=false`).
When enabled, live sessions attach providers from
`TITAN_VOICE_REALTIME_STT_PROVIDER` / `TITAN_VOICE_REALTIME_TTS_PROVIDER` with
configured fallback chains. Secrets: `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`,
`ELEVENLABS_API_KEY` (never logged).

## Phase 20.7 — Live Voice Experience & Production Soak

Polishes conversational flow, microphone calibration, silence / end-of-turn,
and production soak validation without redesigning the Web UI.

| Module | Role |
|--------|------|
| `voice/conversation_flow.py` | Natural pause, barge-in debounce, resume-after-interrupt, confirmation prompts |
| `voice/mic_calibration.py` | Noise floor, speech threshold, gain estimate, clipping / low-volume |
| `voice/silence_detector.py` | Automatic end-of-turn, long pause, false-speech rejection |
| `voice/session_stats.py` | Speech / turn / provider / brain / TTS aggregates |
| `voice/production_soak.py` | In-process soak scenarios (mock-safe) |
| `scripts/phase20_7_voice_soak.py` | CLI soak harness → `data/phase20_7_soak/report.json` |

New authenticated endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/voice/session/calibrate/start` | Start mic calibration window |
| POST | `/voice/session/calibrate/chunk` | Feed calibration audio |
| POST | `/voice/session/calibrate/finish` | Finalize calibration |
| GET | `/voice/session/stats` | Session statistics snapshot |

Web client adds helpers only (`estimateMicMetrics`, `microphonePermissionFlow`,
calibrate/stats API wrappers) — no layout redesign. Always-listening and wake-word
remain disabled.

## Phase 20.8 — Live Providers & Real Voice Preparation

Prepares production live providers and browser transport without collecting
real Nolan/Ibrahim voices yet.

| Module | Role |
|--------|------|
| `voice/transport/socket_backends.py` | Outbound live WebSocket backends (`websocket-client`) |
| `voice/transport/browser_protocol.py` | Browser frame protocol (heartbeat / backpressure / sync) |
| `voice/transport/browser_hub.py` | Server-side browser connection hub + recover |
| `api/voice_ws_routes.py` | Authenticated `WS /voice/session/ws` |
| `web/v2/voice/voice-socket.js` | Browser WS client (reconnect / heartbeat / backpressure) |
| `voice/embedding_provider.py` | Pluggable embeddings (`histogram_v1` default) |
| `voice/enrollment_quality.py` | Quality scoring, cross-user duplicate detection, replace plans |
| `voice/provider_health.py` | Provider + transport + embedding health snapshot |
| `scripts/phase20_8_voice_soak.py` | Extended production soak CLI |

Providers remain interchangeable via `TITAN_VOICE_REALTIME_*` settings. Live
sockets activate only when API keys + `websocket-client` are present
(`TITAN_VOICE_LIVE_SOCKETS=true`). Realtime streaming stays off by default.

New authenticated endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| WS | `/voice/session/ws` | Native browser voice uplink |
| GET | `/voice/session/diagnostics/providers` | Provider / embedding health |
| GET | `/voice/session/diagnostics/transport` | Browser hub connection state |

## Phase 20.9 — Real Speaker Enrollment & Live Provider Soak

Production-ready enrollment pipeline preparation (still **no** real Nolan/Ibrahim
voice collection) plus extended live-provider soak coverage.

| Module | Role |
|--------|------|
| `voice/enrollment_consent.py` | Multi-language consent prompts + audit records |
| `voice/enrollment_diagnostics.py` | Enrollment / provider / confidence / latency snapshot |
| `voice/embedding_provider.py` | Registry + ECAPA / Resemblyzer / OpenAI-compat stubs |
| `voice/enrollment_quality.py` | Session quality + same-user near-duplicate detection |
| `voice/production_soak.py` | Voice verification / consent recovery / live recovery scenarios |
| `scripts/phase20_9_voice_soak.py` | Phase 20.9 soak CLI → `data/phase20_9_soak/report.json` |

Enrollment lifecycle additions: `AWAITING_CONSENT`, `CANCELLED`, recovery tokens,
`grant_consent` / `recover_enrollment`, FR/EN/ES + bilingual scripts.

New authenticated endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/voice/enrollment/consent` | Grant or decline enrollment consent |
| POST | `/voice/enrollment/recover` | Resume interrupted enrollment via recovery token |
| GET | `/voice/enrollment/scripts` | Multi-language scripts + consent prompts |
| GET | `/voice/enrollment/diagnostics` | Enrollment + provider diagnostic snapshot |

## Phase 20.10A — Production Voice Enrollment System

Finalizes the guided production enrollment workflow **without** collecting real
Nolan/Ibrahim voices. Legacy `EnrollmentStatus` values remain for API
compatibility; production workflow states are mirrored on each session.

| Module | Role |
|--------|------|
| `voice/enrollment_workflow.py` | Production state machine + transition audit |
| `voice/enrollment_verification.py` | Confidence-threshold verification + retry pipeline |
| `voice/enrollment_audit.py` | Append-only safe audit events (no biometrics) |
| `voice/enrollment_quality.py` | Production metrics (signal/noise/duration/clip/mic/…) |
| `voice/enrollment_diagnostics.py` | Workflow / failure / confidence / audit snapshot |

Production states: `WAITING_CONSENT`, `CONSENT_GRANTED`, `READY_TO_RECORD`,
`RECORDING`, `VERIFYING`, `SUCCESS`, `FAILED`, `CANCELLED`, `RECOVERY`.

Session capabilities: multiple attempts, resume, safe cancel, replacement
enrollment, profile versioning, duplicate protection, audit history.

New authenticated endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/voice/enrollment/workflow` | Production workflow snapshot |
| GET | `/voice/enrollment/audit` | Safe enrollment audit history |

## Phase 20.11 — Production Speaker Embeddings & Identity Security

Replaces silent reliance on histogram identity with a production-oriented
embedding architecture. Histogram remains available as a **development/test
fallback only** and must never silently become production-trusted.

| Module | Role |
|--------|------|
| `voice/embedding_capabilities.py` | Trust levels + capability detection |
| `voice/embedding_provider.py` | ECAPA / Resemblyzer / local / external registry |
| `voice/speaker_verification.py` | Cosine/provider similarity, UNKNOWN / AMBIGUOUS |
| `voice/identity_security.py` | Voice ID ≠ high-risk authorization |
| `voice/embedding_storage.py` | Encryption-ready storage + integrity / corruption |
| `voice/embedding_migration.py` | Explicit re-enrollment; block histogram auto-trust |
| `voice/anti_spoof.py` | Extensible liveness (null does not weaken verify) |
| `voice/embedding_diagnostics.py` | Safe provider/version/migration/liveness snapshot |

Real Nolan/Ibrahim enrollment remains **Phase 20.10B** (deferred).

## Phase 20.12 — Real Speaker Biometric Backend

Replaces production biometric stubs with real local embedding backends and
hardens storage + identity claim handling before real enrollment.

| Module | Role |
|--------|------|
| `voice/ecapa_provider.py` | Real ECAPA-TDNN (SpeechBrain) — lazy CPU inference |
| `voice/resemblyzer_provider.py` | Resemblyzer GE2E fallback |
| `voice/biometric_trust.py` | DEVELOPMENT / PRODUCTION trust separation |
| `voice/audio_prep.py` | PCM/WAV decode for embedding backends |
| `voice/embedding_storage.py` | AES-GCM envelopes (v2) + legacy XOR migration |
| `voice/identity_security.py` | CLAIMED_IDENTITY ≠ VERIFIED_IDENTITY |
| `voice/embedding_diagnostics.py` | Provider/model/trust/encryption readiness |

### Trust rules

- Histogram embeddings: **development/test only**
- Production trust mode refuses trusted identity on histogram/dev backends
- Spoken/UI « je suis Nolan/Ibrahim » → `CLAIMED_IDENTITY` (never biometrically VERIFIED)
- Personal memory requiring verification attaches only after VERIFIED policy success

### Optional dependencies

Install when enabling `TITAN_VOICE_EMBEDDING_PROVIDER=ecapa` or `resemblyzer`:

```text
torch>=2.1
torchaudio>=2.1
speechbrain>=1.0
resemblyzer>=0.1.1
```

Missing deps keep Titan healthy; `/ready` reports `voice_biometric` as optional.

Real Nolan/Ibrahim enrollment remains **Phase 20.10B** (deferred).

## Phase 20.10B-1 — Production Enrollment Activation

Activates the production biometric enrollment environment **without** collecting
real Nolan/Ibrahim voices.

| Module / Script | Role |
|-----------------|------|
| `voice/enrollment_preflight.py` | Full pre-flight (ECAPA, trust, AES-GCM, storage, mic, consent, slots) |
| `scripts/activate_production_enrollment_env.py` | Write non-secret production flags into local `.env` |
| `scripts/ensure_voice_embedding_storage_key.py` | Generate AES-GCM key in `.env` (never prints it) |
| `scripts/phase20_10b1_enrollment_preflight.py` | Pre-flight CLI |
| `scripts/phase20_10b1_guided_enroll.py` | Guided entry + exact Web App enrollment steps |
| `GET /voice/enrollment/preflight` | Authenticated pre-flight API |
| Voice panel preflight line | Existing enrollment UI shows readiness (no redesign) |

### Activation checklist (local host)

```bash
python scripts/activate_production_enrollment_env.py
python scripts/phase20_10b1_enrollment_preflight.py
python scripts/phase20_10b1_guided_enroll.py --user Nolan
```

Real sample collection is **Phase 20.10B-2** via the Web App Voice panel after
pre-flight passes.

## Phase 20.13 — Durable biometric storage (Railway Volume)

Voice profiles must survive Railway redeploys. Architecture:

| Layer | Choice | Why |
|-------|--------|-----|
| Durable root | Railway Volume at `/app/data` (`TITAN_DATA_DIR`) | Existing Titan persistence path |
| Profiles / sessions / AES-GCM envelopes | `voice_speaker_profiles.json` | Single store; schema v5 |
| Web chat history | PostgreSQL | Unrelated to biometrics — do not migrate embeddings to SQL |
| Encryption | AES-256-GCM via `TITAN_VOICE_EMBEDDING_STORAGE_KEY` | Unchanged key; no plaintext vectors on disk when encryption on |

| Module | Role |
|--------|------|
| `voice/biometric_persistence.py` | Dir creation, writability, volume detection, no ephemeral fallback |
| `voice/speaker_profile_store.py` | AES-GCM wire-up on save/load (schema v5) |
| `/ready` → `biometric_storage` | Required in production; fails closed without volume |

Env flags:

| Variable | Production |
|----------|------------|
| `TITAN_DATA_DIR` | `/app/data` |
| `TITAN_BIOMETRIC_PERSISTENCE_REQUIRED` | `true` |
| `TITAN_BIOMETRIC_STORAGE_PERSISTENT` | set `true` only after confirming volume durability |
| `TITAN_VOICE_EMBEDDING_ENCRYPTION` | `true` |
| `TITAN_VOICE_EMBEDDING_STORAGE_KEY` | Railway secret (never rotate casually) |

## Related documents

- `docs/ARCHITECTURE.md` — official execution path
- `docs/NATURAL_LANGUAGE_ORCHESTRATOR.md` — `Brain.process_request()` routing
- `docs/ROADMAP.md` — Phase 20.x status
- `voice/voice_manager.py` — web client voice status API

## Tests

```bash
pytest tests/test_voice_runtime.py tests/test_voice_manager.py \
  tests/test_speaker_identifier.py tests/test_voice_phase20_1.py \
  tests/test_voice_phase20_2.py tests/test_voice_phase20_3.py \
  tests/test_voice_phase20_4.py tests/test_voice_phase20_5.py \
  tests/test_voice_phase20_6.py tests/test_voice_phase20_7.py \
  tests/test_voice_phase20_8.py tests/test_voice_phase20_9.py \
  tests/test_voice_phase20_10a.py tests/test_voice_phase20_11.py \
  tests/test_voice_phase20_12.py tests/test_voice_phase20_10b1.py -v
```

Coverage: session lifecycle, provider registry, STT/TTS mocks, OpenAI adapters
(mocked client), speaker enrollment/identification, guided enrollment + verification,
live VAD/segmentation/barge-in/identity confirm, confirm-on-unknown memory isolation,
conversation flows, interruptions, Brain integration, Web App voice UI contracts
(mocked MediaDevices / MediaRecorder / Audio), continuous multi-turn streaming,
partial/stable/final STT, Brain/TTS stream cancel, session recovery, timeouts,
latency metrics, transport reconnect/fallback, provider switching, Deepgram/ElevenLabs/
Whisper streaming adapters (injected transports), failover diagnostics, mic calibration,
silence/end-of-turn, conversation flow polish, production soak scenarios, browser
WebSocket hub reconnect/backpressure, embedding provider upgrades path, cross-user
duplicate enrollment guards, provider health diagnostics, real enrollment consent/
recovery/cancel, embedding registry stubs, enrollment diagnostics, live-provider soak,
production enrollment workflow / quality / verification / audit (Phase 20.10A),
production embeddings / verification / identity security / storage / anti-spoof /
migration / diagnostics privacy (Phase 20.11), real ECAPA/Resemblyzer biometric
backends / AES-GCM storage / claimed-vs-verified identity / Railway-safe biometric
readiness (Phase 20.12), production enrollment activation / preflight / AES-GCM key
bootstrap / guided entry without real voice collection (Phase 20.10B-1).
