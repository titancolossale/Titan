/** Titan Frontend V2 — Neural stage mount & renderer integration (Phase E3). */

import { NeuralEngine } from "./engine.js";
import { normalizeCognitiveState } from "./cognitive.js";

/** Master Blueprint — neural master state enum. */
export const NEURAL_MASTER_STATES = Object.freeze([
  "BOOTING",
  "AWAKE",
  "IDLE",
  "THINKING",
  "WORKING",
  "LISTENING",
  "SPEAKING",
  "DEPTH_RECALL",
  "ERROR",
  "SLEEP",
]);

export class NeuralStage {
  /**
   * @param {import("../layout/shell.js").Shell} shell
   */
  constructor(shell) {
    this._shell = shell;
    /** @type {HTMLElement | null} */
    this._host = null;
    /** @type {HTMLCanvasElement | null} */
    this._canvas = null;
    /** @type {HTMLElement | null} */
    this._cameraEl = null;
    /** @type {NeuralEngine | null} */
    this._engine = null;
    this._masterState = "BOOTING";
    this._cognitiveTag = "idle";
    this._pointerRaf = 0;
    this._boundPointer = (event) => this._onPointerMove(event);
  }

  mount() {
    this._host = this._shell.get("tdl-v2-neural-host");
    this._canvas = /** @type {HTMLCanvasElement | null} */ (
      this._shell.get("tdl-v2-neural-canvas")
    );
    this._cameraEl = this._host?.querySelector(".tdl-v2-neural-camera") ?? null;

    if (!this._host || !this._canvas) {
      return;
    }

    this._engine = new NeuralEngine(this._canvas, { cameraEl: this._cameraEl });
    this._engine.init();

    this._host.dataset.masterState = this._masterState;
    this._host.dataset.cognitiveTag = this._cognitiveTag;
    this._host.dataset.renderer = "v3";
    this._host.setAttribute("data-neural-ready", "true");

    this._activateDepthBands();
    this.setMasterState("BOOTING");

    window.addEventListener("pointermove", this._boundPointer, { passive: true });
  }

  /** @param {PointerEvent} event */
  _onPointerMove(event) {
    if (!this._engine || this._pointerRaf) return;
    this._pointerRaf = requestAnimationFrame(() => {
      this._pointerRaf = 0;
      const nx = (event.clientX / window.innerWidth) * 2 - 1;
      const ny = (event.clientY / window.innerHeight) * 2 - 1;
      this._engine?.setPointerParallax(nx, ny);
    });
  }

  _activateDepthBands() {
    if (!this._host) return;
    const bands = this._host.querySelectorAll(".tdl-v2-neural-depth-band");
    bands.forEach((band, i) => {
      /** @type {HTMLElement} */ (band).style.opacity = String(0.35 + i * 0.08);
    });
  }

  /** @returns {NeuralEngine | null} */
  getEngine() {
    return this._engine;
  }

  /** @param {string} state */
  setMasterState(state) {
    this._masterState = state;
    if (this._host) {
      this._host.dataset.masterState = state;
    }
    this._engine?.setMasterState(state);
  }

  /** @param {string} tag */
  setCognitiveTag(tag) {
    this._cognitiveTag = tag;
    if (this._host) {
      this._host.dataset.cognitiveTag = tag;
    }
    this._engine?.setCognitiveState(normalizeCognitiveState(tag));
  }

  /** @param {number} level 0–1 */
  setActivityLevel(level) {
    if (this._host) {
      this._host.dataset.activityLevel = String(level);
    }
    if (level > 0.5) {
      this._engine?.setMode("thinking");
    } else if (level < 0.15) {
      this._engine?.setMode("idle");
    }
  }

  /** @param {string} hookName @param {object} [payload] */
  trigger(hookName, payload) {
    this._engine?.trigger(hookName, payload);
  }

  /** @param {object | null} blend */
  applyToolActivity(blend) {
    this._engine?.applyToolActivity(blend);
  }

  /** @param {object | null} blend @param {{ triggerHooks?: boolean }} [options] */
  applyMemoryActivity(blend, options) {
    this._engine?.applyMemoryActivity(blend, options);
  }

  /** @param {object | null} blend @param {{ triggerHooks?: boolean, eventType?: string }} [options] */
  applyConversationActivity(blend, options) {
    this._engine?.applyConversationActivity(blend, options);
  }

  destroy() {
    window.removeEventListener("pointermove", this._boundPointer);
    if (this._pointerRaf) {
      cancelAnimationFrame(this._pointerRaf);
      this._pointerRaf = 0;
    }
    this._engine?.destroy();
    this._engine = null;
  }
}
