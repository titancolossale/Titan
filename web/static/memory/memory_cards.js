/**
 * Titan Memory Cards — subtle floating recall labels (Phase 17.9)
 *
 * Brief thematic cards during reasoning. Never show raw memory content.
 */
(function (global) {
  "use strict";

  var DEFAULT_DURATION_MS = 3200;
  var STAGGER_MS = 280;

  function MemoryCards(options) {
    this.layerEl = options.layerEl || null;
    this.durationMs = options.durationMs || DEFAULT_DURATION_MS;
    this._active = [];
    this._timers = [];
  }

  MemoryCards.prototype.show = function (labels, options) {
    var self = this;
    if (!this.layerEl || !labels || !labels.length) {
      return;
    }

    var opts = options || {};
    var duration = opts.durationMs || this.durationMs;

    labels.forEach(function (label, index) {
      setTimeout(function () {
        self._spawnCard(label, duration);
      }, index * STAGGER_MS);
    });
  };

  MemoryCards.prototype._spawnCard = function (label, duration) {
    var card = document.createElement("div");
    card.className = "tdl-memory-card";
    card.textContent = label;
    card.setAttribute("role", "presentation");

    this.layerEl.appendChild(card);
    this._active.push(card);

    requestAnimationFrame(function () {
      card.classList.add("tdl-memory-card--visible");
    });

    var hideTimer = setTimeout(function () {
      card.classList.remove("tdl-memory-card--visible");
      card.classList.add("tdl-memory-card--fading");
    }, duration - 600);

    var removeTimer = setTimeout(function () {
      if (card.parentNode) {
        card.parentNode.removeChild(card);
      }
      var idx = this._active.indexOf(card);
      if (idx !== -1) {
        this._active.splice(idx, 1);
      }
    }.bind(this), duration);

    this._timers.push(hideTimer, removeTimer);
  };

  MemoryCards.prototype.clear = function () {
    this._timers.forEach(function (timer) {
      clearTimeout(timer);
    });
    this._timers = [];

    this._active.forEach(function (card) {
      if (card.parentNode) {
        card.parentNode.removeChild(card);
      }
    });
    this._active = [];
  };

  MemoryCards.prototype.attach = function (bus, events) {
    var self = this;
    if (!bus || !events) {
      return;
    }

    bus.on(events.RECALL, function (envelope) {
      var cards = envelope.payload && envelope.payload.cards;
      if (cards && cards.length) {
        self.show(cards);
      }
    });

    bus.on(events.CARD_SHOW, function (envelope) {
      var label = envelope.payload && envelope.payload.label;
      if (label) {
        self.show([label], envelope.payload);
      }
    });

    bus.on(events.TURN_END, function () {
      self.clear();
    });
  };

  global.TitanMemoryCards = MemoryCards;
})(window);
