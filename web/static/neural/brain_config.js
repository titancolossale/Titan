/**
 * Titan Neural Brain Engine — Configuration
 * Phase 17.4 · Phase 18.0 · Phase 19.1 · Phase 19.2 — infinite neural space
 */
(function (global) {
  "use strict";

  var TitanNeural = (global.TitanNeural = global.TitanNeural || {});

  TitanNeural.CONFIG = {
    colors: {
      redCore: "rgba(204, 0, 0, ",
      redGlow: "rgba(255, 26, 26, ",
      whiteDim: "rgba(255, 255, 255, ",
      vignette: "rgba(0, 0, 0, ",
    },

    layers: [
      {
        id: "abyss",
        depth: 0,
        baseOpacity: 0.1,
        driftMult: 0.18,
        radiusMin: 0.35,
        radiusMax: 0.72,
        weight: 0.22,
        parallax: 0.22,
        edgeOpacity: 0.28,
        fogDim: 0.28,
      },
      {
        id: "deep",
        depth: 1,
        baseOpacity: 0.16,
        driftMult: 0.28,
        radiusMin: 0.5,
        radiusMax: 1.0,
        weight: 0.2,
        parallax: 0.38,
        edgeOpacity: 0.36,
        fogDim: 0.4,
      },
      {
        id: "background",
        depth: 2,
        baseOpacity: 0.22,
        driftMult: 0.38,
        radiusMin: 0.7,
        radiusMax: 1.3,
        weight: 0.28,
        parallax: 0.55,
        edgeOpacity: 0.48,
        fogDim: 0.52,
      },
      {
        id: "midground",
        depth: 3,
        baseOpacity: 0.42,
        driftMult: 0.68,
        radiusMin: 1.0,
        radiusMax: 2.0,
        weight: 0.24,
        parallax: 0.78,
        edgeOpacity: 0.78,
        fogDim: 0.72,
      },
      {
        id: "foreground",
        depth: 4,
        baseOpacity: 0.68,
        driftMult: 1.0,
        radiusMin: 1.3,
        radiusMax: 2.6,
        weight: 0.16,
        parallax: 1.0,
        edgeOpacity: 1.0,
        fogDim: 0.88,
      },
    ],

    world: {
      padding: 0.38,
      connectionMaxDistRatio: 0.38,
      connectionProbability: 0.62,
      maxConnectionsPerNode: 11,
      newConnectionInterval: 3200,
      newConnectionChance: 0.72,
    },

    nodes: {
      minCount: 180,
      maxCount: 380,
      areaDivisor: 6200,
      densityDefault: 1.72,
      pulseSpeedMin: 0.006,
      pulseSpeedMax: 0.016,
      driftSpeedMin: 0.022,
      driftSpeedMax: 0.085,
      breatheAmplitude: 0.24,
      breatheSpeed: 0.00042,
    },

    camera: {
      driftSpeedX: 0.00006,
      driftSpeedY: 0.00005,
      amplitudeXRatio: 0.048,
      amplitudeYRatio: 0.038,
      easing: 0.00012,
      breatheZoomAmplitude: 0.014,
      breatheZoomSpeed: 0.00035,
      thinkingFocusMult: 0.58,
      thinkingZoomIn: 0.016,
      idleDriftBoost: 1.12,
      recallDiveScale: 0.055,
      recallDiveDecay: 0.0035,
    },

    signals: {
      speedMin: 0.28,
      speedMax: 0.62,
      maxActiveIdle: 14,
      maxActiveThinking: 32,
      spawnIntervalIdle: 1600,
      spawnIntervalThinking: 140,
      microPulseInterval: 850,
      nodeGlowDecay: 0.014,
      edgeGlowDecay: 0.018,
      waveRadius: 108,
      waveSpeed: 0.065,
      waveDecay: 0.009,
      particleSize: 1.8,
      particleTrail: 0.42,
    },

    thinking: {
      activityBoost: 2.15,
      driftBoost: 1.48,
      decayRate: 0.0028,
      nearbyRadiusRatio: 0.26,
      nearbyGlow: 0.78,
      pathSpreadChance: 0.68,
    },

    depth: {
      ghostCount: 36,
      voidLineCount: 18,
      recallBoost: 0.45,
      farLayerOpacity: 0.1,
      parallaxBands: [
        { id: "void", parallax: 0.12, nodeCount: 10, speedMult: 0.35, opacityMin: 0.03, opacityMax: 0.08, radiusMin: 0.3, radiusMax: 0.65 },
        { id: "far", parallax: 0.28, nodeCount: 12, speedMult: 0.48, opacityMin: 0.05, opacityMax: 0.12, radiusMin: 0.4, radiusMax: 0.9 },
        { id: "distant", parallax: 0.45, nodeCount: 10, speedMult: 0.62, opacityMin: 0.06, opacityMax: 0.14, radiusMin: 0.5, radiusMax: 1.0 },
        { id: "horizon", parallax: 0.62, nodeCount: 8, speedMult: 0.78, opacityMin: 0.07, opacityMax: 0.16, radiusMin: 0.55, radiusMax: 1.1 },
      ],
      streamRespawnMargin: 0.18,
      voidLineFadeStrength: 0.88,
    },

    infiniteSpace: {
      enabled: true,
      wrapMargin: 28,
      worldExpansion: 0.55,
      edgeStreamRate: 0.0022,
    },

    parallax: {
      nearBrightnessBoost: 1.18,
      farDimFactor: 0.42,
      movementSpread: 1.35,
    },

    vitality: {
      idleFloor: 0.12,
      idleCeiling: 0.28,
      oscillationSpeed: 0.00055,
    },

    render: {
      maxDpr: 2,
      edgeFadeStrength: 0.48,
      ambientGlowStrength: 0.38,
      thinkingBrightness: 1.38,
      hazeStrength: 0.08,
      panelOcclusionStrength: 0.02,
      parallaxScale: 1,
      curveEdgesForeground: true,
      depthFogStrength: 0.08,
      signalParticleGlow: 0.62,
      centralCoreStrength: 1.65,
    },

    performance: {
      targetFps: 60,
      hiddenTabPause: true,
      adaptiveNodeCount: true,
      frameBudgetMs: 16.8,
      sampleWindow: 45,
      densityFloor: 0.55,
      densityRecoverMs: 8000,
    },

    activityHooks: [
      "brain_activity",
      "tool_usage",
      "memory_retrieval",
      "reasoning",
      "voice",
      "speaking",
    ],
  };

  TitanNeural.computeNodeCount = function (width, height, density) {
    var cfg = TitanNeural.CONFIG.nodes;
    var d = density || cfg.densityDefault;
    var count = Math.floor(((width * height) / cfg.areaDivisor) * d);
    return Math.max(cfg.minCount, Math.min(count, cfg.maxCount));
  };

  TitanNeural.rand = function (min, max) {
    return min + Math.random() * (max - min);
  };

  TitanNeural.randInt = function (min, max) {
    return Math.floor(TitanNeural.rand(min, max + 1));
  };

  if (global.TitanMotion && global.TitanMotion.syncNeuralColors) {
    global.TitanMotion.syncNeuralColors(TitanNeural.CONFIG);
  }
})(window);
