/** Titan Frontend V2 — Conversation Manager (Phase E7 + E8 + Web Runtime V1 + 11.1B + 12.1). */

import { MessageRenderer } from "./message-renderer.js";
import { CONVERSATION_ACTIVITY_EVENTS } from "./conversation-activity-engine.js";
import {
  clearConversationSession,
  createClientRequestId,
  getStoredConversationId,
  saveConversationId,
} from "../core/conversation-session.js";
import { SessionExpiredError, ChatRequestError } from "../core/backend-bridge.js";
import { authHeaders } from "../core/web-auth.js";
import { chatDiag } from "../core/chat-diagnostics.js";
import {
  archiveConversation,
  createConversation,
  listConversations,
  loadConversation,
  renameConversation,
} from "../core/conversation-api.js";

/** Max UI text updates per second while streaming tokens. */
const STREAM_UI_HZ = 24;

/**
 * Yield to the browser so optimistic DOM updates paint before network work.
 * @returns {Promise<void>}
 */
function yieldForPaint() {
  return new Promise((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => resolve());
    });
  });
}

/**
 * Orchestrates composer UX, message rendering, and backend chat stream.
 */
export class ConversationManager {
  /**
   * @param {{ brain: import("../core/cognitive-state-engine.js").CognitiveStateEngine, store?: import("../core/state-store.js").StateStore, neural?: { notifyInteractive?: Function } | null }} deps
   */
  constructor(deps) {
    this._brain = deps.brain;
    this._store = deps.store ?? null;
    this._neural = deps.neural ?? null;
    this._renderer = new MessageRenderer({ store: deps.store ?? null });
    /** @type {boolean} */
    this._busy = false;
    /** @type {boolean} */
    this._domBound = false;
    /** @type {ReturnType<typeof setInterval> | null} */
    this._streamTimer = null;
    /** @type {HTMLElement | null} */
    this._thinkingEl = null;
    /** @type {HTMLTextAreaElement | null} */
    this._input = null;
    /** @type {HTMLButtonElement | null} */
    this._sendBtn = null;
    /** @type {HTMLButtonElement | null} */
    this._stopBtn = null;
    /** @type {string | null} */
    this._lastFailedMessage = null;
    /** @type {HTMLElement | null} */
    this._retryBtn = null;
    /** @type {string | null} */
    this._activeRequestId = null;
    /** Monotonic generation — discard abandoned/late responses. */
    this._sendGeneration = 0;
    /** @type {number} */
    this._activeGeneration = 0;
    /** @type {ReturnType<typeof setInterval> | null} */
    this._thinkingTimer = null;
    /** @type {number} */
    this._thinkingStartedAt = 0;
    /** Live token stream state (Phase 12.1). */
    this._liveStream = null;
    /** @type {number | null} */
    this._liveRaf = null;
    /** @type {string} */
    this._liveBuffer = "";
    /** @type {string} */
    this._liveDisplayed = "";
    /** @type {number} */
    this._lastLivePaint = 0;
    /** @type {boolean} */
    this._receivedLiveDelta = false;
    /** @type {(event: Event) => void} */
    this._onSendClick = () => {
      void this.send();
    };
    /** @type {(event: Event) => void} */
    this._onStopClick = () => this.interrupt();
    /** @type {(event: Event) => void} */
    this._onRetryClick = () => {
      void this.retryLast();
    };
    /** @type {(event: KeyboardEvent) => void} */
    this._onInputKeydown = (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        void this.send();
      }
    };
    this._onNewConversation = () => {
      void this.startNewConversation();
    };
    this._onRenameConversation = () => {
      void this.renameActiveConversation();
    };
  }

  /**
   * Wire composer + chat panel listeners. Idempotent — safe to call after panel mount.
   */
  bindDom() {
    this._input = /** @type {HTMLTextAreaElement | null} */ (
      document.getElementById("tdl-v2-chat-input")
    );
    this._sendBtn = /** @type {HTMLButtonElement | null} */ (
      document.getElementById("tdl-v2-send-chat")
    );
    this._stopBtn = /** @type {HTMLButtonElement | null} */ (
      document.getElementById("tdl-v2-stop-generation")
    );
    this._thinkingEl = document.getElementById("tdl-v2-thinking-indicator");
    this._retryBtn = document.getElementById("tdl-v2-chat-retry");

    try {
      this._renderer.ensureContainer();
    } catch {
      /* panel may mount shortly after boot — send() re-resolves */
    }

    if (this._domBound) {
      return;
    }
    this._domBound = true;

    this._sendBtn?.addEventListener("click", this._onSendClick);
    this._stopBtn?.addEventListener("click", this._onStopClick);
    this._retryBtn?.addEventListener("click", this._onRetryClick);
    this._input?.addEventListener("keydown", this._onInputKeydown);
    document.getElementById("tdl-v2-new-conversation")?.addEventListener(
      "click",
      this._onNewConversation,
    );
    document.getElementById("tdl-v2-rename-conversation")?.addEventListener(
      "click",
      this._onRenameConversation,
    );

    this._brain.conversation.onActivity((event) => {
      this._onConversationActivity(event);
    });

    this._brain.on?.("response", (data) => {
      if (data.text && !this._streamTimer && !this._receivedLiveDelta) {
        this._streamResponse(data.text, data.metadata ?? null);
      }
    });

    // Progressive provider deltas from BackendBridge.
    this._brain.on?.("text_delta", (data) => {
      this._onTextDelta(data?.text ?? "");
    });
    this._brain.on?.("response_started", () => {
      this._ensureLiveBubble();
    });

    this._brain.on?.("approval_required", (data) => {
      this._renderer.showApprovalBanner(data.summary ?? "Approbation requise.", data);
    });

    if (this._store) {
      const conversationId = getStoredConversationId();
      if (conversationId) {
        this._store.setState({ conversationId });
      }
    }

    void this.restoreActiveConversation();
  }

  /** Re-resolve DOM nodes after delayed panel mount (boot race). */
  refreshDom() {
    this._input = /** @type {HTMLTextAreaElement | null} */ (
      document.getElementById("tdl-v2-chat-input")
    );
    this._sendBtn = /** @type {HTMLButtonElement | null} */ (
      document.getElementById("tdl-v2-send-chat")
    );
    this._stopBtn = /** @type {HTMLButtonElement | null} */ (
      document.getElementById("tdl-v2-stop-generation")
    );
    this._thinkingEl = document.getElementById("tdl-v2-thinking-indicator");
    this._retryBtn = document.getElementById("tdl-v2-chat-retry");
    try {
      this._renderer.ensureContainer();
    } catch {
      /* still mounting */
    }
  }

  /** Send current composer text through the backend SSE chat stream. */
  async send(messageOverride = null) {
    this.refreshDom();
    const text = (messageOverride ?? this._input?.value.trim() ?? "").trim();
    if (!text || this._busy) return;

    this._busy = true;
    this._lastFailedMessage = null;
    this._hideRetry();
    this._setComposerBusy(true);
    this._setChatPending(true);
    this._neural?.notifyInteractive?.(4000);
    this._resetLiveStream();

    const startedAt = performance.now();
    let requestId = null;
    const generation = ++this._sendGeneration;
    this._activeGeneration = generation;

    try {
      // Optimistic UI BEFORE any network await — must paint first.
      this._renderer.appendMessage(text, "user");

      if (!messageOverride && this._input) {
        this._input.value = "";
      }

      this._showThinking(true);
      this._startThinkingElapsed();
      await yieldForPaint();

      this._store?.setState({
        chatStage: "submitting",
        chatElapsedMs: 0,
        lastHttpStatus: null,
        providerDurationMs: null,
      });

      requestId = createClientRequestId();
      this._activeRequestId = requestId;

      chatDiag("CHAT_SUBMIT_START", {
        message_length: text.length,
        request_id: requestId,
        conversation_id: this._store?.getState().conversationId ?? getStoredConversationId(),
      });

      let result;
      try {
        result = await this._brain.emit?.("send_message", {
          message: text,
          request_id: requestId,
          client_request_id: requestId,
          conversation_id: this._store?.getState().conversationId ?? getStoredConversationId(),
        });
      } catch (emitErr) {
        throw emitErr;
      }

      // Abandoned after Stop / newer send — never render late results.
      if (generation !== this._activeGeneration) {
        chatDiag("CHAT_ERROR", {
          request_id: requestId,
          code: "abandoned",
          status: "discarded",
        });
        return;
      }

      requestId = result?.request_id ?? requestId;
      this._activeRequestId = requestId;
      if (result?.conversation_id) {
        saveConversationId(result.conversation_id);
        this._store?.setState({ conversationId: result.conversation_id });
      }
      this._store?.setState({
        lastRequestId: requestId,
        chatStage: "response_received",
        lastHttpStatus: result?.http_status ?? 200,
        providerDurationMs: result?.provider_duration_ms ?? null,
        chatElapsedMs: Math.round(performance.now() - startedAt),
      });

      if (result?.skipped) {
        chatDiag("CHAT_ERROR", {
          request_id: requestId,
          code: "duplicate_request",
          status: "skipped",
        });
        return;
      }

      if (result?.error_code === "brain_timeout" || result?.error_code === "provider_timeout") {
        throw new ChatRequestError(
          result?.response
            || "Titan n’a pas pu terminer sa réponse dans le délai prévu.",
          {
            code: result.error_code,
            retryable: true,
            requestId,
          },
        );
      }

      const response = result?.response ?? "";
      if (this._receivedLiveDelta) {
        this._finalizeLiveStream(response, result?.orchestration ?? null);
        chatDiag("CHAT_UI_RENDERED", {
          request_id: requestId,
          response_length: response.length,
          duration_ms: Math.round(performance.now() - startedAt),
          streamed: true,
          ttft_ms: result?.ttft_ms ?? null,
        });
      } else if (response && !this._streamTimer) {
        this._streamResponse(response, result?.orchestration ?? null);
        chatDiag("CHAT_UI_RENDERED", {
          request_id: requestId,
          response_length: response.length,
          duration_ms: Math.round(performance.now() - startedAt),
          streamed: false,
        });
      } else if (!response && !this._streamTimer) {
        this._clearBusyState();
      }

      if (result?.orchestration?.approval_required || result?.approval_required) {
        this._renderer.showApprovalBanner(
          result.approval_summary ?? "Une action nécessite ton approbation.",
          result,
        );
      }
      void this.refreshConversationList();
    } catch (error) {
      if (error instanceof SessionExpiredError || error?.name === "SessionExpiredError") {
        chatDiag("CHAT_ERROR", {
          request_id: requestId ?? error?.requestId ?? null,
          code: "unauthenticated",
        });
        this._clearBusyState();
        try {
          this._renderer.appendErrorCard(
            "Session expirée. Redirection vers la connexion…",
            { code: "unauthenticated", requestId },
          );
        } catch {
          /* container race during redirect */
        }
        return;
      }

      if (generation !== this._activeGeneration) {
        this._clearBusyState();
        return;
      }

      const aborted =
        error?.name === "AbortError" ||
        error?.code === "provider_timeout" ||
        error?.code === "brain_timeout" ||
        (typeof error?.message === "string" && /aborted|timeout/i.test(error.message));

      // User-initiated stop — not a hard failure.
      if (
        error?.name === "AbortError"
        && error?.code !== "provider_timeout"
        && error?.code !== "brain_timeout"
      ) {
        chatDiag("CHAT_ERROR", {
          request_id: requestId,
          code: "aborted",
        });
        this._clearBusyState();
        this._input?.focus();
        return;
      }

      this._lastFailedMessage = text;
      const retryable = error?.retryable !== false;
      const code =
        error?.code ??
        (aborted ? "brain_timeout" : "network_error");
      const message =
        error instanceof ChatRequestError || error instanceof Error
          ? aborted
            ? (error?.message
              || "Titan n’a pas pu terminer sa réponse dans le délai prévu.")
            : error.message
          : "Erreur de connexion au backend Titan.";

      chatDiag("CHAT_ERROR", {
        request_id: requestId ?? error?.requestId ?? null,
        code,
        retryable,
        duration_ms: Math.round(performance.now() - startedAt),
      });

      this._store?.setState({
        chatStage: "error",
        chatElapsedMs: Math.round(performance.now() - startedAt),
        lastHttpStatus: error?.status ?? null,
      });

      if (retryable) {
        this._showRetry();
      } else {
        this._hideRetry();
      }
      this._clearBusyState();
      try {
        this._renderer.appendErrorCard(message, {
          code,
          requestId: requestId ?? error?.requestId ?? null,
        });
      } catch {
        this._store?.setState({ lastError: message });
      }
      this._store?.setState({ lastError: message });
      this._input?.focus();
    } finally {
      // If typewriter owns busy, leave it; otherwise ensure pending cleared.
      if (!this._streamTimer && this._busy === false) {
        this._setChatPending(false);
      }
    }
  }

  /** Retry the last failed message without retyping. */
  async retryLast() {
    if (!this._lastFailedMessage || this._busy) return;
    await this.send(this._lastFailedMessage);
  }

  /** Cancel in-flight chat stream and streaming display. */
  interrupt() {
    // Invalidate generation so late SSE/provider results are never rendered.
    this._activeGeneration = -1;
    if (this._streamTimer !== null) {
      window.clearInterval(this._streamTimer);
      this._streamTimer = null;
    }
    this._resetLiveStream({ keepBubble: true });
    const requestId = this._activeRequestId;
    this._brain._backendBridge?._chatAbort?.abort();
    this._brain.conversation.cancel?.();
    // Best-effort server-side cancel (does not block UI clear).
    if (requestId) {
      void fetch("/api/chat/cancel", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({ request_id: requestId, client_request_id: requestId }),
      }).catch(() => {});
    }
    this._clearBusyState();
    this._input?.focus();
  }

  /**
   * @param {string} fullText
   * @param {object | null} [metadata]
   */
  _streamResponse(fullText, metadata = null) {
    if (this._streamTimer !== null) {
      window.clearInterval(this._streamTimer);
    }

    const { row, bubble } = this._renderer.beginTitanMessage();
    const reduced = this._store?.getState()?.reducedMotion ?? false;
    const chunkSize = reduced ? fullText.length : 3;
    let index = 0;

    const finish = () => {
      this._renderer.finishStreaming(row);
      if (metadata) {
        this._renderer.attachDevMetadata(row, metadata);
      }
      this._clearBusyState();
      this._lastFailedMessage = null;
      this._hideRetry();
      this._input?.focus();
    };

    if (reduced || fullText.length <= chunkSize) {
      this._renderer.setBubbleText(bubble, fullText, { forceScroll: true });
      finish();
      return;
    }

    // Keep busy true during typewriter so double-submit cannot race.
    this._busy = true;
    this._setComposerBusy(true);

    this._streamTimer = window.setInterval(() => {
      index = Math.min(fullText.length, index + chunkSize);
      this._renderer.setBubbleText(bubble, fullText.slice(0, index));
      if (index >= fullText.length) {
        if (this._streamTimer !== null) {
          window.clearInterval(this._streamTimer);
          this._streamTimer = null;
        }
        finish();
      }
    }, 22);
  }

  _ensureLiveBubble() {
    if (this._liveStream) return;
    this._showThinking(false);
    const started = this._renderer.beginTitanMessage();
    this._liveStream = started;
    this._liveBuffer = "";
    this._liveDisplayed = "";
    this._receivedLiveDelta = true;
  }

  /** @param {string} text */
  _onTextDelta(text) {
    if (!text || this._activeGeneration < 0) return;
    this._ensureLiveBubble();
    this._liveBuffer += text;
    this._scheduleLivePaint();
  }

  _scheduleLivePaint() {
    const minInterval = 1000 / STREAM_UI_HZ;
    const now = performance.now();
    if (this._liveRaf != null) return;
    const delay = Math.max(0, minInterval - (now - this._lastLivePaint));
    this._liveRaf = window.setTimeout(() => {
      this._liveRaf = null;
      this._paintLiveBuffer();
    }, delay);
  }

  _paintLiveBuffer() {
    if (!this._liveStream) return;
    if (this._liveDisplayed === this._liveBuffer) return;
    this._liveDisplayed = this._liveBuffer;
    this._lastLivePaint = performance.now();
    this._renderer.setBubbleText(this._liveStream.bubble, this._liveDisplayed);
  }

  /**
   * @param {string} finalText
   * @param {object | null} [metadata]
   */
  _finalizeLiveStream(finalText, metadata = null) {
    this._ensureLiveBubble();
    const text = finalText || this._liveBuffer;
    this._liveBuffer = text;
    this._paintLiveBuffer();
    if (this._liveRaf != null) {
      window.clearTimeout(this._liveRaf);
      this._liveRaf = null;
    }
    if (this._liveStream) {
      this._renderer.finishStreaming(this._liveStream.row);
      if (metadata) {
        this._renderer.attachDevMetadata(this._liveStream.row, metadata);
      }
    }
    this._liveStream = null;
    this._receivedLiveDelta = false;
    this._clearBusyState();
    this._lastFailedMessage = null;
    this._hideRetry();
    this._input?.focus();
  }

  /** @param {{ keepBubble?: boolean }} [options] */
  _resetLiveStream(options = {}) {
    if (this._liveRaf != null) {
      window.clearTimeout(this._liveRaf);
      this._liveRaf = null;
    }
    if (this._liveStream && !options.keepBubble) {
      this._liveStream.row.remove();
    } else if (this._liveStream) {
      this._renderer.finishStreaming(this._liveStream.row);
    }
    this._liveStream = null;
    this._liveBuffer = "";
    this._liveDisplayed = "";
    this._receivedLiveDelta = false;
  }

  async restoreActiveConversation() {
    const conversationId = this._store?.getState().conversationId ?? getStoredConversationId();
    await this.refreshConversationList();
    if (!conversationId) {
      this._setTitle("Nouvelle conversation");
      return;
    }
    try {
      const { conversation, messages } = await loadConversation(conversationId);
      saveConversationId(conversation.id);
      this._store?.setState({ conversationId: conversation.id });
      this._setTitle(conversation.title || "Conversation");
      this._renderer.hydrateMessages(messages);
    } catch {
      // Stale id — leave empty state; next send creates a new conversation.
      clearConversationSession();
      this._store?.setState({ conversationId: null });
      this._setTitle("Nouvelle conversation");
    }
  }

  async startNewConversation() {
    this.interrupt();
    try {
      const created = await createConversation();
      const conversation = created.conversation ?? created;
      clearConversationSession();
      saveConversationId(conversation.id);
      this._store?.setState({ conversationId: conversation.id });
      this._renderer.clearMessages();
      this._setTitle(conversation.title || "Nouvelle conversation");
      await this.refreshConversationList();
      this._input?.focus();
    } catch (error) {
      this._renderer.appendErrorCard(
        error?.message || "Impossible de créer une conversation.",
        { code: error?.code },
      );
    }
  }

  async renameActiveConversation() {
    const conversationId = this._store?.getState().conversationId ?? getStoredConversationId();
    if (!conversationId) return;
    const current = document.getElementById("tdl-v2-conversation-title")?.textContent || "";
    const next = window.prompt("Nouveau titre", current);
    if (!next || !next.trim()) return;
    try {
      const renamed = await renameConversation(conversationId, next.trim());
      this._setTitle(renamed.conversation?.title || next.trim());
      await this.refreshConversationList();
    } catch (error) {
      this._renderer.appendErrorCard(
        error?.message || "Impossible de renommer.",
        { code: error?.code },
      );
    }
  }

  async refreshConversationList() {
    const list = document.getElementById("tdl-v2-conversation-list");
    if (!list) return;
    try {
      const { conversations } = await listConversations(12);
      list.replaceChildren();
      const activeId = this._store?.getState().conversationId ?? getStoredConversationId();
      for (const conv of conversations) {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "tdl-v2-conversation__history-item";
        if (conv.id === activeId) {
          btn.dataset.active = "true";
        }
        btn.textContent = conv.title || "Sans titre";
        btn.addEventListener("click", () => {
          void this.switchConversation(conv.id);
        });
        const archiveBtn = document.createElement("button");
        archiveBtn.type = "button";
        archiveBtn.className = "tdl-v2-conversation__archive";
        archiveBtn.title = "Archiver";
        archiveBtn.textContent = "×";
        archiveBtn.addEventListener("click", (event) => {
          event.stopPropagation();
          void this.archiveAndRefresh(conv.id);
        });
        li.append(btn, archiveBtn);
        list.appendChild(li);
      }
    } catch {
      /* list is optional on boot */
    }
  }

  /** @param {string} conversationId */
  async switchConversation(conversationId) {
    if (!conversationId || this._busy) return;
    this.interrupt();
    try {
      const { conversation, messages } = await loadConversation(conversationId);
      saveConversationId(conversation.id);
      this._store?.setState({ conversationId: conversation.id });
      this._setTitle(conversation.title || "Conversation");
      this._renderer.hydrateMessages(messages);
      await this.refreshConversationList();
    } catch (error) {
      this._renderer.appendErrorCard(
        error?.message || "Impossible de charger la conversation.",
        { code: error?.code },
      );
    }
  }

  /** @param {string} conversationId */
  async archiveAndRefresh(conversationId) {
    try {
      await archiveConversation(conversationId, true);
      const active = this._store?.getState().conversationId ?? getStoredConversationId();
      if (active === conversationId) {
        await this.startNewConversation();
      } else {
        await this.refreshConversationList();
      }
    } catch (error) {
      this._renderer.appendErrorCard(
        error?.message || "Impossible d’archiver.",
        { code: error?.code },
      );
    }
  }

  /** @param {string} title */
  _setTitle(title) {
    const el = document.getElementById("tdl-v2-conversation-title");
    if (el) el.textContent = title || "Nouvelle conversation";
  }

  /** @param {object} event */
  _onConversationActivity(event) {
    if (event.type === CONVERSATION_ACTIVITY_EVENTS.FINISHED) {
      // Do not clear busy while typewriter/live stream is still running, or while
      // send() is still awaiting the HTTP result (response dispatch follows).
      if (
        !this._streamTimer
        && !this._receivedLiveDelta
        && !this._brain?._backendBridge?._submitting
      ) {
        this._clearBusyState();
      }
    }
  }

  _clearBusyState() {
    this._stopThinkingElapsed();
    this._showThinking(false);
    this._setComposerBusy(false);
    this._busy = false;
    this._setChatPending(false);
    this._store?.setState({
      chatStage: null,
      chatElapsedMs: null,
    });
  }

  /** @param {boolean} pending */
  _setChatPending(pending) {
    this._store?.setState({ chatPending: pending });
    this._neural?.setChatPending?.(pending);
    if (pending) {
      this._neural?.notifyInteractive?.(8000);
    }
  }

  _startThinkingElapsed() {
    this._stopThinkingElapsed();
    this._thinkingStartedAt = performance.now();
    this._updateThinkingLabel(0);
    this._thinkingTimer = window.setInterval(() => {
      const elapsed = performance.now() - this._thinkingStartedAt;
      this._store?.setState({
        chatElapsedMs: Math.round(elapsed),
        chatStage: "awaiting_provider",
      });
      this._updateThinkingLabel(elapsed);
    }, 1000);
  }

  _stopThinkingElapsed() {
    if (this._thinkingTimer !== null) {
      window.clearInterval(this._thinkingTimer);
      this._thinkingTimer = null;
    }
  }

  /**
   * Progressive French feedback — never fake a Titan reply.
   * @param {number} elapsedMs
   */
  _updateThinkingLabel(elapsedMs) {
    if (!this._thinkingEl) {
      this._thinkingEl = document.getElementById("tdl-v2-thinking-indicator");
    }
    if (!this._thinkingEl) return;
    const sec = Math.floor(elapsedMs / 1000);
    let text = "Titan réfléchit…";
    if (sec >= 30) {
      text = `Le traitement prend plus de temps que prévu… (${sec}s)`;
    } else if (sec >= 10) {
      text = `Titan traite ta demande… (${sec}s)`;
    } else if (sec >= 3) {
      text = `Titan réfléchit… (${sec}s)`;
    }
    // Cheap text-only update — never triggers neural cache rebuild.
    if (this._thinkingEl.textContent !== text) {
      this._thinkingEl.textContent = text;
    }
  }

  /** @param {boolean} visible */
  _showThinking(visible) {
    if (!this._thinkingEl) {
      this._thinkingEl = document.getElementById("tdl-v2-thinking-indicator");
    }
    if (!this._thinkingEl) return;
    this._thinkingEl.dataset.visible = String(visible);
    this._thinkingEl.hidden = !visible;
    if (visible) {
      this._updateThinkingLabel(0);
    } else {
      this._thinkingEl.textContent = "Titan réfléchit…";
    }
  }

  /** @param {boolean} busy */
  _setComposerBusy(busy) {
    if (this._sendBtn) {
      this._sendBtn.disabled = busy;
    }
    if (this._stopBtn) {
      if (busy) {
        this._stopBtn.removeAttribute("hidden");
        this._stopBtn.hidden = false;
      } else {
        this._stopBtn.setAttribute("hidden", "");
        this._stopBtn.hidden = true;
      }
    }
  }

  _showRetry() {
    if (!this._retryBtn) {
      this._retryBtn = document.getElementById("tdl-v2-chat-retry");
    }
    if (this._retryBtn) {
      this._retryBtn.removeAttribute("hidden");
      this._retryBtn.hidden = false;
    }
  }

  _hideRetry() {
    if (!this._retryBtn) {
      this._retryBtn = document.getElementById("tdl-v2-chat-retry");
    }
    if (this._retryBtn) {
      this._retryBtn.setAttribute("hidden", "");
      this._retryBtn.hidden = true;
    }
  }

  destroy() {
    this.interrupt();
    this._stopThinkingElapsed();
    if (this._domBound) {
      this._sendBtn?.removeEventListener("click", this._onSendClick);
      this._stopBtn?.removeEventListener("click", this._onStopClick);
      this._retryBtn?.removeEventListener("click", this._onRetryClick);
      this._input?.removeEventListener("keydown", this._onInputKeydown);
      this._domBound = false;
    }
  }
}
