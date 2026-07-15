/** Titan Frontend V2 — Conversation Activity Engine (Phase E7). */

import {
  CONVERSATION_ACTIVITY_EVENTS,
  CONVERSATION_STAGE_SIGNATURES,
  getConversationStageSignature,
} from "./conversation-registry.js";

export {
  CONVERSATION_ACTIVITY_EVENTS,
  CONVERSATION_STAGE_SIGNATURES,
} from "./conversation-registry.js";

/**
 * @typedef {Object} ConversationActivityBlend
 * @property {object | null} signature
 * @property {Array<{ id: string, strength: number }>} regions
 * @property {string | null} stage
 * @property {string | null} eventType
 * @property {number} blendWeight
 * @property {string} [statusLine]
 * @property {string | null} [hook]
 * @property {string} [cognitiveState]
 * @property {string} [masterState]
 */

/**
 * Event-driven conversation activity hub — every message generates visible cognitive activity.
 */
export class ConversationActivityEngine {
  constructor() {
    /** @type {Set<(event: object) => void>} */
    this._listeners = new Set();
    /** @type {ConversationActivityBlend | null} */
    this._blend = null;
    /** @type {boolean} */
    this._active = false;
    /** @type {string | null} */
    this._currentMessage = null;
    /** @type {string | null} */
    this._currentStage = null;
    /** @type {Array<{ toolId: string, label: string }>} */
    this._selectedTools = [];
    /** @type {string[]} */
    this._planSteps = [];
    /** @type {string} */
    this._thinkingLine = "";
    /** @type {string} */
    this._reasoningLine = "";
    /** @type {ReturnType<typeof setTimeout>[]} */
    this._pipelineTimers = [];
    /** @type {boolean} */
    this._cancelled = false;
    /** @type {boolean} */
    this._reducedMotion = false;
  }

  /** @param {boolean} reduced */
  setReducedMotion(reduced) {
    this._reducedMotion = reduced;
  }

  /** @returns {boolean} */
  isActive() {
    return this._active;
  }

  /** @returns {ConversationActivityBlend | null} */
  getBlend() {
    return this._blend;
  }

  /** @returns {string | null} */
  getCurrentMessage() {
    return this._currentMessage;
  }

  /** @returns {string[]} */
  getPlanSteps() {
    return [...this._planSteps];
  }

  /** @returns {string} */
  getThinkingLine() {
    return this._thinkingLine;
  }

  /** @returns {string} */
  getReasoningLine() {
    return this._reasoningLine;
  }

  /**
   * Receive user message — wide pulse enters neural field.
   * @param {string} message
   * @param {{ source?: string }} [options]
   * @returns {object}
   */
  receive(message, options = {}) {
    this._cancelled = false;
    this._active = true;
    this._currentMessage = message;

    this._selectedTools = [];
    this._planSteps = [];

    const blend = this._buildBlend("received", CONVERSATION_ACTIVITY_EVENTS.RECEIVED);
    this._thinkingLine = "Message entrant — Titan écoute et oriente son attention.";

    this._emit(CONVERSATION_ACTIVITY_EVENTS.RECEIVED, {
      message,
      source: options.source ?? "user",
      blend,
      planSteps: this._planSteps,
      tools: this._selectedTools,
      thinkingLine: this._thinkingLine,
    });

    return { message, blend, tools: this._selectedTools };
  }

  /**
   * Intent analysis — signals split into exploration branches.
   * @param {{ message?: string }} [options]
   * @returns {object}
   */
  analyze(options = {}) {
    const message = options.message ?? this._currentMessage ?? "";
    const blend = this._buildBlend("analysis", CONVERSATION_ACTIVITY_EVENTS.ANALYSIS);
    this._thinkingLine = `Analyse de l'intention — ${message.trim().slice(0, 60) || "demande utilisateur"}${message.length > 60 ? "…" : ""}`;

    this._emit(CONVERSATION_ACTIVITY_EVENTS.ANALYSIS, {
      message,
      blend,
      thinkingLine: this._thinkingLine,
      intent: this._inferIntent(message),
    });

    return { blend, thinkingLine: this._thinkingLine };
  }

  /**
   * Memory recall — memory region activates, related links illuminate.
   * @param {{ query?: string }} [options]
   * @returns {object}
   */
  recallMemory(options = {}) {
    const query = options.query ?? this._currentMessage ?? "";
    const blend = this._buildBlend("memory", CONVERSATION_ACTIVITY_EVENTS.MEMORY);
    this._thinkingLine = "Consultation du fil conversationnel et des souvenirs pertinents…";

    this._emit(CONVERSATION_ACTIVITY_EVENTS.MEMORY, {
      query,
      blend,
      thinkingLine: this._thinkingLine,
      memoryType: "conversation",
    });

    return { blend, query };
  }

  /**
   * Reasoning — large central activity, deep layered glow.
   * @param {{ summary?: string }} [options]
   * @returns {object}
   */
  reason(options = {}) {
    const blend = this._buildBlend("reasoning", CONVERSATION_ACTIVITY_EVENTS.REASONING);
    this._reasoningLine =
      options.summary ??
      "Évaluation des contraintes, du contexte mémoriel et de la meilleure stratégie de réponse.";
    this._thinkingLine = this._reasoningLine;

    this._emit(CONVERSATION_ACTIVITY_EVENTS.REASONING, {
      blend,
      reasoningLine: this._reasoningLine,
      thinkingLine: this._thinkingLine,
    });

    return { blend, reasoningLine: this._reasoningLine };
  }

  /**
   * Planning — stable rotating clusters in neural field.
   * @param {{ steps?: string[] }} [options]
   * @returns {object}
   */
  plan(options = {}) {
    if (options.steps?.length) {
      this._planSteps = options.steps;
    }
    const blend = this._buildBlend("planning", null);
    this._thinkingLine = "Structuration du plan d'exécution…";

    this._emit("conversation_planning", {
      blend,
      planSteps: this._planSteps,
      thinkingLine: this._thinkingLine,
    });

    return { blend, planSteps: this._planSteps };
  }

  /**
   * Tool selection — selected region lights up, connections strengthen.
   * @param {{ tools?: Array<{ toolId: string, label: string }> }} [options]
   * @returns {object}
   */
  selectTools(options = {}) {
    if (options.tools?.length) {
      this._selectedTools = options.tools;
    }
    const blend = this._buildBlend("tool_selection", CONVERSATION_ACTIVITY_EVENTS.TOOL_SELECTION);
    this._thinkingLine = `Outils retenus — ${this._selectedTools.map((t) => t.label).join(", ")}`;

    this._emit(CONVERSATION_ACTIVITY_EVENTS.TOOL_SELECTION, {
      blend,
      tools: this._selectedTools,
      thinkingLine: this._thinkingLine,
    });

    return { blend, tools: this._selectedTools };
  }

  /**
   * Tool execution — active tool region pulses.
   * @param {{ toolId?: string }} [options]
   * @returns {object}
   */
  executeTool(options = {}) {
    const toolId = options.toolId ?? this._selectedTools[0]?.toolId ?? "chat";
    const blend = this._buildBlend("tool_execution", CONVERSATION_ACTIVITY_EVENTS.TOOL_EXECUTION);
    this._thinkingLine = `Exécution — ${toolId}`;

    this._emit(CONVERSATION_ACTIVITY_EVENTS.TOOL_EXECUTION, {
      blend,
      toolId,
      thinkingLine: this._thinkingLine,
    });

    return { blend, toolId };
  }

  /**
   * Response generation — signals converge, center becomes brightest.
   * @param {{ preview?: string }} [options]
   * @returns {object}
   */
  respond(options = {}) {
    const preview =
      options.preview ??
      this._buildSimulatedResponse(this._currentMessage ?? "", this._selectedTools);
    const blend = this._buildBlend("response", CONVERSATION_ACTIVITY_EVENTS.RESPONSE);
    this._thinkingLine = "Synthèse de la réponse…";

    this._emit(CONVERSATION_ACTIVITY_EVENTS.RESPONSE, {
      blend,
      preview,
      thinkingLine: this._thinkingLine,
    });

    return { blend, preview };
  }

  /**
   * Memory storage — consolidate conversation context.
   * @param {{ summary?: string }} [options]
   * @returns {object}
   */
  storeMemory(options = {}) {
    const blend = this._buildBlend("memory_store", CONVERSATION_ACTIVITY_EVENTS.MEMORY_STORE);
    const summary = options.summary ?? this._currentMessage?.slice(0, 120) ?? "";

    this._emit(CONVERSATION_ACTIVITY_EVENTS.MEMORY_STORE, {
      blend,
      summary,
      memoryType: "conversation",
    });

    return { blend, summary };
  }

  /**
   * Finish turn — outgoing pulse, brain returns to calm.
   * @param {{ reason?: string }} [options]
   * @returns {object}
   */
  finish(options = {}) {
    const blend = this._buildBlend("finished", CONVERSATION_ACTIVITY_EVENTS.FINISHED);
    this._active = false;
    this._currentStage = "finished";
    this._thinkingLine = "";
    this._reasoningLine = "";

    this._emit(CONVERSATION_ACTIVITY_EVENTS.FINISHED, {
      blend,
      reason: options.reason ?? "complete",
    });

    this._blend = null;
    return { blend };
  }

  /** Cancel in-flight pipeline. */
  cancel() {
    this._cancelled = true;
    for (const id of this._pipelineTimers) {
      window.clearTimeout(id);
    }
    this._pipelineTimers = [];
    if (this._active) {
      this.finish({ reason: "cancelled" });
    }
  }

  /**
   * Subscribe to conversation activity events.
   * @param {(event: object) => void} callback
   * @returns {() => void}
   */
  onActivity(callback) {
    this._listeners.add(callback);
    return () => {
      this._listeners.delete(callback);
    };
  }

  destroy() {
    this.cancel();
    this._listeners.clear();
  }

  /**
   * Begin a conversation turn from backend conversation_started event.
   * @param {string} message
   * @param {object} [_meta]
   */
  startFromBackend(message, _meta = {}) {
    this.cancel();
    this._cancelled = false;
    this.receive(message, { source: "backend" });
  }

  /**
   * Apply a sanitized orchestrator progress step from backend.
   * @param {{ phase?: string, label?: string, neural_state?: string, tool?: string | null, plan_steps?: string[] }} data
   */
  ingestStage(data) {
    const phase = data.phase ?? "understanding";
    const label = data.label ?? "";

    switch (phase) {
      case "understanding":
        this._thinkingLine = label || this._thinkingLine;
        this.analyze({ message: this._currentMessage ?? "" });
        break;
      case "planning":
        this._thinkingLine = label || this._thinkingLine;
        this.plan({ steps: data.plan_steps?.length ? data.plan_steps : label ? [label] : this._planSteps });
        break;
      case "memory":
        this._thinkingLine = label || this._thinkingLine;
        this.recallMemory({ query: label });
        break;
      case "research":
        this._thinkingLine = label || this._thinkingLine;
        if (data.tool) {
          this._selectedTools = [{ toolId: data.tool, label: data.tool }];
          this.selectTools({ tools: this._selectedTools });
        }
        this.executeTool({ toolId: data.tool ?? this._selectedTools[0]?.toolId ?? "browser" });
        break;
      case "writing":
        this._thinkingLine = label || "Synthèse de la réponse…";
        this.respond({ preview: label });
        break;
      case "verification":
        this._reasoningLine = label || this._reasoningLine;
        this.reason({ summary: label });
        break;
      default:
        if (label) {
          this._thinkingLine = label;
          this.analyze({ message: this._currentMessage ?? "" });
        }
        break;
    }
  }

  /**
   * Complete a conversation turn from backend conversation_finished event.
   * @param {{ response?: string }} data
   */
  finishFromBackend(data) {
    if (data.response) {
      this.respond({ preview: data.response });
    }
    this.finish({ reason: "backend" });
  }

  /**
   * @param {keyof typeof CONVERSATION_STAGE_SIGNATURES} stageId
   * @param {string | null} eventType
   * @returns {ConversationActivityBlend}
   */
  _buildBlend(stageId, eventType) {
    const sig = getConversationStageSignature(stageId);
    /** @type {ConversationActivityBlend} */
    const blend = {
      signature: { ...sig },
      regions: sig.regions ? [...sig.regions] : [],
      stage: stageId,
      eventType,
      blendWeight: stageId === "finished" ? 0.2 : 0.72,
      statusLine: sig.statusLine,
      hook: sig.hook ?? null,
      cognitiveState: sig.cognitiveState,
      masterState: sig.masterState,
    };
    this._blend = blend;
    this._currentStage = stageId;
    return blend;
  }

  /** @param {string} message */
  _inferIntent(message) {
    const lower = message.toLowerCase();
    if (/\b(code|python|script|bug|fix)\b/.test(lower)) return "coding";
    if (/\b(recherche|search|web|browser)\b/.test(lower)) return "research";
    if (/\b(plan|étape|step|mission)\b/.test(lower)) return "planning";
    if (/\b(mémoire|souviens|remember)\b/.test(lower)) return "memory";
    return "general";
  }

  /**
   * @param {string} message
   * @param {Array<{ toolId: string, label: string }>} tools
   * @returns {string}
   */
  _buildSimulatedResponse(message, tools) {
    const trimmed = message.trim();
    if (!trimmed) {
      return "Je suis là. Que veux-tu accomplir ?";
    }
    const toolHint =
      tools.length && tools[0].toolId !== "chat"
        ? ` J'ai consulté ${tools.map((t) => t.label).join(" et ")} pour préparer cette réponse.`
        : "";
    return `Compris.${toolHint} Voici ma synthèse sur « ${trimmed.slice(0, 48)}${trimmed.length > 48 ? "…" : ""} » — dis-moi si tu veux approfondir ou passer à l'action.`;
  }

  /** @param {string} type @param {object} payload */
  _emit(type, payload) {
    const event = {
      type,
      timestamp: performance.now(),
      stage: this._currentStage,
      blend: payload.blend ?? this._blend,
      active: this._active,
      ...payload,
    };

    for (const listener of this._listeners) {
      try {
        listener(event);
      } catch {
        /* listener errors must not break conversation flow */
      }
    }
  }
}
