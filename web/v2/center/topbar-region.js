/** Titan Frontend V2 — Top Bar (Canonical Final Reference + Phase 9 telemetry).
 * Presentation only: six cognitive modules with micro-sparklines.
 * Wired to StateStore / CognitiveStateEngine only — never fake backend execution.
 */

import { REGION_IDS } from "../layout/regions.js";
import { appendChildren, div, el, svgIcon } from "../components/dom-utils.js";
import { createTitanLogo } from "../components/titan-logo.js";
import {
  MODULE_STATE_LABELS,
  resolveModuleTelemetry,
  resolveDominantOsState,
} from "../core/cognitive-os-telemetry.js";

/** @typedef {import("../core/cognitive-os-telemetry.js").ModuleCognitiveState} ModuleCognitiveState */

const PILL_LABELS = Object.freeze({
  memory: "Mémoire",
  reflection: "Réflexion",
  presence: "Présence",
  tools: "Outils",
  mode: "Cerveau",
  runtime: "Runtime",
});

export class TopbarRegion {
  /**
   * @param {import("../layout/shell.js").Shell} shell
   * @param {import("../core/state-store.js").StateStore} store
   */
  constructor(shell, store) {
    this._shell = shell;
    this._store = store;
    /** @type {import("../core/cognitive-state-engine.js").CognitiveStateEngine | null} */
    this._brain = null;
    /** @type {ReturnType<typeof setInterval> | null} */
    this._clockTimer = null;
  }

  /**
   * @param {import("../core/cognitive-state-engine.js").CognitiveStateEngine} brain
   */
  setBrain(brain) {
    this._brain = brain;
    brain.onToolActivity(() => this._syncTelemetry());
    brain.onMemoryActivity(() => this._syncTelemetry());
    brain.onStateChanged(() => this._syncTelemetry());
    this._syncTelemetry();
  }

  mount() {
    const host = this._shell.get(REGION_IDS.topbar);
    if (!host) {
      return;
    }

    host.classList.remove("tdl-v2-topbar--v3", "tdl-v2-topbar--os");
    host.classList.add(
      "tdl-v2-topbar--telemetry",
      "tdl-v2-topbar--phase5",
      "tdl-v2-topbar--living",
      "tdl-v2-topbar--presence",
      "tdl-v2-topbar--cognitive-os",
      "tdl-v2-topbar--canonical",
    );
    host.dataset.phase = "10";
    host.dataset.living = "10";
    host.dataset.cognitiveOs = "9";
    host.dataset.canonical = "final";
    host.dataset.runtime = "idle";

    host.append(this._buildPills(), this._buildPresence(), this._buildActions());

    this._store.subscribe(() => this._syncTelemetry(), "connectionState");
    this._store.subscribe(() => this._syncTelemetry(), "presence");
    this._store.subscribe(() => this._syncTelemetry(), "recallActive");
    this._store.subscribe(() => this._syncTelemetry(), "activeToolCount");
    this._store.subscribe(() => this._syncTelemetry(), "pipelineThinking");
    this._store.subscribe(() => this._syncTelemetry(), "memoryStatusLine");
    this._store.subscribe(() => this._syncTelemetry(), "cognitiveState");
    this._store.subscribe(() => this._syncTelemetry(), "activeToolIds");
    this._store.subscribe(() => this._syncTelemetry(), "conversationActive");
    this._store.subscribe(() => this._syncTelemetry(), "conversationStage");
    this._store.subscribe(() => this._syncTelemetry(), "orchestrationDuration");
    this._store.subscribe((state) => this._syncContextToggle(state), "contextPanelOpen");

    this._startRuntimeClock();
    this._syncTelemetry();
  }

  destroy() {
    if (this._clockTimer !== null) {
      window.clearInterval(this._clockTimer);
      this._clockTimer = null;
    }
  }

  _buildPills() {
    const pills = div("tdl-v2-topbar__pills");
    pills.setAttribute("aria-label", "Télémétrie cognitive");

    pills.append(
      this._pill("memory", PILL_LABELS.memory, "En veille"),
      this._pill("reflection", PILL_LABELS.reflection, "En veille"),
      this._pill("presence", PILL_LABELS.presence, "En veille"),
      this._pill("tools", PILL_LABELS.tools, "0 Actifs"),
      this._pill("mode", PILL_LABELS.mode, "En veille"),
      this._pill("runtime", PILL_LABELS.runtime, "--:--:--"),
    );
    return pills;
  }

  /**
   * @param {string} id
   * @param {string} label
   * @param {string} value
   */
  _pill(id, label, value) {
    const pill = div(`tdl-v2-topbar__pill tdl-v2-topbar__pill--${id}`);
    pill.id = `tdl-v2-topbar-pill-${id}`;
    pill.dataset.status = "idle";
    pill.dataset.activity = "idle";
    pill.dataset.cognitive = "idle";
    pill.append(
      div("tdl-v2-topbar__pill-dot"),
      el("span", "tdl-v2-topbar__pill-label", { text: label }),
      el("span", "tdl-v2-topbar__pill-value", {
        id: `tdl-v2-topbar-pill-${id}-value`,
        text: value,
      }),
      this._spark(id),
    );
    return pill;
  }

  /** @param {string} id */
  _spark(id) {
    const spark = div("tdl-v2-topbar__pill-spark");
    spark.setAttribute("aria-hidden", "true");
    spark.dataset.spark = id;
    const paths = {
      memory: "M1 7 L4 5 L7 8 L10 3 L14 6 L18 4 L22 7",
      reflection: "M1 6 L5 6 L7 3 L10 9 L13 4 L16 7 L22 5",
      presence: "M1 8 L4 7 L8 8 L12 6 L16 8 L20 7 L22 8",
      tools: "M2 8 L2 4 M6 8 L6 2 M10 8 L10 5 M14 8 L14 3 M18 8 L18 6",
      mode: "M1 7 C4 2, 7 10, 11 5 S18 9, 22 4",
      runtime: "M2 8 H5 V4 H8 V8 H11 V3 H14 V8 H17 V5 H20 V8 H22",
    };
    spark.innerHTML = `
      <svg viewBox="0 0 24 12" preserveAspectRatio="none">
        <path d="${paths[id] || paths.memory}" fill="none" stroke="rgba(225,29,46,0.7)"
          stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    `;
    return spark;
  }

  _buildPresence() {
    const presence = div("tdl-v2-topbar__presence");
    presence.appendChild(
      el("span", "tdl-v2-topbar__presence-copy", {
        id: "tdl-v2-topbar-presence-copy",
        text: "Présent — en attente",
      }),
    );
    return presence;
  }

  _buildActions() {
    const actions = div("tdl-v2-topbar__actions");

    const brainMode = el("button", "tdl-v2-topbar__brain-mode", {
      type: "button",
      id: "tdl-v2-topbar-brain-mode",
      "aria-pressed": "true",
      title: "Mode Cerveau",
    });
    brainMode.append(
      svgIcon(
        "0 0 24 24",
        '<path d="M12 3c-1.8 0-3.2 1-4 2.4C7.2 4 5.8 3 4 4.2 2.5 5.2 2 7 2.6 8.6 1.6 9.4 1 10.8 1.2 12.2c.2 1.6 1.2 2.8 2.6 3.4-.2 1.6.4 3.2 1.8 4.1 1.6 1 3.6.7 4.8-.6.8 1.2 2.2 2 3.8 2 2.4 0 4.2-2 4-4.4 1.4-.6 2.4-2 2.4-3.6 0-1.6-.8-3-2.2-3.8C20.6 5.8 19 4.6 17.2 5c-.8-1.4-2.2-2-3.6-2H12z" stroke="currentColor" stroke-width="1.4" fill="none"/>',
        16,
      ),
      el("span", "tdl-v2-topbar__brain-mode-label", { text: "Cerveau" }),
    );

    const contextToggle = this._iconBtn(
      "Orchestrateur cognitif",
      svgIcon(
        "0 0 24 24",
        '<rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/><path d="M15 4v16" stroke="currentColor" stroke-width="1.5"/>',
      ),
    );
    contextToggle.id = "tdl-v2-topbar-context-toggle";
    contextToggle.addEventListener("click", () => {
      const mode = this._store.getState().viewportMode;
      if (mode === "tablet" || mode === "phone") {
        const open = !this._store.getState().orchestratorDrawerOpen;
        this._store.setState({ orchestratorDrawerOpen: open });
      } else {
        const open = !this._store.getState().contextPanelOpen;
        this._store.setState({ contextPanelOpen: open });
      }
    });

    const settings = this._iconBtn(
      "Paramètres",
      svgIcon(
        "0 0 24 24",
        '<circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.5"/><path d="M12 2v2M12 20v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M2 12h2M20 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
      ),
    );
    settings.addEventListener("click", () => {
      this._store.setState({ settingsOpen: true });
    });

    const profile = el("button", "tdl-v2-topbar__profile", {
      type: "button",
      "aria-label": "Profil — Nolan",
      title: "Nolan",
    });
    const avatar = createTitanLogo({
      size: "sm",
      className: "tdl-v2-topbar__profile-avatar",
    });
    const profileMeta = div("tdl-v2-topbar__profile-meta");
    profileMeta.append(
      el("span", "tdl-v2-topbar__profile-name", { text: "Nolan" }),
      el("span", "tdl-v2-topbar__profile-role", { text: "Opérateur" }),
    );
    profile.append(avatar, profileMeta);

    appendChildren(actions, brainMode, contextToggle, settings, profile);
    return actions;
  }

  _startRuntimeClock() {
    const tick = () => {
      const valueEl = document.getElementById("tdl-v2-topbar-pill-runtime-value");
      if (!valueEl) return;
      const state = this._store.getState();
      const modules = resolveModuleTelemetry(state);
      if (modules.runtime === "idle" || modules.runtime === "finished") {
        const now = new Date();
        const hh = String(now.getHours()).padStart(2, "0");
        const mm = String(now.getMinutes()).padStart(2, "0");
        const ss = String(now.getSeconds()).padStart(2, "0");
        valueEl.textContent = `${hh}:${mm}:${ss}`;
      }
    };
    tick();
    this._clockTimer = window.setInterval(tick, 1000);
  }

  /**
   * @param {ModuleCognitiveState} cognitive
   */
  _toLegacyActivity(cognitive) {
    switch (cognitive) {
      case "searching":
        return "searching";
      case "reading":
        return "remembering";
      case "writing":
        return "working";
      case "planning":
        return "planning";
      case "reasoning":
        return "thinking";
      case "waiting":
        return "thinking";
      case "finished":
        return "idle";
      default:
        return "idle";
    }
  }

  /**
   * @param {string} id
   * @param {ModuleCognitiveState} cognitive
   * @param {import("../core/state-store.js").AppState} state
   */
  _pillValue(id, cognitive, state) {
    if (id === "runtime" && (cognitive === "idle" || cognitive === "finished")) {
      const now = new Date();
      return [
        String(now.getHours()).padStart(2, "0"),
        String(now.getMinutes()).padStart(2, "0"),
        String(now.getSeconds()).padStart(2, "0"),
      ].join(":");
    }
    if (id === "tools") {
      const n = state.activeToolCount ?? 0;
      if (cognitive === "idle" || cognitive === "finished") {
        return n === 0 ? "0 Actifs" : n === 1 ? "1 Actif" : `${n} Actifs`;
      }
    }
    if (id === "mode" && (cognitive === "idle" || cognitive === "finished")) {
      return "Actif";
    }
    if (id === "memory" && cognitive === "reading" && state.memoryStatusLine) {
      return state.memoryStatusLine.slice(0, 22);
    }
    if (id === "reflection" && cognitive === "reasoning") {
      return "Thinking";
    }
    return MODULE_STATE_LABELS[cognitive] ?? "En veille";
  }

  /**
   * @param {ModuleCognitiveState} cognitive
   * @returns {"idle"|"active"|"live"}
   */
  _pillStatus(cognitive) {
    if (cognitive === "idle" || cognitive === "finished") return "idle";
    if (cognitive === "waiting") return "live";
    return "active";
  }

  _syncTelemetry() {
    const state = this._store.getState();
    const modules = resolveModuleTelemetry(state);
    const dominant = resolveDominantOsState(state);
    const connected =
      state.connectionState === "connected" || state.connectionState === "streaming";

    const host = this._shell.get(REGION_IDS.topbar);
    if (host) {
      host.dataset.runtime = this._toLegacyActivity(dominant);
      host.dataset.cognitive = dominant;
      host.dataset.cognitiveOs = "9";
      host.dataset.canonical = "final";
    }

    const root = document.getElementById("titan-v2-root");
    if (root) {
      root.dataset.runtime = this._toLegacyActivity(dominant);
      root.dataset.cognitive = dominant;
      root.dataset.living = "10";
      root.dataset.phase = "10";
      root.dataset.cognitiveOs = "9";
      root.dataset.canonical = "final";
    }

    /** @type {Array<{ id: string, key: keyof typeof modules }>} */
    const map = [
      { id: "memory", key: "memory" },
      { id: "reflection", key: "reflection" },
      { id: "presence", key: "presence" },
      { id: "tools", key: "tools" },
      { id: "mode", key: "brain" },
      { id: "runtime", key: "runtime" },
    ];

    for (const entry of map) {
      const cognitive = modules[entry.key];
      this._setPill(
        entry.id,
        this._pillStatus(cognitive),
        this._pillValue(entry.id, cognitive, state),
        this._toLegacyActivity(cognitive),
        cognitive,
      );
    }

    const copy = document.getElementById("tdl-v2-topbar-presence-copy");
    if (copy) {
      if (!connected) {
        copy.textContent = "Connexion au Brain…";
      } else {
        copy.textContent = this._presenceCopy(dominant);
      }
    }
  }

  /** @param {ModuleCognitiveState} dominant */
  _presenceCopy(dominant) {
    switch (dominant) {
      case "planning":
        return "Planification en cours";
      case "reasoning":
        return "Raisonnement en cours";
      case "searching":
        return "Recherche web";
      case "writing":
        return "Synthèse en cours";
      case "reading":
        return "Lecture mémoire";
      case "waiting":
        return "En attente";
      case "finished":
        return "Cycle terminé";
      default:
        return "Présent — intelligence en veille";
    }
  }

  /**
   * @param {string} id
   * @param {string} status
   * @param {string} value
   * @param {string} [activity]
   * @param {ModuleCognitiveState} [cognitive]
   */
  _setPill(id, status, value, activity = "idle", cognitive = "idle") {
    const pill = document.getElementById(`tdl-v2-topbar-pill-${id}`);
    const valueEl = document.getElementById(`tdl-v2-topbar-pill-${id}-value`);
    if (pill) {
      pill.dataset.status = status;
      pill.dataset.activity = activity;
      pill.dataset.cognitive = cognitive;
    }
    if (valueEl) valueEl.textContent = value;
  }

  /** @param {import("../core/state-store.js").AppState} [state] */
  _syncContextToggle(state = this._store.getState()) {
    const toggle = document.getElementById("tdl-v2-topbar-context-toggle");
    if (!toggle) return;
    const mode = state.viewportMode;
    const pressed =
      mode === "tablet" || mode === "phone"
        ? Boolean(state.orchestratorDrawerOpen)
        : Boolean(state.contextPanelOpen);
    toggle.setAttribute("aria-pressed", String(pressed));
    toggle.classList.toggle("tdl-v2-topbar__icon-btn--active", pressed);
  }

  /** @param {string} label @param {SVGElement} icon */
  _iconBtn(label, icon) {
    const btn = el("button", "tdl-v2-topbar__icon-btn", {
      type: "button",
      "aria-label": label,
      title: label,
    });
    btn.appendChild(icon);
    return btn;
  }
}
