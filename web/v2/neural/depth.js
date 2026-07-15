/** Titan Neural Renderer V3 — Depth recall state (fog driven by renderer). */

import { NEURAL_CONFIG } from "./config.js";

export class DepthField {
  constructor() {
    this._infiniteEnabled = NEURAL_CONFIG.infiniteSpace.enabled !== false;
    this._depthBudget = 1;
    this._recallDepthBoost = 0;
  }

  setInfiniteEnabled(enabled) {
    this._infiniteEnabled = Boolean(enabled);
  }

  /** @param {number} budget */
  setDepthBudget(budget) {
    this._depthBudget = Math.max(0, Math.min(1, budget || 1));
  }

  getRecallDive() {
    return this._recallDepthBoost;
  }

  /** @param {number} [amount] */
  boostRecallDepth(amount) {
    this._recallDepthBoost = Math.min(1, this._recallDepthBoost + (amount || 0.35));
  }

  /**
   * @param {number} deltaMs
   * @param {import("./camera.js").NeuralCamera} camera
   * @param {import("./state.js").NeuralState} state
   */
  update(deltaMs, camera, state) {
    const dt = deltaMs / 16.67;
    this._recallDepthBoost = Math.max(0, this._recallDepthBoost - 0.0035 * dt);

    const signature = state?.getCognitiveSignature?.() ?? null;
    if (signature?.cameraDive > 0.2) {
      this._recallDepthBoost = Math.max(this._recallDepthBoost, signature.cameraDive * 0.55);
    }
  }

  /**
   * Canvas depth is rendered by NeuralRenderer V3 — no wallpaper draw pass.
   * @param {CanvasRenderingContext2D} _ctx
   * @param {import("./camera.js").NeuralCamera} _camera
   * @param {number} _w
   * @param {number} _h
   */
  draw(_ctx, _camera, _w, _h) {
    /* intentionally empty — depth fog lives in renderer */
  }
}
