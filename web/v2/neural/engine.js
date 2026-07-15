/** Titan Neural Renderer V3 — Engine orchestrator (STATE · WORLD · CAMERA · RENDERER). */

import { NEURAL_CONFIG } from "./config.js";
import { CognitiveOverlay, getAllCognitiveCssClasses, getCognitiveCssClass, getMasterCssClass } from "./cognitive.js";
import { NeuralCamera } from "./camera.js";
import { DepthField } from "./depth.js";
import { GhostLayer } from "./ghosts.js";
import { NeuralNodes } from "./nodes.js";
import { RegionFocus } from "./regions.js";
import { NeuralRenderer } from "./renderer.js";
import { NeuralSignals } from "./signals.js";
import { NeuralState } from "./state.js";
import { prefersReducedMotion } from "./utils.js";

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

    this.depthField.setInfiniteEnabled(true);

    /** @type {number | null} */
    this.frameId = null;
    /** @type {ResizeObserver | null} */
    this.resizeObserver = null;
    this._lastFrameTime = 0;
    this._frameSkipCounter = 0;
    /** @type {number[]} */
    this._frameSamples = [];
    this._lastDensityAdjust = 0;
    this._baseDensity = options.density ?? NEURAL_CONFIG.nodes.densityDefault;
    this._fps = 60;

    this._boundResize = () => this.resize();
    this._boundTick = (ts) => this.tick(ts);
    this._boundVisibility = () => this._onVisibilityChange();
  }

  init() {
    if (this.options.density) {
      this._baseDensity = this.options.density;
      this.nodes.setDensity(this.options.density);
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

    this.resize();
    this.frameId = requestAnimationFrame(this._boundTick);
  }

  destroy() {
    if (this.frameId !== null) {
      cancelAnimationFrame(this.frameId);
      this.frameId = null;
    }
    window.removeEventListener("resize", this._boundResize);
    document.removeEventListener("visibilitychange", this._boundVisibility);
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
  }

  _onVisibilityChange() {
    this.state.setVisible(!document.hidden);
    if (!document.hidden && this.frameId === null && !this.state.isPaused) {
      this._lastFrameTime = 0;
      this.frameId = requestAnimationFrame(this._boundTick);
    }
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

  resize() {
    const parent = this.canvas.parentElement;
    const width = parent?.clientWidth || window.innerWidth;
    const height = parent?.clientHeight || window.innerHeight;
    if (width < 1 || height < 1) return;

    this.camera.resize(width, height);
    this.renderer.resize(width, height);
    const densityScale = this.state.getDensityScale();
    this.nodes.build(width, height, densityScale);
    this.ghostLayer._built = false;
    this.ghostLayer.build(this.camera);
  }

  /** @param {number} timestamp */
  tick(timestamp) {
    if (this.state.isPaused) {
      this.frameId = null;
      return;
    }

    if (!this._lastFrameTime) {
      this._lastFrameTime = timestamp;
    }

    let deltaMs = Math.min(timestamp - this._lastFrameTime, 50);
    const reduced = prefersReducedMotion();

    if (reduced) {
      this._frameSkipCounter += 1;
      if (this._frameSkipCounter % 4 !== 0) {
        this.frameId = requestAnimationFrame(this._boundTick);
        return;
      }
      deltaMs = 0;
    } else {
      this._frameSkipCounter = 0;
    }

    this._fps = deltaMs > 0 ? Math.round(1000 / deltaMs) : 60;
    this._lastFrameTime = timestamp;

    this.update(timestamp, deltaMs);
    this.draw();
    this._trackAdaptivePerformance(deltaMs, timestamp);
    this._syncCameraDom();

    this.frameId = requestAnimationFrame(this._boundTick);
  }

  /** @param {number} timestamp @param {number} deltaMs */
  update(timestamp, deltaMs) {
    this.state.update(timestamp, deltaMs);
    const intensity = this.state.getIntensity();
    const breathe = this.state.getBreathe();
    const recallDive = this.depthField.getRecallDive();

    this.regionFocus.decay(deltaMs);
    const attraction = this.regionFocus.getAttractionPoint(this.camera.worldWidth, this.camera.worldHeight);

    // Local regional life — thinking / execution never flash the whole field.
    if (attraction && attraction.pull > 0.08 && (this.state.isThinking() || this.state.masterState === "WORKING")) {
      const exec = NEURAL_CONFIG.execution || {};
      this.nodes.activateWorldPoint(attraction.x, attraction.y, {
        radiusRatio: exec.regionRadiusRatio ?? 0.14,
        glow: (exec.regionGlow ?? 0.55) * Math.min(1, attraction.pull),
      });
    }

    this.camera.update(deltaMs, intensity, breathe, this.state, recallDive, attraction);
    this.nodes.update(deltaMs, this.state);
    this.nodes.trySpawnConnection(timestamp, intensity, this.state.getConnectionProbabilityScale());
    this.signals.update(timestamp, deltaMs, this.state);
    this.depthField.update(deltaMs, this.camera, this.state);

    const signature = this.state.getCognitiveSignature();
    this.cognitiveOverlay.update(deltaMs, signature);

    const recallActive =
      this.state.cognitiveState === "memory_recall" || this.state.masterState === "DEPTH_RECALL";
    this.ghostLayer.setRecallActive(recallActive || signature?.ghostActivity, deltaMs);
    if (recallActive || signature?.ghostActivity) {
      this.ghostLayer.update(deltaMs, this.camera);
    }

    if (this.state.bootComplete && this.state.masterState === "BOOTING") {
      this.state.masterState = "AWAKE";
    }
    if (this.state.bootComplete && this.state.masterState === "AWAKE") {
      this.state.masterState = "IDLE";
    }
  }

  draw() {
    this.renderer.render(
      this.camera,
      this.nodes,
      this.signals,
      this.state,
      this.depthField,
      this.cognitiveOverlay,
      this.ghostLayer,
    );
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

  /** @param {number} deltaMs @param {number} timestamp */
  _trackAdaptivePerformance(deltaMs, timestamp) {
    const perfCfg = NEURAL_CONFIG.performance;
    if (!perfCfg.adaptiveNodeCount) return;

    this._frameSamples.push(deltaMs);
    const windowSize = perfCfg.sampleWindow || 45;
    if (this._frameSamples.length > windowSize) {
      this._frameSamples.shift();
    }
    if (this._frameSamples.length < windowSize) return;
    if (timestamp - this._lastDensityAdjust < (perfCfg.densityRecoverMs || 8000)) {
      return;
    }

    const avg = this._frameSamples.reduce((a, b) => a + b, 0) / this._frameSamples.length;
    const budget = perfCfg.frameBudgetMs || 16.8;
    const floor = perfCfg.densityFloor || 0.55;
    const current = this.nodes.density;

    if (avg > budget * 1.08 && current > floor) {
      this.nodes.setDensity(Math.max(floor, current * 0.9));
      this.nodes.build(this.camera.width, this.camera.height, this.state.getDensityScale());
      this.depthField.setDepthBudget(Math.max(0.65, this.depthField._depthBudget * 0.92));
      this._lastDensityAdjust = timestamp;
    } else if (avg < budget * 0.82 && current < this._baseDensity) {
      this.nodes.setDensity(Math.min(this._baseDensity, current * 1.04));
      this.nodes.build(this.camera.width, this.camera.height, this.state.getDensityScale());
      this.depthField.setDepthBudget(Math.min(1, this.depthField._depthBudget * 1.03));
      this._lastDensityAdjust = timestamp;
    }
  }
}
