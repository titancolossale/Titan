/** Titan Neural Renderer V3 — Configuration (Neural Architecture Reconstruction). */

export const NEURAL_CONFIG = {
  colors: {
    redCore: "rgba(185, 28, 28, ",
    redGlow: "rgba(239, 68, 68, ",
    redHot: "rgba(255, 90, 70, ",
    redDeep: "rgba(127, 29, 29, ",
    redCrimson: "rgba(220, 38, 38, ",
    redEmber: "rgba(153, 27, 27, ",
    whiteDim: "rgba(255, 210, 200, ",
    whiteCore: "rgba(255, 255, 255, ",
    vignette: "rgba(2, 2, 2, ",
    hazeRed: "rgba(72, 8, 8, ",
    dust: "rgba(255, 200, 190, ",
    signalMemory: "rgba(255, 180, 160, ",
    signalPlanning: "rgba(248, 113, 113, ",
    signalTrading: "rgba(239, 68, 68, ",
    signalBrowser: "rgba(251, 146, 146, ",
    signalVoice: "rgba(254, 202, 202, ",
    signalTool: "rgba(220, 38, 38, ",
  },

  // Large-scale depth: very far → far → mid → near → foreground.
  // Strong brightness / opacity / blur / speed / scale separation.
  layers: [
    { id: "abyss", depth: 0, z: 0.02, baseOpacity: 0.04, driftMult: 0.015, radiusMin: 0.03, radiusMax: 0.12, weight: 0.1, parallax: 0.02, edgeOpacity: 0.04, fogDim: 0.03, blur: 10.5 },
    { id: "deep", depth: 1, z: 0.12, baseOpacity: 0.08, driftMult: 0.04, radiusMin: 0.06, radiusMax: 0.22, weight: 0.14, parallax: 0.1, edgeOpacity: 0.08, fogDim: 0.08, blur: 7.2 },
    { id: "background", depth: 2, z: 0.32, baseOpacity: 0.16, driftMult: 0.11, radiusMin: 0.14, radiusMax: 0.5, weight: 0.2, parallax: 0.28, edgeOpacity: 0.2, fogDim: 0.24, blur: 3.8 },
    { id: "midground", depth: 3, z: 0.55, baseOpacity: 0.48, driftMult: 0.32, radiusMin: 0.36, radiusMax: 1.0, weight: 0.24, parallax: 0.55, edgeOpacity: 0.58, fogDim: 0.6, blur: 1.15 },
    { id: "near", depth: 4, z: 0.78, baseOpacity: 0.78, driftMult: 0.82, radiusMin: 0.62, radiusMax: 1.75, weight: 0.18, parallax: 0.92, edgeOpacity: 0.92, fogDim: 0.92, blur: 0.08 },
    { id: "foreground", depth: 5, z: 1.0, baseOpacity: 0.94, driftMult: 1.18, radiusMin: 1.05, radiusMax: 2.7, weight: 0.14, parallax: 1.12, edgeOpacity: 1.0, fogDim: 1.12, blur: 0 },
  ],

  world: {
    padding: 0.38,
    // Local synapses inside colonies; major highways are dedicated strands.
    connectionMaxDistRatio: 0.032,
    connectionProbability: 0.9,
    maxConnectionsPerNode: 7,
    newConnectionInterval: 1200,
    newConnectionChance: 0.88,
    organicCurveStrength: 0.52,
    dendriteBranchChance: 0.55,
  },

  /**
   * Intentional neural civilization map — named colonies + highway topology.
   * Composition owns density rhythm; micro detail never fakes structure.
   */
  architecture: {
    colonies: [
      // Core stays largest — peripheral hubs sit farther out as islands.
      { id: "core", x: 0.5, y: 0.48, r: 0.16, mass: 1.95, stretchX: 1.45, stretchY: 0.7, density: 1.7, shape: "nebula", localBranch: 1.45 },
      { id: "memory", x: 0.16, y: 0.16, r: 0.095, mass: 1.15, stretchX: 1.22, stretchY: 0.9, density: 1.3, shape: "cluster", localBranch: 1.2 },
      { id: "planning", x: 0.5, y: 0.9, r: 0.1, mass: 1.1, stretchX: 1.65, stretchY: 0.48, density: 1.12, shape: "ridge", localBranch: 1.0 },
      { id: "browser", x: 0.88, y: 0.15, r: 0.088, mass: 1.05, stretchX: 0.8, stretchY: 1.4, density: 1.28, shape: "plume", localBranch: 1.3 },
      { id: "communication", x: 0.07, y: 0.48, r: 0.095, mass: 1.08, stretchX: 0.65, stretchY: 1.5, density: 1.18, shape: "arc", localBranch: 1.12 },
      { id: "obsidian", x: 0.11, y: 0.76, r: 0.082, mass: 1.0, stretchX: 1.1, stretchY: 1.15, density: 1.35, shape: "knot", localBranch: 1.4 },
      { id: "tools", x: 0.93, y: 0.48, r: 0.08, mass: 0.92, stretchX: 1.05, stretchY: 1.08, density: 1.05, shape: "cluster", localBranch: 0.95, secondary: true },
      { id: "trading", x: 0.34, y: 0.86, r: 0.065, mass: 0.75, stretchX: 1.4, stretchY: 0.55, density: 0.92, shape: "plume", localBranch: 0.85, secondary: true },
      { id: "calendar", x: 0.88, y: 0.8, r: 0.062, mass: 0.72, stretchX: 0.95, stretchY: 0.85, density: 0.88, shape: "cluster", localBranch: 0.8, secondary: true },
    ],
    voids: {
      count: 9,
      radiusMinRatio: 0.14,
      radiusMaxRatio: 0.3,
    },
    highways: {
      coreLinksPerColony: 1,
      interColonyLinks: 8,
      splitCount: 28,
      mergeCount: 18,
      forkChance: 0.68,
    },
  },

  // Architecture-first tissue — island colonies, dark voids, artery highways.
  // Cut mid-field fog so composition reads as civilization, not particle soup.
  tissue: {
    coreStrandCount: 1280,
    corePocketCount: 210,
    fieldPocketCount: 180,
    galaxyCount: 9,
    voidCount: 9,
    // Sparse atmospheric fill — composition lives in colonies + highways.
    veryFarStrandCount: 180,
    farStrandCount: 220,
    midStrandCount: 260,
    nearStrandCount: 180,
    foregroundStrandCount: 48,
    galaxySynapseCount: 560,
    colonyLocalCount: 760,
    majorPathwayCount: 22,
    highwaySplitCount: 28,
    highwayMergeCount: 18,
    secondaryBranchCount: 70,
    tertiaryBranchCount: 120,
    microBridgeCount: 120,
    dustAxonCount: 140,
    voidFringeCount: 56,
    // Extra microscopic tissue packed behind TITAN CORE typography.
    labelZoneStrandCount: 320,
    // Sparse near-camera filaments (canvas depth; DOM overlay owns text-crossers).
    nearForegroundCount: 64,
    // Short curved local synapses + micro colonies around Core.
    coreColonyCount: 22,
    coreColonySynapseCount: 200,
  },

  nodes: {
    minCount: 5200,
    maxCount: 12000,
    areaDivisor: 88,
    densityDefault: 6.4,
    pulseSpeedMin: 0.0028,
    pulseSpeedMax: 0.022,
    driftSpeedMin: 0.004,
    driftSpeedMax: 0.028,
    breatheAmplitude: 0.3,
    breatheSpeed: 0.00026,
    hubRatio: 0.018,
    coreSatellites: 260,
    // Colony gravity dominates — avoid uniform particle fog.
    coreClusterChance: 0.38,
    regionClusterChance: 0.48,
    microClusterChance: 0.26,
    clusterPower: 1.85,
    sizeVariance: 2.2,
    microSeedCount: 120,
    localPocketCount: 22,
    galaxyCount: 9,
    voidCount: 9,
    sparseFieldChance: 0.03,
  },

  core: {
    xRatio: 0.5,
    // Align canvas gravity with satellite-core (optical center of neural stage)
    yRatio: 0.5,
    hubRadius: 1.7,
    satelliteRadiusMin: 0.28,
    satelliteRadiusMax: 1.0,
    // Wider soft density scale — gradual ramp, no object silhouette.
    clusterRadiusRatio: 0.36,
    // Mild asymmetry — intentional, not a left-weighted fog bank.
    asymmetry: { x: -0.035, y: 0.012 },
    branchCount: 120,
    // Slow conscious breath — almost imperceptible.
    breatheSpeed: 0.00022,
    pulseAmplitude: 0.055,
    // Soft local aura scale (elliptic, never a hard orb).
    auraMaxScreenPx: 280,
    // Final balance: nucleus ~30% smaller; plasma kept via renderer scale.
    whiteCenterRadius: 0.8,
    energyRingCount: 0,
    // Plasma + atmosphere stack — Core is the brightest object.
    outerGlowMult: 0.7,
    // Local contrast: mid-ring darkens so nucleus locks the eye.
    fieldDarkenStrength: 0.3,
    filamentCount: 1280,
    microNeuronCount: 3200,
    // Local energy packets (same budget — orbiters + filament riders).
    energyPacketCount: 28,
    // Fraction of packets that orbit tight around the nucleus.
    orbitPacketRatio: 0.48,
    // Band fade multipliers for volumetric depth separation.
    bandFade: {
      veryFar: 0.1,
      far: 0.22,
      mid: 0.58,
      bridge: 0.72,
      near: 1.2,
      foreground: 1.35,
      front: 1.35,
    },
  },

  camera: {
    driftSpeedX: 0.000012,
    driftSpeedY: 0.000009,
    amplitudeXRatio: 0.026,
    amplitudeYRatio: 0.02,
    easing: 0.00007,
    breatheZoomAmplitude: 0.008,
    breatheZoomSpeed: 0.00022,
    thinkingFocusMult: 0.42,
    thinkingZoomIn: 0.006,
    idleDriftBoost: 1.05,
    recallDiveScale: 0.035,
    recallDiveDecay: 0.0028,
    pointerParallaxRatio: 0.024,
    pointerEase: 0.004,
  },

  signals: {
    speedMin: 0.08,
    speedMax: 0.4,
    maxActiveIdle: 68,
    maxActiveThinking: 130,
    spawnIntervalIdle: 340,
    spawnIntervalThinking: 55,
    microPulseInterval: 380,
    nodeGlowDecay: 0.01,
    edgeGlowDecay: 0.011,
    waveRadius: 64,
    waveSpeed: 0.055,
    waveDecay: 0.01,
    particleSize: 1.3,
    particleTrail: 0.65,
    splitChance: 0.24,
    collideChance: 0.025,
    trailSegments: 6,
    // Highways of thought pull toward the Core — gravitational, not random.
    convergeToCoreChance: 0.34,
    accelJitter: 0.1,
  },

  thinking: {
    activityBoost: 2.2,
    driftBoost: 1.25,
    decayRate: 0.0028,
    nearbyRadiusRatio: 0.24,
    nearbyGlow: 0.78,
    pathSpreadChance: 0.68,
  },

  execution: {
    regionRadiusRatio: 0.14,
    regionGlow: 0.55,
    impulseLocality: 0.78,
  },

  depth: {
    ghostCount: 96,
    recallBoost: 0.48,
    fogLayers: 5,
    parallaxBands: [
      { id: "void", parallax: 0.08, nodeCount: 0, speedMult: 0.28, opacityMin: 0, opacityMax: 0, radiusMin: 0, radiusMax: 0 },
      { id: "far", parallax: 0.18, nodeCount: 0, speedMult: 0.38, opacityMin: 0, opacityMax: 0, radiusMin: 0, radiusMax: 0 },
      { id: "distant", parallax: 0.32, nodeCount: 0, speedMult: 0.48, opacityMin: 0, opacityMax: 0, radiusMin: 0, radiusMax: 0 },
      { id: "horizon", parallax: 0.48, nodeCount: 0, speedMult: 0.58, opacityMin: 0, opacityMax: 0, radiusMin: 0, radiusMax: 0 },
    ],
    streamRespawnMargin: 0.14,
  },

  infiniteSpace: {
    enabled: true,
    wrapMargin: 40,
    worldExpansion: 0.72,
    edgeStreamRate: 0.0035,
  },

  parallax: {
    nearBrightnessBoost: 1.35,
    farDimFactor: 0.14,
    movementSpread: 1.55,
  },

  vitality: {
    idleFloor: 0.22,
    idleCeiling: 0.48,
    oscillationSpeed: 0.00034,
  },

    atmosphere: {
    hazeStrength: 0.028,
    ambientGlowStrength: 0.034,
    dustCount: 180,
    dustSpeedMin: 0.0014,
    dustSpeedMax: 0.008,
    dustOpacity: 0.09,
    // Soft Core bloom — restrained so nearby neural tissue stays readable.
    bloomStrength: 0.032,
    vignetteStrength: 0.96,
    // No oversized straight light beams across the top (canonical reference).
    lightShaftStrength: 0,
    lensDiffusion: 0.009,
    fogRedStrength: 0.02,
    // Soft foreground bokeh sparks — living intelligence depth cue.
    foregroundBokehCount: 28,
  },

  render: {
    // Hard ceiling — QualityController caps further per mode (Balanced ≤ 1.25).
    maxDpr: 1.75,
    edgeFadeStrength: 0.72,
    thinkingBrightness: 1.24,
    hazeStrength: 0.028,
    panelOcclusionStrength: 0.014,
    depthFogStrength: 0.46,
    signalParticleGlow: 0.7,
    voidColor: "#000000",
    vignetteStrength: 0.95,
    coreDrawStrength: 1.55,
    intersectionBoost: 0.72,
    highwaySheath: 0.28,
    // Pathway brightness peels toward Core (gravitational attraction).
    highwayCoreGravity: 0.72,
  },

  performance: {
    targetFps: 60,
    hiddenTabPause: true,
    // Geometry density is mode-driven via QualityController (no per-frame rebuild).
    adaptiveNodeCount: false,
    frameBudgetMs: 16.8,
    sampleWindow: 45,
    densityFloor: 0.5,
    densityRecoverMs: 6000,
    // Cinematic ceilings — Balanced/Performance scale these at runtime.
    maxEdgesDrawn: 26000,
    maxTissueDrawn: 3400,
    defaultQualityMode: "auto",
  },

  boot: {
    voidHoldMs: 280,
    sparseFadeMs: 520,
    connectionRampMs: 740,
    fullDensityMs: 960,
    awakeMs: 1150,
  },

  activityHooks: [
    "brain_activity",
    "tool_usage",
    "memory_retrieval",
    "reasoning",
    "voice",
    "speaking",
    "browser_research",
  ],
};
