/**
 * Titan Sound Hooks — optional audio architecture (Phase 18.0)
 *
 * No sounds are implemented. This module provides event hooks for future
 * ambient audio: startup chime, thinking ambience, notifications, voice fade.
 */
(function (global) {
  "use strict";

  var EVENTS = {
    STARTUP: "sound:startup",
    THINKING_START: "sound:thinking_start",
    THINKING_STOP: "sound:thinking_stop",
    NOTIFICATION: "sound:notification",
    VOICE_FADE_IN: "sound:voice_fade_in",
    VOICE_FADE_OUT: "sound:voice_fade_out",
  };

  function SoundHooks(options) {
    this._enabled = !!(options && options.enabled);
    this._listeners = {};
    for (var key in EVENTS) {
      if (Object.prototype.hasOwnProperty.call(EVENTS, key)) {
        this._listeners[EVENTS[key]] = [];
      }
    }
  }

  SoundHooks.prototype.isEnabled = function () {
    return this._enabled;
  };

  SoundHooks.prototype.setEnabled = function (enabled) {
    this._enabled = !!enabled;
  };

  SoundHooks.prototype.on = function (event, callback) {
    if (typeof callback !== "function" || !this._listeners[event]) {
      return;
    }
    this._listeners[event].push(callback);
  };

  SoundHooks.prototype.off = function (event, callback) {
    var list = this._listeners[event];
    if (!list) {
      return;
    }
    var idx = list.indexOf(callback);
    if (idx !== -1) {
      list.splice(idx, 1);
    }
  };

  SoundHooks.prototype.emit = function (event, payload) {
    if (!this._enabled) {
      return;
    }
    var list = this._listeners[event];
    if (!list) {
      return;
    }
    for (var i = 0; i < list.length; i++) {
      try {
        list[i](payload || {});
      } catch (_err) {
        /* sound hooks must never break UI */
      }
    }
  };

  SoundHooks.prototype.startup = function (payload) {
    this.emit(EVENTS.STARTUP, payload);
  };

  SoundHooks.prototype.thinkingStart = function (payload) {
    this.emit(EVENTS.THINKING_START, payload);
  };

  SoundHooks.prototype.thinkingStop = function (payload) {
    this.emit(EVENTS.THINKING_STOP, payload);
  };

  SoundHooks.prototype.notification = function (payload) {
    this.emit(EVENTS.NOTIFICATION, payload);
  };

  SoundHooks.prototype.voiceFadeIn = function (payload) {
    this.emit(EVENTS.VOICE_FADE_IN, payload);
  };

  SoundHooks.prototype.voiceFadeOut = function (payload) {
    this.emit(EVENTS.VOICE_FADE_OUT, payload);
  };

  global.TitanSoundHooks = SoundHooks;
  global.TitanSoundEvents = EVENTS;
})(window);
