/**
 * Titan Launch Sequence — entering Titan's mind (Phase 18.0 · 19.1)
 *
 * Brain wakes from void, ambient presence emerges, greeting under 2 seconds.
 * Respects reduced motion — instant reveal when animations are disabled.
 */
(function (global) {
  "use strict";

  var Motion = global.TitanMotion;
  var TOTAL_MS = 2200;

  function LaunchSequence(options) {
    this.overlay = options.overlay || null;
    this.statusEl = options.statusEl || null;
    this.appRoot = options.appRoot || null;
    this.ambientGlow = options.ambientGlow || null;
    this.neuralCanvas = options.neuralCanvas || null;
    this.getUserName = options.getUserName || function () {
      return "Nolan";
    };
    this.onComplete = options.onComplete || null;
    this.soundHooks = options.soundHooks || null;
    this._timers = [];
  }

  LaunchSequence.prototype._schedule = function (fn, delayMs) {
    var id = global.setTimeout(fn, delayMs);
    this._timers.push(id);
    return id;
  };

  LaunchSequence.prototype._clearTimers = function () {
    for (var i = 0; i < this._timers.length; i++) {
      clearTimeout(this._timers[i]);
    }
    this._timers = [];
  };

  LaunchSequence.prototype._setStatus = function (text) {
    if (this.statusEl) {
      this.statusEl.textContent = text;
    }
  };

  LaunchSequence.prototype._finish = function () {
    this._clearTimers();
    if (document.body) {
      document.body.classList.remove("tdl-page--launching");
      document.body.classList.add("tdl-page--ready");
    }
    if (this.overlay) {
      this.overlay.classList.remove("tdl-launch--active");
      this.overlay.classList.add("tdl-launch--done");
    }
    if (this.neuralCanvas) {
      this.neuralCanvas.classList.remove("tdl-neural-canvas--booting");
      this.neuralCanvas.classList.add("tdl-neural-canvas--awake");
    }
    if (typeof this.onComplete === "function") {
      this.onComplete();
    }
  };

  LaunchSequence.prototype.run = function () {
    var self = this;
    var name = this.getUserName();

    if (document.body) {
      document.body.classList.add("tdl-page--launching");
    }
    if (this.overlay) {
      this.overlay.hidden = false;
      requestAnimationFrame(function () {
        self.overlay.classList.add("tdl-launch--active");
      });
    }
    if (this.neuralCanvas) {
      this.neuralCanvas.classList.add("tdl-neural-canvas--booting");
    }

    if (this.soundHooks && this.soundHooks.startup) {
      this.soundHooks.startup({ user: name });
    }

    if (Motion && Motion.prefersReducedMotion()) {
      this._setStatus("Je suis là.");
      this._finish();
      return;
    }

    this._schedule(function () {
      if (self.neuralCanvas) {
        self.neuralCanvas.classList.add("tdl-neural-canvas--awake");
      }
      if (self.ambientGlow) {
        self.ambientGlow.classList.add("tdl-glow-ambient--launch");
      }
    }, 320);

    this._schedule(function () {
      self._setStatus("Connexion à l'esprit de Titan…");
    }, 480);

    this._schedule(function () {
      self._setStatus("Bonjour " + name + ".");
    }, 980);

    this._schedule(function () {
      self._setStatus("Je suis là.");
    }, 1580);

    this._schedule(function () {
      self._finish();
    }, TOTAL_MS);
  };

  LaunchSequence.prototype.destroy = function () {
    this._clearTimers();
  };

  global.TitanLaunchSequence = LaunchSequence;
})(window);
