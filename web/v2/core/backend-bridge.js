/** Titan Frontend V2 — Backend Bridge (Phase E8 + Web Runtime V1). */

import { routeBackendEvent } from "./event-router.js";
import { COGNITIVE_STREAM_EVENTS } from "./cognitive-pipeline-store.js";
import { authHeaders, getStoredToken } from "./web-auth.js";
import {
  createClientRequestId,
  getStoredConversationId,
  saveConversationId,
  saveRequestId,
} from "./conversation-session.js";
const RECONNECT_BASE_MS = 1200;
const RECONNECT_MAX_MS = 15000;

/**
 * Parse SSE text chunks into { event, data, id } records.
 * @param {string} buffer
 * @returns {{ events: Array<{ event: string, data: object, id: string | null }>, remainder: string }}
 */
export function parseSseBuffer(buffer) {
  const events = [];
  const blocks = buffer.split("\n\n");
  const remainder = blocks.pop() ?? "";

  for (const block of blocks) {
    if (!block.trim() || block.trimStart().startsWith(":")) continue;

    let eventType = "message";
    let eventId = null;
    const dataLines = [];

    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) {
        eventType = line.slice(6).trim();
      } else if (line.startsWith("id:")) {
        eventId = line.slice(3).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }

    if (!dataLines.length) continue;

    try {
      const data = JSON.parse(dataLines.join("\n"));
      events.push({ event: eventType, data, id: eventId });
    } catch {
      /* ignore malformed frames */
    }
  }

  return { events, remainder };
}

/**
 * Connect Frontend V2 to the Titan Python backend via SSE.
 * Exposes connect/disconnect/on/off/emit/state/connection on the brain instance.
 */
export class BackendBridge {
  /**
   * @param {import("./cognitive-state-engine.js").CognitiveStateEngine} brain
   * @param {import("./state-store.js").StateStore | null} [store]
   */
  constructor(brain, store = null) {
    this._brain = brain;
    this._store = store;
    /** @type {Map<string, Set<(data: object) => void>>} */
    this._listeners = new Map();
    /** @type {EventSource | null} */
    this._eventSource = null;
    /** @type {AbortController | null} */
    this._chatAbort = null;
    /** @type {boolean} */
    this._shouldReconnect = false;
    /** @type {number} */
    this._reconnectAttempts = 0;
    /** @type {ReturnType<typeof setTimeout> | null} */
    this._reconnectTimer = null;
    /** @type {Array<{ event: string, data: object, id: string | null }>} */
    this._missedQueue = [];
    /** @type {boolean} */
    this._submitting = false;

    /** @type {{ connected: boolean, streaming: boolean, lastEventId: string | null, reconnectAttempts: number, mode: "idle"|"streaming"|"disconnected" }} */
    this.connection = {
      connected: false,
      streaming: false,
      lastEventId: null,
      reconnectAttempts: 0,
      mode: "disconnected",
    };

    /** @type {{ brainState: string, presence: string, user: string | null, version: string | null }} */
    this.state = {
      brainState: "idle",
      presence: "idle",
      user: null,
      version: null,
    };
  }

  /** Establish persistent SSE connection to /events/stream. */
  connect() {
    if (this._eventSource) return;

    this._shouldReconnect = true;
    this._reconnectAttempts = 0;
    this._openEventSource();
    this._flushMissedQueue();
  }

  /** Close SSE connection and cancel in-flight chat stream. */
  disconnect() {
    this._shouldReconnect = false;
    this._chatAbort?.abort();
    this._chatAbort = null;

    if (this._reconnectTimer !== null) {
      window.clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }

    if (this._eventSource) {
      this._eventSource.close();
      this._eventSource = null;
    }

    this.connection.connected = false;
    this.connection.streaming = false;
    this.connection.mode = "disconnected";
  }

  /**
   * Subscribe to backend events.
   * @param {string} type
   * @param {(data: object) => void} callback
   * @returns {() => void}
   */
  on(type, callback) {
    if (!this._listeners.has(type)) {
      this._listeners.set(type, new Set());
    }
    this._listeners.get(type).add(callback);
    return () => this.off(type, callback);
  }

  /**
   * @param {string} type
   * @param {(data: object) => void} callback
   */
  off(type, callback) {
    this._listeners.get(type)?.delete(callback);
  }

  /**
   * Client emit — send_message starts a streaming chat turn.
   * @param {string} type
   * @param {object} [payload]
   * @returns {Promise<object | void>}
   */
  async emit(type, payload = {}) {
    if (type === "send_message") {
      return this._streamChat(payload.message ?? "", payload);
    }
    this._dispatch(type, payload);
  }

  /** @param {string} message @param {object} [options] */
  async _streamChat(message, options = {}) {
    const text = (message ?? "").trim();
    if (!text) return { response: "" };
    if (this._submitting) {
      return { response: "", skipped: true };
    }

    this._submitting = true;
    this._chatAbort?.abort();
    this._chatAbort = new AbortController();
    this.connection.streaming = true;
    this.connection.mode = "streaming";
    if (this._store) {
      this._store.setState({ lastError: null, connectionState: "streaming" });
    }

    const requestId = options.request_id ?? createClientRequestId();
    const conversationId = options.conversation_id ?? getStoredConversationId();

    let responseText = "";
    let orchestrationPayload = null;

    try {
      const httpResponse = await fetch("/chat/stream", {
        method: "POST",
        signal: this._chatAbort.signal,
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          message: text,
          user: options.user ?? null,
          conversation_id: conversationId,
          request_id: requestId,
          client_metadata: options.client_metadata ?? null,
        }),
      });

      if (!httpResponse.ok) {
        const detail = await httpResponse.text();
        throw new Error(detail || httpResponse.statusText);
      }

      const reader = httpResponse.body?.getReader();
      if (!reader) {
        throw new Error("Flux SSE indisponible.");
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parsed = parseSseBuffer(buffer);
        buffer = parsed.remainder;
        for (const frame of parsed.events) {
          if (frame.event === "conversation_finished") {
            if (frame.data.response) {
              responseText = frame.data.response;
            }
            if (frame.data.conversation_id) {
              saveConversationId(frame.data.conversation_id);
            }
            if (frame.data.request_id) {
              saveRequestId(frame.data.request_id);
            }
            orchestrationPayload = frame.data.orchestration ?? frame.data;
            this._applyOrchestrationMeta(frame.data);
          }
          this._handleBackendEvent(frame.event, frame.data, frame.id);
        }
      }

      return {
        response: responseText,
        orchestration: orchestrationPayload,
        conversation_id: conversationId,
        request_id: requestId,
        ...options,
      };
    } finally {
      this._submitting = false;
      this.connection.streaming = false;
      this.connection.mode = this.connection.connected ? "idle" : "disconnected";
      if (this._store) {
        this._store.setState({
          connectionState: this.connection.connected ? "connected" : "disconnected",
        });
      }
    }
  }

  /** @param {object} data */
  _applyOrchestrationMeta(data) {
    if (!this._store) return;
    this._store.setState({
      conversationId: data.conversation_id ?? this._store.getState().conversationId,
      lastRequestId: data.request_id ?? null,
      detectedIntent: data.detected_intent ?? data.orchestration?.detected_intent ?? null,
      orchestrationConfidence:
        data.confidence ?? data.orchestration?.confidence ?? null,
      systemsUsed: data.systems_used ?? data.orchestration?.systems_used ?? null,
      reasoningSummary:
        data.reasoning_summary ?? data.orchestration?.reasoning_summary ?? "",
      orchestrationDuration:
        data.duration_seconds ?? data.orchestration?.duration_seconds ?? null,
      approvalRequired: Boolean(
        data.approval_required ?? data.orchestration?.approval_required,
      ),
      approvalId: data.approval_id ?? null,
      approvalSummary: data.approval_summary ?? null,
    });
  }

  _openEventSource() {
    // Prefer session cookies (sent automatically by EventSource on same origin).
    // Legacy bearer mode still passes ?token= when a localStorage secret exists.
    const token = getStoredToken();
    const params = new URLSearchParams();
    if (token) params.set("token", token);
    const url = `/events/stream${params.toString() ? `?${params}` : ""}`;

    this._eventSource = new EventSource(url);

    this._eventSource.onopen = () => {
      this.connection.connected = true;
      this.connection.mode = "idle";
      this._reconnectAttempts = 0;
      this.connection.reconnectAttempts = 0;
      if (this._store) {
        this._store.setState({ connectionState: "connected" });
      }
      this._dispatch("connection", { state: "connected" });
    };

    this._eventSource.onerror = () => {
      this.connection.connected = false;
      this.connection.mode = "disconnected";
      if (this._store) {
        this._store.setState({ connectionState: "disconnected" });
      }
      this._eventSource?.close();
      this._eventSource = null;
      this._dispatch("connection", { state: "disconnected" });
      this._scheduleReconnect();
    };

    const eventTypes = [
      ...COGNITIVE_STREAM_EVENTS,
      "brain_state",
      "conversation_started",
      "conversation_stage",
      "conversation_finished",
      "memory_activity",
      "tool_activity",
      "presence",
      "thinking",
      "planning",
      "reasoning",
      "status",
      "telemetry",
      "error",
      "orchestration_started",
      "orchestration_finished",
      "approval_required",
    ];

    for (const type of eventTypes) {
      this._eventSource.addEventListener(type, (event) => {
        /** @type {MessageEvent} */
        const msg = event;
        let data = {};
        try {
          data = JSON.parse(msg.data);
        } catch {
          data = { raw: msg.data };
        }
        const eventId = msg.lastEventId || null;
        this._handleBackendEvent(type, data, eventId);
      });
    }
  }

  _scheduleReconnect() {
    if (!this._shouldReconnect) return;
    if (this._reconnectTimer !== null) return;

    this._reconnectAttempts += 1;
    this.connection.reconnectAttempts = this._reconnectAttempts;
    const delay = Math.min(
      RECONNECT_MAX_MS,
      RECONNECT_BASE_MS * 2 ** Math.min(this._reconnectAttempts - 1, 4),
    );

    this._reconnectTimer = window.setTimeout(() => {
      this._reconnectTimer = null;
      if (this._shouldReconnect && !this._eventSource) {
        this._openEventSource();
        this._flushMissedQueue();
      }
    }, delay);
  }

  _flushMissedQueue() {
    if (!this._missedQueue.length) return;
    const pending = [...this._missedQueue];
    this._missedQueue = [];
    for (const frame of pending) {
      this._handleBackendEvent(frame.event, frame.data, frame.id, { replay: true });
    }
  }

  /**
   * @param {string} type
   * @param {object} data
   * @param {string | null} [eventId]
   * @param {{ replay?: boolean }} [options]
   */
  _handleBackendEvent(type, data, eventId = null, options = {}) {
    if (eventId) {
      this.connection.lastEventId = eventId;
    }

    if (type === "brain_state" && data.state) {
      this.state.brainState = data.state;
    }
    if (type === "presence" && data.state) {
      this.state.presence = data.state;
    }
    if (type === "status") {
      this.state.user = data.user ?? this.state.user;
      this.state.version = data.version ?? this.state.version;
    }

    routeBackendEvent(this._brain, this._store, type, data);
    this._dispatch(type, data);

    if (type === "conversation_finished" && !options.replay) {
      this._dispatch("response", { text: data.response ?? "" });
    }
  }

  /** @param {string} type @param {object} data */
  _dispatch(type, data) {
    const listeners = this._listeners.get(type);
    if (!listeners) return;
    for (const listener of listeners) {
      try {
        listener(data);
      } catch {
        /* listener isolation */
      }
    }
    const wildcard = this._listeners.get("*");
    if (wildcard) {
      for (const listener of wildcard) {
        try {
          listener({ type, data });
        } catch {
          /* listener isolation */
        }
      }
    }
  }

}

/**
 * Attach BackendBridge API to a CognitiveStateEngine instance.
 * @param {import("./cognitive-state-engine.js").CognitiveStateEngine} brain
 * @param {import("./state-store.js").StateStore | null} store
 * @returns {BackendBridge}
 */
export function attachBackendBridge(brain, store = null) {
  const bridge = new BackendBridge(brain, store);

  brain.connect = () => bridge.connect();
  brain.disconnect = () => bridge.disconnect();
  brain.on = (type, cb) => bridge.on(type, cb);
  brain.off = (type, cb) => bridge.off(type, cb);
  brain.emit = (type, payload) => bridge.emit(type, payload);
  Object.defineProperty(brain, "connection", {
    configurable: true,
    get() {
      return bridge.connection;
    },
  });
  Object.defineProperty(brain, "state", {
    configurable: true,
    get() {
      return bridge.state;
    },
  });

  const pipelineStore = brain.getPipelineStore();
  Object.defineProperty(brain, "thinking", {
    configurable: true,
    get() {
      return pipelineStore.thinking;
    },
  });
  Object.defineProperty(brain, "currentStage", {
    configurable: true,
    get() {
      return pipelineStore.currentStage;
    },
  });
  Object.defineProperty(brain, "stageHistory", {
    configurable: true,
    get() {
      return pipelineStore.stageHistory;
    },
  });
  Object.defineProperty(brain, "timeline", {
    configurable: true,
    get() {
      return pipelineStore.timeline;
    },
  });
  Object.defineProperty(brain, "pipeline", {
    configurable: true,
    get() {
      return pipelineStore.snapshot();
    },
  });

  brain._backendBridge = bridge;

  return bridge;
}
