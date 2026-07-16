/** Titan Frontend V2 — Animation framework (Phase E1 + 11.P3 shared clock). */

import { DURATION, EASING } from "./tokens.js";
import { getFrameScheduler } from "../neural/frame-scheduler.js";

/**
 * @typedef {Object} AnimationTask
 * @property {string} id
 * @property {number} startTime
 * @property {number} duration
 * @property {(progress: number) => void} onUpdate
 * @property {() => void} [onComplete]
 * @property {string} easing
 */

const ANIM_FRAME_ID = "titan-animation-engine";

export class AnimationEngine {
  /** @param {{ reducedMotion?: boolean }} [options] */
  constructor(options = {}) {
    this._reducedMotion = Boolean(options.reducedMotion);
    this._tasks = new Map();
    this._rafId = null;
    this._running = false;
    this._unregister = /** @type {(() => void) | null} */ (null);
    this._boundTick = (frame) => this._onFrame(frame);
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
      if (this._tasks.size === 0) {
        this._teardownLoop();
      }
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

    // One-shot paint — not a persistent RAF loop.
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
    if (this._running && this._unregister) {
      return;
    }
    this._running = true;
    const scheduler = getFrameScheduler();
    this._unregister = scheduler.register(ANIM_FRAME_ID, this._boundTick, {
      cadence: 1,
      priority: 50,
    });
    this._rafId = scheduler.isRunning() ? 1 : null;
  }

  _teardownLoop() {
    if (this._unregister) {
      this._unregister();
      this._unregister = null;
    }
    this._running = false;
    this._rafId = null;
  }

  /**
   * @param {{ timestamp: number, deltaMs: number }} frame
   */
  _onFrame(frame) {
    const now = frame.timestamp;
    for (const [id, task] of this._tasks) {
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
      this._teardownLoop();
    }
  }

  /** Legacy alias used by older callers. */
  _tick(now) {
    this._onFrame({ timestamp: now, deltaMs: 16.7 });
  }

  /** @param {number} t 0–1 */
  _applyEasing(t, _easingKey) {
    return t;
  }

  destroy() {
    this._teardownLoop();
    this._tasks.clear();
  }
}
