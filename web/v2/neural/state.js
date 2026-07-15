/** Titan Neural Renderer V2 — State machine & activity hooks. */

import { NEURAL_CONFIG } from "./config.js";
import { prefersReducedMotion } from "./utils.js";
import {
  blendCognitiveSignatures,
  getCognitiveSignature,
  normalizeCognitiveState,
} from "./cognitive.js";

export class NeuralState {
  constructor() {
    this.mode = "idle";
    this.masterState = "BOOTING";
    this.cognitiveState = "idle";
    this.previousCognitiveState = "idle";
    this.cognitiveBlend = 1;
    this.cognitiveBlendSpeed = 0.0022;
    /** @type {object} */
    this.activeSignature = getCognitiveSignature("idle");

    this.activityLevel = 0;
    this.thinkingIntensity = 0;
    this.breathePhase = 0;
    this.bootProgress = 0;
    this.bootComplete = false;
    this.isVisible = true;
    this.isPaused = false;
    this.presenceGlow = 0.38;
    this.presenceBreatheSpeed = 1;
    this.presenceSignalDensity = 0.35;
    this.vitalityPhase = Math.random() * Math.PI * 2;
    this.vitalityLevel = NEURAL_CONFIG.vitality.idleFloor;

    /** @type {Record<string, Function[]>} */
    this.hooks = {};
    for (const hook of NEURAL_CONFIG.activityHooks) {
      this.hooks[hook] = [];
    }

    this._pendingHookType = undefined;
    this._pendingActivation = undefined;
    this._pendingWaveStyle = undefined;
    this._pendingPreferDeep = undefined;
    this._pendingToolPattern = undefined;
    this._bootStartTime = 0;

    /** @type {object | null} */
    this._toolActivitySignature = null;
    /** @type {number} */
    this._toolActivityWeight = 0;

    /** @type {object | null} */
    this._memoryActivitySignature = null;
    /** @type {number} */
    this._memoryActivityWeight = 0;

    /** @type {object | null} */
    this._conversationActivitySignature = null;
    /** @type {number} */
    this._conversationActivityWeight = 0;
  }

  /** @param {string} masterState */
  setMasterState(masterState) {
    this.masterState = masterState;
    if (masterState === "BOOTING" && !this._bootStartTime) {
      this._bootStartTime = performance.now();
      this.bootProgress = 0;
      this.bootComplete = false;
    }
    if (masterState === "AWAKE" || masterState === "IDLE") {
      this.bootComplete = true;
      this.bootProgress = 1;
    }
  }

  /** @param {string} stateName */
  setCognitiveState(stateName) {
    const normalized = normalizeCognitiveState(stateName);
    if (normalized === this.cognitiveState) return normalized;

    this.previousCognitiveState = this.cognitiveState;
    this.cognitiveState = normalized;
    this.cognitiveBlend = 0;

    const signature = getCognitiveSignature(normalized);
    this.cognitiveBlendSpeed = 1 / Math.max(signature.transitionMs || 700, 320);
    this.setMode(signature.neuralMode || "idle");
    return normalized;
  }

  /** @param {string} mode */
  setMode(mode) {
    this.mode = mode === "thinking" ? "thinking" : "idle";
  }

  setVisible(visible) {
    this.isVisible = visible;
    this.isPaused = NEURAL_CONFIG.performance.hiddenTabPause && !visible;
  }

  /** @param {object} [profile] */
  setPresenceProfile(profile) {
    if (!profile) return;
    if (profile.glowLevel !== undefined) this.presenceGlow = profile.glowLevel;
    if (profile.breatheSpeed !== undefined) this.presenceBreatheSpeed = profile.breatheSpeed;
    if (profile.signalDensity !== undefined) this.presenceSignalDensity = profile.signalDensity;
  }

  /** @param {number} timestamp @param {number} deltaMs */
  update(timestamp, deltaMs) {
    if (!this._bootStartTime) {
      this._bootStartTime = timestamp;
    }

    const bootMs = NEURAL_CONFIG.boot.awakeMs;
    if (!this.bootComplete && this.masterState === "BOOTING") {
      this.bootProgress = Math.min(1, (timestamp - this._bootStartTime) / bootMs);
      if (this.bootProgress >= 1) {
        this.bootComplete = true;
        this.masterState = "AWAKE";
      }
    }

    if (prefersReducedMotion()) {
      this._updateCognitiveBlend(deltaMs);
      return;
    }

    this._updateCognitiveBlend(deltaMs);

    const signature = this.getCognitiveSignature();
    const breatheSpeed =
      (NEURAL_CONFIG.nodes.breatheSpeed || 0.00038) *
      (signature.breatheSpeed || 1) *
      this.presenceBreatheSpeed;
    const vitalityCfg = NEURAL_CONFIG.vitality;

    this.breathePhase += breatheSpeed * deltaMs;
    this.vitalityPhase += (vitalityCfg.oscillationSpeed || 0.00055) * deltaMs;

    const vitalityWave = (Math.sin(this.vitalityPhase) + 1) * 0.5;
    this.vitalityLevel =
      vitalityCfg.idleFloor + vitalityWave * (vitalityCfg.idleCeiling - vitalityCfg.idleFloor);

    const activityTarget = signature.activityTarget ?? 0.08;
    const thinkingTarget = signature.thinkingTarget ?? 0;
    const riseRate = this.mode === "thinking" ? 0.04 : 0.028;
    const decayRate = NEURAL_CONFIG.thinking.decayRate;

    if (this.activityLevel < activityTarget) {
      this.activityLevel = Math.min(activityTarget, this.activityLevel + riseRate);
    } else {
      this.activityLevel = Math.max(activityTarget, this.activityLevel - decayRate * 0.65);
    }

    if (this.thinkingIntensity < thinkingTarget) {
      this.thinkingIntensity = Math.min(thinkingTarget, this.thinkingIntensity + 0.035);
    } else {
      this.thinkingIntensity = Math.max(thinkingTarget, this.thinkingIntensity - decayRate);
    }

    if (signature.signalDensity !== undefined) {
      this.presenceSignalDensity = signature.signalDensity;
    }
    if (signature.glowLevel !== undefined) {
      this.presenceGlow = signature.glowLevel;
    }
  }

  /** @param {number} deltaMs */
  _updateCognitiveBlend(deltaMs) {
    if (this.cognitiveBlend < 1) {
      this.cognitiveBlend = Math.min(1, this.cognitiveBlend + this.cognitiveBlendSpeed * deltaMs);
    }
    let signature = blendCognitiveSignatures(
      this.previousCognitiveState,
      this.cognitiveState,
      this.cognitiveBlend,
    );

    signature = this._blendActivityOverlay(signature, this._toolActivitySignature, this._toolActivityWeight);
    signature = this._blendActivityOverlay(signature, this._memoryActivitySignature, this._memoryActivityWeight);
    signature = this._blendActivityOverlay(
      signature,
      this._conversationActivitySignature,
      this._conversationActivityWeight,
    );

    this.activeSignature = signature;
  }

  /**
   * Overlay blended tool activity on cognitive signature (Phase E5).
   * @param {object | null} signature
   * @param {number} [weight=0.5]
   */
  setToolActivityOverlay(signature, weight = 0.5) {
    this._toolActivitySignature = signature;
    this._toolActivityWeight = Math.max(0, Math.min(1, weight));
  }

  clearToolActivityOverlay() {
    this._toolActivitySignature = null;
    this._toolActivityWeight = 0;
  }

  /**
   * Overlay blended memory activity on cognitive signature (Phase E6).
   * @param {object | null} signature
   * @param {number} [weight=0.5]
   */
  setMemoryActivityOverlay(signature, weight = 0.5) {
    this._memoryActivitySignature = signature;
    this._memoryActivityWeight = Math.max(0, Math.min(1, weight));
  }

  clearMemoryActivityOverlay() {
    this._memoryActivitySignature = null;
    this._memoryActivityWeight = 0;
  }

  /**
   * Overlay blended conversation activity on cognitive signature (Phase E7).
   * @param {object | null} signature
   * @param {number} [weight=0.5]
   */
  setConversationActivityOverlay(signature, weight = 0.5) {
    this._conversationActivitySignature = signature;
    this._conversationActivityWeight = Math.max(0, Math.min(1, weight));
  }

  clearConversationActivityOverlay() {
    this._conversationActivitySignature = null;
    this._conversationActivityWeight = 0;
  }

  /**
   * @param {object} signature
   * @param {object | null} overlay
   * @param {number} weight
   */
  _blendActivityOverlay(signature, overlay, weight) {
    if (!overlay || weight <= 0.02) return signature;

    const blended = { ...signature };
    for (const key of Object.keys(overlay)) {
      const a = blended[key];
      const b = overlay[key];
      if (typeof b === "number") {
        blended[key] = (typeof a === "number" ? a : 0) * (1 - weight) + b * weight;
      } else if (typeof b === "boolean") {
        blended[key] = weight >= 0.4 ? b || Boolean(a) : Boolean(a);
      } else if (b !== undefined) {
        blended[key] = weight >= 0.55 ? b : a;
      }
    }
    return blended;
  }

  getCognitiveSignature() {
    return this.activeSignature;
  }

  getBreathe() {
    return (Math.sin(this.breathePhase) + 1) * 0.5;
  }

  isThinking() {
    return this.mode === "thinking" || this.thinkingIntensity > 0.05;
  }

  getIntensity() {
    const bootScale = 0.35 + this.bootProgress * 0.65;
    return Math.max(
      this.thinkingIntensity,
      this.activityLevel,
      this.presenceGlow * 0.35,
      this.vitalityLevel,
    ) * bootScale;
  }

  getVitality() {
    return this.vitalityLevel;
  }

  getDensityScale() {
    return 0.4 + this.bootProgress * 0.6;
  }

  getConnectionProbabilityScale() {
    if (this.bootProgress < 0.4) return 0;
    if (this.bootProgress < 0.8) return (this.bootProgress - 0.4) / 0.4;
    return 1;
  }

  /** @param {string} hookName @param {Function} callback */
  on(hookName, callback) {
    if (!this.hooks[hookName] || typeof callback !== "function") return;
    this.hooks[hookName].push(callback);
  }

  /** @param {string} hookName @param {object} [payload] */
  trigger(hookName, payload) {
    if (!this.hooks[hookName]) return;

    const event = { type: hookName, payload: payload ?? {}, timestamp: performance.now() };
    for (const cb of this.hooks[hookName]) {
      try {
        cb(event);
      } catch {
        /* hook errors must not break render loop */
      }
    }
    this._applyActivityPulse(hookName, payload);
  }

  /** @param {string} hookName @param {object} [payload] */
  _applyActivityPulse(hookName, payload) {
    let boost = 0.15;
    if (hookName === "brain_activity" || hookName === "reasoning") {
      boost = 0.35;
      this.setCognitiveState(hookName === "reasoning" ? "reasoning" : "thinking");
    } else if (hookName === "tool_usage") {
      boost = 0.28;
    } else if (hookName === "memory_retrieval") {
      boost = 0.22;
      this.setCognitiveState("memory_recall");
      this.masterState = "DEPTH_RECALL";
    } else if (hookName === "voice") {
      boost = 0.4;
      this.setCognitiveState("listening");
      this.masterState = "LISTENING";
    } else if (hookName === "speaking") {
      boost = 0.32;
      this.setCognitiveState("voice");
      this.masterState = "SPEAKING";
    } else if (hookName === "browser_research") {
      boost = 0.3;
      this.setCognitiveState("browser_research");
      this.masterState = "WORKING";
    }

    this.activityLevel = Math.min(1, this.activityLevel + boost);
    this._pendingHookType = hookName;

    if (payload?.originNodeId !== undefined) {
      this._pendingActivation = payload.originNodeId;
    }

    const signature = this.getCognitiveSignature();
    this._pendingWaveStyle = payload?.waveStyle ?? signature.waveStyle ?? "default";
    this._pendingPreferDeep = hookName === "memory_retrieval" || Boolean(signature.preferDeep);
    this._pendingToolPattern = payload?.tool;

    if (payload?.tool) {
      const toolState = normalizeCognitiveState(payload.tool);
      if (toolState !== "idle" && toolState !== "tool_execution") {
        this.setCognitiveState(toolState);
      } else if (hookName === "tool_usage") {
        this.setCognitiveState("tool_execution");
      }
      this.masterState = "WORKING";
    }
  }

  consumePendingWaveStyle() {
    const style = this._pendingWaveStyle;
    this._pendingWaveStyle = undefined;
    return style;
  }

  consumePendingActivation() {
    const id = this._pendingActivation;
    this._pendingActivation = undefined;
    return id;
  }

  consumePendingHookType() {
    const hook = this._pendingHookType;
    this._pendingHookType = undefined;
    return hook;
  }

  consumePreferDeep() {
    const deep = this._pendingPreferDeep;
    this._pendingPreferDeep = undefined;
    return Boolean(deep);
  }

  consumeToolPattern() {
    const tool = this._pendingToolPattern;
    this._pendingToolPattern = undefined;
    return tool;
  }

  getSnapshot() {
    return {
      mode: this.mode,
      masterState: this.masterState,
      cognitiveState: this.cognitiveState,
      previousCognitiveState: this.previousCognitiveState,
      cognitiveBlend: this.cognitiveBlend,
      activityLevel: this.activityLevel,
      thinkingIntensity: this.thinkingIntensity,
      bootProgress: this.bootProgress,
      isPaused: this.isPaused,
      isVisible: this.isVisible,
      breathe: this.getBreathe(),
      signature: this.getCognitiveSignature(),
    };
  }
}
