/** Titan Neural Renderer — Adaptive visual quality controller (Phase 11.P1). */

import { NEURAL_CONFIG } from "./config.js";
import { prefersReducedMotion } from "./utils.js";

export const QUALITY_STORAGE_KEY = "titan_visual_quality_mode";

/** @typedef {"performance" | "balanced" | "cinematic"} QualityMode */

/**
 * Approved cinematic ceilings live in NEURAL_CONFIG.
 * Modes scale draw/build budgets relative to those ceilings.
 */
export const QUALITY_PRESETS = Object.freeze({
  performance: Object.freeze({
    id: "performance",
    label: "Performance",
    maxDpr: 1.0,
    targetFps: 50,
    frameBudgetMs: 20,
    nodeDensityScale: 0.32,
    maxNodeCount: 3200,
    maxEdgesDrawn: 4200,
    maxTissueDrawn: 900,
    dustCount: 36,
    bokehCount: 0,
    filamentDrawScale: 0.35,
    microNeuronDrawScale: 0.28,
    ambientPatchCount: 2,
    bloomSpotCount: 1,
    fogPatchCount: 1,
    hazePatchCount: 1,
    enableBloom: true,
    enableBokeh: false,
    enableLensDiffusion: false,
    enableAtmosphericFog: false,
    enableVolumetricHaze: true,
    enableForegroundFog: false,
    enableLightShafts: false,
    softHaloFarLayers: false,
    nodeHaloEnabled: false,
    intersectionMarks: false,
    idleFrameSkip: 1,
    interactiveSkipDecorative: true,
    adaptive: false,
    rebuildGeometry: true,
  }),
  balanced: Object.freeze({
    id: "balanced",
    label: "Balanced",
    maxDpr: 1.25,
    targetFps: 55,
    frameBudgetMs: 18,
    nodeDensityScale: 0.55,
    maxNodeCount: 6500,
    maxEdgesDrawn: 10000,
    maxTissueDrawn: 1800,
    dustCount: 72,
    bokehCount: 10,
    filamentDrawScale: 0.62,
    microNeuronDrawScale: 0.55,
    ambientPatchCount: 3,
    bloomSpotCount: 2,
    fogPatchCount: 2,
    hazePatchCount: 2,
    enableBloom: true,
    enableBokeh: true,
    enableLensDiffusion: false,
    enableAtmosphericFog: true,
    enableVolumetricHaze: true,
    enableForegroundFog: false,
    enableLightShafts: false,
    softHaloFarLayers: false,
    nodeHaloEnabled: true,
    intersectionMarks: true,
    idleFrameSkip: 0,
    interactiveSkipDecorative: true,
    adaptive: true,
    rebuildGeometry: true,
  }),
  cinematic: Object.freeze({
    id: "cinematic",
    label: "Cinematic",
    maxDpr: 1.75,
    targetFps: 45,
    frameBudgetMs: 22,
    nodeDensityScale: 1.0,
    maxNodeCount: NEURAL_CONFIG.nodes.maxCount,
    maxEdgesDrawn: NEURAL_CONFIG.performance.maxEdgesDrawn,
    maxTissueDrawn: NEURAL_CONFIG.performance.maxTissueDrawn,
    dustCount: NEURAL_CONFIG.atmosphere.dustCount,
    bokehCount: NEURAL_CONFIG.atmosphere.foregroundBokehCount,
    filamentDrawScale: 1.0,
    microNeuronDrawScale: 1.0,
    ambientPatchCount: 6,
    bloomSpotCount: 5,
    fogPatchCount: 5,
    hazePatchCount: 3,
    enableBloom: true,
    enableBokeh: true,
    enableLensDiffusion: true,
    enableAtmosphericFog: true,
    enableVolumetricHaze: true,
    enableForegroundFog: true,
    enableLightShafts: Boolean(NEURAL_CONFIG.atmosphere.lightShaftStrength),
    softHaloFarLayers: true,
    nodeHaloEnabled: true,
    intersectionMarks: true,
    idleFrameSkip: 0,
    interactiveSkipDecorative: false,
    adaptive: false,
    rebuildGeometry: true,
  }),
});

/** Adaptive draw tiers applied inside Balanced (no geometry rebuild). */
const ADAPTIVE_TIERS = Object.freeze([
  Object.freeze({
    id: 0,
    label: "high",
    edgeScale: 1.0,
    tissueScale: 1.0,
    dustScale: 1.0,
    bokehScale: 1.0,
    filamentScale: 1.0,
    microScale: 1.0,
    effectMask: 0b1111,
  }),
  Object.freeze({
    id: 1,
    label: "mid",
    edgeScale: 0.72,
    tissueScale: 0.7,
    dustScale: 0.65,
    bokehScale: 0.5,
    filamentScale: 0.7,
    microScale: 0.65,
    effectMask: 0b0111,
  }),
  Object.freeze({
    id: 2,
    label: "low",
    edgeScale: 0.48,
    tissueScale: 0.48,
    dustScale: 0.4,
    bokehScale: 0,
    filamentScale: 0.45,
    microScale: 0.4,
    effectMask: 0b0011,
  }),
]);

/**
 * @returns {QualityMode}
 */
export function loadStoredQualityMode() {
  try {
    const raw = localStorage.getItem(QUALITY_STORAGE_KEY);
    if (raw === "performance" || raw === "balanced" || raw === "cinematic") {
      return raw;
    }
  } catch {
    /* ignore */
  }
  return "balanced";
}

/**
 * @param {QualityMode} mode
 */
export function persistQualityMode(mode) {
  try {
    localStorage.setItem(QUALITY_STORAGE_KEY, mode);
  } catch {
    /* ignore */
  }
}

export class QualityController {
  /**
   * @param {{ mode?: QualityMode }} [options]
   */
  constructor(options = {}) {
    /** @type {QualityMode} */
    this._mode = options.mode ?? loadStoredQualityMode();
    this._tier = 0;
    this._frameSamples = [];
    this._sampleWindow = 48;
    this._lastTierChangeMs = 0;
    this._degradeHoldMs = 2200;
    this._recoverHoldMs = 9000;
    this._hysteresisMs = 3500;
    this._pendingMode = /** @type {QualityMode | null} */ (null);
    this._geometryDirty = true;
    this._interactiveUntil = 0;
    this._reducedMotionForced = false;
  }

  /** @returns {QualityMode} */
  getMode() {
    return this._mode;
  }

  /** @returns {number} */
  getTier() {
    return this._tier;
  }

  /** @returns {string} */
  getTierLabel() {
    return ADAPTIVE_TIERS[this._tier]?.label ?? "high";
  }

  /**
   * @param {QualityMode} mode
   * @param {{ persist?: boolean }} [options]
   * @returns {boolean} true when geometry should be rebuilt
   */
  setMode(mode, options = {}) {
    if (mode !== "performance" && mode !== "balanced" && mode !== "cinematic") {
      return false;
    }
    const changed = mode !== this._mode;
    this._mode = mode;
    this._tier = 0;
    this._frameSamples = [];
    this._lastTierChangeMs = 0;
    if (options.persist !== false) {
      persistQualityMode(mode);
    }
    if (changed) {
      this._geometryDirty = true;
    }
    return changed;
  }

  markGeometryClean() {
    this._geometryDirty = false;
  }

  needsGeometryRebuild() {
    return this._geometryDirty;
  }

  /** Signal typing / submit / scroll — decorative work may be skipped. */
  notifyInteractive(durationMs = 220) {
    this._interactiveUntil = performance.now() + durationMs;
  }

  isInteractive() {
    return performance.now() < this._interactiveUntil;
  }

  /**
   * @param {number} frameMs
   * @param {number} nowMs
   */
  sampleFrame(frameMs, nowMs) {
    if (!Number.isFinite(frameMs) || frameMs <= 0) return;
    this._frameSamples.push(Math.min(frameMs, 64));
    if (this._frameSamples.length > this._sampleWindow) {
      this._frameSamples.shift();
    }

    const preset = QUALITY_PRESETS[this._mode];
    if (!preset.adaptive || this._frameSamples.length < this._sampleWindow) {
      return;
    }
    if (nowMs - this._lastTierChangeMs < this._hysteresisMs) {
      return;
    }

    const avg =
      this._frameSamples.reduce((a, b) => a + b, 0) / this._frameSamples.length;
    const budget = preset.frameBudgetMs;

    if (avg > budget * 1.15 && this._tier < ADAPTIVE_TIERS.length - 1) {
      if (nowMs - this._lastTierChangeMs >= this._degradeHoldMs || this._lastTierChangeMs === 0) {
        this._tier += 1;
        this._lastTierChangeMs = nowMs;
        this._frameSamples = [];
      }
    } else if (avg < budget * 0.78 && this._tier > 0) {
      if (nowMs - this._lastTierChangeMs >= this._recoverHoldMs) {
        this._tier -= 1;
        this._lastTierChangeMs = nowMs;
        this._frameSamples = [];
      }
    }
  }

  /** Effective budgets for the current mode + adaptive tier + reduced motion. */
  getBudgets() {
    const base = { ...QUALITY_PRESETS[this._mode] };
    const tier = ADAPTIVE_TIERS[this._tier] ?? ADAPTIVE_TIERS[0];
    const reduced = prefersReducedMotion() || this._reducedMotionForced;

    if (reduced) {
      base.maxDpr = Math.min(base.maxDpr, 1);
      base.maxEdgesDrawn = Math.floor(base.maxEdgesDrawn * 0.35);
      base.maxTissueDrawn = Math.floor(base.maxTissueDrawn * 0.35);
      base.dustCount = Math.min(base.dustCount, 16);
      base.bokehCount = 0;
      base.filamentDrawScale *= 0.35;
      base.microNeuronDrawScale *= 0.3;
      base.enableBloom = false;
      base.enableBokeh = false;
      base.enableLensDiffusion = false;
      base.enableAtmosphericFog = false;
      base.enableVolumetricHaze = false;
      base.enableForegroundFog = false;
      base.idleFrameSkip = Math.max(base.idleFrameSkip, 3);
      base.nodeHaloEnabled = false;
      base.intersectionMarks = false;
    }

    const edges = Math.max(800, Math.floor(base.maxEdgesDrawn * tier.edgeScale));
    const tissue = Math.max(200, Math.floor(base.maxTissueDrawn * tier.tissueScale));
    const dust = Math.max(0, Math.floor(base.dustCount * tier.dustScale));
    const bokeh = Math.max(0, Math.floor(base.bokehCount * tier.bokehScale));

    const effectsOk = (bit) => (tier.effectMask & bit) !== 0;

    return {
      mode: this._mode,
      tier: this._tier,
      tierLabel: tier.label,
      maxDpr: base.maxDpr,
      targetFps: base.targetFps,
      frameBudgetMs: base.frameBudgetMs,
      nodeDensityScale: base.nodeDensityScale,
      maxNodeCount: base.maxNodeCount,
      maxEdgesDrawn: edges,
      maxTissueDrawn: tissue,
      dustCount: dust,
      bokehCount: base.enableBokeh && effectsOk(0b1000) ? bokeh : 0,
      filamentDrawScale: base.filamentDrawScale * tier.filamentScale,
      microNeuronDrawScale: base.microNeuronDrawScale * tier.microScale,
      ambientPatchCount: base.ambientPatchCount,
      bloomSpotCount: base.enableBloom && effectsOk(0b0100) ? base.bloomSpotCount : 0,
      fogPatchCount: base.enableAtmosphericFog && effectsOk(0b0010) ? base.fogPatchCount : 0,
      hazePatchCount: base.enableVolumetricHaze && effectsOk(0b0001) ? base.hazePatchCount : 0,
      enableBloom: base.enableBloom && effectsOk(0b0100) && base.bloomSpotCount > 0,
      enableBokeh: base.enableBokeh && effectsOk(0b1000) && bokeh > 0,
      enableLensDiffusion: base.enableLensDiffusion && this._tier === 0 && !reduced,
      enableAtmosphericFog: base.enableAtmosphericFog && effectsOk(0b0010),
      enableVolumetricHaze: base.enableVolumetricHaze && effectsOk(0b0001),
      enableForegroundFog: base.enableForegroundFog && this._tier === 0 && !reduced,
      enableLightShafts: base.enableLightShafts && this._tier === 0 && !reduced,
      softHaloFarLayers: base.softHaloFarLayers && this._tier === 0,
      nodeHaloEnabled: base.nodeHaloEnabled && this._tier < 2,
      intersectionMarks: base.intersectionMarks && this._tier < 2,
      idleFrameSkip: base.idleFrameSkip + (this._tier >= 2 ? 1 : 0),
      interactiveSkipDecorative: base.interactiveSkipDecorative,
      reducedMotion: reduced,
    };
  }

  /** Snapshot for developer telemetry. */
  getSnapshot() {
    const budgets = this.getBudgets();
    return {
      mode: this._mode,
      tier: this._tier,
      tierLabel: budgets.tierLabel,
      geometryDirty: this._geometryDirty,
      interactive: this.isInteractive(),
      budgets,
    };
  }
}
