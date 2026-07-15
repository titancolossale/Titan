/** Titan Frontend V3 — Entry point. */

import { TitanAppV2 } from "./core/app.js";
import { ensureAuthenticated } from "./core/web-auth.js";

const app = new TitanAppV2();

ensureAuthenticated()
  .then(() => app.start())
  .catch((error) => {
    console.error("[Titan V2] Boot failed:", error);
  });

/** Dev-only globals — append `?dev=1` to enable console inspection. */
const devMode =
  new URLSearchParams(window.location.search).has("dev") ||
  window.localStorage.getItem("titan-v2-dev") === "1";

if (devMode) {
  window.__TITAN_V2__ = app;
  Object.defineProperty(window, "__TITAN_BRAIN__", {
    configurable: true,
    get() {
      return app.brain;
    },
  });
}
