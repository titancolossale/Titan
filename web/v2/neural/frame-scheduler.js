/** Titan Neural Renderer — Shared display-clock scheduler (Phase 11.P3). */

/**
 * One primary requestAnimationFrame loop for visual systems.
 * Subsystems register lightweight callbacks; large resume deltas are clamped
 * so hidden-tab restore cannot create animation jumps or duplicate loops.
 */

export const MAX_FRAME_DELTA_MS = 33.5;
export const NOMINAL_FRAME_MS = 1000 / 60;

/**
 * @typedef {{
 *   timestamp: number,
 *   deltaMs: number,
 *   frameIndex: number,
 *   clamped: boolean,
 * }} FrameClock
 */

/**
 * @typedef {{
 *   id: string,
 *   fn: (frame: FrameClock) => void,
 *   cadence: number,
 *   phase: number,
 *   priority: number,
 * }} SchedulerRegistration
 */

export class FrameScheduler {
  constructor() {
    /** @type {Map<string, SchedulerRegistration>} */
    this._callbacks = new Map();
    /** Cached priority-ordered list — rebuilt only on register/unregister. */
    this._ordered = /** @type {SchedulerRegistration[]} */ ([]);
    this._orderDirty = true;
    /** @type {number | null} */
    this._rafId = null;
    this._running = false;
    this._lastTs = 0;
    this._hasClock = false;
    this._frameIndex = 0;
    this._boundTick = (ts) => this._tick(ts);
    this._boundVisibility = () => this._onVisibilityChange();
    this._visibilityAttached = false;
    /** Cumulative primary RAF start count (diagnostics). */
    this._startCount = 0;
  }

  /**
   * Register or replace a frame callback. Idempotent for the same id.
   * @param {string} id
   * @param {(frame: FrameClock) => void} fn
   * @param {{ cadence?: number, phase?: number, priority?: number }} [options]
   * @returns {() => void} unregister
   */
  register(id, fn, options = {}) {
    if (!id || typeof fn !== "function") {
      return () => {};
    }
    const cadence = Math.max(1, Math.floor(options.cadence ?? 1));
    this._callbacks.set(id, {
      id,
      fn,
      cadence,
      phase: Math.max(0, Math.floor(options.phase ?? 0)) % cadence,
      priority: options.priority ?? 0,
    });
    this._orderDirty = true;
    this.start();
    return () => this.unregister(id);
  }

  /** @param {string} id */
  unregister(id) {
    this._callbacks.delete(id);
    this._orderDirty = true;
    if (this._callbacks.size === 0) {
      this.stop();
    }
  }

  _rebuildOrder() {
    if (!this._orderDirty) return;
    this._ordered = [...this._callbacks.values()].sort((a, b) => b.priority - a.priority);
    this._orderDirty = false;
  }

  /** Idempotent — at most one primary RAF loop. */
  start() {
    this._attachVisibility();
    if (this._running && this._rafId !== null) {
      return;
    }
    if (typeof document !== "undefined" && document.hidden) {
      this._running = false;
      this._rafId = null;
      this._hasClock = false;
      return;
    }
    if (typeof requestAnimationFrame !== "function") {
      return;
    }
    if (this._rafId !== null && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(this._rafId);
      this._rafId = null;
    }
    this._running = true;
    this._hasClock = false;
    this._startCount += 1;
    this._rafId = requestAnimationFrame(this._boundTick);
  }

  stop() {
    this._running = false;
    if (this._rafId !== null && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(this._rafId);
    }
    this._rafId = null;
    this._hasClock = false;
  }

  /**
   * Idempotent start after stop — cancels any stale handle first.
   * Prevents duplicate loops if a tick was manually driven in tests.
   */
  _restartClean() {
    if (this._rafId !== null && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(this._rafId);
      this._rafId = null;
    }
    this._running = false;
    this.start();
  }

  /** True when the primary loop is scheduled. */
  isRunning() {
    return this._rafId !== null;
  }

  /** Always 0 or 1 — primary display clock only. */
  getActiveRafCount() {
    return this._rafId !== null ? 1 : 0;
  }

  getCallbackCount() {
    return this._callbacks.size;
  }

  getFrameIndex() {
    return this._frameIndex;
  }

  getStartCount() {
    return this._startCount;
  }

  /** @returns {FrameClock} */
  getLastFrame() {
    return {
      timestamp: this._lastTs,
      deltaMs: NOMINAL_FRAME_MS,
      frameIndex: this._frameIndex,
      clamped: false,
    };
  }

  destroy() {
    this.stop();
    this._callbacks.clear();
    this._detachVisibility();
  }

  _attachVisibility() {
    if (this._visibilityAttached || typeof document === "undefined") return;
    document.addEventListener("visibilitychange", this._boundVisibility);
    this._visibilityAttached = true;
  }

  _detachVisibility() {
    if (!this._visibilityAttached || typeof document === "undefined") return;
    document.removeEventListener("visibilitychange", this._boundVisibility);
    this._visibilityAttached = false;
  }

  _onVisibilityChange() {
    if (typeof document === "undefined") return;
    if (document.hidden) {
      this.stop();
      return;
    }
    if (this._callbacks.size > 0) {
      // Resume with fresh clock — first delta uses nominal, not wall-clock gap.
      this._hasClock = false;
      this._restartClean();
    }
  }

  /** @param {number} timestamp */
  _tick(timestamp) {
    if (!this._running) {
      this._rafId = null;
      return;
    }
    if (typeof document !== "undefined" && document.hidden) {
      this._rafId = null;
      this._running = false;
      this._hasClock = false;
      return;
    }

    let deltaMs = NOMINAL_FRAME_MS;
    let clamped = false;
    if (this._hasClock) {
      const raw = timestamp - this._lastTs;
      if (raw > MAX_FRAME_DELTA_MS) {
        deltaMs = MAX_FRAME_DELTA_MS;
        clamped = true;
      } else {
        deltaMs = Math.max(0, raw);
      }
    }
    this._lastTs = timestamp;
    this._hasClock = true;
    this._frameIndex += 1;

    /** @type {FrameClock} */
    const frame = {
      timestamp,
      deltaMs,
      frameIndex: this._frameIndex,
      clamped,
    };

    this._rebuildOrder();
    const ordered = this._ordered;
    for (let i = 0; i < ordered.length; i++) {
      const reg = ordered[i];
      if ((this._frameIndex + reg.phase) % reg.cadence !== 0) {
        continue;
      }
      reg.fn(frame);
    }

    this._rafId = requestAnimationFrame(this._boundTick);
  }
}

/** @type {FrameScheduler | null} */
let _shared = null;

/** Process-wide shared scheduler (idempotent). */
export function getFrameScheduler() {
  if (!_shared) {
    _shared = new FrameScheduler();
  }
  return _shared;
}

/** Test helper — reset singleton. */
export function resetFrameSchedulerForTests() {
  if (_shared) {
    _shared.destroy();
  }
  _shared = null;
}
