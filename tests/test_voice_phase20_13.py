# =====================================
# Titan Phase 20.13 — Enrollment Consent + Recording UX Fix
# =====================================

"""Prove consent wiring, Enregistrer vs composer mic separation, and status isolation."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

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
from voice.enrollment_models import EnrollmentConfig, EnrollmentStatus
from voice.exceptions import VoiceEnrollmentError
from voice.speaker_profile_store import SpeakerProfileStore
from voice.voice_enrollment import VoiceEnrollmentService

ROOT = Path(__file__).resolve().parent.parent
VOICE_JS = ROOT / "web" / "v2" / "voice"


def _node_available() -> bool:
    return shutil.which("node") is not None


def _run_node(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def _build_brain(tmp_path: Path) -> Brain:
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "ok"
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


def _enrollment_service(tmp_path: Path, **config_kwargs: object) -> VoiceEnrollmentService:
    store = SpeakerProfileStore(file_path=tmp_path / "profiles.json")
    defaults: dict[str, object] = {
        "min_sample_count": 3,
        "min_quality_score": 0.2,
        "require_consent": True,
    }
    defaults.update(config_kwargs)
    return VoiceEnrollmentService(
        store=store,
        config=EnrollmentConfig(**defaults),  # type: ignore[arg-type]
        state_manager=StateManager(file_path=tmp_path / "state.json"),
        temp_dir=tmp_path / "enroll_tmp",
    )


# ---------------------------------------------------------------------------
# Static UI contracts
# ---------------------------------------------------------------------------


def test_ui_unchecked_consent_cannot_start_enrollment() -> None:
    """Continuer stays gated on the checkbox; consent is never auto-set."""
    ui = (VOICE_JS / "enrollment-ui.js").read_text(encoding="utf-8")
    assert "consentCheck.checked" in ui
    assert "consentStart.disabled = !consentCheck.checked" in ui
    assert "consent_accepted: true" in ui or "consent_accepted:true" in ui
    # Must not open wizard / set consented before the checkbox gate.
    start_handler = ui.split("consentStart.addEventListener")[1].split(
        "function updateWizard"
    )[0]
    assert "if (!consentCheck.checked" in start_handler
    assert "consent_accepted: true" in start_handler or "consent_accepted:true" in start_handler
    # No automatic consent without user action.
    assert "consentCheck.checked = true" not in ui
    assert "consent_accepted: true" not in ui.split("consentStart.addEventListener")[0]


def test_ui_checked_consent_propagated_to_backend_contract() -> None:
    ui = (VOICE_JS / "enrollment-ui.js").read_text(encoding="utf-8")
    api = (VOICE_JS / "voice-api.js").read_text(encoding="utf-8")
    assert "consent_accepted: true" in ui or "consent_accepted:true" in ui
    assert "grantEnrollmentConsent" in ui
    assert "grantEnrollmentConsent" in api
    assert "/voice/enrollment/consent" in api
    assert "startEnrollment" in api


def test_enregistrer_uses_enrollment_sample_endpoint() -> None:
    ui = (VOICE_JS / "enrollment-ui.js").read_text(encoding="utf-8")
    api = (VOICE_JS / "voice-api.js").read_text(encoding="utf-8")
    assert 'id="tdl-v2-voice-record-sample"' in ui
    assert "submitEnrollmentSample" in ui
    assert "recordSampleWav" in ui
    assert "/voice/enrollment/sample" in api
    sample_fn = api.split("export async function submitEnrollmentSample")[1].split(
        "export async function"
    )[0]
    assert "/voice/enrollment/sample" in sample_fn


def test_composer_mic_is_not_enrollment_recorder() -> None:
    ui = (VOICE_JS / "enrollment-ui.js").read_text(encoding="utf-8")
    ctrl = (VOICE_JS / "voice-controller.js").read_text(encoding="utf-8")
    api = (VOICE_JS / "voice-api.js").read_text(encoding="utf-8")
    # Enrollment samples go through Enregistrer → recordSampleWav → /sample.
    assert "tdl-v2-voice-record-sample" in ui
    assert "submitEnrollmentSample" in ui
    # Composer mic is live PTT only and locks during enrollment.
    assert "voiceEnrollmentActive" in ctrl
    assert "beginListening" in ctrl
    begin = ctrl.split("async beginListening()")[1].split("async endListening")[0]
    assert "voiceEnrollmentActive" in begin
    assert "/voice/session/start" in api
    assert "tdl-v2-voice-mic--enrollment-locked" in ctrl
    assert "Utilise le micro du compositeur pour le push-to-talk" not in ui


def test_live_failed_does_not_mark_enrollment_failed() -> None:
    ui = (VOICE_JS / "enrollment-ui.js").read_text(encoding="utf-8")
    store = (ROOT / "web" / "v2" / "core" / "state-store.js").read_text(encoding="utf-8")
    assert "voiceSessionState" in store
    assert "voiceEnrollmentStatus" in store
    assert "voiceEnrollmentActive" in store
    # Status line separates enrollment from live PTT FAILED.
    assert "Enrollment :" in ui
    assert "Session live (PTT)" in ui
    assert "FAILED" in ui
    assert "pas un échec d’enrollment" in ui or "pas un échec d'enrollment" in ui
    # Must not overwrite enrollment status from live FAILED.
    assert 'voiceEnrollmentStatus: "FAILED"' not in ui
    assert "voiceEnrollmentStatus: state.voiceSessionState" not in ui


# ---------------------------------------------------------------------------
# Backend consent acceptance (require_consent=true)
# ---------------------------------------------------------------------------


def test_backend_rejects_start_without_consent(tmp_path: Path) -> None:
    enrollment_svc = _enrollment_service(tmp_path, require_consent=True)
    started = enrollment_svc.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        locale="fr-FR",
        consent_accepted=False,
    )
    session = started["session"]
    assert session["status"] == EnrollmentStatus.AWAITING_CONSENT.value
    assert session["consent_given"] is False
    with pytest.raises(VoiceEnrollmentError) as exc:
        enrollment_svc.submit_sample(
            session_id=session["session_id"],
            audio_bytes=b"RIFF" + b"\x00" * 100,
            authenticated_user="Nolan",
        )
    assert exc.value.code == "consent_required"


def test_backend_accepts_checked_consent_inline(tmp_path: Path) -> None:
    enrollment_svc = _enrollment_service(tmp_path, require_consent=True)
    started = enrollment_svc.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        locale="fr-FR",
        consent_accepted=True,
    )
    session = started["session"]
    assert session["status"] == EnrollmentStatus.COLLECTING.value
    assert session["consent_given"] is True
    assert started.get("next_phrase") is not None


def test_backend_accepts_deferred_consent_api(tmp_path: Path) -> None:
    enrollment_svc = _enrollment_service(tmp_path, require_consent=True)
    started = enrollment_svc.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        locale="fr-FR",
        consent_accepted=False,
    )
    sid = started["session"]["session_id"]
    granted = enrollment_svc.grant_consent(
        session_id=sid,
        authenticated_user="Nolan",
        accepted=True,
        locale="fr-FR",
    )
    assert granted["ok"] is True
    assert granted["accepted"] is True
    assert granted["session"]["consent_given"] is True
    assert granted["session"]["status"] == EnrollmentStatus.COLLECTING.value


def test_nolan_remains_unenrolled_before_real_samples(tmp_path: Path) -> None:
    """Consent alone must not create a Nolan biometric profile."""
    enrollment_svc = _enrollment_service(tmp_path, require_consent=True)
    started = enrollment_svc.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        locale="fr-FR",
        consent_accepted=True,
    )
    assert started["session"]["status"] == EnrollmentStatus.COLLECTING.value
    assert enrollment_svc.store.get_active_profile("Nolan") is None
    status = enrollment_svc.get_status(user_id="Nolan", authenticated_user="Nolan")
    active = status.get("active_profile")
    assert active is None or active.get("active") is not True


def test_api_consent_paths_with_require_consent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TITAN_WEB_DEV_MODE", "true")
    monkeypatch.setenv("TITAN_AUTH_REQUIRED", "false")
    monkeypatch.setenv("TITAN_VOICE_ENROLLMENT_REQUIRE_CONSENT", "true")
    reset_titan()
    reset_live_orchestrator_for_tests()
    import api.voice_enrollment_routes as enroll_routes

    enroll_routes._enrollment_service = None  # noqa: SLF001
    brain = _build_brain(tmp_path)
    titan = Titan.__new__(Titan)
    titan.brain = brain
    titan.state_manager = brain.state_manager
    titan.mission_manager = brain.mission_manager
    set_titan(titan)
    service = _enrollment_service(tmp_path, require_consent=True)
    enroll_routes._enrollment_service = service
    client = TestClient(create_app())

    blocked = client.post(
        "/voice/enrollment/start",
        json={"user": "Nolan", "locale": "fr-FR", "consent_accepted": False},
    )
    assert blocked.status_code == 200
    assert blocked.json()["session"]["status"] == EnrollmentStatus.AWAITING_CONSENT.value
    assert blocked.json()["session"]["consent_given"] is False

    ok = client.post(
        "/voice/enrollment/start",
        json={"user": "Nolan", "locale": "fr-FR", "consent_accepted": True},
    )
    assert ok.status_code == 200
    assert ok.json()["session"]["status"] == EnrollmentStatus.COLLECTING.value
    assert ok.json()["session"]["consent_given"] is True
    assert service.store.get_active_profile("Nolan") is None

    deferred = client.post(
        "/voice/enrollment/start",
        json={"user": "Nolan", "locale": "fr-FR", "consent_accepted": False},
    )
    sid = deferred.json()["session"]["session_id"]
    granted = client.post(
        "/voice/enrollment/consent",
        json={"session_id": sid, "accepted": True, "locale": "fr-FR"},
    )
    assert granted.status_code == 200
    assert granted.json()["ok"] is True
    assert granted.json()["session"]["consent_given"] is True
    assert granted.json()["session"]["status"] == EnrollmentStatus.COLLECTING.value
    assert service.store.get_active_profile("Nolan") is None

    reset_live_orchestrator_for_tests()
    reset_titan()
    enroll_routes._enrollment_service = None  # noqa: SLF001


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_node_consent_payload_and_enrollment_lock_contract() -> None:
    """Source-level Node checks: consent payload shape + mic lock flag."""
    script = r"""
import { readFileSync } from 'fs';
const ui = readFileSync('./web/v2/voice/enrollment-ui.js', 'utf8');
const api = readFileSync('./web/v2/voice/voice-api.js', 'utf8');
const ctrl = readFileSync('./web/v2/voice/voice-controller.js', 'utf8');
const store = readFileSync('./web/v2/core/state-store.js', 'utf8');

if (!ui.includes('consent_accepted: true') && !ui.includes('consent_accepted:true')) {
  throw new Error('missing consent_accepted:true');
}
if (!api.includes('/voice/enrollment/consent')) throw new Error('missing consent route');
if (!api.includes('/voice/enrollment/sample')) throw new Error('missing sample route');
if (!ui.includes('submitEnrollmentSample')) throw new Error('missing sample submit');
if (!ui.includes('tdl-v2-voice-record-sample')) throw new Error('missing Enregistrer');
if (!store.includes('voiceEnrollmentActive')) throw new Error('missing enrollment active flag');
if (!ctrl.includes('voiceEnrollmentActive')) throw new Error('controller missing lock');
if (!ctrl.includes('tdl-v2-voice-mic--enrollment-locked')) throw new Error('missing lock class');
if (ui.includes('Utilise le micro du compositeur pour le push-to-talk')) {
  throw new Error('misleading composer mic enrollment hint still present');
}
if (!ui.includes('Session live (PTT)')) throw new Error('live/enrollment status not separated');
console.log('ok');
"""
    result = _run_node(script)
    assert result.returncode == 0, result.stderr or result.stdout
