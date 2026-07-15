/** Titan Neural Renderer V2 — Node class taxonomy. */

export const NODE_CLASSES = Object.freeze({
  CORE: "core",
  MEMORY: "memory",
  REASONING: "reasoning",
  PLANNING: "planning",
  COMMUNICATION: "communication",
  TOOL: "tool",
  GHOST: "ghost",
  IDLE: "idle",
});

/** @typedef {"core"|"memory"|"reasoning"|"planning"|"communication"|"tool"|"ghost"|"idle"} NodeClassId */

/**
 * Normalized world-region anchors (0–1) aligned to shell region anchors.
 * @type {Record<string, { x: number, y: number, radius: number, class: NodeClassId }>}
 */
/** Anchors aligned with cognitive satellite ring (CSS) + canvas depth regions. */
export const REGION_ANCHORS = {
  core: { x: 0.5, y: 0.44, radius: 0.15, class: NODE_CLASSES.CORE },
  memory: { x: 0.2, y: 0.21, radius: 0.11, class: NODE_CLASSES.MEMORY },
  reasoning: { x: 0.5, y: 0.1, radius: 0.12, class: NODE_CLASSES.REASONING },
  knowledge: { x: 0.8, y: 0.21, radius: 0.1, class: NODE_CLASSES.MEMORY },
  tools: { x: 0.9, y: 0.45, radius: 0.1, class: NODE_CLASSES.TOOL },
  workflow: { x: 0.79, y: 0.71, radius: 0.1, class: NODE_CLASSES.TOOL },
  planning: { x: 0.5, y: 0.82, radius: 0.11, class: NODE_CLASSES.PLANNING },
  world_model: { x: 0.21, y: 0.71, radius: 0.1, class: NODE_CLASSES.REASONING },
  communication: { x: 0.1, y: 0.45, radius: 0.11, class: NODE_CLASSES.COMMUNICATION },
  browser: { x: 0.82, y: 0.22, radius: 0.09, class: NODE_CLASSES.TOOL },
  obsidian: { x: 0.11, y: 0.46, radius: 0.08, class: NODE_CLASSES.TOOL },
  trading: { x: 0.5, y: 0.84, radius: 0.08, class: NODE_CLASSES.REASONING },
  calendar: { x: 0.9, y: 0.78, radius: 0.08, class: NODE_CLASSES.PLANNING },
};

/** @param {NodeClassId} nodeClass */
export function getSignalColorKey(nodeClass) {
  switch (nodeClass) {
    case NODE_CLASSES.MEMORY:
      return "signalMemory";
    case NODE_CLASSES.PLANNING:
      return "signalPlanning";
    case NODE_CLASSES.REASONING:
      return "redCrimson";
    case NODE_CLASSES.COMMUNICATION:
      return "signalVoice";
    case NODE_CLASSES.TOOL:
      return "signalBrowser";
    case NODE_CLASSES.CORE:
      return "redGlow";
    default:
      return "redGlow";
  }
}

/**
 * Assign node class from world position relative to cognitive regions.
 * @param {number} wx
 * @param {number} wy
 * @param {number} worldWidth
 * @param {number} worldHeight
 * @param {number} layerIdx
 * @returns {NodeClassId}
 */
export function assignNodeClass(wx, wy, worldWidth, worldHeight, layerIdx) {
  const nx = wx / worldWidth;
  const ny = wy / worldHeight;

  let best = null;
  let bestDist = Infinity;

  for (const anchor of Object.values(REGION_ANCHORS)) {
    const dx = nx - anchor.x;
    const dy = ny - anchor.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < anchor.radius && dist < bestDist) {
      bestDist = dist;
      best = anchor;
    }
  }

  if (best) {
    return best.class;
  }

  if (layerIdx <= 1) {
    return NODE_CLASSES.IDLE;
  }
  if (layerIdx >= 3) {
    return NODE_CLASSES.REASONING;
  }
  return NODE_CLASSES.IDLE;
}

/**
 * Create extended node properties per spec.
 * @param {NodeClassId} nodeClass
 * @returns {{ energy: number, temperature: number, activity: number, connectionCount: number, state: string }}
 */
export function createNodeVitality(nodeClass) {
  const base = nodeClass === NODE_CLASSES.CORE ? 0.72 : nodeClass === NODE_CLASSES.IDLE ? 0.18 : 0.42;
  return {
    energy: base + Math.random() * 0.28,
    temperature: 0.1 + Math.random() * 0.35,
    activity: 0,
    connectionCount: 0,
    state: "idle",
  };
}
