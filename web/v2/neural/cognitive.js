/** Titan Neural Renderer V2 — Cognitive signatures & overlay (Phase E4). */

import { lerp } from "./utils.js";

/** Canonical cognitive state ids (Phase E4 minimum set). */
export const COGNITIVE_STATE_IDS = [
  "idle",
  "listening",
  "thinking",
  "planning",
  "memory_recall",
  "reasoning",
  "writing",
  "tool_execution",
  "browser_research",
  "obsidian",
  "calendar",
  "trading",
  "voice",
  "error",
  "sleep",
];

/** Uppercase keys for API consumers. */
export const COGNITIVE_STATE_ENUM = Object.freeze(
  COGNITIVE_STATE_IDS.reduce((acc, id) => {
    acc[id.toUpperCase()] = id;
    return acc;
  }, /** @type {Record<string, string>} */ ({})),
);

const STATE_ALIASES = {
  idle: "idle",
  listening: "listening",
  thinking: "thinking",
  planning: "planning",
  plan: "planning",
  memory_recall: "memory_recall",
  memory_retrieval: "memory_recall",
  memory: "memory_recall",
  recall: "memory_recall",
  reasoning: "reasoning",
  deep: "reasoning",
  deep_analysis: "reasoning",
  analysis: "reasoning",
  writing: "writing",
  write: "writing",
  tool_execution: "tool_execution",
  tool_usage: "tool_execution",
  tool: "tool_execution",
  working: "tool_execution",
  browser_research: "browser_research",
  browser: "browser_research",
  exploration: "browser_research",
  research: "browser_research",
  obsidian: "obsidian",
  vault: "obsidian",
  calendar: "calendar",
  calendar_planning: "calendar",
  trading: "trading",
  trading_analysis: "trading",
  voice: "voice",
  speaking: "voice",
  voice_speaking: "voice",
  error: "error",
  err: "error",
  sleep: "sleep",
  sleeping: "sleep",
  dormant: "sleep",
  email: "writing",
  email_processing: "writing",
};

const CSS_CLASS_MAP = {
  idle: "tdl-v2-neural-canvas--cognitive-idle",
  listening: "tdl-v2-neural-canvas--cognitive-listening",
  thinking: "tdl-v2-neural-canvas--cognitive-thinking",
  planning: "tdl-v2-neural-canvas--cognitive-planning",
  memory_recall: "tdl-v2-neural-canvas--cognitive-memory",
  reasoning: "tdl-v2-neural-canvas--cognitive-reasoning",
  writing: "tdl-v2-neural-canvas--cognitive-writing",
  tool_execution: "tdl-v2-neural-canvas--cognitive-tool",
  browser_research: "tdl-v2-neural-canvas--cognitive-browser",
  obsidian: "tdl-v2-neural-canvas--cognitive-obsidian",
  calendar: "tdl-v2-neural-canvas--cognitive-calendar",
  trading: "tdl-v2-neural-canvas--cognitive-trading",
  voice: "tdl-v2-neural-canvas--cognitive-voice",
  error: "tdl-v2-neural-canvas--cognitive-error",
  sleep: "tdl-v2-neural-canvas--cognitive-sleep",
};

const MASTER_CSS_MAP = {
  BOOTING: "tdl-v2-neural-canvas--booting",
  AWAKE: "tdl-v2-neural-canvas--awake",
  IDLE: "tdl-v2-neural-canvas--idle",
  LISTENING: "tdl-v2-neural-canvas--listening",
  THINKING: "tdl-v2-neural-canvas--thinking",
  WORKING: "tdl-v2-neural-canvas--working",
  SPEAKING: "tdl-v2-neural-canvas--speaking",
  DEPTH_RECALL: "tdl-v2-neural-canvas--depth-recall",
  ERROR: "tdl-v2-neural-canvas--error",
  SLEEP: "tdl-v2-neural-canvas--sleep",
};

/** French labels for UI transparency. */
export const COGNITIVE_STATE_LABELS = Object.freeze({
  idle: "Repos",
  listening: "Écoute",
  thinking: "Réflexion",
  planning: "Planification",
  memory_recall: "Rappel mémoire",
  reasoning: "Raisonnement",
  writing: "Rédaction",
  tool_execution: "Exécution d'outil",
  browser_research: "Recherche web",
  obsidian: "Obsidian",
  calendar: "Calendrier",
  trading: "Trading",
  voice: "Voix",
  error: "Erreur",
  sleep: "Veille",
});

/** @type {Record<string, object>} */
const SIGNATURES = {
  idle: {
    neuralMode: "idle",
    activityTarget: 0.08,
    thinkingTarget: 0,
    glowLevel: 0.44,
    breatheSpeed: 0.92,
    signalDensity: 0.32,
    signalBrightness: 0.55,
    spawnIntervalMult: 1.45,
    maxSignalsMult: 0.48,
    speedMult: 0.62,
    connectionIntensity: 0.42,
    nodeActivityMult: 0.38,
    cameraDive: 0,
    cameraShake: 0,
    focusPull: 0,
    waveStyle: "central",
    waveBurst: 1,
    memoryFragments: false,
    neuralEchoes: false,
    distantRegions: false,
    longPaths: false,
    circularWaves: false,
    regionSync: false,
    distributedExploration: false,
    sharpSignals: false,
    fastSync: false,
    structuredGeometry: false,
    rhythmicPulse: false,
    localBursts: false,
    preferDeep: false,
    ghostActivity: false,
    signalFragmentation: false,
    nodeInstability: false,
    focusComposer: false,
    transitionMs: 900,
  },
  listening: {
    neuralMode: "idle",
    activityTarget: 0.22,
    thinkingTarget: 0.08,
    glowLevel: 0.52,
    breatheSpeed: 1.08,
    signalDensity: 0.38,
    signalBrightness: 0.62,
    spawnIntervalMult: 1.12,
    maxSignalsMult: 0.62,
    speedMult: 0.78,
    connectionIntensity: 0.48,
    nodeActivityMult: 0.52,
    cameraDive: 0,
    cameraShake: 0,
    focusPull: 0.12,
    waveStyle: "default",
    waveBurst: 1,
    memoryFragments: false,
    neuralEchoes: false,
    distantRegions: false,
    longPaths: false,
    circularWaves: false,
    regionSync: false,
    distributedExploration: false,
    sharpSignals: false,
    fastSync: false,
    structuredGeometry: false,
    rhythmicPulse: false,
    localBursts: true,
    preferDeep: false,
    ghostActivity: false,
    signalFragmentation: false,
    nodeInstability: false,
    focusComposer: true,
    transitionMs: 500,
  },
  thinking: {
    neuralMode: "thinking",
    activityTarget: 0.75,
    thinkingTarget: 0.82,
    glowLevel: 0.78,
    breatheSpeed: 1.22,
    signalDensity: 0.88,
    signalBrightness: 0.82,
    spawnIntervalMult: 0.34,
    maxSignalsMult: 1,
    speedMult: 1.05,
    connectionIntensity: 0.78,
    nodeActivityMult: 0.85,
    cameraDive: 0.08,
    cameraShake: 0,
    focusPull: 0.62,
    waveStyle: "default",
    waveBurst: 2,
    memoryFragments: false,
    neuralEchoes: false,
    distantRegions: false,
    longPaths: true,
    circularWaves: false,
    regionSync: false,
    distributedExploration: false,
    sharpSignals: false,
    fastSync: false,
    structuredGeometry: false,
    rhythmicPulse: false,
    localBursts: true,
    preferDeep: false,
    ghostActivity: false,
    signalFragmentation: false,
    nodeInstability: false,
    focusComposer: false,
    transitionMs: 700,
  },
  planning: {
    neuralMode: "thinking",
    activityTarget: 0.72,
    thinkingTarget: 0.7,
    glowLevel: 0.7,
    breatheSpeed: 1.12,
    signalDensity: 0.8,
    signalBrightness: 0.74,
    spawnIntervalMult: 0.55,
    maxSignalsMult: 0.92,
    speedMult: 1.02,
    connectionIntensity: 0.72,
    nodeActivityMult: 0.68,
    cameraDive: 0.14,
    cameraShake: 0,
    focusPull: 0.55,
    waveStyle: "circular",
    waveBurst: 2,
    memoryFragments: false,
    neuralEchoes: false,
    distantRegions: false,
    longPaths: false,
    circularWaves: true,
    regionSync: true,
    distributedExploration: false,
    sharpSignals: false,
    fastSync: false,
    structuredGeometry: false,
    rhythmicPulse: false,
    localBursts: false,
    preferDeep: false,
    ghostActivity: false,
    signalFragmentation: false,
    nodeInstability: false,
    focusComposer: false,
    transitionMs: 680,
  },
  memory_recall: {
    neuralMode: "thinking",
    activityTarget: 0.68,
    thinkingTarget: 0.45,
    glowLevel: 0.72,
    breatheSpeed: 1.05,
    signalDensity: 0.74,
    signalBrightness: 0.88,
    spawnIntervalMult: 0.52,
    maxSignalsMult: 0.88,
    speedMult: 0.82,
    connectionIntensity: 0.65,
    nodeActivityMult: 0.62,
    cameraDive: 0.38,
    cameraShake: 0,
    focusPull: 0.48,
    waveStyle: "deep_central",
    waveBurst: 2,
    memoryFragments: true,
    neuralEchoes: true,
    distantRegions: false,
    longPaths: true,
    circularWaves: false,
    regionSync: false,
    distributedExploration: false,
    sharpSignals: false,
    fastSync: false,
    structuredGeometry: false,
    rhythmicPulse: false,
    localBursts: false,
    preferDeep: true,
    ghostActivity: true,
    signalFragmentation: false,
    nodeInstability: false,
    focusComposer: false,
    transitionMs: 760,
  },
  reasoning: {
    neuralMode: "thinking",
    activityTarget: 0.92,
    thinkingTarget: 0.95,
    glowLevel: 0.86,
    breatheSpeed: 1.28,
    signalDensity: 0.96,
    signalBrightness: 0.9,
    spawnIntervalMult: 0.26,
    maxSignalsMult: 1.15,
    speedMult: 0.92,
    connectionIntensity: 0.92,
    nodeActivityMult: 0.95,
    cameraDive: 0.58,
    cameraShake: 0,
    focusPull: 0.88,
    waveStyle: "slow",
    waveBurst: 3,
    memoryFragments: false,
    neuralEchoes: false,
    distantRegions: true,
    longPaths: true,
    circularWaves: false,
    regionSync: true,
    distributedExploration: false,
    sharpSignals: false,
    fastSync: false,
    structuredGeometry: false,
    rhythmicPulse: false,
    localBursts: true,
    preferDeep: true,
    ghostActivity: false,
    signalFragmentation: false,
    nodeInstability: false,
    focusComposer: false,
    transitionMs: 820,
  },
  writing: {
    neuralMode: "thinking",
    activityTarget: 0.64,
    thinkingTarget: 0.52,
    glowLevel: 0.66,
    breatheSpeed: 1.06,
    signalDensity: 0.72,
    signalBrightness: 0.7,
    spawnIntervalMult: 0.68,
    maxSignalsMult: 0.8,
    speedMult: 0.88,
    connectionIntensity: 0.58,
    nodeActivityMult: 0.55,
    cameraDive: 0.06,
    cameraShake: 0,
    focusPull: 0.35,
    waveStyle: "distributed",
    waveBurst: 1,
    memoryFragments: false,
    neuralEchoes: false,
    distantRegions: false,
    longPaths: false,
    circularWaves: false,
    regionSync: false,
    distributedExploration: true,
    sharpSignals: false,
    fastSync: false,
    structuredGeometry: false,
    rhythmicPulse: true,
    localBursts: false,
    preferDeep: false,
    ghostActivity: false,
    signalFragmentation: false,
    nodeInstability: false,
    focusComposer: true,
    transitionMs: 650,
  },
  tool_execution: {
    neuralMode: "thinking",
    activityTarget: 0.65,
    thinkingTarget: 0.55,
    glowLevel: 0.66,
    breatheSpeed: 1.1,
    signalDensity: 0.76,
    signalBrightness: 0.72,
    spawnIntervalMult: 0.62,
    maxSignalsMult: 0.85,
    speedMult: 1,
    connectionIntensity: 0.68,
    nodeActivityMult: 0.7,
    cameraDive: 0.1,
    cameraShake: 0,
    focusPull: 0.42,
    waveStyle: "default",
    waveBurst: 1,
    memoryFragments: false,
    neuralEchoes: false,
    distantRegions: false,
    longPaths: false,
    circularWaves: false,
    regionSync: false,
    distributedExploration: false,
    sharpSignals: false,
    fastSync: false,
    structuredGeometry: false,
    rhythmicPulse: false,
    localBursts: true,
    preferDeep: false,
    ghostActivity: false,
    signalFragmentation: false,
    nodeInstability: false,
    focusComposer: false,
    transitionMs: 650,
  },
  browser_research: {
    neuralMode: "thinking",
    activityTarget: 0.82,
    thinkingTarget: 0.68,
    glowLevel: 0.76,
    breatheSpeed: 1.18,
    signalDensity: 0.9,
    signalBrightness: 0.78,
    spawnIntervalMult: 0.4,
    maxSignalsMult: 1.05,
    speedMult: 1.15,
    connectionIntensity: 0.75,
    nodeActivityMult: 0.78,
    cameraDive: 0.16,
    cameraShake: 0,
    focusPull: 0.55,
    waveStyle: "distributed",
    waveBurst: 3,
    memoryFragments: false,
    neuralEchoes: false,
    distantRegions: true,
    longPaths: true,
    circularWaves: false,
    regionSync: false,
    distributedExploration: true,
    sharpSignals: false,
    fastSync: false,
    structuredGeometry: false,
    rhythmicPulse: false,
    localBursts: false,
    preferDeep: false,
    ghostActivity: false,
    signalFragmentation: false,
    nodeInstability: false,
    focusComposer: false,
    transitionMs: 680,
  },
  obsidian: {
    neuralMode: "thinking",
    activityTarget: 0.6,
    thinkingTarget: 0.48,
    glowLevel: 0.64,
    breatheSpeed: 1,
    signalDensity: 0.68,
    signalBrightness: 0.75,
    spawnIntervalMult: 0.74,
    maxSignalsMult: 0.76,
    speedMult: 0.86,
    connectionIntensity: 0.62,
    nodeActivityMult: 0.58,
    cameraDive: 0.12,
    cameraShake: 0,
    focusPull: 0.4,
    waveStyle: "deep_central",
    waveBurst: 1,
    memoryFragments: true,
    neuralEchoes: false,
    distantRegions: false,
    longPaths: true,
    circularWaves: false,
    regionSync: false,
    distributedExploration: false,
    sharpSignals: false,
    fastSync: false,
    structuredGeometry: false,
    rhythmicPulse: false,
    localBursts: false,
    preferDeep: false,
    ghostActivity: true,
    signalFragmentation: false,
    nodeInstability: false,
    focusComposer: false,
    transitionMs: 720,
  },
  calendar: {
    neuralMode: "thinking",
    activityTarget: 0.62,
    thinkingTarget: 0.5,
    glowLevel: 0.64,
    breatheSpeed: 1.02,
    signalDensity: 0.7,
    signalBrightness: 0.68,
    spawnIntervalMult: 0.72,
    maxSignalsMult: 0.78,
    speedMult: 0.9,
    connectionIntensity: 0.6,
    nodeActivityMult: 0.55,
    cameraDive: 0.08,
    cameraShake: 0,
    focusPull: 0.38,
    waveStyle: "circular",
    waveBurst: 1,
    memoryFragments: false,
    neuralEchoes: false,
    distantRegions: false,
    longPaths: false,
    circularWaves: true,
    regionSync: true,
    distributedExploration: false,
    sharpSignals: false,
    fastSync: false,
    structuredGeometry: false,
    rhythmicPulse: false,
    localBursts: false,
    preferDeep: false,
    ghostActivity: false,
    signalFragmentation: false,
    nodeInstability: false,
    focusComposer: false,
    transitionMs: 700,
  },
  trading: {
    neuralMode: "thinking",
    activityTarget: 0.85,
    thinkingTarget: 0.78,
    glowLevel: 0.8,
    breatheSpeed: 1.24,
    signalDensity: 0.92,
    signalBrightness: 0.92,
    spawnIntervalMult: 0.38,
    maxSignalsMult: 1.08,
    speedMult: 1.38,
    connectionIntensity: 0.95,
    nodeActivityMult: 0.88,
    cameraDive: 0.18,
    cameraShake: 0,
    focusPull: 0.72,
    waveStyle: "sharp",
    waveBurst: 3,
    memoryFragments: false,
    neuralEchoes: false,
    distantRegions: false,
    longPaths: false,
    circularWaves: false,
    regionSync: true,
    distributedExploration: false,
    sharpSignals: true,
    fastSync: true,
    structuredGeometry: true,
    rhythmicPulse: false,
    localBursts: true,
    preferDeep: false,
    ghostActivity: false,
    signalFragmentation: false,
    nodeInstability: false,
    focusComposer: false,
    transitionMs: 620,
  },
  voice: {
    neuralMode: "thinking",
    activityTarget: 0.76,
    thinkingTarget: 0.58,
    glowLevel: 0.74,
    breatheSpeed: 1.18,
    signalDensity: 0.86,
    signalBrightness: 0.8,
    spawnIntervalMult: 0.44,
    maxSignalsMult: 0.9,
    speedMult: 1.1,
    connectionIntensity: 0.7,
    nodeActivityMult: 0.72,
    cameraDive: 0.1,
    cameraShake: 0,
    focusPull: 0.52,
    waveStyle: "circular",
    waveBurst: 2,
    memoryFragments: false,
    neuralEchoes: false,
    distantRegions: false,
    longPaths: false,
    circularWaves: true,
    regionSync: true,
    distributedExploration: false,
    sharpSignals: false,
    fastSync: true,
    structuredGeometry: false,
    rhythmicPulse: true,
    localBursts: false,
    preferDeep: false,
    ghostActivity: false,
    signalFragmentation: false,
    nodeInstability: false,
    focusComposer: false,
    transitionMs: 580,
  },
  error: {
    neuralMode: "thinking",
    activityTarget: 0.55,
    thinkingTarget: 0.35,
    glowLevel: 0.58,
    breatheSpeed: 1.35,
    signalDensity: 0.62,
    signalBrightness: 0.95,
    spawnIntervalMult: 0.48,
    maxSignalsMult: 0.95,
    speedMult: 1.45,
    connectionIntensity: 0.35,
    nodeActivityMult: 0.82,
    cameraDive: 0.05,
    cameraShake: 0.85,
    focusPull: 0.25,
    waveStyle: "sharp",
    waveBurst: 2,
    memoryFragments: false,
    neuralEchoes: false,
    distantRegions: false,
    longPaths: false,
    circularWaves: false,
    regionSync: false,
    distributedExploration: false,
    sharpSignals: true,
    fastSync: false,
    structuredGeometry: false,
    rhythmicPulse: false,
    localBursts: true,
    preferDeep: false,
    ghostActivity: false,
    signalFragmentation: true,
    nodeInstability: true,
    focusComposer: false,
    transitionMs: 420,
  },
  sleep: {
    neuralMode: "idle",
    activityTarget: 0.03,
    thinkingTarget: 0,
    glowLevel: 0.22,
    breatheSpeed: 0.55,
    signalDensity: 0.12,
    signalBrightness: 0.28,
    spawnIntervalMult: 2.2,
    maxSignalsMult: 0.22,
    speedMult: 0.38,
    connectionIntensity: 0.18,
    nodeActivityMult: 0.15,
    cameraDive: 0,
    cameraShake: 0,
    focusPull: 0,
    waveStyle: "central",
    waveBurst: 0,
    memoryFragments: false,
    neuralEchoes: false,
    distantRegions: false,
    longPaths: false,
    circularWaves: false,
    regionSync: false,
    distributedExploration: false,
    sharpSignals: false,
    fastSync: false,
    structuredGeometry: false,
    rhythmicPulse: false,
    localBursts: false,
    preferDeep: false,
    ghostActivity: false,
    signalFragmentation: false,
    nodeInstability: false,
    focusComposer: false,
    transitionMs: 1200,
  },
};

/** @param {string} [name] */
export function normalizeCognitiveState(name) {
  if (!name || typeof name !== "string") return "idle";
  const key = name.trim().toLowerCase().replace(/[\s-]+/g, "_");
  const mapped = STATE_ALIASES[key];
  if (mapped && SIGNATURES[mapped]) return mapped;
  if (SIGNATURES[key]) return key;
  return "idle";
}

/** @param {string} stateId */
export function getCognitiveSignature(stateId) {
  const normalized = normalizeCognitiveState(stateId);
  return SIGNATURES[normalized] ?? SIGNATURES.idle;
}

/** @param {string} fromId @param {string} toId @param {number} blend */
export function blendCognitiveSignatures(fromId, toId, blend) {
  const from = getCognitiveSignature(fromId);
  const to = getCognitiveSignature(toId);
  const t = Math.max(0, Math.min(1, blend));
  /** @type {Record<string, unknown>} */
  const out = {};

  for (const key of Object.keys(to)) {
    const a = from[key];
    const b = to[key];
    if (typeof b === "number") {
      out[key] = lerp(typeof a === "number" ? a : 0, b, t);
    } else if (typeof b === "boolean") {
      out[key] = t >= 0.55 ? b : Boolean(a);
    } else {
      out[key] = t >= 0.65 ? b : a;
    }
  }
  return out;
}

/** @param {string} stateId */
export function getCognitiveCssClass(stateId) {
  const normalized = normalizeCognitiveState(stateId);
  return CSS_CLASS_MAP[normalized] ?? CSS_CLASS_MAP.idle;
}

export function getAllCognitiveCssClasses() {
  return COGNITIVE_STATE_IDS.map((id) => CSS_CLASS_MAP[id]);
}

/** @param {string} masterState */
export function getMasterCssClass(masterState) {
  return MASTER_CSS_MAP[masterState] ?? MASTER_CSS_MAP.AWAKE;
}

/** Map cognitive id → neural master state. */
export function resolveMasterState(cognitiveId) {
  const id = normalizeCognitiveState(cognitiveId);
  if (id === "listening") return "LISTENING";
  if (id === "voice") return "SPEAKING";
  if (id === "memory_recall") return "DEPTH_RECALL";
  if (id === "error") return "ERROR";
  if (id === "sleep") return "SLEEP";
  if (id === "idle") return "IDLE";
  if (
    id === "thinking" ||
    id === "reasoning" ||
    id === "planning" ||
    id === "writing"
  ) {
    return "THINKING";
  }
  return "WORKING";
}

export class CognitiveOverlay {
  constructor() {
    this.fragments = [];
    this.geometry = [];
    this.rings = [];
    this._spawnAcc = 0;
    this._voicePhase = 0;
    this._errorAcc = 0;
  }

  /** @param {number} deltaMs @param {object | null} signature */
  update(deltaMs, signature) {
    if (!signature) return;
    const dt = deltaMs / 16.67;
    this._voicePhase += signature.rhythmicPulse ? 0.065 * dt : 0.012 * dt;
    this._spawnAcc += deltaMs;
    this._errorAcc += deltaMs;

    this._fadeCollection(this.fragments, 0.014 * dt);
    this._fadeCollection(this.geometry, 0.018 * dt);
    this._fadeCollection(this.rings, 0.016 * dt);

    if (signature.memoryFragments && this._spawnAcc > 1400) {
      this._spawnAcc = 0;
      this._spawnFragment();
      if (signature.neuralEchoes && Math.random() < 0.45) {
        this._spawnFragment(true);
      }
    }

    if (signature.structuredGeometry && this.geometry.length < 5 && Math.random() < 0.08 * dt) {
      this._spawnTradingGeometry();
    }

    if ((signature.circularWaves || signature.regionSync) && this.rings.length < 3 && Math.random() < 0.04 * dt) {
      this._spawnPlanningRing(signature.rhythmicPulse);
    }

    if (signature.distributedExploration && Math.random() < 0.03 * dt) {
      this._spawnExplorationSpark();
    }

    if (signature.signalFragmentation && this._errorAcc > 280) {
      this._errorAcc = 0;
      this._spawnErrorShard();
      if (Math.random() < 0.55) {
        this._spawnErrorShard(true);
      }
    }

    for (const f of this.fragments) {
      f.x += f.vx * dt;
      f.y += f.vy * dt;
      f.rot += f.vr * dt;
      if (f.erratic) {
        f.vx += (Math.random() - 0.5) * 0.0012 * dt;
        f.vy += (Math.random() - 0.5) * 0.0012 * dt;
      }
    }
  }

  /** @param {Array<{ alpha: number }>} list @param {number} decay */
  _fadeCollection(list, decay) {
    const remaining = [];
    for (const item of list) {
      item.alpha -= decay;
      if (item.alpha > 0.02) remaining.push(item);
    }
    list.length = 0;
    list.push(...remaining);
  }

  _spawnFragment(echo = false) {
    this.fragments.push({
      x: 0.2 + Math.random() * 0.6,
      y: 0.18 + Math.random() * 0.55,
      w: 6 + Math.random() * 14,
      h: 3 + Math.random() * 8,
      rot: Math.random() * Math.PI,
      vx: (Math.random() - 0.5) * 0.0008,
      vy: -0.0003 - Math.random() * 0.0006,
      vr: (Math.random() - 0.5) * 0.00004,
      alpha: echo ? 0.22 : 0.34,
      echo,
      spark: false,
      erratic: false,
    });
  }

  /** @param {boolean} [large] */
  _spawnErrorShard(large = false) {
    this.fragments.push({
      x: 0.15 + Math.random() * 0.7,
      y: 0.2 + Math.random() * 0.55,
      w: large ? 12 + Math.random() * 22 : 4 + Math.random() * 10,
      h: large ? 2 + Math.random() * 6 : 2 + Math.random() * 5,
      rot: Math.random() * Math.PI * 2,
      vx: (Math.random() - 0.5) * 0.003,
      vy: (Math.random() - 0.5) * 0.0025,
      vr: (Math.random() - 0.5) * 0.00012,
      alpha: large ? 0.48 : 0.32,
      echo: false,
      spark: !large,
      erratic: true,
    });
  }

  _spawnTradingGeometry() {
    this.geometry.push({
      cx: 0.35 + Math.random() * 0.3,
      cy: 0.32 + Math.random() * 0.28,
      size: 28 + Math.random() * 42,
      angle: Math.random() * Math.PI,
      alpha: 0.38,
      pulse: Math.random() * Math.PI * 2,
    });
  }

  /** @param {boolean} rhythmic */
  _spawnPlanningRing(rhythmic) {
    this.rings.push({
      cx: 0.38 + Math.random() * 0.24,
      cy: 0.34 + Math.random() * 0.22,
      radius: 18 + Math.random() * 36,
      alpha: rhythmic ? 0.42 : 0.3,
      speed: rhythmic ? 0.85 : 0.55,
      rhythmic,
    });
  }

  _spawnExplorationSpark() {
    this.fragments.push({
      x: Math.random(),
      y: Math.random(),
      w: 2 + Math.random() * 4,
      h: 2 + Math.random() * 4,
      rot: 0,
      vx: (Math.random() - 0.5) * 0.002,
      vy: (Math.random() - 0.5) * 0.0016,
      vr: 0,
      alpha: 0.2,
      echo: false,
      spark: true,
      erratic: false,
    });
  }

  /**
   * @param {CanvasRenderingContext2D} ctx
   * @param {number} w
   * @param {number} h
   * @param {object | null} signature
   * @param {import("./config.js").NEURAL_CONFIG["colors"]} colors
   */
  draw(ctx, w, h, signature, colors) {
    if (!signature) return;
    const redGlow = colors.redGlow;
    const whiteDim = colors.whiteDim;

    for (const f of this.fragments) {
      ctx.save();
      ctx.translate(f.x * w, f.y * h);
      ctx.rotate(f.rot);
      const tint = f.erratic ? redGlow : f.echo ? whiteDim : redGlow;
      ctx.fillStyle = `${tint}${f.alpha})`;
      if (f.spark) {
        ctx.beginPath();
        ctx.arc(0, 0, f.w, 0, Math.PI * 2);
        ctx.fill();
      } else {
        ctx.fillRect(-f.w * 0.5, -f.h * 0.5, f.w, f.h);
      }
      ctx.restore();
    }

    for (const geo of this.geometry) {
      geo.pulse += 0.04;
      const pulse = 0.65 + Math.sin(geo.pulse) * 0.35;
      const a = geo.alpha * pulse;
      ctx.save();
      ctx.translate(geo.cx * w, geo.cy * h);
      ctx.rotate(geo.angle);
      ctx.strokeStyle = `${redGlow}${a})`;
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      ctx.moveTo(-geo.size * 0.5, 0);
      ctx.lineTo(geo.size * 0.5, 0);
      ctx.moveTo(0, -geo.size * 0.35);
      ctx.lineTo(0, geo.size * 0.35);
      ctx.stroke();
      ctx.restore();
    }

    for (const ring of this.rings) {
      ring.radius += ring.speed;
      const ringAlpha = ring.alpha * (1 - ring.radius / (w * 0.42));
      if (ringAlpha <= 0.02) continue;
      const voiceMod = ring.rhythmic ? 0.75 + Math.sin(this._voicePhase * 3) * 0.25 : 1;
      ctx.beginPath();
      ctx.arc(ring.cx * w, ring.cy * h, ring.radius, 0, Math.PI * 2);
      ctx.strokeStyle = `${redGlow}${ringAlpha * voiceMod})`;
      ctx.lineWidth = ring.rhythmic ? 1.1 : 0.7;
      ctx.stroke();
    }
  }

  clear() {
    this.fragments.length = 0;
    this.geometry.length = 0;
    this.rings.length = 0;
  }
}
