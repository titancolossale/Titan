/**
 * Titan Voice Events — event-driven voice lifecycle (Phase 17.8)
 *
 * Provider-independent event bus for STT/TTS and presence synchronization.
 */
(function (global) {
  "use strict";

  var EVENTS = {
    READY: "voice:ready",
    ERROR: "voice:error",
    MODE_CHANGE: "voice:mode_change",

    LISTEN_START: "voice:listen_start",
    LISTEN_END: "voice:listen_end",
    LISTEN_PARTIAL: "voice:listen_partial",
    LISTEN_FINAL: "voice:listen_final",

    SPEAK_START: "voice:speak_start",
    SPEAK_CHUNK: "voice:speak_chunk",
    SPEAK_WORD: "voice:speak_word",
    SPEAK_END: "voice:speak_end",
    SPEAK_INTERRUPTED: "voice:speak_interrupted",

    THINKING: "voice:thinking",
    WORKING: "voice:working",
    IDLE: "voice:idle",

    INTERRUPT: "voice:interrupt",
    WAKE_WORD_ARMED: "voice:wake_word_armed",
    WAKE_WORD_DETECTED: "voice:wake_word_detected",
  };

  var MODES = {
    PUSH_TO_TALK: "push_to_talk",
    CONTINUOUS: "continuous",
    WAKE_WORD: "wake_word",
  };

  function VoiceEventBus() {
    this._listeners = {};
  }

  VoiceEventBus.prototype.on = function (event, callback) {
    if (typeof callback !== "function") {
      return;
    }
    if (!this._listeners[event]) {
      this._listeners[event] = [];
    }
    this._listeners[event].push(callback);
  };

  VoiceEventBus.prototype.off = function (event, callback) {
    var list = this._listeners[event];
    if (!list) {
      return;
    }
    var idx = list.indexOf(callback);
    if (idx !== -1) {
      list.splice(idx, 1);
    }
  };

  VoiceEventBus.prototype.emit = function (event, payload) {
    var list = this._listeners[event];
    if (!list) {
      return;
    }
    var envelope = {
      type: event,
      payload: payload || {},
      timestamp: performance.now(),
    };
    for (var i = 0; i < list.length; i++) {
      try {
        list[i](envelope);
      } catch (_err) {
        /* voice listeners must not break the pipeline */
      }
    }
  };

  VoiceEventBus.prototype.destroy = function () {
    this._listeners = {};
  };

  global.TitanVoiceEvents = {
    EVENTS: EVENTS,
    MODES: MODES,
    VoiceEventBus: VoiceEventBus,
  };
})(window);
