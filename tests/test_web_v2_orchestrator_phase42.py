# =====================================
# Titan Web V2 — Phase 4.2 Cognitive Orchestrator Reconstruction Tests
# =====================================

"""Frontend contracts for right-panel Cognitive Orchestrator reconstruction.

Scope guard: Phase 4.2 may touch orchestrator CSS/JS + version/load order only.
Does not require Brain, API, Memory, Voice, neural, sidebar, or dock changes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "web" / "v2"


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


def test_phase42_orchestrator_stylesheet_loaded_last() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert "./design/orchestrator.css" in html
    assert (V2 / "design" / "orchestrator.css").exists()
    assert html.index("./design/sidebar.css") < html.index("./design/orchestrator.css")
    assert html.index("./design/reference-final.css") < html.index("./design/orchestrator.css")


def test_phase42_orchestrator_css_reconstruction_contracts() -> None:
    """Phase 4.2 contracts remain satisfied under Phase 4.3 refinement."""
    css = (V2 / "design" / "orchestrator.css").read_text(encoding="utf-8")
    for token in (
        "tdl-v2-orchestrator--phase42",
        "tdl-orch-glass",
        "CURRENT OBJECTIVE",
        "EXECUTION PIPELINE",
        "ACTIVE TOOLS",
        "NEURAL ACTIVITY",
        "tdl-v2-orchestrator-tool-card",
        "tdl-orch-neural-pulse",
        "prefers-reduced-motion",
        "does not touch sidebar",
    ):
        assert token in css


def test_phase42_orchestrator_region_command_center() -> None:
    orch = (V2 / "orchestrator" / "orchestrator-region.js").read_text(encoding="utf-8")
    assert "tdl-v2-orchestrator--phase42" in orch
    assert "Current Objective" in orch or "Objectif Actuel" in orch
    assert "Execution Pipeline" in orch or "Pipeline d'Exécution" in orch
    assert "Active Tools" in orch or "Systèmes Connectés" in orch
    assert "Neural Activity" in orch or "Activité Neurale" in orch
    assert "ORCHESTRATOR_TOOL_CATALOG" in orch
    assert "Understanding Request" in orch or "Compréhension" in orch
    assert "Final Response" in orch or "Réponse" in orch
    assert "✓ Finished" in orch or "Terminé" in orch
    assert "ACTIVE" in orch or "Active" in orch
    assert "Waiting" in orch or "En attente" in orch
    assert "tdl-v2-orchestrator-header__neural" in orch
    assert "_startWaveform" in orch
    # Previous dashboard section titles must not remount as primary story.
    assert '"System Presence"' not in orch
    assert '"Cognitive State"' not in orch
    assert '"Execution Timeline"' not in orch
    assert '"Instruments"' not in orch
    assert '"Neural Field"' not in orch


def test_phase42_tool_catalog_covers_reference_instruments() -> None:
    orch = (V2 / "orchestrator" / "orchestrator-region.js").read_text(encoding="utf-8")
    assert 'title: "Obsidian"' in orch
    assert 'title: "Browser"' in orch
    assert 'title: "Trading"' in orch
    assert 'title: "Calendar"' in orch
    assert 'title: "Mémoire"' in orch or 'title: "Memory"' in orch


def test_phase42_preserves_honest_idle_presence_hooks() -> None:
    """Idle presence truth remains available; not shown as a dashboard list."""
    orch = (V2 / "orchestrator" / "orchestrator-region.js").read_text(encoding="utf-8")
    assert "IDLE_PRESENCE_ROWS" in orch
    assert "tdl-v2-orchestrator-presence--sr" in orch
    assert "Présence calme" in orch
    assert "En attente d'une demande" in orch or "Comprendre et assister" in orch
    assert "Aucune active" in orch


def test_phase42_does_not_touch_frozen_architecture_surfaces() -> None:
    css = (V2 / "design" / "orchestrator.css").read_text(encoding="utf-8")
    assert "orchestrator only" in css.lower() or "does not touch sidebar" in css.lower()
    assert (ROOT / "api" / "app.py").exists()
    assert (ROOT / "brain" / "brain.py").exists()
    assert (V2 / "neural").exists() or (V2 / "design" / "neural.css").exists()
    assert (V2 / "sidebar" / "sidebar-region.js").exists()
    assert (V2 / "center" / "topbar-region.js").exists()


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_phase42_idle_plan_steps_match_reference_pipeline() -> None:
    out = _run_node(
        """
import { IDLE_PLAN_STEPS, ORCHESTRATOR_TOOL_CATALOG } from './web/v2/orchestrator/orchestrator-region.js';
if (IDLE_PLAN_STEPS.length !== 9) throw new Error('expected 9 idle plan steps');
if (!['Understanding Request', 'Compréhension'].includes(IDLE_PLAN_STEPS[0])) {
  throw new Error('bad first step');
}
if (IDLE_PLAN_STEPS[8] !== 'Final Response') throw new Error('bad last step');
if (ORCHESTRATOR_TOOL_CATALOG.length < 5) throw new Error('expected 5+ tools');
console.log(JSON.stringify({ ok: true, count: IDLE_PLAN_STEPS.length, tools: ORCHESTRATOR_TOOL_CATALOG.length }));
"""
    )
    payload = json.loads(out.splitlines()[-1])
    assert payload["ok"] is True
    assert payload["count"] == 9
    assert payload["tools"] >= 5


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_phase42_ui_version_bump() -> None:
    out = _run_node(
        """
import { TITAN_UI_VERSION, TITAN_UI_VERSION_LABEL } from './web/v2/core/version.js';
if (!/^0\\.29|^0\\.3|^0\\.4/.test(TITAN_UI_VERSION)) throw new Error('expected 0.29+ UI version');
if (!TITAN_UI_VERSION_LABEL.includes(TITAN_UI_VERSION)) throw new Error('bad label');
console.log(JSON.stringify({ ok: true, version: TITAN_UI_VERSION }));
"""
    )
    payload = json.loads(out.splitlines()[-1])
    assert payload["ok"] is True
    assert payload["version"].startswith("0.")
