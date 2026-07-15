# =====================================
# Titan Web V2 — Phase 5.1 Immersive Neural Stage Tests
# =====================================

"""Frontend contracts for Phase 5.1 immersive neural stage presentation.

Validates atmosphere layer, buried Titan Core, distant satellites,
stylesheet authority, and version — without Brain/API/renderer changes.
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


def test_immersive_stylesheet_loaded_last() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert "./design/immersive-neural-stage.css" in html
    assert (V2 / "design" / "immersive-neural-stage.css").exists()
    assert html.index("./design/phase5-layout.css") < html.index(
        "./design/immersive-neural-stage.css"
    )
    assert html.index("./design/neural.css") < html.index(
        "./design/immersive-neural-stage.css"
    )
    assert html.index("./design/satellites.css") < html.index(
        "./design/immersive-neural-stage.css"
    )


def test_immersive_css_atmosphere_contracts() -> None:
    css = (V2 / "design" / "immersive-neural-stage.css").read_text(encoding="utf-8")
    for token in (
        "Phase 5.1",
        "IMMERSIVE NEURAL STAGE",
        "living-neural-core-closeup.png",
        "tdl-v2-neural-depth-band",
        "tdl-v2-neural-vignette",
        "tdl-v2-satellite-core__tissue",
        "tdl-v2-satellite-core__filament",
        "tdl-v2-satellite-core__veil",
        "tdl-imm-fog",
        "prefers-reduced-motion",
        "background: transparent !important",
    ):
        assert token in css


def test_immersive_core_has_no_glass_pill() -> None:
    css = (V2 / "design" / "immersive-neural-stage.css").read_text(encoding="utf-8")
    # Core must not reintroduce a rectangular / pill plate
    core_block_start = css.index(".tdl-v2-satellite-core {")
    core_block = css[core_block_start : core_block_start + 500]
    assert "border-radius: 0" in core_block or "border-radius: 0 !" in core_block
    assert "background: transparent" in core_block
    assert "999px" not in core_block


def test_immersive_satellites_buried_core_markup() -> None:
    satellites = (V2 / "center" / "cognitive-satellites.js").read_text(encoding="utf-8")
    assert "tdl-v2-satellite-core__tissue" in satellites
    assert "tdl-v2-satellite-core__filament" in satellites
    assert "tdl-v2-satellite-core__veil" in satellites
    assert "TITAN CORE" in satellites


def test_immersive_shell_phase_marker() -> None:
    shell = (V2 / "layout" / "shell.js").read_text(encoding="utf-8")
    # Later phases supersede 5.1 while preserving depth atmosphere markup.
    assert (
        'dataset.phase = "10"' in shell
        or 'dataset.phase = "8"' in shell
        or 'dataset.phase = "7"' in shell
        or 'dataset.phase = "5.4"' in shell
        or 'dataset.phase = "5.3"' in shell
        or 'dataset.phase = "5.2"' in shell
        or 'dataset.phase = "5.1"' in shell
    )
    assert (
        'dataset.layout = "canonical-final"' in shell
        or 'dataset.layout = "reference-scene"' in shell
        or 'dataset.layout = "cinematic-living"' in shell
        or 'dataset.layout = "immersive-neural"' in shell
    )
    assert "tdl-v2-neural-depth-band" in shell
    assert '"void", "far", "distant", "horizon"' in shell


def test_immersive_index_meta_and_title() -> None:
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
    assert "immersive-neural-stage.css" in html
    assert (
        "Cognitive Operating System" in html
        or "Canonical" in html
        or "Living Presence" in html
        or "Living Runtime Experience" in html
        or "Living Cognitive Orchestrator" in html
        or "Floating Workspaces" in html
        or "Reference Scene" in html
        or "Immersive Neural Stage" in html
        or "Cinematic Living Intelligence" in html
    )


def test_phase5_layout_still_before_immersive() -> None:
    """Phase 5 geometry remains; 5.1 only wins on atmosphere presentation."""
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert "./design/phase5-layout.css" in html
    assert html.index("./design/orchestrator.css") < html.index("./design/phase5-layout.css")


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_immersive_ui_version() -> None:
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