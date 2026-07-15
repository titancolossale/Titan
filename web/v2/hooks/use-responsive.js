/** Titan Frontend V2 — Responsive engine (Production Spec §1.7–1.10). */

import { resolveViewportMode } from "../layout/regions.js";

export class ResponsiveEngine {
  /**
   * @param {import("../core/state-store.js").StateStore} store
   */
  constructor(store) {
    this._store = store;
    this._mq = null;
    this._onResize = this._onResize.bind(this);
  }

  start() {
    this._onResize();
    window.addEventListener("resize", this._onResize, { passive: true });
  }

  stop() {
    window.removeEventListener("resize", this._onResize);
  }

  _onResize() {
    const width = window.innerWidth;
    const mode = resolveViewportMode(width);
    const prev = this._store.getState().viewportMode;

    if (mode === prev) {
      return;
    }

    const patch = { viewportMode: mode };

    if (mode === "desktop" || mode === "wide" || mode === "ultrawide" || mode === "laptop") {
      patch.orchestratorDrawerOpen = false;
    }

    if (mode === "phone") {
      patch.sidebarDrawerOpen = false;
    }

    this._store.setState(patch);
  }
}

/** Hook-style accessor for subscribers. */
export function createResponsiveSubscription(store, listener) {
  return store.subscribe((state, patch) => {
    if ("viewportMode" in patch) {
      listener(state.viewportMode, state);
    }
  }, "viewportMode");
}
