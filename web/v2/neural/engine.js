/** Titan Neural Renderer V3 — Engine orchestrator (STATE · WORLD · CAMERA · RENDERER). */

import { NEURAL_CONFIG } from "./config.js";
import { CognitiveOverlay, getAllCognitiveCssClasses, getCognitiveCssClass, getMasterCssClass } from "./cognitive.js";
import { NeuralCamera } from "./camera.js";
import { DepthField } from "./depth.js";
import { GhostLayer } from "./ghosts.js";
import { getFrameScheduler } from "./frame-scheduler.js";
import { NeuralNodes } from "./nodes.js";
import { PerformanceMonitor } from "./performance-monitor.js";
import { QualityController } from "./quality-controller.js";
import { RegionFocus } from "./regions.js";
import { NeuralRenderer } from "./renderer.js";
import { NeuralSignals } from "./signals.js";
import { NeuralState } from "./state.js";
import { prefersReducedMotion } from "./utils.js";

/** Debounce browser chrome / panel resize noise. */
const RESIZE_DEBOUNCE_MS = 160;
/** Ignore sub-threshold dimension jitter (mobile URL bar, scrollbar). */
const MIN_RESIZE_DELTA_PX = 8;
/** Scheduler registration id — single neural callback. */
const NEURAL_FRAME_ID = "titan-neural-engine";

export class NeuralEngine {
  /**
   * @param {HTMLCanvasElement} canvas
   * @param {{ density?: number, cameraEl?: HTMLElement | null }} [options]
   */
  constructor(canvas, options = {}) {
    this.canvas = canvas;
    this.cameraEl = options.cameraEl ?? null;
    this.options = options;

    this.state = new NeuralState();
    this.camera = new NeuralCamera();
    this.nodes = new NeuralNodes(this.camera);
    this.signals = new NeuralSignals(this.nodes);
    this.renderer = new NeuralRenderer(canvas);
    this.depthField = new DepthField();
    this.cognitiveOverlay = new CognitiveOverlay();
    this.ghostLayer = new GhostLayer();
    this.regionFocus = new RegionFocus();
    this.quality = new QualityController();
    this.perf = new PerformanceMonitor();
    this.scheduler = getFrameScheduler();

    this.depthField.setInfiniteEnabled(true);

    /** @deprecated use scheduler — kept for diagnostics / tests */
    this.frameId = null;
    /** @type {ResizeObserver | null} */
    this.resizeObserver = null;
    this._baseDensity = options.density ?? NEURAL_CONFIG.nodes.densityDefault;
    this._fps = 60;
    this._initialized = false;
    this._destroyed = false;
    /** @type {ReturnType<typeof setTimeout> | null} */
    this._resizeTimer = null;
    this._lastWidth = 0;
    this._lastHeight = 0;
    this._geometryBuildCount = 0;
    /** @type {boolean} */
    this._chatPending = false;
    this._unregisterFrame = /** @type {(() => void) | null} */ (null);
    this._pendingEmergencyRebuild = false;
    this._pendingQualityRebuild = false;
    this._metaBudgets = /** @type {Record<string, number | boolean | string> | null} */ (null);
    this._frameCounter = 0;

    this._boundResize = () => this._scheduleResize();
    this._boundVisibility = () => this._onVisibilityChange();
    this._boundFrame = (frame) => this._onFrame(frame);
  }

  init() {
    if (this._initialized) {
      // Idempotent — ensure single scheduler registration.
      this._ensureSchedulerRegistration();
      return;
    }
    this._initialized = true;
    this._destroyed = false;

    if (this.options.density) {
      this._baseDensity = this.options.density;
    }

    window.addEventListener("resize", this._boundResize);
    document.addEventListener("visibilitychange", this._boundVisibility);

    if (typeof ResizeObserver !== "undefined" && this.canvas.parentElement) {
      this.resizeObserver = new ResizeObserver(this._boundResize);
      this.resizeObserver.observe(this.canvas.parentElement);
    }

    this.state.setVisible(!document.hidden);
    this.state.setMasterState("BOOTING");
    this.state.setCognitiveState("idle");
    this._applyCssClasses();

    this.resize({ immediate: true });
    this._syncPresenceDecorations();
    this._ensureSchedulerRegistration();
  }

  destroy() {
    this._destroyed = true;
    this._initialized = false;
    if (this._unregisterFrame) {
      this._unregisterFrame();
      this._unregisterFrame = null;
    }
    this.frameId = null;
    if (this._resizeTimer !== null) {
      clearTimeout(this._resizeTimer);
      this._resizeTimer = null;
    }
    window.removeEventListener("resize", this._boundResize);
    document.removeEventListener("visibilitychange", this._boundVisibility);
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
  }

  _ensureSchedulerRegistration() {
    if (this._destroyed) return;
    if (this._unregisterFrame) return;
    this._unregisterFrame = this.scheduler.register(NEURAL_FRAME_ID, this._boundFrame, {
      cadence: 1,
      priority: 100,
    });
    this.frameId = this.scheduler.isRunning() ? 1 : null;
  }

  _onVisibilityChange() {
    this.state.setVisible(!document.hidden);
    this.perf.updateMeta({
      paused: this.state.isPaused || document.hidden,
      rafLoops: this.scheduler.getActiveRafCount(),
    });
    if (document.hidden) {
      this.frameId = null;
      return;
    }
    // Re-register + force start — scheduler visibility handler may run after us.
    if (!this.state.isPaused && !this._destroyed) {
      this._ensureSchedulerRegistration();
      this.scheduler.start();
      this.frameId = this.scheduler.isRunning() ? 1 : null;
    }
  }

  /**
   * User-facing quality mode: auto | performance | balanced | cinematic.
   * @param {"auto"|"performance"|"balanced"|"cinematic"} mode
   */
  setQualityMode(mode) {
    const changed = this.quality.setMode(mode);
    if (changed || this.quality.needsGeometryRebuild()) {
      // Stage rebuild — keep last valid frame visible.
      this._pendingQualityRebuild = true;
      this.renderer.markStaticRebuildPending();
      this.resize({ immediate: true, forceRebuild: true, stageCache: true });
    }
    this._syncPresenceDecorations();
    return this.quality.getSnapshot();
  }

  getQualityMode() {
    return this.quality.getMode();
  }

  /** Notify that input / chat UI needs main-thread priority. */
  notifyInteractive(durationMs = 220) {
    this.quality.notifyInteractive(durationMs);
  }

  /** @param {boolean} pending */
  setChatPending(pending) {
    const next = Boolean(pending);
    if (next === this._chatPending) return;
    this._chatPending = next;
    this.quality.setChatPending(next);
    // Chat pending must never rebuild static cache or geometry.
    if (next) {
      this.quality.notifyInteractive(8000);
    }
    this._syncPresenceDecorations();
  }

  getPerformanceSnapshot() {
    const snap = this.perf.getSnapshot();
    const q = this.quality.getSnapshot();
    return {
      ...snap,
      emergencyTier: q.emergencyTier,
      staticRebuilds: this.renderer.getStaticRebuildCount?.() ?? snap.staticRebuilds,
      cacheRebuildCount: this.renderer.getStaticRebuildCount?.() ?? snap.cacheRebuildCount,
      chatPending: this._chatPending,
      budgets: q.budgets,
      activeRafCount: this.scheduler.getActiveRafCount(),
      rafLoops: this.scheduler.getActiveRafCount(),
    };
  }

  /** @returns {number} */
  getGeometryBuildCount() {
    return this._geometryBuildCount;
  }

  /** @param {string} masterState */
  setMasterState(masterState) {
    this.state.setMasterState(masterState);
    if (masterState === "IDLE" || masterState === "AWAKE" || masterState === "SLEEP") {
      this.state.setMode("idle");
    } else if (
      masterState === "THINKING" ||
      masterState === "WORKING" ||
      masterState === "ERROR"
    ) {
      this.state.setMode("thinking");
    }
    this._applyCssClasses();
  }

  /** @param {string} cognitiveState */
  setCognitiveState(cognitiveState) {
    const normalized = this.state.setCognitiveState(cognitiveState);
    this._applyCognitiveDepth(normalized);
    this._syncRegionFocus(normalized);
    this._applyCssClasses();
    return normalized;
  }

  /** @param {string} mode */
  setMode(mode) {
    this.state.setMode(mode);
    this._applyCssClasses();
  }

  /** @param {number} nx @param {number} ny normalized -1..1 pointer parallax. */
  setPointerParallax(nx, ny) {
    this.camera.setPointerParallax(nx, ny);
  }

  /** @param {string} hookName @param {object} [payload] */
  trigger(hookName, payload) {
    this.state.trigger(hookName, payload);
    if (hookName === "memory_retrieval") {
      const boost = NEURAL_CONFIG.depth.recallBoost || 0.45;
      this.depthField.boostRecallDepth(boost);
      this.camera.boostRecallDive(boost * 0.75);
      this.ghostLayer.setRecallActive(true, 0);
    }
    this._applyCssClasses();
  }

  triggerBrainActivity(payload) {
    this.trigger("brain_activity", payload);
  }
  triggerToolUsage(payload) {
    this.trigger("tool_usage", payload);
  }
  triggerMemoryRetrieval(payload) {
    this.trigger("memory_retrieval", payload);
  }
  triggerReasoning(payload) {
    this.trigger("reasoning", payload);
  }
  triggerVoice(payload) {
    this.trigger("voice", payload);
  }
  triggerSpeaking(payload) {
    this.trigger("speaking", payload);
  }
  triggerBrowserResearch(payload) {
    this.trigger("browser_research", payload);
  }

  /**
   * Apply blended tool activity to neural regions (Phase E5).
   * @param {{ signature?: object | null, regions?: Array<{ id: string, strength: number }>, blendWeight?: number, dominant?: { id: string, definition?: object } | null }} blend
   * @param {{ triggerHooks?: boolean }} [options]
   */
  applyToolActivity(blend, options = {}) {
    if (!blend) {
      this.state.clearToolActivityOverlay();
      return;
    }

    const weight = blend.blendWeight ?? 0.5;
    if (blend.signature) {
      this.state.setToolActivityOverlay(blend.signature, weight);
    } else {
      this.state.clearToolActivityOverlay();
    }

    if (blend.regions?.length) {
      for (const region of blend.regions) {
        this.regionFocus.setFocus(region.id, region.strength);
      }
    }

    if (!options.triggerHooks) {
      if (blend.regions?.length) {
        this.setMasterState("WORKING");
        this.setMode("thinking");
      }
      return;
    }

    const dominant = blend.dominant;
    if (dominant?.definition) {
      const def = dominant.definition;
      const hook = def.hook ?? "tool_usage";
      const payload = {
        tool: dominant.id,
        waveStyle: def.waveStyle,
        originNodeId: undefined,
      };

      if (hook === "memory_retrieval") {
        this.trigger("memory_retrieval", payload);
      } else if (hook === "browser_research") {
        this.trigger("browser_research", payload);
      } else if (hook === "speaking") {
        this.trigger("speaking", payload);
      } else if (hook === "reasoning") {
        this.trigger("reasoning", payload);
      } else if (hook === "brain_activity") {
        this.trigger("brain_activity", payload);
      } else {
        this.trigger("tool_usage", payload);
      }

      this._applyCognitiveDepth(def.cognitiveState);
      this._syncRegionFocus(def.cognitiveState);
    }

    if (blend.regions?.length) {
      this.setMasterState("WORKING");
      this.setMode("thinking");
    }
  }

  /**
   * Apply blended memory activity to neural regions (Phase E6).
   * @param {{ signature?: object | null, regions?: Array<{ id: string, strength: number }>, blendWeight?: number, hook?: string | null, eventType?: string | null }} blend
   * @param {{ triggerHooks?: boolean }} [options]
   */
  applyMemoryActivity(blend, options = {}) {
    if (!blend) {
      this.state.clearMemoryActivityOverlay();
      this.ghostLayer.setRecallActive(false, 0);
      return;
    }

    const weight = blend.blendWeight ?? 0.52;
    if (blend.signature) {
      this.state.setMemoryActivityOverlay(blend.signature, weight);
    } else {
      this.state.clearMemoryActivityOverlay();
    }

    if (blend.regions?.length) {
      for (const region of blend.regions) {
        this.regionFocus.setFocus(region.id, region.strength);
      }
    }

    const hook = blend.hook;
    const recallLike =
      hook === "memory_retrieval" ||
      blend.eventType === "memory_recalled" ||
      blend.eventType === "memory_search";

    if (recallLike) {
      this.ghostLayer.setRecallActive(true, 0);
    }

    if (!options.triggerHooks) {
      if (blend.regions?.length || recallLike) {
        this.setMasterState(recallLike ? "DEPTH_RECALL" : "WORKING");
        this.setMode("thinking");
      }
      return;
    }

    if (hook === "memory_retrieval" || recallLike) {
      this.trigger("memory_retrieval", {
        tool: "memory",
        waveStyle: blend.signature?.waveStyle ?? "deep_central",
      });
      this.setCognitiveState("memory_recall");
      this.setMasterState("DEPTH_RECALL");
    } else if (blend.eventType === "memory_linked") {
      this.trigger("brain_activity", { waveStyle: blend.signature?.waveStyle ?? "default" });
      this.setMasterState("WORKING");
    } else if (blend.eventType === "memory_created") {
      this.trigger("brain_activity", { waveStyle: "central" });
      this.setMasterState("WORKING");
    } else if (
      blend.eventType === "memory_archived" ||
      blend.eventType === "memory_deleted"
    ) {
      this.trigger("memory_retrieval", {
        tool: "memory",
        waveStyle: "slow",
        fade: true,
      });
    } else if (blend.regions?.length) {
      this.setMasterState("WORKING");
      this.setMode("thinking");
    }
  }

  /**
   * Apply blended conversation activity to neural regions (Phase E7).
   * @param {{ signature?: object | null, regions?: Array<{ id: string, strength: number }>, blendWeight?: number, hook?: string | null, stage?: string | null }} blend
   * @param {{ triggerHooks?: boolean, eventType?: string }} [options]
   */
  applyConversationActivity(blend, options = {}) {
    if (!blend) {
      this.state.clearConversationActivityOverlay();
      return;
    }

    const weight = blend.blendWeight ?? 0.68;
    if (blend.signature) {
      this.state.setConversationActivityOverlay(blend.signature, weight);
    } else {
      this.state.clearConversationActivityOverlay();
    }

    if (blend.regions?.length) {
      for (const region of blend.regions) {
        this.regionFocus.setFocus(region.id, region.strength);
      }
    }

    const sig = blend.signature ?? {};
    if (options.triggerHooks !== false) {
      const hook = blend.hook ?? sig.hook;
      const payload = {
        waveStyle: sig.waveStyle ?? "default",
        tool: "chat",
        conversationStage: blend.stage,
      };

      if (hook === "memory_retrieval") {
        this.trigger("memory_retrieval", payload);
        this.depthField.boostRecallDepth(NEURAL_CONFIG.depth.recallBoost || 0.45);
        this.camera.boostRecallDive((sig.cameraDive ?? 0.25) * 0.75);
        this.ghostLayer.setRecallActive(true, 0);
      } else if (hook === "reasoning") {
        this.trigger("reasoning", payload);
        this.camera.boostRecallDive((sig.cameraDive ?? 0.45) * 0.85);
      } else if (hook === "voice") {
        this.trigger("voice", payload);
        this.camera.boostRecallDive(0.1);
      } else if (hook === "tool_usage") {
        this.trigger("tool_usage", payload);
      } else if (hook === "brain_activity") {
        this.trigger("brain_activity", payload);
        if (sig.cameraDive > 0.35) {
          this.camera.boostRecallDive(sig.cameraDive * 0.7);
        }
      }

      if (sig.outgoingPulse) {
        this.trigger("speaking", { waveStyle: "outbound_calm" });
      }
    }

    if (sig.cognitiveState) {
      this.setCognitiveState(sig.cognitiveState);
    }
    if (sig.masterState) {
      this.setMasterState(sig.masterState);
    } else if (blend.regions?.length) {
      this.setMasterState("WORKING");
      this.setMode("thinking");
    }

    if (options.eventType === "conversation_finished") {
      this.state.clearConversationActivityOverlay();
      this.ghostLayer.setRecallActive(false, 0);
      this.setMasterState("IDLE");
      this.setMode("idle");
    }
  }

  /** @param {string} hookName @param {Function} callback */
  on(hookName, callback) {
    this.state.on(hookName, callback);
  }

  getState() {
    return this.state.getSnapshot();
  }

  getFps() {
    return this._fps;
  }

  _scheduleResize() {
    if (this._resizeTimer !== null) {
      clearTimeout(this._resizeTimer);
    }
    this._resizeTimer = setTimeout(() => {
      this._resizeTimer = null;
      this.resize();
    }, RESIZE_DEBOUNCE_MS);
  }

  /**
   * @param {{ immediate?: boolean, forceRebuild?: boolean, stageCache?: boolean }} [options]
   */
  resize(options = {}) {
    if (options.immediate && this._resizeTimer !== null) {
      clearTimeout(this._resizeTimer);
      this._resizeTimer = null;
    }

    const parent = this.canvas.parentElement;
    const width = parent?.clientWidth || window.innerWidth;
    const height = parent?.clientHeight || window.innerHeight;
    if (width < 1 || height < 1) return;

    const budgets = this.quality.getBudgets();
    const dw = Math.abs(width - this._lastWidth);
    const dh = Math.abs(height - this._lastHeight);
    const sizeChangedMaterially =
      this._lastWidth === 0 ||
      this._lastHeight === 0 ||
      dw >= MIN_RESIZE_DELTA_PX ||
      dh >= MIN_RESIZE_DELTA_PX;
    const needsGeometry =
      options.forceRebuild || this.quality.needsGeometryRebuild() || sizeChangedMaterially;

    // Minor chrome resize — update canvas CSS size only, keep cache.
    if (!needsGeometry && !sizeChangedMaterially) {
      return;
    }

    this._lastWidth = width;
    this._lastHeight = height;

    this.camera.resize(width, height);
    this.renderer.resize(width, height, budgets, {
      invalidateStatic: Boolean(needsGeometry || options.forceRebuild),
      stageCache: Boolean(options.stageCache),
    });

    if (needsGeometry) {
      this._rebuildGeometry(width, height, budgets);
    }

    this.perf.updateMeta({
      canvasWidth: width,
      canvasHeight: height,
      dpr: this.renderer.dpr,
      qualityMode: budgets.mode,
      qualityTier: budgets.tierLabel,
      rafLoops: this.scheduler.getActiveRafCount(),
      staticRebuilds: this.renderer.getStaticRebuildCount(),
      paused: this.state.isPaused,
    });
  }

  /**
   * @param {number} width
   * @param {number} height
   * @param {ReturnType<QualityController["getBudgets"]>} budgets
   */
  _rebuildGeometry(width, height, budgets) {
    const density = this._baseDensity * budgets.nodeDensityScale;
    this.nodes.setDensity(density);
    this.nodes.setMaxNodeCount(budgets.maxNodeCount);
    const densityScale = this.state.getDensityScale();
    this.nodes.build(width, height, densityScale);
    this.ghostLayer._built = false;
    this.ghostLayer.build(this.camera);
    this.quality.markGeometryClean();
    this.renderer.invalidateStaticCache();
    this._geometryBuildCount += 1;
    this.perf.recordGeometryRebuild();
    this._pendingQualityRebuild = false;
  }

  /** Pause decorative DOM particles when emergency / chat pending. */
  _syncPresenceDecorations() {
    const budgets = this.quality.getBudgets();
    const root = document.getElementById("titan-v2-root") || document.documentElement;
    const light = budgets.emergency || budgets.chatPending || budgets.mode === "performance";
    root.classList.toggle("tdl-v2--perf-light", light);
    root.dataset.qualityMode = budgets.mode;
    root.dataset.qualityTier = budgets.tierLabel;
  }

  /**
   * Primary display-clock callback (shared FrameScheduler).
   * @param {{ timestamp: number, deltaMs: number, frameIndex: number, clamped?: boolean }} frame
   */
  _onFrame(frame) {
    if (this._destroyed || this.state.isPaused || document.hidden) {
      this.frameId = null;
      this.perf.updateMeta({ paused: true, rafLoops: 0 });
      return;
    }

    this.frameId = 1;
    this._frameCounter = frame.frameIndex;
    const deltaMs = frame.deltaMs;
    const timestamp = frame.timestamp;
    const budgets = this.quality.getBudgets();
    const reduced = prefersReducedMotion() || budgets.reducedMotion;
    const interactive = this.quality.isInteractive();
    const chatPending = Boolean(this._chatPending) || budgets.chatPending;

    this.quality.advanceFade(deltaMs, timestamp);

    // Reduced motion: update Core slowly, skip most decorative.
    if (reduced && frame.frameIndex % 4 !== 0) {
      this.perf.recordSkippedFrame();
      this.state.update(timestamp, 0);
      this.renderer.renderLight(this.camera, this.nodes, this.state, budgets);
      this._syncCameraDom();
      return;
    }

    this._fps = deltaMs > 0 ? Math.round(1000 / deltaMs) : 60;
    this.perf.recordFrame(deltaMs || 16.7);

    const frameStart = performance.now();
    this.update(timestamp, deltaMs, budgets);

    // Deferred emergency / quality rebuild — never hitch mid-draw.
    if (this._pendingEmergencyRebuild) {
      this._pendingEmergencyRebuild = false;
      this.resize({ immediate: true, forceRebuild: true, stageCache: true });
    }

    const elapsedUpdate = performance.now() - frameStart;
    const overBudget = elapsedUpdate > budgets.frameBudgetMs * 0.55;
    const decoCadence = Math.max(1, budgets.decorativeCadence ?? 2);
    const decorativeDue = frame.frameIndex % decoCadence === 0;
    const skipDecorative =
      ((interactive || chatPending) && budgets.interactiveSkipDecorative) ||
      overBudget ||
      (chatPending && !decorativeDue);

    if (skipDecorative) {
      this.perf.recordDroppedDecorative();
      this.renderer.renderLight(this.camera, this.nodes, this.state, budgets, deltaMs);
    } else {
      this.draw(budgets, deltaMs, frame.frameIndex);
    }

    this.quality.sampleFrame(performance.now() - frameStart, timestamp);

    // Auto emergency watchdog — stage rebuild next frame (no mid-tick hitch).
    const rolling = this.perf.getSnapshot().rollingFps;
    const emergencyChanged = this.quality.sampleRollingFps(rolling, timestamp);
    if (emergencyChanged) {
      this._pendingEmergencyRebuild = true;
      this.renderer.markStaticRebuildPending();
      this._syncPresenceDecorations();
    }

    this._syncCameraDom();

    // Throttle meta object churn — reuse one budgets summary.
    if (!this._metaBudgets) this._metaBudgets = {};
    this._metaBudgets.maxEdgesDrawn = budgets.maxEdgesDrawn;
    this._metaBudgets.maxTissueDrawn = budgets.maxTissueDrawn;
    this._metaBudgets.maxNodeCount = budgets.maxNodeCount;
    this._metaBudgets.dustCount = budgets.dustCount;
    this._metaBudgets.targetVisualHz = budgets.targetVisualHz;
    this._metaBudgets.emergency = budgets.emergency;
    this.perf.updateMeta({
      paused: false,
      rafLoops: this.scheduler.getActiveRafCount(),
      qualityMode: budgets.mode,
      qualityTier: this.quality.getTierLabel(),
      dpr: this.renderer.dpr,
      budgets: this._metaBudgets,
      staticRebuilds: this.renderer.getStaticRebuildCount(),
    });
  }

  /**
   * Legacy entry — forwards to shared scheduler path for tests.
   * @param {number} timestamp
   */
  tick(timestamp) {
    this._onFrame({
      timestamp,
      deltaMs: 16.7,
      frameIndex: this._frameCounter + 1,
      clamped: false,
    });
  }

  /**
   * @param {number} timestamp
   * @param {number} deltaMs
   * @param {ReturnType<QualityController["getBudgets"]>} [budgets]
   */
  update(timestamp, deltaMs, budgets) {
    const q = budgets ?? this.quality.getBudgets();
    this.state.update(timestamp, deltaMs);
    const intensity = this.state.getIntensity();
    const breathe = this.state.getBreathe();
    const recallDive = this.depthField.getRecallDive();

    this.regionFocus.decay(deltaMs);
    const attraction = this.regionFocus.getAttractionPoint(this.camera.worldWidth, this.camera.worldHeight);

    if (
      attraction &&
      attraction.pull > 0.08 &&
      (this.state.isThinking() || this.state.masterState === "WORKING") &&
      !q.lightenThinking
    ) {
      const exec = NEURAL_CONFIG.execution || {};
      this.nodes.activateWorldPoint(attraction.x, attraction.y, {
        radiusRatio: exec.regionRadiusRatio ?? 0.14,
        glow: (exec.regionGlow ?? 0.55) * Math.min(1, attraction.pull),
      });
    }

    this.camera.update(deltaMs, intensity, breathe, this.state, recallDive, attraction);
    this.nodes.update(deltaMs, this.state);
    if (!q.chatPending) {
      this.nodes.trySpawnConnection(timestamp, intensity, this.state.getConnectionProbabilityScale());
    }

    this.state.signalLighten = Boolean(q.lightenThinking || q.emergency || q.chatPending);
    if (q.lightenThinking || q.emergency) {
      this.signals.update(timestamp, deltaMs * 0.35, this.state);
    } else {
      this.signals.update(timestamp, deltaMs, this.state);
    }
    this.depthField.update(deltaMs, this.camera, this.state);

    const signature = this.state.getCognitiveSignature();
    if (!q.emergency && !q.chatPending) {
      this.cognitiveOverlay.update(deltaMs, signature);
    }

    const recallActive =
      this.state.cognitiveState === "memory_recall" || this.state.masterState === "DEPTH_RECALL";
    this.ghostLayer.setRecallActive(recallActive || signature?.ghostActivity, deltaMs);
    if ((recallActive || signature?.ghostActivity) && !q.emergency) {
      this.ghostLayer.update(deltaMs, this.camera);
    }

    if (this.state.bootComplete && this.state.masterState === "BOOTING") {
      this.state.masterState = "AWAKE";
    }
    if (this.state.bootComplete && this.state.masterState === "AWAKE") {
      this.state.masterState = "IDLE";
    }
  }

  /**
   * @param {ReturnType<QualityController["getBudgets"]>} [budgets]
   * @param {number} [deltaMs]
   * @param {number} [frameIndex]
   */
  draw(budgets, deltaMs = 16.7, frameIndex = 0) {
    const q = budgets ?? this.quality.getBudgets();
    this.renderer.render(
      this.camera,
      this.nodes,
      this.signals,
      this.state,
      this.depthField,
      this.cognitiveOverlay,
      this.ghostLayer,
      q,
      deltaMs,
      frameIndex,
    );
    if (!this.renderer.isStaticCacheDirty()) {
      this.quality.markStaticCacheClean();
    }
  }

  _syncCameraDom() {
    if (!this.cameraEl) return;
    this.cameraEl.style.transform = this.camera.getDomTransform();
  }

  _applyCssClasses() {
    const masterClass = getMasterCssClass(this.state.masterState);
    const cognitiveClasses = getAllCognitiveCssClasses();
    for (const cls of cognitiveClasses) {
      this.canvas.classList.remove(cls);
    }
    for (const cls of Object.values({
      BOOTING: "tdl-v2-neural-canvas--booting",
      AWAKE: "tdl-v2-neural-canvas--awake",
      IDLE: "tdl-v2-neural-canvas--idle",
      LISTENING: "tdl-v2-neural-canvas--listening",
      THINKING: "tdl-v2-neural-canvas--thinking",
      WORKING: "tdl-v2-neural-canvas--working",
      SPEAKING: "tdl-v2-neural-canvas--speaking",
      DEPTH_RECALL: "tdl-v2-neural-canvas--depth-recall",
      ERROR: "tdl-v2-neural-canvas--error",
      SLEEP: "tdl-v2-neural-canvas--sleep",
    })) {
      this.canvas.classList.remove(cls);
    }

    this.canvas.classList.add(masterClass);
    this.canvas.classList.add(getCognitiveCssClass(this.state.cognitiveState));
    this.canvas.classList.toggle("tdl-v2-neural-canvas--thinking", this.state.isThinking());
    this.canvas.classList.toggle(
      "tdl-v2-neural-canvas--depth-recall",
      this.state.cognitiveState === "memory_recall" || this.state.masterState === "DEPTH_RECALL",
    );
    this.canvas.classList.toggle(
      "tdl-v2-neural-canvas--error-master",
      this.state.masterState === "ERROR" || this.state.cognitiveState === "error",
    );
    this.canvas.classList.toggle(
      "tdl-v2-neural-canvas--sleep-master",
      this.state.masterState === "SLEEP" || this.state.cognitiveState === "sleep",
    );
  }

  /** @param {string} stateId */
  _applyCognitiveDepth(stateId) {
    if (stateId === "memory_recall") {
      const recallBoost = NEURAL_CONFIG.depth.recallBoost || 0.45;
      this.depthField.boostRecallDepth(recallBoost * 0.85);
      this.camera.boostRecallDive(recallBoost * 0.7);
    } else if (stateId === "reasoning") {
      this.depthField.boostRecallDepth(0.28);
      this.camera.boostRecallDive(0.42);
    } else if (stateId === "obsidian") {
      this.depthField.boostRecallDepth(0.18);
      this.camera.boostRecallDive(0.22);
    }
  }

  /** @param {string} stateId */
  _syncRegionFocus(stateId) {
    const regions = RegionFocus.mapCognitiveToRegions(stateId);
    for (const region of regions) {
      this.regionFocus.setFocus(region, 0.85);
    }
  }
}

export { MIN_RESIZE_DELTA_PX, RESIZE_DEBOUNCE_MS, NEURAL_FRAME_ID };
