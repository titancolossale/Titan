/**
 * Titan Memory Activity Manager — event-driven memory experience hub (Phase 17.9)
 *
 * Titan never "loads memory" — Titan remembers. Orchestrates status lines,
 * neural visualization, and floating cards synchronized with tool experience.
 */
(function (global) {
  "use strict";

  var EVENTS = global.TitanMemoryEvents
    ? global.TitanMemoryEvents.EVENTS
    : {
        TURN_BEGIN: "memory:turn_begin",
        TURN_END: "memory:turn_end",
        SEARCH_START: "memory:search_start",
        RECALL: "memory:recall",
        COMPLETE: "memory:complete",
        STATUS_LINE: "memory:status_line",
      };

  /**
   * User-facing memory source registry — thematic labels only.
   */
  var MEMORY_REGISTRY = {
    conversation: {
      title: "Conversation précédente",
      icon: "○",
      searchLine: "Souvenirs de la conversation…",
      recallLine: "Fil de la conversation…",
      waveStyle: "deep_central",
    },
    long_term: {
      title: "Souvenirs permanents",
      icon: "◈",
      searchLine: "Souvenirs en éveil…",
      recallLine: "Souvenirs retrouvés…",
      waveStyle: "slow",
    },
    obsidian: {
      title: "Notes Obsidian",
      icon: "◇",
      searchLine: "Consultation des notes…",
      recallLine: "Notes en mémoire…",
      waveStyle: "geometric",
    },
    browser: {
      title: "Recherche navigateur",
      icon: "◎",
      searchLine: "Parcours récent…",
      recallLine: "Contexte web…",
      waveStyle: "distributed",
    },
    calendar: {
      title: "Agenda",
      icon: "◷",
      searchLine: "Événements en mémoire…",
      recallLine: "Rythme du calendrier…",
      waveStyle: "circular",
    },
    trading: {
      title: "Marchés",
      icon: "◆",
      searchLine: "Stratégies en mémoire…",
      recallLine: "Contexte trading…",
      waveStyle: "sharp",
    },
    project: {
      title: "Projet",
      icon: "◐",
      searchLine: "Contexte du projet…",
      recallLine: "Projet actif…",
      waveStyle: "default",
    },
    default: {
      title: "Souvenirs",
      icon: "◈",
      searchLine: "Souvenirs en éveil…",
      recallLine: "Souvenirs intégrés.",
      waveStyle: "central",
    },
  };

  function normalizeSource(raw) {
    if (!raw) {
      return "long_term";
    }
    var key = String(raw).toLowerCase().replace(/[^a-z0-9_]/g, "_");
    if (MEMORY_REGISTRY[key]) {
      return key;
    }
    if (key.indexOf("obsidian") !== -1 || key.indexOf("vault") !== -1) {
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
    if (key.indexOf("conversation") !== -1 || key.indexOf("dialogue") !== -1) {
      return "conversation";
    }
    if (key.indexOf("project") !== -1 || key.indexOf("projet") !== -1) {
      return "project";
    }
    return "long_term";
  }

  function MemoryActivityManager(options) {
    this.options = options || {};
    this.bus = options.bus || new global.TitanMemoryEvents.MemoryEventBus();
    this.getToolActivityManager = options.getToolActivityManager || function () {
      return null;
    };
    this._turnId = null;
    this._statusEl = options.statusLineEl || null;
    this._statusHideTimer = null;
    this._anticipatoryRecall = false;
  }

  MemoryActivityManager.EVENTS = EVENTS;
  MemoryActivityManager.MEMORY_REGISTRY = MEMORY_REGISTRY;

  MemoryActivityManager.prototype.getRegistryEntry = function (sourceKey) {
    return MEMORY_REGISTRY[normalizeSource(sourceKey)] || MEMORY_REGISTRY.default;
  };

  MemoryActivityManager.prototype.beginTurn = function (turnId) {
    this._turnId = turnId || "mem-turn-" + Date.now();
    this.bus.emit(EVENTS.TURN_BEGIN, { turnId: this._turnId });
    return this._turnId;
  };

  MemoryActivityManager.prototype.endTurn = function () {
    var turnId = this._turnId;
    this.bus.emit(EVENTS.TURN_END, { turnId: turnId });
    this._turnId = null;
    this._anticipatoryRecall = false;
    this._hideStatusLine();
  };

  MemoryActivityManager.prototype.beginRecall = function (options) {
    var opts = options || {};
    var source = normalizeSource(opts.source || "long_term");
    var entry = this.getRegistryEntry(source);

    this._anticipatoryRecall = true;

    this._showStatusLine(entry.searchLine);
    this.bus.emit(EVENTS.SEARCH_START, {
      turnId: this._turnId,
      source: source,
      title: entry.title,
      icon: entry.icon,
      waveStyle: entry.waveStyle,
      statusLine: entry.searchLine,
    });

    this._syncToolStatus(entry.searchLine);
  };

  MemoryActivityManager.prototype.emitSearch = function (record) {
    var source = normalizeSource(record.source || record.source_key);
    var entry = this.getRegistryEntry(source);
    var statusLine = record.status_line || record.statusLine || entry.searchLine;

    this._showStatusLine(statusLine);
    this.bus.emit(EVENTS.SEARCH_START, {
      turnId: this._turnId,
      runId: record.run_id || record.runId,
      source: source,
      title: record.title || entry.title,
      icon: record.icon || entry.icon,
      waveStyle: record.wave_style || record.waveStyle || entry.waveStyle,
      statusLine: statusLine,
    });
    this._syncToolStatus(statusLine);
  };

  MemoryActivityManager.prototype.emitRecall = function (record) {
    var source = normalizeSource(record.source || "long_term");
    var entry = this.getRegistryEntry(source);
    var statusLine = record.status_line || record.statusLine || entry.recallLine;

    this._showStatusLine(statusLine);
    this.bus.emit(EVENTS.RECALL, {
      turnId: this._turnId,
      runId: record.run_id || record.runId,
      source: source,
      title: record.title || entry.title,
      icon: record.icon || entry.icon,
      waveStyle: record.wave_style || record.waveStyle || entry.waveStyle,
      statusLine: statusLine,
      cards: record.cards || [],
      matchCount: record.match_count || record.matchCount || 0,
      hasMatches: record.has_matches !== false && record.hasMatches !== false,
    });
    this._syncToolStatus(statusLine);
  };

  MemoryActivityManager.prototype.emitComplete = function (record) {
    var source = normalizeSource(record && record.source);
    var entry = this.getRegistryEntry(source);

    this.bus.emit(EVENTS.COMPLETE, {
      turnId: this._turnId,
      source: source,
      success: !record || record.success !== false,
    });

    this._hideStatusLine(400);
    this._syncToolStatus(entry.recallLine);
  };

  MemoryActivityManager.prototype._showStatusLine = function (text) {
    if (!this._statusEl || !text) {
      return;
    }
    this._statusEl.textContent = text;
    this._statusEl.hidden = false;
    requestAnimationFrame(
      function (el) {
        el.classList.add("tdl-memory-status-line--visible");
      }.bind(null, this._statusEl)
    );

    if (this._statusHideTimer) {
      clearTimeout(this._statusHideTimer);
    }

    this.bus.emit(EVENTS.STATUS_LINE, { text: text });
  };

  MemoryActivityManager.prototype._hideStatusLine = function (delayMs) {
    var self = this;
    if (!this._statusEl) {
      return;
    }

    if (this._statusHideTimer) {
      clearTimeout(this._statusHideTimer);
    }

    this._statusHideTimer = setTimeout(function () {
      self._statusEl.classList.remove("tdl-memory-status-line--visible");
      setTimeout(function () {
        if (!self._statusEl.classList.contains("tdl-memory-status-line--visible")) {
          self._statusEl.hidden = true;
        }
      }, 320);
    }, delayMs || 0);
  };

  MemoryActivityManager.prototype._syncToolStatus = function (text) {
    var tools = this.getToolActivityManager();
    if (!tools || !tools._emit) {
      return;
    }
    tools._emit(tools.constructor.EVENTS.STATUS_LINE, { text: text, source: "memory" });
  };

  MemoryActivityManager.prototype.ingest = function (record) {
    if (!record) {
      return;
    }

    var phase = record.phase || "search";
    if (phase === "search" && this._anticipatoryRecall) {
      return;
    }
    if (phase === "search") {
      this.emitSearch(record);
      return;
    }
    if (phase === "recall") {
      this.emitRecall(record);
      return;
    }
    if (phase === "complete" || record.state === "complete") {
      this.emitComplete(record);
    }
  };

  MemoryActivityManager.prototype.ingestAnimated = function (records, options) {
    var self = this;
    var opts = options || {};
    var stepDelay = opts.stepDelayMs || 160;
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
        var delay = stepDelay;
        if (record.phase === "recall" && record.cards && record.cards.length) {
          delay = stepDelay * 1.4;
        }
        setTimeout(next, delay);
      }

      next();
    });
  };

  MemoryActivityManager.prototype.registerSource = function (key, definition) {
    MEMORY_REGISTRY[key] = Object.assign({}, MEMORY_REGISTRY.default, definition || {});
  };

  global.TitanMemoryActivityManager = MemoryActivityManager;
})(window);
