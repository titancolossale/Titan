# =====================================
# Titan Web V2 — Titan Core Identity Tests
# =====================================

"""Contracts for FINAL ARTISTIC PASS — Titan Core Identity.

Frontend-only. Validates layered nucleus, breathing, local orbit packets,
gravitational energy flow, and Core-scoped lighting without locked chrome changes.
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


def test_core_identity_config() -> None:
    cfg = (V2 / "neural" / "config.js").read_text(encoding="utf-8")
    for token in (
        "fieldDarkenStrength",
        "orbitPacketRatio",
        "whiteCenterRadius: 0.8",
        "energyPacketCount: 28",
        "outerGlowMult: 0.7",
        "highwayCoreGravity",
        "bloomStrength: 0.032",
        "convergeToCoreChance: 0.34",
        # Particle budgets must not inflate.
        "microNeuronCount: 3200",
        "dustCount: 180",
        "foregroundBokehCount: 28",
    ):
        assert token in cfg


def test_core_identity_renderer_layers() -> None:
    renderer = (V2 / "neural" / "renderer.js").read_text(encoding="utf-8")
    for token in (
        "_drawCoreNucleus",
        "_drawCoreFieldDarken",
        "_drawCoreAura",
        "_drawCoreEnergyPackets",
        "White-hot nucleus",
        "plasma shell",
        "highwayCoreGravity",
        "kind === \"orbit\"",
    ):
        assert token in renderer
    # Still no energy-ring regress / star topology.
    assert "energyRingCount" not in renderer
    assert "star topology" not in renderer.lower()
    assert "whiteR * 6.5" not in renderer


def test_core_identity_orbit_packets() -> None:
    core = (V2 / "neural" / "core.js").read_text(encoding="utf-8")
    assert 'kind: "orbit"' in core
    assert 'kind: "filament"' in core
    assert "orbitPacketRatio" in core
    assert "Identity nucleus anchor" in core
    assert "radial: true" not in core


def test_core_identity_highway_gravity() -> None:
    tissue = (V2 / "neural" / "tissue.js").read_text(encoding="utf-8")
    assert "Gravitational funnel" in tissue
    assert "massA" in tissue


def test_core_identity_css_scoped() -> None:
    css = (V2 / "design" / "canonical-final.css").read_text(encoding="utf-8")
    assert "tdl-cf-core-nucleus" in css
    assert "rgba(255, 255, 255, 0.55)" in css
    assert "illuminated by the Core" in css or "illuminated by the nucleus" in css
    # Locked chrome regions still present (not deleted).
    assert "LEFT SIDEBAR" in css
    assert "tdl-v2-region--sidebar" in css


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_core_identity_packets_build() -> None:
    out = _run_node(
        """
import { NeuralCamera } from './web/v2/neural/camera.js';
import { NeuralNodes } from './web/v2/neural/nodes.js';
const camera = new NeuralCamera();
camera.resize(1000, 800);
const nodes = new NeuralNodes(camera);
nodes.build(1000, 800, 0.35);
const core = nodes.core;
if (!core) throw new Error('missing core');
const packets = core.energyPackets || [];
if (packets.length !== 28) throw new Error('packet budget changed: ' + packets.length);
const orbits = packets.filter((p) => p.kind === 'orbit');
const filaments = packets.filter((p) => p.kind === 'filament');
if (orbits.length < 8) throw new Error('too few orbit packets: ' + orbits.length);
if (filaments.length < 8) throw new Error('too few filament packets: ' + filaments.length);
const fakeState = { getIntensity: () => 0.4, isThinking: () => false, getBreathe: () => 0.5 };
core.update(16, fakeState);
const angle0 = orbits[0].angle;
core.update(16, fakeState);
if (orbits[0].angle === angle0) throw new Error('orbit angle did not advance');
console.log(JSON.stringify({ ok: true, orbits: orbits.length, filaments: filaments.length }));
"""
    )
    assert '"ok":true' in out.replace(" ", "")
