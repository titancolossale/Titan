/** Titan Frontend V2 — Composer region (premium command console). Sprint 2.7 / 2.9. */

import { appendChildren, div, el, svgIcon } from "../components/dom-utils.js";
import { REGION_IDS } from "../layout/regions.js";

export class ComposerRegion {
  /**
   * @param {import("../layout/shell.js").Shell} shell
   */
  constructor(shell) {
    this._shell = shell;
    /** @type {import("../core/cognitive-state-engine.js").CognitiveStateEngine | null} */
    this._brain = null;
    /** @type {import("../neural/stage.js").NeuralStage | null} */
    this._neural = null;
    /** @type {HTMLTextAreaElement | null} */
    this._input = null;
    this._focusState = false;
    /** @type {boolean} */
    this._focusBound = false;
  }

  /**
   * @param {import("../core/cognitive-state-engine.js").CognitiveStateEngine} brain
   */
  setBrain(brain) {
    this._brain = brain;
    this._bindCognitiveFocus();
  }

  /**
   * @param {import("../neural/stage.js").NeuralStage} neural
   */
  setNeuralStage(neural) {
    this._neural = neural;
  }

  mount() {
    const host = this._shell.get(REGION_IDS.dockComposer);
    if (!host) {
      return;
    }

    const composer = div("tdl-v2-composer tdl-v2-composer--reference tdl-v2-composer--console");
    composer.id = "tdl-v2-chat-composer";

    const mic = el("button", "tdl-v2-voice-mic tdl-v2-voice-mic--idle", {
      type: "button",
      id: "tdl-v2-voice-mic",
      "aria-label": "Parler à Titan",
      "aria-pressed": "false",
      title: "Maintenir pour parler",
    });
    const micRing = div("tdl-v2-voice-mic__ring");
    micRing.setAttribute("aria-hidden", "true");
    mic.append(
      micRing,
      svgIcon(
        "0 0 24 24",
        '<path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z" stroke="currentColor" stroke-width="1.5"/><path d="M19 11a7 7 0 0 1-14 0M12 18v3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
        18,
      ),
    );

    const attach = el("button", "tdl-v2-composer-attach", {
      type: "button",
      id: "tdl-v2-composer-attach",
      "aria-label": "Joindre un fichier",
      title: "Joindre",
    });
    attach.appendChild(
      svgIcon(
        "0 0 24 24",
        '<path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
        16,
      ),
    );

    const input = el("textarea", "tdl-v2-composer__input", {
      id: "tdl-v2-chat-input",
      rows: "1",
      placeholder: "Message à Titan…",
      "aria-label": "Message à Titan",
    });

    const actions = div("tdl-v2-composer__actions");
    const stopBtn = el("button", "tdl-v2-btn tdl-v2-btn--ghost tdl-v2-composer__stop", {
      type: "button",
      id: "tdl-v2-stop-generation",
      text: "Arrêter",
      hidden: "",
    });
    const sendBtn = el("button", "tdl-v2-btn tdl-v2-btn--primary tdl-v2-composer__send", {
      type: "button",
      id: "tdl-v2-send-chat",
      "aria-label": "Envoyer",
      title: "Envoyer",
    });
    sendBtn.append(
      el("span", "tdl-v2-composer__send-label", { text: "Envoyer" }),
      svgIcon(
        "0 0 24 24",
        '<path d="M5 12h12M13 6l6 6-6 6" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/><path d="M5 12h1" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>',
        16,
      ),
    );

    actions.append(stopBtn, sendBtn);
    appendChildren(composer, mic, attach, input, actions);
    host.appendChild(composer);

    this._input = /** @type {HTMLTextAreaElement} */ (input);
  }

  _bindCognitiveFocus() {
    const input = this._input ?? /** @type {HTMLTextAreaElement | null} */ (
      document.getElementById("tdl-v2-chat-input")
    );
    if (!input || !this._brain) return;
    // Idempotent — neural focus listeners must not stack across re-entry.
    if (this._focusBound) return;
    this._focusBound = true;

    input.addEventListener("focus", () => {
      this._focusState = true;
      this._neural?.notifyInteractive?.(320);
      this._brain?.setState("listening", { source: "composer" });
    });

    input.addEventListener("blur", () => {
      this._focusState = false;
      const current = this._brain?.getState().id;
      if (current === "listening" && !this._brain?.thinking) {
        this._brain?.setState("idle", { source: "composer" });
      }
    });

    input.addEventListener("input", () => {
      this._neural?.notifyInteractive?.(280);
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        this._neural?.notifyInteractive?.(600);
      }
    });

    // Neural pulse only — ConversationManager owns the actual send.
    document.getElementById("tdl-v2-send-chat")?.addEventListener("click", () => {
      this._neural?.notifyInteractive?.(800);
    });

    this._brain.getPipelineStore().subscribe((snap) => {
      const composer = document.getElementById("tdl-v2-chat-composer");
      if (composer) {
        composer.dataset.thinking = String(snap.thinking);
      }
      // Do not fight ConversationManager stop-button visibility during chat pending.
      if (this._storeChatPending?.()) return;
      const stopBtn = document.getElementById("tdl-v2-stop-generation");
      if (stopBtn && !snap.thinking) {
        /* leave ConversationManager in control while idle */
      }
    });
  }

  /** Optional hook — overridden when store is wired via setBrain path. */
  _storeChatPending() {
    return false;
  }
}
