# =====================================
# Titan Phase 20.8 Voice Production Soak CLI
# =====================================

"""Run Phase 20.8 production soak scenarios (mock-safe by default).

Usage (from project root):

    python scripts/phase20_8_voice_soak.py

Writes ``data/phase20_8_soak/report.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.agent_manager import AgentManager
from brain.brain import Brain
from brain.llm import LLM
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.state_manager import StateManager
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService
from tools.tool_manager import ToolManager
from voice.live_session import LiveVoiceSessionOrchestrator
from voice.models import VoiceConfig
from voice.production_soak import VoiceProductionSoakRunner
from voice.speaker_identifier import SpeakerIdentifier
from voice.speaker_profile_store import SpeakerProfileStore
from voice.speech_to_text import MockSpeechToTextProvider, SpeechToTextRegistry
from voice.voice_session import VoiceSessionStore


def _speech(seed: int, seconds: float = 1.0) -> bytes:
    n = int(16000 * seconds)
    return bytes(((seed * 37 + i * 17) % 180) + 40 for i in range(n))


def main() -> int:
    out_dir = ROOT / "data" / "phase20_8_soak"
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "runtime"
    tmp.mkdir(exist_ok=True)

    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Soak reply."
    state = StateManager(file_path=tmp / "titan_state.json")
    mission = MissionManager(file_path=tmp / "titan_mission.json")
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp / "long_term_memory.json"),
    )
    brain = Brain(
        agent_manager=AgentManager(memory_service=memory),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=memory,
        tool_manager=ToolManager(project_root=tmp),
        llm=mock_llm,
    )
    brain.process_request = MagicMock(
        return_value=SimpleNamespace(final_response="Soak reply.")
    )
    store = SpeakerProfileStore(file_path=tmp / "profiles.json")
    identifier = SpeakerIdentifier(
        file_path=tmp / "legacy.json", profile_store=store, enabled=True
    )
    registry = SpeechToTextRegistry()
    registry.register(MockSpeechToTextProvider(default_text="bonjour soak"))
    orch = LiveVoiceSessionOrchestrator(
        brain,
        config=VoiceConfig(stt_provider="mock", tts_provider="mock", language="fr-FR"),
        session_store=VoiceSessionStore(file_path=tmp / "sessions.json"),
        stt_registry=registry,
        speaker_identifier=identifier,
        state_manager=state,
        temp_dir=tmp / "voice_tmp",
    )
    runner = VoiceProductionSoakRunner(orch, speech_factory=_speech)
    report = runner.run()
    path = out_dir / "report.json"
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(f"Phase 20.8 soak ok={report.ok} passed={report.to_dict()['passed']}/{report.to_dict()['scenario_count']}")
    print(f"Report: {path}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
