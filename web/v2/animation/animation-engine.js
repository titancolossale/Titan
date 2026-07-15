/** Titan Frontend V2 — Animation framework (Phase E1 architecture). */

import { DURATION, EASING } from "./tokens.js";

/**
 * @typedef {Object} AnimationTask
 * @property {string} id
 * @property {number} startTime
 * @property {number} duration
 * @property {(progress: number) => void} onUpdate
 * @property {() => void} [onComplete]
 * @property {string} easing
 */

export class AnimationEngine {
  /** @param {{ reducedMotion?: boolean }} [options] */
  constructor(options = {}) {
    this._reducedMotion = Boolean(options.reducedMotion);
    this._tasks = new Map();
    this._rafId = null;
    this._running = false;
  }

  /** @param {boolean} enabled */
  setReducedMotion(enabled) {
    this._reducedMotion = enabled;
  }

  /**
   * Schedule a timed animation.
   * @param {Omit<AnimationTask, "startTime"> & { delay?: number }} spec
   * @returns {() => void} cancel function
   */
  schedule(spec) {
    const duration = this._reducedMotion ? 0 : spec.duration;
    const delay = this._reducedMotion ? 0 : (spec.delay ?? 0);
    const id = spec.id;
    const startTime = performance.now() + delay;

    const task = {
      id,
      startTime,
      duration: Math.max(duration, 0),
      easing: spec.easing ?? EASING.standard,
      onUpdate: spec.onUpdate,
      onComplete: spec.onComplete,
    };

    this._tasks.set(id, task);
    this._ensureLoop();

    return () => {
      this._tasks.delete(id);
    };
  }

  /** Apply CSS transition class lifecycle on an element. */
  transitionOpacity(element, { from = 0, to = 1, duration = DURATION.normal, easing = EASING.enter } = {}) {
    if (!element) {
      return () => {};
    }

    if (this._reducedMotion) {
      element.style.opacity = String(to);
      return () => {};
    }

    element.style.opacity = String(from);
    element.style.transition = `opacity ${duration}ms ${easing}`;

    const raf = requestAnimationFrame(() => {
      element.style.opacity = String(to);
    });

    const cancel = this.schedule({
      id: `opacity-${Math.random().toString(36).slice(2)}`,
      duration,
      onUpdate: () => {},
      onComplete: () => {
        cancelAnimationFrame(raf);
      },
    });

    return cancel;
  }

  _ensureLoop() {
    if (this._running) {
      return;
    }
    this._running = true;
    this._tick = this._tick.bind(this);
    this._rafId = requestAnimationFrame(this._tick);
  }

  _tick(now) {
    for (const [id, task] of [...this._tasks.entries()]) {
      if (now < task.startTime) {
        continue;
      }

      const elapsed = now - task.startTime;
      const raw = task.duration === 0 ? 1 : Math.min(elapsed / task.duration, 1);
      const progress = this._applyEasing(raw, task.easing);

      task.onUpdate(progress);

      if (raw >= 1) {
        this._tasks.delete(id);
        task.onComplete?.();
      }
    }

    if (this._tasks.size === 0) {
      this._running = false;
      this._rafId = null;
      return;
    }

    this._rafId = requestAnimationFrame(this._tick);
  }

  /** @param {number} t 0–1 */
  _applyEasing(t, _easingKey) {
    return t;
  }

  destroy() {
    if (this._rafId !== null) {
      cancelAnimationFrame(this._rafId);
    }
    this._tasks.clear();
    this._running = false;
  }
}
