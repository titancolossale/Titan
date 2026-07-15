/**
 * Titan Cognitive Visualization Engine — Phase 21.0
 *
 * Abstract neural signatures per cognitive state. Never exposes reasoning or prompts.
 */
(function (global) {
  "use strict";

  var TitanNeural = (global.TitanNeural = global.TitanNeural || {});

  var STATE_IDS = [
    "idle",
    "listening",
    "thinking",
    "deep_analysis",
    "memory_retrieval",
    "planning",
    "tool_usage",
    "trading_analysis",
    "browser_research",
    "calendar_planning",
    "email_processing",
    "voice_speaking",
  ];

  /** Public hook aliases → canonical cognitive state id */
  var STATE_ALIASES = {
    idle: "idle",
    listening: "listening",
    thinking: "thinking",
    deep: "deep_analysis",
    deep_analysis: "deep_analysis",
    analysis: "deep_analysis",
    reasoning: "deep_analysis",
    memory: "memory_retrieval",
    memory_retrieval: "memory_retrieval",
    recall: "memory_retrieval",
    planning: "planning",
    plan: "planning",
    tool: "tool_usage",
    tool_usage: "tool_usage",
    working: "tool_usage",
    trading: "trading_analysis",
    trading_analysis: "trading_analysis",
    browser: "browser_research",
    browser_research: "browser_research",
    exploration: "browser_research",
    research: "browser_research",
    calendar: "calendar_planning",
    calendar_planning: "calendar_planning",
    email: "email_processing",
    email_processing: "email_processing",
    writing: "tool_usage",
    verification: "deep_analysis",
    verify: "deep_analysis",
    voice: "voice_speaking",
    speaking: "voice_speaking",
    voice_speaking: "voice_speaking",
  };

  var CSS_CLASS_MAP = {
    idle: "tdl-neural-canvas--cognitive-idle",
    listening: "tdl-neural-canvas--cognitive-listening",
    thinking: "tdl-neural-canvas--cognitive-thinking",
    deep_analysis: "tdl-neural-canvas--cognitive-deep",
    memory_retrieval: "tdl-neural-canvas--cognitive-memory",
    planning: "tdl-neural-canvas--cognitive-planning",
    tool_usage: "tdl-neural-canvas--cognitive-tool",
    trading_analysis: "tdl-neural-canvas--cognitive-trading",
    browser_research: "tdl-neural-canvas--cognitive-browser",
    calendar_planning: "tdl-neural-canvas--cognitive-calendar",
    email_processing: "tdl-neural-canvas--cognitive-email",
    voice_speaking: "tdl-neural-canvas--cognitive-voice",
  };

  /**
   * Numeric visual targets blended each frame. Booleans gate overlay features.
   */
  var SIGNATURES = {
    idle: {
      neuralMode: "idle",
      activityTarget: 0.08,
      thinkingTarget: 0,
      glowLevel: 0.44,
      breatheSpeed: 0.92,
      signalDensity: 0.32,
      spawnIntervalMult: 1.45,
      maxSignalsMult: 0.48,
      speedMult: 0.62,
      cameraDive: 0,
      focusPull: 0,
      waveStyle: "central",
      waveBurst: 1,
      memoryFragments: false,
      neuralEchoes: false,
      distantRegions: false,
      longPaths: false,
      circularWaves: false,
      regionSync: false,
      distributedExploration: false,
      sharpSignals: false,
      fastSync: false,
      structuredGeometry: false,
      rhythmicPulse: false,
      localBursts: false,
      preferDeep: false,
      transitionMs: 900,
    },
    listening: {
      neuralMode: "idle",
      activityTarget: 0.22,
      thinkingTarget: 0.08,
      glowLevel: 0.52,
      breatheSpeed: 1.08,
      signalDensity: 0.38,
      spawnIntervalMult: 1.12,
      maxSignalsMult: 0.62,
      speedMult: 0.78,
      cameraDive: 0,
      focusPull: 0.12,
      waveStyle: "default",
      waveBurst: 1,
      memoryFragments: false,
      neuralEchoes: false,
      distantRegions: false,
      longPaths: false,
      circularWaves: false,
      regionSync: false,
      distributedExploration: false,
      sharpSignals: false,
      fastSync: false,
      structuredGeometry: false,
      rhythmicPulse: false,
      localBursts: true,
      preferDeep: false,
      transitionMs: 500,
    },
    thinking: {
      neuralMode: "thinking",
      activityTarget: 0.75,
      thinkingTarget: 0.82,
      glowLevel: 0.78,
      breatheSpeed: 1.22,
      signalDensity: 0.88,
      spawnIntervalMult: 0.34,
      maxSignalsMult: 1,
      speedMult: 1.05,
      cameraDive: 0.08,
      focusPull: 0.62,
      waveStyle: "default",
      waveBurst: 2,
      memoryFragments: false,
      neuralEchoes: false,
      distantRegions: false,
      longPaths: false,
      circularWaves: false,
      regionSync: false,
      distributedExploration: false,
      sharpSignals: false,
      fastSync: false,
      structuredGeometry: false,
      rhythmicPulse: false,
      localBursts: true,
      preferDeep: false,
      transitionMs: 700,
    },
    deep_analysis: {
      neuralMode: "thinking",
      activityTarget: 0.92,
      thinkingTarget: 0.95,
      glowLevel: 0.86,
      breatheSpeed: 1.28,
      signalDensity: 0.96,
      spawnIntervalMult: 0.26,
      maxSignalsMult: 1.15,
      speedMult: 0.92,
      cameraDive: 0.58,
      focusPull: 0.88,
      waveStyle: "slow",
      waveBurst: 3,
      memoryFragments: false,
      neuralEchoes: false,
      distantRegions: true,
      longPaths: true,
      circularWaves: false,
      regionSync: true,
      distributedExploration: false,
      sharpSignals: false,
      fastSync: false,
      structuredGeometry: false,
      rhythmicPulse: false,
      localBursts: true,
      preferDeep: true,
      transitionMs: 820,
    },
    memory_retrieval: {
      neuralMode: "thinking",
      activityTarget: 0.68,
      thinkingTarget: 0.45,
      glowLevel: 0.72,
      breatheSpeed: 1.05,
      signalDensity: 0.74,
      spawnIntervalMult: 0.52,
      maxSignalsMult: 0.88,
      speedMult: 0.82,
      cameraDive: 0.38,
      focusPull: 0.48,
      waveStyle: "deep_central",
      waveBurst: 2,
      memoryFragments: true,
      neuralEchoes: true,
      distantRegions: false,
      longPaths: true,
      circularWaves: false,
      regionSync: false,
      distributedExploration: false,
      sharpSignals: false,
      fastSync: false,
      structuredGeometry: false,
      rhythmicPulse: false,
      localBursts: false,
      preferDeep: true,
      transitionMs: 760,
    },
    planning: {
      neuralMode: "thinking",
      activityTarget: 0.72,
      thinkingTarget: 0.7,
      glowLevel: 0.7,
      breatheSpeed: 1.12,
      signalDensity: 0.8,
      spawnIntervalMult: 0.55,
      maxSignalsMult: 0.92,
      speedMult: 1.02,
      cameraDive: 0.14,
      focusPull: 0.55,
      waveStyle: "circular",
      waveBurst: 2,
      memoryFragments: false,
      neuralEchoes: false,
      distantRegions: false,
      longPaths: false,
      circularWaves: true,
      regionSync: true,
      distributedExploration: false,
      sharpSignals: false,
      fastSync: false,
      structuredGeometry: false,
      rhythmicPulse: false,
      localBursts: false,
      preferDeep: false,
      transitionMs: 680,
    },
    tool_usage: {
      neuralMode: "thinking",
      activityTarget: 0.65,
      thinkingTarget: 0.55,
      glowLevel: 0.66,
      breatheSpeed: 1.1,
      signalDensity: 0.76,
      spawnIntervalMult: 0.62,
      maxSignalsMult: 0.85,
      speedMult: 1,
      cameraDive: 0.1,
      focusPull: 0.42,
      waveStyle: "default",
      waveBurst: 1,
      memoryFragments: false,
      neuralEchoes: false,
      distantRegions: false,
      longPaths: false,
      circularWaves: false,
      regionSync: false,
      distributedExploration: false,
      sharpSignals: false,
      fastSync: false,
      structuredGeometry: false,
      rhythmicPulse: false,
      localBursts: true,
      preferDeep: false,
      transitionMs: 650,
    },
    trading_analysis: {
      neuralMode: "thinking",
      activityTarget: 0.85,
      thinkingTarget: 0.78,
      glowLevel: 0.8,
      breatheSpeed: 1.24,
      signalDensity: 0.92,
      spawnIntervalMult: 0.38,
      maxSignalsMult: 1.08,
      speedMult: 1.38,
      cameraDive: 0.18,
      focusPull: 0.72,
      waveStyle: "sharp",
      waveBurst: 3,
      memoryFragments: false,
      neuralEchoes: false,
      distantRegions: false,
      longPaths: false,
      circularWaves: false,
      regionSync: true,
      distributedExploration: false,
      sharpSignals: true,
      fastSync: true,
      structuredGeometry: true,
      rhythmicPulse: false,
      localBursts: true,
      preferDeep: false,
      transitionMs: 620,
    },
    browser_research: {
      neuralMode: "thinking",
      activityTarget: 0.82,
      thinkingTarget: 0.68,
      glowLevel: 0.76,
      breatheSpeed: 1.18,
      signalDensity: 0.9,
      spawnIntervalMult: 0.4,
      maxSignalsMult: 1.05,
      speedMult: 1.15,
      cameraDive: 0.16,
      focusPull: 0.55,
      waveStyle: "distributed",
      waveBurst: 3,
      memoryFragments: false,
      neuralEchoes: false,
      distantRegions: true,
      longPaths: true,
      circularWaves: false,
      regionSync: false,
      distributedExploration: true,
      sharpSignals: false,
      fastSync: false,
      structuredGeometry: false,
      rhythmicPulse: false,
      localBursts: false,
      preferDeep: false,
      transitionMs: 680,
    },
    calendar_planning: {
      neuralMode: "thinking",
      activityTarget: 0.62,
      thinkingTarget: 0.5,
      glowLevel: 0.64,
      breatheSpeed: 1.02,
      signalDensity: 0.7,
      spawnIntervalMult: 0.72,
      maxSignalsMult: 0.78,
      speedMult: 0.9,
      cameraDive: 0.08,
      focusPull: 0.38,
      waveStyle: "circular",
      waveBurst: 1,
      memoryFragments: false,
      neuralEchoes: false,
      distantRegions: false,
      longPaths: false,
      circularWaves: true,
      regionSync: true,
      distributedExploration: false,
      sharpSignals: false,
      fastSync: false,
      structuredGeometry: false,
      rhythmicPulse: false,
      localBursts: false,
      preferDeep: false,
      transitionMs: 700,
    },
    email_processing: {
      neuralMode: "thinking",
      activityTarget: 0.58,
      thinkingTarget: 0.48,
      glowLevel: 0.62,
      breatheSpeed: 0.98,
      signalDensity: 0.66,
      spawnIntervalMult: 0.78,
      maxSignalsMult: 0.72,
      speedMult: 0.85,
      cameraDive: 0.06,
      focusPull: 0.32,
      waveStyle: "distributed",
      waveBurst: 1,
      memoryFragments: false,
      neuralEchoes: false,
      distantRegions: false,
      longPaths: false,
      circularWaves: false,
      regionSync: false,
      distributedExploration: true,
      sharpSignals: false,
      fastSync: false,
      structuredGeometry: false,
      rhythmicPulse: false,
      localBursts: false,
      preferDeep: false,
      transitionMs: 720,
    },
    voice_speaking: {
      neuralMode: "thinking",
      activityTarget: 0.76,
      thinkingTarget: 0.58,
      glowLevel: 0.74,
      breatheSpeed: 1.18,
      signalDensity: 0.86,
      spawnIntervalMult: 0.44,
      maxSignalsMult: 0.9,
      speedMult: 1.1,
      cameraDive: 0.1,
      focusPull: 0.52,
      waveStyle: "circular",
      waveBurst: 2,
      memoryFragments: false,
      neuralEchoes: false,
      distantRegions: false,
      longPaths: false,
      circularWaves: true,
      regionSync: true,
      distributedExploration: false,
      sharpSignals: false,
      fastSync: true,
      structuredGeometry: false,
      rhythmicPulse: true,
      localBursts: false,
      preferDeep: false,
      transitionMs: 580,
    },
  };

  function normalizeState(name) {
    if (!name || typeof name !== "string") {
      return "idle";
    }
    var key = name.trim().toLowerCase().replace(/[\s-]+/g, "_");
    var mapped = STATE_ALIASES[key];
    if (mapped && SIGNATURES[mapped]) {
      return mapped;
    }
    if (SIGNATURES[key]) {
      return key;
    }
    return "idle";
  }

  function getSignature(stateId) {
    return SIGNATURES[stateId] || SIGNATURES.idle;
  }

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  function blendSignatures(fromId, toId, blend) {
    var from = getSignature(fromId);
    var to = getSignature(toId);
    var t = Math.max(0, Math.min(1, blend));
    var out = {};

    for (var key in to) {
      var a = from[key];
      var b = to[key];
      if (typeof b === "number") {
        out[key] = lerp(typeof a === "number" ? a : 0, b, t);
      } else if (typeof b === "boolean") {
        out[key] = t >= 0.55 ? b : !!a;
      } else {
        out[key] = t >= 0.65 ? b : a;
      }
    }

    return out;
  }

  function getCssClass(stateId) {
    return CSS_CLASS_MAP[stateId] || CSS_CLASS_MAP.idle;
  }

  function getAllCssClasses() {
    var list = [];
    for (var i = 0; i < STATE_IDS.length; i++) {
      list.push(CSS_CLASS_MAP[STATE_IDS[i]]);
    }
    return list;
  }

  function CognitiveOverlay() {
    this.fragments = [];
    this.geometry = [];
    this.rings = [];
    this._spawnAcc = 0;
    this._ringPhase = 0;
    this._voicePhase = 0;
  }

  CognitiveOverlay.prototype.update = function (deltaMs, signature, camera, width, height) {
    if (!signature) {
      return;
    }

    var dt = deltaMs / 16.67;
    this._ringPhase += 0.018 * dt;
    this._voicePhase += signature.rhythmicPulse ? 0.065 * dt : 0.012 * dt;
    this._spawnAcc += deltaMs;

    this._fadeCollection(this.fragments, 0.014 * dt);
    this._fadeCollection(this.geometry, 0.018 * dt);
    this._fadeCollection(this.rings, 0.016 * dt);

    if (signature.memoryFragments && this._spawnAcc > 1400) {
      this._spawnAcc = 0;
      this._spawnFragment(width, height);
      if (signature.neuralEchoes && Math.random() < 0.45) {
        this._spawnFragment(width, height, true);
      }
    }

    if (signature.structuredGeometry && this.geometry.length < 5 && Math.random() < 0.08 * dt) {
      this._spawnTradingGeometry(width, height);
    }

    if ((signature.circularWaves || signature.regionSync) && this.rings.length < 3) {
      if (Math.random() < 0.04 * dt) {
        this._spawnPlanningRing(width, height, signature.rhythmicPulse);
      }
    }

    if (signature.distributedExploration && Math.random() < 0.03 * dt) {
      this._spawnExplorationSpark(width, height);
    }

    for (var i = 0; i < this.fragments.length; i++) {
      var f = this.fragments[i];
      f.x += f.vx * dt;
      f.y += f.vy * dt;
      f.rot += f.vr * dt;
    }
  };

  CognitiveOverlay.prototype._fadeCollection = function (list, decay) {
    var remaining = [];
    for (var i = 0; i < list.length; i++) {
      list[i].alpha -= decay;
      if (list[i].alpha > 0.02) {
        remaining.push(list[i]);
      }
    }
    list.length = 0;
    Array.prototype.push.apply(list, remaining);
  };

  CognitiveOverlay.prototype._spawnFragment = function (width, height, echo) {
    this.fragments.push({
      x: width * (0.2 + Math.random() * 0.6),
      y: height * (0.18 + Math.random() * 0.55),
      w: 6 + Math.random() * 14,
      h: 3 + Math.random() * 8,
      rot: Math.random() * Math.PI,
      vx: (Math.random() - 0.5) * 0.12,
      vy: -0.04 - Math.random() * 0.08,
      vr: (Math.random() - 0.5) * 0.004,
      alpha: echo ? 0.22 : 0.34,
      echo: !!echo,
    });
  };

  CognitiveOverlay.prototype._spawnTradingGeometry = function (width, height) {
    var cx = width * (0.35 + Math.random() * 0.3);
    var cy = height * (0.32 + Math.random() * 0.28);
    var size = 28 + Math.random() * 42;
    var angle = Math.random() * Math.PI;

    this.geometry.push({
      cx: cx,
      cy: cy,
      size: size,
      angle: angle,
      alpha: 0.38,
      pulse: Math.random() * Math.PI * 2,
    });
  };

  CognitiveOverlay.prototype._spawnPlanningRing = function (width, height, rhythmic) {
    this.rings.push({
      cx: width * (0.38 + Math.random() * 0.24),
      cy: height * (0.34 + Math.random() * 0.22),
      radius: 18 + Math.random() * 36,
      alpha: rhythmic ? 0.42 : 0.3,
      speed: rhythmic ? 0.85 : 0.55,
      rhythmic: !!rhythmic,
    });
  };

  CognitiveOverlay.prototype._spawnExplorationSpark = function (width, height) {
    this.fragments.push({
      x: width * Math.random(),
      y: height * Math.random(),
      w: 2 + Math.random() * 4,
      h: 2 + Math.random() * 4,
      rot: 0,
      vx: (Math.random() - 0.5) * 0.35,
      vy: (Math.random() - 0.5) * 0.28,
      vr: 0,
      alpha: 0.2,
      echo: false,
      spark: true,
    });
  };

  CognitiveOverlay.prototype.draw = function (ctx, width, height, signature) {
    if (!signature) {
      return;
    }

    var colors = TitanNeural.CONFIG && TitanNeural.CONFIG.colors;
    var redGlow = colors ? colors.redGlow : "rgba(185, 28, 28, ";
    var whiteDim = colors ? colors.whiteDim : "rgba(245, 245, 245, ";

    for (var i = 0; i < this.fragments.length; i++) {
      var f = this.fragments[i];
      ctx.save();
      ctx.translate(f.x, f.y);
      ctx.rotate(f.rot);
      ctx.fillStyle = (f.echo ? whiteDim : redGlow) + f.alpha + ")";
      if (f.spark) {
        ctx.beginPath();
        ctx.arc(0, 0, f.w, 0, Math.PI * 2);
        ctx.fill();
      } else {
        ctx.fillRect(-f.w * 0.5, -f.h * 0.5, f.w, f.h);
      }
      ctx.restore();
    }

    for (var g = 0; g < this.geometry.length; g++) {
      var geo = this.geometry[g];
      geo.pulse += 0.04;
      var pulse = 0.65 + Math.sin(geo.pulse) * 0.35;
      var a = geo.alpha * pulse;

      ctx.save();
      ctx.translate(geo.cx, geo.cy);
      ctx.rotate(geo.angle);
      ctx.strokeStyle = redGlow + a + ")";
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      ctx.moveTo(-geo.size * 0.5, 0);
      ctx.lineTo(geo.size * 0.5, 0);
      ctx.moveTo(0, -geo.size * 0.35);
      ctx.lineTo(0, geo.size * 0.35);
      ctx.stroke();
      ctx.restore();
    }

    for (var r = 0; r < this.rings.length; r++) {
      var ring = this.rings[r];
      ring.radius += ring.speed;
      var ringAlpha = ring.alpha * (1 - ring.radius / (width * 0.42));
      if (ringAlpha <= 0.02) {
        continue;
      }

      var voiceMod = ring.rhythmic ? 0.75 + Math.sin(this._voicePhase * 3) * 0.25 : 1;
      ctx.beginPath();
      ctx.arc(ring.cx, ring.cy, ring.radius, 0, Math.PI * 2);
      ctx.strokeStyle = redGlow + ringAlpha * voiceMod + ")";
      ctx.lineWidth = ring.rhythmic ? 1.1 : 0.7;
      ctx.stroke();
    }
  };

  CognitiveOverlay.prototype.clear = function () {
    this.fragments.length = 0;
    this.geometry.length = 0;
    this.rings.length = 0;
  };

  TitanNeural.Cognitive = {
    STATE_IDS: STATE_IDS,
    STATE_ALIASES: STATE_ALIASES,
    SIGNATURES: SIGNATURES,
    CSS_CLASS_MAP: CSS_CLASS_MAP,
    normalizeState: normalizeState,
    getSignature: getSignature,
    blendSignatures: blendSignatures,
    getCssClass: getCssClass,
    getAllCssClasses: getAllCssClasses,
  };

  TitanNeural.CognitiveOverlay = CognitiveOverlay;
})(window);
