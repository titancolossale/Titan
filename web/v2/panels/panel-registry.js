/** Titan Frontend V2 — Panel registry. */

/** @typedef {import("./panel-slots.js").PanelDefinition} PanelDefinition */

export class PanelRegistry {
  constructor() {
    /** @type {Map<string, PanelDefinition>} */
    this._panels = new Map();
  }

  /** @param {PanelDefinition} definition */
  register(definition) {
    if (this._panels.has(definition.id)) {
      console.warn(`[Titan V2] Panel "${definition.id}" already registered — skipping.`);
      return;
    }
    this._panels.set(definition.id, definition);
  }

  /** @param {string} id */
  get(id) {
    return this._panels.get(id);
  }

  /** @returns {PanelDefinition[]} */
  list() {
    return [...this._panels.values()];
  }
}
