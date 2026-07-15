/** Titan Frontend V2 — Panel mounting and route transitions. */

import { SCREEN_TRANSITION } from "../animation/tokens.js";

export class PanelMount {
  /**
   * @param {import("./panel-registry.js").PanelRegistry} registry
   * @param {import("../animation/animation-engine.js").AnimationEngine} animationEngine
   */
  constructor(registry, animationEngine) {
    this._registry = registry;
    this._animationEngine = animationEngine;
    /** @type {string | null} */
    this._activeId = null;
    /** @type {HTMLElement | null} */
    this._activeNode = null;
  }

  /**
   * Mount panel into slot without transition.
   * @param {HTMLElement} slot
   * @param {string} panelId
   */
  mount(slot, panelId) {
    const definition = this._registry.get(panelId);
    if (!definition) {
      console.warn(`[Titan V2] Unknown panel: ${panelId}`);
      return;
    }

    slot.replaceChildren();
    const node = definition.factory();
    node.dataset.panelId = panelId;
    node.dataset.slot = definition.slot;
    slot.appendChild(node);

    this._activeId = panelId;
    this._activeNode = node;
    slot.dataset.activePanel = panelId;
    slot.dataset.transition = "active";
  }

  /**
   * Cross-fade center content (Master Blueprint — 350ms).
   * @param {HTMLElement} slot
   * @param {string} panelId
   * @param {{ duration?: number, reducedMotion?: boolean }} [options]
   */
  transitionTo(slot, panelId, options = {}) {
    if (this._activeId === panelId) {
      return;
    }

    const duration = options.reducedMotion ? 0 : (options.duration ?? SCREEN_TRANSITION.duration);

    if (duration === 0) {
      this.mount(slot, panelId);
      return;
    }

    slot.dataset.transition = "exit";

    this._animationEngine.schedule({
      id: `panel-exit-${this._activeId ?? "none"}`,
      duration,
      onUpdate: () => {},
      onComplete: () => {
        this.mount(slot, panelId);
        slot.dataset.transition = "enter";
        requestAnimationFrame(() => {
          slot.dataset.transition = "active";
        });
      },
    });
  }

  /** @returns {string | null} */
  getActivePanelId() {
    return this._activeId;
  }
}
