/**
 * Titan Presence Controller — event bridge to UI and neural engine (Phase 17.6)
 *
 * Wires stream lifecycle, composer focus, view changes, and future tool hooks
 * into the PresenceEngine. Makes Titan feel alive without redesigning the shell.
 */
(function (global) {
  "use strict";

  var States = TitanPresenceStates;
  var StreamStates = global.TitanStreamController
    ? TitanStreamController.STATES
    : {
        IDLE: "idle",
        THINKING: "thinking",
        STREAMING: "streaming",
        FINISHED: "finished",
        INTERRUPTED: "interrupted",
      };

  function profileNeuralThinking(profile) {
    return profile.neuralMode === "thinking" || profile.thinkingTarget > 0.2;
  }

  function toolToCognitiveState(tool) {
    var map = {
      browser: "exploration",
      calendar: "calendar",
      trading: "trading",
      memory: "memory",
      email: "email",
      obsidian: "memory",
      planning: "planning",
      voice: "voice",
      speaking: "voice",
      default: "tool",
    };
    return map[tool] || map.default;
  }

  function presenceToCognitiveState(state, activeTool) {
    if (state === States.STATES.LISTENING) {
      return "listening";
    }
    if (state === States.STATES.THINKING) {
      return "thinking";
    }
    if (state === States.STATES.SPEAKING) {
      return "voice";
    }
    if (state === States.STATES.WORKING) {
      return toolToCognitiveState(activeTool);
    }
    return "idle";
  }

  function PresenceController(options) {
    this.options = options || {};
    this.engine = new TitanPresenceEngine();
    this.getNeuralEngine = options.getNeuralEngine || function () {
      return null;
    };

    this.body = options.body || document.body;
    this.ambientGlow = options.ambientGlow || document.querySelector(".tdl-glow-ambient");
    this.appRoot = options.appRoot || document.querySelector(".tdl-app");
    this.thinkingEl = options.thinkingEl || null;
    this.barBrain = options.barBrain || null;
    this.barThinking = options.barThinking || null;
    this.dotThinking = options.dotThinking || null;
    this.composerInput = options.composerInput || null;
    this.composerZone = options.composerZone || null;
    this.neuralCanvas = options.neuralCanvas || null;

    this._composerFocused = false;
    this._streamActive = false;
    this._activeTool = null;
    this._lastNeuralMode = null;

    this._onUpdate = this._applyPresence.bind(this);
    this._onToolPulse = this._handleToolPulse.bind(this);
    this._onRipple = this._handleRipple.bind(this);

    this.engine.on("update", this._onUpdate);
    this.engine.on("toolPulse", this._onToolPulse);
    this.engine.on("ripple", this._onRipple);
    this.engine.on("statusChange", this._onUpdate);

    this._bindComposer();
    this.engine.setIdle();
  }

  PresenceController.prototype._bindComposer = function () {
    var self = this;
    var input = this.composerInput;
    if (!input) {
      return;
    }

    input.addEventListener("focus", function () {
      self._composerFocused = true;
      if (!self._streamActive) {
        self.engine.setListening();
      }
    });

    input.addEventListener("blur", function () {
      self._composerFocused = false;
      if (!self._streamActive && !self._activeTool) {
        self.engine.setIdle();
      }
    });

    input.addEventListener("input", function () {
      self.engine.notifyInputRipple();
    });
  };

  PresenceController.prototype.handleStreamState = function (streamState) {
    this._streamActive =
      streamState === StreamStates.THINKING ||
      streamState === StreamStates.STREAMING;

    if (streamState === StreamStates.THINKING) {
      this.engine.notifyStreamPhase("thinking");
      this._setCognitiveState("thinking");
      this._triggerNeural("reasoning", { phase: "conversation_thinking" });
    } else if (streamState === StreamStates.STREAMING) {
      this.engine.notifyStreamPhase("streaming");
    } else if (
      streamState === StreamStates.FINISHED ||
      streamState === StreamStates.IDLE
    ) {
      this._streamActive = false;
      if (this._activeTool) {
        this.engine.setWorking(this._activeTool);
      } else if (this._composerFocused) {
        this.engine.setListening();
      } else {
        this.engine.notifyStreamPhase("idle");
      }
    } else if (streamState === StreamStates.INTERRUPTED) {
      this._streamActive = false;
      this.engine.setCustomStatus(States.STATUS_LABELS.interrupted, States.STATES.IDLE);
    }
  };

  PresenceController.prototype._setCognitiveState = function (stateName) {
    var engine = this.getNeuralEngine();
    if (!engine) {
      return;
    }
    if (engine.setState) {
      engine.setState(stateName);
    } else if (engine.setMode) {
      engine.setMode(stateName === "thinking" ? "thinking" : "idle");
    }
  };

  PresenceController.prototype.notifyChatRequest = function () {
    this._triggerNeural("brain_activity", { phase: "chat_request" });
  };

  PresenceController.prototype.notifyResponseComplete = function () {
    this._triggerNeural("reasoning", { phase: "response_complete" });
  };

  PresenceController.prototype.setWorkingTool = function (tool, context) {
    this._activeTool = tool || null;
    if (this._streamActive) {
      return;
    }
    if (tool) {
      this.engine.setWorking(tool, context);
    } else if (this._composerFocused) {
      this.engine.setListening();
    } else {
      this.engine.setIdle();
    }
  };

  PresenceController.prototype.handleViewChange = function (view) {
    var toolMap = {
      browser: "browser",
      calendar: "calendar",
      trading: "trading",
      memory: "memory",
    };
    var tool = toolMap[view] || null;
    if (tool && !this._streamActive) {
      this.setWorkingTool(tool, { source: "navigation" });
    } else if (!this._streamActive) {
      this.setWorkingTool(null);
    }
  };

  PresenceController.prototype.handleVoiceSpeaking = function (payload) {
    this.engine.setSpeaking(payload || { source: "voice" });
    this._fireToolPattern("speaking", payload);
  };

  PresenceController.prototype.handleVoiceListening = function (payload) {
    if (this.engine.forceListening) {
      this.engine.forceListening(payload || { source: "voice" });
    } else {
      this.engine.setListening(payload || { source: "voice" });
    }
    this._fireToolPattern("voice", payload);
  };

  PresenceController.prototype.hookVoice = function (payload) {
    var phase = payload && payload.phase;
    if (phase === "speaking") {
      this.handleVoiceSpeaking(payload);
      return;
    }
    if (phase === "listening") {
      this.handleVoiceListening(payload);
      return;
    }
    this.setWorkingTool("voice", payload);
    this._fireToolPattern("voice", payload);
  };

  PresenceController.prototype.hookBrowser = function (payload) {
    this.setWorkingTool("browser", payload);
    this._setCognitiveState("exploration");
    this._fireToolPattern("browser", payload);
  };

  PresenceController.prototype.hookCalendar = function (payload) {
    this.setWorkingTool("calendar", payload);
    this._fireToolPattern("calendar", payload);
  };

  PresenceController.prototype.hookTrading = function (payload) {
    this.setWorkingTool("trading", payload);
    this._fireToolPattern("trading", payload);
  };

  PresenceController.prototype.hookMemoryRetrieval = function (payload) {
    if (!this._streamActive) {
      this.setWorkingTool("memory", payload);
    }
    this._fireToolPattern("memory", payload);
  };

  PresenceController.prototype.hookPlanning = function (payload) {
    if (!this._streamActive) {
      this.setWorkingTool("planning", payload);
    }
    this._fireToolPattern("planning", payload);
  };

  PresenceController.prototype.handleToolActivity = function (event) {
    if (!event) {
      return;
    }

    var tool = event.tool || "default";
    var phase = event.phase || "tool_progress";

    if (phase === "tool_start" || phase === "tool_progress") {
      this._activeTool = tool;
      this.engine.setWorking(tool, { source: "tool_activity", action: event.action });
      if (tool === "browser" || event.cognitiveState === "exploration" || event.exploration) {
        this._setCognitiveState("exploration");
      }
      this._fireToolPattern(tool, {
        phase: phase,
        waveStyle: event.waveStyle,
        action: event.action,
      });
    } else if (phase === "tool_complete" || phase === "tool_error") {
      this._fireToolPattern(tool, {
        phase: phase,
        waveStyle: event.waveStyle,
        action: event.action,
      });
      if (!this._streamActive) {
        this.setWorkingTool(null);
      }
    }
  };

  PresenceController.prototype._handleToolPulse = function (event) {
    this._fireToolPattern(event.tool, event.profile);
  };

  PresenceController.prototype._fireToolPattern = function (tool, extra) {
    var profile = States.getToolProfile(tool);
    var engine = this.getNeuralEngine();
    if (!engine) {
      return;
    }

    var payload = {
      tool: tool,
      pattern: tool,
      speedMult: profile.speedMult,
      waveBurst: profile.waveBurst,
      waveStyle: (extra && extra.waveStyle) || profile.waveStyle || "default",
      phase: (extra && extra.phase) || "presence_working",
    };

    if (profile.hook === "memory_retrieval" && engine.triggerMemoryRetrieval) {
      engine.triggerMemoryRetrieval(payload);
    } else if (profile.hook === "browser_research" && engine.setState) {
      engine.setState("exploration");
      if (engine.triggerToolUsage) {
        engine.triggerToolUsage(payload);
      }
    } else if (profile.hook === "reasoning" && engine.triggerReasoning) {
      engine.triggerReasoning(payload);
    } else if (profile.hook === "voice" && engine.triggerVoice) {
      engine.triggerVoice(payload);
    } else if (profile.hook === "speaking" && engine.triggerSpeaking) {
      engine.triggerSpeaking(payload);
    } else if (engine.triggerToolUsage) {
      engine.triggerToolUsage(payload);
    }

    for (var i = 1; i < profile.waveBurst; i++) {
      this._scheduleDelayedPulse(profile.hook, payload, i * 180);
    }
  };

  PresenceController.prototype._scheduleDelayedPulse = function (hook, payload, delayMs) {
    var self = this;
    setTimeout(function () {
      var engine = self.getNeuralEngine();
      if (!engine) {
        return;
      }
      if (hook === "memory_retrieval" && engine.triggerMemoryRetrieval) {
        engine.triggerMemoryRetrieval(payload);
      } else if (hook === "reasoning" && engine.triggerReasoning) {
        engine.triggerReasoning(payload);
      } else if (hook === "voice" && engine.triggerVoice) {
        engine.triggerVoice(payload);
      } else if (hook === "speaking" && engine.triggerSpeaking) {
        engine.triggerSpeaking(payload);
      } else if (engine.triggerToolUsage) {
        engine.triggerToolUsage(payload);
      }
    }, delayMs);
  };

  PresenceController.prototype._triggerNeural = function (hookName, payload) {
    var engine = this.getNeuralEngine();
    if (!engine) {
      return;
    }
    if (hookName === "brain_activity" && engine.triggerBrainActivity) {
      engine.triggerBrainActivity(payload);
    } else if (hookName === "reasoning" && engine.triggerReasoning) {
      engine.triggerReasoning(payload);
    } else if (hookName === "tool_usage" && engine.triggerToolUsage) {
      engine.triggerToolUsage(payload);
    } else if (hookName === "memory_retrieval" && engine.triggerMemoryRetrieval) {
      engine.triggerMemoryRetrieval(payload);
    } else if (engine.trigger) {
      engine.trigger(hookName, payload);
    }
  };

  PresenceController.prototype._handleRipple = function (event) {
    if (this.composerZone) {
      var strength = event && event.strength ? event.strength : 0.5;
      this.composerZone.style.setProperty(
        "--tdl-presence-ripple",
        String(strength)
      );
    }
  };

  PresenceController.prototype._applyPresence = function () {
    var ctx = this.engine.getContext();
    var profile = ctx.profile;
    var state = ctx.targetState;

    this._applyBodyClasses(state, ctx, profile);
    this._applyCssVariables(profile, ctx);
    this._applyNeural(profile);
    this._applyStatus(ctx.statusText, state);
  };

  PresenceController.prototype._applyBodyClasses = function (state, ctx, profile) {
    var classes = [
      "tdl-presence--idle",
      "tdl-presence--listening",
      "tdl-presence--thinking",
      "tdl-presence--speaking",
      "tdl-presence--working",
    ];
    for (var i = 0; i < classes.length; i++) {
      this.body.classList.remove(classes[i]);
    }
    this.body.classList.add("tdl-presence--" + state);

    if (this.appRoot) {
      for (var j = 0; j < classes.length; j++) {
        this.appRoot.classList.remove(classes[j]);
      }
      this.appRoot.classList.add("tdl-presence--" + state);
    }

    if (this.composerZone) {
      this.composerZone.classList.toggle(
        "tdl-composer--listening",
        state === States.STATES.LISTENING || ctx.listeningRipple > 0.05
      );
    }

    if (this.neuralCanvas) {
      this.neuralCanvas.classList.toggle(
        "tdl-neural-canvas--thinking",
        profileNeuralThinking(profile)
      );
      this.neuralCanvas.classList.toggle(
        "tdl-neural-canvas--listening",
        state === States.STATES.LISTENING
      );
      this.neuralCanvas.classList.toggle(
        "tdl-neural-canvas--working",
        state === States.STATES.WORKING
      );
      this.neuralCanvas.classList.toggle(
        "tdl-neural-canvas--speaking",
        state === States.STATES.SPEAKING
      );
    }
  };

  PresenceController.prototype._applyCssVariables = function (profile, ctx) {
    var root = document.documentElement;
    root.style.setProperty("--tdl-presence-glow", String(profile.glowLevel));
    root.style.setProperty("--tdl-presence-breathe", String(profile.breatheScale));
    root.style.setProperty(
      "--tdl-presence-breathe-speed",
      String(profile.breatheSpeed)
    );
    root.style.setProperty(
      "--tdl-presence-ambient",
      String(profile.ambientMotion)
    );
    root.style.setProperty("--tdl-presence-brightness", String(profile.brightness));
    root.style.setProperty(
      "--tdl-presence-ripple",
      String(ctx.listeningRipple || 0)
    );

    if (this.ambientGlow) {
      this.ambientGlow.style.opacity = String(0.28 + profile.glowLevel * 0.55);
    }
  };

  PresenceController.prototype._applyNeural = function (profile) {
    var engine = this.getNeuralEngine();
    if (!engine) {
      return;
    }

    if (engine.setPresenceProfile) {
      engine.setPresenceProfile(profile);
    }

    var ctx = this.engine.getContext();
    var cognitiveState = presenceToCognitiveState(
      ctx.targetState,
      this._activeTool
    );

    if (engine.setState) {
      engine.setState(cognitiveState);
      this._lastNeuralMode = cognitiveState;
      return;
    }

    if (!engine.setMode) {
      return;
    }

    var mode = profile.neuralMode;
    if (this._lastNeuralMode !== mode) {
      engine.setMode(mode);
      this._lastNeuralMode = mode;
    }
  };

  PresenceController.prototype._applyStatus = function (statusText, state) {
    var isActive =
      state === States.STATES.THINKING ||
      state === States.STATES.WORKING ||
      state === States.STATES.SPEAKING;

    if (this.thinkingEl) {
      this.thinkingEl.textContent = statusText;
      var showThinking =
        state === States.STATES.THINKING ||
        state === States.STATES.WORKING ||
        state === States.STATES.SPEAKING;
      this.thinkingEl.hidden = !showThinking;
      this.thinkingEl.classList.toggle(
        "tdl-conversation__thinking--visible",
        showThinking
      );
    }

    if (this.barBrain) {
      this.barBrain.textContent = statusText;
    }

    if (this.barThinking) {
      this.barThinking.textContent = isActive ? "Actif" : "Inactif";
      this.barThinking.classList.toggle("tdl-statusbar__value--fade", !isActive);
    }

    if (this.dotThinking) {
      this.dotThinking.classList.toggle("tdl-statusbar__dot--active", isActive);
    }
  };

  PresenceController.prototype.destroy = function () {
    this.engine.off("update", this._onUpdate);
    this.engine.off("toolPulse", this._onToolPulse);
    this.engine.off("ripple", this._onRipple);
    this.engine.off("statusChange", this._onUpdate);
    this.engine.destroy();
  };

  global.TitanPresenceController = PresenceController;
})(window);
