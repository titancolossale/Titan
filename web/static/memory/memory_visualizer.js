/**
 * Titan Memory Visualizer — neural recall patterns and ambient life (Phase 17.9)
 *
 * Drives brain activation per memory source. Signals extend beyond the visible canvas.
 */
(function (global) {
  "use strict";

  var AMBIENT_MIN_MS = 14000;
  var AMBIENT_MAX_MS = 28000;

  var SOURCE_NEURAL = {
    conversation: { waveStyle: "deep_central", burst: 2, delay: 0 },
    long_term: { waveStyle: "slow", burst: 2, delay: 120 },
    obsidian: { waveStyle: "geometric", burst: 2, delay: 80 },
    browser: { waveStyle: "distributed", burst: 3, delay: 60 },
    calendar: { waveStyle: "circular", burst: 1, delay: 100 },
    trading: { waveStyle: "sharp", burst: 3, delay: 40 },
    project: { waveStyle: "default", burst: 1, delay: 90 },
    default: { waveStyle: "central", burst: 1, delay: 0 },
  };

  function MemoryVisualizer(options) {
    this.getNeuralEngine = options.getNeuralEngine || function () {
      return null;
    };
    this.getPresenceController = options.getPresenceController || function () {
      return null;
    };
    this._ambientTimer = null;
    this._pulseTimers = [];
    this._depthBound = false;
  }

  MemoryVisualizer.prototype.startAmbient = function () {
    var self = this;
    this.stopAmbient();

    function scheduleNext() {
      var delay =
        AMBIENT_MIN_MS + Math.random() * (AMBIENT_MAX_MS - AMBIENT_MIN_MS);
      self._ambientTimer = setTimeout(function () {
        self._fireAmbientPulse();
        scheduleNext();
      }, delay);
    }

    scheduleNext();
  };

  MemoryVisualizer.prototype.stopAmbient = function () {
    if (this._ambientTimer) {
      clearTimeout(this._ambientTimer);
      this._ambientTimer = null;
    }
  };

  MemoryVisualizer.prototype._fireAmbientPulse = function () {
    var engine = this.getNeuralEngine();
    if (!engine || !engine.triggerMemoryRetrieval) {
      return;
    }

    engine.triggerMemoryRetrieval({
      phase: "ambient",
      waveStyle: "central",
      intensity: 0.12,
      source: "long_term",
    });
  };

  MemoryVisualizer.prototype.pulse = function (source, phase, extra) {
    var profile = SOURCE_NEURAL[source] || SOURCE_NEURAL.default;
    var payload = {
      source: source,
      phase: phase || "recall",
      waveStyle: (extra && extra.waveStyle) || profile.waveStyle,
      intensity: extra && extra.intensity !== undefined ? extra.intensity : 0.55,
    };

    this._clearPulseTimers();
    this._emitNeural(payload, profile.burst, profile.delay);

    var presence = this.getPresenceController();
    if (presence && presence.hookMemoryRetrieval) {
      presence.hookMemoryRetrieval({
        source: source,
        phase: phase,
        waveStyle: payload.waveStyle,
      });
    }
  };

  MemoryVisualizer.prototype._emitNeural = function (payload, burst, staggerMs) {
    var self = this;
    var count = burst || 1;
    var delay = staggerMs || 0;

    for (var i = 0; i < count; i++) {
      var timer = setTimeout(function () {
        var engine = self.getNeuralEngine();
        if (!engine) {
          return;
        }
        if (engine.triggerMemoryRetrieval) {
          engine.triggerMemoryRetrieval(payload);
        } else if (engine.trigger) {
          engine.trigger("memory_retrieval", payload);
        }
      }, i * delay);
      this._pulseTimers.push(timer);
    }
  };

  MemoryVisualizer.prototype._clearPulseTimers = function () {
    this._pulseTimers.forEach(function (timer) {
      clearTimeout(timer);
    });
    this._pulseTimers = [];
  };

  MemoryVisualizer.prototype.bindDepth = function () {
    if (this._depthBound) {
      return;
    }
    var engine = this.getNeuralEngine();
    if (!engine || !engine.on) {
      return;
    }

    var self = this;
    engine.on("memory_retrieval", function () {
      self._hintDepthBeyondViewport();
    });
    this._depthBound = true;
  };

  MemoryVisualizer.prototype._hintDepthBeyondViewport = function () {
    var canvas = document.getElementById("neural-canvas");
    if (!canvas) {
      return;
    }
    canvas.classList.add("tdl-neural-canvas--depth-recall");
    setTimeout(function () {
      canvas.classList.remove("tdl-neural-canvas--depth-recall");
    }, 1400);
  };

  MemoryVisualizer.prototype.attach = function (bus, events) {
    var self = this;

    if (!bus || !events) {
      return;
    }

    bus.on(events.SEARCH_START, function (envelope) {
      var source = (envelope.payload && envelope.payload.source) || "long_term";
      self.pulse(source, "search", envelope.payload);
    });

    bus.on(events.RECALL, function (envelope) {
      var source = (envelope.payload && envelope.payload.source) || "long_term";
      self.pulse(source, "recall", envelope.payload);
    });

    bus.on(events.NEURAL_PULSE, function (envelope) {
      var payload = envelope.payload || {};
      self.pulse(payload.source || "long_term", payload.phase, payload);
    });

    bus.on(events.AMBIENT, function () {
      self._fireAmbientPulse();
    });

    this.bindDepth();
    this.startAmbient();
  };

  MemoryVisualizer.prototype.destroy = function () {
    this.stopAmbient();
    this._clearPulseTimers();
  };

  global.TitanMemoryVisualizer = MemoryVisualizer;
})(window);
