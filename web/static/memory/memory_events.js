/**
 * Titan Memory Events — event-driven memory visualization lifecycle (Phase 17.9)
 *
 * Provider-independent bus for recall phases, neural pulses, and floating cards.
 */
(function (global) {
  "use strict";

  var EVENTS = {
    TURN_BEGIN: "memory:turn_begin",
    TURN_END: "memory:turn_end",
    SEARCH_START: "memory:search_start",
    SEARCH_PROGRESS: "memory:search_progress",
    RECALL: "memory:recall",
    CARD_SHOW: "memory:card_show",
    CARD_HIDE: "memory:card_hide",
    NEURAL_PULSE: "memory:neural_pulse",
    COMPLETE: "memory:complete",
    AMBIENT: "memory:ambient",
    STATUS_LINE: "memory:status_line",
  };

  function MemoryEventBus() {
    this._listeners = {};
  }

  MemoryEventBus.prototype.on = function (event, callback) {
    if (typeof callback !== "function") {
      return;
    }
    if (!this._listeners[event]) {
      this._listeners[event] = [];
    }
    this._listeners[event].push(callback);
  };

  MemoryEventBus.prototype.off = function (event, callback) {
    var list = this._listeners[event];
    if (!list) {
      return;
    }
    var idx = list.indexOf(callback);
    if (idx !== -1) {
      list.splice(idx, 1);
    }
  };

  MemoryEventBus.prototype.emit = function (event, payload) {
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
        /* memory listeners must not break the pipeline */
      }
    }
  };

  MemoryEventBus.prototype.destroy = function () {
    this._listeners = {};
  };

  global.TitanMemoryEvents = {
    EVENTS: EVENTS,
    MemoryEventBus: MemoryEventBus,
  };
})(window);
