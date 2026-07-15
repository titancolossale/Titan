/** Titan Frontend V2 — Floating Cognitive Workspaces (Phase 9 Cognitive OS).
 * Live cognitive surfaces — Memory · Obsidian · Browser · Cognitive · Presence.
 * Reuses CognitiveStateEngine / MemoryActivityEngine / tool activity / StateStore only.
 * Phase 7–8 living cues preserved. Phase 9: honest OS telemetry — no fake execution.
 */

import { div, el } from "../components/dom-utils.js";
import { REGION_IDS } from "../layout/regions.js";
import { getMemoryDefinition } from "../memory/memory-registry.js";
import {
  formatAttention,
  formatConfidence,
  formatPresenceSurface,
  formatReasoningDepth,
  resolveMemoryModuleState,
  resolveToolsModuleState,
} from "../core/cognitive-os-telemetry.js";

/** Presentation vault label — matches product Obsidian policy (Titan AI). */
const OBSIDIAN_VAULT_LABEL = "Titan AI";

/** @type {Record<string, { title: string, description: string, ui: string }>} */
const COGNITIVE_UI = Object.freeze({
  idle: {
    title: "Idle",
    description: "Présent — en attente",
    ui: "idle",
  },
  sleep: {
    title: "Idle",
    description: "Veille calme",
    ui: "idle",
  },
  listening: {
    title: "Listening",
    description: "À l'écoute",
    ui: "listening",
  },
  thinking: {
    title: "Thinking",
    description: "Réflexion en cours",
    ui: "thinking",
  },
  reasoning: {
    title: "Thinking",
    description: "Raisonnement actif",
    ui: "thinking",
  },
  memory_recall: {
    title: "Learning",
    description: "Rappel mémoire",
    ui: "learning",
  },
  planning: {
    title: "Planning",
    description: "Planification",
    ui: "planning",
  },
  writing: {
    title: "Executing",
    description: "Synthèse en cours",
    ui: "executing",
  },
  tool_execution: {
    title: "Executing",
    description: "Exécution d'outil",
    ui: "executing",
  },
  browser_research: {
    title: "Executing",
    description: "Recherche web",
    ui: "executing",
  },
  obsidian: {
    title: "Executing",
    description: "Consultation vault",
    ui: "executing",
  },
  calendar: {
    title: "Executing",
    description: "Agenda",
    ui: "executing",
  },
  trading: {
    title: "Executing",
    description: "Analyse marchés",
    ui: "executing",
  },
  voice: {
    title: "Listening",
    description: "Voix active",
    ui: "listening",
  },
  error: {
    title: "Error",
    description: "Anomalie détectée",
    ui: "error",
  },
});

/**
 * @param {string} value
 * @returns {string}
 */
function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/**
 * @param {number} ageMs
 * @returns {string}
 */
function formatRelativeAge(ageMs) {
  const sec = Math.max(0, Math.floor(ageMs / 1000));
  if (sec < 45) return "à l'instant";
  const min = Math.floor(sec / 60);
  if (min < 60) return `il y a ${min} min`;
  const hours = Math.floor(min / 60);
  if (hours < 24) return `il y a ${hours} h`;
  const days = Math.floor(hours / 24);
  return `il y a ${days} j`;
}

/**
 * @param {import("../memory/memory-activity-engine.js").MemoryRecord} memory
 * @returns {{ icon: string, title: string, meta: string }}
 */
function presentMemoryRow(memory) {
  const def = getMemoryDefinition(memory.type || memory.source || "long_term");
  const title =
    typeof memory.title === "string" && memory.title.trim()
      ? memory.title.trim().slice(0, 28)
      : def.title;
  const age =
    typeof memory.age === "number"
      ? memory.age
      : performance.now() - (memory.createdAt || performance.now());
  return {
    icon: def.icon || "◈",
    title,
    meta: `Consulté ${formatRelativeAge(age)}`,
  };
}

export class StatusRegion {
  /**
   * @param {import("../layout/shell.js").Shell} shell
   * @param {import("../core/state-store.js").StateStore} [store]
   */
  constructor(shell, store = null) {
    this._shell = shell;
    this._store = store;
    /** @type {import("../core/cognitive-state-engine.js").CognitiveStateEngine | null} */
    this._brain = null;
    /** @type {ReturnType<typeof setInterval> | null} */
    this._clockTimer = null;
    /** @type {ReturnType<typeof setInterval> | null} */
    this._fpsTimer = null;
  }

  /**
   * @param {import("../core/cognitive-state-engine.js").CognitiveStateEngine} brain
   */
  setBrain(brain) {
    this._brain = brain;
    brain.onStateChanged((snapshot) => {
      this._updateCognitiveCard(snapshot.label, snapshot.id);
      this._updatePresenceCard(snapshot);
      this._updateStrip();
    });
    brain.onToolActivity(() => {
      this._updateMemoryUi();
      this._updateToolUi();
      this._updateStrip();
    });
    brain.onMemoryActivity(() => {
      this._updateMemoryUi();
      this._updateToolUi();
      this._updateStrip();
    });
    brain.onConversationActivity(() => {
      this._updateConversationUi();
      this._updateStrip();
    });
    this._updateCognitiveCard(brain.getState().label, brain.getState().id);
    this._updatePresenceCard(brain.getState());
    this._updateToolUi();
    this._updateMemoryUi();
    this._updateStrip();

    this._store?.subscribe(() => this._updateToolUi(), "toolStatusLine");
    this._store?.subscribe(() => this._updateMemoryUi(), "memoryStatusLine");
    this._store?.subscribe(() => this._updateConversationUi(), "conversationStatusLine");
    this._store?.subscribe(() => this._updatePresenceCard(brain.getState()), "presenceLevel");
    this._store?.subscribe(() => this._updateCognitiveCard(
      brain.getState().label,
      brain.getState().id,
    ), "connectionState");
  }

  mount() {
    this._mountStatusCards();
    this._mountStatusLines();
    this._mountTelemetry();
    this._startClock();
    this._startFpsCounter();
  }

  _mountStatusCards() {
    const cards = this._shell.get(REGION_IDS.dockStatusCards);
    if (!cards) {
      return;
    }

    cards.classList.add(
      "tdl-v2-dock-status-cards--float",
      "tdl-v2-dock-status-cards--phase5",
      "tdl-v2-workspace-dock",
      "tdl-v2-workspace-dock--living",
      "tdl-v2-workspace-dock--presence",
      "tdl-v2-workspace-dock--cognitive-os",
    );
    cards.dataset.phase = "10";
    cards.dataset.living = "10";
    cards.dataset.cognitiveOs = "9";
    cards.dataset.canonical = "final";
    cards.dataset.role = "workspace-dock";
    cards.setAttribute("aria-label", "Espaces de travail cognitifs");
    cards.replaceChildren(
      this._memoryCard(),
      this._obsidianCard(),
      this._browserCard(),
      this._cognitiveCard(),
      this._presenceCard(),
    );
  }

  /**
   * Shared workspace chrome: quiet title · indicator · collapse.
   * @param {string} title
   * @param {string} id
   * @param {string} kind
   * @param {{ width?: string, live?: boolean }} [options]
   */
  _workspaceShell(title, id, kind, options = {}) {
    const card = div("tdl-v2-status-card tdl-v2-float-card tdl-v2-workspace-card");
    card.id = id;
    card.dataset.kind = kind;
    card.dataset.workspace = kind;
    card.dataset.phase = "5.4";
    if (options.width) card.dataset.width = options.width;

    const header = div("tdl-v2-status-card__header tdl-v2-workspace-card__header");
    const titleRow = el("span", "tdl-v2-status-card__title");
    const indicator = div(
      `tdl-v2-status-card__indicator ${
        options.live
          ? "tdl-v2-status-card__indicator--live"
          : "tdl-v2-status-card__indicator--idle"
      }`,
    );
    indicator.setAttribute("aria-hidden", "true");
    indicator.dataset.role = "indicator";
    titleRow.append(indicator, document.createTextNode(title));

    const close = el("button", "tdl-v2-float-card__close", {
      type: "button",
      "aria-label": `Masquer ${title}`,
      title: "Masquer",
      text: "×",
    });
    close.addEventListener("click", () => {
      card.dataset.collapsed = card.dataset.collapsed === "true" ? "false" : "true";
    });

    header.append(titleRow, close);
    card.append(header);
    return card;
  }

  _memoryCard() {
    const card = this._workspaceShell("Mémoire Récente", "card-recent-memory", "memory", {
      width: "wide",
    });
    card.dataset.cognitiveOs = "9";
    card.dataset.canonical = "final";
    const body = div("tdl-v2-status-card__body tdl-v2-workspace-card__body");
    body.id = "card-recent-memory-body";
    body.dataset.role = "memory-list";
    body.innerHTML = this._idleMemoryHtml();

    const metrics = div("tdl-v2-workspace-metrics");
    metrics.id = "card-recent-memory-metrics";
    metrics.innerHTML = `
      <span class="tdl-v2-workspace-metric" data-metric="confidence">
        <span class="tdl-v2-workspace-metric__key">Confiance</span>
        <span class="tdl-v2-workspace-metric__value" id="card-memory-confidence">—</span>
      </span>
      <span class="tdl-v2-workspace-metric" data-metric="scan">
        <span class="tdl-v2-workspace-metric__key">Scan</span>
        <span class="tdl-v2-workspace-metric__value" id="card-memory-scan">Idle</span>
      </span>
    `;

    const status = el("span", "tdl-v2-float-card__status", {
      id: "card-recent-memory-status",
      text: "veille",
    });
    const scan = div("tdl-v2-workspace-card__scan");
    scan.setAttribute("aria-hidden", "true");

    card.append(body, metrics, status, scan);
    return card;
  }

  _obsidianCard() {
    const card = this._workspaceShell("Obsidian Vault", "card-obsidian", "obsidian", {
      width: "mid",
    });
    card.dataset.cognitiveOs = "9";
    card.dataset.canonical = "final";

    const mark = div("tdl-v2-workspace-obsidian__mark");
    mark.setAttribute("aria-hidden", "true");
    mark.innerHTML = `
      <svg viewBox="0 0 24 24" class="tdl-v2-workspace-obsidian__glyph">
        <path d="M12 2.5 L19.5 7.2 V16.8 L12 21.5 L4.5 16.8 V7.2 Z"
          fill="none" stroke="currentColor" stroke-width="1.1"/>
        <path d="M12 7.2 V16.8 M8.2 9.4 L12 12.1 L15.8 9.4"
          fill="none" stroke="currentColor" stroke-width="1"/>
      </svg>
    `;

    const body = div("tdl-v2-status-card__body tdl-v2-workspace-card__body");
    body.id = "card-obsidian-body";
    body.innerHTML = `
      <div class="tdl-v2-workspace-obsidian">
        <p class="tdl-v2-workspace-line tdl-v2-workspace-line--primary" id="card-obsidian-vault">
          Vault : ${OBSIDIAN_VAULT_LABEL}
        </p>
        <p class="tdl-v2-workspace-line tdl-v2-workspace-line--meta" id="card-obsidian-meta">
          Vault connecté — en veille
        </p>
        <p class="tdl-v2-workspace-line tdl-v2-workspace-line--quiet" id="card-obsidian-sync">
          Dernière sync — —
        </p>
        <p class="tdl-v2-workspace-line tdl-v2-workspace-line--quiet" id="card-obsidian-activity">
          Notes — aucune activité
        </p>
        <p class="tdl-v2-workspace-line tdl-v2-workspace-line--quiet" id="card-obsidian-counts" hidden></p>
      </div>
    `;

    const status = el("span", "tdl-v2-float-card__status", {
      id: "card-obsidian-status",
      text: "veille",
    });

    card.append(mark, body, status);
    return card;
  }

  _browserCard() {
    const card = this._workspaceShell("Browser", "card-browser", "browser", {
      width: "mid",
    });
    card.dataset.cognitiveOs = "9";
    card.dataset.canonical = "final";

    const preview = div("tdl-v2-workspace-browser__preview");
    preview.setAttribute("aria-hidden", "true");
    preview.innerHTML = `
      <span class="tdl-v2-workspace-browser__bar"></span>
      <span class="tdl-v2-workspace-browser__pane"></span>
    `;

    const body = div("tdl-v2-status-card__body tdl-v2-workspace-card__body");
    body.id = "card-browser-body";
    body.innerHTML = `
      <p class="tdl-v2-workspace-line tdl-v2-workspace-line--primary" id="card-browser-state">
        Navigation en réserve
      </p>
      <p class="tdl-v2-workspace-line tdl-v2-workspace-line--meta" id="card-browser-meta">
        Aucune recherche active
      </p>
      <p class="tdl-v2-workspace-line tdl-v2-workspace-line--quiet" id="card-browser-nav">
        Navigation — idle
      </p>
      <p class="tdl-v2-workspace-line tdl-v2-workspace-line--quiet" id="card-browser-network">
        Réseau — —
      </p>
      <p class="tdl-v2-workspace-line tdl-v2-workspace-line--quiet" id="card-browser-tabs" hidden></p>
    `;

    const status = el("span", "tdl-v2-float-card__status", {
      id: "card-browser-status",
      text: "veille",
    });

    card.append(preview, body, status);
    return card;
  }

  _cognitiveCard() {
    const card = this._workspaceShell("État Cognitif", "card-cognitive", "cognitive", {
      width: "mid",
    });
    card.dataset.cognitiveOs = "9";
    card.dataset.canonical = "final";

    const viz = div("tdl-v2-workspace-cognitive__viz");
    viz.setAttribute("aria-hidden", "true");
    viz.innerHTML = `
      <span class="tdl-v2-workspace-cognitive__pulse"></span>
      <span class="tdl-v2-workspace-cognitive__pulse"></span>
      <span class="tdl-v2-workspace-cognitive__pulse"></span>
    `;

    const body = div("tdl-v2-status-card__body tdl-v2-workspace-card__body");
    body.id = "card-cognitive-body";
    body.innerHTML = `
      <p class="tdl-v2-workspace-line tdl-v2-workspace-line--primary" id="card-cognitive-title">
        Idle
      </p>
      <p class="tdl-v2-workspace-line tdl-v2-workspace-line--meta" id="card-cognitive-desc">
        Présent — en attente
      </p>
      <p class="tdl-v2-workspace-line tdl-v2-workspace-line--quiet" id="card-cognitive-attention">
        Attention — Stable
      </p>
      <p class="tdl-v2-workspace-line tdl-v2-workspace-line--quiet" id="card-cognitive-depth">
        Profondeur — Calme
      </p>
      <p class="tdl-v2-workspace-line tdl-v2-workspace-line--quiet" id="card-cognitive-confidence">
        Confiance — —
      </p>
    `;

    const status = el("span", "tdl-v2-float-card__status", {
      id: "card-cognitive-status",
      text: "présent",
    });

    card.append(viz, body, status);
    return card;
  }

  _presenceCard() {
    const card = this._workspaceShell("Présence", "tdl-v2-card-presence", "presence", {
      width: "presence",
      live: true,
    });
    card.dataset.cognitiveOs = "9";
    card.dataset.canonical = "final";

    const layout = div("tdl-v2-workspace-presence");
    const ring = div("tdl-v2-presence-ring tdl-v2-workspace-presence__ring");
    ring.setAttribute("aria-hidden", "true");
    ring.innerHTML = `
      <svg viewBox="0 0 44 44">
        <circle class="tdl-v2-presence-ring__track" cx="22" cy="22" r="18"></circle>
        <circle class="tdl-v2-presence-ring__fill" id="tdl-v2-presence-ring-fill" cx="22" cy="22" r="18"
          stroke-dasharray="113.1" stroke-dashoffset="65.6"></circle>
      </svg>
      <span class="tdl-v2-presence-ring__value" id="tdl-v2-presence-ring-value">42%</span>
      <span class="tdl-v2-workspace-presence__breath" aria-hidden="true"></span>
    `;

    const body = div("tdl-v2-status-card__body tdl-v2-workspace-card__body");
    body.id = "tdl-v2-card-presence-body";
    body.innerHTML = `
      <strong class="tdl-v2-workspace-line tdl-v2-workspace-line--primary" id="tdl-v2-presence-card-value">
        Présent — calme
      </strong>
      <p class="tdl-v2-workspace-line tdl-v2-workspace-line--meta" id="tdl-v2-presence-activity">
        Activité faible
      </p>
      <p class="tdl-v2-workspace-line tdl-v2-workspace-line--quiet" id="tdl-v2-presence-engagement">
        Engagement — Calme
      </p>
      <p class="tdl-v2-workspace-line tdl-v2-workspace-line--quiet" id="tdl-v2-presence-focus">
        Focus — Stable
      </p>
      <p class="tdl-v2-workspace-line tdl-v2-workspace-line--quiet" id="tdl-v2-presence-availability">
        Disponibilité — Disponible
      </p>
      <p class="tdl-v2-workspace-line tdl-v2-workspace-line--quiet" id="tdl-v2-presence-awaiting">
        En attente de Nolan
      </p>
    `;

    const status = el("span", "tdl-v2-float-card__status", {
      id: "tdl-v2-card-presence-status",
      text: "présent",
    });

    layout.append(body, ring);
    card.append(layout, status);
    return card;
  }

  /** @returns {string} */
  _idleMemoryHtml() {
    return `
      <div class="tdl-v2-workspace-memory tdl-v2-workspace-memory--idle">
        <p class="tdl-v2-workspace-line tdl-v2-workspace-line--primary">Mémoire en veille</p>
        <p class="tdl-v2-workspace-line tdl-v2-workspace-line--meta">Aucune note récente</p>
      </div>
    `;
  }

  _mountStatusLines() {
    const lines = this._shell.get(REGION_IDS.dockStatusLines);
    if (!lines) {
      return;
    }

    lines.replaceChildren(
      el("p", "tdl-v2-status-line tdl-v2-status-line--tools", {
        id: "tdl-v2-tool-status-line",
        text: "Outils — aucune activité",
      }),
      el("p", "tdl-v2-status-line tdl-v2-status-line--memory", {
        id: "tdl-v2-memory-status-line",
        text: "Mémoire — en veille",
      }),
      el("p", "tdl-v2-status-line tdl-v2-status-line--conversation", {
        id: "tdl-v2-conversation-status-line",
        text: "Conversation — en veille",
      }),
    );
  }

  _mountTelemetry() {
    const telemetry = this._shell.get(REGION_IDS.dockTelemetry);
    if (!telemetry) {
      return;
    }

    telemetry.classList.add("tdl-v2-dock-telemetry--system", "tdl-v2-dock-telemetry--canonical");
    telemetry.dataset.canonical = "final";
    telemetry.innerHTML = `
      <div class="tdl-v2-telemetry__group tdl-v2-telemetry__group--primary">
        <span class="tdl-v2-telemetry__item">
          FPS <span class="tdl-v2-telemetry__value" id="tdl-v2-telemetry-fps" data-fallback="true">—</span>
        </span>
        <span class="tdl-v2-telemetry__item">
          BRAIN <span class="tdl-v2-telemetry__value" id="tdl-v2-telemetry-brain">IDLE</span>
        </span>
        <span class="tdl-v2-telemetry__item">
          MEMORY <span class="tdl-v2-telemetry__value" id="tdl-v2-telemetry-memory">VEILLE</span>
        </span>
        <span class="tdl-v2-telemetry__item">
          TOOLS <span class="tdl-v2-telemetry__value" id="tdl-v2-telemetry-tools">0</span>
        </span>
        <span class="tdl-v2-telemetry__item">
          RUNTIME <span class="tdl-v2-telemetry__value tdl-v2-telemetry__value--clock" id="tdl-v2-telemetry-clock">--:--:--</span>
        </span>
      </div>
      <span class="tdl-v2-telemetry__item" hidden>
        Reflection <span class="tdl-v2-telemetry__value" id="tdl-v2-telemetry-reflection">—</span>
      </span>
      <span class="tdl-v2-telemetry__status" id="tdl-v2-telemetry-status" hidden>Titan en ligne</span>
      <span id="tdl-v2-telemetry-status-dot" hidden></span>
      <span id="tdl-v2-telemetry-runtime" hidden>Cognitive V1</span>
      <span id="tdl-v2-telemetry-latency" hidden>—</span>
    `;

    this._store?.subscribe((state) => this._updateStatusTelemetry(state), "connectionState");
    this._store?.subscribe(() => this._updateStrip(), "presence");
    this._store?.subscribe(() => this._updateStrip(), "orchestrationDuration");
    this._updateStatusTelemetry();
    this._updateStrip();
  }

  /** @param {import("../core/state-store.js").AppState} [state] */
  _updateStatusTelemetry(state = this._store?.getState()) {
    const statusEl = document.getElementById("tdl-v2-telemetry-status");
    const connection = state?.connectionState ?? "connecting";
    const online = connection === "connected" || connection === "streaming";
    if (statusEl) {
      statusEl.textContent = online
        ? "Titan en ligne"
        : connection === "connecting"
          ? "Titan connexion…"
          : "Titan hors ligne";
      statusEl.classList.toggle("tdl-v2-telemetry__value--online", online);
    }
  }

  _updateStrip() {
    const state = this._store?.getState();
    const brainEl = document.getElementById("tdl-v2-telemetry-brain");
    const memEl = document.getElementById("tdl-v2-telemetry-memory");
    const toolsEl = document.getElementById("tdl-v2-telemetry-tools");
    const reflEl = document.getElementById("tdl-v2-telemetry-reflection");

    const cognitive = state?.cognitiveState ?? "idle";
    const connected =
      state?.connectionState === "connected" || state?.connectionState === "streaming";
    let brainLabel = (cognitive || "idle").toUpperCase();
    if (brainLabel === "ERROR" && (!connected || !state?.lastError)) {
      brainLabel = "IDLE";
    }
    if (brainEl) {
      brainEl.textContent = brainLabel;
    }
    if (memEl) {
      memEl.textContent = state?.recallActive
        ? `${state.activeMemoryCount || 1} actifs`
        : "veille";
    }
    const active = this._brain?.getActiveTools() ?? [];
    if (toolsEl) {
      toolsEl.textContent = String(active.length);
    }
    if (reflEl) {
      reflEl.textContent = state?.pipelineThinking || state?.presence === "thinking"
        ? "profonde"
        : "—";
      reflEl.dataset.fallback = String(!(state?.pipelineThinking || state?.presence === "thinking"));
    }
  }

  _startClock() {
    const clockEl = document.getElementById("tdl-v2-telemetry-clock");
    if (!clockEl) {
      return;
    }
    const tick = () => {
      clockEl.textContent = new Date().toLocaleTimeString("fr-FR", { hour12: false });
    };
    tick();
    this._clockTimer = window.setInterval(tick, 1000);
  }

  _startFpsCounter() {
    const fpsEl = document.getElementById("tdl-v2-telemetry-fps");
    if (!fpsEl) return;

    const tick = () => {
      const engine = this._brain?._neural?.getEngine?.();
      const fps = engine?.getFps?.() ?? 0;
      if (fps > 0) {
        fpsEl.textContent = String(Math.round(fps));
        fpsEl.dataset.fallback = "false";
      } else {
        fpsEl.textContent = "—";
        fpsEl.dataset.fallback = "true";
      }
    };

    tick();
    this._fpsTimer = window.setInterval(tick, 1000);
  }

  destroy() {
    if (this._clockTimer !== null) {
      window.clearInterval(this._clockTimer);
      this._clockTimer = null;
    }
    if (this._fpsTimer !== null) {
      window.clearInterval(this._fpsTimer);
      this._fpsTimer = null;
    }
  }

  /**
   * @param {import("../core/cognitive-state-engine.js").CognitiveStateSnapshot} snapshot
   */
  _updatePresenceCard(snapshot) {
    const state = this._store?.getState();
    let id = snapshot?.id ?? "idle";
    const connected =
      state?.connectionState === "connected" || state?.connectionState === "streaming";
    // Connection-only faults must not masquerade as cognitive alert presence.
    if (id === "error" && (!connected || !state?.lastError)) {
      id = "idle";
    }
    const idle = id === "idle" || id === "sleep";
    let level = typeof state?.presenceLevel === "number" ? state.presenceLevel : 42;
    if (idle) {
      level = Math.min(level, 48);
    }
    const circumference = 113.1;
    const offset = circumference * (1 - Math.min(100, Math.max(0, level)) / 100);

    const fill = document.getElementById("tdl-v2-presence-ring-fill");
    if (fill) {
      fill.setAttribute("stroke-dashoffset", String(offset.toFixed(1)));
    }

    const valueEl = document.getElementById("tdl-v2-presence-ring-value");
    if (valueEl) {
      valueEl.textContent = `${Math.round(level)}%`;
    }

    const labelEl = document.getElementById("tdl-v2-presence-card-value");
    const activityEl = document.getElementById("tdl-v2-presence-activity");
    const awaitingEl = document.getElementById("tdl-v2-presence-awaiting");
    const statusEl = document.getElementById("tdl-v2-card-presence-status");
    const card = document.getElementById("tdl-v2-card-presence");

    if (labelEl) {
      if (idle) labelEl.textContent = "Présent — calme";
      else if (id === "listening" || id === "voice") labelEl.textContent = "Présent — attentif";
      else if (id === "error") labelEl.textContent = "Présent — alerte";
      else labelEl.textContent = "Présent — engagé";
    }
    if (activityEl) {
      if (idle) activityEl.textContent = "Activité faible";
      else if (level >= 80) activityEl.textContent = "Activité élevée";
      else activityEl.textContent = "Activité modérée";
    }
    if (awaitingEl) {
      awaitingEl.textContent = idle ? "En attente de Nolan" : "À tes côtés";
    }
    if (statusEl) {
      statusEl.textContent = idle ? "présent" : "actif";
    }

    const surface = formatPresenceSurface({
      ...(state ?? {}),
      presence: idle ? "idle" : state?.presence,
      cognitiveState: idle ? "idle" : state?.cognitiveState,
      connectionState: idle && !state?.lastError ? "connected" : state?.connectionState,
      presenceLevel: level,
    });
    const engagementEl = document.getElementById("tdl-v2-presence-engagement");
    const focusEl = document.getElementById("tdl-v2-presence-focus");
    const availabilityEl = document.getElementById("tdl-v2-presence-availability");
    if (engagementEl) engagementEl.textContent = `Engagement — ${surface.engagement}`;
    if (focusEl) focusEl.textContent = `Focus — ${surface.focus}`;
    if (availabilityEl) availabilityEl.textContent = `Disponibilité — ${surface.availability}`;

    if (card) {
      card.dataset.presence = idle ? "calm" : "engaged";
      card.dataset.cognitiveOs = "9";
      this._setCardLive(card, !idle, idle ? "idle" : "engaged");
    }
  }

  /** @param {string} label @param {string} id */
  _updateCognitiveCard(label, id) {
    const state = this._store?.getState();
    const connected =
      state?.connectionState === "connected" || state?.connectionState === "streaming";
    let resolvedId = id;
    if (resolvedId === "error" && (!connected || !state?.lastError)) {
      resolvedId = "idle";
    }
    const offline = false;
    const ui = COGNITIVE_UI[resolvedId] ?? {
      title: label || "Idle",
      description: label || "Présent — en attente",
      ui: "idle",
    };
    // Only escalate to Offline when a real error payload exists.
    const showOffline =
      state?.connectionState === "disconnected" && Boolean(state?.lastError);
    const view = showOffline
      ? { title: "Offline", description: "Hors ligne", ui: "offline" }
      : ui;

    const titleEl = document.getElementById("card-cognitive-title");
    const descEl = document.getElementById("card-cognitive-desc");
    const body = document.getElementById("card-cognitive-body");
    const status = document.getElementById("card-cognitive-status");
    const card = document.getElementById("card-cognitive");

    if (titleEl) titleEl.textContent = view.title;
    if (descEl) descEl.textContent = view.description;
    if (body && !titleEl) {
      body.textContent = view.description;
    }
    if (status) {
      status.textContent =
        view.ui === "idle" || view.ui === "offline" ? "présent" : "actif";
    }
    if (card) {
      card.dataset.cognitiveState = resolvedId;
      card.dataset.cognitiveUi = view.ui;
      card.dataset.cognitiveOs = "9";
      const activity =
        view.ui === "thinking" || view.ui === "planning"
          ? view.ui
          : view.ui === "executing" || view.ui === "learning"
            ? "working"
            : view.ui === "listening"
              ? "thinking"
              : "idle";
      this._setCardLive(card, view.ui !== "idle" && view.ui !== "offline", activity);
    }

    const attentionEl = document.getElementById("card-cognitive-attention");
    const depthEl = document.getElementById("card-cognitive-depth");
    const confEl = document.getElementById("card-cognitive-confidence");
    const surfaceState = {
      ...(state ?? {}),
      connectionState: showOffline ? state?.connectionState : "connected",
      cognitiveState: resolvedId,
    };
    if (attentionEl) attentionEl.textContent = `Attention — ${formatAttention(surfaceState)}`;
    if (depthEl) depthEl.textContent = `Profondeur — ${formatReasoningDepth(surfaceState)}`;
    if (confEl) confEl.textContent = `Confiance — ${formatConfidence(surfaceState)}`;
  }

  /**
   * @param {HTMLElement | null} card
   * @param {boolean} live
   * @param {string} [activity]
   */
  _setCardLive(card, live, activity) {
    if (!card) {
      return;
    }
    card.dataset.live = live ? "true" : "false";
    if (activity) {
      card.dataset.activity = activity;
    } else if (!live) {
      card.dataset.activity = "idle";
    }
    const indicator = card.querySelector(".tdl-v2-status-card__indicator");
    if (!indicator) {
      return;
    }
    indicator.classList.toggle("tdl-v2-status-card__indicator--live", live);
    indicator.classList.toggle("tdl-v2-status-card__indicator--idle", !live);
  }

  _updateMemoryUi() {
    const state = this._store?.getState();
    const activeTools = this._brain?.getActiveTools() ?? [];
    const memories = this._brain?.getMemoryEngine?.()?.getActiveMemories?.() ?? [];
    const memoryActive = Boolean(
      state?.recallActive
      || memories.length > 0
      || activeTools.some((t) => t.id === "memory" || t.id === "obsidian"),
    );

    const body = document.getElementById("card-recent-memory-body");
    if (body) {
      const rows = memories
        .slice()
        .sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0))
        .slice(0, 3)
        .map((memory) => presentMemoryRow(memory));

      if (rows.length) {
        body.innerHTML = `
          <ul class="tdl-v2-workspace-memory-list">
            ${rows.map((row) => `
              <li class="tdl-v2-workspace-memory-item">
                <span class="tdl-v2-workspace-memory-item__icon" aria-hidden="true">${escapeHtml(row.icon)}</span>
                <span class="tdl-v2-workspace-memory-item__text">
                  <span class="tdl-v2-workspace-memory-item__title">${escapeHtml(row.title)}</span>
                  <span class="tdl-v2-workspace-memory-item__meta">${escapeHtml(row.meta)}</span>
                </span>
              </li>
            `).join("")}
          </ul>
        `;
      } else if (state?.memoryStatusLine && memoryActive) {
        body.innerHTML = `
          <div class="tdl-v2-workspace-memory">
            <p class="tdl-v2-workspace-line tdl-v2-workspace-line--primary">
              ${escapeHtml(state.memoryStatusLine.slice(0, 42))}
            </p>
          </div>
        `;
      } else {
        body.innerHTML = this._idleMemoryHtml();
      }
    }

    this._setCardLive(
      document.getElementById("card-recent-memory"),
      memoryActive,
      memoryActive ? "remembering" : "idle",
    );
    const memStatus = document.getElementById("card-recent-memory-status");
    if (memStatus) memStatus.textContent = memoryActive ? "actif" : "veille";

    const memState = resolveMemoryModuleState(state ?? {});
    const confEl = document.getElementById("card-memory-confidence");
    const scanEl = document.getElementById("card-memory-scan");
    if (confEl) confEl.textContent = formatConfidence(state ?? {});
    if (scanEl) {
      scanEl.textContent =
        memState === "reading"
          ? "Scanning"
          : memState === "writing"
            ? "Writing"
            : memState === "waiting"
              ? "Waiting"
              : "Idle";
    }
    const memCard = document.getElementById("card-recent-memory");
    if (memCard) {
      memCard.dataset.cognitive = memState;
      memCard.dataset.cognitiveOs = "9";
    }
  }

  _updateToolUi() {
    const state = this._store?.getState();
    const active = this._brain?.getActiveTools() ?? [];
    const line = state?.toolStatusLine ?? "Outils — aucune activité";

    const toolLine = document.getElementById("tdl-v2-tool-status-line");
    if (toolLine) {
      toolLine.textContent = active.length ? line : "Outils — aucune activité";
      toolLine.dataset.active = String(active.length > 0);
    }

    const obsidianTool = active.find((t) => t.id === "obsidian");
    const obsidianActive = Boolean(obsidianTool);
    const systems = state?.systemsUsed;
    const obsidianInfo =
      systems && typeof systems === "object" && systems.obsidian && typeof systems.obsidian === "object"
        ? systems.obsidian
        : null;

    const vaultEl = document.getElementById("card-obsidian-vault");
    const metaEl = document.getElementById("card-obsidian-meta");
    const countsEl = document.getElementById("card-obsidian-counts");
    const vaultName =
      (typeof obsidianInfo?.vault_name === "string" && obsidianInfo.vault_name)
      || (typeof obsidianInfo?.vault === "string" && obsidianInfo.vault)
      || OBSIDIAN_VAULT_LABEL;

    if (vaultEl) {
      vaultEl.textContent = `Vault : ${vaultName}`;
    }
    if (metaEl) {
      metaEl.textContent = obsidianActive
        ? (obsidianTool?.statusLine || "Consultation vault").slice(0, 42)
        : "Vault connecté — en veille";
    }
    const syncEl = document.getElementById("card-obsidian-sync");
    const activityEl = document.getElementById("card-obsidian-activity");
    if (syncEl) {
      const lastSync =
        typeof obsidianInfo?.last_sync === "string"
          ? obsidianInfo.last_sync
          : typeof obsidianInfo?.synced_at === "string"
            ? obsidianInfo.synced_at
            : null;
      syncEl.textContent = lastSync
        ? `Dernière sync — ${String(lastSync).slice(0, 28)}`
        : obsidianActive
          ? "Dernière sync — en cours"
          : "Dernière sync — en veille";
    }
    if (activityEl) {
      activityEl.textContent = obsidianActive
        ? `Notes — ${(obsidianTool?.statusLine || "activité").slice(0, 32)}`
        : "Notes — aucune activité";
    }
    if (countsEl) {
      const notes = obsidianInfo?.note_count ?? obsidianInfo?.notes_count;
      const folders = obsidianInfo?.folder_count ?? obsidianInfo?.folders_count;
      const parts = [];
      if (typeof notes === "number") parts.push(`${notes} notes`);
      if (typeof folders === "number") parts.push(`${folders} dossiers`);
      if (parts.length) {
        countsEl.hidden = false;
        countsEl.textContent = parts.join(" · ");
      } else {
        countsEl.hidden = true;
        countsEl.textContent = "";
      }
    }
    this._setCardLive(
      document.getElementById("card-obsidian"),
      obsidianActive,
      obsidianActive ? "syncing" : "idle",
    );
    const obsStatus = document.getElementById("card-obsidian-status");
    if (obsStatus) obsStatus.textContent = obsidianActive ? "actif" : "veille";
    const obsCard = document.getElementById("card-obsidian");
    if (obsCard) {
      obsCard.dataset.cognitive = obsidianActive ? "reading" : "idle";
      obsCard.dataset.cognitiveOs = "9";
    }

    const browserTool = active.find((t) => t.id === "browser");
    const browserActive = Boolean(browserTool);
    const browserState = document.getElementById("card-browser-state");
    const browserMeta = document.getElementById("card-browser-meta");
    const browserTabs = document.getElementById("card-browser-tabs");
    const browserNav = document.getElementById("card-browser-nav");
    const browserNetwork = document.getElementById("card-browser-network");
    if (browserState) {
      browserState.textContent = browserActive
        ? "Session active"
        : "Navigation en réserve";
    }
    if (browserMeta) {
      browserMeta.textContent = browserActive
        ? (browserTool?.statusLine || state?.toolStatusLine || "Recherche en cours").slice(0, 42)
        : "Aucune recherche active";
    }
    if (browserNav) {
      browserNav.textContent = browserActive
        ? "Navigation — active"
        : "Navigation — idle";
    }
    if (browserNetwork) {
      const conn = state?.connectionState ?? "disconnected";
      browserNetwork.textContent =
        conn === "connected" || conn === "streaming"
          ? "Réseau — connecté"
          : conn === "connecting"
            ? "Réseau — connexion…"
            : "Réseau — hors ligne";
    }
    if (browserTabs) {
      const tabs =
        browserTool?.tabs
        ?? browserTool?.openTabs
        ?? (typeof systems?.browser?.tabs === "number" ? systems.browser.tabs : null);
      if (typeof tabs === "number" && tabs >= 0) {
        browserTabs.hidden = false;
        browserTabs.textContent = `${tabs} onglet${tabs === 1 ? "" : "s"}`;
      } else {
        browserTabs.hidden = true;
        browserTabs.textContent = "";
      }
    }
    this._setCardLive(
      document.getElementById("card-browser"),
      browserActive,
      browserActive ? "searching" : "idle",
    );
    const brStatus = document.getElementById("card-browser-status");
    if (brStatus) brStatus.textContent = browserActive ? "actif" : "veille";
    const browserCard = document.getElementById("card-browser");
    if (browserCard) {
      browserCard.dataset.cognitive = browserActive
        ? "searching"
        : resolveToolsModuleState(state ?? {}) === "searching"
          ? "searching"
          : "idle";
      browserCard.dataset.cognitiveOs = "9";
    }

    this._updateStrip();
  }

  _updateConversationUi() {
    const state = this._store?.getState();
    const line = state?.conversationStatusLine ?? "Conversation — en veille";
    const convLine = document.getElementById("tdl-v2-conversation-status-line");
    if (convLine) {
      convLine.textContent = line;
      convLine.dataset.active = String(Boolean(state?.conversationActive));
    }

    const memLine = document.getElementById("tdl-v2-memory-status-line");
    if (memLine) {
      memLine.textContent = state?.memoryStatusLine ?? "Mémoire — en veille";
    }
  }
}
