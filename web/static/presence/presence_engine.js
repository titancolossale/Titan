/**
 * Titan Presence Engine — living state orchestrator (Phase 17.6 · 18.0)
 *
 * Event-driven presence with smooth interpolated transitions via TitanMotion easing.
 */
(function (global) {
  "use strict";

  var States = TitanPresenceStates;
  var Motion = global.TitanMotion;

  function lerp(a, b, t) {
    return Motion && Motion.lerp ? Motion.lerp(a, b, t) : a + (b - a) * t;
  }

  function lerpProfile(from, to, t) {
    return {
      neuralMode: t >= 0.55 ? to.neuralMode : from.neuralMode,
      activityTarget: lerp(from.activityTarget, to.activityTarget, t),
      thinkingTarget: lerp(from.thinkingTarget, to.thinkingTarget, t),
      glowLevel: lerp(from.glowLevel, to.glowLevel, t),
      breatheScale: lerp(from.breatheScale, to.breatheScale, t),
      breatheSpeed: lerp(from.breatheSpeed, to.breatheSpeed, t),
      ambientMotion: lerp(from.ambientMotion, to.ambientMotion, t),
      signalDensity: lerp(from.signalDensity, to.signalDensity, t),
      brightness: lerp(from.brightness, to.brightness, t),
    };
  }

  function PresenceEngine(options) {
    this._listeners = {};
    this._currentState = States.STATES.IDLE;
    this._targetState = States.STATES.IDLE;
    this._context = {};
    this._tool = null;
    this._streamPhase = null;
    this._transitionStart = 0;
    this._transitionDuration = States.getTransitionMs(
      States.STATES.IDLE,
      States.STATES.IDLE
    );
    this._transitionProgress = 1;
    this._fromProfile = States.STATE_PROFILES.idle;
    this._toProfile = States.STATE_PROFILES.idle;
    this._blendedProfile = States.STATE_PROFILES.idle;
    this._statusText = States.getStatusForState(States.STATES.IDLE);
    this._workingPulseTimer = null;
    this._frameId = null;
    this._lastTimestamp = 0;
    this._listeningRipple = 0;
    this._documentHidden = false;

    this._tickBound = this._tick.bind(this);
    this._visibilityBound = this._onVisibilityChange.bind(this);
    document.addEventListener("visibilitychange", this._visibilityBound);
    this._startLoop();
  }

  PresenceEngine.prototype._onVisibilityChange = function () {
    this._documentHidden = document.hidden;
    if (!this._documentHidden && !this._frameId) {
      this._startLoop();
    }
  };

  PresenceEngine.prototype.on = function (event, callback) {
    if (typeof callback !== "function") {
      return;
    }
    if (!this._listeners[event]) {
      this._listeners[event] = [];
    }
    this._listeners[event].push(callback);
  };

  PresenceEngine.prototype.off = function (event, callback) {
    var list = this._listeners[event];
    if (!list) {
      return;
    }
    var idx = list.indexOf(callback);
    if (idx !== -1) {
      list.splice(idx, 1);
    }
  };

  PresenceEngine.prototype._emit = function (event, payload) {
    var list = this._listeners[event];
    if (!list) {
      return;
    }
    for (var i = 0; i < list.length; i++) {
      try {
        list[i](payload);
      } catch (_err) {
        /* presence listeners must not break the loop */
      }
    }
  };

  PresenceEngine.prototype.getState = function () {
    return this._currentState;
  };

  PresenceEngine.prototype.getTargetState = function () {
    return this._targetState;
  };

  PresenceEngine.prototype.getStatusText = function () {
    return this._statusText;
  };

  PresenceEngine.prototype.getProfile = function () {
    return this._blendedProfile;
  };

  PresenceEngine.prototype.getContext = function () {
    return {
      state: this._currentState,
      targetState: this._targetState,
      tool: this._tool,
      streamPhase: this._streamPhase,
      transitionProgress: this._transitionProgress,
      listeningRipple: this._listeningRipple,
      statusText: this._statusText,
      profile: this._blendedProfile,
    };
  };

  PresenceEngine.prototype._startLoop = function () {
    if (this._frameId) {
      return;
    }
    this._frameId = requestAnimationFrame(this._tickBound);
  };

  PresenceEngine.prototype._tick = function (timestamp) {
    if (this._documentHidden) {
      this._frameId = null;
      return;
    }

    if (!this._lastTimestamp) {
      this._lastTimestamp = timestamp;
    }

    if (this._transitionProgress < 1) {
      var elapsed = timestamp - this._transitionStart;
      var reduced = Motion && Motion.prefersReducedMotion && Motion.prefersReducedMotion();
      if (reduced) {
        this._transitionProgress = 1;
        this._currentState = this._targetState;
        this._blendedProfile = this._toProfile;
      } else {
        this._transitionProgress = Math.min(1, elapsed / this._transitionDuration);
        var eased = this._easeTransition(this._transitionProgress);
        this._blendedProfile = lerpProfile(this._fromProfile, this._toProfile, eased);

        if (this._transitionProgress >= 1) {
          this._currentState = this._targetState;
          this._blendedProfile = this._toProfile;
        }
      }
    }

    this._decayListeningRipple(timestamp - this._lastTimestamp);
    this._lastTimestamp = timestamp;

    this._emit("update", this.getContext());
    this._frameId = requestAnimationFrame(this._tickBound);
  };

  PresenceEngine.prototype._easeTransition = function (t) {
    if (Motion && Motion.ease) {
      return Motion.ease("organic", t);
    }
    return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
  };

  PresenceEngine.prototype._decayListeningRipple = function (deltaMs) {
    if (this._listeningRipple <= 0) {
      return;
    }
    this._listeningRipple = Math.max(0, this._listeningRipple - deltaMs * 0.004);
  };

  PresenceEngine.prototype._beginTransition = function (toState) {
    if (toState === this._targetState && this._transitionProgress >= 1) {
      return;
    }

    var resolvedFrom =
      this._transitionProgress < 1 ? this._targetState : this._currentState;

    this._fromProfile = this._blendedProfile;
    this._toProfile = States.STATE_PROFILES[toState] || States.STATE_PROFILES.idle;
    this._targetState = toState;
    this._transitionStart = performance.now();
    this._transitionDuration = States.getTransitionMs(resolvedFrom, toState);
    this._transitionProgress = 0;
    this._updateStatusText();
    this._syncWorkingPulse();

    this._emit("stateChange", {
      from: resolvedFrom,
      to: toState,
      context: this.getContext(),
    });
  };

  PresenceEngine.prototype._updateStatusText = function () {
    this._statusText = States.getStatusForState(this._targetState, {
      tool: this._tool,
      streamPhase: this._streamPhase,
      customStatus: this._context.customStatus,
    });
  };

  PresenceEngine.prototype._canOverride = function (nextState) {
    var current =
      this._transitionProgress < 1 ? this._targetState : this._currentState;
    var currentPriority = States.STATE_PRIORITY[current] || 0;
    var nextPriority = States.STATE_PRIORITY[nextState] || 0;
    return nextPriority >= currentPriority;
  };

  PresenceEngine.prototype.setIdle = function (context) {
    this._context = context || {};
    this._tool = null;
    this._streamPhase = null;
    this._beginTransition(States.STATES.IDLE);
  };

  PresenceEngine.prototype.setListening = function (context) {
    this._context = context || {};
    this._streamPhase = null;
    if (!this._canOverride(States.STATES.LISTENING)) {
      this._listeningRipple = 1;
      this._emit("ripple", { strength: 1 });
      return;
    }
    this._beginTransition(States.STATES.LISTENING);
  };

  PresenceEngine.prototype.forceListening = function (context) {
    this._context = context || {};
    this._streamPhase = null;
    this._listeningRipple = 1;
    this._beginTransition(States.STATES.LISTENING);
    this._emit("ripple", { strength: 1 });
  };

  PresenceEngine.prototype.setSpeaking = function (context) {
    this._context = context || {};
    this._tool = null;
    this._streamPhase = "speaking";
    this._beginTransition(States.STATES.SPEAKING);
  };

  PresenceEngine.prototype.setThinking = function (context) {
    this._context = context || {};
    this._tool = null;
    this._streamPhase = (context && context.streamPhase) || null;
    this._beginTransition(States.STATES.THINKING);
  };

  PresenceEngine.prototype.setWorking = function (tool, context) {
    this._context = context || {};
    this._tool = tool || null;
    this._streamPhase = null;
    this._beginTransition(States.STATES.WORKING);
  };

  PresenceEngine.prototype.setCustomStatus = function (text, state) {
    this._context.customStatus = text;
    if (state) {
      this._beginTransition(state);
    } else {
      this._updateStatusText();
      this._emit("statusChange", { statusText: this._statusText });
    }
  };

  PresenceEngine.prototype.notifyInputRipple = function () {
    this._listeningRipple = Math.min(1, this._listeningRipple + 0.35);
    if (this._targetState === States.STATES.IDLE) {
      this.setListening();
    }
    this._emit("ripple", { strength: this._listeningRipple });
  };

  PresenceEngine.prototype.notifyStreamPhase = function (phase) {
    this._streamPhase = phase;
    this._updateStatusText();
    this._emit("statusChange", { statusText: this._statusText });

    if (phase === "thinking") {
      this.setThinking({ streamPhase: phase });
    } else if (phase === "streaming") {
      this.setThinking({ streamPhase: phase });
    } else if (phase === "speaking") {
      this.setSpeaking({ streamPhase: phase });
    } else if (phase === "idle" || phase === "finished" || phase === "interrupted") {
      this.setIdle();
    }
  };

  PresenceEngine.prototype._syncWorkingPulse = function () {
    var self = this;
    if (this._workingPulseTimer) {
      clearInterval(this._workingPulseTimer);
      this._workingPulseTimer = null;
    }

    if (this._targetState !== States.STATES.WORKING) {
      return;
    }

    var profile = States.getToolProfile(this._tool);
    this._workingPulseTimer = setInterval(function () {
      self._emit("toolPulse", {
        tool: self._tool,
        profile: profile,
      });
    }, profile.pulseIntervalMs);

    this._emit("toolPulse", { tool: this._tool, profile: profile });
  };

  PresenceEngine.prototype.destroy = function () {
    document.removeEventListener("visibilitychange", this._visibilityBound);
    if (this._frameId) {
      cancelAnimationFrame(this._frameId);
      this._frameId = null;
    }
    if (this._workingPulseTimer) {
      clearInterval(this._workingPulseTimer);
      this._workingPulseTimer = null;
    }
    this._listeners = {};
  };

  global.TitanPresenceEngine = PresenceEngine;
})(window);
