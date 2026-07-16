/** Titan Frontend V2 — Conversation message renderer (Phase E7 + Web Runtime V1). */

/**
 * Renders user and Titan messages into the chat panel.
 *
 * Container is resolved lazily — the chat panel mounts after ConversationManager
 * bindDom during boot, so a stale null reference must never block submit.
 */
export class MessageRenderer {
  /**
   * @param {{ container?: HTMLElement | null, store?: import("../core/state-store.js").StateStore | null }} [options]
   */
  constructor(options = {}) {
    /** @type {HTMLElement | null} */
    this._container = options.container ?? null;
    /** @type {import("../core/state-store.js").StateStore | null} */
    this._store = options.store ?? null;
  }

  /** @param {HTMLElement | null} container */
  setContainer(container) {
    this._container = container;
  }

  /**
   * Resolve (or re-resolve) the messages container from the live DOM.
   * @returns {HTMLElement}
   */
  ensureContainer() {
    if (this._container?.isConnected) {
      return this._container;
    }
    const live = /** @type {HTMLElement | null} */ (
      document.getElementById("tdl-v2-chat-messages")
    );
    if (!live) {
      throw new Error("MessageRenderer: chat panel not mounted");
    }
    this._container = live;
    return live;
  }

  /** Hide welcome block after first message. */
  _hideWelcome() {
    const welcome = this.ensureContainer().querySelector(".tdl-v2-conversation__welcome");
    if (welcome) {
      welcome.remove();
    }
  }

  /**
   * @param {string} text
   * @param {"user"|"titan"|"system"|"error"} role
   * @returns {HTMLElement}
   */
  appendMessage(text, role) {
    const container = this.ensureContainer();
    this._hideWelcome();

    const row = document.createElement("div");
    const normalized = role === "error" ? "error" : role;
    row.className = `tdl-v2-conversation__message tdl-v2-conversation__message--${normalized}`;
    row.dataset.role = normalized;

    const bubble = document.createElement("div");
    bubble.className = "tdl-v2-conversation__bubble";
    bubble.textContent = text;

    row.appendChild(bubble);
    container.appendChild(row);
    this.scrollToBottom(true);
    return row;
  }

  /**
   * Compact inline error card (retryable failures).
   * @param {string} message
   * @param {{ code?: string, requestId?: string | null }} [meta]
   * @returns {HTMLElement}
   */
  appendErrorCard(message, meta = {}) {
    const container = this.ensureContainer();
    this._hideWelcome();

    const row = document.createElement("div");
    row.className = "tdl-v2-conversation__message tdl-v2-conversation__message--error";
    row.dataset.role = "error";
    if (meta.code) row.dataset.errorCode = meta.code;
    if (meta.requestId) row.dataset.requestId = meta.requestId;

    const bubble = document.createElement("div");
    bubble.className = "tdl-v2-conversation__bubble tdl-v2-conversation__bubble--error";
    bubble.textContent = message;
    row.appendChild(bubble);
    container.appendChild(row);
    this.scrollToBottom(true);
    return row;
  }

  /**
   * Append streaming Titan message with empty bubble for token fill.
   * @returns {{ row: HTMLElement, bubble: HTMLElement }}
   */
  beginTitanMessage() {
    const container = this.ensureContainer();
    this._hideWelcome();

    const row = document.createElement("div");
    row.className = "tdl-v2-conversation__message tdl-v2-conversation__message--titan";
    row.dataset.role = "titan";
    row.dataset.streaming = "true";

    const bubble = document.createElement("div");
    bubble.className = "tdl-v2-conversation__bubble";
    bubble.textContent = "";

    row.appendChild(bubble);
    container.appendChild(row);
    this.scrollToBottom(true);
    return { row, bubble };
  }

  /**
   * @param {HTMLElement} bubble
   * @param {string} text
   */
  setBubbleText(bubble, text) {
    bubble.textContent = text;
    this.scrollToBottom(true);
  }

  /**
   * @param {HTMLElement} row
   */
  finishStreaming(row) {
    row.dataset.streaming = "false";
    delete row.dataset.streaming;
  }

  /**
   * Show approval-required banner above the chat stream area.
   * @param {string} summary
   * @param {object} [data]
   */
  showApprovalBanner(summary, data = {}) {
    try {
      this.ensureContainer();
    } catch {
      return;
    }
    const existing = this._container?.parentElement?.querySelector(
      ".tdl-v2-conversation__approval",
    );
    existing?.remove();

    const banner = document.createElement("div");
    banner.className = "tdl-v2-conversation__approval";
    banner.dataset.approvalId = data.approval_id ?? "";

    const title = document.createElement("strong");
    title.textContent = "Approbation requise";
    const body = document.createElement("span");
    body.textContent = String(summary ?? "");
    banner.appendChild(title);
    banner.appendChild(body);

    this._container?.parentElement?.insertBefore(banner, this._container);
    this._store?.setState({
      approvalRequired: true,
      approvalId: data.approval_id ?? null,
      approvalSummary: summary,
    });
  }

  /**
   * Attach expandable dev metadata under a Titan message (debug mode).
   * @param {HTMLElement} row
   * @param {object} metadata
   */
  attachDevMetadata(row, metadata) {
    const devMode = this._isDevMetadataEnabled();
    if (!devMode) return;

    const details = document.createElement("details");
    details.className = "tdl-v2-conversation__meta";
    const summary = document.createElement("summary");
    summary.textContent = "Détails orchestration";
    details.appendChild(summary);

    const body = document.createElement("pre");
    body.className = "tdl-v2-conversation__meta-body";
    body.textContent = this._formatMetadata(metadata);
    details.appendChild(body);
    row.appendChild(details);
  }

  /** @returns {boolean} */
  _isDevMetadataEnabled() {
    if (this._store?.getState().devMetadataOpen) return true;
    try {
      return localStorage.getItem("titan_v2_dev_metadata") === "true";
    } catch {
      return false;
    }
  }

  /** @param {object} metadata */
  _formatMetadata(metadata) {
    const safe = {
      intent: metadata.detected_intent ?? metadata.intent ?? null,
      confidence: metadata.confidence ?? null,
      systems_used: metadata.systems_used ?? null,
      duration_seconds: metadata.duration_seconds ?? null,
      approval_required: metadata.approval_required ?? false,
      execution_status: metadata.execution_status ?? null,
    };
    return JSON.stringify(safe, null, 2);
  }

  /** @param {boolean} [smooth] */
  scrollToBottom(smooth = false) {
    try {
      this.ensureContainer();
    } catch {
      return;
    }
    const scroll = this._container?.closest(".tdl-v2-conversation__scroll");
    if (!scroll) return;
    scroll.scrollTo({
      top: scroll.scrollHeight,
      behavior: smooth ? "smooth" : "auto",
    });
  }
}
