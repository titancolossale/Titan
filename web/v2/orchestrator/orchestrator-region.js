/** Titan Frontend V2 — Cognitive Operating System Runtime Monitor (Phase 9).
 * Presentation command center · reuses CognitiveStateEngine + StateStore only.
 * Phase 4.2/4.3/5/6/8 contracts preserved. Phase 9: honest OS telemetry — no fake execution.
 */

import { div, el, svgIcon } from "../components/dom-utils.js";
import { createTitanLogo } from "../components/titan-logo.js";
import { REGION_IDS } from "../layout/regions.js";
import { TITAN_UI_VERSION_LABEL } from "../core/version.js";
import {
  formatConnectedSystems,
  formatCurrentObjective,
  formatLatency,
  formatMemoryAccess,
  formatModelState,
  formatPlanningQueue,
  formatReasoningStage,
} from "../core/cognitive-os-telemetry.js";

/** Canonical 9-step execution pipeline (final reference — French). */
export const IDLE_PLAN_STEPS = Object.freeze([
  "Compréhension",
  "Analyse",
  "Planification",
  "Collecte d'informations",
  "Synthèse",
  "Génération",
  "Validation",
  "Réponse",
  "Apprentissage",
]);

/** Sub-labels for pipeline steps — calm secondary line under each title. */
export const IDLE_PLAN_SUBLABELS = Object.freeze({
  "Compréhension": "Intent · contraintes",
  "Analyse": "Signaux · lecture",
  "Planification": "Étapes · ordre",
  "Collecte d'informations": "Sources · rappel",
  "Synthèse": "Unification · clarté",
  "Génération": "Formulation · voix",
  "Validation": "Contrôle · intégrité",
  "Réponse": "Livraison · utilisateur",
  "Apprentissage": "Mémoire · amélioration",
});

/** Instrument catalog — elegant list; activity is honest. */
export const ORCHESTRATOR_TOOL_CATALOG = Object.freeze([
  { id: "memory", title: "Mémoire", idleAction: "En veille" },
  { id: "browser", title: "Browser", idleAction: "En veille" },
  { id: "obsidian", title: "Obsidian", idleAction: "En veille" },
  { id: "trading", title: "Trading", idleAction: "Hors ligne" },
  { id: "calendar", title: "Calendar", idleAction: "Hors ligne" },
  { id: "voice", title: "Voice", idleAction: "Hors ligne" },
]);

/**
 * Honest idle presence signals retained for presence-sprint compatibility.
 * Phase 6 keeps these as hidden hooks — never a dashboard list.
 */
export const IDLE_PRESENCE_ROWS = Object.freeze([
  { key: "Présence", value: "Attentive", tone: "live" },
  { key: "Surveillance", value: "Passive", tone: "calm" },
  { key: "Mémoire", value: "Disponible", tone: "calm" },
  { key: "Attente", value: "Instruction utilisateur", tone: "calm" },
  { key: "Exécution", value: "Aucune active", tone: "calm" },
]);

/** Tiny SVG paths for Active Tools icons. */
const TOOL_ICON_PATHS = Object.freeze({
  memory:
    '<path d="M8 2.5c-2.2 0-4 1.6-4 3.6 0 2.4 1.6 3.8 4 5.9 2.4-2.1 4-3.5 4-5.9 0-2-1.8-3.6-4-3.6z" fill="none" stroke="currentColor" stroke-width="1.1"/><circle cx="8" cy="6.2" r="1.1" fill="currentColor" opacity="0.55"/>',
  browser:
    '<rect x="2.5" y="3.5" width="11" height="9" rx="1.4" fill="none" stroke="currentColor" stroke-width="1.1"/><path d="M2.5 6.2h11M5.2 3.5v2.7" stroke="currentColor" stroke-width="1.1"/>',
  obsidian:
    '<path d="M8 2.2 12.5 5.4v5.2L8 13.8 3.5 10.6V5.4z" fill="none" stroke="currentColor" stroke-width="1.1"/><path d="M8 5.2v5.4M5.6 6.8l4.8 2.4" stroke="currentColor" stroke-width="0.9" opacity="0.7"/>',
  trading:
    '<path d="M3 11.5 6.2 7.8 8.6 9.6 13 4.5" fill="none" stroke="currentColor" stroke-width="1.15" stroke-linecap="round" stroke-linejoin="round"/><path d="M10.5 4.5H13v2.5" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>',
  calendar:
    '<rect x="3" y="4" width="10" height="9" rx="1.3" fill="none" stroke="currentColor" stroke-width="1.1"/><path d="M3 6.8h10M5.5 2.8v2.4M10.5 2.8v2.4" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>',
  voice:
    '<path d="M8 2.8a2.1 2.1 0 0 0-2.1 2.1v3.2a2.1 2.1 0 1 0 4.2 0V4.9A2.1 2.1 0 0 0 8 2.8z" fill="none" stroke="currentColor" stroke-width="1.1"/><path d="M4.2 8.2a3.8 3.8 0 0 0 7.6 0M8 12v1.4" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>',
});

/** @typedef {"completed"|"active"|"waiting"|"failed"|"error"} PlanStepStatus */

const STATUS_COPY = Object.freeze({
  completed: "Terminé",
  active: "Active",
  waiting: "En attente",
  failed: "Erreur",
  error: "Erreur",
});

export class OrchestratorRegion {
  /**
   * @param {import("../layout/shell.js").Shell} shell
   * @param {import("../core/state-store.js").StateStore} store
   */
  constructor(shell, store) {
    this._shell = shell;
    this._store = store;
    /** @type {import("../core/cognitive-state-engine.js").CognitiveStateEngine | null} */
    this._brain = null;
    /** @type {number | null} */
    this._waveRaf = null;
    /** @type {number} */
    this._wavePhase = 0;
    /** @type {Map<string, string>} */
    this._lastToolAction = new Map();
  }

  /**
   * @param {import("../core/cognitive-state-engine.js").CognitiveStateEngine} brain
   */
  setBrain(brain) {
    this._brain = brain;
    brain.onStateChanged((snapshot) => {
      this._updateObjectiveSection(snapshot.label, snapshot.id);
      this._updateNeuralLabel(snapshot.label);
      this._updatePlanSection();
      this._updateRuntimeMonitor();
      this._updateFooterStatus();
      this._syncPresenceDataset();
      this._syncAliveDataset();
    });
    brain.onToolActivity((event) => {
      if (event?.tool?.id && event?.tool?.statusLine) {
        this._lastToolAction.set(event.tool.id, String(event.tool.statusLine).slice(0, 72));
      }
      this._updateToolsSection();
      this._updatePlanSection();
      this._updateRuntimeMonitor();
      this._updateFooterStatus();
      this._syncPresenceDataset();
      this._syncAliveDataset();
    });
    brain.onMemoryActivity(() => {
      this._updateObjectiveSection(
        this._brain?.getState()?.label ?? "Idle",
        this._brain?.getState()?.id ?? "idle",
      );
      this._updateRuntimeMonitor();
      this._updateFooterStatus();
      this._syncPresenceDataset();
      this._syncAliveDataset();
    });
    brain.onConversationActivity(() => {
      this._updatePlanSection();
      this._updateObjectiveSection(
        this._brain?.getState()?.label ?? "Idle",
        this._brain?.getState()?.id ?? "idle",
      );
      this._updateRuntimeMonitor();
      this._updateFooterStatus();
      this._syncPresenceDataset();
      this._syncAliveDataset();
    });
    brain.getPipelineStore().subscribe(() => {
      this._updatePlanSection();
      this._updateRuntimeMonitor();
      this._updateFooterStatus();
      this._syncPresenceDataset();
      this._syncAliveDataset();
    });
    const snap = brain.getState();
    this._updateObjectiveSection(snap.label, snap.id);
    this._updateToolsSection();
    this._updatePlanSection();
    this._updateRuntimeMonitor();
    this._updateFooterStatus();
    this._syncPresenceDataset();
    this._syncAliveDataset();
    this._startWaveform();
  }

  mount() {
    const host = this._shell.get(REGION_IDS.orchestrator);
    if (!host) {
      return;
    }

    host.classList.add(
      "tdl-v2-orchestrator--reference",
      "tdl-v2-orchestrator--phase42",
      "tdl-v2-orchestrator--phase43",
      "tdl-v2-orchestrator--phase5",
      "tdl-v2-orchestrator--phase6",
      "tdl-v2-orchestrator--living",
      "tdl-v2-orchestrator--presence",
      "tdl-v2-orchestrator--cognitive-os",
      "tdl-v2-orchestrator--canonical",
    );
    host.dataset.phase = "10";
    host.dataset.layout = "canonical-final";
    host.dataset.canonical = "final";
    host.dataset.alive = "false";
    host.dataset.presence = "9";
    host.dataset.cognitiveOs = "9";

    const header = div("tdl-v2-orchestrator-header");
    const titleRow = div("tdl-v2-orchestrator-header__title-row");
    const neuralIcon = createTitanLogo({
      size: "md",
      className: "tdl-v2-orchestrator-header__neural",
    });
    const titleBlock = div("tdl-v2-orchestrator-header__titles");
    titleBlock.append(
      el("h2", "tdl-v2-orchestrator-header__title", { text: "Titan Core" }),
      el("span", "tdl-v2-orchestrator-header__subtitle", {
        text: "Conscience & Orchestration",
      }),
    );
    titleRow.append(neuralIcon, titleBlock);

    const alive = div("tdl-v2-orchestrator-header__alive");
    alive.append(
      div("tdl-v2-orchestrator-header__alive-dot"),
      el("span", "", { text: "LIVE" }),
    );

    const activity = div("tdl-v2-orchestrator-header__activity");
    activity.setAttribute("aria-hidden", "true");
    activity.appendChild(div("tdl-v2-orchestrator-header__activity-scan"));

    header.append(titleRow, alive, activity);

    /* Phase 8/9 — tiny activity markers (telemetry chrome only). */
    for (const suffix of ["a", "b", "c"]) {
      const marker = div(`tdl-v2-orch-activity-marker tdl-v2-orch-activity-marker--${suffix}`);
      marker.setAttribute("aria-hidden", "true");
      host.appendChild(marker);
    }

    const sections = div("tdl-v2-orchestrator-sections");
    sections.dataset.role = "orchestrator-sections";

    sections.append(
      this._section("objective", "Objectif Actuel", this._objectiveBlock()),
      this._section("monitor", "Runtime Monitor", this._runtimeMonitorBlock()),
      this._section("plan", "Pipeline d'Exécution", this._planBlock()),
      this._section("tools", "Systèmes Connectés", this._toolsBlock()),
      this._section("sparkline", "Activité Neurale", this._sparklineBlock()),
    );

    // Idle life layer retained for cinematic CSS hooks (hidden in Phase 6).
    const idleLife = this._idleLifeBlock();
    sections.insertBefore(idleLife, sections.firstChild);

    const footer = this._footerBlock();
    host.append(header, sections, footer);

    this._store.subscribe((state) => {
      host.dataset.presence = state.presence;
      host.dataset.drawerOpen = String(state.orchestratorDrawerOpen);
      this._syncPresenceDataset(state);
      this._syncAliveDataset(state);
      this._updateObjectiveSection(
        this._brain?.getState()?.label ?? "Idle",
        this._brain?.getState()?.id ?? "idle",
      );
      this._updatePlanSection();
      this._updateToolsSection();
      this._updateRuntimeMonitor(state);
      this._updateFooterStatus(state);
      const root = document.getElementById("titan-v2-root");
      if (root) {
        root.dataset.presence = state.presence;
        root.dataset.cognitiveOs = "9";
      }
    });

    this._startWaveform();
    this._updateFooterStatus();
    this._updateRuntimeMonitor();
  }

  /** Soft neural glyph — animated via CSS pulse. */
  _neuralGlyph() {
    return svgIcon(
      "0 0 16 16",
      [
        '<circle class="tdl-v2-orch-neural__core" cx="8" cy="8" r="2.2" fill="currentColor"/>',
        '<circle class="tdl-v2-orch-neural__ring" cx="8" cy="8" r="5.2" stroke="currentColor" stroke-width="0.7" fill="none" opacity="0.55"/>',
        '<circle cx="3.2" cy="4.2" r="1" fill="currentColor" opacity="0.55"/>',
        '<circle cx="12.8" cy="4.4" r="1" fill="currentColor" opacity="0.45"/>',
        '<circle cx="3.4" cy="11.6" r="1" fill="currentColor" opacity="0.4"/>',
        '<circle cx="12.6" cy="11.4" r="1" fill="currentColor" opacity="0.5"/>',
        '<path d="M4.1 4.8 L6.6 7.1 M11.9 5 L9.4 7.1 M4.2 11 L6.7 9 M11.8 11 L9.3 9" stroke="currentColor" stroke-width="0.6" opacity="0.4"/>',
      ].join(""),
      14,
    );
  }

  /**
   * @param {import("../core/state-store.js").AppState} [state]
   */
  _syncAliveDataset(state = this._store.getState()) {
    const host = this._shell.get(REGION_IDS.orchestrator);
    if (!host) return;
    const thinking = Boolean(state.pipelineThinking || state.presence === "thinking");
    const tools = state.activeToolCount ?? 0;
    const error = state.cognitiveState === "error" || state.presence === "error";
    host.dataset.alive = String(thinking || tools > 0 || error);
  }

  /**
   * Keep honest presence values available for telemetry consumers / legacy hooks.
   * @param {import("../core/state-store.js").AppState} [state]
   */
  _syncPresenceDataset(state = this._store.getState()) {
    const thinking = Boolean(state.pipelineThinking || state.presence === "thinking");
    const tools = state.activeToolCount ?? 0;
    const memory = Boolean(state.recallActive);
    const connected =
      state.connectionState === "connected" || state.connectionState === "streaming";

    this._setPresenceValue("presence", connected ? "Attentive" : "Reconnexion…", connected ? "live" : "calm");
    this._setPresenceValue(
      "monitoring",
      thinking || tools > 0 ? "Active" : "Passive",
      thinking || tools > 0 ? "live" : "calm",
    );
    this._setPresenceValue(
      "memory",
      memory ? "Rappel en cours" : "Disponible",
      memory ? "live" : "calm",
    );
    this._setPresenceValue(
      "waiting",
      thinking ? "Réflexion en cours" : "Instruction utilisateur",
      thinking ? "live" : "calm",
    );
    this._setPresenceValue(
      "execution",
      tools > 0 ? `${tools} outil${tools > 1 ? "s" : ""} actif${tools > 1 ? "s" : ""}` : "Aucune active",
      tools > 0 ? "live" : "calm",
    );
  }

  /**
   * @param {string} id
   * @param {string} text
   * @param {"live"|"calm"} tone
   */
  _setPresenceValue(id, text, tone) {
    const elValue = document.getElementById(`tdl-v2-orch-presence-${id}`);
    if (!elValue) return;
    elValue.textContent = text;
    elValue.dataset.tone = tone;
  }

  /**
   * Derive operating mode from real frontend state only.
   * @param {import("../core/state-store.js").AppState} state
   * @param {string} cognitiveId
   */
  _resolveOperatingMode(state, cognitiveId) {
    // Connection-only faults are shown under Connexion — not Mode.
    const connected =
      state.connectionState === "connected" || state.connectionState === "streaming";
    if (cognitiveId === "error" && connected && state.lastError) return "Erreur";
    if (state.presence === "error" && connected && state.lastError) return "Erreur";
    if (state.pipelineThinking || state.presence === "thinking") return "Réflexion";
    if ((state.activeToolCount ?? 0) > 0) return "Exécution";
    if (state.recallActive) return "Mémoire";
    if (cognitiveId === "listening" || cognitiveId === "voice") return "Écoute";
    if (cognitiveId === "planning") return "Planification";
    if (cognitiveId === "sleep") return "Veille";
    return "Assistance adaptative";
  }

  /** @param {string} label @param {string} id */
  _updateObjectiveSection(label, id) {
    const badge = document.getElementById("tdl-v2-orchestrator-state-badge");
    const mission = document.getElementById("tdl-v2-orchestrator-mission");
    const objective = document.getElementById("tdl-v2-orchestrator-objective");
    const secondary = document.getElementById("tdl-v2-orchestrator-secondary");
    const live = document.getElementById("tdl-v2-orchestrator-live-status");
    const action = document.getElementById("tdl-v2-orchestrator-action");
    const modeEl = document.getElementById("tdl-v2-orchestrator-mode");
    const statusChip = document.getElementById("tdl-v2-orchestrator-status-chip");
    const idle = id === "idle" || id === "sleep";
    const state = this._store.getState();
    const thinking = Boolean(state.pipelineThinking || state.conversationActive || state.presence === "thinking");
    const connected =
      state.connectionState === "connected" || state.connectionState === "streaming";
    const error = (id === "error" || state.presence === "error") && connected && Boolean(state.lastError);
    const mode = this._resolveOperatingMode(state, id);

    if (badge) badge.textContent = label;
    if (action) {
      action.textContent = idle && !thinking ? "Présence calme" : label;
    }
    if (modeEl) modeEl.textContent = mode;
    if (objective) {
      objective.textContent = formatCurrentObjective(state, label);
    }
    if (mission) {
      const missionLine = state.pipelineLabel && !idle
        ? state.pipelineLabel.slice(0, 72)
        : thinking
          ? "Mission cognitive en cours"
          : "Analyser la demande, orchestrer les ressources nécessaires";
      mission.textContent = missionLine;
    }
    if (secondary) {
      secondary.textContent = idle && !thinking
        ? "Analyser la demande, orchestrer les ressources nécessaires"
        : thinking
          ? "Exécution cognitive · instruments engagés"
          : "Présence attentive · en réserve";
    }
    if (live) {
      live.textContent = error
        ? "ERROR"
        : thinking || (state.activeToolCount ?? 0) > 0
          ? "LIVE"
          : idle
            ? "IDLE"
            : label.toUpperCase();
      live.dataset.tone = error
        ? "error"
        : thinking || (state.activeToolCount ?? 0) > 0
          ? "live"
          : "calm";
    }
    if (statusChip) {
      statusChip.textContent = error
        ? "Erreur"
        : thinking || (state.activeToolCount ?? 0) > 0
          ? "Active"
          : "En veille";
      statusChip.dataset.tone = error
        ? "error"
        : thinking || (state.activeToolCount ?? 0) > 0
          ? "live"
          : "calm";
    }

    const block = document.getElementById("tdl-v2-orchestrator-state");
    if (block) {
      block.dataset.cognitiveState = id;
      block.dataset.alive = String(thinking || (state.activeToolCount ?? 0) > 0 || error);
    }

    this._syncPresenceDataset();
  }

  _updateToolsSection() {
    const list = document.getElementById("tdl-v2-orchestrator-tools");
    if (!list) return;

    list.replaceChildren();
    const active = this._brain?.getActiveTools() ?? [];
    const activeMap = new Map(active.map((t) => [t.id, t]));

    const catalog = [...ORCHESTRATOR_TOOL_CATALOG];
    for (const tool of active) {
      if (!catalog.some((c) => c.id === tool.id)) {
        catalog.push({
          id: tool.id,
          title: tool.definition?.title ?? tool.id,
          idleAction: "En veille",
        });
      }
    }

    for (const entry of catalog) {
      const instance = activeMap.get(entry.id);
      const isActive = Boolean(instance);
      const row = el("li", "tdl-v2-orchestrator-tools__item tdl-v2-orchestrator-tool-row");
      row.dataset.toolId = entry.id;
      row.dataset.active = String(isActive);

      const icon = div("tdl-v2-orchestrator-tools__icon");
      icon.setAttribute("aria-hidden", "true");
      const path = TOOL_ICON_PATHS[entry.id]
        || '<circle cx="8" cy="8" r="2.2" fill="currentColor" opacity="0.7"/>';
      icon.appendChild(svgIcon("0 0 16 16", path, 11));
      icon.appendChild(div("tdl-v2-orchestrator-tools__dot"));

      const body = div("tdl-v2-orchestrator-tool-row__body");
      const head = div("tdl-v2-orchestrator-tool-row__head");
      head.append(
        el("span", "tdl-v2-orchestrator-tools__name", { text: entry.title }),
        el("span", "tdl-v2-orchestrator-tools__state", {
          text: isActive ? "Actif" : entry.idleAction,
        }),
      );

      const recent = this._lastToolAction.get(entry.id)
        || (isActive ? (instance?.statusLine ?? entry.idleAction) : entry.idleAction);
      const action = el("p", "tdl-v2-orchestrator-tool-row__action", {
        text: recent,
      });

      body.append(head, action);
      row.append(icon, body);
      list.appendChild(row);
    }
  }

  /** @param {string} label */
  _updateNeuralLabel(label) {
    const elLabel = document.getElementById("tdl-v2-orchestrator-neural-label");
    if (elLabel) elLabel.textContent = label;
  }

  _updatePlanSection() {
    const list = document.getElementById("tdl-v2-orchestrator-steps");
    if (!list) return;

    const state = this._store.getState();
    const liveSteps = state.conversationPlanSteps ?? [];
    const thinking = Boolean(state.pipelineThinking || state.conversationActive);
    const error = state.cognitiveState === "error" || state.presence === "error";
    const steps = liveSteps.length > 0 ? liveSteps : [...IDLE_PLAN_STEPS];

    list.replaceChildren();
    steps.forEach((step, index) => {
      /** @type {PlanStepStatus} */
      let status = "waiting";
      if (liveSteps.length > 0) {
        if (error && index === liveSteps.length - 1) {
          status = "error";
        } else if (index < liveSteps.length - 1 && thinking) {
          status = "completed";
        } else if (index === liveSteps.length - 1 && thinking) {
          status = "active";
        } else if (!thinking && index < liveSteps.length) {
          status = "completed";
        }
      } else if (error && thinking) {
        status = index === 0 ? "error" : "waiting";
      } else if (!thinking) {
        status = "waiting";
      }

      const item = el("li", "tdl-v2-orchestrator-steps__item");
      item.dataset.status = status;

      const indexEl = el("span", "tdl-v2-orchestrator-steps__index", { text: String(index + 1) });
      if (status === "completed") {
        indexEl.classList.add("tdl-v2-orchestrator-steps__index--done");
      } else if (status === "active") {
        indexEl.classList.add("tdl-v2-orchestrator-steps__index--active");
      } else if (status === "error" || status === "failed") {
        indexEl.classList.add("tdl-v2-orchestrator-steps__index--error");
      }

      const mark = div("tdl-v2-orchestrator-steps__mark");
      mark.setAttribute("aria-hidden", "true");
      mark.dataset.status = status;

      const body = div("tdl-v2-orchestrator-steps__body");
      const titleRow = div("tdl-v2-orchestrator-steps__title-row");
      titleRow.append(
        el("span", "tdl-v2-orchestrator-steps__label", { text: step }),
        mark,
      );
      body.append(
        titleRow,
        el("span", "tdl-v2-orchestrator-steps__status", {
          text: STATUS_COPY[status] ?? "Waiting",
        }),
        el("span", "tdl-v2-orchestrator-steps__sub", {
          text: IDLE_PLAN_SUBLABELS[step] || "Étape cognitive",
        }),
      );

      const progress = div("tdl-v2-orchestrator-steps__progress");
      progress.setAttribute("aria-hidden", "true");
      if (status === "active") {
        progress.appendChild(div("tdl-v2-orchestrator-steps__progress-bar"));
      }

      item.append(indexEl, body, progress);
      list.appendChild(item);
    });

    const idleNote = document.getElementById("tdl-v2-orchestrator-plan-idle");
    if (idleNote) {
      idleNote.hidden = liveSteps.length > 0 || thinking;
    }
  }

  /**
   * Bottom runtime summary — reuses existing telemetry fields only.
   * @param {import("../core/state-store.js").AppState} [state]
   */
  _updateFooterStatus(state = this._store.getState()) {
    const cognitiveId = this._brain?.getState()?.id ?? state.cognitiveState ?? "idle";
    const mode = this._resolveOperatingMode(state, cognitiveId);
    const connected =
      state.connectionState === "connected" || state.connectionState === "streaming";
    const duration = state.orchestrationDuration;
    let latency = "—";
    if (typeof duration === "number" && Number.isFinite(duration)) {
      latency = duration < 1
        ? `${Math.round(duration * 1000)} ms`
        : `${duration.toFixed(1)} s`;
    }

    const systems = state.systemsUsed;
    let subsystems = ORCHESTRATOR_TOOL_CATALOG.length;
    if (systems && typeof systems === "object") {
      const keys = Object.keys(systems).filter((key) => {
        const value = systems[key];
        return value !== null && value !== undefined && value !== false;
      });
      if (keys.length > 0) subsystems = keys.length;
    }

    this._setFooterValue(
      "mode",
      mode,
      mode === "Erreur" ? "error" : mode === "Assistance adaptative" ? "calm" : "live",
    );
    this._setFooterValue("latency", latency, latency === "—" ? "calm" : "live");
    this._setFooterValue("runtime", state.systemVersion || TITAN_UI_VERSION_LABEL, "calm");
    this._setFooterValue(
      "subsystems",
      `${subsystems}/${Math.max(subsystems, ORCHESTRATOR_TOOL_CATALOG.length)} actifs`,
      "calm",
    );
    this._setFooterValue(
      "connection",
      connected
        ? "Sécurisée"
        : state.connectionState === "connecting"
          ? "Connexion…"
          : "Hors ligne",
      connected ? "live" : "calm",
    );
  }

  /**
   * @param {string} id
   * @param {string} text
   * @param {"live"|"calm"|"error"} tone
   */
  _setFooterValue(id, text, tone) {
    const node = document.getElementById(`tdl-v2-orch-footer-${id}`);
    if (!node) return;
    node.textContent = text;
    node.dataset.tone = tone;
  }

  /**
   * Runtime Monitor — honest frontend telemetry only.
   * Current objective · Reasoning stage · Execution queue · Connected systems ·
   * Running tools · Memory access · Latency · Model state · Planning queue.
   * @param {import("../core/state-store.js").AppState} [state]
   */
  _updateRuntimeMonitor(state = this._store.getState()) {
    const activeTools = this._brain?.getActiveTools() ?? [];
    const systems = formatConnectedSystems(state, ORCHESTRATOR_TOOL_CATALOG.length);
    const planQueue = formatPlanningQueue(state);
    const liveSteps = state.conversationPlanSteps ?? [];
    const thinking = Boolean(state.pipelineThinking || state.conversationActive);
    const queueCount = liveSteps.length > 0
      ? liveSteps.length
      : thinking
        ? IDLE_PLAN_STEPS.length
        : 0;

    this._setMonitorValue("reasoning", formatReasoningStage(state));
    this._setMonitorValue(
      "execution",
      queueCount > 0
        ? `${queueCount} étape${queueCount > 1 ? "s" : ""}`
        : "File vide",
    );
    this._setMonitorValue(
      "systems",
      systems.labels.length
        ? systems.labels.slice(0, 4).join(" · ")
        : `${systems.count} connectés`,
    );
    this._setMonitorValue(
      "tools",
      activeTools.length > 0
        ? activeTools.map((t) => t.id).slice(0, 4).join(" · ")
        : "Aucun actif",
    );
    this._setMonitorValue("memory", formatMemoryAccess(state));
    this._setMonitorValue("latency", formatLatency(state));
    this._setMonitorValue("model", formatModelState(state));
    this._setMonitorValue(
      "planning",
      planQueue.length > 0
        ? planQueue.slice(0, 3).join(" → ")
        : thinking
          ? "Pipeline cognitif"
          : "Aucune file",
    );

    const block = document.getElementById("tdl-v2-orchestrator-monitor");
    if (block) {
      const busy = thinking || activeTools.length > 0 || Boolean(state.recallActive);
      block.dataset.alive = String(busy);
      block.dataset.cognitiveOs = "9";
    }
  }

  /**
   * @param {string} id
   * @param {string} text
   */
  _setMonitorValue(id, text) {
    const node = document.getElementById(`tdl-v2-orch-monitor-${id}`);
    if (!node) return;
    node.textContent = text;
    const calm = text === "—"
      || text === "File vide"
      || text === "Aucun actif"
      || text === "Aucune lecture"
      || text === "En réserve"
      || text === "Aucune file"
      || text === "Veille";
    node.dataset.tone = calm ? "calm" : "live";
  }

  /** Runtime monitor body — presentation rows only. */
  _runtimeMonitorBlock() {
    const wrap = div("tdl-v2-orchestrator-monitor");
    wrap.id = "tdl-v2-orchestrator-monitor";
    wrap.dataset.alive = "false";
    wrap.dataset.cognitiveOs = "9";
    wrap.setAttribute("aria-label", "Runtime monitor");

    const rows = [
      { id: "reasoning", key: "Reasoning stage", value: "En réserve" },
      { id: "execution", key: "Execution queue", value: "File vide" },
      { id: "systems", key: "Connected systems", value: String(ORCHESTRATOR_TOOL_CATALOG.length) },
      { id: "tools", key: "Running tools", value: "Aucun actif" },
      { id: "memory", key: "Memory access", value: "Aucune lecture" },
      { id: "latency", key: "Latency", value: "—" },
      { id: "model", key: "Model state", value: "Veille" },
      { id: "planning", key: "Planning queue", value: "Aucune file" },
    ];

    for (const row of rows) {
      const line = el("p", "tdl-v2-orchestrator-monitor__row");
      line.dataset.monitor = row.id;
      line.append(
        el("span", "tdl-v2-orchestrator-monitor__key", { text: row.key }),
        el("span", "tdl-v2-orchestrator-monitor__value", {
          id: `tdl-v2-orch-monitor-${row.id}`,
          text: row.value,
          "data-tone": "calm",
        }),
      );
      wrap.appendChild(line);
    }
    return wrap;
  }

  /** @param {string} id @param {string} title @param {HTMLElement} body */
  _section(id, title, body) {
    const section = el("section", "tdl-v2-orchestrator-section", { "data-section": id });
    section.append(
      el("h3", "tdl-v2-orchestrator-section__title", { text: title }),
      body,
    );
    return section;
  }

  _objectiveBlock() {
    const wrap = div("tdl-v2-orchestrator-state tdl-v2-orchestrator-objective");
    wrap.id = "tdl-v2-orchestrator-state";
    wrap.dataset.alive = "false";
    wrap.dataset.cognitiveState = "idle";

    const pulse = div("tdl-v2-orchestrator-objective__pulse");
    pulse.setAttribute("aria-hidden", "true");
    for (let i = 0; i < 5; i += 1) {
      const bar = div("tdl-v2-orchestrator-state__bar");
      bar.style.height = `${28 + (i % 3) * 18}%`;
      pulse.appendChild(bar);
    }

    const copy = div("tdl-v2-orchestrator-state__copy");
    const meta = div("tdl-v2-orchestrator-objective__meta");
    meta.append(
      el("span", "tdl-v2-orchestrator-state__badge", {
        id: "tdl-v2-orchestrator-state-badge",
        text: "Idle",
      }),
      el("span", "tdl-v2-orchestrator-objective__live", {
        id: "tdl-v2-orchestrator-live-status",
        text: "IDLE",
        "data-tone": "calm",
      }),
    );

    const modeRow = div("tdl-v2-orchestrator-objective__mode-row");
    const modeWrap = el("span", "tdl-v2-orchestrator-objective__mode");
    modeWrap.append(
      el("span", "tdl-v2-orchestrator-objective__mode-key", { text: "Mode Opérationnel" }),
      el("span", "", {
        id: "tdl-v2-orchestrator-mode",
        text: "Assistance adaptative",
      }),
    );
    modeRow.append(
      modeWrap,
      el("span", "tdl-v2-orchestrator-objective__status-chip", {
        id: "tdl-v2-orchestrator-status-chip",
        text: "En veille",
        "data-tone": "calm",
      }),
    );

    copy.append(
      meta,
      el("p", "tdl-v2-orchestrator-objective__headline", {
        id: "tdl-v2-orchestrator-objective",
        text: "Comprendre et assister",
      }),
      el("p", "tdl-v2-orchestrator-objective__mission", {
        id: "tdl-v2-orchestrator-mission",
        text: "Analyser la demande, orchestrer les ressources nécessaires",
      }),
      el("p", "tdl-v2-orchestrator-objective__secondary", {
        id: "tdl-v2-orchestrator-secondary",
        text: "Analyser la demande, orchestrer les ressources nécessaires",
      }),
      el("p", "tdl-v2-orchestrator-state__row tdl-v2-orchestrator-objective__action", {
        html: '<span class="tdl-v2-orchestrator-state__key">Action</span> <span id="tdl-v2-orchestrator-action">Présence calme</span>',
      }),
      modeRow,
    );

    // Hidden honest presence hooks (Sprint 2.9 compatibility / telemetry).
    const presence = div("tdl-v2-orchestrator-presence tdl-v2-orchestrator-presence--sr");
    presence.id = "tdl-v2-orchestrator-presence";
    presence.setAttribute("aria-hidden", "true");
    const ids = ["presence", "monitoring", "memory", "waiting", "execution"];
    IDLE_PRESENCE_ROWS.forEach((row, index) => {
      const line = el("p", "tdl-v2-orchestrator-presence__row");
      line.append(
        el("span", "tdl-v2-orchestrator-presence__key", { text: row.key }),
        el("span", "tdl-v2-orchestrator-presence__value", {
          id: `tdl-v2-orch-presence-${ids[index]}`,
          text: row.value,
          "data-tone": row.tone,
        }),
      );
      presence.appendChild(line);
    });

    wrap.append(copy, pulse, presence);
    return wrap;
  }

  _planBlock() {
    const wrap = div("tdl-v2-orchestrator-plan");
    const idle = el("p", "tdl-v2-orchestrator-plan__idle", {
      id: "tdl-v2-orchestrator-plan-idle",
      text: "Aucune exécution active — parcours cognitif en réserve.",
    });
    const list = el("ol", "tdl-v2-orchestrator-steps", { id: "tdl-v2-orchestrator-steps" });
    for (let i = 0; i < IDLE_PLAN_STEPS.length; i += 1) {
      const step = IDLE_PLAN_STEPS[i];
      const item = el("li", "tdl-v2-orchestrator-steps__item");
      item.dataset.status = "waiting";
      const mark = div("tdl-v2-orchestrator-steps__mark");
      mark.setAttribute("aria-hidden", "true");
      mark.dataset.status = "waiting";
      const body = div("tdl-v2-orchestrator-steps__body");
      const titleRow = div("tdl-v2-orchestrator-steps__title-row");
      titleRow.append(
        el("span", "tdl-v2-orchestrator-steps__label", { text: step }),
        mark,
      );
      body.append(
        titleRow,
        el("span", "tdl-v2-orchestrator-steps__status", { text: STATUS_COPY.waiting }),
        el("span", "tdl-v2-orchestrator-steps__sub", {
          text: IDLE_PLAN_SUBLABELS[step] || "Étape cognitive",
        }),
      );
      item.append(
        el("span", "tdl-v2-orchestrator-steps__index", { text: String(i + 1) }),
        body,
        div("tdl-v2-orchestrator-steps__progress"),
      );
      list.appendChild(item);
    }
    wrap.append(idle, list);
    return wrap;
  }

  _toolsBlock() {
    const list = el("ul", "tdl-v2-orchestrator-tools tdl-v2-orchestrator-tools--list", {
      id: "tdl-v2-orchestrator-tools",
    });
    for (const entry of ORCHESTRATOR_TOOL_CATALOG) {
      const item = el("li", "tdl-v2-orchestrator-tools__item tdl-v2-orchestrator-tool-row");
      item.dataset.active = "false";
      item.dataset.toolId = entry.id;
      const icon = div("tdl-v2-orchestrator-tools__icon");
      icon.setAttribute("aria-hidden", "true");
      const path = TOOL_ICON_PATHS[entry.id]
        || '<circle cx="8" cy="8" r="2.2" fill="currentColor" opacity="0.7"/>';
      icon.appendChild(svgIcon("0 0 16 16", path, 11));
      icon.appendChild(div("tdl-v2-orchestrator-tools__dot"));
      const body = div("tdl-v2-orchestrator-tool-row__body");
      const head = div("tdl-v2-orchestrator-tool-row__head");
      head.append(
        el("span", "tdl-v2-orchestrator-tools__name", { text: entry.title }),
        el("span", "tdl-v2-orchestrator-tools__state", { text: "veille" }),
      );
      body.append(
        head,
        el("p", "tdl-v2-orchestrator-tool-row__action", { text: entry.idleAction }),
      );
      item.append(icon, body);
      list.appendChild(item);
    }
    return list;
  }

  _footerBlock() {
    const footer = el("footer", "tdl-v2-orchestrator-footer", {
      "data-section": "status",
    });
    footer.appendChild(
      el("h3", "tdl-v2-orchestrator-footer__title", { text: "État Système" }),
    );

    const grid = div("tdl-v2-orchestrator-footer__grid");
    const items = [
      { id: "mode", key: "Mode", value: "Assistance adaptative" },
      { id: "latency", key: "Latence", value: "—" },
      { id: "runtime", key: "Runtime", value: TITAN_UI_VERSION_LABEL },
      {
        id: "subsystems",
        key: "Subsystems",
        value: `${ORCHESTRATOR_TOOL_CATALOG.length}/${ORCHESTRATOR_TOOL_CATALOG.length} actifs`,
      },
      { id: "connection", key: "Connexion", value: "Hors ligne" },
    ];
    for (const item of items) {
      const cell = div("tdl-v2-orchestrator-footer__item");
      cell.append(
        el("span", "tdl-v2-orchestrator-footer__key", { text: item.key }),
        el("span", "tdl-v2-orchestrator-footer__value", {
          id: `tdl-v2-orch-footer-${item.id}`,
          text: item.value,
          "data-tone": "calm",
        }),
      );
      grid.appendChild(cell);
    }
    footer.appendChild(grid);
    return footer;
  }

  _startWaveform() {
    if (this._waveRaf != null) return;
    const tick = () => {
      this._wavePhase += 0.028;
      this._paintWaveform();
      this._waveRaf = window.requestAnimationFrame(tick);
    };
    this._waveRaf = window.requestAnimationFrame(tick);
  }

  _paintWaveform() {
    const canvas = /** @type {HTMLCanvasElement | null} */ (
      document.getElementById("tdl-v2-orchestrator-sparkline-canvas")
    );
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const wCss = canvas.offsetWidth || 120;
    const hCss = canvas.offsetHeight || 36;
    const w = Math.max(1, Math.floor(wCss * dpr));
    const h = Math.max(1, Math.floor(hCss * dpr));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }

    ctx.clearRect(0, 0, w, h);

    const state = this._store.getState();
    const thinking = Boolean(state.pipelineThinking || state.presence === "thinking");
    const tools = state.activeToolCount ?? 0;
    const amp = thinking || tools > 0 ? 0.32 : 0.12;
    const phase = this._wavePhase;

    ctx.strokeStyle = "rgba(239, 68, 68, 0.07)";
    ctx.lineWidth = 1 * dpr;
    ctx.beginPath();
    ctx.moveTo(0, h * 0.55);
    ctx.lineTo(w, h * 0.55);
    ctx.stroke();

    // Soft secondary harmonic — neural communication, not a CPU meter.
    ctx.strokeStyle = "rgba(239, 68, 68, 0.1)";
    ctx.lineWidth = 0.85 * dpr;
    ctx.beginPath();
    const softPoints = 40;
    for (let i = 0; i < softPoints; i += 1) {
      const t = i / (softPoints - 1);
      const x = t * w;
      const y = h * 0.55
        + Math.sin(phase * 0.45 + t * 4.4) * h * (amp * 0.55)
        + Math.cos(phase * 0.2 + t * 9.5) * h * (amp * 0.18);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    ctx.strokeStyle = thinking || tools > 0
      ? "rgba(239, 68, 68, 0.4)"
      : "rgba(239, 68, 68, 0.22)";
    ctx.lineWidth = 1.05 * dpr;
    ctx.beginPath();
    const points = 56;
    for (let i = 0; i < points; i += 1) {
      const t = i / (points - 1);
      const x = t * w;
      const y = h * 0.55
        + Math.sin(phase + t * 5.8) * h * amp
        + Math.sin(phase * 0.48 + t * 12.4) * h * (amp * 0.3)
        + Math.sin(phase * 1.1 + t * 2.2) * h * (amp * 0.08);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    const pulseCount = 4;
    for (let i = 0; i < pulseCount; i += 1) {
      const px = ((phase * 0.055 + i / pulseCount) % 1) * w;
      const py = h * 0.55 + Math.sin(phase + i * 1.7) * h * amp * 0.62;
      const r = (0.7 + (i % 2) * 0.35) * dpr;
      ctx.beginPath();
      ctx.fillStyle = `rgba(239, 68, 68, ${0.12 + (i % 3) * 0.05})`;
      ctx.arc(px, py, r, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  /** @deprecated Sparkline now driven by RAF; kept for pipeline subscribe callers. */
  _updateSparkline() {
    this._paintWaveform();
  }

  /**
   * Subtle idle vitality hooks — retained for cinematic CSS; hidden in Phase 6.
   */
  _idleLifeBlock() {
    const wrap = div("tdl-v2-orchestrator-idle-life");
    wrap.setAttribute("aria-hidden", "true");
    wrap.dataset.role = "idle-life";

    const scan = div("tdl-v2-orchestrator-idle-life__scan");
    wrap.appendChild(scan);

    const rows = [
      { label: "Field", bars: 8 },
      { label: "Pulse", bars: 6 },
    ];
    for (const row of rows) {
      const line = div("tdl-v2-orchestrator-idle-life__row");
      line.appendChild(el("span", "tdl-v2-orchestrator-idle-life__label", { text: row.label }));
      const bars = div("tdl-v2-orchestrator-idle-life__bars");
      for (let i = 0; i < row.bars; i += 1) {
        bars.appendChild(div("tdl-v2-orchestrator-idle-life__bar"));
      }
      line.appendChild(bars);
      line.appendChild(div("tdl-v2-orchestrator-idle-life__pulse"));
      wrap.appendChild(line);
    }

    wrap.appendChild(div("tdl-v2-orchestrator-idle-life__placeholder"));
    return wrap;
  }

  _sparklineBlock() {
    const wrap = div("tdl-v2-orchestrator-neural");
    wrap.id = "tdl-v2-orchestrator-neural";

    const spark = div("tdl-v2-orchestrator-sparkline");
    spark.appendChild(div("tdl-v2-orchestrator-sparkline__wave"));
    const pulses = div("tdl-v2-orchestrator-sparkline__pulses");
    pulses.setAttribute("aria-hidden", "true");
    for (let i = 0; i < 3; i += 1) {
      pulses.appendChild(div("tdl-v2-orchestrator-sparkline__pulse"));
    }
    spark.appendChild(pulses);
    spark.appendChild(
      el("canvas", "", {
        id: "tdl-v2-orchestrator-sparkline-canvas",
        "aria-hidden": "true",
      }),
    );

    wrap.append(
      spark,
      el("p", "tdl-v2-orchestrator-sparkline__caption", {
        id: "tdl-v2-orchestrator-neural-label",
        text: "Signal synaptique",
      }),
    );
    return wrap;
  }
}
