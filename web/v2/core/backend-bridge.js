/** Titan Frontend V2 — Backend Bridge (Phase E8 + Web Runtime V1 + 11.1B). */

import { routeBackendEvent } from "./event-router.js";
import { COGNITIVE_STREAM_EVENTS } from "./cognitive-pipeline-store.js";
import { authHeaders, fetchAuthStatus, getStoredToken, redirectToLogin } from "./web-auth.js";
import {
  createClientRequestId,
  getStoredConversationId,
  saveConversationId,
  saveRequestId,
} from "./conversation-session.js";
import { chatDiag } from "./chat-diagnostics.js";

const RECONNECT_BASE_MS = 1500;
const RECONNECT_MAX_MS = 30000;
const RECONNECT_AUTH_FAIL_MAX = 2;
const RECONNECT_HARD_MAX = 12;
/** Client-side chat deadline — must stay below typical proxy idle limits. */
export const CHAT_CLIENT_TIMEOUT_MS = 55000;

/** Thrown when the session cookie/token is no longer valid. */
export class SessionExpiredError extends Error {
  constructor(message = "Session expirée.") {
    super(message);
    this.name = "SessionExpiredError";
    this.code = "session_expired";
    this.retryable = false;
  }
}

/** Structured chat/stream failure with optional retry flag. */
export class ChatRequestError extends Error {
  /**
   * @param {string} message
   * @param {{ code?: string, retryable?: boolean, status?: number, requestId?: string | null }} [options]
   */
  constructor(message, options = {}) {
    super(message);
    this.name = "ChatRequestError";
    this.code = options.code ?? "request_failed";
    this.retryable = Boolean(options.retryable);
    this.status = options.status ?? 0;
    this.requestId = options.requestId ?? null;
  }
}

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
    /** @type {number} */
    this._authFailStreak = 0;
    /** @type {boolean} */
    this._authBlocked = false;
    /** @type {ReturnType<typeof setTimeout> | null} */
    this._reconnectTimer = null;
    /** @type {Array<{ event: string, data: object, id: string | null }>} */
    this._missedQueue = [];
    /** @type {boolean} */
    this._submitting = false;
    /** @type {boolean} */
    this._connecting = false;
    this._boundVisibility = () => this._onVisibilityChange();
    document.addEventListener("visibilitychange", this._boundVisibility);

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
  async connect() {
    if (this._eventSource) return;
    if (this._connecting) return;

    this._connecting = true;
    try {
      // Explicit connect clears prior unauthorized lock (e.g. after login).
      this._authBlocked = false;
      this._authFailStreak = 0;
      this._shouldReconnect = true;
      this._reconnectAttempts = 0;

      const allowed = await this._ensureAuthorizedToStream();
      if (!allowed) {
        this._authBlocked = true;
        this._shouldReconnect = false;
        chatDiag("CHAT_ERROR", { code: "sse_auth_blocked", status: "not_authenticated" });
        return;
      }

      this._openEventSource();
      this._flushMissedQueue();
    } finally {
      this._connecting = false;
    }
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

  /** Tear down listeners (logout / app destroy). */
  destroy() {
    this.disconnect();
    document.removeEventListener("visibilitychange", this._boundVisibility);
  }

  _onVisibilityChange() {
    if (document.hidden) {
      // Pause reconnect storms while the tab is not visible.
      if (this._reconnectTimer !== null) {
        window.clearTimeout(this._reconnectTimer);
        this._reconnectTimer = null;
      }
      return;
    }
    if (
      this._shouldReconnect &&
      !this._eventSource &&
      !this._authBlocked &&
      this._reconnectTimer === null
    ) {
      this._scheduleReconnect({ resumeVisible: true });
    }
  }

  /**
   * Avoid unauthorized /events/stream retry storms before login.
   * @returns {Promise<boolean>}
   */
  async _ensureAuthorizedToStream() {
    try {
      const status = await fetchAuthStatus();
      if (!status.auth_required) return true;
      if (status.authenticated) return true;
      if (getStoredToken()) return true;
      return false;
    } catch {
      // Network blip — allow one attempt; error path will back off.
      return Boolean(getStoredToken());
    }
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
      chatDiag("CHAT_ERROR", { code: "duplicate_request", status: "skipped" });
      return { response: "", skipped: true };
    }

    this._submitting = true;
    this._chatAbort?.abort();
    this._chatAbort = new AbortController();
    const requestId = options.request_id ?? options.client_request_id ?? createClientRequestId();
    const conversationId = options.conversation_id ?? getStoredConversationId();
    const startedAt = performance.now();

    /** @type {ReturnType<typeof setTimeout> | null} */
    let timeoutId = window.setTimeout(() => {
      const err = new DOMException("Chat request timed out", "AbortError");
      // Tag so ConversationManager can show provider_timeout, not silent abort.
      /** @type {any} */
      (err).code = "provider_timeout";
      this._chatAbort?.abort(err);
    }, CHAT_CLIENT_TIMEOUT_MS);

    this.connection.streaming = true;
    this.connection.mode = "streaming";
    if (this._store) {
      this._store.setState({
        lastError: null,
        connectionState: "streaming",
        lastRequestId: requestId,
        chatPending: true,
      });
    }

    let responseText = "";
    let orchestrationPayload = null;
    /** @type {ChatRequestError | null} */
    let streamError = null;

    try {
      chatDiag("CHAT_HTTP_SENT", {
        request_id: requestId,
        message_length: text.length,
        conversation_id: conversationId,
      });

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
          client_request_id: requestId,
          client_metadata: options.client_metadata ?? null,
        }),
      });

      if (!httpResponse.ok) {
        if (httpResponse.status === 401) {
          chatDiag("CHAT_API_RESPONSE", {
            request_id: requestId,
            status: 401,
            code: "unauthenticated",
            duration_ms: Math.round(performance.now() - startedAt),
          });
          redirectToLogin();
          throw new SessionExpiredError();
        }
        let detail = "";
        let code = httpResponse.status === 403 ? "unauthenticated" : "request_failed";
        let retryable = httpResponse.status >= 500;
        try {
          const raw = await httpResponse.text();
          detail = raw;
          try {
            const parsed = JSON.parse(raw);
            if (parsed?.error?.message) {
              detail = parsed.error.message;
              code = parsed.error.code ?? parsed.code ?? code;
              retryable = Boolean(parsed.error.retryable ?? retryable);
            } else if (parsed?.detail) {
              detail = typeof parsed.detail === "string"
                ? parsed.detail
                : JSON.stringify(parsed.detail);
              if (httpResponse.status === 403) {
                code = "invalid_request";
                detail = "Requête refusée (session/CSRF). Recharge la page ou reconnecte-toi.";
                retryable = true;
              }
            } else if (parsed?.error && typeof parsed.error === "string") {
              detail = parsed.error;
              code = parsed.code ?? code;
            }
          } catch {
            /* keep raw text */
          }
        } catch {
          detail = httpResponse.statusText;
        }
        if (httpResponse.status === 403 && /csrf|forbidden/i.test(String(detail))) {
          code = "invalid_request";
          detail = "Requête refusée (session/CSRF). Recharge la page ou reconnecte-toi.";
          retryable = true;
        }
        throw new ChatRequestError(detail || httpResponse.statusText, {
          code,
          retryable,
          status: httpResponse.status,
          requestId,
        });
      }

      const reader = httpResponse.body?.getReader();
      if (!reader) {
        throw new ChatRequestError("Flux SSE indisponible.", {
          code: "response_parse_error",
          retryable: true,
          requestId,
        });
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
            if (frame.data.error_code || frame.data.ok === false) {
              streamError = new ChatRequestError(
                frame.data.response
                  || frame.data.error_code
                  || "Erreur pendant le traitement Titan.",
                {
                  code: frame.data.error_code ?? "brain_failure",
                  retryable: frame.data.retryable !== false,
                  requestId: frame.data.request_id ?? requestId,
                },
              );
            }
          }
          if (frame.event === "error" && !responseText) {
            streamError = new ChatRequestError(
              frame.data.message ?? "Erreur pendant le traitement Titan.",
              {
                code: frame.data.code ?? "unexpected_error",
                retryable: true,
                requestId: frame.data.request_id ?? requestId,
              },
            );
          }
          this._handleBackendEvent(frame.event, frame.data, frame.id);
        }
      }

      chatDiag("CHAT_API_RESPONSE", {
        request_id: requestId,
        status: httpResponse.status,
        ok: !streamError || Boolean(responseText),
        response_length: responseText.length,
        duration_ms: Math.round(performance.now() - startedAt),
      });

      if (streamError && !responseText) {
        throw streamError;
      }

      return {
        response: responseText,
        orchestration: orchestrationPayload,
        conversation_id: conversationId,
        request_id: requestId,
        client_request_id: requestId,
        ...options,
      };
    } catch (error) {
      const isTimeout =
        error?.code === "provider_timeout" ||
        (error?.name === "AbortError" &&
          (String(error?.message || "").includes("timed out") ||
            performance.now() - startedAt >= CHAT_CLIENT_TIMEOUT_MS - 50));

      if (isTimeout) {
        chatDiag("CHAT_ERROR", {
          request_id: requestId,
          code: "provider_timeout",
          duration_ms: Math.round(performance.now() - startedAt),
        });
        throw new ChatRequestError(
          "Titan met trop de temps à répondre. Réessaie.",
          {
            code: "provider_timeout",
            retryable: true,
            requestId,
          },
        );
      }

      if (error?.name === "AbortError") {
        chatDiag("CHAT_ERROR", {
          request_id: requestId,
          code: "aborted",
          duration_ms: Math.round(performance.now() - startedAt),
        });
        throw error;
      }

      if (error instanceof SessionExpiredError || error instanceof ChatRequestError) {
        throw error;
      }

      chatDiag("CHAT_ERROR", {
        request_id: requestId,
        code: "network_error",
        duration_ms: Math.round(performance.now() - startedAt),
      });
      throw new ChatRequestError(
        error instanceof Error ? error.message : "Erreur réseau.",
        {
          code: "network_error",
          retryable: true,
          requestId,
        },
      );
    } finally {
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
        timeoutId = null;
      }
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
    const runtime = data.runtime ?? data.orchestration?.runtime ?? null;
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
      runtimeStages: runtime?.stages ?? null,
      runtimeMemoryUsed: runtime?.memory_used ?? null,
      runtimeToolsUsed: runtime?.tools_used ?? null,
      runtimeModel: runtime?.model ?? null,
      lastError: data.error_code
        ? (data.response ?? data.error_code)
        : this._store.getState().lastError,
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
      this._authFailStreak = 0;
      this._authBlocked = false;
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
      // EventSource does not expose HTTP status; probe auth after repeated failures.
      void this._handleStreamError();
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

  async _handleStreamError() {
    if (!this._shouldReconnect || this._authBlocked) return;
    if (document.hidden) return;

    this._authFailStreak += 1;
    // Probe auth early — EventSource cannot expose 401 status.
    if (this._authFailStreak >= RECONNECT_AUTH_FAIL_MAX) {
      const allowed = await this._ensureAuthorizedToStream();
      if (!allowed) {
        this._authBlocked = true;
        this._shouldReconnect = false;
        chatDiag("CHAT_ERROR", {
          code: "sse_unauthorized",
          retries: this._authFailStreak,
        });
        this._dispatch("connection", { state: "unauthorized" });
        return;
      }
      this._authFailStreak = 0;
    }

    this._scheduleReconnect();
  }

  /**
   * @param {{ resumeVisible?: boolean }} [options]
   */
  _scheduleReconnect(options = {}) {
    if (!this._shouldReconnect || this._authBlocked) return;
    if (this._reconnectTimer !== null) return;
    if (document.hidden && !options.resumeVisible) return;

    this._reconnectAttempts += 1;
    this.connection.reconnectAttempts = this._reconnectAttempts;

    if (this._reconnectAttempts > RECONNECT_HARD_MAX) {
      this._shouldReconnect = false;
      this._dispatch("connection", { state: "reconnect_exhausted" });
      return;
    }

    const delay = Math.min(
      RECONNECT_MAX_MS,
      RECONNECT_BASE_MS * 2 ** Math.min(this._reconnectAttempts - 1, 5),
    );

    this._reconnectTimer = window.setTimeout(() => {
      this._reconnectTimer = null;
      if (!this._shouldReconnect || this._eventSource || this._authBlocked) return;
      if (document.hidden) return;
      void (async () => {
        const allowed = await this._ensureAuthorizedToStream();
        if (!allowed) {
          this._authBlocked = true;
          this._shouldReconnect = false;
          return;
        }
        this._openEventSource();
        this._flushMissedQueue();
      })();
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
 * Idempotent — reuses an existing bridge when already attached.
 * @param {import("./cognitive-state-engine.js").CognitiveStateEngine} brain
 * @param {import("./state-store.js").StateStore | null} store
 * @returns {BackendBridge}
 */
export function attachBackendBridge(brain, store = null) {
  if (brain._backendBridge instanceof BackendBridge) {
    return brain._backendBridge;
  }

  const bridge = new BackendBridge(brain, store);

  brain.connect = () => bridge.connect();
  brain.disconnect = () => bridge.disconnect();
  brain.destroyBridge = () => bridge.destroy();
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
