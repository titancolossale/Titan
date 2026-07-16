/** Titan Frontend V2 — Conversation Manager (Phase E7 + E8 + Web Runtime V1). */

import { MessageRenderer } from "./message-renderer.js";
import { CONVERSATION_ACTIVITY_EVENTS } from "./conversation-activity-engine.js";
import { getStoredConversationId } from "../core/conversation-session.js";
import { SessionExpiredError } from "../core/backend-bridge.js";

/**
 * Orchestrates composer UX, message rendering, and backend chat stream.
 */
export class ConversationManager {
  /**
   * @param {{ brain: import("../core/cognitive-state-engine.js").CognitiveStateEngine, store?: import("../core/state-store.js").StateStore }} deps
   */
  constructor(deps) {
    this._brain = deps.brain;
    this._store = deps.store ?? null;
    this._renderer = new MessageRenderer({ store: deps.store ?? null });
    /** @type {boolean} */
    this._busy = false;
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
  }

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

    const messages = document.getElementById("tdl-v2-chat-messages");
    if (messages) {
      this._renderer.setContainer(messages);
    }

    this._sendBtn?.addEventListener("click", () => this.send());
    this._stopBtn?.addEventListener("click", () => this.interrupt());
    this._retryBtn?.addEventListener("click", () => this.retryLast());

    this._input?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        this.send();
      }
    });

    this._brain.conversation.onActivity((event) => {
      this._onConversationActivity(event);
    });

    this._brain.on?.("response", (data) => {
      if (data.text) {
        this._streamResponse(data.text, data.metadata ?? null);
      }
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
  }

  /** Send current composer text through the backend SSE chat stream. */
  async send(messageOverride = null) {
    const text = (messageOverride ?? this._input?.value.trim() ?? "").trim();
    if (!text || this._busy) return;

    this._busy = true;
    this._lastFailedMessage = null;
    this._hideRetry();
    this._setComposerBusy(true);
    this._renderer.appendMessage(text, "user");

    if (!messageOverride && this._input) {
      this._input.value = "";
    }

    this._showThinking(true);

    try {
      const result = await this._brain.emit?.("send_message", {
        message: text,
        conversation_id: this._store?.getState().conversationId ?? getStoredConversationId(),
      });

      if (result?.skipped) {
        this._showThinking(false);
        this._setComposerBusy(false);
        this._busy = false;
        return;
      }

      const response = result?.response ?? "";
      if (response && !this._streamTimer) {
        this._streamResponse(response, result?.orchestration ?? null);
      }

      if (result?.orchestration?.approval_required || result?.approval_required) {
        this._renderer.showApprovalBanner(
          result.approval_summary ?? "Une action nécessite ton approbation.",
          result,
        );
      }
    } catch (error) {
      if (error instanceof SessionExpiredError || error?.name === "SessionExpiredError") {
        this._showThinking(false);
        this._setComposerBusy(false);
        this._busy = false;
        this._renderer.appendMessage(
          "Session expirée. Redirection vers la connexion…",
          "system",
        );
        return;
      }
      this._lastFailedMessage = text;
      const retryable = error?.retryable !== false;
      if (retryable) {
        this._showRetry();
      } else {
        this._hideRetry();
      }
      this._showThinking(false);
      this._setComposerBusy(false);
      this._busy = false;
      const message =
        error instanceof Error ? error.message : "Erreur de connexion au backend Titan.";
      this._renderer.appendMessage(message, "system");
      this._store?.setState({ lastError: message });
    }
  }

  /** Retry the last failed message without retyping. */
  async retryLast() {
    if (!this._lastFailedMessage || this._busy) return;
    await this.send(this._lastFailedMessage);
  }

  /** Cancel in-flight chat stream and streaming display. */
  interrupt() {
    if (this._streamTimer !== null) {
      window.clearInterval(this._streamTimer);
      this._streamTimer = null;
    }
    this._brain._backendBridge?._chatAbort?.abort();
    this._brain.conversation.cancel?.();
    this._showThinking(false);
    this._setComposerBusy(false);
    this._busy = false;
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
      this._showThinking(false);
      this._setComposerBusy(false);
      this._busy = false;
      this._lastFailedMessage = null;
      this._hideRetry();
    };

    if (reduced || fullText.length <= chunkSize) {
      this._renderer.setBubbleText(bubble, fullText);
      finish();
      return;
    }

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

  /** @param {object} event */
  _onConversationActivity(event) {
    if (event.type === CONVERSATION_ACTIVITY_EVENTS.FINISHED) {
      if (!this._streamTimer) {
        this._showThinking(false);
        this._setComposerBusy(false);
        this._busy = false;
      }
    }
  }

  /** @param {boolean} visible */
  _showThinking(visible) {
    if (!this._thinkingEl) return;
    this._thinkingEl.dataset.visible = String(visible);
    this._thinkingEl.hidden = !visible;
  }

  /** @param {boolean} busy */
  _setComposerBusy(busy) {
    if (this._sendBtn) {
      this._sendBtn.disabled = busy;
    }
    if (this._stopBtn) {
      if (busy) {
        this._stopBtn.removeAttribute("hidden");
      } else {
        this._stopBtn.setAttribute("hidden", "");
      }
    }
  }

  _showRetry() {
    if (this._retryBtn) {
      this._retryBtn.removeAttribute("hidden");
    }
  }

  _hideRetry() {
    if (this._retryBtn) {
      this._retryBtn.setAttribute("hidden", "");
    }
  }

  destroy() {
    this.interrupt();
  }
}
