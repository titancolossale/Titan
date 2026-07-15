/** Titan Frontend V2 — Panel load stagger (Production Spec §1.12). */

import { PANEL_STAGGER } from "./tokens.js";

/**
 * Run cold-load stagger on workspace regions.
 * @param {import("./animation-engine.js").AnimationEngine} engine
 * @param {Record<string, HTMLElement | null>} regionElements
 */
export function runPanelStagger(engine, regionElements) {
  const cancels = [];

  for (const step of PANEL_STAGGER) {
    const element = regionElements[step.region];
    if (!element) {
      continue;
    }

    element.dataset.stagger = "pending";
    element.style.opacity = "0";

    const cancel = engine.schedule({
      id: `stagger-${step.region}`,
      delay: step.delay,
      duration: step.duration,
      easing: "enter",
      onUpdate: (progress) => {
        element.style.opacity = String(progress);
      },
      onComplete: () => {
        element.dataset.stagger = "visible";
        element.classList.add("tdl-v2-stagger-visible");
        element.style.opacity = "";
      },
    });

    cancels.push(cancel);
  }

  return () => {
    cancels.forEach((cancel) => cancel());
  };
}
