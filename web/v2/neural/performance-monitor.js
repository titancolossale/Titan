/** Titan Neural Renderer — Internal performance monitor (Phase 11.P1). */

/**
 * Lightweight rolling FPS / frame-time tracker.
 * Detailed dumps only via getSnapshot() / debug mode — no production log spam.
 */
export class PerformanceMonitor {
  /**
   * @param {{ sampleWindow?: number }} [options]
   */
  constructor(options = {}) {
    this._sampleWindow = options.sampleWindow ?? 90;
    /** @type {number[]} */
    this._frameMs = [];
    this._fps = 60;
    this._rollingFps = 60;
    this._lastFrameMs = 16.7;
    this._droppedDecorative = 0;
    this._skippedFrames = 0;
    this._paused = false;
    this._canvasWidth = 0;
    this._canvasHeight = 0;
    this._dpr = 1;
    this._qualityMode = "balanced";
    this._qualityTier = "high";
    this._budgets = /** @type {Record<string, number | boolean | string> | null} */ (null);
    this._geometryRebuilds = 0;
    this._rafLoops = 1;
    this._debug = false;
  }

  /** @param {boolean} enabled */
  setDebug(enabled) {
    this._debug = Boolean(enabled);
  }

  isDebug() {
    return this._debug;
  }

  /**
   * @param {number} frameMs
   */
  recordFrame(frameMs) {
    const ms = Math.max(0.1, Math.min(frameMs || 16.7, 100));
    this._lastFrameMs = ms;
    this._fps = Math.round(1000 / ms);
    this._frameMs.push(ms);
    if (this._frameMs.length > this._sampleWindow) {
      this._frameMs.shift();
    }
    if (this._frameMs.length) {
      const avg = this._frameMs.reduce((a, b) => a + b, 0) / this._frameMs.length;
      this._rollingFps = Math.round(1000 / avg);
    }
  }

  recordDroppedDecorative() {
    this._droppedDecorative += 1;
  }

  recordSkippedFrame() {
    this._skippedFrames += 1;
  }

  recordGeometryRebuild() {
    this._geometryRebuilds += 1;
  }

  /**
   * @param {{
   *   paused?: boolean,
   *   canvasWidth?: number,
   *   canvasHeight?: number,
   *   dpr?: number,
   *   qualityMode?: string,
   *   qualityTier?: string,
   *   budgets?: Record<string, number | boolean | string> | null,
   *   rafLoops?: number,
   * }} info
   */
  updateMeta(info) {
    if (info.paused != null) this._paused = info.paused;
    if (info.canvasWidth != null) this._canvasWidth = info.canvasWidth;
    if (info.canvasHeight != null) this._canvasHeight = info.canvasHeight;
    if (info.dpr != null) this._dpr = info.dpr;
    if (info.qualityMode != null) this._qualityMode = info.qualityMode;
    if (info.qualityTier != null) this._qualityTier = info.qualityTier;
    if (info.budgets !== undefined) this._budgets = info.budgets;
    if (info.rafLoops != null) this._rafLoops = info.rafLoops;
  }

  /**
   * Approximate 1% low FPS from recent samples.
   * @returns {number}
   */
  getOnePercentLow() {
    if (this._frameMs.length < 10) return this._rollingFps;
    const sorted = [...this._frameMs].sort((a, b) => b - a);
    const idx = Math.max(0, Math.floor(sorted.length * 0.01));
    const worst = sorted[idx] ?? sorted[0];
    return Math.round(1000 / worst);
  }

  /** @returns {number | null} */
  getMemoryEstimateMb() {
    try {
      const mem = performance.memory;
      if (mem?.usedJSHeapSize) {
        return Math.round((mem.usedJSHeapSize / (1024 * 1024)) * 10) / 10;
      }
    } catch {
      /* unsupported */
    }
    return null;
  }

  getSnapshot() {
    return {
      fps: this._fps,
      rollingFps: this._rollingFps,
      onePercentLow: this.getOnePercentLow(),
      frameMs: Math.round(this._lastFrameMs * 10) / 10,
      qualityMode: this._qualityMode,
      qualityTier: this._qualityTier,
      canvasWidth: this._canvasWidth,
      canvasHeight: this._canvasHeight,
      dpr: this._dpr,
      budgets: this._budgets,
      droppedDecorative: this._droppedDecorative,
      skippedFrames: this._skippedFrames,
      geometryRebuilds: this._geometryRebuilds,
      paused: this._paused,
      rafLoops: this._rafLoops,
      memoryMb: this.getMemoryEstimateMb(),
      debug: this._debug,
    };
  }
}
