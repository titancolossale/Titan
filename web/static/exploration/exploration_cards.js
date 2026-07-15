/**
 * Titan Exploration Cards — subtle floating source labels (Phase 23.0)
 *
 * Brief thematic source cards during web exploration. Never show raw URLs or HTML.
 */
(function (global) {
  "use strict";

  var DEFAULT_DURATION_MS = 3600;
  var STAGGER_MS = 320;

  function ExplorationCards(options) {
    this.layerEl = options.layerEl || null;
    this.durationMs = options.durationMs || DEFAULT_DURATION_MS;
    this._active = [];
    this._timers = [];
  }

  ExplorationCards.prototype.show = function (labels, options) {
    var self = this;
    if (!this.layerEl || !labels || !labels.length) {
      return;
    }

    var opts = options || {};
    var duration = opts.durationMs || this.durationMs;

    labels.forEach(function (label, index) {
      setTimeout(function () {
        self._spawnCard(label, duration, index);
      }, index * STAGGER_MS);
    });
  };

  ExplorationCards.prototype._spawnCard = function (label, duration, index) {
    var card = document.createElement("div");
    card.className = "tdl-memory-card tdl-source-card";
    card.textContent = label;
    card.setAttribute("role", "presentation");

    if (index % 3 === 1) {
      card.style.top = "30%";
      card.style.marginLeft = "-6rem";
    } else if (index % 3 === 2) {
      card.style.top = "46%";
      card.style.marginLeft = "5rem";
    }

    this.layerEl.appendChild(card);
    this._active.push(card);

    requestAnimationFrame(function () {
      card.classList.add("tdl-memory-card--visible");
    });

    var hideTimer = setTimeout(function () {
      card.classList.remove("tdl-memory-card--visible");
      card.classList.add("tdl-memory-card--fading");
    }, duration - 700);

    var removeTimer = setTimeout(
      function () {
        if (card.parentNode) {
          card.parentNode.removeChild(card);
        }
        var idx = this._active.indexOf(card);
        if (idx !== -1) {
          this._active.splice(idx, 1);
        }
      }.bind(this),
      duration
    );

    this._timers.push(hideTimer, removeTimer);
  };

  ExplorationCards.prototype.clear = function () {
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

  global.TitanExplorationCards = ExplorationCards;
})(window);
