/** Titan Neural Renderer — Adaptive visual quality controller (Phase 11.P1 + 11.P2). */

import { NEURAL_CONFIG } from "./config.js";
import { prefersReducedMotion } from "./utils.js";

export const QUALITY_STORAGE_KEY = "titan_visual_quality_mode";
export const EMERGENCY_SESSION_KEY = "titan_visual_emergency_tier";

/**
 * @typedef {"auto" | "performance" | "balanced" | "cinematic"} QualityMode
 * @typedef {"normal" | "emergency" | "critical"} EmergencyTier
 */

/**
 * Approved cinematic ceilings live in NEURAL_CONFIG.
 * Modes scale draw/build budgets relative to those ceilings.
 */
export const QUALITY_PRESETS = Object.freeze({
  /** Conservative production default — Auto picks this until FPS proves otherwise. */
  auto: Object.freeze({
    id: "auto",
    label: "Auto",
    maxDpr: 1.0,
    targetFps: 50,
    frameBudgetMs: 20,
    targetVisualHz: 30,
    nodeDensityScale: 0.38,
    maxNodeCount: 3800,
    maxEdgesDrawn: 5200,
    maxTissueDrawn: 1100,
    dustCount: 28,
    bokehCount: 0,
    filamentDrawScale: 0.4,
    microNeuronDrawScale: 0.32,
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
    useStaticCache: true,
    adaptive: true,
    rebuildGeometry: true,
  }),
  performance: Object.freeze({
    id: "performance",
    label: "Performance",
    maxDpr: 1.0,
    targetFps: 50,
    frameBudgetMs: 20,
    targetVisualHz: 28,
    nodeDensityScale: 0.32,
    maxNodeCount: 3200,
    maxEdgesDrawn: 4200,
    maxTissueDrawn: 900,
    dustCount: 24,
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
    useStaticCache: true,
    adaptive: false,
    rebuildGeometry: true,
  }),
  balanced: Object.freeze({
    id: "balanced",
    label: "Balanced",
    maxDpr: 1.25,
    targetFps: 55,
    frameBudgetMs: 18,
    targetVisualHz: 45,
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
    useStaticCache: true,
    adaptive: true,
    rebuildGeometry: true,
  }),
  cinematic: Object.freeze({
    id: "cinematic",
    label: "Cinematic",
    maxDpr: 1.75,
    targetFps: 45,
    frameBudgetMs: 22,
    targetVisualHz: 60,
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
    useStaticCache: false,
    adaptive: false,
    rebuildGeometry: true,
  }),
});

/** Explicit emergency budgets — ≥70% cut vs cinematic decorative load. */
export const EMERGENCY_PRESET = Object.freeze({
  id: "emergency",
  label: "Emergency",
  maxDpr: 1.0,
  targetFps: 45,
  frameBudgetMs: 22,
  targetVisualHz: 24,
  nodeDensityScale: 0.22,
  maxNodeCount: 2200,
  maxEdgesDrawn: 2800,
  maxTissueDrawn: 520,
  dustCount: 0,
  bokehCount: 0,
  filamentDrawScale: 0.22,
  microNeuronDrawScale: 0.18,
  ambientPatchCount: 1,
  bloomSpotCount: 1,
  fogPatchCount: 0,
  hazePatchCount: 0,
  enableBloom: true,
  enableBokeh: false,
  enableLensDiffusion: false,
  enableAtmosphericFog: false,
  enableVolumetricHaze: false,
  enableForegroundFog: false,
  enableLightShafts: false,
  softHaloFarLayers: false,
  nodeHaloEnabled: false,
  intersectionMarks: false,
  idleFrameSkip: 2,
  interactiveSkipDecorative: true,
  useStaticCache: true,
  adaptive: false,
  rebuildGeometry: true,
  /** Extra cut when rolling FPS stays below 25. */
  criticalScale: 0.65,
});

/** Adaptive draw tiers applied inside Auto/Balanced (no geometry rebuild). */
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

const VALID_MODES = new Set(["auto", "performance", "balanced", "cinematic"]);

/**
 * @param {string | null | undefined} raw
 * @returns {QualityMode | null}
 */
export function parseQualityMode(raw) {
  if (!raw) return null;
  const normalized = String(raw).trim().toLowerCase();
  if (VALID_MODES.has(normalized)) {
    return /** @type {QualityMode} */ (normalized);
  }
  if (normalized === "emergency") {
    return "performance";
  }
  return null;
}

/**
 * URL override: /app/?quality=performance
 * @returns {QualityMode | null}
 */
export function readQualityUrlOverride() {
  try {
    const params = new URLSearchParams(window.location.search);
    return parseQualityMode(params.get("quality"));
  } catch {
    return null;
  }
}

/**
 * @returns {QualityMode}
 */
export function loadStoredQualityMode() {
  const fromUrl = readQualityUrlOverride();
  if (fromUrl) return fromUrl;
  try {
    const raw = localStorage.getItem(QUALITY_STORAGE_KEY);
    const parsed = parseQualityMode(raw);
    if (parsed) return parsed;
  } catch {
    /* ignore */
  }
  return "auto";
}

/**
 * @param {QualityMode} mode
 */
export function persistQualityMode(mode) {
  if (!VALID_MODES.has(mode)) return;
  try {
    localStorage.setItem(QUALITY_STORAGE_KEY, mode);
  } catch {
    /* ignore */
  }
}

/**
 * @returns {EmergencyTier}
 */
export function loadSessionEmergencyTier() {
  try {
    const raw = sessionStorage.getItem(EMERGENCY_SESSION_KEY);
    if (raw === "emergency" || raw === "critical") return raw;
  } catch {
    /* ignore */
  }
  return "normal";
}

/**
 * @param {EmergencyTier} tier
 */
export function persistSessionEmergencyTier(tier) {
  try {
    if (tier === "normal") {
      sessionStorage.removeItem(EMERGENCY_SESSION_KEY);
    } else {
      sessionStorage.setItem(EMERGENCY_SESSION_KEY, tier);
    }
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
    /** @type {EmergencyTier} */
    this._emergencyTier = this._mode === "auto" ? loadSessionEmergencyTier() : "normal";
    this._frameSamples = [];
    this._fpsSamples = [];
    this._sampleWindow = 48;
    this._lastTierChangeMs = 0;
    this._degradeHoldMs = 2200;
    this._recoverHoldMs = 9000;
    this._hysteresisMs = 3500;
    this._lowFpsSinceMs = 0;
    this._criticalFpsSinceMs = 0;
    this._geometryDirty = true;
    this._staticCacheDirty = true;
    this._interactiveUntil = 0;
    this._reducedMotionForced = false;
    this._chatPending = false;
    this._thinkingLight = false;
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
    if (this._emergencyTier === "critical") return "emergency-critical";
    if (this._emergencyTier === "emergency") return "emergency";
    return ADAPTIVE_TIERS[this._tier]?.label ?? "high";
  }

  /** @returns {EmergencyTier} */
  getEmergencyTier() {
    return this._emergencyTier;
  }

  isEmergency() {
    return this._emergencyTier !== "normal";
  }

  /**
   * @param {QualityMode} mode
   * @param {{ persist?: boolean }} [options]
   * @returns {boolean} true when geometry should be rebuilt
   */
  setMode(mode, options = {}) {
    const parsed = parseQualityMode(mode);
    if (!parsed) return false;
    const changed = parsed !== this._mode;
    this._mode = parsed;
    this._tier = 0;
    this._frameSamples = [];
    this._fpsSamples = [];
    this._lastTierChangeMs = 0;
    this._lowFpsSinceMs = 0;
    this._criticalFpsSinceMs = 0;
    if (parsed !== "auto") {
      this._emergencyTier = "normal";
      persistSessionEmergencyTier("normal");
    } else {
      this._emergencyTier = loadSessionEmergencyTier();
    }
    if (options.persist !== false && !readQualityUrlOverride()) {
      persistQualityMode(parsed);
    }
    if (changed || this._emergencyTier !== "normal") {
      this._geometryDirty = true;
      this._staticCacheDirty = true;
    }
    return changed;
  }

  /**
   * Force emergency tier (session-scoped). Used by Auto FPS watchdog.
   * @param {EmergencyTier} tier
   * @returns {boolean} true when tier changed
   */
  enterEmergencyTier(tier) {
    if (tier !== "emergency" && tier !== "critical" && tier !== "normal") {
      return false;
    }
    if (this._mode !== "auto" && tier !== "normal") {
      // Manual Performance/Balanced/Cinematic — only Auto auto-escalates.
      // Performance mode already uses low budgets; critical still allowed via sampleFps.
      if (this._mode !== "performance") return false;
    }
    const prev = this._emergencyTier;
    if (tier === prev) return false;
    this._emergencyTier = tier;
    persistSessionEmergencyTier(tier);
    this._geometryDirty = true;
    this._staticCacheDirty = true;
    return true;
  }

  markGeometryClean() {
    this._geometryDirty = false;
  }

  needsGeometryRebuild() {
    return this._geometryDirty;
  }

  markStaticCacheDirty() {
    this._staticCacheDirty = true;
  }

  markStaticCacheClean() {
    this._staticCacheDirty = false;
  }

  needsStaticCacheRebuild() {
    return this._staticCacheDirty;
  }

  /** Signal typing / submit / scroll — decorative work may be skipped. */
  notifyInteractive(durationMs = 220) {
    this._interactiveUntil = performance.now() + durationMs;
  }

  isInteractive() {
    return performance.now() < this._interactiveUntil;
  }

  /** @param {boolean} pending */
  setChatPending(pending) {
    this._chatPending = Boolean(pending);
    if (pending) {
      this.notifyInteractive(8000);
      this._thinkingLight = true;
    } else {
      this._thinkingLight = false;
    }
  }

  isChatPending() {
    return this._chatPending;
  }

  /**
   * Thinking must never increase decorative load.
   * @returns {boolean}
   */
  shouldLightenThinking() {
    return (
      this._chatPending ||
      this._thinkingLight ||
      this.isEmergency() ||
      this._mode === "performance" ||
      this._mode === "auto"
    );
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
    if (!preset.adaptive || this.isEmergency()) {
      return;
    }
    if (this._frameSamples.length < this._sampleWindow) {
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

  /**
   * Auto-performance watchdog using rolling FPS (Phase 11.P2).
   * @param {number} rollingFps
   * @param {number} nowMs
   * @returns {boolean} true when emergency tier changed (needs rebuild)
   */
  sampleRollingFps(rollingFps, nowMs) {
    if (!Number.isFinite(rollingFps) || rollingFps <= 0) return false;
    this._fpsSamples.push(rollingFps);
    if (this._fpsSamples.length > 90) {
      this._fpsSamples.shift();
    }

    // Auto + Performance may escalate; Balanced/Cinematic stay user-chosen.
    if (this._mode !== "auto" && this._mode !== "performance") {
      return false;
    }

    let changed = false;

    if (rollingFps < 25) {
      if (!this._criticalFpsSinceMs) this._criticalFpsSinceMs = nowMs;
      if (nowMs - this._criticalFpsSinceMs >= 1500) {
        changed = this.enterEmergencyTier("critical") || changed;
      }
    } else {
      this._criticalFpsSinceMs = 0;
    }

    if (rollingFps < 35) {
      if (!this._lowFpsSinceMs) this._lowFpsSinceMs = nowMs;
      // Sustained <35 FPS for >3s → emergency (do not wait for settings).
      if (nowMs - this._lowFpsSinceMs >= 3000) {
        if (this._emergencyTier === "normal") {
          changed = this.enterEmergencyTier("emergency") || changed;
        }
      }
    } else {
      this._lowFpsSinceMs = 0;
    }

    return changed;
  }

  /** Effective budgets for the current mode + adaptive tier + emergency + reduced motion. */
  getBudgets() {
    const inEmergency = this.isEmergency();
    const base = {
      ...(inEmergency ? EMERGENCY_PRESET : QUALITY_PRESETS[this._mode]),
    };
    const tier = ADAPTIVE_TIERS[this._tier] ?? ADAPTIVE_TIERS[0];
    const reduced = prefersReducedMotion() || this._reducedMotionForced;
    const chatPending = this._chatPending;

    if (this._emergencyTier === "critical") {
      const scale = EMERGENCY_PRESET.criticalScale;
      base.maxNodeCount = Math.floor(base.maxNodeCount * scale);
      base.maxEdgesDrawn = Math.floor(base.maxEdgesDrawn * scale);
      base.maxTissueDrawn = Math.floor(base.maxTissueDrawn * scale);
      base.filamentDrawScale *= scale;
      base.microNeuronDrawScale *= scale;
      base.targetVisualHz = Math.min(base.targetVisualHz, 20);
      base.dustCount = 0;
      base.bokehCount = 0;
      base.enableVolumetricHaze = false;
      base.bloomSpotCount = 0;
      base.enableBloom = false;
    }

    if (chatPending) {
      base.maxEdgesDrawn = Math.floor(base.maxEdgesDrawn * 0.55);
      base.maxTissueDrawn = Math.floor(base.maxTissueDrawn * 0.5);
      base.dustCount = 0;
      base.bokehCount = 0;
      base.enableBokeh = false;
      base.enableAtmosphericFog = false;
      base.enableLensDiffusion = false;
      base.enableForegroundFog = false;
      base.enableLightShafts = false;
      base.targetVisualHz = Math.min(base.targetVisualHz ?? 30, 22);
      base.idleFrameSkip = Math.max(base.idleFrameSkip, 2);
      base.interactiveSkipDecorative = true;
    }

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

    const edgeScale = inEmergency ? 1 : tier.edgeScale;
    const tissueScale = inEmergency ? 1 : tier.tissueScale;
    const dustScale = inEmergency ? 1 : tier.dustScale;
    const bokehScale = inEmergency ? 0 : tier.bokehScale;
    const filamentScale = inEmergency ? 1 : tier.filamentScale;
    const microScale = inEmergency ? 1 : tier.microScale;
    const effectMask = inEmergency ? 0b0001 : tier.effectMask;

    const edges = Math.max(400, Math.floor(base.maxEdgesDrawn * edgeScale));
    const tissue = Math.max(120, Math.floor(base.maxTissueDrawn * tissueScale));
    const dust = Math.max(0, Math.floor(base.dustCount * dustScale));
    const bokeh = Math.max(0, Math.floor(base.bokehCount * bokehScale));

    const effectsOk = (bit) => (effectMask & bit) !== 0;

    return {
      mode: this._mode,
      tier: this._tier,
      tierLabel: this.getTierLabel(),
      emergencyTier: this._emergencyTier,
      emergency: inEmergency,
      maxDpr: Math.min(base.maxDpr, inEmergency ? 1.0 : base.maxDpr),
      targetFps: base.targetFps,
      targetVisualHz: base.targetVisualHz ?? 45,
      frameBudgetMs: base.frameBudgetMs,
      nodeDensityScale: base.nodeDensityScale,
      maxNodeCount: base.maxNodeCount,
      maxEdgesDrawn: edges,
      maxTissueDrawn: tissue,
      dustCount: dust,
      bokehCount: base.enableBokeh && effectsOk(0b1000) ? bokeh : 0,
      filamentDrawScale: base.filamentDrawScale * filamentScale,
      microNeuronDrawScale: base.microNeuronDrawScale * microScale,
      ambientPatchCount: base.ambientPatchCount,
      bloomSpotCount: base.enableBloom && effectsOk(0b0100) ? base.bloomSpotCount : 0,
      fogPatchCount: base.enableAtmosphericFog && effectsOk(0b0010) ? base.fogPatchCount : 0,
      hazePatchCount: base.enableVolumetricHaze && effectsOk(0b0001) ? base.hazePatchCount : 0,
      enableBloom: base.enableBloom && effectsOk(0b0100) && base.bloomSpotCount > 0,
      enableBokeh: base.enableBokeh && effectsOk(0b1000) && bokeh > 0,
      enableLensDiffusion: base.enableLensDiffusion && this._tier === 0 && !reduced && !inEmergency,
      enableAtmosphericFog: base.enableAtmosphericFog && effectsOk(0b0010) && !inEmergency,
      enableVolumetricHaze: base.enableVolumetricHaze && effectsOk(0b0001) && !chatPending,
      enableForegroundFog: base.enableForegroundFog && this._tier === 0 && !reduced && !inEmergency,
      enableLightShafts: base.enableLightShafts && this._tier === 0 && !reduced && !inEmergency,
      softHaloFarLayers: base.softHaloFarLayers && this._tier === 0 && !inEmergency,
      nodeHaloEnabled: base.nodeHaloEnabled && this._tier < 2 && !inEmergency,
      intersectionMarks: base.intersectionMarks && this._tier < 2 && !inEmergency,
      idleFrameSkip: base.idleFrameSkip + (this._tier >= 2 || inEmergency ? 1 : 0),
      interactiveSkipDecorative: base.interactiveSkipDecorative,
      useStaticCache: Boolean(base.useStaticCache) || inEmergency || chatPending,
      chatPending,
      lightenThinking: this.shouldLightenThinking(),
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
      emergencyTier: this._emergencyTier,
      geometryDirty: this._geometryDirty,
      staticCacheDirty: this._staticCacheDirty,
      interactive: this.isInteractive(),
      chatPending: this._chatPending,
      budgets,
    };
  }
}
