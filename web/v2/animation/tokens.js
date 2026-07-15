/** Titan Frontend V2 — Animation tokens (Animation Guide §2). */

export const DURATION = Object.freeze({
  instant: 100,
  fast: 200,
  normal: 350,
  slow: 600,
  breath: 5500,
  neural: 14000,
  thinking: 2400,
  presenceIdle: 6000,
});

export const EASING = Object.freeze({
  standard: "cubic-bezier(0.4, 0, 0.2, 1)",
  enter: "cubic-bezier(0, 0, 0.2, 1)",
  exit: "cubic-bezier(0.4, 0, 1, 1)",
  organic: "cubic-bezier(0.45, 0.05, 0.55, 0.95)",
});

/** Production Spec §1.12 — cold load panel stagger. */
export const PANEL_STAGGER = Object.freeze([
  { region: "sidebar", delay: 0, duration: DURATION.normal },
  { region: "main", delay: 200, duration: DURATION.normal },
  { region: "orchestrator", delay: 400, duration: DURATION.normal },
  { region: "dock", delay: 600, duration: DURATION.normal },
]);

/** Master Blueprint — screen switch cross-fade. */
export const SCREEN_TRANSITION = Object.freeze({
  duration: DURATION.normal,
  easing: EASING.enter,
});

/** Animation Guide §3.1 — presence state transition durations (ms). */
export const PRESENCE_TRANSITION_MS = Object.freeze({
  idle: 900,
  listening: 500,
  thinking: 700,
  speaking: 600,
  working: 650,
  streaming: 700,
  planning: 700,
  error: 900,
});
