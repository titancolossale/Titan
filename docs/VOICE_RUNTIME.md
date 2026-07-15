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
| `voice/voice_runtime.py` | Main orchestrator — sessions, state, interruptions |
| `voice/speech_to_text.py` | STT provider ABC, registry, mock provider |
| `voice/text_to_speech.py` | TTS provider ABC, registry, mock provider |
| `voice/voice_session.py` | Persistent session store (`data/voice_sessions.json`) |
| `voice/audio_devices.py` | Device discovery + capture/playback abstractions |
| `voice/models.py` | `VoiceState`, `VoiceConfig`, `VoiceSession`, metrics |
| `voice/exceptions.py` | Voice error hierarchy |
| `voice/voice_manager.py` | Web API capability/config facade (Phase 17.8) |

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

| Feature | V1 hook |
|---------|---------|
| Streaming STT | Provider interface returns `TranscriptionResult`; stream adapter can wrap |
| Streaming TTS | `AudioPlayback` can accept chunked audio |
| Wake word | `ConversationMode.WAKE_WORD` reserved |
| Emotion detection | Post-STT enrichment hook |
| Speaker identification | Session metadata extension |
| Voice memory | Session `conversation_history` + Memory integration via Brain |
| Multi-user recognition | Session + `ContextManager.current_user` via Brain |

## Related documents

- `docs/ARCHITECTURE.md` — official execution path
- `docs/NATURAL_LANGUAGE_ORCHESTRATOR.md` — `Brain.process_request()` routing
- `voice/voice_manager.py` — web client voice status API

## Tests

```bash
pytest tests/test_voice_runtime.py tests/test_voice_manager.py -v
```

Coverage: session lifecycle, provider registry, STT/TTS mocks, conversation flows,
interruptions, state transitions, Brain integration, configuration, errors.
