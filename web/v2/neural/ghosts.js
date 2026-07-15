/** Titan Neural Renderer V2 — Ghost node layer (memory recall). */

import { NEURAL_CONFIG } from "./config.js";
import { NODE_CLASSES, createNodeVitality } from "./node-classes.js";
import { rand } from "./utils.js";

export class GhostLayer {
  constructor() {
    /** @type {Array<object>} */
    this.ghosts = [];
    this._targetOpacity = 0;
    this._currentOpacity = 0;
    this._built = false;
  }

  /** @param {import("./camera.js").NeuralCamera} camera */
  build(camera) {
    if (this._built) return;
    const count = NEURAL_CONFIG.depth.ghostCount;
    const bounds = camera.getWorldBounds();
    this.ghosts = [];

    for (let i = 0; i < count; i++) {
      const vitality = createNodeVitality(NODE_CLASSES.GHOST);
      this.ghosts.push({
        id: `ghost-${i}`,
        x: rand(bounds.width * 0.08, bounds.width * 0.92),
        y: rand(bounds.height * 0.08, bounds.height * 0.92),
        vx: rand(-0.012, 0.012),
        vy: rand(-0.012, 0.012),
        radius: rand(0.4, 1.1),
        parallax: rand(0.12, 0.45),
        pulse: rand(0, Math.PI * 2),
        pulseSpeed: rand(0.003, 0.008),
        nodeClass: NODE_CLASSES.GHOST,
        ...vitality,
        fadeIn: 0,
      });
    }
    this._built = true;
  }

  /** @param {boolean} active @param {number} deltaMs */
  setRecallActive(active, deltaMs) {
    const target = active ? 1 : 0;
    const speed = active ? 0.0028 : 0.0018;
    this._targetOpacity = target;
    if (this._currentOpacity < target) {
      this._currentOpacity = Math.min(target, this._currentOpacity + speed * deltaMs);
    } else {
      this._currentOpacity = Math.max(target, this._currentOpacity - speed * deltaMs);
    }
  }

  /** @param {number} deltaMs @param {import("./camera.js").NeuralCamera} camera */
  update(deltaMs, camera) {
    if (this._currentOpacity < 0.01) return;
    this.build(camera);
    const dt = deltaMs / 16.67;
    const bounds = camera.getWorldBounds();

    for (const g of this.ghosts) {
      g.x += g.vx * dt;
      g.y += g.vy * dt;
      g.pulse += g.pulseSpeed * dt;
      g.fadeIn = Math.min(1, g.fadeIn + 0.0016 * deltaMs);

      if (g.x < 0) g.x = bounds.width;
      if (g.x > bounds.width) g.x = 0;
      if (g.y < 0) g.y = bounds.height;
      if (g.y > bounds.height) g.y = 0;

      g.energy = 0.2 + Math.sin(g.pulse) * 0.08;
      g.activity = g.fadeIn * this._currentOpacity * 0.6;
    }
  }

  getOpacity() {
    return this._currentOpacity;
  }

  isActive() {
    return this._currentOpacity > 0.02;
  }
}
