/** Titan Neural Renderer V3 — Neural Architecture Reconstruction tissue. */

import { NEURAL_CONFIG } from "./config.js";
import { rand } from "./utils.js";

/**
 * Living neural civilization — composition first, micro detail second.
 * Named major colonies · organic highways (split/merge) · dark voids ·
 * large-scale depth bands. Never a uniform particle fog.
 */

/**
 * Build microscopic local tissue concentrated toward the dense cognitive region.
 * @param {number} cx
 * @param {number} cy
 * @param {number} densityScale
 * @returns {Array<object>}
 */
export function buildCoreTissue(cx, cy, densityScale) {
  const cfg = NEURAL_CONFIG.tissue || {};
  const count = cfg.coreStrandCount ?? 520;
  const focus = _densityFocus(cx, cy, densityScale);
  /** @type {Array<object>} */
  const strands = [];

  const pockets = _seedDensityPockets(focus, densityScale, cfg.corePocketCount ?? 90);
  // Extra pockets packed tightly behind the TITAN CORE label zone.
  const labelPockets = _seedLabelZonePockets(focus, densityScale, Math.max(24, Math.floor((cfg.labelZoneStrandCount ?? 180) / 8)));

  for (let i = 0; i < count; i++) {
    const pocket = pockets[i % pockets.length];
    const kind = Math.random();
    let strand;
    if (kind < 0.4) {
      strand = _microScribble(pocket, densityScale, "core", i);
    } else if (kind < 0.7) {
      strand = _localBridge(pocket, densityScale, "core", i);
    } else if (kind < 0.88) {
      strand = _shortBranch(pocket, densityScale, "core", i);
    } else {
      const other = pockets[(i + 11) % pockets.length];
      strand = _interPocketWhisper(pocket, other, densityScale, "core", i);
    }
    strands.push(_tagCoreDepth(strand, focus, densityScale, i));
  }

  // Dense microscopic tissue immediately behind typography.
  const labelCount = cfg.labelZoneStrandCount ?? 180;
  for (let i = 0; i < labelCount; i++) {
    const pocket = labelPockets[i % labelPockets.length];
    const kind = Math.random();
    let strand;
    if (kind < 0.55) {
      strand = _microScribble(pocket, densityScale * 0.55, "core", i + 9000);
    } else if (kind < 0.82) {
      strand = _localBridge(pocket, densityScale * 0.55, "core", i + 9000);
    } else {
      const other = labelPockets[(i + 5) % labelPockets.length];
      strand = _interPocketWhisper(pocket, other, densityScale * 0.55, "core", i + 9000);
    }
    strand.opacity = Math.min((strand.opacity ?? 0.3) * 1.35, 0.72);
    strand.hue = Math.max(strand.hue ?? 0.7, 0.78);
    strand.depthTier = "labelBack";
    strand.parallax = 0.92;
    strands.push(strand);
  }

  // Irregular local neuron colonies + short curved synapses.
  const colonyCount = cfg.coreColonyCount ?? 14;
  const colonies = _seedCoreColonies(focus, densityScale, colonyCount);
  const synapseCount = cfg.coreColonySynapseCount ?? 120;
  for (let i = 0; i < synapseCount; i++) {
    const colony = colonies[i % colonies.length];
    strands.push(_colonySynapse(colony, densityScale, i));
  }

  // Sparse near-camera filaments — canvas-side foreground depth.
  const frontCount = cfg.nearForegroundCount ?? 40;
  for (let i = 0; i < frontCount; i++) {
    const pocket = pockets[(i * 7) % pockets.length];
    const strand = _shortBranch(pocket, densityScale * 0.7, "front", i + 12000);
    strand.depthTier = "front";
    strand.parallax = 1.12 + (i % 5) * 0.02;
    strand.opacity = rand(0.1, 0.28);
    strand.width = rand(0.35, 0.85);
    strand.hue = rand(0.72, 0.95);
    strands.push(strand);
  }

  return strands;
}

/**
 * Full-canvas neural civilization — colonies → highways → voids → micro detail.
 * @param {number} worldW
 * @param {number} worldH
 * @param {number} cx
 * @param {number} cy
 * @param {number} densityScale
 * @returns {Array<object>}
 */
export function buildFieldTissue(worldW, worldH, cx, cy, densityScale) {
  const cfg = NEURAL_CONFIG.tissue || {};
  const arch = NEURAL_CONFIG.architecture || {};
  const focus = _densityFocus(cx, cy, densityScale);
  /** @type {Array<object>} */
  const strands = [];

  // ——— PASS A: large-scale architecture ———
  const colonies = _seedMajorColonies(worldW, worldH, focus, densityScale, arch);
  const voids = _seedArchitectureVoids(worldW, worldH, focus, colonies, arch);
  const fieldPockets = _seedColonyPockets(colonies, cfg.fieldPocketCount ?? 200);
  /** @type {Array<object>} */
  const highways = [];

  // Neural highways — Core ↔ colonies, inter-colony bridges, splits & merges.
  _buildHighwayNetwork(colonies, voids, densityScale, arch, highways, cfg);
  for (const hw of highways) strands.push(hw);

  // Colony-local branching — unique density / shape / local twigs per hub.
  const colonyLocal = cfg.colonyLocalCount ?? 720;
  for (let i = 0; i < colonyLocal; i++) {
    const colony = _pickColonyByMass(colonies);
    strands.push(_colonyLocalBranch(colony, densityScale, i));
  }

  // Dense local synapses inside each colony (architecture mass, not fog).
  const localSynapse = cfg.galaxySynapseCount ?? 420;
  for (let i = 0; i < localSynapse; i++) {
    const colony = _pickColonyByMass(colonies);
    strands.push(_synapticBridge(colony, densityScale, i));
  }

  // ——— PASS B: depth atmosphere (sparse, colony-biased, void-rejecting) ———
  const veryFarCount = cfg.veryFarStrandCount ?? 220;
  const farCount = cfg.farStrandCount ?? 300;
  const midCount = cfg.midStrandCount ?? 360;
  const nearCount = cfg.nearStrandCount ?? 280;
  const foregroundCount = cfg.foregroundStrandCount ?? 60;

  for (let i = 0; i < veryFarCount; i++) {
    strands.push(_fieldMicroWisp(worldW, worldH, focus, densityScale, fieldPockets, voids, "veryFar", i));
  }
  for (let i = 0; i < farCount; i++) {
    strands.push(_fieldMicroWisp(worldW, worldH, focus, densityScale, fieldPockets, voids, "far", i));
  }
  for (let i = 0; i < midCount; i++) {
    strands.push(_fieldMicroWisp(worldW, worldH, focus, densityScale, fieldPockets, voids, "mid", i));
  }
  for (let i = 0; i < nearCount; i++) {
    strands.push(_fieldMicroWisp(worldW, worldH, focus, densityScale, fieldPockets, voids, "near", i));
  }
  for (let i = 0; i < foregroundCount; i++) {
    const strand = _fieldMicroWisp(
      worldW,
      worldH,
      focus,
      densityScale,
      fieldPockets,
      voids,
      "near",
      i + 8000,
    );
    strand.band = "foreground";
    strand.parallax = 1.1 + (i % 4) * 0.02;
    strand.opacity = Math.min((strand.opacity ?? 0.2) * 1.35, 0.55);
    strand.width = (strand.width ?? 0.4) * 1.25;
    strands.push(strand);
  }

  // ——— PASS C: micro detail only after architecture ———
  const microBridges = cfg.microBridgeCount ?? 180;
  for (let i = 0; i < microBridges; i++) {
    const pocket = fieldPockets[i % fieldPockets.length];
    const other = fieldPockets[(i + 17) % fieldPockets.length];
    // Prefer short bridges inside the same colony mass.
    if (Math.hypot(pocket.x - other.x, pocket.y - other.y) > densityScale * 0.85) continue;
    strands.push(_microColonyBridge(pocket, other, densityScale, i));
  }

  const branchCount = cfg.secondaryBranchCount ?? 48;
  for (let i = 0; i < branchCount; i++) {
    const a = colonies[Math.floor(Math.random() * colonies.length)];
    const b = colonies[Math.floor(Math.random() * colonies.length)];
    if (a === b) continue;
    strands.push(_secondaryBranch(a, b, densityScale, i));
  }

  const tertiaryCount = cfg.tertiaryBranchCount ?? 160;
  for (let i = 0; i < tertiaryCount; i++) {
    const host = fieldPockets[Math.floor(Math.random() * fieldPockets.length)];
    strands.push(_tertiaryTwig(host, densityScale, i));
  }

  const dustAxons = cfg.dustAxonCount ?? 160;
  for (let i = 0; i < dustAxons; i++) {
    strands.push(_dustAxon(worldW, worldH, focus, densityScale, voids, i));
  }

  const voidFringe = cfg.voidFringeCount ?? 40;
  for (let i = 0; i < voidFringe; i++) {
    strands.push(_voidFringeWisp(voids, densityScale, i));
  }

  return strands;
}

/**
 * Advance filament life — extremely subtle phase motion.
 * @param {Array<object>} strands
 * @param {number} deltaMs
 * @param {boolean} thinking
 */
export function updateTissue(strands, deltaMs, thinking) {
  const speed = thinking ? 0.00038 : 0.00018;
  for (const s of strands) {
    s.phase += deltaMs * speed * (s.phaseSpeed || 1);
  }
}

/**
 * @param {number} cx @param {number} cy @param {number} scale
 */
function _densityFocus(cx, cy, scale) {
  const asym = NEURAL_CONFIG.core?.asymmetry || {};
  return {
    x: cx + scale * (asym.x ?? -0.12),
    y: cy + scale * (asym.y ?? 0.08),
  };
}

/**
 * Overlapping local ganglia near the dense cognitive region.
 * @param {{ x: number, y: number }} focus
 * @param {number} scale
 * @param {number} count
 */
function _seedDensityPockets(focus, scale, count) {
  /** @type {Array<{ x: number, y: number, r: number }>} */
  const pockets = [];
  for (let i = 0; i < count; i++) {
    const spread = Math.pow(Math.random(), 1.35);
    const angle = rand(0, Math.PI * 2) + (i % 7) * 0.19;
    const stretchX = 1.25 + Math.sin(i * 0.71) * 0.42;
    const stretchY = 0.7 + Math.cos(i * 0.53) * 0.34;
    const dist = scale * spread * rand(0.04, 1.85);
    pockets.push({
      x: focus.x + Math.cos(angle) * dist * stretchX + rand(-scale * 0.1, scale * 0.1),
      y: focus.y + Math.sin(angle) * dist * stretchY + rand(-scale * 0.1, scale * 0.1),
      r: scale * rand(0.04, 0.18),
    });
  }
  return pockets;
}

/**
 * Tight irregular pockets under the TITAN CORE label — densifies tissue behind type.
 * @param {{ x: number, y: number }} focus
 * @param {number} scale
 * @param {number} count
 */
function _seedLabelZonePockets(focus, scale, count) {
  /** @type {Array<{ x: number, y: number, r: number }>} */
  const pockets = [];
  for (let i = 0; i < count; i++) {
    const angle = rand(-0.85, 0.85) + (i % 5) * 0.11;
    const stretchX = 1.55 + Math.sin(i * 0.4) * 0.25;
    const stretchY = 0.42 + Math.cos(i * 0.55) * 0.12;
    const dist = scale * Math.pow(Math.random(), 0.85) * rand(0.02, 0.38);
    pockets.push({
      x: focus.x + Math.cos(angle) * dist * stretchX + rand(-scale * 0.04, scale * 0.04),
      y: focus.y + Math.sin(angle) * dist * stretchY + rand(-scale * 0.05, scale * 0.05) - scale * 0.02,
      r: scale * rand(0.025, 0.09),
    });
  }
  return pockets;
}

/**
 * Small irregular neuron colonies around Core (organic, never radial).
 * @param {{ x: number, y: number }} focus
 * @param {number} scale
 * @param {number} count
 */
function _seedCoreColonies(focus, scale, count) {
  /** @type {Array<{ x: number, y: number, r: number }>} */
  const colonies = [];
  for (let i = 0; i < count; i++) {
    const angle = rand(0, Math.PI * 2) + i * 1.37;
    const dist = scale * rand(0.12, 0.95) * (0.55 + (i % 3) * 0.18);
    const stretchX = 1.2 + Math.sin(i * 0.9) * 0.35;
    const stretchY = 0.72 + Math.cos(i * 0.7) * 0.28;
    colonies.push({
      x: focus.x + Math.cos(angle) * dist * stretchX,
      y: focus.y + Math.sin(angle) * dist * stretchY,
      r: scale * rand(0.05, 0.14),
    });
  }
  return colonies;
}

/**
 * Short curved synapse inside a local colony — dense intersections without geometry.
 * @param {{ x: number, y: number, r: number }} colony
 * @param {number} scale
 * @param {number} seed
 */
function _colonySynapse(colony, scale, seed) {
  const a = rand(0, Math.PI * 2);
  const span = colony.r * rand(0.55, 1.9);
  const x0 = colony.x + Math.cos(a) * colony.r * rand(-0.7, 0.7);
  const y0 = colony.y + Math.sin(a) * colony.r * rand(-0.7, 0.7);
  const bend = span * rand(0.35, 0.95) * (seed % 2 === 0 ? 1 : -1);
  const x1 = x0 + Math.cos(a + rand(-1.1, 1.1)) * span;
  const y1 = y0 + Math.sin(a + rand(-1.1, 1.1)) * span;
  const mx = (x0 + x1) * 0.5 + Math.cos(a + Math.PI / 2) * bend;
  const my = (y0 + y1) * 0.5 + Math.sin(a + Math.PI / 2) * bend;
  return {
    band: "core",
    kind: "colony",
    depthTier: "mid",
    pts: [
      { x: x0, y: y0 },
      { x: mx, y: my },
      { x: x1, y: y1 },
    ],
    width: rand(0.14, 0.48),
    opacity: rand(0.16, 0.52),
    phase: rand(0, Math.PI * 2),
    phaseSpeed: rand(0.4, 1.15),
    hue: rand(0.62, 0.96),
    parallax: 0.95 + (seed % 4) * 0.02,
    seed,
  };
}

/**
 * Assign volumetric depth tier from distance to Core focus.
 * @param {object} strand
 * @param {{ x: number, y: number }} focus
 * @param {number} scale
 * @param {number} seed
 */
function _tagCoreDepth(strand, focus, scale, seed) {
  const p0 = strand.pts?.[0];
  if (!p0) {
    strand.depthTier = "mid";
    return strand;
  }
  const dx = p0.x - focus.x;
  const dy = p0.y - focus.y;
  const dist = Math.sqrt(dx * dx + dy * dy) / (scale || 1);
  let tier = "mid";
  if (dist > 1.35) tier = "deep";
  else if (dist > 0.75) tier = "mid";
  else if (dist > 0.28) tier = "near";
  else tier = "bright";
  // Sparse promotion to front layer for near-field depth cues.
  if (tier === "near" && seed % 17 === 0) tier = "front";
  strand.depthTier = tier;
  strand.parallax =
    tier === "deep"
      ? 0.72
      : tier === "mid"
        ? 0.88
        : tier === "near"
          ? 0.98
          : tier === "front"
            ? 1.14
            : 1.02;
  if (tier === "deep") {
    strand.opacity = (strand.opacity ?? 0.3) * 0.62;
    strand.width = (strand.width ?? 0.4) * 0.85;
  } else if (tier === "bright") {
    strand.opacity = Math.min((strand.opacity ?? 0.3) * 1.22, 0.78);
    strand.hue = Math.max(strand.hue ?? 0.7, 0.82);
  }
  return strand;
}

/**
 * Seed named major neural colonies — intentional civilization hubs.
 * Unique density, shape, size, and local branching per colony.
 * @param {number} worldW @param {number} worldH
 * @param {{ x: number, y: number }} focus
 * @param {number} scale
 * @param {object} arch
 * @returns {Array<object>}
 */
function _seedMajorColonies(worldW, worldH, focus, scale, arch) {
  const defs = arch.colonies || [];
  /** @type {Array<object>} */
  const colonies = [];
  const minDim = Math.min(worldW, worldH);

  if (!defs.length) {
    // Fallback Core hub if architecture config missing.
    colonies.push({
      id: "core",
      x: focus.x,
      y: focus.y,
      r: scale * 0.55,
      mass: 1.7,
      stretchX: 1.35,
      stretchY: 0.72,
      density: 1.5,
      shape: "nebula",
      localBranch: 1.3,
      secondary: false,
    });
    return colonies;
  }

  for (let i = 0; i < defs.length; i++) {
    const d = defs[i];
    const isCore = d.id === "core";
    const jitter = isCore ? 0.008 : 0.018;
    let x = isCore
      ? focus.x + rand(-scale * 0.06, scale * 0.05)
      : d.x * worldW + rand(-worldW * jitter, worldW * jitter);
    let y = isCore
      ? focus.y + rand(-scale * 0.05, scale * 0.08)
      : d.y * worldH + rand(-worldH * jitter, worldH * jitter);
    x = Math.max(worldW * 0.04, Math.min(worldW * 0.96, x));
    y = Math.max(worldH * 0.06, Math.min(worldH * 0.94, y));
    // Core field mass is restrained so peripheral colonies remain separate islands.
    const rBase = isCore
      ? scale * rand(0.38, 0.52)
      : minDim * (d.r ?? 0.09) * rand(0.95, 1.18);
    colonies.push({
      id: d.id || `colony_${i}`,
      x,
      y,
      r: rBase,
      mass: d.mass ?? 1,
      stretchX: d.stretchX ?? 1.1,
      stretchY: d.stretchY ?? 0.9,
      density: d.density ?? 1,
      shape: d.shape || "cluster",
      localBranch: d.localBranch ?? 1,
      secondary: Boolean(d.secondary),
    });
  }

  return colonies;
}

/**
 * Large dark voids between colonies — visual rhythm / breathing space.
 * Prefer interstitial midpoints so colonies remain islands.
 * @param {number} worldW @param {number} worldH
 * @param {{ x: number, y: number }} focus
 * @param {Array<object>} colonies
 * @param {object} arch
 */
function _seedArchitectureVoids(worldW, worldH, focus, colonies, arch) {
  const voidCfg = arch.voids || {};
  const count = voidCfg.count ?? NEURAL_CONFIG.tissue?.voidCount ?? 7;
  const rMin = voidCfg.radiusMinRatio ?? 0.12;
  const rMax = voidCfg.radiusMaxRatio ?? 0.26;
  /** @type {Array<{ x: number, y: number, r: number }>} */
  const voids = [];
  const minDim = Math.min(worldW, worldH);

  // Seed voids from colony midpoints for intentional negative space rhythm.
  const primaries = colonies.filter((c) => !c.secondary && c.id !== "core");
  for (let i = 0; i < primaries.length && voids.length < count; i++) {
    const a = primaries[i];
    const b = primaries[(i + 1) % primaries.length];
    const mx = (a.x + b.x) * 0.5 + (focus.x - (a.x + b.x) * 0.5) * 0.12;
    const my = (a.y + b.y) * 0.5 + (focus.y - (a.y + b.y) * 0.5) * 0.12;
    const outwardX = mx - focus.x;
    const outwardY = my - focus.y;
    const olen = Math.sqrt(outwardX * outwardX + outwardY * outwardY) || 1;
    const x = mx + (outwardX / olen) * minDim * rand(0.04, 0.12);
    const y = my + (outwardY / olen) * minDim * rand(0.04, 0.12);
    const r = minDim * rand(rMin, rMax);
    if (_voidConflicts(x, y, r, focus, colonies, voids, worldW, worldH)) continue;
    voids.push({ x, y, r });
  }

  let attempts = 0;
  while (voids.length < count && attempts < count * 22) {
    attempts++;
    const x = rand(worldW * 0.08, worldW * 0.92);
    const y = rand(worldH * 0.1, worldH * 0.9);
    const r = minDim * rand(rMin, rMax);
    if (_voidConflicts(x, y, r, focus, colonies, voids, worldW, worldH)) continue;
    voids.push({ x, y, r });
  }
  return voids;
}

/**
 * @param {number} x @param {number} y @param {number} r
 * @param {{ x: number, y: number }} focus
 * @param {Array<object>} colonies
 * @param {Array<{ x: number, y: number, r: number }>} voids
 * @param {number} worldW @param {number} worldH
 */
function _voidConflicts(x, y, r, focus, colonies, voids, worldW, worldH) {
  const minDim = Math.min(worldW, worldH);
  const dfx = x - focus.x;
  const dfy = y - focus.y;
  if (Math.sqrt(dfx * dfx + dfy * dfy) < minDim * 0.24) return true;
  for (const g of colonies) {
    const dx = x - g.x;
    const dy = y - g.y;
    if (Math.sqrt(dx * dx + dy * dy) < g.r * 0.85 + r * 0.7) return true;
  }
  for (const v of voids) {
    const dx = x - v.x;
    const dy = y - v.y;
    if (Math.sqrt(dx * dx + dy * dy) < (v.r + r) * 0.55) return true;
  }
  return false;
}

/**
 * Local ganglion pockets inside each colony (respects stretch shape).
 * @param {Array<object>} colonies
 * @param {number} count
 */
function _seedColonyPockets(colonies, count) {
  /** @type {Array<{ x: number, y: number, r: number, colonyId?: string }>} */
  const pockets = [];
  if (!colonies.length) return pockets;
  for (let i = 0; i < count; i++) {
    const g = _pickColonyByMass(colonies);
    const angle = rand(0, Math.PI * 2);
    // Tight power — pockets hug colony cores; interstitial space stays dark.
    const spread = Math.pow(Math.random(), 1.85);
    const dist = g.r * spread * rand(0.04, 0.92);
    const sx = g.stretchX ?? 1.1;
    const sy = g.stretchY ?? 0.9;
    pockets.push({
      x: g.x + Math.cos(angle) * dist * sx * rand(0.75, 1.2),
      y: g.y + Math.sin(angle) * dist * sy * rand(0.7, 1.15),
      r: g.r * rand(0.07, 0.24) * (g.density ?? 1),
      colonyId: g.id,
    });
  }
  return pockets;
}

/** @param {Array<object>} colonies */
function _pickColonyByMass(colonies) {
  let total = 0;
  for (const c of colonies) total += (c.mass ?? 1) * (c.density ?? 1);
  let roll = Math.random() * total;
  for (const c of colonies) {
    roll -= (c.mass ?? 1) * (c.density ?? 1);
    if (roll <= 0) return c;
  }
  return colonies[colonies.length - 1];
}

/**
 * Build curved neural highways: Core links, inter-colony routes, splits, merges.
 * @param {Array<object>} colonies
 * @param {Array<{ x: number, y: number, r: number }>} voids
 * @param {number} densityScale
 * @param {object} arch
 * @param {Array<object>} out
 * @param {object} cfg
 */
function _buildHighwayNetwork(colonies, voids, densityScale, arch, out, cfg) {
  const hw = arch.highways || {};
  const core = colonies.find((c) => c.id === "core") || colonies[0];
  if (!core) return;

  const majors = colonies.filter((c) => c.id !== "core" && !c.secondary);
  const secondaries = colonies.filter((c) => c.secondary);
  const linksPer = hw.coreLinksPerColony ?? 2;

  // Core → major colony highways (primary arteries + faint companion rail).
  for (let i = 0; i < majors.length; i++) {
    for (let k = 0; k < linksPer; k++) {
      const artery = _majorPathway(core, majors[i], voids, i * 10 + k, {
        artery: true,
        widthScale: 1.55,
      });
      out.push(artery);
      // Companion strand — reads as a bundled biological highway, not a single stroke.
      const companion = _majorPathway(core, majors[i], voids, i * 10 + k + 77, {
        artery: true,
        widthScale: 0.72,
      });
      companion.opacity = (companion.opacity ?? 0.18) * 0.72;
      companion.parallax = (companion.parallax ?? 0.4) * 0.92;
      out.push(companion);
    }
  }

  // Core → secondary hubs (thinner).
  for (let i = 0; i < secondaries.length; i++) {
    out.push(_majorPathway(core, secondaries[i], voids, 200 + i, { artery: false, widthScale: 0.95 }));
  }

  // Inter-colony bridges — biological cross-links (never a star-only topology).
  const interCount = hw.interColonyLinks ?? cfg.majorPathwayCount ?? 10;
  const periphery = majors.concat(secondaries);
  for (let i = 0; i < interCount && periphery.length > 1; i++) {
    const a = periphery[i % periphery.length];
    const b = periphery[(i + 2 + (i % 3)) % periphery.length];
    if (a === b) continue;
    out.push(_majorPathway(a, b, voids, 400 + i, { artery: false, widthScale: 0.95 }));
  }

  // Splits — organic forks peeling from mid-highway.
  const splitCount = cfg.highwaySplitCount ?? hw.splitCount ?? 20;
  for (let i = 0; i < splitCount && out.length; i++) {
    const host = out[i % out.length];
    strandsPushSafe(out, _highwaySplit(host, densityScale, i));
  }

  // Merges — converging tendrils between nearby highways.
  const mergeCount = cfg.highwayMergeCount ?? hw.mergeCount ?? 14;
  for (let i = 0; i < mergeCount && out.length > 1; i++) {
    const a = out[i % out.length];
    const b = out[(i + 3) % out.length];
    strandsPushSafe(out, _highwayMerge(a, b, densityScale, i));
  }
}

/** @param {Array<object>} arr @param {object | null} strand */
function strandsPushSafe(arr, strand) {
  if (strand) arr.push(strand);
}

/**
 * Local branching unique to colony shape — nebula / plume / ridge / knot / arc.
 * @param {object} colony
 * @param {number} scale
 * @param {number} seed
 */
function _colonyLocalBranch(colony, scale, seed) {
  const shape = colony.shape || "cluster";
  const sx = colony.stretchX ?? 1.1;
  const sy = colony.stretchY ?? 0.9;
  const branch = colony.localBranch ?? 1;
  const density = colony.density ?? 1;

  let angle = rand(0, Math.PI * 2);
  if (shape === "ridge") angle = rand(-0.45, 0.45) + (seed % 2 === 0 ? 0 : Math.PI);
  if (shape === "arc") angle = rand(-0.9, 0.9) + Math.PI * 0.85;
  if (shape === "plume") angle = rand(-0.55, 0.55) - Math.PI * 0.35;

  const span = colony.r * rand(0.35, 1.35) * branch;
  const x0 = colony.x + Math.cos(angle) * colony.r * rand(-0.35, 0.55) * sx;
  const y0 = colony.y + Math.sin(angle) * colony.r * rand(-0.35, 0.55) * sy;
  /** @type {Array<{ x: number, y: number }>} */
  const pts = [{ x: x0, y: y0 }];
  let x = x0;
  let y = y0;
  let a = angle;
  const steps = shape === "knot" ? 5 + (seed % 3) : 3 + (seed % 3);
  for (let i = 0; i < steps; i++) {
    const curl =
      shape === "knot"
        ? rand(-1.35, 1.35)
        : shape === "nebula"
          ? rand(-1.05, 1.05)
          : rand(-0.75, 0.75);
    a += curl;
    x += Math.cos(a) * (span / steps) * sx;
    y += Math.sin(a) * (span / steps) * sy;
    // Soft leash so local twigs stay colony-authored.
    x = x * 0.82 + colony.x * 0.18;
    y = y * 0.82 + colony.y * 0.18;
    pts.push({ x, y });
  }

  return {
    band: seed % 5 === 0 ? "near" : seed % 3 === 0 ? "bridge" : "mid",
    kind: "colony",
    colonyId: colony.id,
    pts,
    width: rand(0.12, 0.48) * density,
    opacity: rand(0.1, 0.36) * Math.min(1.25, density),
    phase: rand(0, Math.PI * 2),
    phaseSpeed: rand(0.35, 1.1),
    hue: rand(0.55, 0.96),
    parallax: 0.5 + (seed % 5) * 0.08,
    seed,
  };
}

/**
 * @param {number} x @param {number} y
 * @param {Array<{ x: number, y: number, r: number }>} voids
 */
function _insideVoid(x, y, voids) {
  for (const v of voids) {
    const dx = x - v.x;
    const dy = y - v.y;
    if (dx * dx + dy * dy < v.r * v.r * 0.85) return true;
  }
  return false;
}

/**
 * @param {{ x: number, y: number, r: number }} pocket
 * @param {number} scale @param {string} band @param {number} seed
 */
function _microScribble(pocket, scale, band, seed) {
  const segments = 3 + Math.floor(Math.random() * 4);
  /** @type {Array<{ x: number, y: number }>} */
  const pts = [];
  let x = pocket.x + rand(-pocket.r, pocket.r);
  let y = pocket.y + rand(-pocket.r, pocket.r);
  pts.push({ x, y });
  let angle = rand(0, Math.PI * 2);
  for (let i = 0; i < segments; i++) {
    angle += rand(-1.15, 1.15);
    const step = pocket.r * rand(0.3, 0.95);
    x += Math.cos(angle) * step;
    y += Math.sin(angle) * step;
    x = x * 0.8 + pocket.x * 0.2;
    y = y * 0.8 + pocket.y * 0.2;
    pts.push({ x, y });
  }
  return {
    band,
    kind: "micro",
    pts,
    width: rand(0.18, 0.7),
    opacity: rand(0.18, 0.58),
    phase: rand(0, Math.PI * 2),
    phaseSpeed: rand(0.5, 1.4),
    hue: rand(0.65, 1),
    seed,
  };
}

/**
 * @param {{ x: number, y: number, r: number }} pocket
 * @param {number} scale @param {string} band @param {number} seed
 */
function _localBridge(pocket, scale, band, seed) {
  const a = rand(0, Math.PI * 2);
  const span = pocket.r * rand(0.7, 2.0);
  const x0 = pocket.x + Math.cos(a) * pocket.r * rand(-0.6, 0.6);
  const y0 = pocket.y + Math.sin(a) * pocket.r * rand(-0.6, 0.6);
  const x1 = x0 + Math.cos(a + rand(-0.85, 0.85)) * span;
  const y1 = y0 + Math.sin(a + rand(-0.85, 0.85)) * span;
  const bend = span * rand(0.22, 0.75) * (seed % 2 === 0 ? 1 : -1);
  const mx = (x0 + x1) * 0.5 + Math.cos(a + Math.PI / 2) * bend;
  const my = (y0 + y1) * 0.5 + Math.sin(a + Math.PI / 2) * bend;
  return {
    band,
    kind: "bridge",
    pts: [
      { x: x0, y: y0 },
      { x: mx, y: my },
      { x: x1, y: y1 },
    ],
    width: rand(0.16, 0.58),
    opacity: rand(0.14, 0.48),
    phase: rand(0, Math.PI * 2),
    phaseSpeed: rand(0.45, 1.25),
    hue: rand(0.55, 0.92),
    seed,
  };
}

/**
 * @param {{ x: number, y: number, r: number }} pocket
 * @param {number} scale @param {string} band @param {number} seed
 */
function _shortBranch(pocket, scale, band, seed) {
  /** @type {Array<{ x: number, y: number }>} */
  const pts = [];
  let x = pocket.x + rand(-pocket.r * 0.5, pocket.r * 0.5);
  let y = pocket.y + rand(-pocket.r * 0.5, pocket.r * 0.5);
  pts.push({ x, y });
  let a = rand(0, Math.PI * 2);
  const steps = 3 + Math.floor(Math.random() * 3);
  const len = pocket.r * rand(1.1, 2.6);
  for (let i = 0; i < steps; i++) {
    a += rand(-0.95, 0.95);
    x += Math.cos(a) * (len / steps);
    y += Math.sin(a) * (len / steps);
    pts.push({ x, y });
  }
  return {
    band,
    kind: "branch",
    pts,
    width: rand(0.15, 0.5),
    opacity: rand(0.12, 0.4),
    phase: rand(0, Math.PI * 2),
    phaseSpeed: rand(0.5, 1.2),
    hue: rand(0.5, 0.88),
    seed,
  };
}

/**
 * @param {{ x: number, y: number, r: number }} a
 * @param {{ x: number, y: number, r: number }} b
 * @param {number} scale @param {string} band @param {number} seed
 */
function _interPocketWhisper(a, b, scale, band, seed) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const dist = Math.sqrt(dx * dx + dy * dy) || 1;
  if (dist > scale * 0.7) {
    return _localBridge(a, scale, band, seed);
  }
  const bend = dist * rand(0.18, 0.5) * (seed % 2 === 0 ? 1 : -1);
  const nx = -dy / dist;
  const ny = dx / dist;
  return {
    band,
    kind: "merge",
    pts: [
      { x: a.x + rand(-a.r * 0.3, a.r * 0.3), y: a.y + rand(-a.r * 0.3, a.r * 0.3) },
      { x: (a.x + b.x) * 0.5 + nx * bend, y: (a.y + b.y) * 0.5 + ny * bend },
      { x: b.x + rand(-b.r * 0.3, b.r * 0.3), y: b.y + rand(-b.r * 0.3, b.r * 0.3) },
    ],
    width: rand(0.16, 0.52),
    opacity: band === "bridge" ? rand(0.06, 0.18) : rand(0.12, 0.36),
    phase: rand(0, Math.PI * 2),
    phaseSpeed: rand(0.4, 1.1),
    hue: rand(0.55, 0.9),
    parallax: band === "bridge" ? 0.48 : undefined,
    seed,
  };
}

/**
 * Atmospheric micro-wisp from a galaxy pocket — skips voids.
 * @param {number} worldW @param {number} worldH
 * @param {{ x: number, y: number }} focus
 * @param {number} scale
 * @param {Array<{ x: number, y: number, r: number }>} pockets
 * @param {Array<{ x: number, y: number, r: number }>} voids
 * @param {"veryFar"|"far"|"mid"|"near"} band
 * @param {number} seed
 */
function _fieldMicroWisp(worldW, worldH, focus, densityScale, pockets, voids, band, seed) {
  const pocket = pockets[seed % pockets.length];
  let x = pocket.x + rand(-pocket.r, pocket.r);
  let y = pocket.y + rand(-pocket.r, pocket.r);

  // Soft reject: push samples out of voids into nearest pocket.
  if (_insideVoid(x, y, voids)) {
    x = pocket.x;
    y = pocket.y;
  }

  const lenScale =
    band === "veryFar"
      ? rand(0.008, 0.028)
      : band === "far"
        ? rand(0.009, 0.03)
        : band === "mid"
          ? rand(0.007, 0.024)
          : rand(0.006, 0.018);
  const len = Math.min(worldW, worldH) * lenScale;
  const steps = band === "veryFar" || band === "far" ? 4 : 3;
  /** @type {Array<{ x: number, y: number }>} */
  const pts = [{ x, y }];
  let a = rand(0, Math.PI * 2);
  for (let i = 0; i < steps; i++) {
    a += rand(-1.05, 1.05);
    x += Math.cos(a) * (len / steps);
    y += Math.sin(a) * (len / steps);
    pts.push({ x, y });
  }

  const dx = pocket.x - focus.x;
  const dy = pocket.y - focus.y;
  // Steeper falloff — atmospheric fill stays colony-biased, voids stay dark.
  const prox = 1 - Math.min(1, Math.sqrt(dx * dx + dy * dy) / (densityScale * 3.2));
  const baseOpacity =
    band === "veryFar"
      ? rand(0.015, 0.055)
      : band === "far"
        ? rand(0.03, 0.11)
        : band === "mid"
          ? rand(0.07, 0.22)
          : rand(0.12, 0.36);
  const opacity = baseOpacity * (0.55 + prox * 0.9);

  return {
    band,
    kind: "wisp",
    pts,
    width:
      band === "veryFar"
        ? rand(0.1, 0.34)
        : band === "far"
          ? rand(0.12, 0.4)
          : band === "mid"
            ? rand(0.16, 0.52)
            : rand(0.2, 0.66),
    opacity,
    phase: rand(0, Math.PI * 2),
    phaseSpeed: rand(0.3, 1.05),
    hue: rand(0.38, 0.85),
    parallax:
      band === "veryFar" ? 0.06 : band === "far" ? 0.16 : band === "mid" ? 0.46 : 0.84,
    seed,
  };
}

/**
 * @param {{ x: number, y: number, r: number }} pocket
 * @param {number} scale
 * @param {number} seed
 */
function _synapticBridge(pocket, scale, seed) {
  const dens = pocket.density ?? 1;
  const sx = pocket.stretchX ?? 1;
  const sy = pocket.stretchY ?? 1;
  const span = pocket.r * rand(0.85, 2.2) * Math.min(1.35, dens);
  const a = rand(0, Math.PI * 2);
  const bx = pocket.x + rand(-pocket.r * 0.4, pocket.r * 0.4) * sx;
  const by = pocket.y + rand(-pocket.r * 0.4, pocket.r * 0.4) * sy;
  const x2 = bx + Math.cos(a) * span * sx;
  const y2 = by + Math.sin(a) * span * sy;
  const bend = span * rand(0.32, 0.85) * (seed % 2 === 0 ? 1 : -1);
  const nx = -(y2 - by);
  const ny = x2 - bx;
  const nLen = Math.sqrt(nx * nx + ny * ny) || 1;
  return {
    band: dens > 1.2 ? "near" : "bridge",
    kind: "bridge",
    colonyId: pocket.id || pocket.colonyId,
    pts: [
      { x: bx, y: by },
      { x: (bx + x2) * 0.5 + (nx / nLen) * bend, y: (by + y2) * 0.5 + (ny / nLen) * bend },
      { x: x2, y: y2 },
    ],
    width: rand(0.14, 0.5) * Math.min(1.25, dens),
    opacity: rand(0.08, 0.26) * Math.min(1.3, dens),
    phase: rand(0, Math.PI * 2),
    phaseSpeed: rand(0.45, 1.15),
    hue: rand(0.5, 0.9),
    parallax: 0.5 + (seed % 5) * 0.06,
    seed,
  };
}

/**
 * Major inter-colony highway — multi-segment organic S-curve, never a ruler.
 * Curves, breathes past voids, and carries artery metadata for sheath drawing.
 * @param {{ x: number, y: number, r: number }} a
 * @param {{ x: number, y: number, r: number }} b
 * @param {Array<{ x: number, y: number, r: number }>} voids
 * @param {number} seed
 * @param {{ artery?: boolean, widthScale?: number }} [opts]
 */
function _majorPathway(a, b, voids, seed, opts = {}) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const dist = Math.sqrt(dx * dx + dy * dy) || 1;
  const nx = -dy / dist;
  const ny = dx / dist;
  const sign = seed % 2 === 0 ? 1 : -1;
  const segments = 5 + (seed % 4);
  /** @type {Array<{ x: number, y: number }>} */
  const pts = [];
  const ax = (a.stretchX ?? 1) * a.r;
  const ay = (a.stretchY ?? 1) * a.r;
  const bx = (b.stretchX ?? 1) * b.r;
  const by = (b.stretchY ?? 1) * b.r;
  const x0 = a.x + rand(-ax * 0.32, ax * 0.32);
  const y0 = a.y + rand(-ay * 0.32, ay * 0.32);
  pts.push({ x: x0, y: y0 });

  for (let i = 1; i < segments; i++) {
    const t = i / segments;
    // Biological growth: alternating bends + soft lateral wander.
    const bend =
      dist *
      (0.12 + Math.sin(t * Math.PI) * 0.28 + Math.sin(t * Math.PI * 2.2) * 0.08) *
      sign *
      (i % 2 === 0 ? 1 : -0.78) *
      rand(0.7, 1.3);
    let mx = a.x + dx * t + nx * bend + rand(-dist * 0.04, dist * 0.04);
    let my = a.y + dy * t + ny * bend + rand(-dist * 0.04, dist * 0.04);
    // Gravitational funnel: denser hub (Core) pulls midpoints toward itself.
    const massA = a.mass ?? 1;
    const massB = b.mass ?? 1;
    if (massA > 1.4 || massB > 1.4) {
      const pull = massA >= massB ? a : b;
      const funnel = Math.sin(t * Math.PI) * (opts.artery ? 0.28 : 0.16);
      mx += (pull.x - mx) * funnel;
      my += (pull.y - my) * funnel;
    }
    if (_insideVoid(mx, my, voids)) {
      mx += nx * dist * 0.16 * sign;
      my += ny * dist * 0.16 * sign;
    }
    pts.push({ x: mx, y: my });
  }

  pts.push({
    x: b.x + rand(-bx * 0.32, bx * 0.32),
    y: b.y + rand(-by * 0.32, by * 0.32),
  });

  const artery = Boolean(opts.artery);
  const widthScale = opts.widthScale ?? 1;
  return {
    band: artery ? "near" : seed % 2 === 0 ? "mid" : "bridge",
    kind: "pathway",
    artery,
    pts,
    width: rand(0.45, 1.25) * widthScale * (artery ? 1.35 : 1),
    opacity: rand(0.16, 0.36) * (artery ? 1.35 : 1),
    phase: rand(0, Math.PI * 2),
    phaseSpeed: rand(0.18, 0.65),
    hue: rand(0.68, 1.0),
    parallax: artery ? 0.55 + (seed % 3) * 0.06 : 0.28 + (seed % 4) * 0.08,
    seed,
  };
}

/**
 * Organic fork peeling from a mid-highway corridor.
 * @param {object} host
 * @param {number} scale
 * @param {number} seed
 * @returns {object | null}
 */
function _highwaySplit(host, scale, seed) {
  const pts = host.pts;
  if (!pts || pts.length < 3) return null;
  const idx = 1 + (seed % Math.max(1, pts.length - 2));
  const origin = pts[idx];
  const prev = pts[Math.max(0, idx - 1)];
  const dx = origin.x - prev.x;
  const dy = origin.y - prev.y;
  const len = Math.sqrt(dx * dx + dy * dy) || 1;
  const nx = -dy / len;
  const ny = dx / len;
  const sign = seed % 2 === 0 ? 1 : -1;
  const forkLen = scale * rand(0.22, 0.7);
  /** @type {Array<{ x: number, y: number }>} */
  const fork = [{ x: origin.x, y: origin.y }];
  let x = origin.x;
  let y = origin.y;
  let ang = Math.atan2(dy, dx) + sign * rand(0.55, 1.25);
  const steps = 3 + (seed % 3);
  for (let i = 0; i < steps; i++) {
    ang += rand(-0.55, 0.55);
    x += Math.cos(ang) * (forkLen / steps) + nx * sign * forkLen * 0.04;
    y += Math.sin(ang) * (forkLen / steps) + ny * sign * forkLen * 0.04;
    fork.push({ x, y });
  }
  return {
    band: "bridge",
    kind: "pathway",
    artery: false,
    split: true,
    pts: fork,
    width: (host.width ?? 0.5) * rand(0.35, 0.65),
    opacity: (host.opacity ?? 0.15) * rand(0.55, 0.85),
    phase: rand(0, Math.PI * 2),
    phaseSpeed: rand(0.25, 0.8),
    hue: rand(0.55, 0.92),
    parallax: 0.36 + (seed % 3) * 0.08,
    seed,
  };
}

/**
 * Converging merge tendril between two highway corridors.
 * @param {object} a
 * @param {object} b
 * @param {number} scale
 * @param {number} seed
 * @returns {object | null}
 */
function _highwayMerge(a, b, scale, seed) {
  if (!a?.pts?.length || !b?.pts?.length) return null;
  const pa = a.pts[Math.floor(a.pts.length * rand(0.3, 0.7))];
  const pb = b.pts[Math.floor(b.pts.length * rand(0.3, 0.7))];
  const dx = pb.x - pa.x;
  const dy = pb.y - pa.y;
  const dist = Math.sqrt(dx * dx + dy * dy) || 1;
  if (dist > scale * 1.6 || dist < scale * 0.12) return null;
  const nx = -dy / dist;
  const ny = dx / dist;
  const bend = dist * rand(0.22, 0.55) * (seed % 2 === 0 ? 1 : -1);
  return {
    band: "bridge",
    kind: "pathway",
    artery: false,
    merge: true,
    pts: [
      { x: pa.x, y: pa.y },
      { x: (pa.x + pb.x) * 0.5 + nx * bend, y: (pa.y + pb.y) * 0.5 + ny * bend },
      { x: pb.x, y: pb.y },
    ],
    width: rand(0.22, 0.55),
    opacity: rand(0.08, 0.2),
    phase: rand(0, Math.PI * 2),
    phaseSpeed: rand(0.22, 0.7),
    hue: rand(0.5, 0.9),
    parallax: 0.34 + (seed % 3) * 0.07,
    seed,
  };
}

/**
 * Secondary branch — thinner tendril off a pathway corridor.
 * @param {{ x: number, y: number, r: number }} a
 * @param {{ x: number, y: number, r: number }} b
 * @param {number} scale
 * @param {number} seed
 */
function _secondaryBranch(a, b, scale, seed) {
  const t = rand(0.2, 0.8);
  const bx = a.x + (b.x - a.x) * t;
  const by = a.y + (b.y - a.y) * t;
  const angle = rand(0, Math.PI * 2);
  const len = scale * rand(0.18, 0.55);
  /** @type {Array<{ x: number, y: number }>} */
  const pts = [{ x: bx, y: by }];
  let x = bx;
  let y = by;
  let ang = angle;
  const steps = 4 + Math.floor(Math.random() * 2);
  for (let i = 0; i < steps; i++) {
    ang += rand(-0.85, 0.85);
    x += Math.cos(ang) * (len / steps);
    y += Math.sin(ang) * (len / steps);
    pts.push({ x, y });
  }
  return {
    band: "mid",
    kind: "secondary",
    pts,
    width: rand(0.12, 0.4),
    opacity: rand(0.05, 0.16),
    phase: rand(0, Math.PI * 2),
    phaseSpeed: rand(0.35, 1.0),
    hue: rand(0.4, 0.82),
    parallax: 0.42 + (seed % 3) * 0.1,
    seed,
  };
}

/**
 * Tertiary twig — hair-thin local synaptic feather.
 * @param {{ x: number, y: number, r: number }} host
 * @param {number} scale
 * @param {number} seed
 */
function _tertiaryTwig(host, scale, seed) {
  const angle = rand(0, Math.PI * 2);
  const len = host.r * rand(0.55, 1.65);
  let x = host.x + rand(-host.r * 0.4, host.r * 0.4);
  let y = host.y + rand(-host.r * 0.4, host.r * 0.4);
  /** @type {Array<{ x: number, y: number }>} */
  const pts = [{ x, y }];
  let ang = angle;
  const steps = 2 + Math.floor(Math.random() * 3);
  for (let i = 0; i < steps; i++) {
    ang += rand(-1.1, 1.1);
    x += Math.cos(ang) * (len / steps);
    y += Math.sin(ang) * (len / steps);
    pts.push({ x, y });
  }
  return {
    band: seed % 3 === 0 ? "near" : "mid",
    kind: "tertiary",
    pts,
    width: rand(0.08, 0.26),
    opacity: rand(0.04, 0.12),
    phase: rand(0, Math.PI * 2),
    phaseSpeed: rand(0.4, 1.2),
    hue: rand(0.38, 0.78),
    parallax: 0.55 + (seed % 4) * 0.08,
    seed,
  };
}

/**
 * Micro bridge between neighboring colony pockets — fills empty gaps.
 * @param {{ x: number, y: number, r: number }} a
 * @param {{ x: number, y: number, r: number }} b
 * @param {number} scale
 * @param {number} seed
 */
function _microColonyBridge(a, b, scale, seed) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const dist = Math.sqrt(dx * dx + dy * dy) || 1;
  if (dist > scale * 1.15 || dist < scale * 0.04) {
    return _synapticBridge(a, scale, seed);
  }
  const nx = -dy / dist;
  const ny = dx / dist;
  const bend = dist * rand(0.2, 0.55) * (seed % 2 === 0 ? 1 : -1);
  return {
    band: "bridge",
    kind: "bridge",
    pts: [
      { x: a.x + rand(-a.r * 0.25, a.r * 0.25), y: a.y + rand(-a.r * 0.25, a.r * 0.25) },
      { x: (a.x + b.x) * 0.5 + nx * bend, y: (a.y + b.y) * 0.5 + ny * bend },
      { x: b.x + rand(-b.r * 0.25, b.r * 0.25), y: b.y + rand(-b.r * 0.25, b.r * 0.25) },
    ],
    width: rand(0.1, 0.36),
    opacity: rand(0.05, 0.16),
    phase: rand(0, Math.PI * 2),
    phaseSpeed: rand(0.4, 1.1),
    hue: rand(0.42, 0.85),
    parallax: 0.48 + (seed % 5) * 0.05,
    seed,
  };
}

/**
 * Sparse axon dust — preserves void darkness.
 * @param {number} worldW @param {number} worldH
 * @param {{ x: number, y: number }} focus
 * @param {number} scale
 * @param {Array<{ x: number, y: number, r: number }>} voids
 * @param {number} seed
 */
function _dustAxon(worldW, worldH, focus, scale, voids, seed) {
  let x = rand(worldW * 0.02, worldW * 0.98);
  let y = rand(worldH * 0.02, worldH * 0.98);
  let guard = 0;
  while (_insideVoid(x, y, voids) && guard < 8) {
    x = rand(worldW * 0.02, worldW * 0.98);
    y = rand(worldH * 0.02, worldH * 0.98);
    guard++;
  }

  // Soft Core bias only — dust must not refill architectural voids.
  if (Math.random() < 0.14) {
    const a = rand(0, Math.PI * 2);
    const dist = scale * Math.pow(Math.random(), 1.15) * rand(0.35, 2.2);
    x = focus.x + Math.cos(a) * dist * rand(0.7, 1.35);
    y = focus.y + Math.sin(a) * dist * rand(0.6, 1.2);
    if (_insideVoid(x, y, voids)) {
      x = rand(worldW * 0.02, worldW * 0.98);
      y = rand(worldH * 0.02, worldH * 0.98);
    }
  }

  const len = Math.min(worldW, worldH) * rand(0.004, 0.016);
  const a0 = rand(0, Math.PI * 2);
  const x2 = x + Math.cos(a0) * len;
  const y2 = y + Math.sin(a0) * len;
  const bend = len * rand(0.28, 0.85) * (seed % 2 === 0 ? 1 : -1);
  return {
    band: "veryFar",
    kind: "dust",
    pts: [
      { x, y },
      {
        x: (x + x2) * 0.5 + Math.cos(a0 + Math.PI / 2) * bend,
        y: (y + y2) * 0.5 + Math.sin(a0 + Math.PI / 2) * bend,
      },
      { x: x2, y: y2 },
    ],
    width: rand(0.07, 0.26),
    opacity: rand(0.025, 0.085),
    phase: rand(0, Math.PI * 2),
    phaseSpeed: rand(0.28, 0.9),
    hue: rand(0.32, 0.72),
    parallax: 0.08 + (seed % 4) * 0.03,
    seed,
  };
}

/**
 * Soft fringe along void edges — never fills the breathing space.
 * @param {Array<{ x: number, y: number, r: number }>} voids
 * @param {number} scale
 * @param {number} seed
 */
function _voidFringeWisp(voids, scale, seed) {
  if (!voids.length) {
    return {
      band: "veryFar",
      kind: "voidFringe",
      pts: [
        { x: 0, y: 0 },
        { x: 1, y: 1 },
      ],
      width: 0.1,
      opacity: 0,
      phase: 0,
      phaseSpeed: 1,
      hue: 0.5,
      parallax: 0.1,
      seed,
    };
  }
  const v = voids[seed % voids.length];
  const a = rand(0, Math.PI * 2);
  const rim = v.r * rand(0.92, 1.08);
  const x = v.x + Math.cos(a) * rim;
  const y = v.y + Math.sin(a) * rim;
  const len = scale * rand(0.04, 0.12);
  const tang = a + Math.PI / 2 + rand(-0.4, 0.4);
  return {
    band: "far",
    kind: "voidFringe",
    pts: [
      { x, y },
      {
        x: x + Math.cos(tang) * len * 0.5 + Math.cos(a) * len * 0.15,
        y: y + Math.sin(tang) * len * 0.5 + Math.sin(a) * len * 0.15,
      },
      { x: x + Math.cos(tang) * len, y: y + Math.sin(tang) * len },
    ],
    width: rand(0.1, 0.32),
    opacity: rand(0.025, 0.08),
    phase: rand(0, Math.PI * 2),
    phaseSpeed: rand(0.3, 0.9),
    hue: rand(0.35, 0.7),
    parallax: 0.18 + (seed % 3) * 0.06,
    seed,
  };
}
