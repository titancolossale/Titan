/** Titan Frontend V2 — Panel slot identifiers (Master Blueprint). */

export const PANEL_SLOTS = Object.freeze({
  center: "center",
  overlay: "overlay",
  floating: "floating",
});

export const CENTER_PANELS = Object.freeze([
  "chat",
  "projects",
  "memory",
  "obsidian",
  "browser",
  "trading",
  "calendar",
  "tools",
  "voice",
]);

/** @typedef {typeof CENTER_PANELS[number]} CenterPanelId */

/**
 * @typedef {Object} PanelDefinition
 * @property {string} id
 * @property {keyof typeof PANEL_SLOTS} slot
 * @property {() => HTMLElement} factory
 * @property {string} [label]
 */
