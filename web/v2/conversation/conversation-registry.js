/** Titan Frontend V2 — Conversation Activity Registry (Phase E7). */

/** @typedef {"received"|"analysis"|"memory"|"reasoning"|"tool_selection"|"tool_execution"|"response"|"memory_store"|"finished"} ConversationStageId */

export const CONVERSATION_ACTIVITY_EVENTS = Object.freeze({
  RECEIVED: "conversation_received",
  ANALYSIS: "conversation_analysis",
  MEMORY: "conversation_memory",
  REASONING: "conversation_reasoning",
  TOOL_SELECTION: "conversation_tool_selection",
  TOOL_EXECUTION: "conversation_tool_execution",
  RESPONSE: "conversation_response",
  MEMORY_STORE: "conversation_memory_store",
  FINISHED: "conversation_finished",
});

/**
 * Neural signatures per conversation stage — TITAN_NEURAL_ENGINE + Animation Guide.
 * @type {Record<ConversationStageId, object>}
 */
export const CONVERSATION_STAGE_SIGNATURES = Object.freeze({
  received: {
    cognitiveState: "listening",
    masterState: "LISTENING",
    hook: "voice",
    regions: [
      { id: "communication", strength: 0.88 },
      { id: "core", strength: 0.72 },
    ],
    waveStyle: "wide_inbound",
    focusComposer: true,
    focusPull: 0.42,
    cameraDive: 0.08,
    centralCoreBoost: 0.35,
    signalSplit: false,
    statusLine: "Message reçu — attention portée sur la communication",
  },
  analysis: {
    cognitiveState: "thinking",
    masterState: "THINKING",
    hook: "brain_activity",
    regions: [
      { id: "core", strength: 0.65 },
      { id: "communication", strength: 0.55 },
      { id: "reasoning", strength: 0.48 },
    ],
    waveStyle: "branching",
    signalSplit: true,
    explorationWaves: true,
    focusPull: 0.55,
    cameraDive: 0.12,
    statusLine: "Analyse de l'intention…",
  },
  memory: {
    cognitiveState: "memory_recall",
    masterState: "DEPTH_RECALL",
    hook: "memory_retrieval",
    regions: [
      { id: "memory", strength: 0.92 },
      { id: "core", strength: 0.58 },
    ],
    waveStyle: "deep_central",
    preferDeep: true,
    linkIlluminate: true,
    focusPull: 0.62,
    cameraDive: 0.28,
    statusLine: "Rappel de contexte conversationnel…",
  },
  reasoning: {
    cognitiveState: "reasoning",
    masterState: "THINKING",
    hook: "reasoning",
    regions: [
      { id: "core", strength: 0.95 },
      { id: "reasoning", strength: 0.88 },
    ],
    waveStyle: "layered_deep",
    layeredGlow: true,
    focusPull: 0.78,
    cameraDive: 0.52,
    statusLine: "Raisonnement en profondeur…",
  },
  tool_selection: {
    cognitiveState: "tool_execution",
    masterState: "WORKING",
    hook: "tool_usage",
    regions: [
      { id: "tools", strength: 0.82 },
      { id: "core", strength: 0.55 },
    ],
    waveStyle: "regional_focus",
    regionStrengthen: true,
    focusPull: 0.58,
    cameraDive: 0.38,
    statusLine: "Sélection d'outil…",
  },
  tool_execution: {
    cognitiveState: "tool_execution",
    masterState: "WORKING",
    hook: "tool_usage",
    regions: [
      { id: "tools", strength: 0.95 },
      { id: "core", strength: 0.62 },
    ],
    waveStyle: "tool_pulse",
    focusPull: 0.65,
    cameraDive: 0.42,
    statusLine: "Exécution d'outil…",
  },
  planning: {
    cognitiveState: "planning",
    masterState: "THINKING",
    hook: "brain_activity",
    regions: [
      { id: "core", strength: 0.78 },
      { id: "planning", strength: 0.85 },
    ],
    waveStyle: "rotating_clusters",
    stableClusters: true,
    focusPull: 0.68,
    cameraDive: 0.45,
    statusLine: "Planification des étapes…",
  },
  response: {
    cognitiveState: "writing",
    masterState: "WORKING",
    hook: "brain_activity",
    regions: [
      { id: "core", strength: 0.98 },
      { id: "communication", strength: 0.72 },
    ],
    waveStyle: "converging",
    signalConverge: true,
    centralCoreBoost: 0.55,
    focusPull: 0.82,
    cameraDive: 0.35,
    focusComposer: true,
    statusLine: "Synthèse de réponse…",
  },
  memory_store: {
    cognitiveState: "thinking",
    masterState: "WORKING",
    hook: "memory_retrieval",
    regions: [
      { id: "memory", strength: 0.75 },
      { id: "core", strength: 0.48 },
    ],
    waveStyle: "central",
    focusPull: 0.4,
    cameraDive: 0.18,
    statusLine: "Consolidation du fil de conversation…",
  },
  finished: {
    cognitiveState: "idle",
    masterState: "IDLE",
    hook: null,
    regions: [{ id: "core", strength: 0.35 }],
    waveStyle: "outbound_calm",
    outgoingPulse: true,
    focusPull: 0,
    cameraDive: 0,
    statusLine: "Conversation — en veille",
  },
});

/** Keyword hints for local tool inference (extension fallback). */
export const CONVERSATION_TOOL_HINTS = Object.freeze([
  { pattern: /\b(obsidian|note|vault)\b/i, toolId: "obsidian", label: "Obsidian" },
  { pattern: /\b(browser|web|recherche|search)\b/i, toolId: "browser", label: "Browser" },
  { pattern: /\b(calendar|calendrier|événement|event)\b/i, toolId: "calendar", label: "Calendar" },
  { pattern: /\b(trading|trade|marché|market)\b/i, toolId: "trading", label: "Trading" },
  { pattern: /\b(mémoire|memory|souviens|remember)\b/i, toolId: "memory", label: "Memory" },
]);

/**
 * Infer tools from user message text (local fallback when backend unavailable).
 * @param {string} message
 * @returns {Array<{ toolId: string, label: string }>}
 */
export function inferConversationTools(message) {
  const picks = [];
  for (const hint of CONVERSATION_TOOL_HINTS) {
    if (hint.pattern.test(message)) {
      picks.push({ toolId: hint.toolId, label: hint.label });
    }
  }
  if (!picks.length) {
    picks.push({ toolId: "chat", label: "Chat" });
  }
  return picks;
}

/**
 * @param {ConversationStageId} stageId
 * @returns {object}
 */
export function getConversationStageSignature(stageId) {
  return CONVERSATION_STAGE_SIGNATURES[stageId] ?? CONVERSATION_STAGE_SIGNATURES.analysis;
}

/**
 * Build orchestrator plan steps from message (local fallback).
 * @param {string} message
 * @param {Array<{ toolId: string, label: string }>} tools
 * @returns {string[]}
 */
export function buildSimulatedPlan(message, tools) {
  const trimmed = message.trim().slice(0, 80);
  const toolNames = tools.map((t) => t.label).join(", ");
  return [
    `Comprendre la demande — « ${trimmed}${message.length > 80 ? "…" : ""} »`,
    `Consulter la mémoire conversationnelle`,
    `Raisonner sur la meilleure approche`,
    toolNames !== "Chat" ? `Utiliser ${toolNames}` : `Synthétiser une réponse`,
    `Répondre et consolider le contexte`,
  ];
}
