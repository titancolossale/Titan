/** Titan Frontend V2 — Memory type registry & neural signatures (Phase E6). */

/** Canonical memory type ids. */
export const MEMORY_TYPES = Object.freeze([
  "conversation",
  "long_term",
  "working",
  "project",
  "obsidian",
  "temporary_context",
  "future",
]);

export const MEMORY_ACTIVITY_EVENTS = Object.freeze({
  CREATED: "memory_created",
  UPDATED: "memory_updated",
  RECALLED: "memory_recalled",
  SEARCH: "memory_search",
  SUMMARY: "memory_summary",
  LINKED: "memory_linked",
  ARCHIVED: "memory_archived",
  DELETED: "memory_deleted",
  BLEND_UPDATED: "memory_blend_updated",
});

/** User-facing source presentation — thematic labels only. */
export const DEFAULT_MEMORY_REGISTRY = Object.freeze({
  conversation: {
    id: "conversation",
    title: "Conversation",
    icon: "○",
    neuralRegion: "memory",
    importanceBase: 0.55,
    focusWeight: 0.62,
    waveStyle: "deep_central",
    statusLine: "Fil de la conversation…",
  },
  long_term: {
    id: "long_term",
    title: "Souvenirs permanents",
    icon: "◈",
    neuralRegion: "memory",
    importanceBase: 0.78,
    focusWeight: 0.82,
    waveStyle: "slow",
    statusLine: "Souvenirs en éveil…",
  },
  working: {
    id: "working",
    title: "Mémoire de travail",
    icon: "◉",
    neuralRegion: "core",
    importanceBase: 0.48,
    focusWeight: 0.55,
    waveStyle: "central",
    statusLine: "Contexte actif…",
  },
  project: {
    id: "project",
    title: "Projet",
    icon: "◐",
    neuralRegion: "planning",
    importanceBase: 0.65,
    focusWeight: 0.68,
    waveStyle: "default",
    statusLine: "Contexte du projet…",
  },
  obsidian: {
    id: "obsidian",
    title: "Notes Obsidian",
    icon: "◇",
    neuralRegion: "obsidian",
    importanceBase: 0.72,
    focusWeight: 0.74,
    waveStyle: "geometric",
    statusLine: "Consultation des notes…",
  },
  temporary_context: {
    id: "temporary_context",
    title: "Contexte temporaire",
    icon: "◌",
    neuralRegion: "core",
    importanceBase: 0.32,
    focusWeight: 0.38,
    waveStyle: "default",
    statusLine: "Contexte éphémère…",
  },
  future: {
    id: "future",
    title: "Source future",
    icon: "◫",
    neuralRegion: "memory",
    importanceBase: 0.4,
    focusWeight: 0.45,
    waveStyle: "central",
    statusLine: "Mémoire externe…",
  },
  default: {
    id: "long_term",
    title: "Souvenirs",
    icon: "◈",
    neuralRegion: "memory",
    importanceBase: 0.6,
    focusWeight: 0.65,
    waveStyle: "central",
    statusLine: "Mémoire active…",
  },
});

/**
 * Neural signature overlays per memory event (TITAN_NEURAL_ENGINE + Phase E6 spec).
 * @type {Record<string, object>}
 */
export const EVENT_NEURAL_SIGNATURES = Object.freeze({
  memory_created: {
    signalDensity: 0.58,
    signalBrightness: 0.72,
    connectionIntensity: 0.55,
    nodeActivityMult: 0.68,
    glowLevel: 0.62,
    cameraDive: 0.08,
    focusPull: 0.22,
    waveStyle: "central",
    waveBurst: 2,
    localBursts: true,
    preferDeep: false,
    ghostActivity: false,
    distributedExploration: false,
    longPaths: false,
    memoryFragments: false,
    neuralEchoes: false,
    regionSync: true,
  },
  memory_updated: {
    signalDensity: 0.48,
    signalBrightness: 0.65,
    connectionIntensity: 0.5,
    nodeActivityMult: 0.52,
    glowLevel: 0.55,
    cameraDive: 0.04,
    focusPull: 0.18,
    waveStyle: "default",
    waveBurst: 1,
    localBursts: true,
    preferDeep: false,
    ghostActivity: false,
    distributedExploration: false,
    longPaths: false,
    memoryFragments: false,
    neuralEchoes: false,
    regionSync: false,
  },
  memory_recalled: {
    signalDensity: 0.82,
    signalBrightness: 0.92,
    connectionIntensity: 0.72,
    nodeActivityMult: 0.78,
    glowLevel: 0.78,
    cameraDive: 0.42,
    focusPull: 0.55,
    waveStyle: "deep_central",
    waveBurst: 3,
    localBursts: false,
    preferDeep: true,
    ghostActivity: true,
    distributedExploration: false,
    longPaths: true,
    memoryFragments: true,
    neuralEchoes: true,
    regionSync: false,
  },
  memory_search: {
    signalDensity: 0.62,
    signalBrightness: 0.58,
    connectionIntensity: 0.48,
    nodeActivityMult: 0.55,
    glowLevel: 0.52,
    cameraDive: 0.12,
    focusPull: 0.28,
    waveStyle: "distributed",
    waveBurst: 1,
    localBursts: false,
    preferDeep: false,
    ghostActivity: false,
    distributedExploration: true,
    longPaths: true,
    memoryFragments: false,
    neuralEchoes: false,
    regionSync: false,
    rhythmicPulse: true,
  },
  memory_summary: {
    signalDensity: 0.7,
    signalBrightness: 0.8,
    connectionIntensity: 0.68,
    nodeActivityMult: 0.72,
    glowLevel: 0.68,
    cameraDive: 0.22,
    focusPull: 0.42,
    waveStyle: "central",
    waveBurst: 2,
    localBursts: false,
    preferDeep: true,
    ghostActivity: false,
    distributedExploration: false,
    longPaths: false,
    memoryFragments: true,
    neuralEchoes: false,
    regionSync: true,
    structuredGeometry: true,
  },
  memory_linked: {
    signalDensity: 0.66,
    signalBrightness: 0.85,
    connectionIntensity: 0.88,
    nodeActivityMult: 0.64,
    glowLevel: 0.7,
    cameraDive: 0.15,
    focusPull: 0.38,
    waveStyle: "default",
    waveBurst: 2,
    localBursts: false,
    preferDeep: false,
    ghostActivity: false,
    distributedExploration: false,
    longPaths: true,
    memoryFragments: false,
    neuralEchoes: true,
    regionSync: true,
    circularWaves: true,
  },
  memory_archived: {
    signalDensity: 0.28,
    signalBrightness: 0.42,
    connectionIntensity: 0.32,
    nodeActivityMult: 0.22,
    glowLevel: 0.38,
    cameraDive: 0.28,
    focusPull: 0.12,
    waveStyle: "slow",
    waveBurst: 1,
    localBursts: false,
    preferDeep: true,
    ghostActivity: true,
    distributedExploration: false,
    longPaths: false,
    memoryFragments: false,
    neuralEchoes: false,
    regionSync: false,
    distantRegions: true,
  },
  memory_deleted: {
    signalDensity: 0.18,
    signalBrightness: 0.32,
    connectionIntensity: 0.2,
    nodeActivityMult: 0.12,
    glowLevel: 0.28,
    cameraDive: 0.08,
    focusPull: 0.08,
    waveStyle: "slow",
    waveBurst: 1,
    localBursts: false,
    preferDeep: false,
    ghostActivity: false,
    distributedExploration: false,
    longPaths: false,
    memoryFragments: false,
    neuralEchoes: false,
    regionSync: false,
    distantRegions: true,
  },
});

/** @param {string} raw */
export function normalizeMemoryType(raw) {
  if (!raw) return "long_term";
  const key = String(raw).toLowerCase().replace(/[^a-z0-9_]/g, "_");
  if (DEFAULT_MEMORY_REGISTRY[key]) return key;
  if (key.includes("obsidian") || key.includes("vault")) return "obsidian";
  if (key.includes("conversation") || key.includes("dialogue")) return "conversation";
  if (key.includes("working") || key.includes("session")) return "working";
  if (key.includes("project") || key.includes("projet")) return "project";
  if (key.includes("temp") || key.includes("context")) return "temporary_context";
  return "long_term";
}

/**
 * @param {string} typeKey
 * @param {Record<string, object>} [registry]
 */
export function getMemoryDefinition(typeKey, registry = DEFAULT_MEMORY_REGISTRY) {
  const id = normalizeMemoryType(typeKey);
  return registry[id] ?? registry.default;
}

/**
 * @param {string} eventType
 * @param {object} memory
 * @param {object} [typeDef]
 */
export function getEventNeuralSignature(eventType, memory, typeDef) {
  const base = EVENT_NEURAL_SIGNATURES[eventType] ?? EVENT_NEURAL_SIGNATURES.memory_recalled;
  const importance = memory.importance ?? typeDef?.importanceBase ?? 0.5;
  const energy = memory.energy ?? importance;
  const focus = memory.focusWeight ?? typeDef?.focusWeight ?? 0.6;

  return {
    ...base,
    signalDensity: base.signalDensity * (0.75 + energy * 0.35),
    signalBrightness: base.signalBrightness * (0.8 + importance * 0.25),
    connectionIntensity: base.connectionIntensity * (0.7 + focus * 0.4),
    nodeActivityMult: base.nodeActivityMult * (0.65 + energy * 0.45),
    glowLevel: base.glowLevel * (0.7 + importance * 0.35),
    cameraDive: base.cameraDive * (0.6 + focus * 0.5),
    focusPull: base.focusPull * focus,
    waveStyle: typeDef?.waveStyle ?? base.waveStyle,
  };
}

/**
 * Blend active memory events into a single neural overlay signature.
 * @param {Array<{ eventType: string, memory: object, weight: number }>} events
 */
export function blendMemorySignatures(events) {
  if (!events.length) return null;

  const keys = [
    "signalDensity",
    "signalBrightness",
    "connectionIntensity",
    "nodeActivityMult",
    "glowLevel",
    "cameraDive",
    "focusPull",
    "waveBurst",
  ];
  const boolKeys = [
    "preferDeep",
    "ghostActivity",
    "distributedExploration",
    "longPaths",
    "memoryFragments",
    "neuralEchoes",
    "regionSync",
    "localBursts",
    "circularWaves",
    "structuredGeometry",
    "distantRegions",
    "rhythmicPulse",
  ];

  let totalWeight = 0;
  /** @type {Record<string, number>} */
  const acc = {};
  /** @type {Record<string, boolean>} */
  const boolAcc = {};

  for (const entry of events) {
    const def = getMemoryDefinition(entry.memory.type);
    const sig = getEventNeuralSignature(entry.eventType, entry.memory, def);
    const w = entry.weight ?? entry.memory.focusWeight ?? 0.5;
    totalWeight += w;

    for (const key of keys) {
      acc[key] = (acc[key] ?? 0) + (sig[key] ?? 0) * w;
    }
    for (const key of boolKeys) {
      if (sig[key]) boolAcc[key] = true;
    }
  }

  if (totalWeight <= 0) return null;

  /** @type {Record<string, number | boolean | string>} */
  const blended = {};
  for (const key of keys) {
    blended[key] = acc[key] / totalWeight;
  }
  for (const key of boolKeys) {
    blended[key] = Boolean(boolAcc[key]);
  }

  const dominant = events.reduce((a, b) =>
    (b.weight ?? b.memory.focusWeight ?? 0) > (a.weight ?? a.memory.focusWeight ?? 0) ? b : a,
  );
  const domDef = getMemoryDefinition(dominant.memory.type);
  blended.waveStyle =
    EVENT_NEURAL_SIGNATURES[dominant.eventType]?.waveStyle ?? domDef.waveStyle ?? "central";

  return blended;
}

/**
 * Map memory type to neural region focus keys.
 * @param {string} typeKey
 */
export function mapMemoryToRegions(typeKey) {
  const def = getMemoryDefinition(typeKey);
  const region = def.neuralRegion ?? "memory";
  if (region === "obsidian") return [{ id: "obsidian", strength: 0.85 }, { id: "memory", strength: 0.55 }];
  if (region === "planning") return [{ id: "planning", strength: 0.75 }, { id: "memory", strength: 0.45 }];
  if (region === "core") return [{ id: "core", strength: 0.65 }, { id: "memory", strength: 0.4 }];
  return [{ id: "memory", strength: 0.88 }];
}
