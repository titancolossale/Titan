/** Titan Voice UI — extension registration (Phase 20.4 / 20.13 mount fix). */

import { mountEnrollmentPanel } from "./enrollment-ui.js";
import { VoiceController } from "./voice-controller.js";
import { VoiceSocket, voiceSocketSupported } from "./voice-socket.js";

/** Max wait for center panel DOM after route transition (ms). */
const VOICE_MOUNT_TIMEOUT_MS = 8000;
/** Poll interval while waiting for the voice panel host (ms). */
const VOICE_MOUNT_POLL_MS = 50;

/**
 * Register the Voice extension hook — wires mic + enrollment panel.
 * Phase 20.8: VoiceSocket is available for optional WS uplink (no UI redesign).
 * Phase 20.13: retry mount across async center-panel transitions; never leave
 * the Voice route stuck on "Chargement du module vocal…".
 * @param {import("../core/extension-registry.js").ExtensionRegistry} extensions
 */
export function registerVoiceExtension(extensions) {
  extensions.register("voice", (ctx) => {
    const { app, brain, store, shell } = ctx;

    /** @type {ReturnType<typeof setTimeout> | null} */
    let mountTimer = null;
    /** @type {number} */
    let mountGeneration = 0;

    try {
      const controller = new VoiceController({
        store,
        brain,
        neural: app?._regions?.neural || null,
      });
      controller.bind();

      /** @type {any} */
      (window).__titanVoiceController = controller;
      /** @type {any} */
      (window).__titanVoiceSocketSupported = voiceSocketSupported();
      /** @type {any} */
      (window).__titanVoiceSocket = VoiceSocket;

      // Cleanup on logout / app destroy.
      const prevDestroy = app.destroy?.bind(app);
      if (typeof prevDestroy === "function") {
        app.destroy = async () => {
          cancelMountAttempts();
          await controller.destroy();
          prevDestroy();
        };
      }

      window.addEventListener("titan:logout", () => {
        cancelMountAttempts();
        void controller.destroy();
      });
    } catch (err) {
      console.error("[Titan Voice] controller bind failed", err);
      // Enrollment panel can still mount without live push-to-talk chrome.
    }

    function cancelMountAttempts() {
      mountGeneration += 1;
      if (mountTimer != null) {
        clearTimeout(mountTimer);
        mountTimer = null;
      }
    }

    /**
     * Locate the voice center panel host created by panel layouts.
     * @returns {HTMLElement | null}
     */
    function findVoiceHost() {
      const panel =
        document.querySelector(".tdl-v2-panel-view--voice") ||
        document.getElementById("tdl-v2-voice-panel-root");
      if (!panel) return null;
      let host = panel.querySelector(".tdl-v2-voice-panel-host");
      if (!host) {
        host = document.createElement("div");
        host.className = "tdl-v2-voice-panel-host";
        panel.replaceChildren(host);
      }
      return /** @type {HTMLElement} */ (host);
    }

    /**
     * Visible failure state — preserves black/red shell; offers retry.
     * @param {HTMLElement} host
     * @param {string} message
     */
    function showMountFailure(host, message) {
      host.dataset.mounted = "0";
      host.dataset.mountError = "1";
      host.innerHTML = "";
      host.classList.add("tdl-v2-voice-panel");

      const header = document.createElement("header");
      header.className = "tdl-v2-screen-header";
      header.innerHTML = `
        <h2 class="tdl-v2-screen-header__title">Voice</h2>
        <p class="tdl-v2-screen-header__subtitle">Enrollment et session vocale</p>
      `;

      const body = document.createElement("div");
      body.className = "tdl-v2-screen-body";
      const status = document.createElement("p");
      status.className = "tdl-v2-empty-state tdl-v2-voice-mount-error";
      status.setAttribute("role", "alert");
      status.id = "tdl-v2-voice-mount-error";
      status.textContent = message;

      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "tdl-v2-btn tdl-v2-btn--primary";
      retry.id = "tdl-v2-voice-mount-retry";
      retry.textContent = "Réessayer";
      retry.addEventListener("click", () => {
        host.dataset.mountError = "0";
        scheduleVoicePanelMount({ force: true });
      });

      body.append(status, retry);
      host.append(header, body);
    }

    /**
     * Mount enrollment UI into the voice panel host when present.
     * @param {{ force?: boolean }} [opts]
     * @returns {boolean} true when mounted (or already mounted)
     */
    function tryMountPanel(opts = {}) {
      const host = findVoiceHost();
      if (!host) return false;
      if (!opts.force && host.dataset.mounted === "1") return true;

      try {
        delete host.dataset.mountError;
        mountEnrollmentPanel(host, { store, shell, brain, app });
        host.dataset.mounted = "1";
        return true;
      } catch (err) {
        const msg =
          err instanceof Error && err.message
            ? err.message
            : "Erreur au chargement du module vocal.";
        console.error("[Titan Voice] enrollment panel mount failed", err);
        showMountFailure(
          host,
          `Impossible de charger le module vocal (${msg}). Réessaie.`,
        );
        return true; // stop polling — error UI is visible
      }
    }

    /**
     * Retry across the async center-panel cross-fade (SCREEN_TRANSITION ~350ms).
     * A single rAF is not enough — the voice DOM is created only after exit.
     * @param {{ force?: boolean }} [opts]
     */
    function scheduleVoicePanelMount(opts = {}) {
      cancelMountAttempts();
      const generation = mountGeneration;
      const startedAt = Date.now();

      const tick = () => {
        if (generation !== mountGeneration) return;
        if (store.getState().route !== "voice") return;

        if (tryMountPanel(opts)) {
          mountTimer = null;
          return;
        }

        if (Date.now() - startedAt >= VOICE_MOUNT_TIMEOUT_MS) {
          mountTimer = null;
          const host = findVoiceHost();
          if (host) {
            showMountFailure(
              host,
              "Le module vocal n’a pas pu démarrer (délai dépassé). Réessaie.",
            );
          } else {
            console.error(
              "[Titan Voice] panel host missing after mount timeout",
            );
          }
          return;
        }

        mountTimer = setTimeout(tick, VOICE_MOUNT_POLL_MS);
      };

      // First attempt on next frame; then poll until panel exists or timeout.
      requestAnimationFrame(() => {
        if (generation !== mountGeneration) return;
        tick();
      });
    }

    store.subscribe((state) => {
      if (state.route === "voice") {
        scheduleVoicePanelMount();
      } else {
        cancelMountAttempts();
      }
    }, "route");

    // If the user is already on #voice when the extension loads, mount now.
    if (store.getState().route === "voice") {
      scheduleVoicePanelMount();
    }
  });
}

export { VOICE_MOUNT_TIMEOUT_MS, VOICE_MOUNT_POLL_MS };
