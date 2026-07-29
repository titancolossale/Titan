/** Titan Voice UI — extension registration (Phase 20.4). */

import { mountEnrollmentPanel } from "./enrollment-ui.js";
import { VoiceController } from "./voice-controller.js";
import { VoiceSocket, voiceSocketSupported } from "./voice-socket.js";

/**
 * Register the Voice extension hook — wires mic + enrollment panel.
 * Phase 20.8: VoiceSocket is available for optional WS uplink (no UI redesign).
 * @param {import("../core/extension-registry.js").ExtensionRegistry} extensions
 */
export function registerVoiceExtension(extensions) {
  extensions.register("voice", (ctx) => {
    const { app, brain, store, shell } = ctx;
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

    // Remount enrollment UI whenever the voice panel is shown.
    const tryMountPanel = () => {
      const panel =
        document.querySelector(".tdl-v2-panel-view--voice") ||
        document.getElementById("tdl-v2-voice-panel-root");
      if (!panel) return;
      let host = panel.querySelector(".tdl-v2-voice-panel-host");
      if (!host) {
        host = document.createElement("div");
        host.className = "tdl-v2-voice-panel-host";
        panel.replaceChildren(host);
      }
      if (host.dataset.mounted === "1") return;
      host.dataset.mounted = "1";
      mountEnrollmentPanel(host, { store, shell, brain, app });
    };

    store.subscribe((state) => {
      if (state.route === "voice") {
        requestAnimationFrame(() => tryMountPanel());
      }
    }, "route");

    // Cleanup on logout / app destroy.
    const prevDestroy = app.destroy?.bind(app);
    if (typeof prevDestroy === "function") {
      app.destroy = async () => {
        await controller.destroy();
        prevDestroy();
      };
    }

    // Also hook settings logout path via global.
    window.addEventListener("titan:logout", () => {
      void controller.destroy();
    });
  });
}
