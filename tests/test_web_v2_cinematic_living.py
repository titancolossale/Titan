# =====================================
# Titan Web V2 — Phase 5.2 Cinematic Living Intelligence Tests
# =====================================

"""Frontend contracts for Phase 5.2 cinematic living intelligence.

Validates galactic neural composition, cinematic atmosphere CSS,
ghost satellites, orchestrator idle life, stylesheet authority, and version —
without Brain/API changes.
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


def test_cinematic_stylesheet_loaded_last() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert "./design/cinematic-living.css" in html
    assert (V2 / "design" / "cinematic-living.css").exists()
    assert html.index("./design/immersive-neural-stage.css") < html.index(
        "./design/cinematic-living.css"
    )
    assert html.index("./design/phase5-layout.css") < html.index(
        "./design/cinematic-living.css"
    )


def test_cinematic_css_contracts() -> None:
    css = (V2 / "design" / "cinematic-living.css").read_text(encoding="utf-8")
    for token in (
        "Phase 5.2",
        "CINEMATIC LIVING INTELLIGENCE",
        "tdl-c52-atmosphere-breathe",
        "tdl-v2-orchestrator-idle-life",
        "tdl-c52-scan",
        "tdl-c52-bar-breathe",
        "tdl-c52-idle-pulse",
        "prefers-reduced-motion",
        "opacity: 0.28",
    ):
        assert token in css


def test_neural_tissue_galactic_composition() -> None:
    tissue = (V2 / "neural" / "tissue.js").read_text(encoding="utf-8")
    for token in (
        "_seedMajorColonies",
        "_seedArchitectureVoids",
        "_majorPathway",
        "_secondaryBranch",
        "_voidFringeWisp",
        "galaxySynapseCount",
        "majorPathwayCount",
    ):
        assert token in tissue


def test_neural_config_cinematic_atmosphere() -> None:
    cfg = (V2 / "neural" / "config.js").read_text(encoding="utf-8")
    for token in (
        "galaxyCount",
        "voidCount",
        "lightShaftStrength",
        "lensDiffusion",
        "fogRedStrength",
        "bloomStrength",
        "Architecture Reconstruction",
        "tertiaryBranchCount",
        "foregroundBokehCount",
    ):
        assert token in cfg


def test_neural_renderer_cinematic_passes() -> None:
    renderer = (V2 / "neural" / "renderer.js").read_text(encoding="utf-8")
    for token in (
        "_drawAtmosphericFog",
        "_drawLightShafts",
        "_drawLensDiffusion",
    ):
        assert token in renderer


def test_neural_nodes_void_rejection() -> None:
    nodes = (V2 / "neural" / "nodes.js").read_text(encoding="utf-8")
    assert "_clampAwayFromVoids" in nodes
    assert "_seedVoids" in nodes
    assert "_voidZones" in nodes
    assert "sparseFieldChance" in nodes


def test_orchestrator_idle_life_markup() -> None:
    orch = (V2 / "orchestrator" / "orchestrator-region.js").read_text(encoding="utf-8")
    assert "_idleLifeBlock" in orch
    assert "tdl-v2-orchestrator-idle-life" in orch
    assert "idle-life" in orch


def test_cinematic_shell_phase_marker() -> None:
    """Later phases supersede shell markers; cinematic CSS remains in the cascade."""
    shell = (V2 / "layout" / "shell.js").read_text(encoding="utf-8")
    assert "Phase 5.2" in shell
    assert "Cinematic Living Intelligence" in shell
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
        or 'dataset.layout = "reference"' in shell
    )


def test_cinematic_index_meta() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert "cinematic-living.css" in html
    assert "./design/cinematic-living.css" in html
    # Reference scene (and later workspace sheet) still load after cinematic.
    assert html.index("./design/cinematic-living.css") < html.index(
        "./design/reference-scene.css"
    )


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_tissue_builds_without_error() -> None:
    out = _run_node(
        """
import { buildFieldTissue, buildCoreTissue } from './web/v2/neural/tissue.js';
const core = buildCoreTissue(500, 400, 120);
const field = buildFieldTissue(1000, 800, 500, 400, 120);
if (!Array.isArray(core) || core.length < 50) throw new Error('core tissue too small');
if (!Array.isArray(field) || field.length < 100) throw new Error('field tissue too small');
const kinds = new Set(field.map((s) => s.kind));
for (const need of ['pathway', 'secondary', 'tertiary', 'wisp', 'bridge']) {
  if (!kinds.has(need)) throw new Error('missing kind ' + need);
}
console.log(JSON.stringify({ ok: true, core: core.length, field: field.length }));
"""
    )
    assert '"ok":true' in out.replace(" ", "")
