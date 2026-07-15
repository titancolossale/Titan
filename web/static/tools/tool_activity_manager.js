/**
 * Titan Tool Activity Manager — event-driven tool experience hub (Phase 17.7)
 *
 * Normalizes tool lifecycle events and fans out to timeline, progress cards,
 * presence, and neural hooks. Future tools register once and plug in automatically.
 */
(function (global) {
  "use strict";

  var EVENTS = {
    TURN_BEGIN: "turn_begin",
    TURN_END: "turn_end",
    STATUS_LINE: "status_line",
    TOOL_START: "tool_start",
    TOOL_PROGRESS: "tool_progress",
    TOOL_COMPLETE: "tool_complete",
    TOOL_ERROR: "tool_error",
  };

  /**
   * User-facing tool registry — never expose raw implementation names in UI.
   * category drives neural wave patterns via PresenceController.
   */
  var TOOL_REGISTRY = {
    browser: {
      category: "browser",
      icon: "◎",
      title: "Exploration web",
      startLine: "Navigation web…",
      waveStyle: "distributed",
      cognitiveState: "exploration",
      steps: ["Navigation web", "Recherche", "Analyse", "Synthèse"],
    },
    memory: {
      category: "memory",
      icon: "◈",
      title: "Mémoire",
      startLine: "Recherche en mémoire…",
      waveStyle: "central",
      steps: ["Recherche…", "Correspondances trouvées…", "Lecture des souvenirs…", "Terminé."],
    },
    obsidian: {
      category: "memory",
      icon: "◈",
      title: "Consultation d'Obsidian",
      startLine: "Consultation d'Obsidian…",
      waveStyle: "central",
      steps: ["Recherche…", "Lecture…", "Mise à jour…", "Terminé."],
    },
    calendar: {
      category: "calendar",
      icon: "◷",
      title: "Agenda",
      startLine: "Lecture de l'agenda…",
      waveStyle: "circular",
      steps: ["Ouverture…", "Lecture des événements…", "Analyse…", "Terminé."],
    },
    trading: {
      category: "trading",
      icon: "◆",
      title: "Marchés",
      startLine: "Analyse des marchés…",
      waveStyle: "sharp",
      steps: ["Connexion…", "Lecture des données…", "Analyse…", "Terminé."],
    },
    tradingview: {
      category: "trading",
      icon: "◆",
      title: "TradingView",
      startLine: "Consultation de TradingView…",
      waveStyle: "sharp",
      steps: ["Chargement…", "Lecture du graphique…", "Analyse…", "Terminé."],
    },
    email: {
      category: "email",
      icon: "◇",
      title: "E-mail",
      startLine: "Lecture des e-mails…",
      waveStyle: "distributed",
      steps: ["Connexion…", "Lecture…", "Tri…", "Terminé."],
    },
    time: {
      category: "default",
      icon: "◉",
      title: "Horloge",
      startLine: "Vérification de l'heure…",
      waveStyle: "default",
      steps: ["Lecture…", "Terminé."],
    },
    planning: {
      category: "planning",
      icon: "◐",
      title: "Planification",
      startLine: "Planification en cours…",
      waveStyle: "default",
      steps: ["Analyse…", "Structuration…", "Terminé."],
    },
    default: {
      category: "default",
      icon: "◉",
      title: "Outil",
      startLine: "Action en cours…",
      waveStyle: "default",
      steps: ["Préparation…", "Exécution…", "Terminé."],
    },
  };

  function normalizeToolKey(raw) {
    if (!raw) {
      return "default";
    }
    var key = String(raw).toLowerCase().replace(/[^a-z0-9_]/g, "_");
    if (TOOL_REGISTRY[key]) {
      return key;
    }
    if (key.indexOf("obsidian") !== -1 || key.indexOf("vault") !== -1 || key.indexOf("note") !== -1) {
      return "obsidian";
    }
    if (key.indexOf("browser") !== -1 || key.indexOf("web") !== -1) {
      return "browser";
    }
    if (key.indexOf("calendar") !== -1 || key.indexOf("agenda") !== -1) {
      return "calendar";
    }
    if (key.indexOf("trad") !== -1 || key.indexOf("market") !== -1) {
      return "trading";
    }
    if (key.indexOf("mail") !== -1 || key.indexOf("email") !== -1) {
      return "email";
    }
    if (key.indexOf("memory") !== -1 || key.indexOf("memo") !== -1) {
      return "memory";
    }
    if (key.indexOf("time") !== -1) {
      return "time";
    }
    return "default";
  }

  function ToolActivityManager(options) {
    this.options = options || {};
    this.getPresenceController = options.getPresenceController || function () {
      return null;
    };
    this._listeners = {};
    this._turnId = null;
    this._activeRuns = {};
    this._runCounter = 0;
  }

  ToolActivityManager.EVENTS = EVENTS;
  ToolActivityManager.TOOL_REGISTRY = TOOL_REGISTRY;

  ToolActivityManager.prototype.on = function (eventName, callback) {
    if (!this._listeners[eventName]) {
      this._listeners[eventName] = [];
    }
    this._listeners[eventName].push(callback);
    return this;
  };

  ToolActivityManager.prototype.off = function (eventName, callback) {
    var list = this._listeners[eventName];
    if (!list) {
      return;
    }
    var idx = list.indexOf(callback);
    if (idx !== -1) {
      list.splice(idx, 1);
    }
  };

  ToolActivityManager.prototype._emit = function (eventName, payload) {
    var list = this._listeners[eventName];
    if (!list) {
      return;
    }
    var event = {
      type: eventName,
      turnId: this._turnId,
      timestamp: Date.now(),
      payload: payload || {},
    };
    for (var i = 0; i < list.length; i++) {
      try {
        list[i](event);
      } catch (_err) {
        /* subscriber errors must not break tool flow */
      }
    }
  };

  ToolActivityManager.prototype.getRegistryEntry = function (toolKey) {
    var key = normalizeToolKey(toolKey);
    return TOOL_REGISTRY[key] || TOOL_REGISTRY.default;
  };

  ToolActivityManager.prototype.beginTurn = function (turnId) {
    this._turnId = turnId || "turn-" + Date.now();
    this._activeRuns = {};
    this._emit(EVENTS.TURN_BEGIN, { turnId: this._turnId });
    return this._turnId;
  };

  ToolActivityManager.prototype.endTurn = function () {
    var turnId = this._turnId;
    this._emit(EVENTS.TURN_END, { turnId: turnId });
    this._turnId = null;
    this._activeRuns = {};
  };

  ToolActivityManager.prototype._nextRunId = function () {
    this._runCounter += 1;
    return "run-" + this._runCounter;
  };

  ToolActivityManager.prototype._resolveRun = function (payload) {
    var runId = payload && payload.run_id ? payload.run_id : null;
    if (runId && this._activeRuns[runId]) {
      return runId;
    }
    if (runId) {
      return runId;
    }
    return this._nextRunId();
  };

  ToolActivityManager.prototype._buildRunPayload = function (toolKey, runId, extra) {
    var entry = this.getRegistryEntry(toolKey);
    var data = extra || {};
    return {
      runId: runId,
      tool: entry.category,
      toolKey: normalizeToolKey(toolKey),
      icon: data.icon || entry.icon,
      title: data.title || entry.title,
      waveStyle: entry.waveStyle,
      steps: data.steps || entry.steps,
      action: data.action || entry.startLine,
      statusLine: data.status_line || data.statusLine || entry.startLine,
      success: data.success !== false,
      sources: data.sources || [],
      exploration: data.exploration || entry.cognitiveState === "exploration",
      cognitiveState: data.cognitive_state || data.cognitiveState || entry.cognitiveState,
    };
  };

  ToolActivityManager.prototype.emitToolStart = function (toolKey, payload) {
    var runId = this._resolveRun(payload);
    var run = this._buildRunPayload(toolKey, runId, payload);
    run.phase = "start";
    this._activeRuns[runId] = run;

    this._emit(EVENTS.STATUS_LINE, { text: run.statusLine, runId: runId });
    this._emit(EVENTS.TOOL_START, run);
    this._syncPresence("tool_start", run);
    return runId;
  };

  ToolActivityManager.prototype.emitToolProgress = function (toolKey, action, payload) {
    var runId = this._resolveRun(payload);
    var run = this._activeRuns[runId] || this._buildRunPayload(toolKey, runId, payload);
    run.phase = "progress";
    run.action = action || run.action;
    this._activeRuns[runId] = run;

    this._emit(EVENTS.STATUS_LINE, { text: run.action, runId: runId });
    this._emit(EVENTS.TOOL_PROGRESS, run);
    this._syncPresence("tool_progress", run);
  };

  ToolActivityManager.prototype.emitToolComplete = function (toolKey, payload) {
    var runId = this._resolveRun(payload);
    var run = this._activeRuns[runId] || this._buildRunPayload(toolKey, runId, payload);
    run.phase = "complete";
    run.action = "Terminé.";
    run.success = payload && payload.success === false ? false : true;
    this._activeRuns[runId] = run;

    this._emit(EVENTS.TOOL_COMPLETE, run);
    this._syncPresence("tool_complete", run);
    delete this._activeRuns[runId];
  };

  ToolActivityManager.prototype.emitToolError = function (toolKey, message, payload) {
    var runId = this._resolveRun(payload);
    var run = this._activeRuns[runId] || this._buildRunPayload(toolKey, runId, payload);
    run.phase = "error";
    run.action = message || "Interrompu.";
    run.success = false;
    this._activeRuns[runId] = run;

    this._emit(EVENTS.TOOL_ERROR, run);
    this._syncPresence("tool_error", run);
    delete this._activeRuns[runId];
  };

  ToolActivityManager.prototype._syncPresence = function (phase, run) {
    var presence = this.getPresenceController();
    if (!presence || !presence.handleToolActivity) {
      return;
    }
    presence.handleToolActivity({
      phase: phase,
      tool: run.tool,
      toolKey: run.toolKey,
      waveStyle: run.waveStyle,
      action: run.action,
      runId: run.runId,
    });
  };

  /**
   * Ingest sanitized activity records from the API (no raw JSON shown to user).
   */
  ToolActivityManager.prototype.ingest = function (record) {
    if (!record) {
      return;
    }
    var toolKey = record.tool || record.tool_key || record.toolKey || "default";
    var runId = record.run_id || record.runId;

    if (record.state === "error" || record.success === false) {
      this.emitToolError(toolKey, record.action || "Action interrompue.", { run_id: runId });
      return;
    }

    var steps = record.steps || [];
    var startPayload = {
      run_id: runId,
      title: record.title,
      icon: record.icon,
      status_line: record.status_line || record.statusLine,
      steps: steps,
      sources: record.sources || [],
      exploration: record.exploration,
      cognitive_state: record.cognitive_state,
    };

    this.emitToolStart(toolKey, startPayload);

    if (record.sources && record.sources.length && global.TitanExplorationCards) {
      var cardsLayer = document.getElementById("memory-cards-layer");
      if (cardsLayer) {
        var explorer = new global.TitanExplorationCards({ layerEl: cardsLayer });
        explorer.show(record.sources.slice(0, 4));
      }
    }

    if (steps.length > 1) {
      for (var i = 0; i < steps.length - 1; i++) {
        if (steps[i] !== "Terminé.") {
          this.emitToolProgress(toolKey, steps[i], { run_id: runId });
        }
      }
    } else if (record.action) {
      this.emitToolProgress(toolKey, record.action, { run_id: runId });
    }

    if (record.state === "complete" || record.state === "completed" || record.success !== false) {
      this.emitToolComplete(toolKey, { run_id: runId, success: record.success });
    }
  };

  /**
   * Replay API tool_activity with brief delays — runs parallel to text streaming.
   */
  ToolActivityManager.prototype.ingestAnimated = function (records, options) {
    var self = this;
    var opts = options || {};
    var stepDelay = opts.stepDelayMs || 120;
    var list = records || [];

    if (!list.length) {
      return Promise.resolve();
    }

    return new Promise(function (resolve) {
      var index = 0;

      function next() {
        if (index >= list.length) {
          resolve();
          return;
        }
        var record = list[index];
        index += 1;
        self.ingest(record);
        setTimeout(next, stepDelay * (record.steps ? record.steps.length : 1));
      }

      next();
    });
  };

  ToolActivityManager.prototype.registerTool = function (key, definition) {
    TOOL_REGISTRY[key] = Object.assign({}, TOOL_REGISTRY.default, definition || {});
  };

  global.TitanToolActivityManager = ToolActivityManager;
})(window);
