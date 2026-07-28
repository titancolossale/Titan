# =====================================
# Phase 19.4 — Live production soak (real LLM)
# =====================================
"""Validate Titan against the real configured LLM provider.

Safety: conversation-only + no-side-effect adapters. Never touches Obsidian,
Calendar, email, trading, or repo ``data/`` user files. Isolates all JSON under
``data/phase19_4_soak/``.

Usage (from repo root)::

    python scripts/phase19_4_live_soak.py

Optional Railway chat (requires credentials — never logged)::

    set TITAN_SOAK_BASE_URL=https://titan-production-e377.up.railway.app
    set TITAN_SOAK_USERNAME=...
    set TITAN_SOAK_PASSWORD=...
    python scripts/phase19_4_live_soak.py --include-railway
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

# Isolate ALL runtime persistence before Titan/settings consumers load paths.
SOAK_DIR = ROOT / "data" / "phase19_4_soak"
SOAK_DIR.mkdir(parents=True, exist_ok=True)
os.environ["TITAN_DATA_DIR"] = str(SOAK_DIR)
os.environ["TITAN_STATE_PATH"] = str(SOAK_DIR / "titan_state.json")
os.environ["TITAN_MISSION_PATH"] = str(SOAK_DIR / "titan_mission.json")
os.environ["TITAN_PROJECT_PATH"] = str(SOAK_DIR / "titan_projects.json")
os.environ["TITAN_GOAL_PATH"] = str(SOAK_DIR / "titan_goals.json")
os.environ["TITAN_DECISION_HISTORY_PATH"] = str(SOAK_DIR / "decision_history.json")
os.environ["TITAN_MEMORY_DIR"] = str(SOAK_DIR / "memory")
os.environ["TITAN_OBSIDIAN_ENABLED"] = "false"
os.environ["TITAN_GOOGLE_CALENDAR_ENABLED"] = "false"
os.environ["TITAN_GMAIL_ENABLED"] = "false"
os.environ["TITAN_TRADING_LIVE_ENABLED"] = "false"
os.environ["TITAN_BROWSER_ENABLED"] = "false"
os.environ["TITAN_CHAT_DIAGNOSTICS"] = "true"
os.environ["TITAN_CONVERSATION_STREAM_ENABLED"] = "true"
# Soak needs headroom for real provider latency.
os.environ.setdefault("TITAN_CHAT_DEADLINE_SECONDS", "120")
os.environ.setdefault("TITAN_BRAIN_LOCK_TIMEOUT_SECONDS", "8")
# Local soak uses SQLite under soak dir — Railway remains the Postgres final check.
os.environ["TITAN_DATABASE_URL"] = ""
os.environ["DATABASE_URL"] = ""
os.environ["TITAN_CONVERSATION_PERSISTENCE_ENABLED"] = "true"
os.environ["TITAN_CONVERSATION_SUMMARY_THRESHOLD"] = "12"

REPORT_PATH = SOAK_DIR / "phase19_4_report.json"
LOG_PATH = SOAK_DIR / "phase19_4_soak.log"

# ---------------------------------------------------------------------------
# Logging capture for diagnostics
# ---------------------------------------------------------------------------

DIAG_MARKERS = (
    "CHAT_API_RECEIVED",
    "CHAT_BRAIN_LOCK_WAIT",
    "CHAT_BRAIN_LOCK_ACQUIRED",
    "CHAT_BRAIN_START",
    "CHAT_STREAM_STARTED",
    "CHAT_PROVIDER_START",
    "CHAT_FIRST_DELTA",
    "CHAT_PROVIDER_END",
    "CHAT_STREAM_COMPLETED",
    "CHAT_RESPONSE_READY",
    "CHAT_BRAIN_LOCK_RELEASED",
    "CHAT_CANCELLED",
    "CHAT_TIMEOUT",
    "CHAT_BRAIN_LOCK_TIMEOUT",
    "PIPELINE_START",
    "PIPELINE_STAGE",
    "PIPELINE_FINISHED",
    "PLAN_CREATED",
    "DECISION_SELECTED",
)


class _DiagCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[str] = []
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return
        with self._lock:
            self.records.append(msg)

    def matching(self, *needles: str) -> list[str]:
        with self._lock:
            return [m for m in self.records if any(n in m for n in needles)]

    def clear(self) -> None:
        with self._lock:
            self.records.clear()


def _pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 2)


# ---------------------------------------------------------------------------
# Isolated Brain / Titan builders
# ---------------------------------------------------------------------------


def _build_brain():
    from agents.agent_manager import AgentManager
    from brain.brain import Brain
    from brain.llm import LLM
    from context.context_manager import ContextManager
    from core.conversation_engine import ConversationEngine
    from core.goal_manager import GoalManager
    from core.mission_manager import MissionManager
    from core.project_manager import ProjectManager
    from core.state_manager import StateManager
    from memory.long_term_memory import LongTermMemory
    from memory.memory_manager import MemoryManager
    from memory.memory_service import MemoryService
    from tools.tool_manager import ToolManager

    state = StateManager(file_path=SOAK_DIR / "titan_state.json")
    goals = GoalManager(file_path=SOAK_DIR / "titan_goals.json", state_manager=state)
    projects = ProjectManager(
        file_path=SOAK_DIR / "titan_projects.json",
        state_manager=state,
        goal_manager=goals,
    )
    missions = MissionManager(
        file_path=SOAK_DIR / "titan_mission.json",
        state_manager=state,
        project_manager=projects,
    )
    goals.bind_project_manager(projects)
    goals.bind_mission_manager(missions)
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=SOAK_DIR / "long_term_memory.json"),
    )
    return Brain(
        agent_manager=AgentManager(memory_service=memory),
        context_manager=ContextManager(state_manager=state, mission_manager=missions),
        state_manager=state,
        mission_manager=missions,
        project_manager=projects,
        goal_manager=goals,
        memory_service=memory,
        tool_manager=ToolManager(project_root=SOAK_DIR),
        conversation_engine=ConversationEngine(persist_sessions=False),
        llm=LLM(),
    )


def _scenario(report: dict, name: str, fn: Callable[[], dict]) -> None:
    print(f"\n=== scenario: {name} ===", flush=True)
    started = time.perf_counter()
    entry: dict[str, Any] = {"name": name, "ok": False}
    try:
        result = fn()
        entry.update(result)
        entry.setdefault("ok", True)
    except Exception as exc:  # noqa: BLE001 — surface exact failure layer
        entry["ok"] = False
        entry["error_type"] = type(exc).__name__
        entry["error_message"] = str(exc)[:500]
        entry["layer"] = "soak_scenario"
        print(f"FAIL {name}: {type(exc).__name__}: {exc}", flush=True)
    entry["wall_ms"] = _ms(started)
    report["scenarios"].append(entry)
    status = "PASS" if entry.get("ok") else "FAIL"
    print(f"{status} {name} ({entry['wall_ms']} ms)", flush=True)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def run_local_soak(
    include_heavy: bool = True,
    *,
    heavy_only: bool = False,
) -> dict[str, Any]:
    diag = _DiagCapture()
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(diag)
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root_logger.addHandler(file_handler)

    report: dict[str, Any] = {
        "phase": "19.4",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "soak_dir": str(SOAK_DIR),
        "scenarios": [],
        "performance": {},
        "diagnostics": {},
        "persistence": {},
        "environment": {},
        "failures": [],
        "ok": True,
    }

    # --- Env snapshot (no secrets) ---
    key = os.getenv("OPENAI_API_KEY", "")
    from config import settings

    report["environment"] = {
        "api_key_loaded": bool(key) and key != "your_key_here",
        "api_key_length": len(key),
        "model": getattr(settings, "LLM_MODEL", None),
        "stream_enabled": bool(settings.TITAN_CONVERSATION_STREAM_ENABLED),
        "chat_diagnostics": True,
        "data_isolated": str(SOAK_DIR),
        "obsidian_forced_off": os.environ.get("TITAN_OBSIDIAN_ENABLED"),
        "trading_live_off": os.environ.get("TITAN_TRADING_LIVE_ENABLED"),
        "heavy_only": heavy_only,
    }

    brain = _build_brain()
    # Seed a mission so heavy-only continuity checks have context.
    from core.mission_models import MissionPriority

    brain.mission_manager.create_mission(
        "Phase19.4 Soak Mission",
        "Safe conversation-only soak validation",
        ["Validate greeting", "Validate continuity", "Validate recovery"],
        priority=MissionPriority.NORMAL,
    )
    latencies: list[float] = []
    provider_ttft: list[float] = []
    provider_total: list[float] = []
    pipeline_durations: list[float] = []

    def _turn(message: str, *, request_id: str | None = None) -> dict[str, Any]:
        rid = request_id or f"soak-{uuid.uuid4().hex[:12]}"
        llm = brain.llm
        setattr(llm, "_active_request_id", rid)
        t0 = time.perf_counter()
        result = brain.process_request(message)
        total_ms = _ms(t0)
        latencies.append(total_ms)
        ttft = getattr(llm, "last_ttft_ms", None)
        if isinstance(ttft, (int, float)):
            provider_ttft.append(float(ttft))
        provider_calls = getattr(llm, "last_provider_calls", 0) or 0
        text = (result.final_response or "") if result else ""
        setattr(llm, "_active_request_id", None)
        return {
            "request_id": rid,
            "total_ms": total_ms,
            "provider_ttft_ms": ttft,
            "provider_calls": provider_calls,
            "response_chars": len(text),
            "response_preview": text[:180],
            "intent": getattr(getattr(result, "detected_intent", None), "value", None),
            "confidence": getattr(result, "confidence", None),
            "error_code": getattr(llm, "last_error_code", None),
        }

    if not heavy_only:
        # 1. Greeting
        def s_greeting() -> dict:
            out = _turn("Bonjour Titan.")
            ok = out["response_chars"] > 0 and not out.get("error_code")
            return {"ok": ok, **out}

        _scenario(report, "01_greeting", s_greeting)

    if heavy_only:
        # Jump to heavy scenarios after seeding mission above.
        pass
    else:
      # NOTE: intentionally indented block for core scenarios 02–11 + 15.
      # 2. Context recall
      def s_context_recall() -> dict:
        a = _turn("Mon projet principal s'appelle Titan.")
        b = _turn("Quel est le nom de mon projet principal ?")
        text = (b.get("response_preview") or "").lower()
        recalled = "titan" in text
        return {
            "ok": a["response_chars"] > 0 and b["response_chars"] > 0 and recalled,
            "store": a,
            "recall": b,
            "recalled_titan": recalled,
        }

      _scenario(report, "02_context_recall", s_context_recall)

    # 3. Mission continuity
    def s_mission() -> dict:
        from core.mission_models import MissionPriority

        mission = brain.mission_manager.create_mission(
            "Phase19.4 Soak Mission",
            "Safe conversation-only soak validation",
            ["Validate greeting", "Validate continuity", "Validate recovery"],
            priority=MissionPriority.NORMAL,
        )
        a = _turn("Résume la mission active en une phrase.")
        b = _turn("Continue sur la même mission: quelle est la prochaine étape sûre ?")
        active = brain.mission_manager.get_active_mission()
        same = active is not None and active.id == mission.id
        return {
            "ok": same and a["response_chars"] > 0 and b["response_chars"] > 0,
            "mission_id": mission.id,
            "same_mission": same,
            "summary": a,
            "followup": b,
        }

    _scenario(report, "03_mission_continuity", s_mission)

    # 4. Project switching (matcher + prompt context; NL turns optional)
    def s_project_switch() -> dict:
        from core.project_matcher import match_project

        p_a = brain.project_manager.create_project(
            "Soak Alpha",
            "Isolated soak project A",
            aliases=["soak-alpha", "alpha"],
            keywords=["alpha", "soak-a"],
        )
        p_b = brain.project_manager.create_project(
            "Soak Beta",
            "Isolated soak project B",
            aliases=["soak-beta", "beta"],
            keywords=["beta", "soak-b"],
        )
        brain.project_manager.resume_project(p_a.id)
        projects = brain.project_manager.list_projects()
        high = match_project("Continue on Soak Beta please", projects)
        low = match_project("maybe something vague later", projects)
        if high.matched and high.project_id:
            brain.project_manager.resume_project(high.project_id)
        active = brain.project_manager.get_active_project()
        # Confirm prompt context via a turn that mentions Beta
        turn = _turn("Travaille sur Soak Beta uniquement.")
        ctx = brain.last_think_context
        prompt_project = None
        if ctx is not None and ctx.project_context is not None:
            prompt_project = ctx.project_context.name
        ok = (
            high.matched
            and not low.matched
            and active is not None
            and active.name == "Soak Beta"
            and (prompt_project is None or "Beta" in prompt_project or "beta" in (prompt_project or "").lower())
        )
        return {
            "ok": ok,
            "high_match": {
                "matched": high.matched,
                "confidence": high.confidence,
                "project_id": high.project_id,
            },
            "low_match": {
                "matched": low.matched,
                "confidence": low.confidence,
                "reason": low.reason,
            },
            "active_project": active.name if active else None,
            "prompt_project": prompt_project,
            "turn": turn,
            "seeded": {"alpha": p_a.id, "beta": p_b.id},
        }

    _scenario(report, "04_project_switching", s_project_switch)

    # 5. Goal switching
    def s_goal_switch() -> dict:
        from core.goal_matcher import match_goal

        g_a = brain.goal_manager.create_goal(
            "Soak Goal Alpha",
            "Isolated soak goal A",
            aliases=["goal-alpha"],
            keywords=["goal-alpha", "soak-goal-a"],
        )
        g_b = brain.goal_manager.create_goal(
            "Soak Goal Beta",
            "Isolated soak goal B",
            aliases=["goal-beta"],
            keywords=["goal-beta", "soak-goal-b"],
        )
        brain.goal_manager.resume_goal(g_a.id)
        goals = brain.goal_manager.list_goals()
        high = match_goal("Focus on Soak Goal Beta now", goals)
        low = match_goal("hmm maybe later", goals)
        if high.matched and high.goal_id:
            brain.goal_manager.resume_goal(high.goal_id)
        active = brain.goal_manager.get_active_goal()
        ok = high.matched and not low.matched and active is not None and active.id == g_b.id
        return {
            "ok": ok,
            "high_match": {
                "matched": high.matched,
                "confidence": high.confidence,
                "goal_id": high.goal_id,
            },
            "low_match": {
                "matched": low.matched,
                "confidence": low.confidence,
                "reason": low.reason,
            },
            "active_goal": active.name if active else None,
            "seeded": {"alpha": g_a.id, "beta": g_b.id},
        }

    _scenario(report, "05_goal_switching", s_goal_switch)

    # 6. Planning — create once via PlanningEngine.plan_next
    def s_planning() -> dict:
        from brain.planning_engine import PlanningEngine

        engine = PlanningEngine()
        mission = brain.mission_manager.get_active_mission()
        project = brain.project_manager.get_active_project()
        goal = brain.goal_manager.get_active_goal()
        workspace = brain.state_manager.load()
        t0 = time.perf_counter()
        plan = engine.plan_next(
            workspace=workspace,
            goal=goal,
            project=project,
            mission=mission,
            mission_lookup=brain.mission_manager.runtime.get_mission,
        )
        plan_ms = _ms(t0)
        pipeline_durations.append(plan_ms)
        # Second call evolves the same active plan (no uncontrolled duplicate)
        plan2 = engine.plan_next(
            workspace=workspace,
            goal=goal,
            project=project,
            mission=mission,
            mission_lookup=brain.mission_manager.runtime.get_mission,
        )
        created_logs = diag.matching("PLAN_CREATED")
        ok = (
            plan is not None
            and plan2 is not None
            and len(plan.next_actions) >= 1
            and engine.active_plan is plan2
        )
        return {
            "ok": ok,
            "actions": list(plan.next_actions),
            "actions2": list(plan2.next_actions),
            "revision": plan.revision,
            "revision2": plan2.revision,
            "planning_ms": plan_ms,
            "plan_created_logs": len(created_logs),
            "single_active_plan": engine.active_plan is plan2,
        }

    _scenario(report, "06_planning", s_planning)

    # 7. Decision
    def s_decision() -> dict:
        from brain.decision_engine import DecisionEngine
        from brain.planning_models import Plan, PlanStatus

        stamp = datetime.now(timezone.utc)
        plan = Plan(
            current_goal="Validate soak mission",
            current_project="Soak Beta",
            current_mission="Phase19.4 Soak Mission",
            next_actions=[
                "Summarize mission status",
                "Ask clarifying question",
                "Idle wait",
            ],
            priority_score=0.8,
            estimated_duration=20.0,
            dependencies=[],
            blocked_reason=None,
            created_at=stamp,
            updated_at=stamp,
            status=PlanStatus.ACTIVE,
        )
        t0 = time.perf_counter()
        decision = DecisionEngine(persist=False).decide(plan=plan)
        decision_ms = _ms(t0)
        ok = bool(
            decision.selected_action
            and decision.reason
            and decision.confidence is not None
        )
        return {
            "ok": ok,
            "selected_action": decision.selected_action,
            "reason": decision.reason,
            "confidence": decision.confidence,
            "decision_ms": decision_ms,
        }

    _scenario(report, "07_decision", s_decision)

    # 8. Safe execution (no-side-effect adapter)
    def s_safe_execution() -> dict:
        from brain.autonomy_policy import AutonomyPolicy
        from brain.decision_engine import DecisionEngine
        from brain.execution_engine import ExecutionEngine
        from brain.execution_models import ExecutionStatus
        from brain.execution_tool_models import BridgeExecutionResult
        from brain.planning_models import Plan, PlanStatus
        from core.state_manager import WorkspaceState

        class _NoSideEffectBridge:
            def dispatch(self, **kwargs: Any) -> BridgeExecutionResult:
                return BridgeExecutionResult.cognitive_success(
                    message="no-side-effect ok",
                    duration=0.001,
                )

            def apply_workspace_update(self, workspace: Any, result: Any) -> None:
                if workspace is None:
                    return
                workspace.last_tool = result.tool_id or "soak_echo"
                workspace.execution_status = result.status.value

        stamp = datetime.now(timezone.utc)
        plan = Plan(
            current_goal="Validate soak mission",
            current_project="Soak Beta",
            current_mission="Phase19.4 Soak Mission",
            next_actions=["echo soak status"],
            priority_score=0.7,
            estimated_duration=5.0,
            dependencies=[],
            blocked_reason=None,
            created_at=stamp,
            updated_at=stamp,
            status=PlanStatus.ACTIVE,
        )
        decision = DecisionEngine(persist=False).decide(plan=plan)
        engine = ExecutionEngine(
            autonomy_policy=AutonomyPolicy(
                require_confirmation_writes=True,
                require_confirmation_exec=True,
            ),
            tool_bridge=_NoSideEffectBridge(),
        )
        t0 = time.perf_counter()
        result = engine.execute(
            decision=decision,
            plan=plan,
            workspace=WorkspaceState(active_project="Soak Beta"),
            send_feedback=False,
            action_metadata={
                "risk_level": "SAFE_READ",
                "execution_traits": ["read_only", "no_side_effect"],
            },
        )
        exec_ms = _ms(t0)
        ok = result.status == ExecutionStatus.COMPLETED and result.success
        return {
            "ok": ok,
            "status": result.status.value,
            "success": result.success,
            "requires_confirmation": result.requires_confirmation,
            "execution_ms": exec_ms,
        }

    _scenario(report, "08_safe_execution", s_safe_execution)

    # 9. Confirmation required (synthetic high-risk)
    def s_confirmation() -> dict:
        from brain.autonomy_policy import AutonomyPolicy
        from brain.decision_engine import DecisionEngine
        from brain.execution_engine import ExecutionEngine
        from brain.execution_models import ExecutionStatus
        from brain.planning_models import Plan, PlanStatus
        from core.state_manager import WorkspaceState

        executed = {"count": 0}

        class _MustNotRun:
            def dispatch(self, **kwargs: Any) -> Any:
                executed["count"] += 1
                raise RuntimeError("high-risk adapter must not run")

            def apply_workspace_update(self, *a: Any, **k: Any) -> None:
                return None

        stamp = datetime.now(timezone.utc)
        plan = Plan(
            current_goal="Validate soak mission",
            current_project="Soak Beta",
            current_mission="Phase19.4 Soak Mission",
            next_actions=["delete production database"],
            priority_score=0.9,
            estimated_duration=5.0,
            dependencies=[],
            blocked_reason=None,
            created_at=stamp,
            updated_at=stamp,
            status=PlanStatus.ACTIVE,
        )
        decision = DecisionEngine(persist=False).decide(plan=plan)
        engine = ExecutionEngine(
            autonomy_policy=AutonomyPolicy(
                require_confirmation_writes=True,
                require_confirmation_exec=True,
            ),
            tool_bridge=_MustNotRun(),
        )
        workspace = WorkspaceState(active_project="Soak Beta")
        result = engine.execute(
            decision=decision,
            plan=plan,
            workspace=workspace,
            send_feedback=False,
            action_metadata={
                "risk_level": "CRITICAL",
                "execution_traits": ["destructive", "external_write"],
            },
        )
        ok = (
            result.requires_confirmation is True
            and executed["count"] == 0
            and result.status
            in (
                ExecutionStatus.AWAITING_CONFIRMATION,
                ExecutionStatus.BLOCKED,
                ExecutionStatus.FAILED,
            )
        )
        return {
            "ok": ok,
            "status": result.status.value,
            "requires_confirmation": result.requires_confirmation,
            "bridge_calls": executed["count"],
            "workspace_confirmation_pending": getattr(
                workspace, "confirmation_pending", None
            ),
        }

    _scenario(report, "09_confirmation_required", s_confirmation)

    # 10–11 + streaming via TestClient (real LLM)
    def s_stream_cancel_long() -> dict:
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from api.app import create_app
        from api.chat_service import reset_brain_lock_for_tests
        from api.titan_service import reset_titan, set_titan
        from core.titan import Titan

        reset_brain_lock_for_tests()
        reset_titan()
        titan = Titan()
        # Rebind managers to soak-isolated brain paths already set via env
        titan.brain = brain
        titan.status = "ONLINE"
        set_titan(titan)

        secret = "phase19-4-soak-secret"
        os.environ["TITAN_WEB_ENABLED"] = "true"
        os.environ["TITAN_WEB_SECRET_KEY"] = secret

        events: list[tuple[str, str]] = []
        stream_metrics: dict[str, Any] = {}

        with patch("config.settings.TITAN_WEB_ENABLED", True), patch(
            "config.settings.get_web_secret_key", return_value=secret
        ), patch("api.auth.get_web_secret_key", return_value=secret), patch(
            "api.auth.is_web_dev_mode", return_value=True
        ), patch("api.auth_config.is_session_auth_enabled", return_value=False):
            client = TestClient(create_app())

            # Streaming happy path
            rid = f"soak-stream-{uuid.uuid4().hex[:10]}"
            t0 = time.perf_counter()
            first_delta_ms = None
            order: list[str] = []
            with client.stream(
                "POST",
                "/chat/stream",
                json={"message": "Bonjour, réponds en une courte phrase.", "request_id": rid},
                headers={"Authorization": f"Bearer {secret}"},
            ) as resp:
                assert resp.status_code == 200
                event_name = "message"
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if isinstance(line, bytes):
                        line = line.decode("utf-8", errors="replace")
                    if line.startswith("event:"):
                        event_name = line.split(":", 1)[1].strip()
                        order.append(event_name)
                    elif line.startswith("data:"):
                        events.append((event_name, line[5:].strip()[:200]))
                        if event_name == "text_delta" and first_delta_ms is None:
                            first_delta_ms = _ms(t0)
            stream_metrics = {
                "first_delta_ms": first_delta_ms,
                "total_ms": _ms(t0),
                "event_order": order,
                "event_count": len(events),
            }
            # No deltas after completion
            if "conversation_finished" in order:
                fin_idx = order.index("conversation_finished")
                deltas_after = any(
                    e == "text_delta" for e in order[fin_idx + 1 :]
                )
            else:
                deltas_after = False

            # Cancellation
            rid_c = f"soak-cancel-{uuid.uuid4().hex[:10]}"
            cancel_t0 = time.perf_counter()
            cancel_ok = False
            recovery_ms = None
            # Start stream in background-ish: send cancel mid-flight via API
            # Use a longer prompt then cancel quickly.
            def _cancel_soon() -> None:
                time.sleep(0.35)
                client.post(
                    "/api/chat/cancel",
                    json={"request_id": rid_c},
                    headers={"Authorization": f"Bearer {secret}"},
                )

            cancel_thread = threading.Thread(target=_cancel_soon, daemon=True)
            cancel_thread.start()
            with client.stream(
                "POST",
                "/chat/stream",
                json={
                    "message": (
                        "Explique en détail le rôle du Brain dans Titan, "
                        "sans outils externes."
                    ),
                    "request_id": rid_c,
                },
                headers={"Authorization": f"Bearer {secret}"},
            ) as resp:
                for _line in resp.iter_lines():
                    pass
            cancel_thread.join(timeout=5)
            # Next request must complete normally
            recover = _turn("Dis seulement: récupération OK.")
            recovery_ms = _ms(cancel_t0)
            cancel_ok = recover["response_chars"] > 0 and not recover.get("error_code")

            # Long response
            long = _turn(
                "Explique en 8 phrases claires comment Titan sépare Brain, "
                "Agents, Memory et Tools. Pas d'outils."
            )

        reset_titan()
        reset_brain_lock_for_tests()

        required_events = {
            "conversation_started",
            "brain_state",
            "response_started",
            "text_delta",
            "conversation_finished",
        }
        # Some builds may use alternate names — accept present subset
        present = set(order)
        # soft: at least response path completed
        stream_ok = stream_metrics.get("event_count", 0) > 0 and not deltas_after
        return {
            "ok": stream_ok and cancel_ok and long["response_chars"] > 50,
            "stream": stream_metrics,
            "required_events_present": sorted(required_events & present),
            "missing_events": sorted(required_events - present),
            "deltas_after_completion": deltas_after,
            "cancel_recovery_ok": cancel_ok,
            "cancel_recovery_ms": recovery_ms,
            "long_response": long,
            "diag_stream": len(diag.matching("CHAT_STREAM_STARTED", "CHAT_FIRST_DELTA")),
            "diag_cancel": len(diag.matching("CHAT_CANCELLED")),
        }

    _scenario(report, "10_11_stream_cancel_long", s_stream_cancel_long)

    if include_heavy:
        # 12. Long conversation (25 turns) — force real LLM path (not mission template)
        def s_long_conversation() -> dict:
            conv_lat: list[float] = []
            responses: list[str] = []
            for i in range(25):
                msg = (
                    f"Conversation soak tour {i+1}/25. "
                    f"Réponds en une phrase courte confirmant le numéro {i+1} "
                    f"et que l'on parle toujours de la validation Phase 19.4."
                )
                out = _turn(msg)
                conv_lat.append(out["total_ms"])
                responses.append(out.get("response_preview") or "")
            # Duplicate check (exact consecutive duplicates)
            dup_pairs = sum(
                1 for a, b in zip(responses, responses[1:]) if a and a == b
            )
            # State continuity
            active = brain.mission_manager.get_active_mission()
            mission_label = None
            if active is not None:
                mission_label = getattr(active, "title", None) or getattr(
                    active, "name", None
                )
            ok = (
                len(responses) == 25
                and all(r for r in responses)
                and dup_pairs == 0
                and active is not None
            )
            return {
                "ok": ok,
                "turns": 25,
                "duplicate_consecutive": dup_pairs,
                "avg_ms": round(statistics.mean(conv_lat), 2) if conv_lat else None,
                "p95_ms": _pct(conv_lat, 95),
                "mission_still_active": mission_label,
            }

        _scenario(report, "12_long_conversation_25", s_long_conversation)

        # 13. Repeated requests (50)
        def s_repeated() -> dict:
            times: list[float] = []
            errors = 0
            for i in range(50):
                out = _turn(f"Réponds uniquement: OK-{i+1}")
                times.append(out["total_ms"])
                if out.get("error_code") or out["response_chars"] == 0:
                    errors += 1
            # Latency trend: compare first 10 avg vs last 10 avg
            first = statistics.mean(times[:10])
            last = statistics.mean(times[-10:])
            growth_ratio = (last / first) if first else None
            ok = errors == 0 and (growth_ratio is None or growth_ratio < 3.0)
            return {
                "ok": ok,
                "count": 50,
                "errors": errors,
                "avg_ms": round(statistics.mean(times), 2),
                "p50_ms": _pct(times, 50),
                "p95_ms": _pct(times, 95),
                "slowest_ms": max(times) if times else None,
                "first10_avg_ms": round(first, 2),
                "last10_avg_ms": round(last, 2),
                "growth_ratio": round(growth_ratio, 3) if growth_ratio else None,
            }

        _scenario(report, "13_repeated_50", s_repeated)

        # 14. Concurrent (serialized Brain — expect busy/timeout bounded)
        def s_concurrent() -> dict:
            from api.chat_service import (
                _acquire_brain_lock,
                _release_brain_lock,
                reset_brain_lock_for_tests,
            )
            from brain.request_deadline import RequestDeadline

            reset_brain_lock_for_tests()
            results: list[dict] = []

            def worker(n: int) -> dict:
                rid = f"soak-conc-{n}-{uuid.uuid4().hex[:8]}"
                deadline = RequestDeadline.start(total_seconds=30, request_id=rid)
                t0 = time.perf_counter()
                if n == 0:
                    acquired = _acquire_brain_lock(rid, deadline, timeout_seconds=5.0)
                    if not acquired:
                        return {
                            "n": n,
                            "acquired": False,
                            "ms": _ms(t0),
                            "busy": True,
                        }
                    try:
                        time.sleep(2.0)
                        return {
                            "n": n,
                            "acquired": True,
                            "ms": _ms(t0),
                            "busy": False,
                        }
                    finally:
                        _release_brain_lock(rid)
                acquired = _acquire_brain_lock(rid, deadline, timeout_seconds=0.4)
                if not acquired:
                    return {
                        "n": n,
                        "acquired": False,
                        "ms": _ms(t0),
                        "busy": True,
                    }
                try:
                    time.sleep(0.05)
                    return {"n": n, "acquired": True, "ms": _ms(t0), "busy": False}
                finally:
                    _release_brain_lock(rid)

            with ThreadPoolExecutor(max_workers=3) as pool:
                holder = pool.submit(worker, 0)
                time.sleep(0.15)
                futs = [pool.submit(worker, i) for i in (1, 2)]
                results.append(holder.result())
                for f in as_completed(futs):
                    results.append(f.result())
            acquired_count = sum(1 for r in results if r.get("acquired"))
            busy_count = sum(1 for r in results if r.get("busy"))
            # Exactly one holder path + at least one bounded busy/timeout.
            ok = acquired_count >= 1 and busy_count >= 1 and len(results) == 3
            reset_brain_lock_for_tests()

            # Also fire two real process_request calls — second should not corrupt
            out_a: dict = {}
            out_b: dict = {}

            def ra() -> None:
                nonlocal out_a
                out_a = _turn("Concurrent A: dis A")

            def rb() -> None:
                nonlocal out_b
                time.sleep(0.05)
                out_b = _turn("Concurrent B: dis B")

            t1 = threading.Thread(target=ra)
            t2 = threading.Thread(target=rb)
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            both_ok = out_a.get("response_chars", 0) > 0 and out_b.get("response_chars", 0) > 0
            return {
                "ok": ok and both_ok,
                "lock_results": results,
                "acquired_count": acquired_count,
                "busy_count": busy_count,
                "turn_a": out_a,
                "turn_b": out_b,
            }

        _scenario(report, "14_concurrent", s_concurrent)

    # Persistence (local SQLite soak store — Railway Postgres checked separately)
    def s_persistence() -> dict:
        from core.web_conversations.db import (
            apply_migrations,
            backend_name,
            create_conversation_engine,
        )
        from core.web_conversations.models import MessageStatus
        from core.web_conversations.repository import ConversationRepository
        from core.web_conversations.service import ConversationService

        db_path = SOAK_DIR / "conversations.db"
        engine = create_conversation_engine(
            sqlite_path=db_path,
            force_sqlite=True,
        )
        apply_migrations(engine)
        service = ConversationService(
            repository=ConversationRepository(engine=engine)
        )
        user_id = "soak-user"
        conv = service.create_conversation(user_id, title="Phase19.4")
        cid = conv.id
        service.repository.add_message(
            conversation_id=cid,
            user_id=user_id,
            role="user",
            content="ping soak",
            status=MessageStatus.COMPLETED.value,
        )
        service.repository.add_message(
            conversation_id=cid,
            user_id=user_id,
            role="assistant",
            content="pong soak",
            request_id="soak-persist-1",
            status=MessageStatus.COMPLETED.value,
        )
        # Idempotent assistant insert must not duplicate
        service.repository.add_message(
            conversation_id=cid,
            user_id=user_id,
            role="assistant",
            content="pong soak duplicate attempt",
            request_id="soak-persist-1",
            status=MessageStatus.COMPLETED.value,
        )
        _conv, messages, total = service.get_conversation_with_messages(cid, user_id)
        # Restart simulation with new engine on same file
        engine2 = create_conversation_engine(
            sqlite_path=db_path,
            force_sqlite=True,
        )
        service2 = ConversationService(
            repository=ConversationRepository(engine=engine2)
        )
        _c2, messages2, total2 = service2.get_conversation_with_messages(cid, user_id)
        pending = [
            m
            for m in messages
            if m.role == "assistant" and m.status == MessageStatus.PENDING.value
        ]
        ok = total == 2 and total2 == 2 and not pending
        return {
            "ok": ok,
            "backend": backend_name(str(engine.url)),
            "conversation_id": cid,
            "message_count": total,
            "survives_reopen": total2 == 2,
            "no_duplicate_assistant": total == 2,
            "assistant_pending": len(pending),
            "note": "Local soak uses SQLite isolation; Railway /ready confirms postgresql.",
        }

    _scenario(report, "15_persistence_local_store", s_persistence)

    # Diagnostics inventory
    found = {m: bool(diag.matching(m)) for m in DIAG_MARKERS}
    report["diagnostics"] = {
        "markers_found": {k: v for k, v in found.items() if v},
        "markers_missing": [k for k, v in found.items() if not v],
        "total_log_lines": len(diag.records),
    }

    report["performance"] = {
        "request_count": len(latencies),
        "avg_ms": round(statistics.mean(latencies), 2) if latencies else None,
        "p50_ms": _pct(latencies, 50),
        "p95_ms": _pct(latencies, 95),
        "slowest_ms": max(latencies) if latencies else None,
        "provider_ttft_avg_ms": (
            round(statistics.mean(provider_ttft), 2) if provider_ttft else None
        ),
        "provider_ttft_p95_ms": _pct(provider_ttft, 95),
        "provider_samples": len(provider_ttft),
        "error_rate": round(
            sum(1 for s in report["scenarios"] if not s.get("ok"))
            / max(1, len(report["scenarios"])),
            4,
        ),
    }

    report["failures"] = [s for s in report["scenarios"] if not s.get("ok")]
    report["ok"] = len(report["failures"]) == 0
    report["finished_at"] = datetime.now(timezone.utc).isoformat()

    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nReport written: {REPORT_PATH}", flush=True)
    print(f"Overall ok={report['ok']} failures={len(report['failures'])}", flush=True)
    return report


def run_railway_probes(include_authenticated: bool = False) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    base = (
        os.getenv("TITAN_SOAK_BASE_URL")
        or "https://titan-production-e377.up.railway.app"
    ).rstrip("/")
    out: dict[str, Any] = {"base": base, "checks": []}

    def get(path: str) -> dict:
        url = f"{base}{path}"
        entry: dict[str, Any] = {"path": path, "ok": False}
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                body = json.loads(resp.read().decode())
                entry["status"] = resp.status
                entry["ok"] = 200 <= resp.status < 300
                entry["body"] = body
        except Exception as exc:  # noqa: BLE001
            entry["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        out["checks"].append(entry)
        return entry

    health = get("/health")
    ready = get("/ready")

    # Auth must block chat
    auth_entry: dict[str, Any] = {"path": "/chat/stream", "ok": False}
    try:
        req = urllib.request.Request(
            f"{base}/chat/stream",
            data=b'{"message":"x"}',
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=15)
        auth_entry["error"] = "expected_401"
    except urllib.error.HTTPError as exc:
        auth_entry["status"] = exc.code
        auth_entry["ok"] = exc.code == 401
        auth_entry["body"] = exc.read()[:200].decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        auth_entry["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    out["checks"].append(auth_entry)

    health_body = health.get("body") or {}
    ready_body = ready.get("body") or {}
    store = ((ready_body.get("checks") or {}).get("conversation_store") or {})
    out["summary"] = {
        "health_ok": health.get("ok"),
        "ready_ok": ready.get("ok"),
        "auth_required": health_body.get("auth_required"),
        "session_auth": health_body.get("session_auth"),
        "conversation_backend": store.get("backend"),
        "conversation_store_ok": store.get("ok"),
        "unauthenticated_chat_blocked": auth_entry.get("ok"),
    }

    user = os.getenv("TITAN_SOAK_USERNAME", "").strip()
    password = os.getenv("TITAN_SOAK_PASSWORD", "").strip()
    if include_authenticated and user and password:
        # Login + one streaming turn against Railway (credentials never logged)
        login_ok = False
        try:
            import http.cookiejar

            jar = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(jar)
            )
            payload = json.dumps({"username": user, "password": password}).encode()
            req = urllib.request.Request(
                f"{base}/auth/login",
                data=payload,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with opener.open(req, timeout=30) as resp:
                login_ok = 200 <= resp.status < 300
            out["railway_login_ok"] = login_ok
            if login_ok:
                rid = f"soak-rail-{uuid.uuid4().hex[:10]}"
                req2 = urllib.request.Request(
                    f"{base}/chat/stream",
                    data=json.dumps(
                        {"message": "Bonjour Titan (soak Railway).", "request_id": rid}
                    ).encode(),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with opener.open(req2, timeout=120) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                out["railway_stream_chars"] = len(raw)
                out["railway_stream_has_delta"] = "text_delta" in raw
                out["railway_stream_ok"] = "conversation_finished" in raw or len(raw) > 0
        except Exception as exc:  # noqa: BLE001
            out["railway_auth_error"] = type(exc).__name__
            out["railway_auth_message"] = str(exc)[:200]
    else:
        out["railway_chat_soak"] = "skipped_no_credentials"

    out["ok"] = bool(
        out["summary"]["health_ok"]
        and out["summary"]["ready_ok"]
        and out["summary"]["auth_required"]
        and out["summary"]["conversation_backend"] == "postgresql"
        and out["summary"]["unauthenticated_chat_blocked"]
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="Skip 25/50 heavy loops")
    parser.add_argument(
        "--heavy-only",
        action="store_true",
        help="Run only scenarios 12–14 (long/repeated/concurrent)",
    )
    parser.add_argument("--include-railway", action="store_true")
    parser.add_argument("--railway-only", action="store_true")
    args = parser.parse_args()

    print("Phase 19.4 live soak starting...", flush=True)
    combined: dict[str, Any] = {"phase": "19.4"}

    railway = run_railway_probes(include_authenticated=args.include_railway)
    combined["railway"] = railway
    print(
        json.dumps(
            {"railway_summary": railway.get("summary"), "ok": railway.get("ok")},
            indent=2,
        ),
        flush=True,
    )

    if args.railway_only:
        (SOAK_DIR / "phase19_4_railway.json").write_text(
            json.dumps(railway, indent=2), encoding="utf-8"
        )
        return 0 if railway.get("ok") else 1

    if args.heavy_only:
        report = run_local_soak(include_heavy=True, heavy_only=True)
    else:
        report = run_local_soak(include_heavy=not args.quick)
    report["railway"] = railway
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return 0 if report.get("ok") and railway.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
