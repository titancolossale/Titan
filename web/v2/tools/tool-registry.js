/** Titan Frontend V2 — Tool registry & region mapping (Phase E5). */

import { getCognitiveSignature } from "../neural/cognitive.js";

/**
 * Canonical tool ids — future tools register via ToolActivityEngine.registerTool().
 * @typedef {"memory"|"obsidian"|"browser"|"calendar"|"trading"|"voice"|"projects"|"chat"} ToolId
 */

/** @type {Record<string, object>} */
export const DEFAULT_TOOL_REGISTRY = Object.freeze({
  memory: {
    id: "memory",
    title: "Mémoire",
    icon: "◈",
    startLine: "Recherche en mémoire…",
    visualRegion: "memory",
    regions: ["memory"],
    cognitiveState: "memory_recall",
    hook: "memory_retrieval",
    waveStyle: "deep_central",
    priority: 6,
    energy: 0.75,
    focusWeight: 0.9,
    activityBase: 0.68,
    pulseIntervalMs: 1400,
    neuralEffects: {
      memoryFragments: true,
      neuralEchoes: true,
      preferDeep: true,
      longPaths: true,
      ghostActivity: true,
    },
  },
  obsidian: {
    id: "obsidian",
    title: "Obsidian",
    icon: "◈",
    startLine: "Consultation d'Obsidian…",
    visualRegion: "obsidian",
    regions: ["obsidian", "memory"],
    cognitiveState: "obsidian",
    hook: "tool_usage",
    waveStyle: "deep_central",
    priority: 5,
    energy: 0.62,
    focusWeight: 0.82,
    activityBase: 0.6,
    pulseIntervalMs: 1500,
    neuralEffects: {
      memoryFragments: true,
      ghostActivity: true,
      longPaths: true,
    },
  },
  browser: {
    id: "browser",
    title: "Exploration web",
    icon: "◎",
    startLine: "Navigation web…",
    visualRegion: "browser",
    regions: ["browser"],
    cognitiveState: "browser_research",
    hook: "browser_research",
    waveStyle: "distributed",
    priority: 7,
    energy: 0.88,
    focusWeight: 0.9,
    activityBase: 0.82,
    pulseIntervalMs: 1200,
    neuralEffects: {
      distributedExploration: true,
      distantRegions: true,
      longPaths: true,
    },
  },
  calendar: {
    id: "calendar",
    title: "Agenda",
    icon: "◷",
    startLine: "Lecture de l'agenda…",
    visualRegion: "calendar",
    regions: ["calendar", "planning"],
    cognitiveState: "calendar",
    hook: "tool_usage",
    waveStyle: "circular",
    priority: 5,
    energy: 0.58,
    focusWeight: 0.78,
    activityBase: 0.62,
    pulseIntervalMs: 1300,
    neuralEffects: {
      circularWaves: true,
      regionSync: true,
    },
  },
  trading: {
    id: "trading",
    title: "Marchés",
    icon: "◆",
    startLine: "Analyse des marchés…",
    visualRegion: "trading",
    regions: ["trading"],
    cognitiveState: "trading",
    hook: "tool_usage",
    waveStyle: "sharp",
    priority: 8,
    energy: 0.92,
    focusWeight: 0.95,
    activityBase: 0.85,
    pulseIntervalMs: 1100,
    neuralEffects: {
      sharpSignals: true,
      fastSync: true,
      structuredGeometry: true,
      localBursts: true,
    },
  },
  voice: {
    id: "voice",
    title: "Voix",
    icon: "◉",
    startLine: "Communication vocale…",
    visualRegion: "communication",
    regions: ["communication", "core"],
    cognitiveState: "voice",
    hook: "speaking",
    waveStyle: "circular",
    priority: 9,
    energy: 0.8,
    focusWeight: 0.88,
    activityBase: 0.76,
    pulseIntervalMs: 900,
    neuralEffects: {
      circularWaves: true,
      regionSync: true,
      rhythmicPulse: true,
      fastSync: true,
    },
  },
  projects: {
    id: "projects",
    title: "Projets",
    icon: "◐",
    startLine: "Gestion de projet…",
    visualRegion: "planning",
    regions: ["planning", "tools"],
    cognitiveState: "planning",
    hook: "brain_activity",
    waveStyle: "circular",
    priority: 4,
    energy: 0.55,
    focusWeight: 0.72,
    activityBase: 0.58,
    pulseIntervalMs: 1450,
    neuralEffects: {
      circularWaves: true,
      regionSync: true,
    },
  },
  chat: {
    id: "chat",
    title: "Conversation",
    icon: "◉",
    startLine: "Synthèse de réponse…",
    visualRegion: "core",
    regions: ["core", "communication"],
    cognitiveState: "writing",
    hook: "brain_activity",
    waveStyle: "distributed",
    priority: 3,
    energy: 0.48,
    focusWeight: 0.65,
    activityBase: 0.52,
    pulseIntervalMs: 1600,
    neuralEffects: {
      rhythmicPulse: true,
      focusComposer: true,
    },
  },
});

/** @param {string} raw */
export function normalizeToolId(raw) {
  if (!raw || typeof raw !== "string") return "chat";
  const key = raw.trim().toLowerCase().replace(/[\s-]+/g, "_");
  if (DEFAULT_TOOL_REGISTRY[key]) return key;
  if (key.includes("obsidian") || key.includes("vault") || key.includes("note")) return "obsidian";
  if (key.includes("browser") || key.includes("web")) return "browser";
  if (key.includes("calendar") || key.includes("agenda")) return "calendar";
  if (key.includes("trad") || key.includes("market")) return "trading";
  if (key.includes("memory") || key.includes("memo")) return "memory";
  if (key.includes("voice") || key.includes("speak")) return "voice";
  if (key.includes("project")) return "projects";
  if (key.includes("chat") || key.includes("conversation")) return "chat";
  return key in DEFAULT_TOOL_REGISTRY ? key : "chat";
}

/**
 * @param {string} toolId
 * @param {Record<string, object>} registry
 */
export function getToolDefinition(toolId, registry = DEFAULT_TOOL_REGISTRY) {
  const id = normalizeToolId(toolId);
  return registry[id] ?? registry.chat;
}

/**
 * Weighted blend of cognitive signatures from active tool instances.
 * Priority × energy determines dominance — never abrupt replacement.
 * @param {Array<{ definition: object, activity: number, energy: number, priority: number }>} instances
 */
export function blendToolSignatures(instances) {
  if (!instances.length) return null;

  let totalWeight = 0;
  /** @type {Record<string, number>} */
  const accum = {};
  /** @type {Record<string, boolean>} */
  const bools = {};

  for (const inst of instances) {
    const def = inst.definition;
    const weight = Math.max(0.05, (inst.priority ?? def.priority ?? 1) * (inst.energy ?? def.energy ?? 0.5));
    totalWeight += weight;

    const base = getCognitiveSignature(def.cognitiveState);
    const merged = { ...base, ...(def.neuralEffects ?? {}), waveStyle: def.waveStyle };

    for (const [key, value] of Object.entries(merged)) {
      if (typeof value === "number") {
        accum[key] = (accum[key] ?? 0) + value * weight;
      } else if (typeof value === "boolean" && value) {
        bools[key] = (bools[key] ?? 0) + weight;
      }
    }
  }

  /** @type {Record<string, unknown>} */
  const out = {};
  for (const [key, sum] of Object.entries(accum)) {
    out[key] = sum / totalWeight;
  }
  for (const [key, sum] of Object.entries(bools)) {
    out[key] = sum >= totalWeight * 0.35;
  }

  return out;
}

/**
 * @param {Array<{ definition: object, activity: number, energy: number, priority: number, focusWeight: number }>} instances
 */
export function blendToolRegions(instances) {
  /** @type {Map<string, number>} */
  const regionStrength = new Map();

  for (const inst of instances) {
    const def = inst.definition;
    const weight =
      (inst.focusWeight ?? def.focusWeight ?? 0.5) *
      (inst.activity ?? def.activityBase ?? 0.5) *
      (inst.energy ?? def.energy ?? 0.5);

    for (const regionId of def.regions ?? [def.visualRegion]) {
      const prev = regionStrength.get(regionId) ?? 0;
      regionStrength.set(regionId, Math.min(1, prev + weight * 0.55));
    }
  }

  return Array.from(regionStrength.entries()).map(([id, strength]) => ({ id, strength }));
}

/**
 * Dominant tool by priority × energy × activity.
 * @param {Array<{ id: string, definition: object, activity: number, energy: number, priority: number }>} instances
 */
export function resolveDominantTool(instances) {
  if (!instances.length) return null;

  let best = instances[0];
  let bestScore = -1;

  for (const inst of instances) {
    const score =
      (inst.priority ?? inst.definition.priority ?? 1) *
      (inst.energy ?? inst.definition.energy ?? 0.5) *
      (inst.activity ?? inst.definition.activityBase ?? 0.5);
    if (score > bestScore) {
      bestScore = score;
      best = inst;
    }
  }

  return best;
}
