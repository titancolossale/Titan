/**
 * Titan Neural Brain Engine — Orchestrator
 * Phase 17.4 · Phase 18.0 · Phase 19.1 · Phase 19.2 · Phase 21.0 — cognitive visualization
 */
(function (global) {
  "use strict";

  var TitanNeural = global.TitanNeural || {};
  var CONFIG = TitanNeural.CONFIG;
  var Motion = global.TitanMotion;

  function NeuralBrainEngine(canvas, options) {
    this.canvas = canvas;
    this.options = options || {};

    this.state = new TitanNeural.BrainState();
    this.camera = new TitanNeural.BrainCamera();
    this.nodes = new TitanNeural.BrainNodes(this.camera);
    this.signals = new TitanNeural.BrainSignals(this.nodes);
    this.renderer = new TitanNeural.BrainRenderer(canvas);
    this.depthField = TitanNeural.DepthField
      ? new TitanNeural.DepthField()
      : null;
    this.cognitiveOverlay = TitanNeural.CognitiveOverlay
      ? new TitanNeural.CognitiveOverlay()
      : null;
    this._cognitiveCssState = "idle";

    this.frameId = null;
    this.resizeObserver = null;
    this._boundResize = this.resize.bind(this);
    this._boundTick = this.tick.bind(this);
    this._boundVisibility = this._onVisibilityChange.bind(this);
    this._lastFrameTime = 0;
    this._frameSkipCounter = 0;
    this._frameSamples = [];
    this._lastDensityAdjust = 0;
    this._baseDensity = this.options.density || CONFIG.nodes.densityDefault;

    if (this.depthField) {
      this.depthField.setInfiniteEnabled(true);
    }

    if (Motion && Motion.onMotionChange) {
      this._boundMotionChange = this._onMotionChange.bind(this);
      Motion.onMotionChange(this._boundMotionChange);
    }
  }

  NeuralBrainEngine.prototype.init = function () {
    if (this.options.density) {
      this._baseDensity = this.options.density;
      this.nodes.setDensity(this.options.density);
    }

    window.addEventListener("resize", this._boundResize);
    document.addEventListener("visibilitychange", this._boundVisibility);

    if (typeof ResizeObserver !== "undefined") {
      this.resizeObserver = new ResizeObserver(this._boundResize);
      this.resizeObserver.observe(this.canvas.parentElement || this.canvas);
    }

    this.state.setVisible(!document.hidden);
    this.setState("idle");
    this.resize();
    this.frameId = requestAnimationFrame(this._boundTick);
  };

  NeuralBrainEngine.prototype.destroy = function () {
    if (this.frameId) {
      cancelAnimationFrame(this.frameId);
      this.frameId = null;
    }
    window.removeEventListener("resize", this._boundResize);
    document.removeEventListener("visibilitychange", this._boundVisibility);
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
      this.resizeObserver = null;
    }
    if (Motion && Motion.offMotionChange && this._boundMotionChange) {
      Motion.offMotionChange(this._boundMotionChange);
    }
  };

  NeuralBrainEngine.prototype._onMotionChange = function () {
    this._lastFrameTime = 0;
    if (!this.frameId && !this.state.isPaused) {
      this.frameId = requestAnimationFrame(this._boundTick);
    }
  };

  NeuralBrainEngine.prototype._prefersReducedMotion = function () {
    return Motion && Motion.prefersReducedMotion ? Motion.prefersReducedMotion() : false;
  };

  NeuralBrainEngine.prototype.setPresenceProfile = function (profile) {
    this.state.setPresenceProfile(profile);
  };

  NeuralBrainEngine.prototype._onVisibilityChange = function () {
    this.state.setVisible(!document.hidden);
    if (!document.hidden) {
      this._lastFrameTime = 0;
      if (!this.frameId) {
        this.frameId = requestAnimationFrame(this._boundTick);
      }
    }
  };

  NeuralBrainEngine.prototype.setMode = function (mode) {
    this.state.setMode(mode);
    this._syncThinkingCss();
  };

  NeuralBrainEngine.prototype.setState = function (stateName) {
    if (!this.state.setState) {
      this.setMode(stateName === "thinking" ? "thinking" : "idle");
      return "idle";
    }

    var normalized = this.state.setState(stateName);
    this._applyCognitiveCss(normalized);
    this._syncThinkingCss();
    this._applyCognitiveDepth(normalized);
    return normalized;
  };

  NeuralBrainEngine.prototype.getCognitiveState = function () {
    return this.state.getCognitiveState
      ? this.state.getCognitiveState()
      : this.state.mode;
  };

  NeuralBrainEngine.prototype._syncThinkingCss = function () {
    this.canvas.classList.toggle(
      "tdl-neural-canvas--thinking",
      this.state.mode === "thinking"
    );
  };

  NeuralBrainEngine.prototype._applyCognitiveCss = function (stateId) {
    if (!TitanNeural.Cognitive) {
      return;
    }

    var classes = TitanNeural.Cognitive.getAllCssClasses();
    for (var i = 0; i < classes.length; i++) {
      this.canvas.classList.remove(classes[i]);
    }

    var cssClass = TitanNeural.Cognitive.getCssClass(stateId);
    if (cssClass) {
      this.canvas.classList.add(cssClass);
    }

    this.canvas.classList.toggle(
      "tdl-neural-canvas--depth-recall",
      stateId === "memory_retrieval" || stateId === "deep_analysis"
    );

    this._cognitiveCssState = stateId;
  };

  NeuralBrainEngine.prototype._applyCognitiveDepth = function (stateId) {
    if (!this.depthField) {
      return;
    }

    if (stateId === "memory_retrieval") {
      var recallBoost = (CONFIG.depth && CONFIG.depth.recallBoost) || 0.45;
      this.depthField.boostRecallDepth(recallBoost * 0.85);
      this.camera.boostRecallDive(recallBoost * 0.7);
    } else if (stateId === "deep_analysis") {
      this.depthField.boostRecallDepth(0.28);
      this.camera.boostRecallDive(0.42);
    }
  };

  NeuralBrainEngine.prototype.getState = function () {
    return this.state.getSnapshot();
  };

  NeuralBrainEngine.prototype.on = function (hookName, callback) {
    this.state.on(hookName, callback);
  };

  NeuralBrainEngine.prototype.off = function (hookName, callback) {
    this.state.off(hookName, callback);
  };

  NeuralBrainEngine.prototype.getDepthField = function () {
    return this.depthField;
  };

  NeuralBrainEngine.prototype.trigger = function (hookName, payload) {
    this.state.trigger(hookName, payload);
    if (hookName === "memory_retrieval" && this.depthField) {
      var boost = (CONFIG.depth && CONFIG.depth.recallBoost) || 0.45;
      this.depthField.boostRecallDepth(boost);
      this.camera.boostRecallDive(boost * 0.75);
    }
  };

  NeuralBrainEngine.prototype.triggerBrainActivity = function (payload) {
    this.trigger("brain_activity", payload);
  };

  NeuralBrainEngine.prototype.triggerToolUsage = function (payload) {
    this.trigger("tool_usage", payload);
  };

  NeuralBrainEngine.prototype.triggerMemoryRetrieval = function (payload) {
    this.trigger("memory_retrieval", payload);
  };

  NeuralBrainEngine.prototype.triggerReasoning = function (payload) {
    this.trigger("reasoning", payload);
  };

  NeuralBrainEngine.prototype.triggerVoice = function (payload) {
    this.trigger("voice", payload);
  };

  NeuralBrainEngine.prototype.triggerSpeaking = function (payload) {
    this.trigger("speaking", payload);
  };

  NeuralBrainEngine.prototype.resize = function () {
    var parent = this.canvas.parentElement;
    var useViewport =
      parent &&
      parent.classList &&
      parent.classList.contains("tdl-neural-stage--viewport");
    var width = useViewport ? window.innerWidth : parent ? parent.clientWidth : window.innerWidth;
    var height = useViewport ? window.innerHeight : parent ? parent.clientHeight : window.innerHeight;

    if (width < 1 || height < 1) return;

    this.camera.resize(width, height);
    this.renderer.resize(width, height);
    this.nodes.build(width, height);
  };

  NeuralBrainEngine.prototype._trackAdaptivePerformance = function (deltaMs, timestamp) {
    var perfCfg = CONFIG.performance || {};
    if (!perfCfg.adaptiveNodeCount) return;

    this._frameSamples.push(deltaMs);
    var windowSize = perfCfg.sampleWindow || 45;
    if (this._frameSamples.length > windowSize) {
      this._frameSamples.shift();
    }

    if (this._frameSamples.length < windowSize) return;
    if (timestamp - this._lastDensityAdjust < (perfCfg.densityRecoverMs || 8000)) {
      return;
    }

    var total = 0;
    for (var i = 0; i < this._frameSamples.length; i++) {
      total += this._frameSamples[i];
    }
    var avg = total / this._frameSamples.length;
    var budget = perfCfg.frameBudgetMs || 16.8;
    var floor = perfCfg.densityFloor || 0.55;
    var current = this.nodes.density;

    if (avg > budget * 1.08 && current > floor) {
      this.nodes.setDensity(Math.max(floor, current * 0.9));
      this.nodes.build(this.camera.width, this.camera.height);
      if (this.depthField) {
        this.depthField.setDepthBudget(Math.max(0.65, this.depthField._depthBudget * 0.92));
      }
      this._lastDensityAdjust = timestamp;
    } else if (avg < budget * 0.82 && current < this._baseDensity) {
      this.nodes.setDensity(Math.min(this._baseDensity, current * 1.04));
      this.nodes.build(this.camera.width, this.camera.height);
      if (this.depthField) {
        this.depthField.setDepthBudget(Math.min(1, this.depthField._depthBudget * 1.03));
      }
      this._lastDensityAdjust = timestamp;
    }
  };

  NeuralBrainEngine.prototype.tick = function (timestamp) {
    if (this.state.isPaused) {
      this.frameId = null;
      return;
    }

    if (!this._lastFrameTime) {
      this._lastFrameTime = timestamp;
    }

    var deltaMs = Math.min(timestamp - this._lastFrameTime, 50);
    var reduced = this._prefersReducedMotion();

    if (reduced) {
      this._frameSkipCounter += 1;
      if (this._frameSkipCounter % 4 !== 0) {
        this.frameId = requestAnimationFrame(this._boundTick);
        return;
      }
      deltaMs = 0;
    } else {
      this._frameSkipCounter = 0;
    }

    this._lastFrameTime = timestamp;

    this.update(timestamp, deltaMs);
    this.draw();
    this._trackAdaptivePerformance(deltaMs, timestamp);

    this.frameId = requestAnimationFrame(this._boundTick);
  };

  NeuralBrainEngine.prototype.update = function (timestamp, deltaMs) {
    this.state.update(timestamp, deltaMs);
    var intensity = this.state.getIntensity();
    var breathe = this.state.getBreathe();
    var recallDive = this.depthField ? this.depthField.getRecallDive() : 0;

    this.camera.update(deltaMs, intensity, breathe, this.state, recallDive);
    this.nodes.update(deltaMs, this.state);
    this.nodes.trySpawnConnection(timestamp, intensity);
    this.signals.update(timestamp, deltaMs, this.state);

    if (this.depthField) {
      this.depthField.update(deltaMs, this.camera, this.state);
    }

    if (this.cognitiveOverlay) {
      var signature = this.state.getCognitiveSignature
        ? this.state.getCognitiveSignature()
        : null;
      this.cognitiveOverlay.update(
        deltaMs,
        signature,
        this.camera,
        this.camera.width,
        this.camera.height
      );
    }
  };

  NeuralBrainEngine.prototype.draw = function () {
    this.renderer.renderWithSignals(
      this.camera,
      this.nodes,
      this.signals,
      this.state,
      this.depthField,
      this.cognitiveOverlay
    );
  };

  TitanNeural.NeuralBrainEngine = NeuralBrainEngine;
  global.NeuralBrainEngine = NeuralBrainEngine;
})(window);
