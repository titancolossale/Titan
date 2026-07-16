/** Titan Neural Renderer — Frame-time performance monitor (Phase 11.P1 + 11.P3). */

/**
 * Rolling FPS + frame-time percentiles.
 * Display consumers must throttle DOM updates — this class itself is allocation-light.
 */

const DEFAULT_WINDOW = 120;

/**
 * @param {Float64Array} buf
 * @param {number} len
 * @param {number} percentile 0–100
 */
function percentileOf(buf, len, percentile) {
  if (len <= 0) return 16.7;
  const tmp = [];
  for (let i = 0; i < len; i++) tmp.push(buf[i]);
  tmp.sort((a, b) => a - b);
  const idx = Math.min(len - 1, Math.max(0, Math.ceil((percentile / 100) * len) - 1));
  return tmp[idx];
}

export class PerformanceMonitor {
  /**
   * @param {{ sampleWindow?: number }} [options]
   */
  constructor(options = {}) {
    this._sampleWindow = options.sampleWindow ?? DEFAULT_WINDOW;
    /** Circular buffer of frame times (ms). */
    this._frameBuf = new Float64Array(this._sampleWindow);
    this._bufLen = 0;
    this._bufWrite = 0;
    this._fps = 60;
    this._rollingFps = 60;
    this._lastFrameMs = 16.7;
    this._medianMs = 16.7;
    this._p95Ms = 16.7;
    this._p99Ms = 16.7;
    this._framesOver25 = 0;
    this._framesOver50 = 0;
    this._longFrames = 0;
    this._droppedDecorative = 0;
    this._skippedFrames = 0;
    this._skippedDecorative = 0;
    this._paused = false;
    this._canvasWidth = 0;
    this._canvasHeight = 0;
    this._dpr = 1;
    this._qualityMode = "auto";
    this._qualityTier = "high";
    this._budgets = /** @type {Record<string, number | boolean | string> | null} */ (null);
    this._geometryRebuilds = 0;
    this._staticRebuilds = 0;
    this._rafLoops = 1;
    this._debug = false;
    this._percentilesDirty = true;
    this._lastPercentileComputeMs = 0;
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

    this._frameBuf[this._bufWrite] = ms;
    this._bufWrite = (this._bufWrite + 1) % this._sampleWindow;
    if (this._bufLen < this._sampleWindow) this._bufLen += 1;
    this._percentilesDirty = true;

    if (ms > 25) this._framesOver25 += 1;
    if (ms > 50) {
      this._framesOver50 += 1;
      this._longFrames += 1;
    }

    // Rolling FPS from mean — no array alloc.
    let sum = 0;
    for (let i = 0; i < this._bufLen; i++) sum += this._frameBuf[i];
    const avg = sum / Math.max(1, this._bufLen);
    this._rollingFps = Math.round(1000 / avg);
  }

  recordDroppedDecorative() {
    this._droppedDecorative += 1;
    this._skippedDecorative += 1;
  }

  recordSkippedFrame() {
    this._skippedFrames += 1;
  }

  recordGeometryRebuild() {
    this._geometryRebuilds += 1;
  }

  /** @param {number} [count] */
  recordStaticRebuild(count = 1) {
    this._staticRebuilds += count;
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
   *   staticRebuilds?: number,
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
    if (info.staticRebuilds != null) this._staticRebuilds = info.staticRebuilds;
  }

  _recomputePercentiles(nowMs = 0) {
    // Throttle percentile sorts — not every frame.
    if (!this._percentilesDirty && nowMs - this._lastPercentileComputeMs < 250) {
      return;
    }
    this._medianMs = percentileOf(this._frameBuf, this._bufLen, 50);
    this._p95Ms = percentileOf(this._frameBuf, this._bufLen, 95);
    this._p99Ms = percentileOf(this._frameBuf, this._bufLen, 99);
    this._percentilesDirty = false;
    this._lastPercentileComputeMs = nowMs || performance.now();
  }

  /** Approximate 1% low FPS from recent samples. */
  getOnePercentLow() {
    this._recomputePercentiles();
    return Math.round(1000 / Math.max(0.1, this._p99Ms));
  }

  /** @returns {number | null} */
  getMemoryEstimateMb() {
    try {
      const mem = /** @type {{ usedJSHeapSize?: number }} */ (performance).memory;
      if (mem?.usedJSHeapSize) {
        return Math.round((mem.usedJSHeapSize / (1024 * 1024)) * 10) / 10;
      }
    } catch {
      /* unsupported */
    }
    return null;
  }

  getSnapshot() {
    this._recomputePercentiles(performance.now());
    return {
      fps: this._fps,
      rollingFps: this._rollingFps,
      onePercentLow: Math.round(1000 / Math.max(0.1, this._p99Ms)),
      frameMs: Math.round(this._lastFrameMs * 10) / 10,
      medianFrameMs: Math.round(this._medianMs * 10) / 10,
      p95FrameMs: Math.round(this._p95Ms * 10) / 10,
      p99FrameMs: Math.round(this._p99Ms * 10) / 10,
      framesOver25: this._framesOver25,
      framesOver50: this._framesOver50,
      longFrames: this._longFrames,
      qualityMode: this._qualityMode,
      qualityTier: this._qualityTier,
      canvasWidth: this._canvasWidth,
      canvasHeight: this._canvasHeight,
      dpr: this._dpr,
      budgets: this._budgets,
      droppedDecorative: this._droppedDecorative,
      skippedDecorative: this._skippedDecorative,
      skippedFrames: this._skippedFrames,
      geometryRebuilds: this._geometryRebuilds,
      staticRebuilds: this._staticRebuilds,
      cacheRebuildCount: this._staticRebuilds,
      paused: this._paused,
      rafLoops: this._rafLoops,
      activeRafCount: this._rafLoops,
      memoryMb: this.getMemoryEstimateMb(),
      debug: this._debug,
    };
  }
}
