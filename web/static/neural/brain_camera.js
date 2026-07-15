/**
 * Titan Neural Brain Engine — Camera
 * Phase 17.4 · Phase 19.1 · Phase 19.2 — drift, breathing, recall dive, thinking focus
 */
(function (global) {
  "use strict";

  var TitanNeural = (global.TitanNeural = global.TitanNeural || {});
  var CONFIG = TitanNeural.CONFIG;

  function BrainCamera() {
    this.x = 0;
    this.y = 0;
    this.targetX = 0;
    this.targetY = 0;
    this.phaseX = Math.random() * Math.PI * 2;
    this.phaseY = Math.random() * Math.PI * 2;
    this.breathePhase = Math.random() * Math.PI * 2;
    this.width = 0;
    this.height = 0;
    this.worldWidth = 0;
    this.worldHeight = 0;
    this.depthScale = 1;
    this.recallDive = 0;
    this.focusPull = 0;
  }

  BrainCamera.prototype.resize = function (width, height) {
    this.width = width;
    this.height = height;
    var pad = CONFIG.world.padding;
    var expansion =
      (CONFIG.infiniteSpace && CONFIG.infiniteSpace.worldExpansion) || 0;
    this.worldWidth = width * (1 + pad * 2 + expansion);
    this.worldHeight = height * (1 + pad * 2 + expansion);
  };

  BrainCamera.prototype.update = function (deltaMs, intensity, breathe, state, recallDive) {
    var cfg = CONFIG.camera;
    var thinking = state && state.isThinking ? state.isThinking() : false;
    var signature = state && state.getCognitiveSignature ? state.getCognitiveSignature() : null;
    var recall = recallDive !== undefined ? recallDive : this.recallDive;

    if (recallDive !== undefined) {
      this.recallDive = recallDive;
    } else {
      this.recallDive = Math.max(
        0,
        this.recallDive - (cfg.recallDiveDecay || 0.0035) * (deltaMs / 16.67)
      );
    }

    var targetFocus = thinking
      ? signature && signature.focusPull !== undefined
        ? signature.focusPull
        : 1
      : 0;
    this.focusPull += (targetFocus - this.focusPull) * 0.0028 * deltaMs;

    if (signature && signature.cameraDive !== undefined) {
      this.recallDive = Math.max(this.recallDive, signature.cameraDive * 0.85);
    }

    var focusMult = 1 - this.focusPull * (1 - (cfg.thinkingFocusMult || 0.58));
    var idleBoost = thinking ? 1 : cfg.idleDriftBoost || 1.12;
    var boost = (1 + intensity * 0.32) * focusMult * idleBoost;

    this.phaseX += cfg.driftSpeedX * deltaMs * boost;
    this.phaseY += cfg.driftSpeedY * deltaMs * boost;
    this.breathePhase += (cfg.breatheZoomSpeed || 0.00035) * deltaMs;

    var ampX = this.width * cfg.amplitudeXRatio * focusMult;
    var ampY = this.height * cfg.amplitudeYRatio * focusMult;

    this.targetX = Math.sin(this.phaseX) * ampX;
    this.targetY = Math.cos(this.phaseY * 0.87) * ampY;

    var ease = cfg.easing * deltaMs;
    this.x += (this.targetX - this.x) * ease;
    this.y += (this.targetY - this.y) * ease;

    var breatheVal = breathe !== undefined ? breathe : 0.5;
    var zoomAmp = cfg.breatheZoomAmplitude || 0.014;
    var thinkingZoom = 1 + this.focusPull * (cfg.thinkingZoomIn || 0.016);
    var recallScale = 1 - this.recallDive * (cfg.recallDiveScale || 0.055);
    this.depthScale =
      (1 + (breatheVal - 0.5) * zoomAmp * (1 + intensity * 0.12)) *
      thinkingZoom *
      recallScale;
  };

  BrainCamera.prototype.boostRecallDive = function (amount) {
    this.recallDive = Math.min(1, this.recallDive + (amount || 0.35));
  };

  BrainCamera.prototype.getRecallDive = function () {
    return this.recallDive;
  };

  BrainCamera.prototype.getDepthScale = function () {
    return this.depthScale || 1;
  };

  BrainCamera.prototype.getParallaxOffset = function (parallax) {
    var p = parallax !== undefined ? parallax : 1;
    var driftScale = this.getDepthScale();
    return {
      x: this.x * p * driftScale,
      y: this.y * p * driftScale,
    };
  };

  BrainCamera.prototype.worldToScreen = function (wx, wy, parallax) {
    var offset = this.getParallaxOffset(parallax);
    return {
      x: wx - offset.x - CONFIG.world.padding * this.width,
      y: wy - offset.y - CONFIG.world.padding * this.height,
    };
  };

  BrainCamera.prototype.getOffset = function () {
    return { x: this.x, y: this.y };
  };

  BrainCamera.prototype.getWorldBounds = function () {
    return {
      x: 0,
      y: 0,
      width: this.worldWidth,
      height: this.worldHeight,
    };
  };

  TitanNeural.BrainCamera = BrainCamera;
})(window);
