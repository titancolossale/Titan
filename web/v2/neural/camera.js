/** Titan Neural Renderer V3 — Cinematic depth camera (micro-drift, breathe, recall dive). */

import { NEURAL_CONFIG } from "./config.js";
import { prefersReducedMotion } from "./utils.js";

export class NeuralCamera {
  constructor() {
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
    this._focusOffsetX = 0;
    this._focusOffsetY = 0;
    this._shakeDecay = 0;
    this._shakeX = 0;
    this._shakeY = 0;
    this.pointerX = 0;
    this.pointerY = 0;
    this.pointerTargetX = 0;
    this.pointerTargetY = 0;
  }

  /**
   * Set a subtle pointer-driven parallax target (disabled under reduced motion,
   * since update() early-returns and holds the camera centered in that case).
   * @param {number} nx normalized -1..1
   * @param {number} ny normalized -1..1
   */
  setPointerParallax(nx, ny) {
    this.pointerTargetX = Math.max(-1, Math.min(1, nx));
    this.pointerTargetY = Math.max(-1, Math.min(1, ny));
  }

  /** @param {number} width @param {number} height */
  resize(width, height) {
    this.width = width;
    this.height = height;
    const pad = NEURAL_CONFIG.world.padding;
    const expansion = NEURAL_CONFIG.infiniteSpace.worldExpansion || 0;
    this.worldWidth = width * (1 + pad * 2 + expansion);
    this.worldHeight = height * (1 + pad * 2 + expansion);
  }

  /**
   * @param {number} deltaMs
   * @param {number} intensity
   * @param {number} breathe
   * @param {import("./state.js").NeuralState} state
   * @param {number} [recallDive]
   * @param {{ x: number, y: number, pull: number } | null} [attraction]
   */
  update(deltaMs, intensity, breathe, state, recallDive, attraction) {
    const cfg = NEURAL_CONFIG.camera;
    const thinking = state?.isThinking?.() ?? false;
    const signature = state?.getCognitiveSignature?.() ?? null;

    if (recallDive !== undefined) {
      this.recallDive = recallDive;
    } else {
      this.recallDive = Math.max(0, this.recallDive - (cfg.recallDiveDecay || 0.0035) * (deltaMs / 16.67));
    }

    const targetFocus = thinking ? (signature?.focusPull ?? 1) : 0;
    this.focusPull += (targetFocus - this.focusPull) * 0.0028 * deltaMs;

    if (signature?.cameraDive !== undefined) {
      this.recallDive = Math.max(this.recallDive, signature.cameraDive * 0.85);
    }

    if (prefersReducedMotion()) {
      this.x = 0;
      this.y = 0;
      this.depthScale = 1;
      return;
    }

    const focusMult = 1 - this.focusPull * (1 - (cfg.thinkingFocusMult || 0.58));
    const idleBoost = thinking ? 1 : cfg.idleDriftBoost || 1.12;
    const boost = (1 + intensity * 0.32) * focusMult * idleBoost;

    this.phaseX += cfg.driftSpeedX * deltaMs * boost;
    this.phaseY += cfg.driftSpeedY * deltaMs * boost;
    this.breathePhase += (cfg.breatheZoomSpeed || 0.00035) * deltaMs;

    const ampX = this.width * cfg.amplitudeXRatio * focusMult;
    const ampY = this.height * cfg.amplitudeYRatio * focusMult;

    this.targetX = Math.sin(this.phaseX) * ampX;
    this.targetY = Math.cos(this.phaseY * 0.87) * ampY;

    const pointerEase = (cfg.pointerEase || 0.0045) * deltaMs;
    this.pointerX += (this.pointerTargetX - this.pointerX) * pointerEase;
    this.pointerY += (this.pointerTargetY - this.pointerY) * pointerEase;
    const pointerAmp = cfg.pointerParallaxRatio || 0.02;
    this.targetX += this.pointerX * this.width * pointerAmp * focusMult;
    this.targetY += this.pointerY * this.height * pointerAmp * focusMult;

    if (signature?.focusComposer) {
      const comm = { x: 0.15 * this.worldWidth, y: 0.76 * this.worldHeight };
      const pullStrength = 0.22 * (thinking ? 1.15 : 0.85);
      this._focusOffsetX += (comm.x - this.worldWidth * 0.5) * pullStrength * 0.00035 * deltaMs;
      this._focusOffsetY += (comm.y - this.worldHeight * 0.5) * pullStrength * 0.00035 * deltaMs;
    }

    if (attraction && attraction.pull > 0.05) {
      const pullStrength = attraction.pull * 0.18 * (thinking ? 1.2 : 0.6);
      this._focusOffsetX += (attraction.x - this.worldWidth * 0.5) * pullStrength * 0.0004 * deltaMs;
      this._focusOffsetY += (attraction.y - this.worldHeight * 0.5) * pullStrength * 0.0004 * deltaMs;
    }
    this._focusOffsetX *= 0.998;
    this._focusOffsetY *= 0.998;

    const ease = cfg.easing * deltaMs;
    this.x += (this.targetX + this._focusOffsetX - this.x) * ease;
    this.y += (this.targetY + this._focusOffsetY - this.y) * ease;

    const breatheVal = breathe ?? 0.5;
    const zoomAmp = cfg.breatheZoomAmplitude || 0.014;
    const thinkingZoom = 1 + this.focusPull * (cfg.thinkingZoomIn || 0.016);
    const recallScale = 1 - this.recallDive * (cfg.recallDiveScale || 0.055);
    this.depthScale =
      (1 + (breatheVal - 0.5) * zoomAmp * (1 + intensity * 0.12)) * thinkingZoom * recallScale;
  }

  /** @param {number} [amount] */
  boostRecallDive(amount) {
    this.recallDive = Math.min(1, this.recallDive + (amount || 0.35));
  }

  getRecallDive() {
    return this.recallDive;
  }

  getDepthScale() {
    return this.depthScale || 1;
  }

  /** @param {number} [parallax] */
  getParallaxOffset(parallax = 1) {
    const driftScale = this.getDepthScale();
    return { x: this.x * parallax * driftScale, y: this.y * parallax * driftScale };
  }

  /** @param {number} wx @param {number} wy @param {number} [parallax] */
  worldToScreen(wx, wy, parallax = 1) {
    const offset = this.getParallaxOffset(parallax);
    return {
      x: wx - offset.x - NEURAL_CONFIG.world.padding * this.width,
      y: wy - offset.y - NEURAL_CONFIG.world.padding * this.height,
    };
  }

  getOffset() {
    return { x: this.x, y: this.y };
  }

  getWorldBounds() {
    return { x: 0, y: 0, width: this.worldWidth, height: this.worldHeight };
  }

  /** CSS transform for DOM camera wrapper. */
  getDomTransform() {
    const scale = this.getDepthScale();
    return `translate(${this.x.toFixed(2)}px, ${this.y.toFixed(2)}px) scale(${scale.toFixed(4)})`;
  }
}
