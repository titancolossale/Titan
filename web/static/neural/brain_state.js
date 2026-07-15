/**
 * Titan Neural Brain Engine — State & Activity Hooks
 * Phase 17.4 · Phase 19.1 · Phase 21.0 — cognitive visualization signatures
 */
(function (global) {
  "use strict";

  var TitanNeural = (global.TitanNeural = global.TitanNeural || {});
  var CONFIG = TitanNeural.CONFIG;
  var Cognitive = TitanNeural.Cognitive;

  function BrainState() {
    this.mode = "idle";
    this.cognitiveState = "idle";
    this.previousCognitiveState = "idle";
    this.cognitiveBlend = 1;
    this.cognitiveBlendSpeed = 0.0022;
    this.activeSignature = Cognitive
      ? Cognitive.getSignature("idle")
      : null;

    this.activityLevel = 0;
    this.thinkingIntensity = 0;
    this.breathePhase = 0;
    this.lastTimestamp = 0;
    this.isVisible = true;
    this.isPaused = false;
    this.presenceGlow = 0.38;
    this.presenceBreatheSpeed = 1;
    this.presenceSignalDensity = 0.35;
    this.vitalityPhase = Math.random() * Math.PI * 2;
    this.vitalityLevel = CONFIG.vitality ? CONFIG.vitality.idleFloor : 0.12;
    this.hooks = {};
    this._activityEvents = [];
    this._pendingHookType = undefined;

    var hooks = CONFIG.activityHooks;
    for (var i = 0; i < hooks.length; i++) {
      this.hooks[hooks[i]] = [];
    }
  }

  BrainState.prototype.setMode = function (mode) {
    this.mode = mode === "thinking" ? "thinking" : "idle";
  };

  BrainState.prototype.setState = function (stateName) {
    if (!Cognitive) {
      this.setMode(stateName === "thinking" ? "thinking" : "idle");
      return this.cognitiveState;
    }

    var normalized = Cognitive.normalizeState(stateName);
    if (normalized === this.cognitiveState) {
      return normalized;
    }

    this.previousCognitiveState = this.cognitiveState;
    this.cognitiveState = normalized;
    this.cognitiveBlend = 0;

    var signature = Cognitive.getSignature(normalized);
    this.cognitiveBlendSpeed = 1 / Math.max(signature.transitionMs || 700, 320);
    this.setMode(signature.neuralMode || "idle");

    return normalized;
  };

  BrainState.prototype.getCognitiveState = function () {
    return this.cognitiveState;
  };

  BrainState.prototype.getCognitiveSignature = function () {
    return this.activeSignature || (Cognitive ? Cognitive.getSignature("idle") : null);
  };

  BrainState.prototype.setVisible = function (visible) {
    this.isVisible = visible;
    this.isPaused = CONFIG.performance.hiddenTabPause && !visible;
  };

  BrainState.prototype.setPresenceProfile = function (profile) {
    if (!profile) {
      return;
    }
    this.presenceGlow = profile.glowLevel !== undefined ? profile.glowLevel : this.presenceGlow;
    this.presenceBreatheSpeed =
      profile.breatheSpeed !== undefined ? profile.breatheSpeed : this.presenceBreatheSpeed;
    this.presenceSignalDensity =
      profile.signalDensity !== undefined ? profile.signalDensity : this.presenceSignalDensity;
  };

  BrainState.prototype._updateCognitiveBlend = function (deltaMs) {
    if (!Cognitive) {
      return;
    }

    if (this.cognitiveBlend < 1) {
      this.cognitiveBlend = Math.min(
        1,
        this.cognitiveBlend + this.cognitiveBlendSpeed * deltaMs
      );
    }

    this.activeSignature = Cognitive.blendSignatures(
      this.previousCognitiveState,
      this.cognitiveState,
      this.cognitiveBlend
    );
  };

  BrainState.prototype.update = function (timestamp, deltaMs) {
    if (!this.lastTimestamp) {
      this.lastTimestamp = timestamp;
    }

    var reduced =
      global.TitanMotion && global.TitanMotion.prefersReducedMotion
        ? global.TitanMotion.prefersReducedMotion()
        : false;
    if (reduced) {
      this.lastTimestamp = timestamp;
      this._updateCognitiveBlend(deltaMs);
      return;
    }

    this._updateCognitiveBlend(deltaMs);

    var signature = this.getCognitiveSignature();
    var breatheSpeed =
      (CONFIG.nodes.breatheSpeed || 0.00038) *
      (signature ? signature.breatheSpeed : 1) *
      this.presenceBreatheSpeed;
    var vitalityCfg = CONFIG.vitality || {};

    this.breathePhase += breatheSpeed * deltaMs;
    this.vitalityPhase += (vitalityCfg.oscillationSpeed || 0.00055) * deltaMs;

    var idleFloor = vitalityCfg.idleFloor !== undefined ? vitalityCfg.idleFloor : 0.12;
    var idleCeiling = vitalityCfg.idleCeiling !== undefined ? vitalityCfg.idleCeiling : 0.28;
    var vitalityWave = (Math.sin(this.vitalityPhase) + 1) * 0.5;
    this.vitalityLevel = idleFloor + vitalityWave * (idleCeiling - idleFloor);

    var activityTarget = signature ? signature.activityTarget : 0.08;
    var thinkingTarget = signature ? signature.thinkingTarget : 0;
    var riseRate = this.mode === "thinking" ? 0.04 : 0.028;
    var decayRate = CONFIG.thinking.decayRate;

    if (this.activityLevel < activityTarget) {
      this.activityLevel = Math.min(activityTarget, this.activityLevel + riseRate);
    } else {
      this.activityLevel = Math.max(activityTarget, this.activityLevel - decayRate * 0.65);
    }

    if (this.thinkingIntensity < thinkingTarget) {
      this.thinkingIntensity = Math.min(thinkingTarget, this.thinkingIntensity + 0.035);
    } else {
      this.thinkingIntensity = Math.max(thinkingTarget, this.thinkingIntensity - decayRate);
    }

    if (signature && signature.signalDensity !== undefined) {
      this.presenceSignalDensity = signature.signalDensity;
    }

    if (signature && signature.glowLevel !== undefined) {
      this.presenceGlow = signature.glowLevel;
    }

    this.lastTimestamp = timestamp;
  };

  BrainState.prototype.getBreathe = function () {
    return (Math.sin(this.breathePhase) + 1) * 0.5;
  };

  BrainState.prototype.isThinking = function () {
    return this.mode === "thinking" || this.thinkingIntensity > 0.05;
  };

  BrainState.prototype.getIntensity = function () {
    return Math.max(
      this.thinkingIntensity,
      this.activityLevel,
      this.presenceGlow * 0.35,
      this.vitalityLevel
    );
  };

  BrainState.prototype.getVitality = function () {
    return this.vitalityLevel;
  };

  BrainState.prototype.on = function (hookName, callback) {
    if (!this.hooks[hookName] || typeof callback !== "function") {
      return;
    }
    this.hooks[hookName].push(callback);
  };

  BrainState.prototype.off = function (hookName, callback) {
    var list = this.hooks[hookName];
    if (!list) return;
    var idx = list.indexOf(callback);
    if (idx !== -1) list.splice(idx, 1);
  };

  BrainState.prototype.trigger = function (hookName, payload) {
    if (!this.hooks[hookName]) return;

    var event = {
      type: hookName,
      payload: payload || {},
      timestamp: performance.now(),
    };
    this._activityEvents.push(event);
    if (this._activityEvents.length > 32) {
      this._activityEvents.shift();
    }

    var list = this.hooks[hookName];
    for (var i = 0; i < list.length; i++) {
      try {
        list[i](event);
      } catch (_err) {
        /* hook errors must not break render loop */
      }
    }

    this._applyActivityPulse(hookName, payload);
  };

  BrainState.prototype._applyActivityPulse = function (hookName, payload) {
    var boost = 0.15;
    if (hookName === "brain_activity" || hookName === "reasoning") {
      boost = 0.35;
      if (Cognitive) {
        this.setState("deep_analysis");
      }
    } else if (hookName === "tool_usage") {
      boost = 0.28;
    } else if (hookName === "memory_retrieval") {
      boost = 0.22;
      if (Cognitive) {
        this.setState("memory_retrieval");
      }
    } else if (hookName === "voice") {
      boost = 0.4;
      if (Cognitive) {
        this.setState("listening");
      }
    } else if (hookName === "speaking") {
      boost = 0.32;
      if (Cognitive) {
        this.setState("voice_speaking");
      }
    }

    this.activityLevel = Math.min(1, this.activityLevel + boost);
    this._pendingHookType = hookName;

    if (payload && payload.originNodeId !== undefined) {
      this._pendingActivation = payload.originNodeId;
    }

    var signature = this.getCognitiveSignature();
    var waveStyle =
      (payload && payload.waveStyle) ||
      (signature && signature.waveStyle) ||
      "default";

    this._pendingWaveStyle = waveStyle;

    this._pendingPreferDeep =
      hookName === "memory_retrieval" || (signature && signature.preferDeep);
    this._pendingToolPattern = payload && payload.tool ? payload.tool : undefined;

    if (payload && payload.tool && Cognitive) {
      var toolState = Cognitive.normalizeState(payload.tool);
      if (toolState !== "idle" && toolState !== "tool_usage") {
        this.setState(toolState);
      } else if (hookName === "tool_usage") {
        this.setState("tool_usage");
      }
    }
  };

  BrainState.prototype.consumePendingWaveStyle = function () {
    var style = this._pendingWaveStyle;
    this._pendingWaveStyle = undefined;
    return style;
  };

  BrainState.prototype.consumePendingActivation = function () {
    var id = this._pendingActivation;
    this._pendingActivation = undefined;
    return id;
  };

  BrainState.prototype.consumePendingHookType = function () {
    var hook = this._pendingHookType;
    this._pendingHookType = undefined;
    return hook;
  };

  BrainState.prototype.consumePreferDeep = function () {
    var deep = this._pendingPreferDeep;
    this._pendingPreferDeep = undefined;
    return !!deep;
  };

  BrainState.prototype.consumeToolPattern = function () {
    var tool = this._pendingToolPattern;
    this._pendingToolPattern = undefined;
    return tool;
  };

  BrainState.prototype.getSnapshot = function () {
    return {
      mode: this.mode,
      cognitiveState: this.cognitiveState,
      activityLevel: this.activityLevel,
      thinkingIntensity: this.thinkingIntensity,
      isPaused: this.isPaused,
      isVisible: this.isVisible,
      breathe: this.getBreathe(),
      signature: this.getCognitiveSignature(),
    };
  };

  TitanNeural.BrainState = BrainState;
})(window);
