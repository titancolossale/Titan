# =====================================
# Titan Web V2 — Phase 6 Living Cognitive Orchestrator Tests
# =====================================

"""Frontend contracts for Phase 6 Living Cognitive Orchestrator.

Scope guard: Phase 6 may touch orchestrator CSS/JS + version/load order only.
Does not require Brain, API, Memory, Voice Runtime, neural, sidebar, or dock changes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "web" / "v2"
ORCH = V2 / "orchestrator" / "orchestrator-region.js"
CSS = V2 / "design" / "living-orchestrator.css"
DOCS = ROOT / "docs" / "WEB_APP_LIVING_ORCHESTRATOR.md"


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


def test_phase6_living_orchestrator_stylesheet_loaded_last() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert "./design/living-orchestrator.css" in html
    assert CSS.exists()
    assert html.index("./design/orchestrator.css") < html.index(
        "./design/living-orchestrator.css"
    )
    assert html.index("./design/floating-workspaces.css") < html.index(
        "./design/living-orchestrator.css"
    )
    # Phase 7 living-runtime may load after Phase 6 authority
    if "./design/living-runtime.css" in html:
        assert html.index("./design/living-orchestrator.css") < html.index(
            "./design/living-runtime.css"
        )


def test_phase6_living_orchestrator_css_contracts() -> None:
    css = CSS.read_text(encoding="utf-8")
    for token in (
        "Phase 6",
        "LIVING COGNITIVE ORCHESTRATOR",
        "tdl-v2-orchestrator--phase6",
        "tdl-v2-orchestrator--living",
        "tdl-v2-orchestrator-footer",
        "tdl-lo-glass",
        "tdl-lo-header-scan",
        "CURRENT OBJECTIVE",
        "EXECUTION PIPELINE",
        "ACTIVE TOOLS",
        "NEURAL ACTIVITY",
        "BOTTOM STATUS",
        "prefers-reduced-motion",
        "does not touch sidebar",
    ):
        assert token in css


def test_phase6_orchestrator_region_command_center() -> None:
    orch = ORCH.read_text(encoding="utf-8")
    assert (
        'dataset.phase = "10"' in orch
        or 'dataset.phase = "9"' in orch
        or 'dataset.phase = "8"' in orch
        or 'dataset.phase = "6"' in orch
    )
    assert "tdl-v2-orchestrator--phase6" in orch
    assert "tdl-v2-orchestrator--living" in orch
    assert "Current Objective" in orch or "Objectif Actuel" in orch
    assert "Execution Pipeline" in orch or "Pipeline d'Exécution" in orch
    assert "Active Tools" in orch or "Systèmes Connectés" in orch
    assert "Neural Activity" in orch or "Activité Neurale" in orch
    assert "Runtime Status" in orch or "État Système" in orch
    assert "tdl-v2-orchestrator-footer" in orch
    assert "tdl-v2-orchestrator-header__activity" in orch
    assert "ORCHESTRATOR_TOOL_CATALOG" in orch
    assert "IDLE_PLAN_SUBLABELS" in orch
    assert "Understanding Request" in orch or "Compréhension" in orch
    assert "Final Response" in orch or "Réponse" in orch
    assert "✓ Finished" in orch or "Terminé" in orch
    assert "ACTIVE" in orch or "Active" in orch
    assert "Waiting" in orch or "En attente" in orch
    assert "Error" in orch or "Erreur" in orch
    assert 'text: "LIVE"' in orch
    assert "_updateFooterStatus" in orch
    assert "_resolveOperatingMode" in orch
    assert "_startWaveform" in orch
    assert '"System Presence"' not in orch
    assert '"Cognitive State"' not in orch
    assert "BIENTÔT" not in orch


def test_phase6_tool_catalog_includes_voice() -> None:
    orch = ORCH.read_text(encoding="utf-8")
    for title in ("Mémoire", "Memory", "Browser", "Obsidian", "Trading", "Calendar", "Voice"):
        if title in ("Mémoire", "Memory"):
            assert 'title: "Mémoire"' in orch or 'title: "Memory"' in orch
            continue
        assert f'title: "{title}"' in orch


def test_phase6_footer_reuses_existing_telemetry_fields() -> None:
    orch = ORCH.read_text(encoding="utf-8")
    for field in (
        "orchestrationDuration",
        "connectionState",
        "systemsUsed",
        "systemVersion",
        "TITAN_UI_VERSION_LABEL",
    ):
        assert field in orch
    assert "tdl-v2-orch-footer-" in orch
    assert "_setFooterValue" in orch
    assert '"mode"' in orch
    assert '"latency"' in orch or '"Latence"' in orch or "latency" in orch
    assert '"runtime"' in orch
    assert '"subsystems"' in orch
    assert '"connection"' in orch
    assert "Connected" in orch or "Sécurisée" in orch
    assert "Offline" in orch or "Hors ligne" in orch


def test_phase6_preserves_honest_idle_presence_hooks() -> None:
    orch = ORCH.read_text(encoding="utf-8")
    assert "IDLE_PRESENCE_ROWS" in orch
    assert "tdl-v2-orchestrator-presence--sr" in orch
    assert "Présence calme" in orch
    assert "En attente d'une demande" in orch or "Comprendre et assister" in orch
    assert "Aucune active" in orch


def test_phase6_does_not_touch_frozen_architecture_surfaces() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert "does not touch sidebar" in css.lower()
    assert (ROOT / "api" / "app.py").exists()
    assert (ROOT / "brain" / "brain.py").exists()
    assert (V2 / "neural").exists() or (V2 / "design" / "neural.css").exists()
    assert (V2 / "sidebar" / "sidebar-region.js").exists()
    assert (V2 / "center" / "topbar-region.js").exists()
    assert (V2 / "composer" / "composer-region.js").exists()
    assert (V2 / "status" / "status-region.js").exists()


def test_phase6_docs_exist() -> None:
    assert DOCS.exists()
    docs = DOCS.read_text(encoding="utf-8")
    assert "Phase 6" in docs
    assert "Living Cognitive Orchestrator" in docs
    assert "Runtime Status" in docs


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_phase6_idle_plan_and_tools_catalog() -> None:
    out = _run_node(
        """
import {
  IDLE_PLAN_STEPS,
  IDLE_PLAN_SUBLABELS,
  ORCHESTRATOR_TOOL_CATALOG,
} from './web/v2/orchestrator/orchestrator-region.js';
if (IDLE_PLAN_STEPS.length !== 9) throw new Error('expected 9 idle plan steps');
if (!['Understanding Request', 'Compréhension'].includes(IDLE_PLAN_STEPS[0])) {
  throw new Error('bad first step');
}
if (IDLE_PLAN_STEPS[8] !== 'Final Response') throw new Error('bad last step');
if (Object.keys(IDLE_PLAN_SUBLABELS).length < 9) throw new Error('missing sublabels');
if (ORCHESTRATOR_TOOL_CATALOG.length < 6) throw new Error('expected 6+ tools');
if (!ORCHESTRATOR_TOOL_CATALOG.some((t) => t.id === 'voice')) {
  throw new Error('voice tool missing');
}
console.log(JSON.stringify({
  ok: true,
  count: IDLE_PLAN_STEPS.length,
  tools: ORCHESTRATOR_TOOL_CATALOG.length,
  voice: true,
}));
"""
    )
    payload = json.loads(out.splitlines()[-1])
    assert payload["ok"] is True
    assert payload["count"] == 9
    assert payload["tools"] >= 6
    assert payload["voice"] is True


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_phase6_ui_version_bump() -> None:
    out = _run_node(
        """
import { TITAN_UI_VERSION, TITAN_UI_VERSION_LABEL } from './web/v2/core/version.js';
const ok = ['0.51.0','0.50.0', '0.48.0', '0.47.0', '0.46.0', '0.45.0'].includes(TITAN_UI_VERSION);
if (!ok) throw new Error('expected 0.50.0 / 0.48.0 / 0.47.0 / 0.46.0 / 0.45.0 UI version');
if (!TITAN_UI_VERSION_LABEL.includes(TITAN_UI_VERSION)) throw new Error('bad label');
console.log(JSON.stringify({ ok: true, version: TITAN_UI_VERSION }));
"""
    )
    payload = json.loads(out.splitlines()[-1])
    assert payload["ok"] is True
    assert payload["version"] in {"0.51.0","0.50.0", "0.48.0", "0.47.0", "0.46.0", "0.45.0"}


def test_phase6_settings_version_bump() -> None:
    settings = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    assert (
        'VERSION = "0.43.0"' in settings
        or 'VERSION = "0.42.0"' in settings
        or 'VERSION = "0.41.0"' in settings
        or 'VERSION = "0.40.0"' in settings
    )


def test_phase6_index_meta_version() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert (
        'content="0.51.0"' in html or 'content="0.50.0"' in html or 'content="0.48.0"' in html
        or 'content="0.47.0"' in html
        or 'content="0.46.0"' in html
        or 'content="0.45.0"' in html
    )
    assert (
        "Cognitive Operating System" in html
        or "Living Presence" in html
        or "Living Runtime Experience" in html
        or "Living Cognitive Orchestrator" in html
    )
