/** Titan Frontend V2 — Live cognitive pipeline state (Phase E9). */

/** @typedef {{ stage: string, label: string, timestamp: number, sequence: number }} StageEntry */

/** @typedef {{ event: string, label?: string, timestamp?: number, sequence?: number, [key: string]: unknown }} TimelineEntry */

/**
 * Tracks live cognitive streaming state from backend E9 events.
 * Exposed on brain.pipeline, brain.currentStage, brain.stageHistory, brain.timeline.
 */
export class CognitivePipelineStore {
  constructor() {
    /** @type {boolean} */
    this._thinking = false;
    /** @type {string | null} */
    this._currentStage = null;
    /** @type {StageEntry[]} */
    this._stageHistory = [];
    /** @type {TimelineEntry[]} */
    this._timeline = [];
    /** @type {string[]} */
    this._pipeline = [];
    /** @type {Set<(snapshot: object) => void>} */
    this._listeners = new Set();
  }

  /** @returns {boolean} */
  get thinking() {
    return this._thinking;
  }

  /** @returns {string | null} */
  get currentStage() {
    return this._currentStage;
  }

  /** @returns {StageEntry[]} */
  get stageHistory() {
    return [...this._stageHistory];
  }

  /** @returns {TimelineEntry[]} */
  get timeline() {
    return [...this._timeline];
  }

  /** @returns {string[]} */
  get pipeline() {
    return [...this._pipeline];
  }

  /** @returns {object} */
  snapshot() {
    return {
      thinking: this._thinking,
      currentStage: this._currentStage,
      stageHistory: this.stageHistory,
      timeline: this.timeline,
      pipeline: this.pipeline,
    };
  }

  /**
   * Ingest an E9 cognitive stream event.
   * @param {string} eventType
   * @param {object} data
   */
  ingest(eventType, data = {}) {
    const label = data.label ?? eventType;
    const timestamp = data.timestamp ?? Date.now() / 1000;
    const sequence = data.sequence ?? this._timeline.length;

    if (eventType === "thinking_started") {
      this._thinking = true;
      this._stageHistory = [];
      this._timeline = [];
      this._pipeline = [];
    }

    if (eventType === "thinking_finished") {
      this._thinking = false;
      this._currentStage = null;
    } else {
      this._currentStage = eventType;
      if (!this._pipeline.includes(eventType)) {
        this._pipeline.push(eventType);
      }
      this._stageHistory.push({ stage: eventType, label, timestamp, sequence });
    }

    this._timeline.push({ event: eventType, label, timestamp, sequence, ...data });
    this._emit();
  }

  /** Reset to idle — called on conversation_finished. */
  reset() {
    this._thinking = false;
    this._currentStage = null;
    this._emit();
  }

  /** Apply final pipeline snapshot from conversation_finished. */
  applySnapshot(snapshot = {}) {
    if (Array.isArray(snapshot.stage_history)) {
      this._stageHistory = snapshot.stage_history.map((entry) => ({
        stage: entry.stage ?? "",
        label: entry.label ?? "",
        timestamp: entry.timestamp ?? 0,
        sequence: entry.sequence ?? 0,
      }));
    }
    if (Array.isArray(snapshot.timeline)) {
      this._timeline = snapshot.timeline;
    }
    if (Array.isArray(snapshot.pipeline)) {
      this._pipeline = snapshot.pipeline;
    }
    this._thinking = false;
    this._currentStage = null;
    this._emit();
  }

  /**
   * @param {(snapshot: object) => void} callback
   * @returns {() => void}
   */
  subscribe(callback) {
    this._listeners.add(callback);
    return () => this._listeners.delete(callback);
  }

  _emit() {
    const snap = this.snapshot();
    for (const listener of this._listeners) {
      try {
        listener(snap);
      } catch {
        /* listener isolation */
      }
    }
  }
}

/** E9 event types — must match backend COGNITIVE_EVENT_TYPES. */
export const COGNITIVE_STREAM_EVENTS = [
  "thinking_started",
  "intent_detected",
  "memory_lookup",
  "memory_hit",
  "memory_miss",
  "obsidian_lookup",
  "tool_selection",
  "tool_execution",
  "reasoning",
  "planning",
  "verification",
  "response_building",
  "response_ready",
  "thinking_finished",
];

/** Neural hook + cognitive state mapping per E9 stage. */
export const STAGE_NEURAL_MAP = {
  thinking_started: { cognitive: "thinking", hook: "brain_activity", camera: "zoom" },
  intent_detected: { cognitive: "thinking", hook: "brain_activity", camera: "zoom", pulse: 0.35 },
  memory_lookup: { cognitive: "memory_recall", hook: "memory_retrieval", camera: "recall" },
  memory_hit: { cognitive: "memory_recall", hook: "memory_retrieval", camera: "recall" },
  memory_miss: { cognitive: "memory_recall", hook: "memory_retrieval", camera: "recall" },
  obsidian_lookup: { cognitive: "obsidian", hook: "memory_retrieval", camera: "recall" },
  tool_selection: { cognitive: "tool_execution", hook: "tool_usage", camera: "zoom" },
  tool_execution: { cognitive: "tool_execution", hook: "tool_usage", camera: "zoom" },
  reasoning: { cognitive: "reasoning", hook: "reasoning", camera: "deep" },
  planning: { cognitive: "planning", hook: "brain_activity", camera: "zoom" },
  verification: { cognitive: "reasoning", hook: "reasoning", camera: "stable" },
  response_building: { cognitive: "writing", hook: "brain_activity", camera: "zoom" },
  response_ready: { cognitive: "writing", hook: "brain_activity", camera: "return" },
  thinking_finished: { cognitive: "idle", hook: null, camera: "return" },
};
