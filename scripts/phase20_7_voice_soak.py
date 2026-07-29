#!/usr/bin/env python3
# =====================================
# Titan Phase 20.7 — Voice Production Soak CLI
# =====================================

"""Run mock-safe voice production soak scenarios locally.

Usage (from repo root):

    python scripts/phase20_7_voice_soak.py
    python scripts/phase20_7_voice_soak.py --out data/phase20_7_soak/report.json

Does not require live provider API keys. Does not enable always-listening.
"""

from __future__ import annotations

import argparse
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
from voice.diagnostics import emit_voice_diagnostic
from voice.live_session import LiveVoiceSessionOrchestrator
from voice.models import VoiceConfig
from voice.production_soak import VoiceProductionSoakRunner
from voice.speaker_identifier import SpeakerIdentifier
from voice.speaker_profile_store import SpeakerProfileStore
from voice.speech_to_text import MockSpeechToTextProvider, SpeechToTextRegistry
from voice.voice_session import VoiceSessionStore


def _build_orchestrator(work: Path) -> LiveVoiceSessionOrchestrator:
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Réponse soak."
    state = StateManager(file_path=work / "titan_state.json")
    mission = MissionManager(file_path=work / "titan_mission.json")
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=work / "long_term_memory.json"),
    )
    brain = Brain(
        agent_manager=AgentManager(memory_service=memory),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=memory,
        tool_manager=ToolManager(project_root=work),
        llm=mock_llm,
    )
    brain.process_request = MagicMock(
        return_value=SimpleNamespace(final_response="Soak response.")
    )
    store = SpeakerProfileStore(file_path=work / "profiles.json")
    identifier = SpeakerIdentifier(file_path=work / "profiles.json", profile_store=store)
    registry = SpeechToTextRegistry()
    registry.register(MockSpeechToTextProvider(default_text="bonjour soak"))
    return LiveVoiceSessionOrchestrator(
        brain,
        config=VoiceConfig(stt_provider="mock", tts_provider="mock", language="fr-FR"),
        session_store=VoiceSessionStore(file_path=work / "voice_sessions.json"),
        stt_registry=registry,
        speaker_identifier=identifier,
        state_manager=state,
        temp_dir=work / "voice_tmp",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 20.7 voice production soak")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "phase20_7_soak" / "report.json",
        help="Write soak report JSON here",
    )
    args = parser.parse_args()
    work = args.out.parent
    work.mkdir(parents=True, exist_ok=True)
    orchestrator = _build_orchestrator(work)
    runner = VoiceProductionSoakRunner(orchestrator)
    report = runner.run()
    payload = report.to_dict()
    for result in payload.get("results", []):
        emit_voice_diagnostic(
            "VOICE_SOAK_SCENARIO",
            scenario_id=result.get("scenario_id"),
            ok=result.get("ok"),
        )
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"ok": payload["ok"], "passed": payload["passed"], "failed": payload["failed"], "out": str(args.out)}, indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
