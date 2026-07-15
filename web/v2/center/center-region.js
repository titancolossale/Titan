/** Titan Frontend V2 — Center neural core overlay (Sprint 2 · Living Neural Core V1).
 *
 * Owns the DOM overlay that frames Titan's living neural core: the dominant
 * Titan Core label, the ring of cognitive satellites with neural links, and the
 * activity HUD. Rendering is delegated to CognitiveSatelliteField; behavior and
 * satellite statuses are derived from the shared StateStore via the pure
 * NeuralStatusAdapter. This region reads state only — it never mutates backend
 * capabilities and gracefully falls back to IDLE when state is unavailable.
 */

import { CognitiveSatelliteField } from "./cognitive-satellites.js";
import { resolveNeuralStatus } from "./neural-status-adapter.js";

export class CenterRegion {
  /**
   * @param {import("../layout/shell.js").Shell} shell
   * @param {import("../core/state-store.js").StateStore} store
   */
  constructor(shell, store) {
    this._shell = shell;
    this._store = store;
    /** @type {import("../core/cognitive-state-engine.js").CognitiveStateEngine | null} */
    this._brain = null;
    /** @type {HTMLElement | null} */
    this._labelsHost = null;
    /** @type {CognitiveSatelliteField | null} */
    this._field = null;
    /** @type {(() => void) | null} */
    this._unsubscribe = null;
    this._pointerRaf = 0;
    this._onPointerMove = (event) => this._handlePointer(event);
  }

  /** @param {import("../core/cognitive-state-engine.js").CognitiveStateEngine} brain */
  setBrain(brain) {
    this._brain = brain;
    this._sync();
  }

  mount() {
    const labelsHost = this._shell.get("tdl-v2-neural-labels");
    if (!labelsHost) {
      return;
    }
    this._labelsHost = labelsHost;

    this._field = new CognitiveSatelliteField(labelsHost);
    this._field.mount();

    labelsHost.appendChild(this._createHud());

    this._unsubscribe = this._store.subscribe(() => this._sync());
    window.addEventListener("pointermove", this._onPointerMove, { passive: true });

    this._sync();
  }

  _createHud() {
    const hud = document.createElement("div");
    hud.className = "tdl-v2-center-hud";
    hud.setAttribute("aria-hidden", "true");
    hud.innerHTML = `
      <div class="tdl-v2-center-hud__panel tdl-v2-center-hud__panel--activity">
        <span class="tdl-v2-center-hud__title">Activité Neurale</span>
        <div class="tdl-v2-center-hud__sparkline" id="tdl-v2-center-activity-spark"></div>
      </div>
      <div class="tdl-v2-center-hud__panel tdl-v2-center-hud__panel--focus">
        <span class="tdl-v2-center-hud__title">Focus Actuel</span>
        <span class="tdl-v2-center-hud__focus-icon" aria-hidden="true"></span>
      </div>
    `;
    return hud;
  }

  /** Recompute the neural status from current app state and apply it. */
  _sync() {
    if (!this._field) return;
    const status = resolveNeuralStatus(this._store.getState());
    this._field.apply(status);
  }

  /** @param {PointerEvent} event */
  _handlePointer(event) {
    if (!this._field || this._store.getState().reducedMotion) {
      return;
    }
    if (this._pointerRaf) return;
    this._pointerRaf = requestAnimationFrame(() => {
      this._pointerRaf = 0;
      const nx = (event.clientX / window.innerWidth) * 2 - 1;
      const ny = (event.clientY / window.innerHeight) * 2 - 1;
      this._field?.setParallax(nx, ny);
    });
  }

  destroy() {
    if (this._pointerRaf) {
      cancelAnimationFrame(this._pointerRaf);
      this._pointerRaf = 0;
    }
    window.removeEventListener("pointermove", this._onPointerMove);
    this._unsubscribe?.();
    this._unsubscribe = null;
    this._field?.destroy();
    this._field = null;
  }
}
