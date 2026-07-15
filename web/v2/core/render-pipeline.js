/** Titan Frontend V2 — Render pipeline orchestration (Phase E1). */

import { SCREEN_TRANSITION } from "../animation/tokens.js";

/**
 * Coordinates layout → panel mount → animation hooks per frame/route change.
 */
export class RenderPipeline {
  /**
   * @param {Object} deps
   * @param {import("./state-store.js").StateStore} deps.store
   * @param {import("../layout/layout-engine.js").LayoutEngine} deps.layoutEngine
   * @param {import("../panels/panel-mount.js").PanelMount} deps.panelMount
   * @param {import("../animation/animation-engine.js").AnimationEngine} deps.animationEngine
   */
  constructor({ store, layoutEngine, panelMount, animationEngine }) {
    this._store = store;
    this._layoutEngine = layoutEngine;
    this._panelMount = panelMount;
    this._animationEngine = animationEngine;
    this._unsubscribers = [];
  }

  start() {
    this._unsubscribers.push(
      this._store.subscribe((state, patch) => {
        if ("viewportMode" in patch || "settingsOpen" in patch || "orchestratorDrawerOpen" in patch) {
          this._layoutEngine.apply(state);
        }

        if ("route" in patch || "activePanelId" in patch) {
          this._handleRouteChange(state, patch);
        }

        if ("reducedMotion" in patch || "highContrast" in patch || "fontScale" in patch) {
          this._layoutEngine.applyAccessibility(state);
        }
      }),
    );

    this._layoutEngine.apply(this._store.getState());
  }

  /** Cold boot sequence — launch stagger without neural renderer. */
  async boot() {
    const regions = this._layoutEngine.getStaggerTargets();
    const { runPanelStagger } = await import("../animation/stagger.js");
    runPanelStagger(this._animationEngine, regions);

    this._store.setState({ bootComplete: true, presence: "idle" });
  }

  /** @param {import("./state-store.js").AppState} state @param {Partial<import("./state-store.js").AppState>} patch */
  _handleRouteChange(state, patch) {
    const route = patch.route ?? state.route;
    const panelId = state.activePanelId ?? route;

    if (!panelId) {
      return;
    }

    const slot = this._layoutEngine.getCenterSlot();
    if (!slot) {
      return;
    }

    this._panelMount.transitionTo(slot, panelId, {
      duration: SCREEN_TRANSITION.duration,
      reducedMotion: state.reducedMotion,
    });

    this._layoutEngine.setOrchestratorFocus(route);
  }

  destroy() {
    this._unsubscribers.forEach((unsub) => unsub());
    this._unsubscribers = [];
  }
}
