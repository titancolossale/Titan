/**
 * Titan Presence States — emotional state definitions (Phase 17.6)
 *
 * Four living states: idle, listening, thinking, working.
 * Profiles drive neural intensity, ambient glow, and natural status copy.
 */
(function (global) {
  "use strict";

  var STATES = {
    IDLE: "idle",
    LISTENING: "listening",
    THINKING: "thinking",
    SPEAKING: "speaking",
    WORKING: "working",
  };

  /** Natural status copy — never "Loading…" */
  var STATUS_LABELS = {
    idle: "Présent — en attente",
    listening: "À l'écoute",
    thinking: "Réflexion en cours",
    speaking: "Titan parle",
    working: "En action",
    streaming: "Formulation de la réponse",
    planning: "Planification",
    interrupted: "Pause",
  };

  /** Tool-specific working status and neural hook patterns */
  var TOOL_PROFILES = {
    browser: {
      status: "Exploration web",
      hook: "browser_research",
      cognitiveState: "exploration",
      pulseIntervalMs: 1200,
      waveBurst: 3,
      speedMult: 1.18,
      waveStyle: "distributed",
    },
    calendar: {
      status: "Consultation de l'agenda",
      hook: "tool_usage",
      pulseIntervalMs: 1800,
      waveBurst: 1,
      speedMult: 0.9,
      waveStyle: "circular",
    },
    trading: {
      status: "Analyse des marchés",
      hook: "tool_usage",
      pulseIntervalMs: 1100,
      waveBurst: 3,
      speedMult: 1.35,
      waveStyle: "sharp",
    },
    memory: {
      status: "Recherche en mémoire",
      hook: "memory_retrieval",
      pulseIntervalMs: 1600,
      waveBurst: 2,
      speedMult: 1.0,
      waveStyle: "central",
    },
    email: {
      status: "Lecture des e-mails",
      hook: "tool_usage",
      pulseIntervalMs: 2000,
      waveBurst: 1,
      speedMult: 0.85,
      waveStyle: "distributed",
    },
    obsidian: {
      status: "Consultation d'Obsidian",
      hook: "memory_retrieval",
      pulseIntervalMs: 1700,
      waveBurst: 2,
      speedMult: 0.95,
      waveStyle: "geometric",
    },
    planning: {
      status: "Planification",
      hook: "reasoning",
      pulseIntervalMs: 1500,
      waveBurst: 2,
      speedMult: 1.05,
    },
    voice: {
      status: "Écoute vocale",
      hook: "voice",
      pulseIntervalMs: 900,
      waveBurst: 2,
      speedMult: 1.2,
    },
    speaking: {
      status: "Titan parle",
      hook: "speaking",
      pulseIntervalMs: 520,
      waveBurst: 2,
      speedMult: 1.1,
      waveStyle: "circular",
    },
    default: {
      status: "En action",
      hook: "tool_usage",
      pulseIntervalMs: 1600,
      waveBurst: 1,
      speedMult: 1.0,
      waveStyle: "default",
    },
  };

  /**
   * Visual + neural targets per presence state (0–1 scales).
   * Transitions lerp between source and target profiles in PresenceEngine.
   */
  var STATE_PROFILES = {
    idle: {
      neuralMode: "idle",
      activityTarget: 0.08,
      thinkingTarget: 0,
      glowLevel: 0.44,
      breatheScale: 1.02,
      breatheSpeed: 0.92,
      ambientMotion: 0.42,
      signalDensity: 0.32,
      brightness: 1,
    },
    listening: {
      neuralMode: "idle",
      activityTarget: 0.22,
      thinkingTarget: 0.08,
      glowLevel: 0.52,
      breatheScale: 1.06,
      breatheSpeed: 1.08,
      ambientMotion: 0.48,
      signalDensity: 0.38,
      brightness: 1.03,
    },
    thinking: {
      neuralMode: "thinking",
      activityTarget: 0.88,
      thinkingTarget: 0.92,
      glowLevel: 0.78,
      breatheScale: 1.14,
      breatheSpeed: 1.22,
      ambientMotion: 0.72,
      signalDensity: 0.95,
      brightness: 1.08,
    },
    speaking: {
      neuralMode: "thinking",
      activityTarget: 0.76,
      thinkingTarget: 0.58,
      glowLevel: 0.74,
      breatheScale: 1.1,
      breatheSpeed: 1.18,
      ambientMotion: 0.66,
      signalDensity: 0.88,
      brightness: 1.07,
    },
    working: {
      neuralMode: "thinking",
      activityTarget: 0.72,
      thinkingTarget: 0.65,
      glowLevel: 0.68,
      breatheScale: 1.1,
      breatheSpeed: 1.15,
      ambientMotion: 0.62,
      signalDensity: 0.82,
      brightness: 1.06,
    },
  };

  /** Transition durations (ms) — no instant switching */
  var TRANSITION_MS = {
    idle: 900,
    listening: 500,
    thinking: 700,
    speaking: 600,
    working: 650,
    default: 750,
  };

  /** Priority when multiple signals compete (higher wins) */
  var STATE_PRIORITY = {
    idle: 0,
    listening: 4,
    thinking: 3,
    speaking: 2,
    working: 2,
  };

  function getToolProfile(toolName) {
    if (!toolName) {
      return TOOL_PROFILES.default;
    }
    return TOOL_PROFILES[toolName] || TOOL_PROFILES.default;
  }

  function getStatusForState(state, context) {
    var ctx = context || {};
    if (state === STATES.WORKING && ctx.tool) {
      return getToolProfile(ctx.tool).status;
    }
    if (state === STATES.THINKING && ctx.streamPhase === "streaming") {
      return STATUS_LABELS.streaming;
    }
    if (state === STATES.SPEAKING) {
      return STATUS_LABELS.speaking;
    }
    if (ctx.customStatus) {
      return ctx.customStatus;
    }
    return STATUS_LABELS[state] || STATUS_LABELS.idle;
  }

  function getTransitionMs(fromState, toState) {
    var to = TRANSITION_MS[toState] || TRANSITION_MS.default;
    var from = TRANSITION_MS[fromState] || TRANSITION_MS.default;
    return Math.max(to, from) * 0.85;
  }

  global.TitanPresenceStates = {
    STATES: STATES,
    STATUS_LABELS: STATUS_LABELS,
    TOOL_PROFILES: TOOL_PROFILES,
    STATE_PROFILES: STATE_PROFILES,
    TRANSITION_MS: TRANSITION_MS,
    STATE_PRIORITY: STATE_PRIORITY,
    getToolProfile: getToolProfile,
    getStatusForState: getStatusForState,
    getTransitionMs: getTransitionMs,
  };
})(window);
