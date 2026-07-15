# =====================================
# Titan Web V2 — Neural Architecture Reconstruction Tests
# =====================================

"""Contracts for Neural Architecture Reconstruction — living neural civilization.

Frontend-only. Validates named major colonies, organic highways (split/merge),
intentional voids, large-scale depth bands, and Core preservation.
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


def test_architecture_config_colonies() -> None:
    cfg = (V2 / "neural" / "config.js").read_text(encoding="utf-8")
    for token in (
        "Neural Architecture Reconstruction",
        "architecture:",
        'id: "core"',
        'id: "memory"',
        'id: "planning"',
        'id: "browser"',
        'id: "communication"',
        'id: "obsidian"',
        "colonyLocalCount: 760",
        "highwaySplitCount: 28",
        "highwayMergeCount: 18",
        "foregroundStrandCount: 48",
        "voidCount: 9",
        "sparseFieldChance: 0.03",
        "highwaySheath: 0.2",
    ):
        assert token in cfg


def test_architecture_tissue_symbols() -> None:
    tissue = (V2 / "neural" / "tissue.js").read_text(encoding="utf-8")
    for token in (
        "Neural Architecture Reconstruction",
        "_seedMajorColonies",
        "_seedArchitectureVoids",
        "_buildHighwayNetwork",
        "_highwaySplit",
        "_highwayMerge",
        "_colonyLocalBranch",
        "PASS A: large-scale architecture",
        "PASS C: micro detail",
        "Living neural civilization",
    ):
        assert token in tissue


def test_architecture_renderer_depth_and_highways() -> None:
    renderer = (V2 / "neural" / "renderer.js").read_text(encoding="utf-8")
    for token in (
        "Architecture Reconstruction",
        '"foreground"',
        "highwayFirst",
        "highwaySheath",
        "strand.artery",
    ):
        assert token in renderer


def test_architecture_nodes_colony_seeds() -> None:
    nodes = (V2 / "neural" / "nodes.js").read_text(encoding="utf-8")
    assert "architecture?.colonies" in nodes or "architecture.colonies" in nodes
    assert "stretchX" in nodes
    assert "Interstitial voids" in nodes or "breathing spaces" in nodes.lower()


def test_core_preserved() -> None:
    """Titan Core builders remain wired — architecture grows around Core."""
    core = (V2 / "neural" / "core.js").read_text(encoding="utf-8")
    assert "buildCoreTissue" in core
    assert "buildFieldTissue" in core
    assert "microNeuronCount" in core


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_architecture_field_builds_civilization() -> None:
    out = _run_node(
        """
import { buildFieldTissue, buildCoreTissue } from './web/v2/neural/tissue.js';
import { NEURAL_CONFIG } from './web/v2/neural/config.js';

const core = buildCoreTissue(500, 400, 140);
const field = buildFieldTissue(1000, 800, 500, 400, 140);
if (!Array.isArray(core) || core.length < 200) throw new Error('core tissue too small: ' + core.length);
if (!Array.isArray(field) || field.length < 400) throw new Error('field tissue too small: ' + field.length);

const kinds = new Set(field.map((s) => s.kind));
for (const need of ['pathway', 'secondary', 'tertiary', 'wisp', 'bridge', 'dust', 'colony']) {
  if (!kinds.has(need)) throw new Error('missing kind ' + need);
}

const pathways = field.filter((s) => s.kind === 'pathway');
const multi = pathways.filter((s) => s.pts && s.pts.length >= 4).length;
if (multi < pathways.length * 0.35) throw new Error('highways not multi-segment enough');

const splits = pathways.filter((s) => s.split).length;
const merges = pathways.filter((s) => s.merge).length;
const arteries = pathways.filter((s) => s.artery).length;
if (arteries < 4) throw new Error('too few core arteries: ' + arteries);
if (splits < 4) throw new Error('too few highway splits: ' + splits);
if (merges < 2) throw new Error('too few highway merges: ' + merges);

const bands = new Set(field.map((s) => s.band));
for (const need of ['veryFar', 'far', 'mid', 'near', 'foreground', 'bridge']) {
  if (!bands.has(need)) throw new Error('missing band ' + need);
}

const colonyIds = new Set(
  field.filter((s) => s.colonyId).map((s) => s.colonyId)
);
for (const need of ['memory', 'planning', 'browser', 'communication', 'obsidian']) {
  if (!colonyIds.has(need)) throw new Error('missing colony local tissue: ' + need);
}

const archIds = (NEURAL_CONFIG.architecture?.colonies || []).map((c) => c.id);
if (!archIds.includes('core')) throw new Error('architecture missing core colony');

console.log(JSON.stringify({
  ok: true,
  core: core.length,
  field: field.length,
  pathways: pathways.length,
  arteries,
  splits,
  merges,
  colonyIds: [...colonyIds].length,
}));
"""
    )
    assert '"ok":true' in out.replace(" ", "")
