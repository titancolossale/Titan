/**
 * Titan Tool Timeline — compact status lines and activity feed (Phase 17.7)
 *
 * Shows ephemeral status lines during tool work and a collapsible history
 * in the context rail. Never displays raw JSON or implementation details.
 */
(function (global) {
  "use strict";

  var Events = TitanToolActivityManager.EVENTS;

  function ToolTimeline(options) {
    this.statusLineEl = options.statusLineEl || null;
    this.timelineEl = options.timelineEl || null;
    this.maxItems = options.maxItems || 8;
    this.statusHideMs = options.statusHideMs || 2400;

    this._manager = options.manager || null;
    this._statusTimer = null;
    this._history = [];
    this._boundHandlers = {};
  }

  ToolTimeline.prototype.attach = function (manager) {
    if (!manager) {
      return;
    }
    this.detach();
    this._manager = manager;

    this._boundHandlers.statusLine = this._onStatusLine.bind(this);
    this._boundHandlers.toolStart = this._onToolStart.bind(this);
    this._boundHandlers.toolComplete = this._onToolComplete.bind(this);
    this._boundHandlers.toolError = this._onToolError.bind(this);
    this._boundHandlers.turnEnd = this._onTurnEnd.bind(this);

    manager.on(Events.STATUS_LINE, this._boundHandlers.statusLine);
    manager.on(Events.TOOL_START, this._boundHandlers.toolStart);
    manager.on(Events.TOOL_COMPLETE, this._boundHandlers.toolComplete);
    manager.on(Events.TOOL_ERROR, this._boundHandlers.toolError);
    manager.on(Events.TURN_END, this._boundHandlers.turnEnd);
  };

  ToolTimeline.prototype.detach = function () {
    if (!this._manager) {
      return;
    }
    var m = this._manager;
    m.off(Events.STATUS_LINE, this._boundHandlers.statusLine);
    m.off(Events.TOOL_START, this._boundHandlers.toolStart);
    m.off(Events.TOOL_COMPLETE, this._boundHandlers.toolComplete);
    m.off(Events.TOOL_ERROR, this._boundHandlers.toolError);
    m.off(Events.TURN_END, this._boundHandlers.turnEnd);
    this._manager = null;
  };

  ToolTimeline.prototype._showStatusLine = function (text) {
    if (!this.statusLineEl || !text) {
      return;
    }

    this.statusLineEl.textContent = text;
    this.statusLineEl.hidden = false;
    this.statusLineEl.classList.add("tdl-tool-status-line--visible");

    if (this._statusTimer) {
      clearTimeout(this._statusTimer);
    }

    var self = this;
    this._statusTimer = setTimeout(function () {
      self._hideStatusLine();
    }, this.statusHideMs);
  };

  ToolTimeline.prototype._hideStatusLine = function () {
    if (!this.statusLineEl) {
      return;
    }
    this.statusLineEl.classList.remove("tdl-tool-status-line--visible");
    this.statusLineEl.hidden = true;
  };

  ToolTimeline.prototype._onStatusLine = function (event) {
    var text = event.payload && event.payload.text;
    this._showStatusLine(text);
  };

  ToolTimeline.prototype._onToolStart = function (event) {
    var run = event.payload;
    if (run && run.statusLine) {
      this._showStatusLine(run.statusLine);
    }
  };

  ToolTimeline.prototype._addHistoryItem = function (entry) {
    this._history.unshift(entry);
    if (this._history.length > this.maxItems) {
      this._history.pop();
    }
    this._renderTimeline();
  };

  ToolTimeline.prototype._onToolComplete = function (event) {
    var run = event.payload;
    this._addHistoryItem({
      runId: run.runId,
      icon: run.icon,
      title: run.title,
      summary: run.title + " — terminé",
      success: true,
      timestamp: event.timestamp,
    });
  };

  ToolTimeline.prototype._onToolError = function (event) {
    var run = event.payload;
    this._addHistoryItem({
      runId: run.runId,
      icon: run.icon,
      title: run.title,
      summary: run.title + " — interrompu",
      success: false,
      timestamp: event.timestamp,
    });
  };

  ToolTimeline.prototype._onTurnEnd = function () {
    var self = this;
    setTimeout(function () {
      self._hideStatusLine();
    }, 600);
  };

  ToolTimeline.prototype._renderTimeline = function () {
    if (!this.timelineEl) {
      return;
    }

    this.timelineEl.innerHTML = "";

    if (this._history.length === 0) {
      var empty = document.createElement("li");
      empty.className = "tdl-tool-timeline__item tdl-tool-timeline__item--empty";
      empty.textContent = "Aucune action récente";
      this.timelineEl.appendChild(empty);
      return;
    }

    for (var i = 0; i < this._history.length; i++) {
      var item = this._history[i];
      var li = document.createElement("li");
      li.className = "tdl-tool-timeline__item";
      if (!item.success) {
        li.classList.add("tdl-tool-timeline__item--error");
      }

      var icon = document.createElement("span");
      icon.className = "tdl-tool-timeline__icon";
      icon.textContent = item.icon || "◉";
      icon.setAttribute("aria-hidden", "true");

      var text = document.createElement("span");
      text.className = "tdl-tool-timeline__text";
      text.textContent = item.summary;

      li.appendChild(icon);
      li.appendChild(text);
      this.timelineEl.appendChild(li);
    }
  };

  ToolTimeline.prototype.clear = function () {
    this._history = [];
    this._renderTimeline();
    this._hideStatusLine();
  };

  global.TitanToolTimeline = ToolTimeline;
})(window);
