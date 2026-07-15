# =====================================
# Titan Web V2 — Phase 9 Cognitive Operating System Tests
# =====================================

"""Frontend contracts for Phase 9 Cognitive Operating System.

Scope guard: presentation telemetry only — top-bar module states / workspace
surfaces / runtime monitor / cognitive-os.css. No Brain, API, Memory, neural
engine rewrite, layout redesign, or color system changes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "web" / "v2"
TOPBAR = V2 / "center" / "topbar-region.js"
STATUS = V2 / "status" / "status-region.js"
ORCH = V2 / "orchestrator" / "orchestrator-region.js"
TELEMETRY = V2 / "core" / "cognitive-os-telemetry.js"
CSS = V2 / "design" / "cognitive-os.css"
DOCS = ROOT / "docs" / "WEB_APP_COGNITIVE_OS.md"


def _node_available() -> bool:
    return shutil.which("node") is not None


def _run_node(script: str) -> str:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout.strip()


def test_phase9_cognitive_os_stylesheet_loaded_last() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert "./design/cognitive-os.css" in html
    assert CSS.exists()
    assert html.index("./design/living-presence.css") < html.index(
        "./design/cognitive-os.css"
    )
    # Canonical final reference may follow Phase 9 as absolute last authority.
    if "./design/canonical-final.css" in html:
        assert html.index("./design/cognitive-os.css") < html.index(
            "./design/canonical-final.css"
        )


def test_phase9_cognitive_os_css_contracts() -> None:
    css = CSS.read_text(encoding="utf-8")
    for token in (
        "Phase 9",
        "COGNITIVE OPERATING SYSTEM",
        "data-cognitive",
        "tdl-v2-orchestrator-monitor",
        "tdl-v2-workspace-metrics",
        "tdl-cos-pill-breathe",
        "prefers-reduced-motion",
        "No new colors",
        "no layout rebuild",
    ):
        assert token in css


def test_phase9_module_cognitive_states() -> None:
    telemetry = TELEMETRY.read_text(encoding="utf-8")
    for state in (
        "idle",
        "reading",
        "searching",
        "planning",
        "reasoning",
        "writing",
        "waiting",
        "finished",
    ):
        assert f'"{state}"' in telemetry
    for fn in (
        "resolveMemoryModuleState",
        "resolveReflectionModuleState",
        "resolvePresenceModuleState",
        "resolveToolsModuleState",
        "resolveBrainModuleState",
        "resolveRuntimeModuleState",
        "formatReasoningStage",
        "formatMemoryAccess",
        "formatModelState",
        "formatPlanningQueue",
    ):
        assert fn in telemetry
    assert "Never invents backend" in telemetry or "never invents" in telemetry.lower()


def test_phase9_topbar_module_states() -> None:
    topbar = TOPBAR.read_text(encoding="utf-8")
    assert "tdl-v2-topbar--cognitive-os" in topbar
    assert 'dataset.phase = "9"' in topbar or 'dataset.phase = "10"' in topbar
    assert "data-cognitive" in topbar or "dataset.cognitive" in topbar
    assert "resolveModuleTelemetry" in topbar
    assert "MODULE_STATE_LABELS" in topbar
    for module in ("memory", "reflection", "presence", "tools", "mode", "runtime"):
        assert f'"{module}"' in topbar or f"pill--{module}" in topbar or f"-{module}" in topbar


def test_phase9_workspace_surfaces() -> None:
    status = STATUS.read_text(encoding="utf-8")
    assert "tdl-v2-workspace-dock--cognitive-os" in status
    assert 'dataset.living = "9"' in status or 'dataset.living = "10"' in status
    assert "card-memory-confidence" in status
    assert "card-memory-scan" in status
    assert "card-obsidian-sync" in status
    assert "card-obsidian-activity" in status
    assert "card-browser-nav" in status
    assert "card-browser-network" in status
    assert "card-cognitive-attention" in status
    assert "card-cognitive-depth" in status
    assert "card-cognitive-confidence" in status
    assert "tdl-v2-presence-engagement" in status
    assert "tdl-v2-presence-focus" in status
    assert "tdl-v2-presence-availability" in status
    assert "formatPresenceSurface" in status


def test_phase9_runtime_monitor() -> None:
    orch = ORCH.read_text(encoding="utf-8")
    assert "tdl-v2-orchestrator--cognitive-os" in orch
    assert "Runtime Monitor" in orch
    assert "_runtimeMonitorBlock" in orch
    assert "_updateRuntimeMonitor" in orch
    assert "tdl-v2-orch-monitor-${" in orch or "tdl-v2-orch-monitor-" in orch
    for key in (
        "reasoning",
        "execution",
        "systems",
        "tools",
        "memory",
        "latency",
        "model",
        "planning",
    ):
        assert f'id: "{key}"' in orch or f'"{key}"' in orch
    assert "no fake execution" in orch.lower() or "honest" in orch.lower()


def test_phase9_honest_state_only() -> None:
    for path in (TOPBAR, STATUS, ORCH, TELEMETRY):
        text = path.read_text(encoding="utf-8")
        for banned in (
            "remember_user_note",
            "create_note",
            "POST /api",
            "fake_execution",
            "simulateBackend",
        ):
            assert banned not in text


def test_phase9_docs_exist() -> None:
    assert DOCS.exists()
    docs = DOCS.read_text(encoding="utf-8")
    assert "Phase 9" in docs
    assert "Cognitive Operating System" in docs
    assert "Runtime Monitor" in docs
    assert "Idle" in docs
    assert "Reasoning" in docs


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_phase9_telemetry_resolver() -> None:
    out = _run_node(
        """
import {
  MODULE_COGNITIVE_STATES,
  resolveModuleTelemetry,
  formatModelState,
  formatReasoningStage,
} from './web/v2/core/cognitive-os-telemetry.js';

const idle = {
  presence: 'idle',
  cognitiveState: 'idle',
  connectionState: 'connected',
  pipelineThinking: false,
  conversationActive: false,
  recallActive: false,
  activeToolCount: 0,
  activeToolIds: [],
  presenceLevel: 42,
  orchestrationConfidence: null,
  orchestrationDuration: null,
  conversationPlanSteps: [],
  systemsUsed: null,
  memoryStatusLine: 'Mémoire — en veille',
  pipelineLabel: '',
  conversationThinkingLine: '',
  conversationReasoningLine: '',
  conversationStage: null,
  conversationEventType: null,
  memoryEventType: null,
  reasoningSummary: '',
  detectedIntent: null,
};

const thinking = {
  ...idle,
  pipelineThinking: true,
  presence: 'thinking',
  cognitiveState: 'reasoning',
  conversationActive: true,
  orchestrationConfidence: 0.82,
};

const mods = resolveModuleTelemetry(idle);
if (mods.brain !== 'idle') throw new Error('brain should be idle');
if (mods.memory !== 'idle') throw new Error('memory should be idle');

const live = resolveModuleTelemetry(thinking);
if (live.reflection !== 'reasoning') throw new Error('reflection should be reasoning');
if (live.brain !== 'reasoning') throw new Error('brain should be reasoning');
if (formatModelState(thinking) !== 'Inférence') throw new Error('model state');
if (formatReasoningStage(thinking) !== 'Raisonnement') throw new Error('stage');

if (MODULE_COGNITIVE_STATES.length !== 8) throw new Error('expected 8 states');
console.log(JSON.stringify({ ok: true, idle: mods, live }));
"""
    )
    payload = json.loads(out.splitlines()[-1])
    assert payload["ok"] is True
    assert payload["idle"]["brain"] == "idle"
    assert payload["live"]["reflection"] == "reasoning"


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_phase9_ui_version_bump() -> None:
    out = _run_node(
        """
import {
  TITAN_UI_VERSION,
  TITAN_UI_VERSION_LABEL,
  TITAN_PRODUCT_VERSION,
} from './web/v2/core/version.js';
const ok = ['0.51.0','0.50.0', '0.48.0'].includes(TITAN_UI_VERSION);
if (!ok) throw new Error('expected 0.50.0 / 0.48.0 UI version');
if (!TITAN_UI_VERSION_LABEL.includes(TITAN_PRODUCT_VERSION)) {
  throw new Error('brand label must include product version');
}
console.log(JSON.stringify({ ok: true, version: TITAN_UI_VERSION }));
"""
    )
    payload = json.loads(out.splitlines()[-1])
    assert payload["ok"] is True
    assert payload["version"] in {"0.51.0","0.50.0", "0.48.0"}


def test_phase9_settings_version_bump() -> None:
    settings = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    assert 'VERSION = "0.43.0"' in settings


def test_phase9_index_meta_version() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert 'content="0.51.0"' in html or 'content="0.50.0"' in html or 'content="0.48.0"' in html
    assert "Cognitive Operating System" in html
