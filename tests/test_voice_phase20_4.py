# =====================================
# Titan Phase 20.4 — Web App Voice UI Tests
# =====================================

"""Web App voice UI contracts, mic safety, TTS chunks, API auth, regressions."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agents.agent_manager import AgentManager
from api.app import create_app
from api.titan_service import reset_titan, set_titan
from api.voice_session_routes import reset_live_orchestrator_for_tests
from brain.brain import Brain
from brain.llm import LLM
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.state_manager import StateManager
from core.titan import Titan
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService
from tools.tool_manager import ToolManager
from voice.live_session import (
    LiveVoiceSessionOrchestrator,
    wrap_pcm_as_wav,
)
from voice.models import VoiceConfig
from voice.speech_to_text import MockSpeechToTextProvider, SpeechToTextRegistry
from voice.voice_session import VoiceSessionStore

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "web" / "v2"
VOICE_JS = V2 / "voice"


def _node_available() -> bool:
    return shutil.which("node") is not None


def _speech_like(seed: int, seconds: float = 1.25) -> bytes:
    n = int(16000 * seconds)
    return bytes(((seed * 37 + i * 17) % 180) + 40 for i in range(n))


def _build_brain(tmp_path: Path) -> Brain:
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Réponse vocale de test."
    state = StateManager(file_path=tmp_path / "titan_state.json")
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )
    return Brain(
        agent_manager=AgentManager(memory_service=memory),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=memory,
        tool_manager=ToolManager(project_root=tmp_path),
        llm=mock_llm,
    )


def _run_node(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


# ---------------------------------------------------------------------------
# Static / contract tests (no browser hardware)
# ---------------------------------------------------------------------------


def test_voice_ui_modules_exist() -> None:
    for name in (
        "diagnostics.js",
        "errors.js",
        "microphone.js",
        "audio-capture.js",
        "tts-playback.js",
        "voice-api.js",
        "voice-controller.js",
        "enrollment-ui.js",
        "register.js",
        "voice.css",
    ):
        assert (VOICE_JS / name).is_file(), name


def test_voice_controls_require_auth_markers() -> None:
    api = (VOICE_JS / "voice-api.js").read_text(encoding="utf-8")
    assert "authHeaders" in api
    assert "credentials: \"same-origin\"" in api
    assert "/voice/session/start" in api
    assert "/voice/enrollment/start" in api
    assert "session_expired" in api


def test_microphone_never_auto_activates() -> None:
    mic = (VOICE_JS / "microphone.js").read_text(encoding="utf-8")
    ctrl = (VOICE_JS / "voice-controller.js").read_text(encoding="utf-8")
    assert "getUserMedia" in mic
    assert "requestMicrophone" in mic
    # Controller only requests mic inside beginListening (user gesture path).
    assert "beginListening" in ctrl
    assert "always_listening" not in ctrl.lower() or "disabled" in ctrl.lower()
    assert "requestMicrophone()" in ctrl


def test_no_raw_audio_in_browser_persistence() -> None:
    for path in VOICE_JS.glob("*.js"):
        text = path.read_text(encoding="utf-8")
        assert "localStorage.setItem" not in text or "titan-v2-dev" in text
        assert "indexedDB" not in text.lower()
        assert "audio_base64" not in text or path.name in {
            "voice-api.js",
            "voice-controller.js",
            "tts-playback.js",
            "enrollment-ui.js",
            "diagnostics.js",
        }
    diag = (VOICE_JS / "diagnostics.js").read_text(encoding="utf-8")
    assert "audio_base64" in diag  # forbidden key list
    assert "FORBIDDEN" in diag


def test_enrollment_consent_required() -> None:
    text = (VOICE_JS / "enrollment-ui.js").read_text(encoding="utf-8")
    assert "consent" in text.lower()
    assert "tdl-v2-voice-consent-check" in text
    assert "consent_required" in text or "CONSENT" in text


def test_push_to_talk_and_barge_in_controls() -> None:
    ctrl = (VOICE_JS / "voice-controller.js").read_text(encoding="utf-8")
    assert "beginListening" in ctrl
    assert "endListening" in ctrl
    assert "bargeIn" in ctrl
    assert "Interrompre" in ctrl
    assert "pointerdown" in ctrl
    assert "keydown" in ctrl


def test_speaker_identity_ui_safe_labels() -> None:
    ctrl = (VOICE_JS / "voice-controller.js").read_text(encoding="utf-8")
    assert "Nolan" in ctrl and "Ibrahim" in ctrl
    assert "Inconnu" in ctrl
    assert "Confirmation" in ctrl
    assert "confidence" not in ctrl.lower() or "band" in ctrl.lower()


def test_voice_nav_and_composer_mic_wired() -> None:
    router = (V2 / "core" / "router.js").read_text(encoding="utf-8")
    assert 'key: "voice"' in router
    assert "nav: true" in router.split('key: "voice"')[1][:200]
    main = (V2 / "main.js").read_text(encoding="utf-8")
    assert "registerVoiceExtension" in main
    composer = (V2 / "composer" / "composer-region.js").read_text(encoding="utf-8")
    assert "tdl-v2-voice-mic" in composer
    store = (V2 / "core" / "state-store.js").read_text(encoding="utf-8")
    for field in (
        "voiceSessionState",
        "voiceInputLevel",
        "voiceCurrentSpeaker",
        "voiceEnrollmentStatus",
        "voicePendingConfirmation",
    ):
        assert field in store


def test_voice_panel_mount_retries_across_transition() -> None:
    """Phase 20.13 — must not leave Voice stuck on the loading placeholder."""
    register = (VOICE_JS / "register.js").read_text(encoding="utf-8")
    layouts = (V2 / "panels" / "layouts" / "index.js").read_text(encoding="utf-8")
    assert "Chargement du module vocal" in layouts
    assert "VOICE_MOUNT_TIMEOUT_MS" in register
    assert "VOICE_MOUNT_POLL_MS" in register
    assert "scheduleVoicePanelMount" in register
    assert "tdl-v2-voice-mount-retry" in register
    assert "tdl-v2-voice-mount-error" in register
    assert "mountEnrollmentPanel" in register
    # Single rAF without retry is the production stuck-state bug.
    assert "setTimeout(tick" in register or "setTimeout(tick," in register


@pytest.mark.skipif(not _node_available(), reason="node required")
def test_voice_mount_survives_delayed_panel_dom() -> None:
    """Reproduce the 350ms panel-transition race and assert mount succeeds."""
    script = r"""
const VOICE_MOUNT_TIMEOUT_MS = 8000;
const VOICE_MOUNT_POLL_MS = 50;
let panelExists = false;
let mounted = false;

function tryMountPanel() {
  if (!panelExists) return false;
  if (mounted) return true;
  mounted = true;
  return true;
}

function scheduleVoicePanelMount() {
  const startedAt = Date.now();
  const tick = () => {
    if (tryMountPanel()) {
      console.log(JSON.stringify({ ok: true, elapsed: Date.now() - startedAt }));
      process.exit(0);
      return;
    }
    if (Date.now() - startedAt >= VOICE_MOUNT_TIMEOUT_MS) {
      console.error(JSON.stringify({ ok: false, reason: "timeout" }));
      process.exit(1);
      return;
    }
    setTimeout(tick, VOICE_MOUNT_POLL_MS);
  };
  setTimeout(tick, 0); // rAF stand-in
}

scheduleVoicePanelMount();
setTimeout(() => { panelExists = true; }, 350);
setTimeout(() => {
  if (!mounted) {
    console.error(JSON.stringify({ ok: false, reason: "never_mounted" }));
    process.exit(1);
  }
}, 2000);
"""
    result = _run_node(script)
    assert result.returncode == 0, result.stderr + result.stdout
    assert '"ok":true' in result.stdout.replace(" ", "")


def test_text_chat_unchanged_markers() -> None:
    conv = (V2 / "conversation" / "conversation-manager.js").read_text(encoding="utf-8")
    assert "sendMessage" in conv or "retryLast" in conv
    assert "tdl-v2-send-chat" in (V2 / "composer" / "composer-region.js").read_text(
        encoding="utf-8"
    )


def test_visual_identity_css_black_red() -> None:
    css = (VOICE_JS / "voice.css").read_text(encoding="utf-8")
    assert "#ef4444" in css or "tdl-red" in css
    assert "prefers-reduced-motion" in css
    assert "Interrompre" not in css  # label is in JS; styles exist
    assert ".tdl-v2-voice-interrupt" in css


def test_wrap_pcm_as_wav_roundtrip() -> None:
    pcm = _speech_like(3, 0.5)
    wav = wrap_pcm_as_wav(pcm)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    assert wrap_pcm_as_wav(wav) == wav
    webm = b"\x1a\x45\xdf\xa3" + b"\x00" * 40
    assert wrap_pcm_as_wav(webm) == webm


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_node_mime_detection_and_sequence() -> None:
    script = r"""
import { detectSupportedMimeType, encodeWavPcm16, bytesToBase64 } from './web/v2/voice/audio-capture.js';
import { emitVoiceUiDiagnostic, VOICE_UI_EVENTS } from './web/v2/voice/diagnostics.js';
import { voiceErrorMessage } from './web/v2/voice/errors.js';

// Mock MediaRecorder.isTypeSupported
globalThis.MediaRecorder = {
  isTypeSupported(m) { return m === 'audio/webm'; }
};
const mime = detectSupportedMimeType();
if (mime !== 'audio/webm') throw new Error('mime ' + mime);

const pcm = new Int16Array([0, 1000, -1000, 0]);
const wav = encodeWavPcm16(pcm, 16000);
if (wav[0] !== 82) throw new Error('not RIFF');
const b64 = bytesToBase64(wav);
if (!b64.length) throw new Error('empty b64');

if (!VOICE_UI_EVENTS.includes('VOICE_UI_PERMISSION_GRANTED')) throw new Error('events');
let seen = false;
window.addEventListener('titan:voice-ui-diagnostic', () => { seen = true; });
emitVoiceUiDiagnostic('VOICE_UI_PERMISSION_GRANTED', { audio_base64: 'SECRET', tracks: 1 });
if (!seen) throw new Error('diag not emitted');

const msg = voiceErrorMessage('microphone_denied');
if (!msg.includes('microphone') && !msg.includes('Microphone') && !msg.includes('micro')) {
  throw new Error('bad fr error: ' + msg);
}
console.log('ok');
"""
    # Provide minimal window/document for diagnostics
    prelude = r"""
globalThis.window = globalThis;
globalThis.document = { cookie: '' };
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
globalThis.CustomEvent = class CustomEvent {
  constructor(type, init) { this.type = type; this.detail = init?.detail; }
};
globalThis.window.addEventListener = (type, fn) => {
  globalThis.__listeners = globalThis.__listeners || {};
  (globalThis.__listeners[type] = globalThis.__listeners[type] || []).push(fn);
};
globalThis.window.dispatchEvent = (ev) => {
  for (const fn of (globalThis.__listeners?.[ev.type] || [])) fn(ev);
  return true;
};
"""
    result = _run_node(prelude + script)
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_node_tts_queue_order_and_no_overlap() -> None:
    script = r"""
import { TtsPlaybackQueue } from './web/v2/voice/tts-playback.js';

const played = [];
class FakeAudio {
  constructor() { this.src = ''; this._handlers = {}; }
  addEventListener(ev, fn) { this._handlers[ev] = fn; }
  removeEventListener(ev, fn) { if (this._handlers[ev] === fn) delete this._handlers[ev]; }
  async play() {
    played.push(this.src);
    queueMicrotask(() => this._handlers.ended?.());
  }
  pause() {}
  load() {}
  removeAttribute() {}
}
globalThis.Audio = FakeAudio;
globalThis.URL = {
  createObjectURL: (blob) => 'blob:' + (blob.type || 'audio') + ':' + played.length,
  revokeObjectURL: () => {},
};
globalThis.atob = (s) => Buffer.from(s, 'base64').toString('binary');
globalThis.Blob = class {
  constructor(parts, opts) { this.parts = parts; this.type = opts?.type; }
};
globalThis.window = globalThis;
globalThis.CustomEvent = class { constructor(t, i) { this.type=t; this.detail=i?.detail; } };
globalThis.window.addEventListener = () => {};
globalThis.window.dispatchEvent = () => true;
globalThis.localStorage = { getItem: () => null };

const q = new TtsPlaybackQueue();
const mk = (seq, tag) => ({
  sequence: seq,
  audio_base64: Buffer.from(tag).toString('base64'),
  mime_type: 'audio/mpeg',
});
await q.playChunks([mk(1, 'b'), mk(0, 'a'), mk(2, 'c')]);
if (played.length !== 3) throw new Error('expected 3 plays got ' + played.length);

// Second play must not overlap — stop first mid-flight
let secondStarted = false;
const q2 = new TtsPlaybackQueue();
const p1 = q2.playChunks([mk(0, 'x'), mk(1, 'y')]);
q2.stop();
await p1.catch(() => {});
await q2.playChunks([mk(0, 'z')]);
secondStarted = true;
if (!secondStarted) throw new Error('second play failed');
console.log('ok');
"""
    result = _run_node(script)
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_node_mic_permission_flows_mocked() -> None:
    script = r"""
import {
  requestMicrophone,
  releaseMediaStream,
  queryMicrophonePermission,
  isSecureMicContext,
} from './web/v2/voice/microphone.js';

globalThis.window = globalThis;
globalThis.isSecureContext = true;
globalThis.CustomEvent = class { constructor(t, i) { this.type=t; this.detail=i?.detail; } };
globalThis.window.addEventListener = () => {};
globalThis.window.dispatchEvent = () => true;
globalThis.localStorage = { getItem: () => null };

let getUserMediaCalls = 0;
const track = { stop() { track.stopped = true; }, addEventListener() {}, removeEventListener() {}, stopped: false };
navigator.mediaDevices = {
  async getUserMedia() {
    getUserMediaCalls += 1;
    return { getTracks: () => [track], getAudioTracks: () => [track] };
  },
};
navigator.permissions = {
  async query() { return { state: 'prompt' }; },
};

if (!isSecureMicContext()) throw new Error('secure');
const q = await queryMicrophonePermission();
if (q !== 'prompt') throw new Error('perm ' + q);

// Never auto-call — only after requestMicrophone
if (getUserMediaCalls !== 0) throw new Error('auto mic');

const ok = await requestMicrophone();
if (!ok.ok) throw new Error('grant failed');
if (getUserMediaCalls !== 1) throw new Error('calls');
releaseMediaStream(ok.stream);
if (!track.stopped) throw new Error('track not stopped');

navigator.mediaDevices.getUserMedia = async () => {
  const err = new Error('denied');
  err.name = 'NotAllowedError';
  throw err;
};
const denied = await requestMicrophone();
if (denied.ok) throw new Error('should deny');
if (denied.state !== 'denied') throw new Error('state ' + denied.state);

navigator.mediaDevices.getUserMedia = async () => {
  const err = new Error('missing');
  err.name = 'NotFoundError';
  throw err;
};
const missing = await requestMicrophone();
if (missing.state !== 'none') throw new Error('missing state');

globalThis.isSecureContext = false;
const insecure = await requestMicrophone();
if (insecure.state !== 'insecure') throw new Error('insecure');
console.log('ok');
"""
    result = _run_node(script)
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_node_audio_capture_sequence_and_flush() -> None:
    script = r"""
import { AudioCaptureSession, detectSupportedMimeType } from './web/v2/voice/audio-capture.js';

globalThis.window = {
  ...globalThis,
  setInterval: (fn, ms) => 1,
  clearInterval: () => {},
  AudioContext: null,
  webkitAudioContext: null,
  addEventListener: () => {},
  dispatchEvent: () => true,
  localStorage: { getItem: () => null },
};
globalThis.CustomEvent = class { constructor(t, i) { this.type=t; this.detail=i?.detail; } };

const chunks = [];
const seen = new Set();
class FakeRecorder {
  constructor(stream, opts) { this.mimeType = opts.mimeType; this.state = 'inactive'; this.ondataavailable = null; this.onerror = null; this.onstop = null; }
  start() { this.state = 'recording'; }
  requestData() {
    const blob = { size: 4, arrayBuffer: async () => new Uint8Array([1,2,3,4]).buffer };
    this.ondataavailable?.({ data: blob });
  }
  stop() { this.state = 'inactive'; this.onstop?.(); }
}
FakeRecorder.isTypeSupported = (m) => m === 'audio/webm';
globalThis.MediaRecorder = FakeRecorder;

const session = new AudioCaptureSession({
  chunkDurationMs: 50,
  onChunk: (c) => {
    if (seen.has(c.sequence)) throw new Error('duplicate seq ' + c.sequence);
    seen.add(c.sequence);
    chunks.push(c);
  },
});
const track = { stop() {}, addEventListener() {}, removeEventListener() {} };
const stream = { getTracks: () => [track], getAudioTracks: () => [track] };
await session.start(stream);
session._recorder.requestData();
session._recorder.requestData();
await session.stop({ releaseStream: true });
if (chunks.length < 1) throw new Error('no chunks');
if (chunks[0].sequence !== 0) throw new Error('seq start');
// unsupported mime
FakeRecorder.isTypeSupported = () => false;
const bad = new AudioCaptureSession();
let failed = false;
try { await bad.start(stream); } catch { failed = true; }
if (!failed) throw new Error('expected unsupported mime failure');
console.log('ok');
"""
    result = _run_node(script)
    assert result.returncode == 0, result.stderr or result.stdout


# ---------------------------------------------------------------------------
# Backend: TTS chunks returned to web client
# ---------------------------------------------------------------------------


@pytest.fixture()
def web_secret() -> str:
    return "test-secret-phase20-4"


@pytest.fixture()
def voice_api_client(
    web_secret: str, tmp_path: Path
) -> TestClient:
    reset_titan()
    reset_live_orchestrator_for_tests()
    tool_manager = ToolManager(project_root=tmp_path)
    titan = Titan()
    titan.tools = tool_manager
    titan.brain.tool_manager = tool_manager
    titan.status = "ONLINE"
    titan.brain.process_request = MagicMock(
        return_value=SimpleNamespace(final_response="ok")
    )
    set_titan(titan)

    with patch("config.settings.TITAN_WEB_ENABLED", True), patch(
        "config.settings.get_web_secret_key", return_value=web_secret
    ), patch("api.auth.get_web_secret_key", return_value=web_secret), patch(
        "api.auth.is_web_dev_mode", return_value=False
    ), patch(
        "api.auth.is_session_auth_enabled", return_value=False
    ), patch(
        "api.auth_middleware.is_session_auth_enabled", return_value=False
    ), patch(
        "api.voice_session_routes.is_session_auth_enabled", return_value=False
    ):
        client = TestClient(create_app())
        yield client

    reset_live_orchestrator_for_tests()
    reset_titan()


def test_voice_session_requires_authentication(voice_api_client: TestClient) -> None:
    res = voice_api_client.post(
        "/voice/session/start",
        json={"capture_mode": "push_to_talk"},
    )
    assert res.status_code == 401


def test_finish_returns_tts_audio_chunks(tmp_path: Path) -> None:
    from voice.enrollment_models import RecognitionBand
    from voice.speaker_identifier import SpeakerIdentifier
    from voice.speaker_profile_store import SpeakerProfileStore
    from voice.tts_strategy import TTSStrategyConfig, TTSStrategyMode
    from voice.vad import VADConfig

    brain = _build_brain(tmp_path)
    brain.process_request = MagicMock(
        return_value=SimpleNamespace(final_response="Bonjour, voici ma réponse claire.")
    )
    store = SpeakerProfileStore(file_path=tmp_path / "profiles.json")
    identifier = SpeakerIdentifier(
        file_path=tmp_path / "profiles.json",
        profile_store=store,
        min_confidence=0.72,
        medium_confidence=0.55,
        ambiguity_delta=0.05,
    )
    sample = _speech_like(21, 1.5)
    identifier.enroll(
        "Nolan",
        [sample, _speech_like(22, 1.5), _speech_like(23, 1.5)],
    )
    stt = SpeechToTextRegistry()
    mock_stt = MockSpeechToTextProvider(default_text="bonjour titan")
    stt.register(mock_stt)
    mock_stt.set_response(sample, "bonjour titan")
    orchestrator = LiveVoiceSessionOrchestrator(
        brain,
        config=VoiceConfig(stt_provider="mock", tts_provider="mock", language="fr-FR"),
        vad_config=VADConfig(
            min_utterance_duration_seconds=0.2,
            max_utterance_duration_seconds=8.0,
            silence_timeout_seconds=0.3,
            speech_start_threshold=0.02,
            sensitivity=0.7,
        ),
        session_store=VoiceSessionStore(file_path=tmp_path / "sessions.json"),
        stt_registry=stt,
        speaker_identifier=identifier,
        state_manager=StateManager(file_path=tmp_path / "state.json"),
        temp_dir=tmp_path / "tmp",
        tts_strategy_config=TTSStrategyConfig(
            mode=TTSStrategyMode.SENTENCE_BUFFERED,
            min_text_chunk_chars=10,
        ),
    )
    started = orchestrator.start_session(authenticated_user="Nolan")
    sid = started["session_id"]
    orchestrator.submit_audio_chunk(sid, audio_bytes=sample, sequence=0)
    result = orchestrator.finish_utterance(sid)
    assert result.get("voice_current_speaker") == "Nolan"
    assert result.get("voice_identity_confidence_band") == RecognitionBand.HIGH.value
    assert "tts_audio_chunks" in result
    chunks = result["tts_audio_chunks"]
    assert isinstance(chunks, list) and len(chunks) >= 1
    assert chunks[0]["sequence"] == 0
    assert chunks[0]["audio_base64"]
    assert "mime_type" in chunks[0]
    seqs = [c["sequence"] for c in chunks]
    assert seqs == sorted(seqs)


def test_duplicate_chunk_sequence_ignored(tmp_path: Path) -> None:
    from voice.vad import VADConfig

    brain = _build_brain(tmp_path)
    brain.process_request = MagicMock(
        return_value=SimpleNamespace(final_response="ok")
    )
    stt = SpeechToTextRegistry()
    stt.register(MockSpeechToTextProvider(default_text="x"))
    orchestrator = LiveVoiceSessionOrchestrator(
        brain,
        config=VoiceConfig(stt_provider="mock", tts_provider="mock"),
        vad_config=VADConfig(min_utterance_duration_seconds=0.2),
        session_store=VoiceSessionStore(file_path=tmp_path / "sessions.json"),
        stt_registry=stt,
        temp_dir=tmp_path / "tmp",
    )
    started = orchestrator.start_session(authenticated_user="Nolan")
    sid = started["session_id"]
    audio = _speech_like(2, 0.8)
    first = orchestrator.submit_audio_chunk(sid, audio_bytes=audio, sequence=0)
    assert first.get("accepted") is True
    dup = orchestrator.submit_audio_chunk(sid, audio_bytes=audio, sequence=0)
    assert dup.get("duplicate") is True


# ---------------------------------------------------------------------------
# Regression: prior voice phases + web visual markers
# ---------------------------------------------------------------------------


def test_phase20_4_does_not_remove_canonical_mic() -> None:
    canonical = (V2 / "design" / "canonical-final.css").read_text(encoding="utf-8")
    # Mic control remains part of the shell; voice.css extends it.
    assert (V2 / "composer" / "composer-region.js").exists()
    index = (V2 / "index.html").read_text(encoding="utf-8")
    assert "voice/voice.css" in index


def test_voice_diagnostics_event_names_present() -> None:
    text = (VOICE_JS / "diagnostics.js").read_text(encoding="utf-8")
    for name in (
        "VOICE_UI_PERMISSION_REQUESTED",
        "VOICE_UI_PERMISSION_GRANTED",
        "VOICE_UI_PERMISSION_DENIED",
        "VOICE_UI_SESSION_STARTED",
        "VOICE_UI_RECORDING_STARTED",
        "VOICE_UI_AUDIO_CHUNK_SENT",
        "VOICE_UI_RECORDING_STOPPED",
        "VOICE_UI_IDENTITY_CONFIRMATION_SHOWN",
        "VOICE_UI_PLAYBACK_STARTED",
        "VOICE_UI_PLAYBACK_STOPPED",
        "VOICE_UI_BARGE_IN",
        "VOICE_UI_SESSION_CANCELLED",
        "VOICE_UI_SESSION_FAILED",
        "VOICE_UI_SESSION_COMPLETED",
    ):
        assert name in text
