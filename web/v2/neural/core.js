/** Titan Neural Renderer V3 — Dense cognitive region continuum (Neural Core Master Polish). */

import { NEURAL_CONFIG } from "./config.js";
import { buildOrganicControls } from "./bezier.js";
import { NODE_CLASSES } from "./node-classes.js";
import { buildCoreTissue, buildFieldTissue, updateTissue } from "./tissue.js";
import { rand } from "./utils.js";

/**
 * Titan Core is not a separate brain object.
 * It is the region where neural density naturally peaks inside one continuous field.
 * No sphere, yarn-ball silhouette, glowing orb, or star hub.
 */
export class NeuralCore {
  constructor() {
    this.cx = 0;
    this.cy = 0;
    this.breathePhase = Math.random() * Math.PI * 2;
    this.pulse = 0.72;
    /** @type {number[]} */
    this.hubNodeIds = [];
    /** @type {number | null} */
    this.centerNodeId = null;
    /** @type {number[]} */
    this.branchEdgeIndices = [];
    /** @type {number[]} */
    this.radialEdgeIndices = [];
    /** Dense-region microscopic filaments (overlapping local clusters). */
    /** @type {Array<object>} */
    this.filaments = [];
    /** Near-camera front filaments (drawn after mid field for depth). */
    /** @type {Array<object>} */
    this.filamentsFront = [];
    /** Full-canvas atmospheric neural tissue. */
    /** @type {Array<object>} */
    this.fieldTissue = [];
    /** Microscopic neuron dust concentrated by density, not by a sphere. */
    /** @type {Array<{ x: number, y: number, r: number, a: number, phase: number }>} */
    this.microNeurons = [];
    /**
     * Local energy packets — filament riders + tight nucleus orbiters.
     * Never roam the full canvas; Core-local only.
     * @type {Array<object>}
     */
    this.energyPackets = [];
  }

  /**
   * @param {import("./nodes.js").NeuralNodes} nodes
   * @param {number} worldWidth
   * @param {number} worldHeight
   */
  build(nodes, worldWidth, worldHeight) {
    const cfg = NEURAL_CONFIG.core;
    this.cx = worldWidth * cfg.xRatio;
    this.cy = worldHeight * cfg.yRatio;
    this.hubNodeIds = [];
    this.branchEdgeIndices = [];
    this.radialEdgeIndices = [];
    this.centerNodeId = null;
    this.filaments = [];
    this.filamentsFront = [];
    this.fieldTissue = [];
    this.microNeurons = [];
    this.energyPackets = [];

    // Soft spatial scale — guides density, never a hard circular boundary.
    const densityScale = Math.min(worldWidth, worldHeight) * cfg.clusterRadiusRatio;
    const nodeCfg = NEURAL_CONFIG.nodes;
    const satelliteCount = nodeCfg.coreSatellites ?? 96;
    const asym = cfg.asymmetry || {};
    const focusX = this.cx + densityScale * (asym.x ?? -0.12);
    const focusY = this.cy + densityScale * (asym.y ?? 0.08);

    // Identity nucleus anchor — layered white-hot Core drawn in renderer.
    const centerIdx = nodes.nodes.length;
    nodes.nodes.push(this._createHubNode(centerIdx, focusX, focusY, cfg.hubRadius * 0.55, true));
    this.centerNodeId = centerIdx;
    this.hubNodeIds.push(centerIdx);

    // Overlapping local hub pockets — irregular ganglia that merge into density.
    for (let i = 0; i < satelliteCount; i++) {
      const angle = rand(0, Math.PI * 2) + i * 0.11;
      const spread = Math.pow(Math.random(), 1.15);
      // Elongated / asymmetric cloud — never a ball silhouette; spreads into field.
      const stretchX = 1.28 + Math.sin(i * 0.61) * 0.45;
      const stretchY = 0.68 + Math.cos(i * 0.47) * 0.36;
      const dist = densityScale * (0.02 + spread * 2.4);
      const sx =
        focusX + Math.cos(angle) * dist * stretchX + rand(-densityScale * 0.14, densityScale * 0.14);
      const sy =
        focusY + Math.sin(angle) * dist * stretchY + rand(-densityScale * 0.14, densityScale * 0.14);
      const id = nodes.nodes.length;
      nodes.nodes.push(
        this._createHubNode(
          id,
          sx,
          sy,
          rand(cfg.satelliteRadiusMin, cfg.satelliteRadiusMax) * rand(0.45, 0.88),
          false,
        ),
      );
      this.hubNodeIds.push(id);
    }

    // Nearest-neighbor mesh among hubs — short local synapses only.
    const hubsOnly = this.hubNodeIds.slice(1);
    for (let i = 0; i < hubsOnly.length; i++) {
      const hubId = hubsOnly[i];
      const hub = nodes.nodes[hubId];
      if (!hub) continue;
      const neighbors = hubsOnly
        .filter((id) => id !== hubId)
        .map((id) => {
          const n = nodes.nodes[id];
          const dx = n.x - hub.x;
          const dy = n.y - hub.y;
          return { id, dist: Math.sqrt(dx * dx + dy * dy) };
        })
        .sort((a, b) => a.dist - b.dist);

      const linkCount = 2 + (Math.random() < 0.55 ? 1 : 0) + (Math.random() < 0.25 ? 1 : 0);
      let linked = 0;
      for (const nb of neighbors) {
        if (linked >= linkCount) break;
        if (nb.id < hubId) continue;
        // Short biological range — no long decorative arcs.
        if (nb.dist > densityScale * 0.38) continue;
        const edgeIdx = this._addCoreEdge(nodes, hubId, nb.id, {
          opacity: rand(0.12, 0.36),
          targetOpacity: rand(0.18, 0.48),
          curveStrength: rand(0.2, 0.45),
          width: rand(0.18, 0.58),
        });
        if (edgeIdx >= 0) {
          this.branchEdgeIndices.push(edgeIdx);
          linked++;
        }
      }
    }

    // Sparse short feeders into surrounding field — blend, never radial explosion.
    const branchTargets = this._findBranchTargets(nodes, worldWidth, worldHeight, cfg.branchCount);
    const outerHubs = hubsOnly
      .map((id) => {
        const n = nodes.nodes[id];
        const dx = n.x - focusX;
        const dy = n.y - focusY;
        return { id, dist: Math.sqrt(dx * dx + dy * dy) };
      })
      .sort((a, b) => b.dist - a.dist)
      .slice(0, Math.min(36, hubsOnly.length));

    for (const { id: hubId } of outerHubs) {
      const hub = nodes.nodes[hubId];
      if (!hub) continue;
      let linked = 0;
      for (const targetId of branchTargets) {
        if (linked >= 3) break;
        const target = nodes.nodes[targetId];
        if (!target) continue;
        const dx = target.x - hub.x;
        const dy = target.y - hub.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > densityScale * 2.8 || dist < densityScale * 0.15) continue;
        const edgeIdx = this._addCoreEdge(nodes, hubId, targetId, {
          opacity: rand(0.05, 0.16),
          targetOpacity: rand(0.08, 0.22),
          curveStrength: rand(0.24, 0.48),
          width: rand(0.16, 0.38),
        });
        if (edgeIdx >= 0) {
          this.branchEdgeIndices.push(edgeIdx);
          linked++;
        }
      }
    }

    // Continuous field: dense-region tissue + full-canvas atmospheric tissue.
    const allTissue = buildCoreTissue(this.cx, this.cy, densityScale);
    // Partition once — avoid per-frame sorts for depth layers.
    this.filaments = [];
    this.filamentsFront = [];
    const tierOrder = { deep: 0, mid: 1, labelBack: 2, near: 3, bright: 4, front: 5 };
    allTissue.sort((a, b) => (tierOrder[a.depthTier] ?? 2) - (tierOrder[b.depthTier] ?? 2));
    for (const strand of allTissue) {
      if (strand.depthTier === "front" || strand.band === "front") {
        this.filamentsFront.push(strand);
      } else {
        this.filaments.push(strand);
      }
    }
    this.fieldTissue = buildFieldTissue(worldWidth, worldHeight, this.cx, this.cy, densityScale);

    // Microscopic neurons — denser near focus (Core gravity), continuum into mid-field.
    const microCount = cfg.microNeuronCount ?? 1200;
    for (let i = 0; i < microCount; i++) {
      const angle = rand(0, Math.PI * 2) + i * 0.07;
      // Stronger Core attraction — more mass near focus, soft falloff to borders.
      const spread = Math.pow(Math.random(), 1.55);
      const stretchX = 1.22 + Math.sin(i * 0.33) * 0.4;
      const stretchY = 0.7 + Math.cos(i * 0.41) * 0.34;
      // ~10% spill into far field so density has no hard edge.
      const reach = Math.random() < 0.1 ? rand(2.1, 3.6) : rand(0.015, 1.95);
      const dist = densityScale * spread * reach;
      const proximity = 1 - Math.min(1, dist / (densityScale * 2.0));
      this.microNeurons.push({
        x: focusX + Math.cos(angle) * dist * stretchX + rand(-densityScale * 0.06, densityScale * 0.06),
        y: focusY + Math.sin(angle) * dist * stretchY + rand(-densityScale * 0.06, densityScale * 0.06),
        r: rand(0.12, 0.95) * (0.8 + proximity * 0.45),
        a: rand(0.18, 0.78) * (0.5 + proximity * 0.7) * (1 - spread * 0.22),
        phase: rand(0, Math.PI * 2),
      });
    }

    // Local packets only — orbit nucleus or ride near-Core filaments (fixed budget).
    const packetCount = cfg.energyPacketCount ?? 28;
    const orbitCount = Math.floor(packetCount * (cfg.orbitPacketRatio ?? 0.45));
    const filamentLen = this.filaments.length;
    for (let i = 0; i < orbitCount; i++) {
      this.energyPackets.push({
        kind: "orbit",
        angle: rand(0, Math.PI * 2),
        radius: densityScale * rand(0.028, 0.1),
        speed: rand(0.0004, 0.00125),
        stretchX: rand(1.2, 1.6),
        stretchY: rand(0.48, 0.75),
        r: rand(0.55, 1.15),
        a: rand(0.35, 0.62),
        phase: rand(0, Math.PI * 2),
      });
    }
    for (let i = orbitCount; i < packetCount && filamentLen > 0; i++) {
      this.energyPackets.push({
        kind: "filament",
        filamentIndex: Math.floor(Math.random() * filamentLen),
        t: Math.random(),
        speed: rand(0.01, 0.032),
        r: rand(0.45, 1.1),
        a: rand(0.2, 0.42),
        phase: rand(0, Math.PI * 2),
      });
    }
  }

  /**
   * @param {import("./nodes.js").NeuralNodes} nodes
   * @param {number} a
   * @param {number} b
   * @param {object} opts
   */
  _addCoreEdge(nodes, a, b, opts) {
    const na = nodes.nodes[a];
    const nb = nodes.nodes[b];
    if (!na || !nb) return -1;
    const controls = buildOrganicControls(na, nb, opts.curveStrength ?? 0.32, Math.random(), {
      radial: false,
      maxBendRatio: 0.38,
      tangle: Math.random() < 0.35,
    });
    const edgeIdx = nodes._addEdge(a, b, {
      opacity: opts.opacity,
      targetOpacity: opts.targetOpacity,
      visible: true,
      isCore: true,
      curveStrength: opts.curveStrength,
      width: opts.width,
      ...controls,
    });
    return edgeIdx;
  }

  /**
   * @param {number} id
   * @param {number} x
   * @param {number} y
   * @param {number} radius
   * @param {boolean} isCenter
   */
  _createHubNode(id, x, y, radius, isCenter) {
    const fgLayer = NEURAL_CONFIG.layers.length - 1;
    const layer = NEURAL_CONFIG.layers[fgLayer];
    return {
      id,
      x,
      y,
      vx: rand(-0.0025, 0.0025),
      vy: rand(-0.0025, 0.0025),
      radius: isCenter ? radius * 0.7 : radius * rand(0.45, 0.9),
      layer: fgLayer,
      depth: layer.depth,
      parallax: layer.parallax,
      z: layer.z,
      baseOpacity: isCenter ? 0.72 : 0.48,
      opacity: isCenter ? 0.72 : 0.48,
      pulse: rand(0, Math.PI * 2),
      pulseSpeed: rand(0.0035, 0.011),
      glow: isCenter ? 0.85 : 0.26,
      activation: isCenter ? 0.55 : 0.18,
      nodeClass: NODE_CLASSES.CORE,
      signalColorKey: "redGlow",
      isHub: true,
      isCenter,
      redHue: isCenter ? 0.98 : rand(0.65, 0.95),
      brightness: isCenter ? 1.15 : rand(0.55, 0.88),
      energy: isCenter ? 0.92 : 0.45,
      temperature: isCenter ? 0.88 : 0.42,
      activity: isCenter ? 0.62 : 0.24,
      connectionCount: 0,
      state: "core",
    };
  }

  /**
   * @param {import("./nodes.js").NeuralNodes} nodes
   * @param {number} worldWidth
   * @param {number} worldHeight
   * @param {number} count
   */
  _findBranchTargets(nodes, worldWidth, worldHeight, count) {
    const cfg = NEURAL_CONFIG.core;
    const densityScale = Math.min(worldWidth, worldHeight) * cfg.clusterRadiusRatio;
    const asym = cfg.asymmetry || {};
    const focusX = this.cx + densityScale * (asym.x ?? -0.12);
    const focusY = this.cy + densityScale * (asym.y ?? 0.08);
    const candidates = [];

    for (let i = 0; i < nodes.nodes.length; i++) {
      const n = nodes.nodes[i];
      if (n.isHub) continue;
      const dx = n.x - focusX;
      const dy = n.y - focusY;
      const dist = Math.sqrt(dx * dx + dy * dy);
      // Soft annulus — wide blend zone (no hard wall between core and field).
      if (dist > densityScale * 0.4 && dist < densityScale * 3.6) {
        candidates.push({ id: i, dist });
      }
    }

    candidates.sort((a, b) => a.dist - b.dist);
    const picked = [];
    const step = Math.max(1, Math.floor(candidates.length / count));
    for (let i = 0; i < candidates.length && picked.length < count; i += step) {
      picked.push(candidates[i].id);
    }
    return picked;
  }

  /** @param {number} deltaMs @param {import("./state.js").NeuralState} state */
  update(deltaMs, state) {
    const cfg = NEURAL_CONFIG.core;
    const intensity = state.getIntensity();
    const thinking = state.isThinking();
    const breathe = state.getBreathe();

    this.breathePhase += cfg.breatheSpeed * deltaMs * (thinking ? 1.2 : 1);
    // Slow expand / contract / light pulse — premium, almost imperceptible.
    this.pulse =
      0.78 +
      Math.sin(this.breathePhase) * cfg.pulseAmplitude +
      Math.sin(this.breathePhase * 0.5) * (cfg.pulseAmplitude * 0.35) +
      breathe * 0.06 +
      intensity * (thinking ? 0.14 : 0.06);

    updateTissue(this.filaments, deltaMs, thinking);
    updateTissue(this.filamentsFront, deltaMs, thinking);
    updateTissue(this.fieldTissue, deltaMs, thinking);

    for (const m of this.microNeurons) {
      m.phase += deltaMs * 0.00032 * (thinking ? 1.25 : 1);
    }

    for (const p of this.energyPackets) {
      if (p.kind === "orbit") {
        p.angle += p.speed * deltaMs * (thinking ? 1.35 : 1);
        p.phase += deltaMs * 0.0008;
      }
    }

    return this.pulse;
  }

  /** @returns {{ cx: number, cy: number, pulse: number, intensity: number }} */
  getDrawState(intensity, thinking) {
    return {
      cx: this.cx,
      cy: this.cy,
      pulse: this.pulse,
      intensity: intensity * (thinking ? 1.35 : 1),
    };
  }
}
