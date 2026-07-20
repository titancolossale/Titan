/** Titan Frontend V2 — Backend event router (Phase E8 + E9). */

import { normalizeCognitiveState } from "../neural/cognitive.js";
import { CONVERSATION_ACTIVITY_EVENTS } from "../conversation/conversation-activity-engine.js";
import {
  COGNITIVE_STREAM_EVENTS,
  STAGE_NEURAL_MAP,
} from "./cognitive-pipeline-store.js";

/** Map API neural_state aliases to cognitive state ids. */
const NEURAL_TO_COGNITIVE = {
  idle: "idle",
  listening: "listening",
  thinking: "thinking",
  planning: "planning",
  memory_retrieval: "memory_recall",
  deep_analysis: "reasoning",
  tool_usage: "tool_execution",
  browser_research: "browser_research",
  calendar_planning: "calendar",
  email_processing: "writing",
  trading_analysis: "trading",
  voice_speaking: "voice",
};

/**
 * Apply neural renderer + camera reactions for an E9 stage.
 * @param {import("./cognitive-state-engine.js").CognitiveStateEngine} brain
 * @param {string} eventType
 * @param {object} data
 */
function applyStageNeuralReaction(brain, eventType, data) {
  const mapping = STAGE_NEURAL_MAP[eventType];
  if (!mapping) return;

  if (mapping.cognitive) {
    brain.setState(mapping.cognitive, { source: "backend", force: true });
  }

  const engine = brain._neural?.getEngine?.();
  const camera = engine?.camera;

  if (mapping.hook) {
    brain._neural?.trigger?.(mapping.hook, {
      tool: data.tool ?? undefined,
      waveStyle: data.wave_style,
      intensity: mapping.pulse ?? undefined,
    });
  }

  if (camera) {
    switch (mapping.camera) {
      case "zoom":
        camera.boostRecallDive?.(0.18);
        break;
      case "deep":
        camera.boostRecallDive?.(0.42);
        break;
      case "recall":
        camera.boostRecallDive?.(0.55);
        break;
      case "stable":
        camera.boostRecallDive?.(0.28);
        break;
      case "return":
        camera.boostRecallDive?.(0);
        break;
      default:
        break;
    }
  }
}

/**
 * Route E9 cognitive stream event.
 * @param {import("./cognitive-state-engine.js").CognitiveStateEngine} brain
 * @param {import("./state-store.js").StateStore | null} store
 * @param {string} eventType
 * @param {object} data
 */
function routeCognitiveStreamEvent(brain, store, eventType, data) {
  const pipeline = brain._pipelineStore;
  if (pipeline) {
    pipeline.ingest(eventType, data);
  }

  applyStageNeuralReaction(brain, eventType, data);

  if (store) {
    store.setState({
      pipelineStage: eventType,
      pipelineLabel: data.label ?? eventType,
      pipelineThinking: eventType !== "thinking_finished",
    });
  }

  switch (eventType) {
    case "thinking_started":
      brain.getConversationEngine().startFromBackend(data.message ?? "", data);
      brain.setState("thinking", { source: "backend", force: true });
      break;
    case "intent_detected":
      if (store && data.label) {
        store.setState({ conversationThinkingLine: data.label });
      }
      brain.getConversationEngine().ingestStage({ ...data, phase: "understanding" });
      break;
    case "memory_lookup":
    case "memory_hit":
    case "memory_miss":
      brain.getMemoryEngine().ingest({
        run_id: `live-${eventType}`,
        source: data.source ?? "long_term",
        phase: eventType === "memory_lookup" ? "search" : "recall",
        title: data.label ?? "Mémoire",
        status_line: data.label ?? "",
        has_matches: data.has_matches ?? eventType === "memory_hit",
        match_count: data.match_count ?? 0,
        state: "running",
      });
      break;
    case "obsidian_lookup":
      brain.getMemoryEngine().ingest({
        run_id: "live-obsidian",
        source: "obsidian",
        phase: "recall",
        title: "Notes Obsidian",
        status_line: data.label ?? "Consultation Obsidian…",
        has_matches: data.has_matches ?? false,
        state: "running",
      });
      brain.setState("obsidian", { source: "backend", force: true });
      break;
    case "tool_selection":
      brain.getConversationEngine().ingestStage({ ...data, phase: "research" });
      if (data.tool) {
        brain.activateTool(data.tool, { statusLine: data.label });
      }
      break;
    case "tool_execution":
      brain.getConversationEngine().ingestStage({ ...data, phase: "research" });
      if (data.tool) {
        brain.activateTool(data.tool, { statusLine: data.label, state: "progress" });
      }
      brain.getToolEngine().ingest(data);
      break;
    case "planning":
      if (store && data.label) {
        store.setState({
          conversationThinkingLine: data.label,
          conversationPlanSteps: data.plan_steps ?? [data.label],
        });
      }
      brain.getConversationEngine().ingestStage({ ...data, phase: "planning" });
      break;
    case "reasoning":
    case "verification":
      if (store && data.label) {
        store.setState({ conversationReasoningLine: data.label });
      }
      brain.getConversationEngine().ingestStage({
        ...data,
        phase: "verification",
      });
      break;
    case "response_building":
      brain.getConversationEngine().ingestStage({ ...data, phase: "writing" });
      break;
    case "response_ready":
      if (store) {
        store.setState({ conversationStatusLine: data.label ?? "Réponse prête" });
      }
      break;
    case "thinking_finished":
      brain.getConversationEngine().finishFromBackend(data);
      brain.setState("idle", { source: "backend", force: true });
      pipeline?.reset();
      break;
    default:
      break;
  }
}

/**
 * Route a backend SSE event into the cognitive state engine and store.
 * @param {import("./cognitive-state-engine.js").CognitiveStateEngine} brain
 * @param {import("./state-store.js").StateStore | null} store
 * @param {string} type
 * @param {object} data
 */
export function routeBackendEvent(brain, store, type, data) {
  if (COGNITIVE_STREAM_EVENTS.includes(type)) {
    routeCognitiveStreamEvent(brain, store, type, data);
    return;
  }

  switch (type) {
    case "brain_state": {
      const state = NEURAL_TO_COGNITIVE[data.state] ?? normalizeCognitiveState(data.state);
      brain.setState(state, { source: "backend", force: true });
      break;
    }
    case "presence":
      if (store) {
        store.setState({ presence: data.state ?? "idle" });
      }
      break;
    case "status":
      if (store) {
        store.setState({
          systemStatus: data.status ?? "ONLINE",
          systemUser: data.user ?? null,
          systemVersion: data.version ?? null,
        });
      }
      break;
    case "telemetry":
      if (store) {
        store.setState({ telemetry: data });
      }
      break;
    case "conversation_started":
      brain.getConversationEngine().startFromBackend(data.message ?? "", data);
      brain.setState("listening", { source: "backend", force: true });
      break;
    case "conversation_stage":
      brain.getConversationEngine().ingestStage(data);
      if (data.stage && COGNITIVE_STREAM_EVENTS.includes(data.stage)) {
        brain._pipelineStore?.ingest(data.stage, data);
      }
      if (data.neural_state) {
        const mapped = NEURAL_TO_COGNITIVE[data.neural_state] ?? data.neural_state;
        brain.setState(mapped, { source: "backend", force: true });
      }
      break;
    case "text_delta":
    case "token":
      // Progressive tokens — do not rebuild neural/conversation stage caches.
      break;
    case "response_started":
      if (data.neural_state) {
        const mapped = NEURAL_TO_COGNITIVE[data.neural_state] ?? data.neural_state;
        brain.setState(mapped, { source: "backend", force: true });
      }
      break;
    case "response_completed":
    case "acknowledged":
    case "structured_error":
    case "cancelled":
      break;
    case "conversation_finished":
      brain.getConversationEngine().finishFromBackend(data);
      if (data.pipeline) {
        brain._pipelineStore?.applySnapshot(data.pipeline);
      }
      if (store) {
        store.setState({
          detectedIntent: data.detected_intent ?? store.getState().detectedIntent,
          orchestrationDuration: data.duration_seconds ?? null,
          approvalRequired: Boolean(data.approval_required),
          approvalId: data.approval_id ?? null,
          approvalSummary: data.approval_summary ?? null,
          conversationId: data.conversation_id ?? store.getState().conversationId,
          lastRequestId: data.request_id ?? store.getState().lastRequestId,
        });
      }
      break;
    case "orchestration_started":
      if (store && data.intent) {
        store.setState({
          detectedIntent: data.intent,
          conversationThinkingLine: data.label ?? `Intent: ${data.intent}`,
          pipelineThinking: true,
        });
      }
      brain.setState("thinking", { source: "backend", force: true });
      break;
    case "orchestration_finished":
      if (store) {
        store.setState({
          detectedIntent: data.detected_intent ?? store.getState().detectedIntent,
          orchestrationConfidence: data.confidence ?? null,
          systemsUsed: data.systems_used ?? null,
          reasoningSummary: data.reasoning_summary ?? "",
          orchestrationDuration: data.duration_seconds ?? null,
          approvalRequired: Boolean(data.approval_required),
        });
      }
      break;
    case "approval_required":
      brain.setState("awaiting_approval", { source: "backend", force: true });
      if (store) {
        store.setState({
          approvalRequired: true,
          approvalId: data.approval_id ?? null,
          approvalSummary: data.summary ?? "Approbation requise.",
          presence: "working",
        });
      }
      break;
    case "thinking":
      if (store && data.label) {
        store.setState({ conversationThinkingLine: data.label });
      }
      brain.setState("thinking", { source: "backend", force: true });
      break;
    case "planning":
      if (store && data.label) {
        store.setState({
          conversationThinkingLine: data.label,
          conversationPlanSteps: data.plan_steps ?? [data.label],
        });
      }
      brain.getConversationEngine().ingestStage({ ...data, phase: "planning" });
      brain.setState("planning", { source: "backend", force: true });
      break;
    case "reasoning":
      if (store && data.label) {
        store.setState({ conversationReasoningLine: data.label });
      }
      brain.getConversationEngine().ingestStage({ ...data, phase: "verification" });
      brain.setState("reasoning", { source: "backend", force: true });
      break;
    case "memory_activity":
      brain.getMemoryEngine().ingest(data);
      break;
    case "tool_activity":
      brain.getToolEngine().ingest(data);
      break;
    case "error":
      brain.setState("error", { source: "backend", force: true });
      if (store) {
        store.setState({ lastError: data.message ?? data.code ?? "error" });
      }
      break;
    default:
      break;
  }
}

/**
 * @param {string} phase
 * @returns {string | null}
 */
export function phaseToConversationEvent(phase) {
  const map = {
    understanding: CONVERSATION_ACTIVITY_EVENTS.ANALYSIS,
    planning: "conversation_planning",
    memory: CONVERSATION_ACTIVITY_EVENTS.MEMORY,
    research: CONVERSATION_ACTIVITY_EVENTS.TOOL_EXECUTION,
    writing: CONVERSATION_ACTIVITY_EVENTS.RESPONSE,
    verification: CONVERSATION_ACTIVITY_EVENTS.REASONING,
  };
  return map[phase] ?? null;
}
