/**
 * Titan Reference Shell — Official UI widgets (Phase 24.2)
 *
 * Footer telemetry, presence waveform, sparkline, status cards.
 * Frontend-only; reads existing API payloads and presence engine.
 */
(function (global) {
  "use strict";

  var RING_CIRCUMFERENCE = 2 * Math.PI * 18;

  function ReferenceShell(options) {
    this.getNeuralEngine = options.getNeuralEngine || function () { return null; };
    this.getPresenceController = options.getPresenceController || function () { return null; };
    this.getToolActivityManager = options.getToolActivityManager || function () { return null; };
    this.apiFetch = options.apiFetch || null;

    this.fpsEl = document.getElementById("telemetry-fps");
    this.clockEl = document.getElementById("telemetry-clock");
    this.brainEl = document.getElementById("telemetry-brain");
    this.memoryEl = document.getElementById("telemetry-memory");
    this.toolsEl = document.getElementById("telemetry-tools");
    this.reflectionEl = document.getElementById("telemetry-reflection");
    this.ringFill = document.getElementById("presence-ring-fill");
    this.ringValue = document.getElementById("presence-ring-value");
    this.presenceCardValue = document.getElementById("presence-card-value");
    this.recentMemoryBody = document.getElementById("card-recent-memory-body");
    this.obsidianBody = document.getElementById("card-obsidian-body");
    this.browserBody = document.getElementById("card-browser-body");
    this.chatZone = document.getElementById("chat-zone");
    this.waveCanvas = document.getElementById("presence-waveform-canvas");
    this.sparkCanvas = document.getElementById("orchestrator-sparkline-canvas");
    this.neuralModulesRoot = document.querySelector(".tdl-neural-labels");
    this.topbarPresence = document.getElementById("topbar-presence");

    this._waveCtx = this.waveCanvas ? this.waveCanvas.getContext("2d") : null;
    this._sparkCtx = this.sparkCanvas ? this.sparkCanvas.getContext("2d") : null;
    this._sparkHistory = [];
    this._frameTimes = [];
    this._lastFpsUpdate = 0;
    this._animId = null;
    this._wavePhase = 0;
    this._activeTools = 0;
    this._concentration = 0.72;
    this._reflectionLabel = "Calme";
  }

  ReferenceShell.prototype.init = function () {
    this._resizeCanvases();
    window.addEventListener("resize", this._resizeCanvases.bind(this));
    this._startLoop();
    this._startClock();
    this._observeChatMessages();
  };

  ReferenceShell.prototype._resizeCanvases = function () {
    if (this.waveCanvas && this._waveCtx) {
      var wRect = this.waveCanvas.parentElement.getBoundingClientRect();
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      this.waveCanvas.width = Math.floor(wRect.width * dpr);
      this.waveCanvas.height = Math.floor(wRect.height * dpr);
      this._waveCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    if (this.sparkCanvas && this._sparkCtx) {
      var sRect = this.sparkCanvas.parentElement.getBoundingClientRect();
      var dpr2 = Math.min(window.devicePixelRatio || 1, 2);
      this.sparkCanvas.width = Math.floor(sRect.width * dpr2);
      this.sparkCanvas.height = Math.floor(sRect.height * dpr2);
      this._sparkCtx.setTransform(dpr2, 0, 0, dpr2, 0, 0);
    }
  };

  ReferenceShell.prototype._startClock = function () {
    var self = this;
    function tick() {
      if (self.clockEl) {
        var now = new Date();
        self.clockEl.textContent =
          String(now.getHours()).padStart(2, "0") + ":" +
          String(now.getMinutes()).padStart(2, "0") + ":" +
          String(now.getSeconds()).padStart(2, "0");
      }
      setTimeout(tick, 1000);
    }
    tick();
  };

  ReferenceShell.prototype._observeChatMessages = function () {
    var messagesEl = document.getElementById("chat-messages");
    if (!messagesEl || !this.chatZone) {
      return;
    }
    var observer = new MutationObserver(function () {
      var hasMessages = messagesEl.children.length > 0;
      this.chatZone.classList.toggle("tdl-ref-chat--has-messages", hasMessages);
    }.bind(this));
    observer.observe(messagesEl, { childList: true });
  };

  ReferenceShell.prototype._startLoop = function () {
    var self = this;
    var last = performance.now();

    function frame(now) {
      var dt = now - last;
      last = now;
      self._frameTimes.push(dt);
      if (self._frameTimes.length > 30) {
        self._frameTimes.shift();
      }

      if (now - self._lastFpsUpdate > 500) {
        self._lastFpsUpdate = now;
        var avg = self._frameTimes.reduce(function (a, b) { return a + b; }, 0) / self._frameTimes.length;
        if (self.fpsEl) {
          self.fpsEl.textContent = String(Math.round(1000 / Math.max(avg, 1)));
        }
      }

      self._updatePresenceMetrics();
      self._drawWaveform(now);
      self._drawSparkline(now);
      self._animId = requestAnimationFrame(frame);
    }

    this._animId = requestAnimationFrame(frame);
  };

  ReferenceShell.prototype._updatePresenceMetrics = function () {
    var presence = this.getPresenceController();
    var profile = presence && presence.engine ? presence.engine.getProfile() : null;
    var activity = profile ? profile.activityTarget || 0.2 : 0.2;
    var thinking = profile ? profile.thinkingTarget || 0 : 0;

    this._concentration = Math.min(0.98, 0.55 + activity * 0.35 + thinking * 0.25);
    var concentrationPct = Math.round(this._concentration * 100);

    if (this.ringFill) {
      var offset = RING_CIRCUMFERENCE * (1 - this._concentration);
      this.ringFill.setAttribute("stroke-dashoffset", String(offset));
    }
    if (this.ringValue) {
      this.ringValue.textContent = concentrationPct + "%";
    }
    if (this.presenceCardValue) {
      this.presenceCardValue.textContent =
        thinking > 0.35 ? "Intense" : activity > 0.45 ? "Élevée" : "Stable";
    }

    if (this.reflectionEl) {
      if (thinking > 0.5) {
        this._reflectionLabel = "Profonde";
      } else if (thinking > 0.2) {
        this._reflectionLabel = "Active";
      } else if (activity > 0.4) {
        this._reflectionLabel = "Exploration";
      } else {
        this._reflectionLabel = "Calme";
      }
      this.reflectionEl.textContent = this._reflectionLabel;
    }

    if (this.topbarPresence) {
      if (thinking > 0.35) {
        this.topbarPresence.textContent = "Réflexion — En cours";
      } else if (activity > 0.45) {
        this.topbarPresence.textContent = "Exploration — Actif";
      } else {
        this.topbarPresence.textContent = "Présent — En attente";
      }
    }

    this._sparkHistory.push(activity + thinking * 0.6);
    if (this._sparkHistory.length > 80) {
      this._sparkHistory.shift();
    }
  };

  ReferenceShell.prototype._drawWaveform = function (now) {
    if (!this._waveCtx || !this.waveCanvas) {
      return;
    }
    var ctx = this._waveCtx;
    var w = this.waveCanvas.parentElement.clientWidth;
    var h = this.waveCanvas.parentElement.clientHeight;
    var presence = this.getPresenceController();
    var profile = presence && presence.engine ? presence.engine.getProfile() : null;
    var amp = profile ? 0.35 + (profile.activityTarget || 0.15) * 0.5 : 0.4;

    this._wavePhase += 0.04 + amp * 0.06;
    ctx.clearRect(0, 0, w, h);

    var mid = h * 0.5;
    ctx.beginPath();
    for (var x = 0; x <= w; x += 2) {
      var t = (x / w) * Math.PI * 4 + this._wavePhase;
      var y = mid + Math.sin(t) * amp * h * 0.35 +
        Math.sin(t * 2.3 + 1.2) * amp * h * 0.12;
      if (x === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.strokeStyle = "rgba(255, 26, 26, 0.75)";
    ctx.lineWidth = 1.2;
    ctx.shadowColor = "rgba(255, 0, 0, 0.5)";
    ctx.shadowBlur = 6;
    ctx.stroke();
    ctx.shadowBlur = 0;
  };

  ReferenceShell.prototype._drawSparkline = function () {
    if (!this._sparkCtx || !this.sparkCanvas || this._sparkHistory.length < 2) {
      return;
    }
    var ctx = this._sparkCtx;
    var w = this.sparkCanvas.parentElement.clientWidth;
    var h = this.sparkCanvas.parentElement.clientHeight;
    var data = this._sparkHistory;

    ctx.clearRect(0, 0, w, h);
    ctx.beginPath();
    for (var i = 0; i < data.length; i++) {
      var x = (i / (data.length - 1)) * w;
      var y = h - data[i] * h * 0.85 - h * 0.08;
      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.strokeStyle = "rgba(255, 40, 40, 0.85)";
    ctx.lineWidth = 1.4;
    ctx.stroke();

    var lastX = w;
    var lastY = h - data[data.length - 1] * h * 0.85 - h * 0.08;
    ctx.beginPath();
    ctx.arc(lastX - 1, lastY, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255, 60, 60, 0.9)";
    ctx.fill();
  };

  ReferenceShell.prototype.updateFromStatus = function (status, toolsPayload, memoryPayload) {
    if (toolsPayload) {
      var tools = toolsPayload.tools || [];
      this._activeTools = tools.length;
      if (this.toolsEl) {
        this.toolsEl.textContent = this._activeTools + " actifs";
      }
      if (document.getElementById("tools-float-value")) {
        document.getElementById("tools-float-value").textContent = String(this._activeTools);
      }
    }

    if (memoryPayload) {
      var users = (memoryPayload.long_term_users || []).length;
      var notes = memoryPayload.short_term_notes_count || 0;
      if (this.memoryEl) {
        this.memoryEl.textContent = users + " profil · " + notes + " note(s)";
      }
      if (document.getElementById("memory-float-value")) {
        document.getElementById("memory-float-value").textContent = users + " · " + notes;
      }
    }

    if (status && status.state && status.state.last_messages) {
      this._renderRecentMemory(status.state.last_messages);
    }
  };

  ReferenceShell.prototype._renderRecentMemory = function (messages) {
    if (!this.recentMemoryBody) {
      return;
    }
    var list = Array.isArray(messages) ? messages.slice(0, 3) : [];
    if (!list.length) {
      this.recentMemoryBody.innerHTML = '<div class="tdl-ref-status-card__line">Aucune activité récente</div>';
      return;
    }
    this.recentMemoryBody.innerHTML = "";
    list.forEach(function (msg, i) {
      var line = document.createElement("div");
      line.className = "tdl-ref-status-card__line";
      var text = typeof msg === "string" ? msg.slice(0, 36) : "Entrée mémoire";
      line.innerHTML = text + ' <time>· ' + String(i + 1).padStart(2, "0") + ":00</time>";
      this.recentMemoryBody.appendChild(line);
    }, this);
  };

  ReferenceShell.prototype.refreshConnectors = function () {
    if (!this.apiFetch) {
      return Promise.resolve();
    }
    var self = this;

    return Promise.all([
      this.apiFetch("/obsidian/status").catch(function () { return null; }),
      this.apiFetch("/browser/status").catch(function () { return null; }),
    ]).then(function (results) {
      var obsidian = results[0];
      var browser = results[1];

      if (obsidian && self.obsidianBody) {
        var noteCount = obsidian.note_count || obsidian.notes_count || "—";
        var vaultName = obsidian.vault_name || obsidian.vault || "Vault";
        self.obsidianBody.textContent = vaultName + " · " + noteCount + " notes";
        self._setModuleState("obsidian", obsidian.enabled !== false);
      }

      if (browser && self.browserBody) {
        var query = browser.last_query || browser.active_query;
        self.browserBody.textContent = query
          ? "Recherche: " + String(query).slice(0, 40)
          : browser.enabled
            ? "Prêt — exploration"
            : "Inactif";
        self._setModuleState("browser", browser.enabled !== false);
      }
    });
  };

  ReferenceShell.prototype._setModuleState = function (region, active) {
    if (!this.neuralModulesRoot) {
      return;
    }
    var mod = this.neuralModulesRoot.querySelector('[data-region="' + region + '"]');
    if (!mod) {
      return;
    }
    mod.classList.toggle("tdl-neural-module--active", !!active);
    mod.classList.toggle("tdl-neural-module--idle", !active);
    var statusEl = mod.querySelector(".tdl-neural-module__status");
    if (statusEl) {
      statusEl.textContent = active ? "ACTIF" : "IDLE";
    }
  };

  ReferenceShell.prototype.setBrainState = function (label) {
    if (this.brainEl) {
      this.brainEl.textContent = label || "Actif";
    }
  };

  ReferenceShell.prototype.updateOrchestratorTools = function (tools) {
    var listEl = document.getElementById("orchestrator-tools");
    if (!listEl) {
      return;
    }
    if (!tools || !tools.length) {
      listEl.innerHTML =
        '<li class="tdl-orchestrator-tools__item tdl-orchestrator-tools__item--empty">Aucun outil actif</li>';
      return;
    }
    listEl.innerHTML = "";
    tools.forEach(function (tool) {
      var item = document.createElement("li");
      item.className = "tdl-orchestrator-tools__item";
      var icon = document.createElement("span");
      icon.className = "tdl-orchestrator-tools__icon";
      icon.textContent = (tool.icon || tool.name || "?").slice(0, 1).toUpperCase();
      var label = document.createElement("span");
      label.textContent = tool.label || tool.name || "Outil";
      var status = document.createElement("span");
      status.className = "tdl-orchestrator-tools__status";
      status.textContent = "Actif";
      item.appendChild(icon);
      item.appendChild(label);
      item.appendChild(status);
      listEl.appendChild(item);
    });
  };

  ReferenceShell.prototype.destroy = function () {
    if (this._animId) {
      cancelAnimationFrame(this._animId);
    }
  };

  global.TitanReferenceShell = ReferenceShell;
})(window);
