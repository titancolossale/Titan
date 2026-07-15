# =====================================
# Titan Web V2 — Sprint 2.7 Reference Composition Tests
# =====================================

"""Frontend contracts for Reference Composition Reconstruction.

Validates desktop composition regions, navigation, orchestrator panel,
floating cards, composer wiring, state adapters, and /app load path —
without touching Brain or API backends.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "web" / "v2"
API = ROOT / "api" / "app.py"


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


def test_app_mount_serves_v2_frontend() -> None:
    content = API.read_text(encoding="utf-8")
    assert 'mount("/app"' in content
    assert "V2_DIR" in content or "web/v2" in content or 'name="app"' in content


def test_single_frontend_root_no_duplicate_routers() -> None:
    """Production UI is web/v2 only under /app — one router module."""
    routers = list(V2.rglob("router.js"))
    assert len(routers) == 1
    assert (V2 / "index.html").exists()
    assert (V2 / "main.js").exists()


def test_composition_stylesheet_loaded() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert "./design/composition.css" in html
    assert (V2 / "design" / "composition.css").exists()


def test_full_sidebar_navigation_labels() -> None:
    router = (V2 / "core" / "router.js").read_text(encoding="utf-8")
    sidebar = (V2 / "sidebar" / "sidebar-region.js").read_text(encoding="utf-8")
    for label in (
        "Chat",
        "Projects",
        "Memory",
        "Exploration",
        "Calendar",
        "Trading",
        "Tools",
        "Settings",
    ):
        assert f'label: "{label}"' in router
    assert "TITAN ONLINE" in sidebar
    assert "CERVEAU ACTIF" in sidebar
    assert "Je suis prêt. À tes côtés." in sidebar
    assert "BIENTÔT" in sidebar
    assert "sidebarPinned: true" in (V2 / "core" / "state-store.js").read_text(encoding="utf-8")


def test_permanent_desktop_orchestrator_panel() -> None:
    orch = (V2 / "orchestrator" / "orchestrator-region.js").read_text(encoding="utf-8")
    layout = (V2 / "design" / "layout.css").read_text(encoding="utf-8")
    assert "Cognitive Orchestrator" in orch
    assert "Current Objective" in orch
    assert "Execution Pipeline" in orch
    assert "Active Tools" in orch
    assert "Neural Activity" in orch
    assert "IDLE_PLAN_STEPS" in orch
    assert "Understanding Request" in orch
    assert "Final Response" in orch
    assert "dataset.status" in orch
    assert "var(--tdl-orchestrator-width)" in layout


def test_lower_floating_card_row() -> None:
    status = (V2 / "status" / "status-region.js").read_text(encoding="utf-8")
    css = (V2 / "design" / "composition.css").read_text(encoding="utf-8")
    for title in (
        "Recent Memory",
        "Obsidian",
        "Browser",
        "Cognitive State",
        "Presence",
    ):
        assert title in status
    assert "tdl-v2-dock-status-cards--float" in status
    assert "tdl-v2-float-card" in css
    assert "tdl-v2-float-card__close" in status


def test_chat_composer_ids_preserved() -> None:
    composer = (V2 / "composer" / "composer-region.js").read_text(encoding="utf-8")
    manager = (V2 / "conversation" / "conversation-manager.js").read_text(encoding="utf-8")
    assert 'id: "tdl-v2-chat-input"' in composer or 'id="tdl-v2-chat-input"' in composer
    assert "tdl-v2-send-chat" in composer
    assert "tdl-v2-send-chat" in manager
    assert "tdl-v2-voice-mic" in composer
    assert "tdl-v2-composer-attach" in composer
    assert "SEND" in composer


def test_no_marketing_welcome_headline() -> None:
    layouts = (V2 / "panels" / "layouts" / "index.js").read_text(encoding="utf-8")
    assert "Titan est présent" not in layouts
    assert "Que veux-tu accomplir aujourd'hui" not in layouts


def test_state_adapters_remain_connected() -> None:
    center = (V2 / "center" / "center-region.js").read_text(encoding="utf-8")
    orch = (V2 / "orchestrator" / "orchestrator-region.js").read_text(encoding="utf-8")
    status = (V2 / "status" / "status-region.js").read_text(encoding="utf-8")
    assert "resolveNeuralStatus" in center
    assert "onToolActivity" in orch
    assert "onMemoryActivity" in status
    assert "getPipelineStore" in orch


def test_telemetry_graceful_fallback_markers() -> None:
    status = (V2 / "status" / "status-region.js").read_text(encoding="utf-8")
    css = (V2 / "design" / "composition.css").read_text(encoding="utf-8")
    assert 'data-fallback="true"' in status
    assert "tdl-v2-telemetry-fps" in status
    assert '[data-fallback="true"]' in css


def test_responsive_orchestrator_drawer_behavior() -> None:
    layout = (V2 / "design" / "layout.css").read_text(encoding="utf-8")
    topbar = (V2 / "center" / "topbar-region.js").read_text(encoding="utf-8")
    composition = (V2 / "design" / "composition.css").read_text(encoding="utf-8")
    assert "tdl-v2--mode-tablet" in layout
    assert "orchestratorDrawerOpen" in topbar
    assert "overflow-x: auto" in composition


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_idle_plan_steps_exported() -> None:
    out = _run_node(
        """
import { IDLE_PLAN_STEPS } from './web/v2/orchestrator/orchestrator-region.js';
if (IDLE_PLAN_STEPS.length !== 9) throw new Error('expected 9 idle plan steps');
if (IDLE_PLAN_STEPS[0] !== 'Understanding Request') throw new Error('bad first step');
if (IDLE_PLAN_STEPS[8] !== 'Final Response') throw new Error('bad last step');
console.log(JSON.stringify({ ok: true, count: IDLE_PLAN_STEPS.length }));
"""
    )
    payload = json.loads(out.splitlines()[-1])
    assert payload["ok"] is True
    assert payload["count"] == 9


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_reference_satellites_resolve() -> None:
    out = _run_node(
        """
import { SATELLITE_IDS, resolveNeuralStatus } from './web/v2/center/neural-status-adapter.js';
const expected = ['memory','planning','browser','obsidian','tools','communication','trading','calendar'];
if (SATELLITE_IDS.join(',') !== expected.join(',')) throw new Error('bad satellite ids');
const r = resolveNeuralStatus({ cognitiveState: 'obsidian', activeToolIds: ['obsidian'] });
if (r.satellites.obsidian !== 'active') throw new Error('obsidian should be active');
if (r.satellites.memory !== 'active') throw new Error('memory should warm for obsidian');
console.log(JSON.stringify({ ok: true, behavior: r.behavior }));
"""
    )
    payload = json.loads(out.splitlines()[-1])
    assert payload["ok"] is True
    assert payload["behavior"] == "EXECUTING"
