/**
 * Titan Voice Controller — orchestrates voice I/O with Presence and chat (Phase 17.8)
 *
 * Event-driven bridge between speech modules, conversation stream, and neural brain.
 */
(function (global) {
  "use strict";

  var VoiceEvents = global.TitanVoiceEvents;
  var EVENTS = VoiceEvents.EVENTS;
  var MODES = VoiceEvents.MODES;

  function VoiceController(options) {
    this.options = options || {};
    this.bus = new VoiceEvents.VoiceEventBus();

    this.micBtn = options.micBtn || null;
    this.micToggle = options.micToggle || null;
    this.neuralStage = options.neuralStage || null;

    this.getConversation = options.getConversation || function () {
      return null;
    };
    this.getPresenceController = options.getPresenceController || function () {
      return null;
    };
    this.getNeuralEngine = options.getNeuralEngine || function () {
      return null;
    };
    this.apiFetch = options.apiFetch || null;
    this.validateBeforeSend = options.validateBeforeSend || null;

    this.config = {
      locale: "fr-FR",
      rate: 0.95,
      pitch: 1,
      continuous: false,
      enabled: true,
    };

    this.input = new TitanSpeechInput.SpeechInput({
      bus: this.bus,
      locale: this.config.locale,
      mode: MODES.PUSH_TO_TALK,
      continuousPreferred: this.config.continuous,
    });

    this.output = new TitanSpeechOutput.SpeechOutput({
      bus: this.bus,
      locale: this.config.locale,
      rate: this.config.rate,
      pitch: this.config.pitch,
    });

    this._voiceTurnActive = false;
    this._speakPulseTimer = null;
    this._pushHeld = false;
    this._ready = false;

    this._bindEvents();
    this._bindMic();
    this._loadConfig();
  }

  VoiceController.prototype._loadConfig = function () {
    var self = this;
    if (!this.apiFetch) {
      this._markReady();
      return;
    }

    this.apiFetch("/voice/status")
      .then(function (payload) {
        if (!payload) {
          self._markReady();
          return;
        }
        var caps = payload.capabilities || {};
        var speech = payload.speech || {};
        self.config.enabled = caps.enabled !== false;
        self.config.locale = speech.locale || self.config.locale;
        self.config.rate = speech.rate !== undefined ? speech.rate : self.config.rate;
        self.config.pitch = speech.pitch !== undefined ? speech.pitch : self.config.pitch;
        self.config.continuous = !!caps.continuous_listening;

        self.input.locale = self.config.locale;
        self.output.locale = self.config.locale;
        self.output.rate = self.config.rate;
        self.output.pitch = self.config.pitch;

        if (self.config.continuous) {
          self.input.setMode(MODES.CONTINUOUS);
        }
        self._markReady();
      })
      .catch(function () {
        self._markReady();
      });
  };

  VoiceController.prototype._markReady = function () {
    this._ready = true;
    this._updateMicAvailability();
    this.bus.emit(EVENTS.READY, {
      supported: this.isSupported(),
      config: this.config,
    });
  };

  VoiceController.prototype.isSupported = function () {
    return this.input.isSupported() && this.output.isSupported();
  };

  VoiceController.prototype._bindEvents = function () {
    var self = this;

    this.bus.on(EVENTS.LISTEN_START, function () {
      self._setMicState("listening");
      self._applyPresenceListening(true);
      self._triggerNeural("voice", { phase: "listen_start" });
    });

    this.bus.on(EVENTS.LISTEN_PARTIAL, function (event) {
      var text = event.payload && event.payload.text;
      if (text) {
        self._applyPresenceRipple();
      }
    });

    this.bus.on(EVENTS.LISTEN_END, function (event) {
      self._setMicState("idle");
      var transcript = event.payload && event.payload.transcript;
      if (transcript && self._voiceTurnActive) {
        self._submitTranscript(transcript);
      } else if (!self._pushHeld && self.input.getMode() !== MODES.CONTINUOUS) {
        self._applyPresenceIdle();
      }
    });

    this.bus.on(EVENTS.SPEAK_START, function () {
      self._setMicState("speaking");
      self._applyPresenceSpeaking(true);
      self._startSpeakPulse();
    });

    this.bus.on(EVENTS.SPEAK_WORD, function () {
      self._triggerNeural("speaking", { phase: "word_boundary" });
      self._applyPresenceRipple(0.25);
    });

    this.bus.on(EVENTS.SPEAK_END, function () {
      self._stopSpeakPulse();
      self._setMicState("idle");
      self._voiceTurnActive = false;
      if (self.input.getMode() === MODES.CONTINUOUS) {
        self.startListening();
      } else {
        self._applyPresenceIdle();
      }
    });

    this.bus.on(EVENTS.SPEAK_INTERRUPTED, function () {
      self._stopSpeakPulse();
      self._setMicState("idle");
    });

    this.bus.on(EVENTS.ERROR, function (event) {
      var code = event.payload && event.payload.code;
      if (code === "not-allowed" || code === "not_allowed") {
        self._setMicState("denied");
      } else {
        self._setMicState("idle");
      }
      self._voiceTurnActive = false;
      self._applyPresenceIdle();
    });
  };

  VoiceController.prototype._bindMic = function () {
    var self = this;
    if (!this.micBtn) {
      return;
    }

    this.micBtn.addEventListener("mousedown", function (event) {
      event.preventDefault();
      if (self.input.getMode() === MODES.CONTINUOUS) {
        return;
      }
      self._pushHeld = true;
      self.interrupt();
      self.startListening();
    });

    this.micBtn.addEventListener("mouseup", function () {
      if (self.input.getMode() === MODES.CONTINUOUS) {
        return;
      }
      self._pushHeld = false;
      self.stopListening();
    });

    this.micBtn.addEventListener("mouseleave", function () {
      if (self._pushHeld && self.input.getMode() !== MODES.CONTINUOUS) {
        self._pushHeld = false;
        self.stopListening();
      }
    });

    this.micBtn.addEventListener("touchstart", function (event) {
      event.preventDefault();
      if (self.input.getMode() === MODES.CONTINUOUS) {
        return;
      }
      self._pushHeld = true;
      self.interrupt();
      self.startListening();
    }, { passive: false });

    this.micBtn.addEventListener("touchend", function (event) {
      event.preventDefault();
      if (self.input.getMode() === MODES.CONTINUOUS) {
        return;
      }
      self._pushHeld = false;
      self.stopListening();
    });

    this.micBtn.addEventListener("click", function (event) {
      if (self.input.getMode() !== MODES.CONTINUOUS) {
        return;
      }
      event.preventDefault();
      if (self.input.isListening()) {
        self.stopListening();
      } else {
        self.interrupt();
        self.startListening();
      }
    });

    if (this.micToggle) {
      this.micToggle.addEventListener("change", function () {
        var continuous = self.micToggle.checked;
        self.input.setMode(continuous ? MODES.CONTINUOUS : MODES.PUSH_TO_TALK);
        self.config.continuous = continuous;
      });
    }
  };

  VoiceController.prototype.startListening = function () {
    if (!this._ready || !this.config.enabled || !this.isSupported()) {
      return false;
    }
    if (this.validateBeforeSend && !this.validateBeforeSend()) {
      return false;
    }
    this._voiceTurnActive = true;
    return this.input.startListening();
  };

  VoiceController.prototype.stopListening = function () {
    return this.input.stopListening();
  };

  VoiceController.prototype.interrupt = function () {
    this.bus.emit(EVENTS.INTERRUPT, {});

    if (this.output.isSpeaking()) {
      this.output.cancel();
    }

    var conversation = this.getConversation();
    if (conversation && conversation.interrupt) {
      conversation.interrupt();
    }

    if (this.input.isListening()) {
      this.input.abortListening();
    }

    this._voiceTurnActive = false;
    this._stopSpeakPulse();
    this._applyPresenceIdle();
  };

  VoiceController.prototype._submitTranscript = function (transcript) {
    var conversation = this.getConversation();
    if (!conversation || !conversation.sendFromVoice) {
      return;
    }

    this.bus.emit(EVENTS.THINKING, { transcript: transcript });
    this._applyPresenceThinking();

    var self = this;
    conversation.sendFromVoice(transcript, {
      onStreamToken: function (_token, accumulated) {
        if (!self.output.isSpeaking() && accumulated) {
          self.output.beginStream(accumulated);
        } else {
          self.output.syncToText(accumulated);
        }
      },
      onStreamComplete: function (finalText) {
        self.output.finishStream(finalText);
      },
      onStreamInterrupt: function () {
        self.output.cancel();
        self._voiceTurnActive = false;
      },
    });
  };

  VoiceController.prototype._applyPresenceListening = function (force) {
    var presence = this.getPresenceController();
    if (!presence) {
      return;
    }
    if (force && presence.engine && presence.engine.forceListening) {
      presence.engine.forceListening({ source: "voice" });
    } else if (presence.engine && presence.engine.setListening) {
      presence.engine.setListening({ source: "voice" });
    }
    if (presence.hookVoice) {
      presence.hookVoice({ phase: "listening" });
    }
    if (this.neuralStage) {
      this.neuralStage.classList.add("tdl-neural-stage--listening");
    }
  };

  VoiceController.prototype._applyPresenceThinking = function () {
    var presence = this.getPresenceController();
    if (presence && presence.engine && presence.engine.setThinking) {
      presence.engine.setThinking({ source: "voice", streamPhase: "thinking" });
    }
    this.bus.emit(EVENTS.THINKING, {});
  };

  VoiceController.prototype._applyPresenceSpeaking = function () {
    var presence = this.getPresenceController();
    if (presence && presence.engine && presence.engine.setSpeaking) {
      presence.engine.setSpeaking({ source: "voice" });
    }
    if (presence && presence.hookVoice) {
      presence.hookVoice({ phase: "speaking", waveStyle: "circular" });
    }
    if (this.neuralStage) {
      this.neuralStage.classList.remove("tdl-neural-stage--listening");
      this.neuralStage.classList.add("tdl-neural-stage--speaking");
    }
  };

  VoiceController.prototype._applyPresenceIdle = function () {
    var presence = this.getPresenceController();
    if (presence && presence.engine && presence.engine.setIdle) {
      presence.engine.setIdle({ source: "voice" });
    }
    if (this.neuralStage) {
      this.neuralStage.classList.remove("tdl-neural-stage--listening");
      this.neuralStage.classList.remove("tdl-neural-stage--speaking");
    }
    this.bus.emit(EVENTS.IDLE, {});
  };

  VoiceController.prototype._applyPresenceRipple = function (strength) {
    var presence = this.getPresenceController();
    if (presence && presence.engine && presence.engine.notifyInputRipple) {
      presence.engine.notifyInputRipple();
    }
    if (this.neuralStage) {
      var ripple = strength !== undefined ? strength : 0.5;
      this.neuralStage.style.setProperty("--tdl-voice-ripple", String(ripple));
    }
  };

  VoiceController.prototype._startSpeakPulse = function () {
    if (
      global.TitanMotion &&
      global.TitanMotion.prefersReducedMotion &&
      global.TitanMotion.prefersReducedMotion()
    ) {
      return;
    }
    var self = this;
    this._stopSpeakPulse();
    this._speakPulseTimer = setInterval(function () {
      self._triggerNeural("speaking", { phase: "rhythm_pulse" });
    }, 520);
  };

  VoiceController.prototype._stopSpeakPulse = function () {
    if (this._speakPulseTimer) {
      clearInterval(this._speakPulseTimer);
      this._speakPulseTimer = null;
    }
    if (this.neuralStage) {
      this.neuralStage.style.setProperty("--tdl-voice-ripple", "0");
    }
  };

  VoiceController.prototype._triggerNeural = function (hookName, payload) {
    var engine = this.getNeuralEngine();
    if (!engine) {
      return;
    }
    if (hookName === "speaking" && engine.triggerSpeaking) {
      engine.triggerSpeaking(payload);
    } else if (hookName === "voice" && engine.triggerVoice) {
      engine.triggerVoice(payload);
    } else if (engine.trigger) {
      engine.trigger(hookName, payload);
    }
  };

  VoiceController.prototype._setMicState = function (state) {
    if (!this.micBtn) {
      return;
    }
    var classes = [
      "tdl-voice-mic--idle",
      "tdl-voice-mic--listening",
      "tdl-voice-mic--speaking",
      "tdl-voice-mic--denied",
    ];
    for (var i = 0; i < classes.length; i++) {
      this.micBtn.classList.remove(classes[i]);
    }
    this.micBtn.classList.add("tdl-voice-mic--" + state);
    this.micBtn.setAttribute("aria-pressed", state === "listening" ? "true" : "false");
    this.micBtn.dataset.state = state;
  };

  VoiceController.prototype._updateMicAvailability = function () {
    if (!this.micBtn) {
      return;
    }
    var supported = this.isSupported() && this.config.enabled;
    this.micBtn.disabled = !supported;
    this.micBtn.title = supported
      ? "Maintenir pour parler"
      : "Voix non disponible dans ce navigateur";
  };

  VoiceController.prototype.destroy = function () {
    this.interrupt();
    this.bus.destroy();
    this._stopSpeakPulse();
  };

  global.TitanVoiceController = VoiceController;
})(window);
