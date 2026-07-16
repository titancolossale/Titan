/** Titan Frontend V2 — Visual quality settings wiring (Phase 11.P1). */

import { loadStoredQualityMode, persistQualityMode } from "../neural/quality-controller.js";

/**
 * Wire Visual Quality controls inside the existing Settings overlay.
 * @param {{
 *   store: import("./state-store.js").StateStore,
 *   neuralStage: import("../neural/stage.js").NeuralStage | null,
 * }} deps
 */
export function wireVisualQualitySettings(deps) {
  const { store, neuralStage } = deps;
  const select = /** @type {HTMLSelectElement | null} */ (
    document.getElementById("tdl-v2-visual-quality")
  );
  const reduceMotion = /** @type {HTMLInputElement | null} */ (
    document.getElementById("tdl-v2-reduce-motion-pref")
  );
  const showFps = /** @type {HTMLInputElement | null} */ (
    document.getElementById("tdl-v2-show-fps")
  );
  const fpsWrap = document.getElementById("tdl-v2-fps-toggle-wrap");

  const mode = loadStoredQualityMode();
  if (select) {
    select.value = mode;
  }
  store.setState({ visualQuality: mode });
  neuralStage?.setQualityMode?.(mode);

  if (reduceMotion) {
    reduceMotion.checked = Boolean(store.getState().reducedMotion);
    reduceMotion.addEventListener("change", () => {
      const on = reduceMotion.checked;
      document.documentElement.classList.toggle("tdl-v2--reduced-motion", on);
      store.setState({ reducedMotion: on });
      // Force a light geometry refresh so budgets pick up reduced-motion.
      neuralStage?.setQualityMode?.(store.getState().visualQuality);
    });
  }

  const debugEnabled =
    Boolean(store.getState().devMetadataOpen) ||
    new URLSearchParams(window.location.search).has("debug") ||
    localStorage.getItem("titan_debug_perf") === "1";
  if (fpsWrap) {
    fpsWrap.hidden = !debugEnabled;
  }
  if (showFps) {
    showFps.checked = Boolean(store.getState().showFpsOverlay);
    showFps.addEventListener("change", () => {
      store.setState({ showFpsOverlay: showFps.checked });
      _syncFpsOverlay(store, neuralStage);
    });
  }

  select?.addEventListener("change", () => {
    const next = /** @type {"performance"|"balanced"|"cinematic"} */ (select.value);
    persistQualityMode(next);
    store.setState({ visualQuality: next });
    neuralStage?.setQualityMode?.(next);
  });

  if (debugEnabled || store.getState().showFpsOverlay) {
    _syncFpsOverlay(store, neuralStage);
  }

  return () => {
    if (_fpsTimer) {
      clearInterval(_fpsTimer);
      _fpsTimer = null;
    }
  };
}

/** @type {ReturnType<typeof setInterval> | null} */
let _fpsTimer = null;

/**
 * @param {import("./state-store.js").StateStore} store
 * @param {import("../neural/stage.js").NeuralStage | null} neuralStage
 */
function _syncFpsOverlay(store, neuralStage) {
  let el = document.getElementById("tdl-v2-fps-overlay");
  const show = store.getState().showFpsOverlay;
  if (!show) {
    el?.remove();
    if (_fpsTimer) {
      clearInterval(_fpsTimer);
      _fpsTimer = null;
    }
    return;
  }
  if (!el) {
    el = document.createElement("div");
    el.id = "tdl-v2-fps-overlay";
    el.className = "tdl-v2-fps-overlay";
    el.setAttribute("aria-hidden", "true");
    document.body.appendChild(el);
  }
  if (_fpsTimer) clearInterval(_fpsTimer);
  _fpsTimer = setInterval(() => {
    const snap = neuralStage?.getPerformanceSnapshot?.();
    if (!snap || !el) return;
    store.setState({
      clientFps: snap.rollingFps,
      clientFrameMs: snap.frameMs,
    });
    el.textContent =
      `FPS ${snap.rollingFps} (${snap.fps})\n` +
      `${snap.frameMs}ms · ${snap.qualityMode}/${snap.qualityTier}\n` +
      `DPR ${snap.dpr} · ${snap.canvasWidth}×${snap.canvasHeight}\n` +
      `skip ${snap.skippedFrames} · drop ${snap.droppedDecorative}` +
      (snap.paused ? "\nPAUSED" : "");
  }, 400);
}
