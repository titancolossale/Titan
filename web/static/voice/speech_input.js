/**
 * Titan Speech Input — STT with push-to-talk and continuous modes (Phase 17.8)
 *
 * Browser Web Speech API provider today; swappable via provider interface.
 */
(function (global) {
  "use strict";

  var VoiceEvents = global.TitanVoiceEvents;
  var EVENTS = VoiceEvents.EVENTS;
  var MODES = VoiceEvents.MODES;

  function getSpeechRecognition() {
    return (
      global.SpeechRecognition ||
      global.webkitSpeechRecognition ||
      null
    );
  }

  /**
   * Future wake-word detector — architecture stub only (Phase 17.8).
   */
  function WakeWordDetector(options) {
    this.enabled = false;
    this.phrase = (options && options.phrase) || "titan";
    this.onDetect = (options && options.onDetect) || null;
  }

  WakeWordDetector.prototype.arm = function () {
    this.enabled = true;
  };

  WakeWordDetector.prototype.disarm = function () {
    this.enabled = false;
  };

  WakeWordDetector.prototype.processTranscript = function (text) {
    if (!this.enabled || !text) {
      return false;
    }
    var lower = text.toLowerCase();
    if (lower.indexOf(this.phrase) !== -1) {
      if (this.onDetect) {
        this.onDetect(text);
      }
      return true;
    }
    return false;
  };

  function BrowserSpeechInputProvider(options) {
    this.locale = (options && options.locale) || "fr-FR";
    this.continuous = !!(options && options.continuous);
    this.interimResults = options && options.interimResults !== false;
    this._recognition = null;
    this._active = false;
    this._callbacks = {};
  }

  BrowserSpeechInputProvider.prototype.isSupported = function () {
    return !!getSpeechRecognition();
  };

  BrowserSpeechInputProvider.prototype._ensureRecognition = function () {
    if (this._recognition) {
      return this._recognition;
    }
    var SpeechRecognition = getSpeechRecognition();
    if (!SpeechRecognition) {
      return null;
    }

    var recognition = new SpeechRecognition();
    recognition.lang = this.locale;
    recognition.continuous = this.continuous;
    recognition.interimResults = this.interimResults;
    recognition.maxAlternatives = 1;

    var self = this;
    recognition.onresult = function (event) {
      var interim = "";
      var finalText = "";

      for (var i = event.resultIndex; i < event.results.length; i++) {
        var result = event.results[i];
        var transcript = result[0] ? result[0].transcript : "";
        if (result.isFinal) {
          finalText += transcript;
        } else {
          interim += transcript;
        }
      }

      if (interim && self._callbacks.onPartial) {
        self._callbacks.onPartial(interim.trim());
      }
      if (finalText && self._callbacks.onFinal) {
        self._callbacks.onFinal(finalText.trim());
      }
    };

    recognition.onerror = function (event) {
      self._active = false;
      if (self._callbacks.onError) {
        self._callbacks.onError(event.error || "recognition_error");
      }
    };

    recognition.onend = function () {
      var wasActive = self._active;
      self._active = false;
      if (self._callbacks.onEnd) {
        self._callbacks.onEnd(wasActive);
      }
    };

    this._recognition = recognition;
    return recognition;
  };

  BrowserSpeechInputProvider.prototype.start = function (callbacks) {
    var recognition = this._ensureRecognition();
    if (!recognition) {
      if (callbacks && callbacks.onError) {
        callbacks.onError("not_supported");
      }
      return false;
    }

    this._callbacks = callbacks || {};
    if (this._active) {
      return true;
    }

    try {
      recognition.lang = this.locale;
      recognition.continuous = this.continuous;
      recognition.start();
      this._active = true;
      return true;
    } catch (err) {
      if (callbacks && callbacks.onError) {
        callbacks.onError(err && err.message ? err.message : "start_failed");
      }
      return false;
    }
  };

  BrowserSpeechInputProvider.prototype.stop = function () {
    if (!this._recognition || !this._active) {
      return;
    }
    try {
      this._recognition.stop();
    } catch (_err) {
      /* already stopped */
    }
    this._active = false;
  };

  BrowserSpeechInputProvider.prototype.abort = function () {
    if (!this._recognition) {
      return;
    }
    try {
      this._recognition.abort();
    } catch (_err) {
      /* ignore */
    }
    this._active = false;
  };

  BrowserSpeechInputProvider.prototype.isActive = function () {
    return this._active;
  };

  function SpeechInput(options) {
    this.bus = options.bus;
    this.locale = options.locale || "fr-FR";
    this.mode = options.mode || MODES.PUSH_TO_TALK;
    this.continuousPreferred = !!options.continuousPreferred;

    this.provider = options.provider || new BrowserSpeechInputProvider({
      locale: this.locale,
      continuous: this.mode === MODES.CONTINUOUS,
    });

    this.wakeWord = new WakeWordDetector({
      phrase: "titan",
      onDetect: this._onWakeWord.bind(this),
    });

    this._listening = false;
    this._accumulatedFinal = "";
  }

  SpeechInput.prototype.isSupported = function () {
    return this.provider.isSupported();
  };

  SpeechInput.prototype.setMode = function (mode) {
    this.mode = mode;
    this.provider.continuous = mode === MODES.CONTINUOUS;
    if (this.bus) {
      this.bus.emit(EVENTS.MODE_CHANGE, { mode: mode });
    }
  };

  SpeechInput.prototype.getMode = function () {
    return this.mode;
  };

  SpeechInput.prototype.startListening = function () {
    if (this._listening) {
      return true;
    }

    this._accumulatedFinal = "";
    var self = this;

    var started = this.provider.start({
      onPartial: function (text) {
        if (self.bus) {
          self.bus.emit(EVENTS.LISTEN_PARTIAL, { text: text });
        }
      },
      onFinal: function (text) {
        if (!text) {
          return;
        }
        self._accumulatedFinal = self._accumulatedFinal
          ? self._accumulatedFinal + " " + text
          : text;
        if (self.bus) {
          self.bus.emit(EVENTS.LISTEN_FINAL, { text: text, accumulated: self._accumulatedFinal });
        }
        if (self.mode === MODES.WAKE_WORD) {
          self.wakeWord.processTranscript(text);
        }
      },
      onError: function (code) {
        self._listening = false;
        if (self.bus) {
          self.bus.emit(EVENTS.ERROR, { phase: "listen", code: code });
        }
      },
      onEnd: function () {
        self._listening = false;
        var transcript = self._accumulatedFinal.trim();
        if (self.bus) {
          self.bus.emit(EVENTS.LISTEN_END, { transcript: transcript });
        }
      },
    });

    if (started) {
      this._listening = true;
      if (this.bus) {
        this.bus.emit(EVENTS.LISTEN_START, { mode: this.mode });
      }
    }
    return started;
  };

  SpeechInput.prototype.stopListening = function () {
    if (!this._listening) {
      return "";
    }
    this.provider.stop();
    return this._accumulatedFinal.trim();
  };

  SpeechInput.prototype.abortListening = function () {
    this.provider.abort();
    this._listening = false;
    this._accumulatedFinal = "";
  };

  SpeechInput.prototype.isListening = function () {
    return this._listening;
  };

  SpeechInput.prototype.armWakeWord = function () {
    this.wakeWord.arm();
    if (this.bus) {
      this.bus.emit(EVENTS.WAKE_WORD_ARMED, { phrase: this.wakeWord.phrase });
    }
  };

  SpeechInput.prototype._onWakeWord = function (text) {
    if (this.bus) {
      this.bus.emit(EVENTS.WAKE_WORD_DETECTED, { text: text });
    }
  };

  global.TitanSpeechInput = {
    SpeechInput: SpeechInput,
    BrowserSpeechInputProvider: BrowserSpeechInputProvider,
    WakeWordDetector: WakeWordDetector,
  };
})(window);
