/** Titan Frontend V2 — Layout engine (Production Spec §1). */

import { ORCHESTRATOR_FOCUS, REGION_IDS, resolveViewportMode } from "./regions.js";

export class LayoutEngine {
  /**
   * @param {import("./shell.js").Shell} shell
   */
  constructor(shell) {
    this._shell = shell;
  }

  init() {
    const state = { viewportMode: resolveViewportMode(window.innerWidth) };
    this.apply({ ...state, settingsOpen: false, orchestratorDrawerOpen: false });
  }

  /** @param {import("../core/state-store.js").AppState} state */
  apply(state) {
    const root = this._shell.root;
    if (!root) {
      return;
    }

    const mode = state.viewportMode || resolveViewportMode(window.innerWidth);
    root.dataset.mode = mode;
    root.classList.remove(
      "tdl-v2--mode-phone",
      "tdl-v2--mode-tablet",
      "tdl-v2--mode-laptop",
      "tdl-v2--mode-desktop",
      "tdl-v2--mode-wide",
      "tdl-v2--mode-ultrawide",
    );
    root.classList.add(`tdl-v2--mode-${mode}`);

    const orchestrator = this._shell.get(REGION_IDS.orchestrator);
    if (orchestrator) {
      orchestrator.dataset.drawerOpen = String(state.orchestratorDrawerOpen);
    }

    const overlay = this._shell.get("tdl-v2-overlay-layer");
    if (overlay) {
      overlay.dataset.active = String(state.settingsOpen);
    }
  }

  /** @param {import("../core/state-store.js").AppState} state */
  applyAccessibility(state) {
    const root = this._shell.root;
    if (!root) {
      return;
    }

    root.classList.toggle("tdl-v2--reduced-motion", state.reducedMotion);
    root.classList.toggle("tdl-v2--high-contrast", state.highContrast);
    root.classList.remove("tdl-v2--font-scale-112", "tdl-v2--font-scale-125");

    if (state.fontScale === 112) {
      root.classList.add("tdl-v2--font-scale-112");
    } else if (state.fontScale === 125) {
      root.classList.add("tdl-v2--font-scale-125");
    }
  }

  /** @param {string} routeKey */
  setOrchestratorFocus(routeKey) {
    const orchestrator = this._shell.get(REGION_IDS.orchestrator);
    if (!orchestrator) {
      return;
    }

    const focus = ORCHESTRATOR_FOCUS[routeKey] ?? [];
    orchestrator.dataset.focus = focus.join(",");
  }

  getCenterSlot() {
    return this._shell.get(REGION_IDS.centerSlot);
  }

  /** @returns {Record<string, HTMLElement | null>} */
  getStaggerTargets() {
    return {
      sidebar: this._shell.get(REGION_IDS.sidebar),
      main: this._shell.get(REGION_IDS.main),
      orchestrator: this._shell.get(REGION_IDS.orchestrator),
      dock: this._shell.get(REGION_IDS.dock),
    };
  }
}
