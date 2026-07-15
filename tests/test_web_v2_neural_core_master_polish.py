# =====================================
# Titan Web V2 — Neural Core Master Polish Tests
# =====================================

"""Contracts for Neural Core Master Polish — living artificial intelligence field.

Frontend-only. Validates denser tissue, organic colonies, depth/gravity,
curved highways, Core bloom, and atmosphere without Brain/API changes.
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


def test_master_polish_config_density() -> None:
    """Superseded counts live in architecture config — keep Core polish invariants."""
    cfg = (V2 / "neural" / "config.js").read_text(encoding="utf-8")
    for token in (
        "coreStrandCount: 1280",
        "microNeuronCount: 3200",
        "energyRingCount: 0",
        "labelZoneStrandCount: 320",
        "nearForegroundCount: 64",
        "energyPacketCount: 28",
        "architecture:",
    ):
        assert token in cfg


def test_master_polish_tissue_highways_and_colonies() -> None:
    tissue = (V2 / "neural" / "tissue.js").read_text(encoding="utf-8")
    for token in (
        "_seedMajorColonies",
        "_majorPathway",
        "_secondaryBranch",
        "_tertiaryTwig",
        "_microColonyBridge",
        "_seedLabelZonePockets",
        "_tagCoreDepth",
        "_colonySynapse",
    ):
        assert token in tissue


def test_master_polish_renderer_atmosphere() -> None:
    renderer = (V2 / "neural" / "renderer.js").read_text(encoding="utf-8")
    for token in (
        "_drawForegroundBokeh",
        "_drawRestrainedBloom",
        "_drawAtmosphericFog",
        "_drawCoreAura",
        "_drawCoreFrontTissue",
        "_drawCoreEnergyPackets",
        "pathway",
        "tertiary",
    ):
        assert token in renderer
    # No hard orb / star topology regress.
    assert "energyRingCount" not in renderer
    assert "star topology" not in renderer.lower()


def test_master_polish_core_micro_gravity() -> None:
    core = (V2 / "neural" / "core.js").read_text(encoding="utf-8")
    assert "Core gravity" in core or "Stronger Core attraction" in core
    assert "microNeuronCount" in core
    assert "buildCoreTissue" in core
    assert "radial: true" not in core


def test_master_polish_nodes_organic_colonies() -> None:
    nodes = (V2 / "neural" / "nodes.js").read_text(encoding="utf-8")
    assert "colony" in nodes.lower() or "stretchX" in nodes
    assert "coreClusterChance" in nodes
    assert "_clampAwayFromVoids" in nodes


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_master_polish_tissue_builds_dense() -> None:
    out = _run_node(
        """
import { buildFieldTissue, buildCoreTissue } from './web/v2/neural/tissue.js';
const core = buildCoreTissue(500, 400, 140);
const field = buildFieldTissue(1000, 800, 500, 400, 140);
if (!Array.isArray(core) || core.length < 200) throw new Error('core tissue too small: ' + core.length);
if (!Array.isArray(field) || field.length < 400) throw new Error('field tissue too small: ' + field.length);
const kinds = new Set(field.map((s) => s.kind));
for (const need of ['pathway', 'secondary', 'tertiary', 'wisp', 'bridge', 'dust']) {
  if (!kinds.has(need)) throw new Error('missing kind ' + need);
}
const pathways = field.filter((s) => s.kind === 'pathway');
const multi = pathways.filter((s) => s.pts && s.pts.length >= 4).length;
if (multi < pathways.length * 0.35) throw new Error('highways not multi-segment');
console.log(JSON.stringify({ ok: true, core: core.length, field: field.length, pathways: pathways.length }));
"""
    )
    assert '"ok":true' in out.replace(" ", "")
