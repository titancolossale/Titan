/** Titan Neural Renderer V2 — Cognitive region focus system. */

import { REGION_ANCHORS } from "./node-classes.js";

/**
 * Tracks active focus regions for camera attraction and signal routing.
 */
export class RegionFocus {
  constructor() {
    /** @type {Map<string, number>} */
    this._focus = new Map();
    this._activeRegion = "core";
  }

  /** @param {string} regionId @param {number} strength 0–1 */
  setFocus(regionId, strength = 1) {
    this._focus.set(regionId, Math.max(0, Math.min(1, strength)));
    if (strength > 0.2) {
      this._activeRegion = regionId;
    }
  }

  /** @param {string} regionId */
  clearFocus(regionId) {
    this._focus.delete(regionId);
  }

  decay(dt) {
    for (const [key, val] of this._focus.entries()) {
      const next = val - 0.002 * dt;
      if (next <= 0.01) {
        this._focus.delete(key);
      } else {
        this._focus.set(key, next);
      }
    }
  }

  /** @returns {{ x: number, y: number, pull: number } | null} */
  getAttractionPoint(worldWidth, worldHeight) {
    let totalPull = 0;
    let ax = 0;
    let ay = 0;

    for (const [regionId, pull] of this._focus.entries()) {
      const anchor = REGION_ANCHORS[regionId];
      if (!anchor || pull <= 0) continue;
      ax += anchor.x * pull;
      ay += anchor.y * pull;
      totalPull += pull;
    }

    if (totalPull < 0.05) {
      const core = REGION_ANCHORS.core;
      return { x: core.x * worldWidth, y: core.y * worldHeight, pull: 0.12 };
    }

    return {
      x: (ax / totalPull) * worldWidth,
      y: (ay / totalPull) * worldHeight,
      pull: Math.min(1, totalPull),
    };
  }

  getActiveRegion() {
    return this._activeRegion;
  }

  /** Map tool id → neural region focus keys (Phase E5). */
  static mapToolToRegions(toolId) {
    const map = {
      memory: ["memory"],
      obsidian: ["obsidian", "memory"],
      browser: ["browser"],
      calendar: ["calendar", "planning"],
      trading: ["trading"],
      voice: ["communication", "core"],
      projects: ["planning", "tools"],
      chat: ["core", "communication"],
    };
    return map[toolId] ?? ["tools"];
  }

  /** Map cognitive state id → region focus keys. */
  static mapCognitiveToRegions(stateId) {
    const map = {
      idle: ["core"],
      sleep: ["core"],
      listening: ["communication", "core"],
      thinking: ["core", "reasoning", "knowledge"],
      planning: ["planning", "core", "workflow"],
      memory_recall: ["memory", "knowledge"],
      reasoning: ["reasoning", "core", "knowledge"],
      writing: ["communication", "core"],
      tool_execution: ["tools", "workflow"],
      browser_research: ["browser", "tools", "knowledge"],
      obsidian: ["obsidian", "memory", "knowledge"],
      calendar: ["calendar", "planning"],
      trading: ["trading", "reasoning"],
      voice: ["communication", "core"],
      error: ["core"],
    };
    return map[stateId] ?? ["core"];
  }
}
