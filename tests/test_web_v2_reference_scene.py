# =====================================
# Titan Web V2 — Phase 5.3 Reference Scene Reconstruction Tests
# =====================================

"""Frontend contracts for Phase 5.3 reference scene reconstruction.

Validates Core gravity hierarchy, organic satellite orbits, major neural
highways, atmosphere authority CSS, stylesheet load order, and UI version —
without Brain/API/neural engine changes.
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


def test_reference_scene_stylesheet_loaded_last() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert "./design/reference-scene.css" in html
    assert (V2 / "design" / "reference-scene.css").exists()
    assert html.index("./design/cinematic-living.css") < html.index(
        "./design/reference-scene.css"
    )
    assert html.index("./design/immersive-neural-stage.css") < html.index(
        "./design/reference-scene.css"
    )


def test_reference_scene_css_contracts() -> None:
    css = (V2 / "design" / "reference-scene.css").read_text(encoding="utf-8")
    for token in (
        "Phase 5.3",
        "REFERENCE SCENE RECONSTRUCTION",
        "tdl-c53-atmosphere-breathe",
        "tdl-c53-core-breathe",
        "tdl-c53-gravity-pulse",
        "tdl-c53-highway-flow",
        "tdl-v2-satellite-core__gravity",
        "tdl-v2-satellite-link--secondary",
        "tdl-v2-satellite-link--synapse",
        "tdl-v2-satellite--memory",
        "tdl-v2-satellite--planning",
        "tdl-v2-satellite--obsidian",
        "prefers-reduced-motion",
        "left: 21%",
        "left: 90%",
    ):
        assert token in css


def test_satellite_field_highways() -> None:
    satellites = (V2 / "center" / "cognitive-satellites.js").read_text(encoding="utf-8")
    for token in (
        "Phase 5.3",
        "tdl-v2-satellite-core__gravity",
        "_secondaryLinks",
        "_synapseLinks",
        "tdl-v2-satellite-link--secondary",
        "tdl-v2-satellite-link--synapse",
        "_curvePath",
    ):
        assert token in satellites


def test_reference_scene_shell_phase_marker() -> None:
    shell = (V2 / "layout" / "shell.js").read_text(encoding="utf-8")
    assert (
        'dataset.phase = "10"' in shell
        or 'dataset.phase = "8"' in shell
        or 'dataset.phase = "7"' in shell
        or 'dataset.phase = "5.4"' in shell
        or 'dataset.phase = "5.3"' in shell
    )
    assert (
        'dataset.layout = "canonical-final"' in shell
        or 'dataset.layout = "reference-scene"' in shell
    )
    assert "Phase 5.3" in shell


def test_reference_scene_index_meta() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert (
        'content="0.51.0"' in html or 'content="0.50.0"' in html or 'content="0.48.0"' in html
        or 'content="0.47.0"' in html
        or 'content="0.46.0"' in html
        or 'content="0.45.0"' in html
        or 'content="0.44.0"' in html
        or 'content="0.43.0"' in html
    )
    assert (
        "Cognitive Operating System" in html
        or "Living Presence" in html
        or "Living Runtime Experience" in html
        or "Living Cognitive Orchestrator" in html
        or "Floating Workspaces" in html
        or "Reference Scene" in html
    )
    assert "reference-scene.css" in html


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_reference_scene_ui_version() -> None:
    out = _run_node(
        """
import { TITAN_UI_VERSION, TITAN_UI_VERSION_LABEL } from './web/v2/core/version.js';
const ok = ['0.51.0','0.50.0', '0.48.0', '0.47.0', '0.46.0', '0.45.0', '0.44.0', '0.43.0'].includes(TITAN_UI_VERSION);
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
    )


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_satellite_definitions_intact() -> None:
    out = _run_node(
        """
import { SATELLITE_DEFINITIONS, TITAN_CORE_LABEL } from './web/v2/center/cognitive-satellites.js';
const ids = SATELLITE_DEFINITIONS.map((s) => s.id);
const need = ['memory','planning','browser','obsidian','tools','communication','trading','calendar'];
for (const id of need) {
  if (!ids.includes(id)) throw new Error('missing satellite ' + id);
}
if (TITAN_CORE_LABEL.title !== 'TITAN CORE') throw new Error('bad core title');
console.log(JSON.stringify({ ok: true, count: ids.length }));
"""
    )
    assert '"ok":true' in out.replace(" ", "")
