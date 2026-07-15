/** Titan Frontend V2 — Phase 9 Cognitive Operating System telemetry.
 * Pure frontend mapping of StateStore / CognitiveStateEngine → module states.
 * Never invents backend execution. Never mutates Brain / API / memory systems.
 */

/**
 * Canonical per-module cognitive states (presentation telemetry).
 * @typedef {"idle"|"reading"|"searching"|"planning"|"reasoning"|"writing"|"waiting"|"finished"} ModuleCognitiveState
 */

/** @type {readonly ModuleCognitiveState[]} */
export const MODULE_COGNITIVE_STATES = Object.freeze([
  "idle",
  "reading",
  "searching",
  "planning",
  "reasoning",
  "writing",
  "waiting",
  "finished",
]);

/** French display labels for module cognitive states (canonical final reference). */
export const MODULE_STATE_LABELS = Object.freeze({
  idle: "En veille",
  reading: "Lecture",
  searching: "Recherche",
  planning: "Planification",
  reasoning: "Thinking",
  writing: "Écriture",
  waiting: "En attente",
  finished: "Terminé",
});

/**
 * @param {string | null | undefined} value
 * @returns {ModuleCognitiveState}
 */
export function normalizeModuleState(value) {
  const key = String(value || "idle").toLowerCase();
  return MODULE_COGNITIVE_STATES.includes(/** @type {ModuleCognitiveState} */ (key))
    ? /** @type {ModuleCognitiveState} */ (key)
    : "idle";
}

/**
 * @param {import("./state-store.js").AppState} state
 * @returns {boolean}
 */
function isConnected(state) {
  return state.connectionState === "connected" || state.connectionState === "streaming";
}

/**
 * @param {import("./state-store.js").AppState} state
 * @returns {boolean}
 */
function isThinking(state) {
  const cognitive = String(state.cognitiveState || "").toLowerCase();
  return Boolean(
    state.pipelineThinking
    || state.presence === "thinking"
    || cognitive === "thinking"
    || cognitive === "reasoning",
  );
}

/**
 * @param {import("./state-store.js").AppState} state
 * @returns {boolean}
 */
function isPlanning(state) {
  return (
    String(state.cognitiveState || "").toLowerCase() === "planning"
    || state.presence === "planning"
    || state.conversationStage === "planning"
  );
}

/**
 * @param {import("./state-store.js").AppState} state
 * @returns {boolean}
 */
function isWriting(state) {
  const cognitive = String(state.cognitiveState || "").toLowerCase();
  return (
    cognitive === "writing"
    || state.presence === "streaming"
    || state.presence === "speaking"
    || state.conversationStage === "writing"
    || state.connectionState === "streaming"
  );
}

/**
 * @param {import("./state-store.js").AppState} state
 * @returns {string[]}
 */
function toolIds(state) {
  return Array.isArray(state.activeToolIds) ? state.activeToolIds : [];
}

/**
 * Memory module telemetry.
 * @param {import("./state-store.js").AppState} state
 * @returns {ModuleCognitiveState}
 */
export function resolveMemoryModuleState(state) {
  const cognitive = String(state.cognitiveState || "").toLowerCase();
  if (state.recallActive || cognitive === "memory_recall") return "reading";
  if (state.memoryEventType === "write" || state.memoryEventType === "remember") {
    return "writing";
  }
  if (isConnected(state) && state.conversationActive && !state.recallActive) {
    return "waiting";
  }
  if (
    state.memoryEventType === "complete"
    || state.conversationEventType === "memory_complete"
  ) {
    return "finished";
  }
  return "idle";
}

/**
 * Reflection / reasoning module telemetry.
 * @param {import("./state-store.js").AppState} state
 * @returns {ModuleCognitiveState}
 */
export function resolveReflectionModuleState(state) {
  if (isWriting(state)) return "writing";
  if (isPlanning(state)) return "planning";
  if (isThinking(state)) return "reasoning";
  if (state.conversationActive && !isThinking(state) && !isWriting(state)) {
    return "waiting";
  }
  if (
    !state.conversationActive
    && !state.pipelineThinking
    && (state.conversationStage === "complete" || state.conversationEventType === "complete")
  ) {
    return "finished";
  }
  return "idle";
}

/**
 * Presence module telemetry.
 * @param {import("./state-store.js").AppState} state
 * @returns {ModuleCognitiveState}
 */
export function resolvePresenceModuleState(state) {
  if (state.connectionState === "connecting") return "waiting";
  if (!isConnected(state)) return "waiting";
  if (isWriting(state)) return "writing";
  if (isPlanning(state)) return "planning";
  if (isThinking(state)) return "reasoning";
  if (state.presence === "listening" || state.cognitiveState === "listening") {
    return "reading";
  }
  if (state.presence === "working" || (state.activeToolCount ?? 0) > 0) {
    return "searching";
  }
  return "idle";
}

/**
 * Tools module telemetry.
 * @param {import("./state-store.js").AppState} state
 * @returns {ModuleCognitiveState}
 */
export function resolveToolsModuleState(state) {
  const ids = toolIds(state);
  const cognitive = String(state.cognitiveState || "").toLowerCase();
  if (ids.includes("browser") || cognitive === "browser_research") return "searching";
  if (ids.includes("obsidian") || cognitive === "obsidian") return "reading";
  if (ids.includes("memory") || cognitive === "memory_recall") return "reading";
  if ((state.activeToolCount ?? 0) > 0 || cognitive === "tool_execution") return "writing";
  if (isPlanning(state) && (state.activeToolCount ?? 0) === 0) return "planning";
  if (state.conversationActive && (state.activeToolCount ?? 0) === 0) return "waiting";
  return "idle";
}

/**
 * Brain (mode) module telemetry — dominant cognitive surface.
 * @param {import("./state-store.js").AppState} state
 * @returns {ModuleCognitiveState}
 */
export function resolveBrainModuleState(state) {
  const tools = resolveToolsModuleState(state);
  if (tools === "searching") return "searching";
  if (resolveMemoryModuleState(state) === "reading") return "reading";
  if (isWriting(state)) return "writing";
  if (isPlanning(state)) return "planning";
  if (isThinking(state)) return "reasoning";
  if (!isConnected(state) || state.connectionState === "connecting") return "waiting";
  if (state.conversationActive) return "waiting";
  if (
    state.conversationStage === "complete"
    || state.conversationEventType === "complete"
  ) {
    return "finished";
  }
  return "idle";
}

/**
 * Runtime module telemetry.
 * @param {import("./state-store.js").AppState} state
 * @returns {ModuleCognitiveState}
 */
export function resolveRuntimeModuleState(state) {
  if (state.connectionState === "connecting") return "waiting";
  if (!isConnected(state)) return "waiting";
  if (isWriting(state)) return "writing";
  if (isPlanning(state)) return "planning";
  if (isThinking(state) || (state.activeToolCount ?? 0) > 0) return "reasoning";
  if (
    typeof state.orchestrationDuration === "number"
    && !state.conversationActive
    && !state.pipelineThinking
  ) {
    return "finished";
  }
  return "idle";
}

/**
 * Snapshot of all top-bar module states from honest frontend state.
 * @param {import("./state-store.js").AppState} state
 */
export function resolveModuleTelemetry(state) {
  return {
    memory: resolveMemoryModuleState(state),
    reflection: resolveReflectionModuleState(state),
    presence: resolvePresenceModuleState(state),
    tools: resolveToolsModuleState(state),
    brain: resolveBrainModuleState(state),
    runtime: resolveRuntimeModuleState(state),
  };
}

/**
 * Dominant OS runtime label for atmosphere / root dataset.
 * @param {import("./state-store.js").AppState} state
 * @returns {ModuleCognitiveState}
 */
export function resolveDominantOsState(state) {
  return resolveBrainModuleState(state);
}

/**
 * Confidence display — only from orchestrationConfidence when present.
 * @param {import("./state-store.js").AppState} state
 * @returns {string}
 */
export function formatConfidence(state) {
  const conf = state.orchestrationConfidence;
  if (typeof conf === "number" && Number.isFinite(conf)) {
    const pct = conf <= 1 ? Math.round(conf * 100) : Math.round(conf);
    return `${Math.max(0, Math.min(100, pct))}%`;
  }
  return "—";
}

/**
 * Reasoning depth label from pipeline / conversation stage.
 * @param {import("./state-store.js").AppState} state
 * @returns {string}
 */
export function formatReasoningDepth(state) {
  if (state.pipelineThinking || state.presence === "thinking") return "Profonde";
  if (isPlanning(state)) return "Structurée";
  if (state.conversationActive) return "Modérée";
  return "Calme";
}

/**
 * Attention label from presence level + activity.
 * @param {import("./state-store.js").AppState} state
 * @returns {string}
 */
export function formatAttention(state) {
  const level = typeof state.presenceLevel === "number" ? state.presenceLevel : 42;
  if (!isConnected(state)) return "Hors ligne";
  if (isThinking(state) || (state.activeToolCount ?? 0) > 0) return "Focalisée";
  if (level >= 70) return "Élevée";
  if (level >= 40) return "Stable";
  return "Diffuse";
}

/**
 * Latency label from orchestrationDuration only.
 * @param {import("./state-store.js").AppState} state
 * @returns {string}
 */
export function formatLatency(state) {
  const duration = state.orchestrationDuration;
  if (typeof duration !== "number" || !Number.isFinite(duration)) return "—";
  return duration < 1
    ? `${Math.round(duration * 1000)} ms`
    : `${duration.toFixed(1)} s`;
}

/**
 * Model / system state label — honest connection + cognitive surface.
 * @param {import("./state-store.js").AppState} state
 * @returns {string}
 */
export function formatModelState(state) {
  if (state.connectionState === "connecting") return "Connexion…";
  if (!isConnected(state)) return "Hors ligne";
  if (isWriting(state)) return "Génération";
  if (isThinking(state)) return "Inférence";
  if (isPlanning(state)) return "Planification";
  if ((state.activeToolCount ?? 0) > 0) return "Outils";
  return "Veille";
}

/**
 * Connected systems count from systemsUsed or tool catalog baseline.
 * @param {import("./state-store.js").AppState} state
 * @param {number} [catalogBaseline=6]
 * @returns {{ count: number, labels: string[] }}
 */
export function formatConnectedSystems(state, catalogBaseline = 6) {
  const systems = state.systemsUsed;
  if (systems && typeof systems === "object") {
    const labels = Object.keys(systems).filter((key) => {
      const value = systems[key];
      return value !== null && value !== undefined && value !== false;
    });
    if (labels.length > 0) {
      return { count: labels.length, labels };
    }
  }
  return { count: catalogBaseline, labels: [] };
}

/**
 * Planning queue — conversationPlanSteps when present; empty otherwise.
 * @param {import("./state-store.js").AppState} state
 * @returns {string[]}
 */
export function formatPlanningQueue(state) {
  return Array.isArray(state.conversationPlanSteps)
    ? state.conversationPlanSteps.filter((step) => typeof step === "string" && step.trim())
    : [];
}

/**
 * Reasoning stage line from existing pipeline / conversation fields.
 * @param {import("./state-store.js").AppState} state
 * @returns {string}
 */
export function formatReasoningStage(state) {
  if (state.pipelineLabel) return state.pipelineLabel.slice(0, 72);
  if (state.pipelineStage) return String(state.pipelineStage).slice(0, 72);
  if (state.conversationReasoningLine) return state.conversationReasoningLine.slice(0, 72);
  if (state.conversationThinkingLine) return state.conversationThinkingLine.slice(0, 72);
  if (isPlanning(state)) return "Planification";
  if (isThinking(state)) return "Raisonnement";
  if (isWriting(state)) return "Synthèse";
  return "En réserve";
}

/**
 * Current objective line — honest idle when quiet.
 * @param {import("./state-store.js").AppState} state
 * @param {string} [cognitiveLabel="Idle"]
 * @returns {string}
 */
export function formatCurrentObjective(state, cognitiveLabel = "Idle") {
  if (state.conversationThinkingLine) return state.conversationThinkingLine.slice(0, 96);
  if (state.pipelineLabel) return state.pipelineLabel.slice(0, 96);
  if (state.reasoningSummary) return state.reasoningSummary.slice(0, 96);
  if (state.detectedIntent) return String(state.detectedIntent).slice(0, 96);
  if (isThinking(state) || state.conversationActive) {
    return `Activité — ${String(cognitiveLabel).toLowerCase()}`;
  }
  /* Honest idle fallback — canonical reference presentation */
  return "Comprendre et assister";
}

/**
 * Memory access line for runtime monitor.
 * @param {import("./state-store.js").AppState} state
 * @returns {string}
 */
export function formatMemoryAccess(state) {
  if (state.recallActive) {
    const count = state.activeMemoryCount || 1;
    return `${count} rappel${count > 1 ? "s" : ""} actifs`;
  }
  if (state.memoryStatusLine && state.memoryStatusLine !== "Mémoire — en veille") {
    return state.memoryStatusLine.slice(0, 48);
  }
  return "Aucune lecture";
}

/**
 * Engagement / focus / availability for Presence workspace.
 * @param {import("./state-store.js").AppState} state
 */
export function formatPresenceSurface(state) {
  const level = typeof state.presenceLevel === "number" ? state.presenceLevel : 42;
  const connected = isConnected(state);
  const busy = isThinking(state) || (state.activeToolCount ?? 0) > 0 || isWriting(state);
  return {
    engagement: !connected ? "Hors ligne" : busy ? "Engagé" : level >= 60 ? "Présent" : "Calme",
    focus: formatAttention(state),
    availability: !connected
      ? "Indisponible"
      : busy
        ? "Occupé"
        : "Disponible",
  };
}
