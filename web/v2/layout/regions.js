/** Titan Frontend V2 — Workspace region definitions (Layout Guide §2). */

export const LAYER_IDS = Object.freeze({
  neural: "tdl-v2-layer-neural",
  glow: "tdl-v2-layer-glow",
  workspace: "tdl-v2-layer-workspace",
  floating: "tdl-v2-layer-floating",
  overlay: "tdl-v2-layer-overlay",
});

export const REGION_IDS = Object.freeze({
  sidebar: "tdl-v2-region-sidebar",
  main: "tdl-v2-region-main",
  topbar: "tdl-v2-region-topbar",
  center: "tdl-v2-region-center",
  orchestrator: "tdl-v2-region-orchestrator",
  dock: "tdl-v2-region-dock",
  dockStatusCards: "tdl-v2-dock-status-cards",
  dockStatusLines: "tdl-v2-dock-status-lines",
  dockComposer: "tdl-v2-dock-composer",
  dockTelemetry: "tdl-v2-dock-telemetry",
  centerSlot: "tdl-v2-center-slot",
  contextPanel: "tdl-v2-region-context-panel",
});

/** Orchestrator refocus matrix — Master Blueprint Cross-Screen Architecture. */
export const ORCHESTRATOR_FOCUS = Object.freeze({
  chat: ["state", "plan", "tools", "sparkline"],
  projects: ["state", "mission", "agents", "tools"],
  memory: ["state", "retrieval", "writes", "sparkline"],
  obsidian: ["connector", "operation", "decision", "timeline"],
  browser: ["health", "urls", "fetch", "timeline"],
  trading: ["analysis", "broker", "orders", "risk"],
  calendar: ["planning", "conflicts", "tool"],
  voice: ["state"],
  settings: [],
});

/** Production Spec §1.7 breakpoints. */
export const BREAKPOINTS = Object.freeze({
  phone: 768,
  tablet: 1024,
  laptop: 1280,
  desktop: 1920,
  ultrawide: 2560,
});

/** @typedef {"phone"|"tablet"|"laptop"|"desktop"|"wide"|"ultrawide"} ViewportMode */

/**
 * @param {number} width
 * @returns {ViewportMode}
 */
export function resolveViewportMode(width) {
  if (width < BREAKPOINTS.phone) {
    return "phone";
  }
  if (width < BREAKPOINTS.tablet) {
    return "tablet";
  }
  if (width < BREAKPOINTS.laptop) {
    return "laptop";
  }
  if (width < BREAKPOINTS.desktop) {
    return "desktop";
  }
  if (width < BREAKPOINTS.ultrawide) {
    return "wide";
  }
  return "ultrawide";
}
