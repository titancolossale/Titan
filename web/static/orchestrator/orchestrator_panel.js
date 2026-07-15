/**
 * Titan Orchestrator Panel — Cognitive Orchestrator UI (Phase 24.1 · 24.2)
 *
 * Displays high-level plan steps, tools, and neural activity from API payloads.
 * Never exposes chain-of-thought or raw reasoning.
 */
(function (global) {
  "use strict";

  var NEURAL_LABELS = {
    idle: "Idle",
    listening: "Écoute",
    thinking: "Réflexion en cours…",
    deep_analysis: "Analyse profonde…",
    memory_retrieval: "Consultation mémoire…",
    planning: "Planification…",
    tool_usage: "Exécution outils…",
    trading_analysis: "Analyse trading…",
    browser_research: "Exploration en cours…",
    calendar_planning: "Planification agenda…",
    email_processing: "Communication…",
    voice_speaking: "Voix active",
  };

  var REGION_MAP = {
    idle: "core",
    listening: "communication",
    thinking: "core",
    deep_analysis: "core",
    memory_retrieval: "memory",
    planning: "planning",
    tool_usage: "tools",
    trading_analysis: "trading",
    browser_research: "browser",
    calendar_planning: "calendar",
    email_processing: "communication",
    voice_speaking: "communication",
  };

  var TOOL_ICONS = {
    obsidian: { icon: "O", label: "Obsidian" },
    browser: { icon: "B", label: "Browser" },
    memory: { icon: "M", label: "Memory" },
    calendar: { icon: "C", label: "Calendar" },
    trading: { icon: "T", label: "Trading" },
    email: { icon: "E", label: "Email" },
  };

  function OrchestratorPanel(options) {
    this.stateBadgeEl = options.stateBadgeEl || null;
    this.stateDetailEl = options.stateDetailEl || null;
    this.stepsEl = options.stepsEl || null;
    this.neuralLabelEl = options.neuralLabelEl || null;
    this.cognitiveValueEl = options.cognitiveValueEl || null;
    this.presenceValueEl = options.presenceValueEl || null;
    this.memoryValueEl = options.memoryValueEl || null;
    this.toolsValueEl = options.toolsValueEl || null;
    this.neuralLabelsRoot = options.neuralLabelsRoot || null;
    this.referenceShell = options.referenceShell || null;
    this._currentNeural = "idle";
    this._activeStepIndex = -1;
    this._activeTools = [];
  }

  OrchestratorPanel.prototype._formatNeural = function (state) {
    var key = (state || "idle").toLowerCase().replace(/[\s-]+/g, "_");
    return NEURAL_LABELS[key] || NEURAL_LABELS.idle;
  };

  OrchestratorPanel.prototype.setNeuralState = function (state) {
    this._currentNeural = state || "idle";
    var label = this._formatNeural(this._currentNeural);

    if (this.neuralLabelEl) {
      this.neuralLabelEl.textContent = label;
    }
    if (this.cognitiveValueEl) {
      this.cognitiveValueEl.textContent = label.replace(/…$/, "");
    }
    if (this.stateBadgeEl) {
      this.stateBadgeEl.textContent = label.replace(/…$/, "");
    }

    this._highlightNeuralRegion(REGION_MAP[this._currentNeural] || "core");
  };

  OrchestratorPanel.prototype.setPresence = function (text) {
    if (this.presenceValueEl) {
      this.presenceValueEl.textContent = text || "Élevée";
    }
  };

  OrchestratorPanel.prototype.setStateDetail = function (text) {
    if (this.stateDetailEl) {
      this.stateDetailEl.textContent = text || "Titan est présent et attentif.";
    }
  };

  OrchestratorPanel.prototype.updateStatus = function (status, toolsPayload, memoryPayload) {
    if (status) {
      this.setPresence(status.status === "ready" ? "Élevée" : "Stable");
      this.setStateDetail(
        status.mission && status.mission.active
          ? "Exécution du plan en cours…"
          : "Titan est présent et attentif."
      );
    }

    if (memoryPayload) {
      var users = (memoryPayload.long_term_users || []).length;
      var notes = memoryPayload.short_term_notes_count || 0;
      if (this.memoryValueEl) {
        this.memoryValueEl.textContent = users + " profil · " + notes + " note(s)";
      }
    }

    if (toolsPayload) {
      var count = (toolsPayload.tools || []).length;
      if (this.toolsValueEl) {
        this.toolsValueEl.textContent = count + " outil(s)";
      }
    }
  };

  OrchestratorPanel.prototype._renderStep = function (step, index, total, isLast) {
    var item = document.createElement("li");
    var status = "pending";
    if (isLast) {
      status = "active";
    } else if (index < total - 1) {
      status = "done";
    }

    item.className = "tdl-orchestrator-steps__item";
    if (status === "active") {
      item.classList.add("tdl-orchestrator-steps__item--active");
    } else if (status === "done") {
      item.classList.add("tdl-orchestrator-steps__item--done");
    }

    var num = document.createElement("span");
    num.className = "tdl-orchestrator-steps__num";
    num.textContent = String(index + 1);

    var label = document.createElement("span");
    label.className = "tdl-orchestrator-steps__label";
    label.textContent = step.label || step.phase || "Étape " + (index + 1);

    var statusEl = document.createElement("span");
    statusEl.className = "tdl-orchestrator-steps__status";
    if (status === "done") {
      statusEl.textContent = "Terminé";
    } else if (status === "active") {
      statusEl.textContent = "Actif";
    } else {
      statusEl.textContent = "En attente";
    }

    item.appendChild(num);
    item.appendChild(label);
    item.appendChild(statusEl);
    return item;
  };

  OrchestratorPanel.prototype.ingestProgress = function (progress) {
    if (!this.stepsEl) {
      return;
    }

    if (!progress || !progress.length) {
      this.stepsEl.innerHTML =
        '<li class="tdl-orchestrator-steps__item tdl-orchestrator-steps__item--idle">En attente de demande…</li>';
      this._activeStepIndex = -1;
      this._syncTools([]);
      return;
    }

    this.stepsEl.innerHTML = "";
    var lastNeural = "idle";
    var toolSet = {};

    progress.forEach(function (step, index) {
      var isLast = index === progress.length - 1;
      this.stepsEl.appendChild(this._renderStep(step, index, progress.length, isLast));

      if (step.neural_state) {
        lastNeural = step.neural_state;
      }
      if (step.tool) {
        toolSet[step.tool] = true;
      }
    }, this);

    this._activeStepIndex = progress.length - 1;
    this.setNeuralState(lastNeural);
    this.setStateDetail("Exécution du plan en cours…");

    var tools = Object.keys(toolSet).map(function (key) {
      return TOOL_ICONS[key] || { icon: key.slice(0, 1).toUpperCase(), label: key };
    });
    tools.forEach(function (t) { t.name = t.label; });
    this._syncTools(tools);
  };

  OrchestratorPanel.prototype._syncTools = function (tools) {
    this._activeTools = tools;
    if (this.referenceShell) {
      this.referenceShell.updateOrchestratorTools(tools);
    }
  };

  OrchestratorPanel.prototype.beginThinking = function () {
    this.setNeuralState("thinking");
    this.setStateDetail("Exécution du plan en cours…");

    if (this.stepsEl) {
      this.stepsEl.innerHTML = "";
      var item = this._renderStep(
        { label: "Compréhension de la demande…", phase: "thinking" },
        0,
        1,
        true
      );
      this.stepsEl.appendChild(item);
    }
  };

  OrchestratorPanel.prototype.resetIdle = function () {
    this.setNeuralState("idle");
    this.setStateDetail("Titan est présent et attentif.");
    this.ingestProgress([]);
  };

  var PERMANENT_IDLE = {
    planning: true,
    trading: true,
    calendar: true,
  };

  OrchestratorPanel.prototype._highlightNeuralRegion = function (region) {
    if (!this.neuralLabelsRoot) {
      return;
    }

    this.neuralLabelsRoot.querySelectorAll(".tdl-neural-module").forEach(function (el) {
      var elRegion = el.getAttribute("data-region");
      if (elRegion === "core") {
        return;
      }
      if (PERMANENT_IDLE[elRegion]) {
        return;
      }
      var isActive = elRegion === region;
      el.classList.toggle("tdl-neural-module--active", isActive);
      el.classList.toggle("tdl-neural-module--idle", !isActive);
      var statusEl = el.querySelector(".tdl-neural-module__status");
      if (statusEl) {
        statusEl.textContent = isActive ? "ACTIF" : "IDLE";
      }
    });

    var core = this.neuralLabelsRoot.querySelector('[data-region="core"]');
    if (core) {
      core.classList.add("tdl-neural-module--active");
    }
  };

  global.TitanOrchestratorPanel = OrchestratorPanel;
})(window);
