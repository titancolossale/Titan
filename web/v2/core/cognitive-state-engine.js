/** Titan Frontend V2 — Cognitive State Engine (Phase E10 Production). */

import {
  COGNITIVE_STATE_IDS,
  COGNITIVE_STATE_LABELS,
  getCognitiveSignature,
  normalizeCognitiveState,
  resolveMasterState,
} from "../neural/cognitive.js";
import { ToolActivityEngine, TOOL_ACTIVITY_EVENTS } from "../tools/tool-activity-engine.js";
import {
  MemoryActivityEngine,
  MEMORY_ACTIVITY_EVENTS,
} from "../memory/memory-activity-engine.js";
import {
  ConversationActivityEngine,
  CONVERSATION_ACTIVITY_EVENTS,
} from "../conversation/conversation-activity-engine.js";
import { CognitivePipelineStore } from "./cognitive-pipeline-store.js";

/**
 * Maps cognitive states to neural activity hooks for renderer pulses.
 * @type {Record<string, string | null>}
 */
const STATE_HOOKS = {
  idle: null,
  listening: "voice",
  thinking: "brain_activity",
  planning: "brain_activity",
  memory_recall: "memory_retrieval",
  reasoning: "reasoning",
  writing: "brain_activity",
  tool_execution: "tool_usage",
  browser_research: "browser_research",
  obsidian: "tool_usage",
  calendar: "tool_usage",
  trading: "tool_usage",
  voice: "speaking",
  error: "brain_activity",
  sleep: null,
};

/** Tool payload hints for region focus during tool-driven states. */
const STATE_TOOL_HINTS = {
  browser_research: "browser",
  obsidian: "obsidian",
  calendar: "calendar",
  trading: "trading",
  tool_execution: "tools",
};

/**
 * @typedef {Object} CognitiveStateSnapshot
 * @property {string} id
 * @property {string} previous
 * @property {string} label
 * @property {string} masterState
 * @property {boolean} transitioning
 * @property {number} blend
 * @property {object} signature
 * @property {number} changedAt
 */

/**
 * Central cognitive state machine — every UI module requests states through this API.
 * Rendering is delegated to NeuralStage; backend events drive state in production.
 */
export class CognitiveStateEngine {
  /**
   * @param {{ neuralStage: import("../neural/stage.js").NeuralStage, store?: import("./state-store.js").StateStore, toolEngine?: ToolActivityEngine, memoryEngine?: MemoryActivityEngine, conversationEngine?: ConversationActivityEngine }} deps
   */
  constructor(deps) {
    this._neural = deps.neuralStage;
    this._store = deps.store ?? null;
    this._tools =
      deps.toolEngine ??
      new ToolActivityEngine();
    this._memory =
      deps.memoryEngine ??
      new MemoryActivityEngine();
    this._conversation =
      deps.conversationEngine ??
      new ConversationActivityEngine();

    /** @type {string} */
    this._state = "idle";
    /** @type {string} */
    this._previous = "idle";
    /** @type {Set<(snapshot: CognitiveStateSnapshot) => void>} */
    this._listeners = new Set();
    /** @type {Set<(event: object) => void>} */
    this._toolListeners = new Set();
    /** @type {Set<(event: object) => void>} */
    this._memoryListeners = new Set();
    /** @type {Set<(event: object) => void>} */
    this._conversationListeners = new Set();
    /** @type {string[]} */
    this._conversationActiveToolIds = [];
    /** @type {string | null} */
    this._pinnedState = null;
    /** @type {number} */
    this._changedAt = performance.now();
    /** @type {string | null} */
    this._dominantToolId = null;
    this._pipelineStore = new CognitivePipelineStore();

    this._tools.onToolActivity((event) => this._handleToolActivity(event));
    this._memory.onMemoryActivity((event) => this._handleMemoryActivity(event));
    this._conversation.onActivity((event) => this._handleConversationActivity(event));

    /** @type {object} Public memory API — brain.memory.* */
    this.memory = {
      create: (options) => this._memoryDispatch("create", options),
      update: (id, patch) => this._memoryDispatch("update", id, patch),
      recall: (id, options) => this._memoryDispatch("recall", id, options),
      search: (query, options) => this._memoryDispatch("search", query, options),
      link: (a, b, options) => this._memoryDispatch("link", a, b, options),
      summarize: (ids, options) => this._memoryDispatch("summarize", ids, options),
      archive: (id) => this._memoryDispatch("archive", id),
      delete: (id, options) => this._memoryDispatch("delete", id, options),
      onActivity: (cb) => this.onMemoryActivity(cb),
    };

    /** @type {object} Public conversation API — brain.conversation.* */
    this.conversation = {
      receive: (message, options) => this._conversationDispatch("receive", message, options),
      analyze: (options) => this._conversationDispatch("analyze", options),
      reason: (options) => this._conversationDispatch("reason", options),
      plan: (options) => this._conversationDispatch("plan", options),
      respond: (options) => this._conversationDispatch("respond", options),
      finish: (options) => this._conversationDispatch("finish", options),
      onActivity: (cb) => this.onConversationActivity(cb),
      cancel: () => this._conversation.cancel(),
      isActive: () => this._conversation.isActive(),
    };
  }

  /** @returns {MemoryActivityEngine} */
  getMemoryEngine() {
    return this._memory;
  }

  /** @returns {ConversationActivityEngine} */
  getConversationEngine() {
    return this._conversation;
  }

  /** @returns {ToolActivityEngine} */
  getToolEngine() {
    return this._tools;
  }

  /** @returns {CognitivePipelineStore} */
  getPipelineStore() {
    return this._pipelineStore;
  }

  /**
   * Set cognitive state immediately (smooth visual blend handled by renderer).
   * @param {string} state
   * @param {{ source?: string, force?: boolean, silent?: boolean }} [options]
   * @returns {string} normalized state id
   */
  setState(state, options = {}) {
    const normalized = normalizeCognitiveState(state);
    if (!COGNITIVE_STATE_IDS.includes(normalized)) {
      return this._state;
    }

    if (normalized === this._state && !options.force) {
      return normalized;
    }

    if (!options.force && this._pinnedState && options.source !== "pin-release") {
      return this._state;
    }

    this._previous = this._state;
    this._state = normalized;
    this._changedAt = performance.now();

    if (options.source === "pin") {
      this._pinnedState = normalized;
    } else if (options.source === "pin-release") {
      this._pinnedState = null;
    }

    this._applyToRenderer(normalized);
    this._syncStore(normalized);
    this._emit();

    return normalized;
  }

  /**
   * Transition to a new cognitive state (alias for setState — blend is renderer-side).
   * @param {string} toState
   * @param {{ duration?: number, source?: string }} [options]
   * @returns {Promise<string>}
   */
  transition(toState, options = {}) {
    const normalized = this.setState(toState, options);
    const signature = getCognitiveSignature(normalized);
    const duration = options.duration ?? signature.transitionMs ?? 700;

    return new Promise((resolve) => {
      window.setTimeout(() => resolve(normalized), duration);
    });
  }

  /** @returns {CognitiveStateSnapshot} */
  getState() {
    const engine = this._neural.getEngine();
    const neuralSnap = engine?.getState?.() ?? null;
    const blend = neuralSnap?.cognitiveBlend ?? 1;

    return {
      id: this._state,
      previous: this._previous,
      label: COGNITIVE_STATE_LABELS[this._state] ?? this._state,
      masterState: resolveMasterState(this._state),
      transitioning: blend < 0.98,
      blend,
      signature: getCognitiveSignature(this._state),
      changedAt: this._changedAt,
    };
  }

  /**
   * Subscribe to cognitive state changes.
   * @param {(snapshot: CognitiveStateSnapshot) => void} callback
   * @returns {() => void}
   */
  onStateChanged(callback) {
    this._listeners.add(callback);
    return () => {
      this._listeners.delete(callback);
    };
  }

  /** Pin current state — transient UI events won't override until releasePin(). */
  pin() {
    this._pinnedState = this._state;
  }

  releasePin() {
    this._pinnedState = null;
  }

  /**
   * Activate a tool — brain reacts automatically in the matching neural region.
   * @param {string} toolId
   * @param {{ activity?: number, energy?: number, priority?: number, statusLine?: string }} [options]
   */
  activateTool(toolId, options = {}) {
    const instance = this._tools.activateTool(toolId, options);
    const blend = this._tools.getBlend();
    this._applyToolBlend(blend, true);
    return instance;
  }

  /**
   * Deactivate a tool — smooth blend back to remaining active tools or idle.
   * @param {string} toolId
   */
  deactivateTool(toolId) {
    const removed = this._tools.deactivateTool(toolId);
    const blend = this._tools.getBlend();
    if (blend?.dominant) {
      this._applyToolBlend(blend);
    } else {
      this._neural.getEngine()?.applyToolActivity?.(null);
      if (!this._pinnedState) {
        this.setState("idle", { source: "tool-release", force: true });
      }
    }
    return removed;
  }

  /** @returns {import("../tools/tool-activity-engine.js").ToolInstance[]} */
  getActiveTools() {
    return this._tools.getActiveTools();
  }

  /**
   * Subscribe to tool activity events (activate, deactivate, blend, pulse).
   * @param {(event: object) => void} callback
   * @returns {() => void}
   */
  onToolActivity(callback) {
    this._toolListeners.add(callback);
    return () => {
      this._toolListeners.delete(callback);
    };
  }

  /**
   * Subscribe to memory activity events.
   * @param {(event: object) => void} callback
   * @returns {() => void}
   */
  onMemoryActivity(callback) {
    this._memoryListeners.add(callback);
    return () => {
      this._memoryListeners.delete(callback);
    };
  }

  /**
   * Subscribe to conversation activity events.
   * @param {(event: object) => void} callback
   * @returns {() => void}
   */
  onConversationActivity(callback) {
    this._conversationListeners.add(callback);
    return () => {
      this._conversationListeners.delete(callback);
    };
  }

  /** @param {string} method @param {...unknown} args */
  _conversationDispatch(method, ...args) {
    const engine = this._conversation;
    /** @type {unknown} */
    let result;
    switch (method) {
      case "receive":
        result = engine.receive(args[0] ?? "", args[1] ?? {});
        break;
      case "analyze":
        result = engine.analyze(args[0] ?? {});
        break;
      case "recallMemory":
        result = engine.recallMemory(args[0] ?? {});
        break;
      case "reason":
        result = engine.reason(args[0] ?? {});
        break;
      case "plan":
        result = engine.plan(args[0] ?? {});
        break;
      case "selectTools":
        result = engine.selectTools(args[0] ?? {});
        break;
      case "executeTool":
        result = engine.executeTool(args[0] ?? {});
        break;
      case "respond":
        result = engine.respond(args[0] ?? {});
        break;
      case "storeMemory":
        result = engine.storeMemory(args[0] ?? {});
        break;
      case "finish":
        result = engine.finish(args[0] ?? {});
        break;
      default:
        return null;
    }
    return result;
  }

  /** @param {string} method @param {...unknown} args */
  _memoryDispatch(method, ...args) {
    const engine = this._memory;
    /** @type {unknown} */
    let result;
    switch (method) {
      case "create":
        result = engine.create(args[0] ?? {});
        break;
      case "update":
        result = engine.update(args[0], args[1] ?? {});
        break;
      case "recall":
        result = engine.recall(args[0], args[1] ?? {});
        break;
      case "search":
        result = engine.search(args[0] ?? "", args[1] ?? {});
        break;
      case "link":
        result = engine.link(args[0], args[1], args[2] ?? {});
        break;
      case "summarize":
        result = engine.summarize(args[0] ?? [], args[1] ?? {});
        break;
      case "archive":
        result = engine.archive(args[0]);
        break;
      case "delete":
        result = engine.delete(args[0], args[1] ?? {});
        break;
      default:
        return null;
    }
    this._applyMemoryBlend(this._memory.getBlend(), true);
    return result;
  }

  /** @param {object} event */
  _handleMemoryActivity(event) {
    this._applyMemoryBlend(event.blend ?? this._memory.getBlend(), this._shouldTriggerMemoryHooks(event));

    if (
      event.type === MEMORY_ACTIVITY_EVENTS.DELETED &&
      event.pending &&
      !this._memory.getBlend()?.active?.length
    ) {
      /* pending delete — keep fade overlay until confirmed */
    } else if (!this._memory.getBlend()?.signature) {
      this._neural.applyMemoryActivity(null);
    }

    this._syncMemoryStore(event);
    this._emitMemory(event);
  }

  /** @param {object} event */
  _shouldTriggerMemoryHooks(event) {
    if (event.type === MEMORY_ACTIVITY_EVENTS.BLEND_UPDATED) return false;
    return (
      event.type === MEMORY_ACTIVITY_EVENTS.RECALLED ||
      event.type === MEMORY_ACTIVITY_EVENTS.SEARCH ||
      event.type === MEMORY_ACTIVITY_EVENTS.CREATED ||
      event.type === MEMORY_ACTIVITY_EVENTS.LINKED ||
      event.type === MEMORY_ACTIVITY_EVENTS.SUMMARY
    );
  }

  /** @param {import("../memory/memory-activity-engine.js").MemoryActivityBlend | null} blend @param {boolean} [forceHooks] */
  _applyMemoryBlend(blend, forceHooks = false) {
    if (!blend?.signature) {
      this._neural.applyMemoryActivity(null);
      if (!this._pinnedState && !this._tools.getActiveTools().length) {
        this.setState("idle", { source: "memory-release", force: true });
      }
      return;
    }

    const recallLike =
      blend.hook === "memory_retrieval" ||
      blend.eventType === MEMORY_ACTIVITY_EVENTS.RECALLED ||
      blend.eventType === MEMORY_ACTIVITY_EVENTS.SEARCH;

    if (recallLike && !this._pinnedState) {
      this._previous = this._state;
      this._state = "memory_recall";
      this._changedAt = performance.now();
      this._neural.setMasterState("DEPTH_RECALL");
      this._neural.setCognitiveTag("memory_recall");
      this._syncStore("memory_recall");
      this._emit();
    } else if (
      blend.eventType &&
      blend.eventType !== MEMORY_ACTIVITY_EVENTS.ARCHIVED &&
      blend.eventType !== MEMORY_ACTIVITY_EVENTS.DELETED &&
      !this._pinnedState
    ) {
      this._neural.setMasterState("WORKING");
    }

    this._neural.applyMemoryActivity(blend, { triggerHooks: forceHooks });
  }

  /** @param {object} [event] */
  _syncMemoryStore(event) {
    if (!this._store) return;
    const blend = this._memory.getBlend();
    const active = this._memory.getActiveMemories();
    const statusLine =
      event?.statusLine ?? blend?.statusLine ?? "Mémoire — en veille";
    const recallActive =
      blend?.hook === "memory_retrieval" ||
      blend?.eventType === MEMORY_ACTIVITY_EVENTS.RECALLED ||
      blend?.eventType === MEMORY_ACTIVITY_EVENTS.SEARCH;

    this._store.setState({
      memoryStatusLine: statusLine,
      recallActive,
      activeMemoryCount: active.length,
      memoryEventType: blend?.eventType ?? null,
      presence: recallActive ? "thinking" : this._mapPresence(this._state),
    });
  }

  /** @param {object} event */
  _emitMemory(event) {
    for (const listener of this._memoryListeners) {
      try {
        listener(event);
      } catch {
        /* listener errors must not break memory flow */
      }
    }
  }

  /** @param {object} event */
  _handleConversationActivity(event) {
    this._applyConversationBlend(event.blend ?? this._conversation.getBlend(), event);
    this._integrateConversationSubsystems(event);
    this._syncConversationStore(event);
    this._emitConversation(event);
  }

  /** @param {import("../conversation/conversation-activity-engine.js").ConversationActivityBlend | null} blend @param {object} event */
  _applyConversationBlend(blend, event) {
    if (!blend?.signature) {
      this._neural.applyConversationActivity?.(null);
      return;
    }

    const cognitiveId = blend.cognitiveState ?? blend.signature.cognitiveState ?? "thinking";
    if (!this._pinnedState) {
      this._previous = this._state;
      this._state = normalizeCognitiveState(cognitiveId);
      this._changedAt = performance.now();
      this._neural.setMasterState(blend.masterState ?? resolveMasterState(this._state));
      this._neural.setCognitiveTag(this._state);
      this._syncStore(this._state);
      this._emit();
    }

    this._neural.applyConversationActivity?.(blend, {
      triggerHooks: event.type !== CONVERSATION_ACTIVITY_EVENTS.FINISHED,
      eventType: event.type,
    });

    const hook = blend.hook ?? blend.signature.hook;
    if (hook && event.type !== CONVERSATION_ACTIVITY_EVENTS.FINISHED) {
      this._neural.trigger(hook, {
        waveStyle: blend.signature.waveStyle,
        tool: event.toolId ?? "chat",
        conversationStage: blend.stage,
      });
    }

    if (blend.signature.cameraDive > 0.4 && this._neural.getEngine()?.camera) {
      this._neural.getEngine().camera.boostRecallDive(blend.signature.cameraDive * 0.65);
    } else if (event.type === CONVERSATION_ACTIVITY_EVENTS.RECEIVED) {
      this._neural.getEngine()?.camera?.boostRecallDive?.(0.12);
    }
  }

  /** @param {object} event */
  _integrateConversationSubsystems(event) {
    switch (event.type) {
      case CONVERSATION_ACTIVITY_EVENTS.MEMORY:
        this._memory.search(event.query ?? "", { source: "conversation" });
        break;
      case CONVERSATION_ACTIVITY_EVENTS.TOOL_SELECTION:
        for (const id of this._conversationActiveToolIds) {
          this._tools.deactivateTool(id);
        }
        this._conversationActiveToolIds = [];
        for (const tool of event.tools ?? []) {
          this.activateTool(tool.toolId, {
            statusLine: `Conversation — ${tool.label}`,
          });
          this._conversationActiveToolIds.push(tool.toolId);
        }
        break;
      case CONVERSATION_ACTIVITY_EVENTS.TOOL_EXECUTION:
        if (event.toolId) {
          this.activateTool(event.toolId, { state: "progress" });
        }
        break;
      case CONVERSATION_ACTIVITY_EVENTS.RESPONSE:
        this.activateTool("chat", { statusLine: "Synthèse de réponse…" });
        if (!this._conversationActiveToolIds.includes("chat")) {
          this._conversationActiveToolIds.push("chat");
        }
        break;
      case CONVERSATION_ACTIVITY_EVENTS.MEMORY_STORE:
        this._memory.create({
          type: "conversation",
          source: "conversation",
          importance: 0.55,
        });
        break;
      case CONVERSATION_ACTIVITY_EVENTS.FINISHED:
        for (const id of this._conversationActiveToolIds) {
          this.deactivateTool(id);
        }
        this._conversationActiveToolIds = [];
        this._neural.applyConversationActivity?.(null);
        if (!this._pinnedState) {
          this.setState("idle", { source: "conversation-finish", force: true });
        }
        break;
      default:
        break;
    }
  }

  /** @param {object} event */
  _syncConversationStore(event) {
    if (!this._store) return;
    const blend = event.blend ?? this._conversation.getBlend();
    const active = this._conversation.isActive();

    this._store.setState({
      conversationActive: active,
      conversationStage: blend?.stage ?? null,
      conversationEventType: event.type ?? null,
      conversationStatusLine: blend?.statusLine ?? "Conversation — en veille",
      conversationThinkingLine: event.thinkingLine ?? this._conversation.getThinkingLine(),
      conversationReasoningLine:
        event.reasoningLine ?? this._conversation.getReasoningLine(),
      conversationPlanSteps: event.planSteps ?? this._conversation.getPlanSteps(),
      presence: active ? this._mapPresence(this._state) : this._mapPresence(this._state),
    });
  }

  /** @param {object} event */
  _emitConversation(event) {
    for (const listener of this._conversationListeners) {
      try {
        listener(event);
      } catch {
        /* listener errors must not break conversation flow */
      }
    }
  }

  /** @param {object} event */
  _handleToolActivity(event) {
    if (
      event.type === TOOL_ACTIVITY_EVENTS.BLEND_UPDATED ||
      event.type === TOOL_ACTIVITY_EVENTS.ACTIVATED ||
      event.type === TOOL_ACTIVITY_EVENTS.ACTIVITY
    ) {
      this._applyToolBlend(event.blend ?? this._tools.getBlend());
    }

    if (event.type === TOOL_ACTIVITY_EVENTS.DEACTIVATED && this._tools.getActiveTools().length === 0) {
      this._neural.getEngine()?.applyToolActivity?.(null);
    }

    this._syncToolStore();
    this._emitTool(event);
  }

  /** @param {import("../tools/tool-activity-engine.js").ToolActivityBlend | null} blend @param {boolean} [forceHooks] */
  _applyToolBlend(blend, forceHooks = false) {
    if (!blend?.active?.length) {
      this._dominantToolId = null;
      this._neural.getEngine()?.applyToolActivity?.(null);
      return;
    }

    const dominant = blend.dominant;
    if (!dominant) return;

    const cognitiveId = dominant.definition.cognitiveState ?? "tool_execution";
    const dominantChanged = this._dominantToolId !== dominant.id;
    const triggerHooks = forceHooks || dominantChanged;

    if (dominantChanged) {
      this._previous = this._state;
      this._state = normalizeCognitiveState(cognitiveId);
      this._changedAt = performance.now();
      this._dominantToolId = dominant.id;

      this._neural.setMasterState(resolveMasterState(this._state));
      this._neural.setCognitiveTag(this._state);
      this._applyToRenderer(this._state);
      this._syncStore(this._state);
      this._emit();
    }

    this._neural.getEngine()?.applyToolActivity?.(blend, { triggerHooks });
  }

  _syncToolStore() {
    if (!this._store) return;
    const active = this._tools.getActiveTools();
    const blend = this._tools.getBlend();
    const dominant = blend?.dominant;

    this._store.setState({
      activeToolCount: active.length,
      activeToolIds: active.map((t) => t.id),
      dominantToolId: dominant?.id ?? null,
      toolStatusLine: dominant?.statusLine ?? "Outils — aucune activité",
      presence: active.length ? "working" : this._mapPresence(this._state),
      presenceLevel: active.length
        ? Math.max(this._computePresenceLevel(this._state), 82)
        : this._computePresenceLevel(this._state),
    });
  }

  /** @param {object} event */
  _emitTool(event) {
    for (const listener of this._toolListeners) {
      try {
        listener(event);
      } catch {
        /* listener errors must not break tool flow */
      }
    }
  }

  /** @param {string} normalized */
  _applyToRenderer(normalized) {
    const master = resolveMasterState(normalized);
    this._neural.setMasterState(master);
    this._neural.setCognitiveTag(normalized);

    const hook = STATE_HOOKS[normalized];
    const toolHint = STATE_TOOL_HINTS[normalized];
    const payload = toolHint ? { tool: toolHint } : {};

    if (hook === "memory_retrieval") {
      this._neural.trigger("memory_retrieval", payload);
    } else if (hook === "browser_research") {
      this._neural.trigger("browser_research", { tool: "browser" });
    } else if (hook === "tool_usage") {
      this._neural.trigger("tool_usage", payload);
    } else if (hook === "reasoning") {
      this._neural.trigger("reasoning", payload);
    } else if (hook === "brain_activity") {
      this._neural.trigger("brain_activity", payload);
    } else if (hook === "voice") {
      this._neural.trigger("voice", payload);
    } else if (hook === "speaking") {
      this._neural.trigger("speaking", payload);
    }

    if (normalized === "error") {
      this._neural.getEngine()?.trigger?.("brain_activity", { waveStyle: "sharp" });
    }
  }

  /** @param {string} normalized */
  _syncStore(normalized) {
    if (!this._store) return;
    const presence = this._mapPresence(normalized);
    this._store.setState({
      cognitiveState: normalized,
      presence,
      presenceLevel: this._computePresenceLevel(normalized),
    });
  }

  /** @param {string} id @returns {number} 0–100 */
  _computePresenceLevel(id) {
    if (id === "idle" || id === "sleep") return 42;
    if (id === "listening") return 58;
    if (id === "voice") return 72;
    if (id === "memory_recall") return 85;
    if (id === "thinking" || id === "reasoning" || id === "planning" || id === "writing") {
      return 78;
    }
    if (id === "error") return 95;
    if (this._tools.getActiveTools().length > 0) return 82;
    return 65;
  }

  /** @param {string} id */
  _mapPresence(id) {
    if (id === "listening") return "listening";
    if (id === "voice") return "speaking";
    if (id === "error") return "error";
    if (id === "sleep") return "idle";
    if (id === "planning") return "planning";
    if (
      id === "thinking" ||
      id === "reasoning" ||
      id === "memory_recall" ||
      id === "writing"
    ) {
      return "thinking";
    }
    if (id !== "idle") return "working";
    return "idle";
  }

  _emit() {
    const snapshot = this.getState();
    for (const listener of this._listeners) {
      try {
        listener(snapshot);
      } catch {
        /* listener errors must not break state engine */
      }
    }
  }
}

/** Global-friendly alias for UI modules. */
export { CognitiveStateEngine as TitanBrain };
