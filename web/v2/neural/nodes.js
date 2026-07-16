/** Titan Neural Renderer V3 — Dense neuron graph · Neural Architecture Reconstruction. */

import { NEURAL_CONFIG } from "./config.js";
import { buildOrganicControls } from "./bezier.js";
import { NeuralCore } from "./core.js";
import {
  NODE_CLASSES,
  REGION_ANCHORS,
  assignNodeClass,
  createNodeVitality,
  getSignalColorKey,
} from "./node-classes.js";
import { computeNodeCount, rand } from "./utils.js";

export class NeuralNodes {
  /**
   * @param {import("./camera.js").NeuralCamera} camera
   */
  constructor(camera) {
    this.camera = camera;
    /** @type {Array<object>} */
    this.nodes = [];
    /** @type {Array<object>} */
    this.edges = [];
    this.lastNewConnection = 0;
    this.density = NEURAL_CONFIG.nodes.densityDefault;
    this.maxNodeCount = NEURAL_CONFIG.nodes.maxCount;
    this.core = new NeuralCore();
    /** @type {Map<number, number[]>} */
    this._spatialGrid = new Map();
    this._gridCellSize = 1;
    /** @type {Array<{ x: number, y: number, r: number }>} */
    this._clusterSeeds = [];
    /** @type {Array<{ x: number, y: number, r: number }>} */
    this._microSeeds = [];
    /** @type {Array<{ x: number, y: number, r: number }>} */
    this._voidZones = [];
    /** Cached per-layer node lists — rebuilt only with geometry. */
    /** @type {Array<object[]> | null} */
    this._nodesByLayer = null;
  }

  /** @param {number} density */
  setDensity(density) {
    this.density = density || NEURAL_CONFIG.nodes.densityDefault;
  }

  /** @param {number} maxCount */
  setMaxNodeCount(maxCount) {
    this.maxNodeCount = Math.max(400, maxCount || NEURAL_CONFIG.nodes.maxCount);
  }

  /** @param {number} viewportWidth @param {number} viewportHeight @param {number} [densityScale] */
  build(viewportWidth, viewportHeight, densityScale = 1) {
    const count = Math.floor(
      computeNodeCount(viewportWidth, viewportHeight, this.density, this.maxNodeCount) *
        densityScale,
    );
    const bounds = this.camera.getWorldBounds();
    const layers = NEURAL_CONFIG.layers;
    const nodeCfg = NEURAL_CONFIG.nodes;

    this.nodes = [];
    this.edges = [];
    this._clusterSeeds = [];
    this._microSeeds = [];
    this._voidZones = [];

    const coreCfg = NEURAL_CONFIG.core;
    const cxWorld = bounds.width * coreCfg.xRatio;
    const cyWorld = bounds.height * coreCfg.yRatio;
    const clusterMaxR = Math.min(bounds.width, bounds.height) * 0.58;
    this._seedClusters(bounds, cxWorld, cyWorld);
    this._seedMicroClusters(bounds);

    const sizeVar = nodeCfg.sizeVariance ?? 1.4;

    for (let i = 0; i < count; i++) {
      const layerIdx = this._pickLayer(layers);
      const layer = layers[layerIdx];
      const { x: wx, y: wy } = this._samplePosition(bounds, cxWorld, cyWorld, clusterMaxR);
      const nodeClass = assignNodeClass(wx, wy, bounds.width, bounds.height, layerIdx);
      const vitality = createNodeVitality(nodeClass);
      const isHub = Math.random() < nodeCfg.hubRatio && layerIdx >= layers.length - 2;
      const sizeRoll = Math.pow(Math.random(), 0.65);

      this.nodes.push({
        id: i,
        x: wx,
        y: wy,
        vx: rand(nodeCfg.driftSpeedMin, nodeCfg.driftSpeedMax) * layer.driftMult * (Math.random() > 0.5 ? 1 : -1),
        vy: rand(nodeCfg.driftSpeedMin, nodeCfg.driftSpeedMax) * layer.driftMult * (Math.random() > 0.5 ? 1 : -1),
        radius: isHub
          ? rand(layer.radiusMax * 1.15, layer.radiusMax * 1.75)
          : rand(layer.radiusMin, layer.radiusMax) * (0.55 + sizeRoll * sizeVar * 0.55),
        layer: layerIdx,
        depth: layer.depth,
        parallax: layer.parallax,
        z: layer.z,
        baseOpacity: layer.baseOpacity * (isHub ? 1.35 : rand(0.72, 1.18)),
        opacity: layer.baseOpacity,
        pulse: rand(0, Math.PI * 2),
        pulseSpeed: rand(nodeCfg.pulseSpeedMin, nodeCfg.pulseSpeedMax),
        glow: 0,
        activation: 0,
        nodeClass,
        signalColorKey: getSignalColorKey(nodeClass),
        isHub,
        isCenter: false,
        redHue: rand(0.5, 1.0),
        brightness: rand(0.55, 1.15),
        ...vitality,
      });
    }

    this.core.build(this, bounds.width, bounds.height);
    this._rebuildSpatialGrid(viewportWidth, viewportHeight);
    this._buildEdges(viewportWidth, viewportHeight, 1);
    this._cacheNodesByLayer();
  }

  _cacheNodesByLayer() {
    const layerCount = NEURAL_CONFIG.layers.length;
    /** @type {Array<object[]>} */
    const byLayer = Array.from({ length: layerCount }, () => []);
    for (const n of this.nodes) {
      if (n.isCenter) continue;
      const layer = Math.max(0, Math.min(layerCount - 1, n.layer | 0));
      byLayer[layer].push(n);
    }
    for (const list of byLayer) {
      list.sort((a, b) => a.z - b.z);
    }
    this._nodesByLayer = byLayer;
  }

  /** @param {number} layer */
  getNodesForLayer(layer) {
    if (!this._nodesByLayer) this._cacheNodesByLayer();
    return this._nodesByLayer?.[layer] ?? [];
  }

  /**
   * Sample organic position for galactic composition (Phase 5.2):
   * dense galaxy cores, sparse field, intentional void rejection.
   * @param {{ width: number, height: number }} bounds
   * @param {number} cx @param {number} cy @param {number} maxR
   * @returns {{ x: number, y: number }}
   */
  _samplePosition(bounds, cx, cy, maxR) {
    const nodeCfg = NEURAL_CONFIG.nodes;
    const roll = Math.random();
    const power = nodeCfg.clusterPower ?? 1.45;
    const asym = NEURAL_CONFIG.core?.asymmetry || {};
    const focusX = cx + maxR * (asym.x ?? -0.12);
    const focusY = cy + maxR * (asym.y ?? 0.08);

    // Dense cognitive peak — elongated gravity well (Core).
    if (roll < (nodeCfg.coreClusterChance ?? 0.28)) {
      const angle = Math.random() * Math.PI * 2 + rand(-0.4, 0.4);
      const spread = Math.pow(Math.random(), power);
      const stretchX = 1.28 + Math.sin(angle * 2.1) * 0.42;
      const stretchY = 0.68 + Math.cos(angle * 1.7) * 0.34;
      const radius = spread * maxR * rand(0.08, 1.35);
      return this._clampAwayFromVoids(
        focusX + Math.cos(angle) * radius * stretchX + (Math.random() - 0.5) * bounds.width * 0.035,
        focusY + Math.sin(angle) * radius * stretchY + (Math.random() - 0.5) * bounds.height * 0.035,
        bounds,
      );
    }

    // Regional / satellite colonies — elliptical masses, not circles.
    if (roll < (nodeCfg.coreClusterChance ?? 0.28) + (nodeCfg.regionClusterChance ?? 0.42)) {
      if (this._clusterSeeds.length === 0) this._seedClusters(bounds, focusX, focusY);
      const seed = this._clusterSeeds[Math.floor(Math.random() * this._clusterSeeds.length)];
      const angle = Math.random() * Math.PI * 2;
      const spread = Math.pow(Math.random(), 1.55);
      const radius = spread * seed.r * rand(0.08, 1.05);
      const sx = seed.stretchX ?? 1.15;
      const sy = seed.stretchY ?? 0.9;
      return this._clampAwayFromVoids(
        seed.x + Math.cos(angle) * radius * sx + (Math.random() - 0.5) * seed.r * 0.28,
        seed.y + Math.sin(angle) * radius * sy + (Math.random() - 0.5) * seed.r * 0.28,
        bounds,
      );
    }

    // Microscopic local neurons inside galaxies.
    if (
      roll <
      (nodeCfg.coreClusterChance ?? 0.28) +
        (nodeCfg.regionClusterChance ?? 0.42) +
        (nodeCfg.microClusterChance ?? 0.22)
    ) {
      if (this._microSeeds.length === 0) this._seedMicroClusters(bounds);
      const seed = this._microSeeds[Math.floor(Math.random() * this._microSeeds.length)];
      const angle = Math.random() * Math.PI * 2;
      const radius = Math.pow(Math.random(), 1.25) * seed.r;
      return this._clampAwayFromVoids(
        seed.x + Math.cos(angle) * radius + (Math.random() - 0.5) * seed.r * 0.3,
        seed.y + Math.sin(angle) * radius + (Math.random() - 0.5) * seed.r * 0.3,
        bounds,
      );
    }

    // Sparse field scatter — rare, preserves breathing darkness.
    if (Math.random() < (nodeCfg.sparseFieldChance ?? 0.08)) {
      return this._clampAwayFromVoids(
        rand(bounds.width * 0.05, bounds.width * 0.95),
        rand(bounds.height * 0.05, bounds.height * 0.95),
        bounds,
      );
    }

    // Fallback into a galaxy seed rather than filling voids.
    if (this._clusterSeeds.length === 0) this._seedClusters(bounds, focusX, focusY);
    const fallback = this._clusterSeeds[Math.floor(Math.random() * this._clusterSeeds.length)];
    const fa = Math.random() * Math.PI * 2;
    const fr = Math.pow(Math.random(), 1.2) * fallback.r;
    return this._clampAwayFromVoids(
      fallback.x + Math.cos(fa) * fr,
      fallback.y + Math.sin(fa) * fr,
      bounds,
    );
  }

  /** @param {{ width: number, height: number }} bounds @param {number} cx @param {number} cy */
  _seedClusters(bounds, cx, cy) {
    this._clusterSeeds = [];
    const arch = NEURAL_CONFIG.architecture?.colonies || [];
    const minDim = Math.min(bounds.width, bounds.height);

    // Named major colonies — sized / stretched islands (civilization map).
    if (arch.length) {
      for (const d of arch) {
        const isCore = d.id === "core";
        const x = isCore
          ? cx + rand(-bounds.width * 0.02, bounds.width * 0.015)
          : d.x * bounds.width + rand(-bounds.width * 0.015, bounds.width * 0.015);
        const y = isCore
          ? cy + rand(-bounds.height * 0.015, bounds.height * 0.02)
          : d.y * bounds.height + rand(-bounds.height * 0.015, bounds.height * 0.015);
        this._clusterSeeds.push({
          x,
          y,
          r: (isCore ? minDim * 0.2 : minDim * (d.r ?? 0.09)) * rand(0.95, 1.2) * (d.density ?? 1),
          stretchX: d.stretchX ?? 1.1,
          stretchY: d.stretchY ?? 0.9,
          mass: d.mass ?? 1,
          id: d.id,
        });
      }
    } else {
      this._clusterSeeds = Object.values(REGION_ANCHORS).map((a) => ({
        x: a.x * bounds.width + rand(-bounds.width * 0.04, bounds.width * 0.04),
        y: a.y * bounds.height + rand(-bounds.height * 0.04, bounds.height * 0.04),
        r: minDim * a.radius * rand(0.85, 1.45),
        stretchX: 1.15,
        stretchY: 0.9,
      }));
    }

    // Small local pockets only near colony masses — never a uniform lattice.
    const pocketCount = NEURAL_CONFIG.nodes.localPocketCount ?? 12;
    for (let i = 0; i < pocketCount && this._clusterSeeds.length; i++) {
      const host = this._clusterSeeds[i % this._clusterSeeds.length];
      const angle = rand(0, Math.PI * 2);
      const dist = host.r * rand(0.15, 0.95);
      const sx = host.stretchX ?? 1.15;
      const sy = host.stretchY ?? 0.9;
      this._clusterSeeds.push({
        x: host.x + Math.cos(angle) * dist * sx,
        y: host.y + Math.sin(angle) * dist * sy,
        r: minDim * rand(0.016, 0.055),
        stretchX: sx,
        stretchY: sy,
      });
    }

    this._seedVoids(bounds, cx, cy);
  }

  /**
   * Intentional dark breathing spaces between colony islands.
   * @param {{ width: number, height: number }} bounds
   * @param {number} cx @param {number} cy
   */
  _seedVoids(bounds, cx, cy) {
    /** @type {Array<{ x: number, y: number, r: number }>} */
    this._voidZones = [];
    const count = NEURAL_CONFIG.nodes.voidCount ?? 7;
    const voidCfg = NEURAL_CONFIG.architecture?.voids || {};
    const rMin = voidCfg.radiusMinRatio ?? 0.12;
    const rMax = voidCfg.radiusMaxRatio ?? 0.26;
    const minDim = Math.min(bounds.width, bounds.height);

    // Interstitial voids between first-ring colony seeds for visual rhythm.
    const hosts = this._clusterSeeds.slice(0, Math.min(8, this._clusterSeeds.length));
    for (let i = 0; i < hosts.length && this._voidZones.length < count; i++) {
      const a = hosts[i];
      const b = hosts[(i + 1) % hosts.length];
      const x = (a.x + b.x) * 0.5 + (cx - (a.x + b.x) * 0.5) * -0.15;
      const y = (a.y + b.y) * 0.5 + (cy - (a.y + b.y) * 0.5) * -0.15;
      const r = minDim * rand(rMin, rMax);
      const dx = x - cx;
      const dy = y - cy;
      if (Math.sqrt(dx * dx + dy * dy) < minDim * 0.22) continue;
      let clear = true;
      for (const seed of this._clusterSeeds) {
        const sx = x - seed.x;
        const sy = y - seed.y;
        if (Math.sqrt(sx * sx + sy * sy) < seed.r * 0.8 + r * 0.65) {
          clear = false;
          break;
        }
      }
      if (!clear) continue;
      this._voidZones.push({ x, y, r });
    }

    let attempts = 0;
    while (this._voidZones.length < count && attempts < count * 22) {
      attempts++;
      const x = rand(bounds.width * 0.1, bounds.width * 0.9);
      const y = rand(bounds.height * 0.12, bounds.height * 0.88);
      const r = minDim * rand(rMin, rMax);
      const dx = x - cx;
      const dy = y - cy;
      if (Math.sqrt(dx * dx + dy * dy) < minDim * 0.24) continue;
      let clear = true;
      for (const seed of this._clusterSeeds) {
        const sx = x - seed.x;
        const sy = y - seed.y;
        if (Math.sqrt(sx * sx + sy * sy) < seed.r + r * 0.55) {
          clear = false;
          break;
        }
      }
      if (!clear) continue;
      this._voidZones.push({ x, y, r });
    }
  }

  /** @param {{ width: number, height: number }} bounds */
  _seedMicroClusters(bounds) {
    this._microSeeds = [];
    const base = NEURAL_CONFIG.nodes.microSeedCount ?? 72;
    const count = base + Math.floor(Math.random() * 24);
    // Micro neurons live inside galaxies — not uniform scatter.
    for (let i = 0; i < count; i++) {
      if (this._clusterSeeds.length === 0) {
        this._microSeeds.push({
          x: rand(bounds.width * 0.2, bounds.width * 0.8),
          y: rand(bounds.height * 0.2, bounds.height * 0.8),
          r: Math.min(bounds.width, bounds.height) * rand(0.01, 0.035),
        });
        continue;
      }
      const host = this._clusterSeeds[Math.floor(Math.random() * this._clusterSeeds.length)];
      const a = rand(0, Math.PI * 2);
      const d = Math.pow(Math.random(), 1.3) * host.r * rand(0.15, 1.05);
      this._microSeeds.push({
        x: host.x + Math.cos(a) * d,
        y: host.y + Math.sin(a) * d,
        r: Math.min(bounds.width, bounds.height) * rand(0.008, 0.028),
      });
    }
  }

  /**
   * @param {number} x @param {number} y
   * @param {{ width: number, height: number }} bounds
   */
  _clampAwayFromVoids(x, y, bounds) {
    const pos = this._clampPos(x, y, bounds);
    const voids = this._voidZones || [];
    for (let attempt = 0; attempt < 6; attempt++) {
      let hit = null;
      for (const v of voids) {
        const dx = pos.x - v.x;
        const dy = pos.y - v.y;
        if (dx * dx + dy * dy < v.r * v.r * 0.82) {
          hit = v;
          break;
        }
      }
      if (!hit) break;
      const dx = pos.x - hit.x || 0.001;
      const dy = pos.y - hit.y || 0.001;
      const len = Math.sqrt(dx * dx + dy * dy) || 1;
      pos.x = hit.x + (dx / len) * hit.r * 1.08;
      pos.y = hit.y + (dy / len) * hit.r * 1.08;
      const clamped = this._clampPos(pos.x, pos.y, bounds);
      pos.x = clamped.x;
      pos.y = clamped.y;
    }
    return pos;
  }

  /** @param {number} x @param {number} y @param {{ width: number, height: number }} bounds */
  _clampPos(x, y, bounds) {
    return {
      x: Math.max(0, Math.min(bounds.width, x)),
      y: Math.max(0, Math.min(bounds.height, y)),
    };
  }

  /** @param {number} viewportWidth @param {number} viewportHeight */
  _rebuildSpatialGrid(viewportWidth, viewportHeight) {
    const worldCfg = NEURAL_CONFIG.world;
    this._gridCellSize =
      Math.min(viewportWidth, viewportHeight) * worldCfg.connectionMaxDistRatio;
    this._spatialGrid.clear();

    for (let i = 0; i < this.nodes.length; i++) {
      const n = this.nodes[i];
      const key = this._cellKey(n.x, n.y);
      if (!this._spatialGrid.has(key)) this._spatialGrid.set(key, []);
      this._spatialGrid.get(key).push(i);
    }
  }

  /** @param {number} x @param {number} y */
  _cellKey(x, y) {
    const cs = this._gridCellSize || 1;
    return `${Math.floor(x / cs)},${Math.floor(y / cs)}`;
  }

  /** @param {number} wx @param {number} wy @param {number} maxDist */
  _getNearbyCandidates(wx, wy, maxDist) {
    const cs = this._gridCellSize || maxDist;
    const cx = Math.floor(wx / cs);
    const cy = Math.floor(wy / cs);
    const result = [];
    const cellRadius = Math.ceil(maxDist / cs);

    for (let dx = -cellRadius; dx <= cellRadius; dx++) {
      for (let dy = -cellRadius; dy <= cellRadius; dy++) {
        const key = `${cx + dx},${cy + dy}`;
        const cell = this._spatialGrid.get(key);
        if (cell) result.push(...cell);
      }
    }
    return result;
  }

  /** @param {object} n @param {{ width: number, height: number }} bounds */
  _wrapNode(n, bounds) {
    const margin = NEURAL_CONFIG.infiniteSpace.wrapMargin || 40;
    const spanX = bounds.width + margin * 2;
    const spanY = bounds.height + margin * 2;
    if (n.x < -margin) n.x += spanX;
    if (n.x > bounds.width + margin) n.x -= spanX;
    if (n.y < -margin) n.y += spanY;
    if (n.y > bounds.height + margin) n.y -= spanY;
  }

  /** @param {number} layerIdx */
  _isDeepLayer(layerIdx) {
    return layerIdx <= 1;
  }

  /** @param {number} layerIdx */
  _isForegroundLayer(layerIdx) {
    return layerIdx >= NEURAL_CONFIG.layers.length - 2;
  }

  /** @param {typeof NEURAL_CONFIG.layers} layers */
  _pickLayer(layers) {
    const roll = Math.random();
    let cumulative = 0;
    for (let i = 0; i < layers.length; i++) {
      cumulative += layers[i].weight;
      if (roll <= cumulative) return i;
    }
    return layers.length - 1;
  }

  /**
   * @param {number} aIdx
   * @param {number} bIdx
   * @param {object} [opts]
   * @returns {number}
   */
  _addEdge(aIdx, bIdx, opts = {}) {
    if (aIdx === bIdx) return -1;
    const na = this.nodes[aIdx];
    const nb = this.nodes[bIdx];
    if (!na || !nb) return -1;

    const layerMix = Math.round((na.layer + nb.layer) / 2);
    const layerCfg = NEURAL_CONFIG.layers[layerMix] ?? NEURAL_CONFIG.layers[2];
    const curveStrength =
      opts.curveStrength ??
      NEURAL_CONFIG.world.organicCurveStrength * (0.45 + Math.random() * 0.7);
    const controls =
      opts.cp1x != null && opts.cp2x != null
        ? {
            cp1x: opts.cp1x,
            cp1y: opts.cp1y,
            cp2x: opts.cp2x,
            cp2y: opts.cp2y,
          }
        : buildOrganicControls(na, nb, curveStrength, Math.random(), {
            radial: false,
            maxBendRatio: opts.isCore ? 0.55 : 0.48,
            tangle: Boolean(opts.isCore) || Math.random() < 0.35,
          });

    const edgeIdx = this.edges.length;
    this.edges.push({
      a: aIdx,
      b: bIdx,
      opacity: opts.opacity ?? rand(0.04, 0.22),
      targetOpacity: opts.targetOpacity ?? rand(0.08, 0.28),
      fadeSpeed: rand(0.0018, 0.006),
      visible: opts.visible !== false,
      glow: 0,
      signalProgress: -1,
      layerMix,
      edgeOpacity: layerCfg.edgeOpacity ?? 0.7,
      signalColorKey: na.signalColorKey,
      isCore: Boolean(opts.isCore),
      isDendrite: opts.isCore ? false : Math.random() < NEURAL_CONFIG.world.dendriteBranchChance,
      width: opts.width ?? rand(0.35, 1.1) * (layerCfg.z ?? 0.5),
      ...controls,
    });

    na.connectionCount++;
    nb.connectionCount++;
    return edgeIdx;
  }

  /**
   * @param {number} viewportWidth
   * @param {number} viewportHeight
   * @param {number} connectionScale
   */
  _buildEdges(viewportWidth, viewportHeight, connectionScale) {
    const worldCfg = NEURAL_CONFIG.world;
    const maxDist = Math.min(viewportWidth, viewportHeight) * worldCfg.connectionMaxDistRatio;
    const prob = worldCfg.connectionProbability * connectionScale;
    /** @type {Record<number, number>} */
    const connectionCounts = {};

    for (let a = 0; a < this.nodes.length; a++) {
      connectionCounts[a] = 0;
    }

    for (let i = 0; i < this.nodes.length; i++) {
      if (this.nodes[i].isCenter) continue;

      const na = this.nodes[i];
      const candidates = [];

      for (const j of this._getNearbyCandidates(na.x, na.y, maxDist)) {
        if (j <= i) continue;
        const nb = this.nodes[j];
        const dx = na.x - nb.x;
        const dy = na.y - nb.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        // Only connect within adjacent depth layers — large parallax gaps
        // between endpoints are what stretched edges across the viewport.
        if (dist < maxDist && Math.abs(na.layer - nb.layer) <= 1) {
          candidates.push({ index: j, dist });
        }
      }

      candidates.sort((a, b) => a.dist - b.dist);

      for (const cand of candidates) {
        if (connectionCounts[i] >= worldCfg.maxConnectionsPerNode) break;
        if (connectionCounts[cand.index] >= worldCfg.maxConnectionsPerNode) continue;
        if (Math.random() < prob) {
          this._addEdge(i, cand.index);
          connectionCounts[i]++;
          connectionCounts[cand.index]++;
        }
      }
    }

    this._spawnDendriteBranches(maxDist);
  }

  /** @param {number} maxDist */
  _spawnDendriteBranches(maxDist) {
    const branchChance = NEURAL_CONFIG.world.dendriteBranchChance ?? 0.28;
    const branchCandidates = this.edges.filter(
      (e) => e.visible && !e.isCore && Math.random() < branchChance,
    );
    for (const parent of branchCandidates.slice(0, 520)) {
      const na = this.nodes[parent.a];
      const nb = this.nodes[parent.b];
      if (!na || !nb) continue;
      const midX = (na.x + nb.x) * 0.5 + (Math.random() - 0.5) * maxDist * 0.25;
      const midY = (na.y + nb.y) * 0.5 + (Math.random() - 0.5) * maxDist * 0.25;
      let nearest = -1;
      let nearestDist = maxDist * 0.55;
      for (const j of this._getNearbyCandidates(midX, midY, nearestDist)) {
        if (j === parent.a || j === parent.b) continue;
        const n = this.nodes[j];
        const dx = n.x - midX;
        const dy = n.y - midY;
        const d = Math.sqrt(dx * dx + dy * dy);
        if (d < nearestDist) {
          nearestDist = d;
          nearest = j;
        }
      }
      if (nearest >= 0) {
        this._addEdge(parent.b, nearest, {
          opacity: rand(0.02, 0.12),
          targetOpacity: rand(0.05, 0.18),
          visible: Math.random() > 0.22,
          curveStrength: rand(0.32, 0.62),
        });
      }
    }
  }

  /** @param {number} timestamp @param {number} intensity @param {number} [connScale] */
  trySpawnConnection(timestamp, intensity, connScale = 1) {
    const worldCfg = NEURAL_CONFIG.world;
    const interval = intensity > 0.3 ? worldCfg.newConnectionInterval * 0.35 : worldCfg.newConnectionInterval;
    if (timestamp - this.lastNewConnection < interval) return;
    if (Math.random() > worldCfg.newConnectionChance * connScale) return;

    this.lastNewConnection = timestamp;
    if (this.edges.length === 0) return;

    const edge = this.edges[Math.floor(Math.random() * this.edges.length)];
    edge.visible = true;
    edge.opacity = 0.03;
    edge.targetOpacity = 0.12 + intensity * 0.32;
    edge.glow = 0.12 + intensity * 0.28;
  }

  /** @param {number} deltaMs @param {import("./state.js").NeuralState} state */
  update(deltaMs, state) {
    const bounds = this.camera.getWorldBounds();
    const breathe = state.getBreathe();
    const intensity = state.getIntensity();
    const thinking = state.isThinking();
    const signature = state.getCognitiveSignature?.() ?? null;
    const nodeMult = signature?.nodeActivityMult ?? 1;
    const unstable = Boolean(signature?.nodeInstability);
    const nodeCfg = NEURAL_CONFIG.nodes;
    const thinkCfg = NEURAL_CONFIG.thinking;
    const driftBoost = thinking ? thinkCfg.driftBoost : 1;
    const dt = deltaMs / 16.67;

    this.core.update(deltaMs, state);

    for (const n of this.nodes) {
      if (n.isCenter) {
        n.x = this.core.cx;
        n.y = this.core.cy;
        n.vx *= 0.92;
        n.vy *= 0.92;
      } else if (!n.isHub) {
        if (unstable && Math.random() < 0.018 * dt) {
          n.vx += (Math.random() - 0.5) * 0.0025;
          n.vy += (Math.random() - 0.5) * 0.0025;
          n.activation = Math.min(1, n.activation + 0.14);
        }
        n.x += n.vx * driftBoost * dt;
        n.y += n.vy * driftBoost * dt;
        this._wrapNode(n, bounds);
      } else {
        n.x += n.vx * dt * 0.35;
        n.y += n.vy * dt * 0.35;
        // Very soft leash — hubs may drift wider so density has no hard object edge.
        const asym = NEURAL_CONFIG.core?.asymmetry || {};
        const scale = Math.min(bounds.width, bounds.height) * NEURAL_CONFIG.core.clusterRadiusRatio;
        const focusX = this.core.cx + scale * (asym.x ?? -0.12);
        const focusY = this.core.cy + scale * (asym.y ?? 0.08);
        const dx = (n.x - focusX) / 1.35;
        const dy = (n.y - focusY) / 0.9;
        const maxR = scale * 3.2;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > maxR) {
          n.x = focusX + (dx / dist) * maxR * 1.35;
          n.y = focusY + (dy / dist) * maxR * 0.9;
        }
      }

      n.pulse += n.pulseSpeed * (thinking ? thinkCfg.activityBoost : 1) * nodeMult * dt;
      const pulseWave = (Math.sin(n.pulse) + 1) * 0.5;
      const breatheMod = 1 + (breathe - 0.5) * nodeCfg.breatheAmplitude;
      const glowMod = n.glow + n.activation * 0.65;
      const hubBoost = n.isHub ? 1.08 : n.isCenter ? 0.85 : 1;
      n.opacity = Math.min(
        0.98,
        (n.baseOpacity + pulseWave * (thinking ? 0.26 : 0.12) + glowMod * 0.45) * breatheMod * hubBoost,
      );

      n.energy = Math.min(1, n.energy * 0.997 + pulseWave * 0.003 + n.activation * 0.005);
      n.temperature = Math.max(0.05, n.temperature * 0.995 + (thinking ? 0.004 : 0.0015) * pulseWave);
      n.activity = Math.max(0, n.activation * 0.88 + n.glow * 0.45);
      n.state = n.isCenter ? "core" : thinking ? "thinking" : n.activity > 0.22 ? "active" : "idle";

      n.glow = Math.max(0, n.glow - NEURAL_CONFIG.signals.nodeGlowDecay * dt * (thinking ? 0.55 : 1));
      n.activation = Math.max(0, n.activation - NEURAL_CONFIG.signals.nodeGlowDecay * 0.65 * dt);
    }

    for (const e of this.edges) {
      if (!e.visible && Math.random() < 0.0006 * dt) {
        e.visible = true;
        e.opacity = 0.025;
        e.targetOpacity = rand(0.06, 0.18);
      }

      if (e.visible) {
        const diff = e.targetOpacity - e.opacity;
        e.opacity += diff * e.fadeSpeed * (thinking ? 2.0 : 1) * dt;
        if (Math.abs(diff) < 0.01) {
          e.targetOpacity = rand(0.05, thinking ? 0.32 : 0.2);
        }
        e.edgeOpacity = (e.edgeOpacity ?? 0.7) + Math.sin(Date.now() * 0.0009 + e.a * 0.27) * 0.015;
        e.edgeOpacity = Math.max(0.28, Math.min(1, e.edgeOpacity));
        if (e.opacity < 0.012 && e.targetOpacity < 0.035 && e.glow < 0.025) {
          e.visible = Math.random() > 0.55;
        }
      }

      e.glow = Math.max(0, e.glow - NEURAL_CONFIG.signals.edgeGlowDecay * dt);
      if (e.signalProgress >= 0) {
        e.glow = Math.max(e.glow, 0.42);
      }
    }
  }

  /**
   * @param {number} originId
   * @param {number} viewportWidth
   * @param {number} viewportHeight
   * @param {object} [options]
   */
  activateNearby(originId, viewportWidth, viewportHeight, options = {}) {
    if (originId === undefined || originId < 0 || originId >= this.nodes.length) return;

    const origin = this.nodes[originId];
    const radius =
      Math.min(viewportWidth, viewportHeight) *
      (options.radiusRatio ?? NEURAL_CONFIG.thinking.nearbyRadiusRatio);
    const glow = options.glow ?? NEURAL_CONFIG.thinking.nearbyGlow;
    const preferDeep = options.preferDeep ?? false;

    for (const j of this._getNearbyCandidates(origin.x, origin.y, radius)) {
      const n = this.nodes[j];
      if (preferDeep && !this._isDeepLayer(n.layer)) continue;
      const dx = n.x - origin.x;
      const dy = n.y - origin.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < radius) {
        const falloff = 1 - dist / radius;
        const layerBoost = preferDeep && this._isDeepLayer(n.layer) ? 1.4 : 1;
        n.activation = Math.max(n.activation, glow * falloff * layerBoost);
        n.glow = Math.max(n.glow, glow * falloff * 0.8 * layerBoost);
        n.temperature = Math.min(1, n.temperature + falloff * 0.14);
      }
    }
  }

  /**
   * Soft local brightening around a world point (execution / satellite regions).
   * Never flashes the whole field — falloff is spatial only.
   * @param {number} wx @param {number} wy
   * @param {object} [options]
   */
  activateWorldPoint(wx, wy, options = {}) {
    const radius =
      Math.min(this.camera.width, this.camera.height) *
      (options.radiusRatio ?? NEURAL_CONFIG.execution?.regionRadiusRatio ?? 0.14);
    const glow = options.glow ?? NEURAL_CONFIG.execution?.regionGlow ?? 0.55;

    for (const j of this._getNearbyCandidates(wx, wy, radius)) {
      const n = this.nodes[j];
      const dx = n.x - wx;
      const dy = n.y - wy;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist >= radius) continue;
      const falloff = 1 - dist / radius;
      n.activation = Math.max(n.activation, glow * falloff);
      n.glow = Math.max(n.glow, glow * falloff * 0.72);
    }
  }

  /** @param {number} id */
  getNode(id) {
    return this.nodes[id];
  }

  /**
   * @param {boolean} [preferForeground]
   * @param {number | null} [preferLayer]
   * @param {string} [preferClass]
   */
  getRandomNode(preferForeground, preferLayer, preferClass) {
    if (this.nodes.length === 0) return -1;

    if (preferClass) {
      const matches = this.nodes.filter((n) => n.nodeClass === preferClass && !n.isCenter).map((n) => n.id);
      if (matches.length > 0) {
        return matches[Math.floor(Math.random() * matches.length)];
      }
    }

    if (preferLayer !== undefined && preferLayer !== null) {
      const layerMatches = this.nodes.filter((n) => n.layer === preferLayer).map((n) => n.id);
      if (layerMatches.length > 0) {
        return layerMatches[Math.floor(Math.random() * layerMatches.length)];
      }
    }

    if (preferForeground) {
      const foreground = this.nodes
        .filter((n) => this._isForegroundLayer(n.layer) && !n.isCenter)
        .map((n) => n.id);
      if (foreground.length > 0) {
        return foreground[Math.floor(Math.random() * foreground.length)];
      }
    }

    if (preferForeground === false) {
      const background = this.nodes.filter((n) => this._isDeepLayer(n.layer)).map((n) => n.id);
      if (background.length > 0) {
        return background[Math.floor(Math.random() * background.length)];
      }
    }

    const pool = this.nodes.filter((n) => !n.isCenter);
    if (pool.length === 0) return 0;
    return pool[Math.floor(Math.random() * pool.length)].id;
  }

  getDeepRecallOrigin() {
    const deep = this.nodes.filter((n) => this._isDeepLayer(n.layer)).map((n) => n.id);
    if (deep.length === 0) return this.getRandomNode(false);
    return deep[Math.floor(Math.random() * deep.length)];
  }

  /** @param {number} nodeId */
  getEdgesForNode(nodeId) {
    const result = [];
    for (let i = 0; i < this.edges.length; i++) {
      const e = this.edges[i];
      if (e.a === nodeId || e.b === nodeId) {
        result.push({ edge: e, edgeIndex: i, other: e.a === nodeId ? e.b : e.a });
      }
    }
    return result;
  }

  getCoreNodes() {
    return this.nodes.filter((n) => n.nodeClass === NODE_CLASSES.CORE);
  }

  /** @param {string} regionId */
  getNodesInRegion(regionId) {
    const bounds = this.camera.getWorldBounds();
    return this.nodes.filter((n) => {
      const nx = n.x / bounds.width;
      const ny = n.y / bounds.height;
      return assignNodeClass(n.x, n.y, bounds.width, bounds.height, n.layer) !== NODE_CLASSES.IDLE;
    });
  }
}
