/** Titan Frontend V2 — Neural Status Adapter (Sprint 2.7 Reference Composition).
 *
 * Pure, DOM-free translation layer. Maps StateStore → neural behavior +
 * per-subsystem satellite status. Never mutates backend state.
 */

/** Behavior modes for the neural stage. */
export const NEURAL_BEHAVIORS = Object.freeze({
  IDLE: "IDLE",
  LISTENING: "LISTENING",
  THINKING: "THINKING",
  EXECUTING: "EXECUTING",
  ERROR: "ERROR",
  OFFLINE: "OFFLINE",
});

/** Per-satellite visual status. */
export const SATELLITE_STATUS = Object.freeze({
  IDLE: "idle",
  ACTIVE: "active",
  WAITING: "waiting",
});

/**
 * Reference subsystem satellites (Sprint 2.7).
 * MEMORY · PLANNING · BROWSER · OBSIDIAN · TOOLS · COMMUNICATION · TRADING · CALENDAR
 */
export const SATELLITE_IDS = Object.freeze([
  "memory",
  "planning",
  "browser",
  "obsidian",
  "tools",
  "communication",
  "trading",
  "calendar",
]);

const EXECUTING_STATES = Object.freeze([
  "tool_execution",
  "browser_research",
  "obsidian",
  "calendar",
  "trading",
]);

const THINKING_STATES = Object.freeze([
  "thinking",
  "reasoning",
  "planning",
  "writing",
  "memory_recall",
]);

const ONLINE_CONNECTION = Object.freeze(["connected", "streaming", "connecting"]);

const COGNITIVE_SATELLITE_MAP = Object.freeze({
  idle: [],
  sleep: [],
  listening: ["communication"],
  voice: ["communication"],
  thinking: ["planning", "communication"],
  reasoning: ["planning", "memory"],
  planning: ["planning", "calendar"],
  memory_recall: ["memory", "obsidian"],
  writing: ["communication", "obsidian"],
  tool_execution: ["tools"],
  browser_research: ["browser", "tools"],
  obsidian: ["obsidian", "memory"],
  calendar: ["calendar", "planning"],
  trading: ["trading", "tools"],
  error: [],
});

const TOOL_SATELLITE_MAP = Object.freeze({
  memory: "memory",
  obsidian: "obsidian",
  browser: "browser",
  tools: "tools",
  calendar: "calendar",
  trading: "trading",
  voice: "communication",
  chat: "communication",
  projects: "planning",
});

const BEHAVIOR_WAITING = Object.freeze({
  [NEURAL_BEHAVIORS.THINKING]: ["memory", "obsidian", "planning"],
  [NEURAL_BEHAVIORS.EXECUTING]: ["planning", "tools", "communication"],
  [NEURAL_BEHAVIORS.LISTENING]: [],
  [NEURAL_BEHAVIORS.IDLE]: [],
  [NEURAL_BEHAVIORS.ERROR]: [],
  [NEURAL_BEHAVIORS.OFFLINE]: [],
});

/**
 * @param {Partial<import("../core/state-store.js").AppState>} state
 * @returns {string}
 */
export function resolveBehavior(state = {}) {
  if (state.lastError) {
    return NEURAL_BEHAVIORS.ERROR;
  }

  const connection = state.connectionState ?? "disconnected";
  if (state.bootComplete && !ONLINE_CONNECTION.includes(connection)) {
    return NEURAL_BEHAVIORS.OFFLINE;
  }

  const cognitive = state.cognitiveState ?? "idle";

  if (cognitive === "listening" || cognitive === "voice" || state.presence === "listening") {
    return NEURAL_BEHAVIORS.LISTENING;
  }

  if ((state.activeToolCount ?? 0) > 0 || EXECUTING_STATES.includes(cognitive)) {
    return NEURAL_BEHAVIORS.EXECUTING;
  }

  if (THINKING_STATES.includes(cognitive) || state.recallActive || state.presence === "thinking") {
    return NEURAL_BEHAVIORS.THINKING;
  }

  return NEURAL_BEHAVIORS.IDLE;
}

/**
 * @param {Partial<import("../core/state-store.js").AppState>} state
 * @returns {{ behavior: string, satellites: Record<string, string>, active: string[], waiting: string[] }}
 */
export function resolveNeuralStatus(state = {}) {
  const behavior = resolveBehavior(state);

  /** @type {Record<string, string>} */
  const satellites = {};
  for (const id of SATELLITE_IDS) {
    satellites[id] = SATELLITE_STATUS.IDLE;
  }

  if (behavior === NEURAL_BEHAVIORS.OFFLINE || behavior === NEURAL_BEHAVIORS.ERROR) {
    return { behavior, satellites, active: [], waiting: [] };
  }

  const cognitive = state.cognitiveState ?? "idle";
  const active = new Set(COGNITIVE_SATELLITE_MAP[cognitive] ?? []);

  for (const toolId of state.activeToolIds ?? []) {
    const satellite = TOOL_SATELLITE_MAP[toolId];
    if (satellite) {
      active.add(satellite);
    }
  }

  const waiting = new Set();
  for (const id of BEHAVIOR_WAITING[behavior] ?? []) {
    if (!active.has(id)) {
      waiting.add(id);
    }
  }

  for (const id of SATELLITE_IDS) {
    if (active.has(id)) {
      satellites[id] = SATELLITE_STATUS.ACTIVE;
    } else if (waiting.has(id)) {
      satellites[id] = SATELLITE_STATUS.WAITING;
    }
  }

  return {
    behavior,
    satellites,
    active: [...active].filter((id) => SATELLITE_IDS.includes(id)),
    waiting: [...waiting],
  };
}
