/** Titan Neural Renderer V2 — Shared utilities. */

import { NEURAL_CONFIG } from "./config.js";

/** @param {number} min @param {number} max */
export function rand(min, max) {
  return min + Math.random() * (max - min);
}

/** @param {number} min @param {number} max */
export function randInt(min, max) {
  return Math.floor(rand(min, max + 1));
}

/**
 * @param {number} width
 * @param {number} height
 * @param {number} [density]
 * @param {number} [maxCount]
 */
export function computeNodeCount(width, height, density, maxCount) {
  const cfg = NEURAL_CONFIG.nodes;
  const d = density ?? cfg.densityDefault;
  const ceiling = maxCount ?? cfg.maxCount;
  const count = Math.floor(((width * height) / cfg.areaDivisor) * d);
  const floor = Math.min(cfg.minCount, ceiling);
  return Math.max(floor, Math.min(count, ceiling));
}

/** @param {number} a @param {number} b @param {number} t */
export function lerp(a, b, t) {
  return a + (b - a) * t;
}

/** @param {number} t */
export function clamp01(t) {
  return Math.max(0, Math.min(1, t));
}

/** @returns {boolean} */
export function prefersReducedMotion() {
  try {
    if (typeof document === "undefined" || typeof window === "undefined") {
      return false;
    }
    return (
      document.documentElement?.classList?.contains("tdl-v2--reduced-motion") ||
      Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches)
    );
  } catch {
    return false;
  }
}
