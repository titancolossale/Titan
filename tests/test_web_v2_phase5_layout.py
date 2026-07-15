# =====================================
# Titan Web V2 — Phase 5 Reference Layout Reconstruction Tests
# =====================================

"""Frontend contracts for Phase 5 complete visual layout reconstruction.

Validates composition frame, geometry tokens, region reconnection,
stylesheet authority, and version — without Brain/API changes.
"""

from __future__ import annotations

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


def test_phase5_layout_stylesheet_loaded_last() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert "./design/phase5-layout.css" in html
    assert (V2 / "design" / "phase5-layout.css").exists()
    assert html.index("./design/orchestrator.css") < html.index("./design/phase5-layout.css")
    assert html.index("./design/sidebar.css") < html.index("./design/phase5-layout.css")
    assert html.index("./design/reference-final.css") < html.index("./design/phase5-layout.css")
    # Phase 5.1 immersive stage may refine further after Phase 5 layout
    if "./design/immersive-neural-stage.css" in html:
        assert html.index("./design/phase5-layout.css") < html.index(
            "./design/immersive-neural-stage.css"
        )


def test_phase5_layout_css_reference_contracts() -> None:
    css = (V2 / "design" / "phase5-layout.css").read_text(encoding="utf-8")
    for token in (
        "Phase 5",
        "REFERENCE LAYOUT RECONSTRUCTION",
        "sprint-2.7-reference-composition.png",
        "--tdl-sidebar-width: 218px",
        "--tdl-orchestrator-width: 318px",
        "tdl-v2-composition",
        "tdl-v2-dock--floating",
        "tdl-p5-glass",
        "tdl-p5-float-lift",
        "prefers-reduced-motion",
    ):
        assert token in css


def test_phase5_shell_composition_hierarchy() -> None:
    shell = (V2 / "layout" / "shell.js").read_text(encoding="utf-8")
    assert "tdl-v2-composition" in shell
    assert (
        'dataset.phase = "8"' in shell
        or 'dataset.phase = "7"' in shell
        or 'dataset.phase = "5.4"' in shell
        or 'dataset.phase = "5.3"' in shell
        or 'dataset.phase = "5.2"' in shell
        or 'dataset.phase = "5.1"' in shell
        or 'dataset.phase = "5"' in shell
    )
    assert (
        "reference-scene" in shell
        or "cinematic-living" in shell
        or "immersive-neural" in shell
        or 'dataset.layout = "reference"' in shell
    )
    assert "_createCompositionFrame" in shell
    assert "tdl-v2-dock--floating" in shell
    assert "command-columns" in shell
    assert "neural-workspace" in shell
    assert "floating-workspaces" in shell
    # Region IDs preserved for reconnection
    assert "REGION_IDS.sidebar" in shell
    assert "REGION_IDS.orchestrator" in shell
    assert "REGION_IDS.dock" in shell
    assert "REGION_IDS.topbar" in shell
    assert "REGION_IDS.center" in shell


def test_phase5_regions_reconnect_existing_features() -> None:
    sidebar = (V2 / "sidebar" / "sidebar-region.js").read_text(encoding="utf-8")
    orch = (V2 / "orchestrator" / "orchestrator-region.js").read_text(encoding="utf-8")
    topbar = (V2 / "center" / "topbar-region.js").read_text(encoding="utf-8")
    status = (V2 / "status" / "status-region.js").read_text(encoding="utf-8")
    composer = (V2 / "composer" / "composer-region.js").read_text(encoding="utf-8")

    assert (
        'dataset.phase = "5"' in sidebar
        or 'dataset.phase = "10"' in sidebar
    )
    assert "TITAN ONLINE" in sidebar
    assert "Je suis prêt. À tes côtés." in sidebar

    assert (
        'dataset.phase = "10"' in orch
        or 'dataset.phase = "9"' in orch
        or 'dataset.phase = "8"' in orch
        or 'dataset.phase = "6"' in orch
        or 'dataset.phase = "5"' in orch
    )
    assert "Cognitive Orchestrator" in orch or "Titan Core" in orch or "Objectif Actuel" in orch
    assert "tdl-v2-orchestrator--phase5" in orch or "tdl-v2-orchestrator--phase6" in orch
    assert "Current Objective" in orch or "Objectif Actuel" in orch
    assert "Execution Pipeline" in orch or "Pipeline d'Exécution" in orch
    assert "Active Tools" in orch or "Systèmes Connectés" in orch
    assert "Neural Activity" in orch or "Activité Neurale" in orch

    assert "tdl-v2-topbar--phase5" in topbar
    assert "tdl-v2-topbar-brain-mode" in topbar
    assert "Message à Titan" in composer or "Message à Titan…" in composer

    assert "tdl-v2-dock-status-cards--phase5" in status
    assert "Recent Memory" in status or "Mémoire Récente" in status
    assert "Obsidian" in status
    assert "Browser" in status
    assert "Cognitive State" in status or "État Cognitif" in status
    assert "Presence" in status or "Présence" in status


def test_phase5_index_meta_and_title() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert (
        'content="0.51.0"' in html or 'content="0.50.0"' in html or 'content="0.48.0"' in html
        or 'content="0.47.0"' in html
        or 'content="0.46.0"' in html
        or 'content="0.45.0"' in html
        or 'content="0.44.0"' in html
        or 'content="0.43.0"' in html
        or 'content="0.42.0"' in html
        or 'content="0.41.0"' in html
    )
    assert "phase5-layout.css" in html


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_phase5_ui_version() -> None:
    out = _run_node(
        """
import { TITAN_UI_VERSION, TITAN_UI_VERSION_LABEL } from './web/v2/core/version.js';
const ok = ['0.51.0','0.50.0', '0.48.0', '0.47.0', '0.46.0', '0.45.0', '0.44.0', '0.43.0', '0.42.0', '0.41.0'].includes(TITAN_UI_VERSION);
if (!ok) throw new Error('expected 0.47.0+ UI version');
if (!TITAN_UI_VERSION_LABEL.includes(TITAN_UI_VERSION)) throw new Error('bad label');
console.log(JSON.stringify({ ok: true, version: TITAN_UI_VERSION }));
"""
    )
    assert (
        "0.51.0" in out or "0.50.0" in out or "0.48.0" in out
        or "0.47.0" in out
        or "0.46.0" in out
        or "0.45.0" in out
        or "0.44.0" in out
        or "0.43.0" in out
        or "0.42.0" in out
        or "0.41.0" in out
    )