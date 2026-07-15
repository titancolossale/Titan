/** Titan Frontend V2 — Sidebar region (Phase 4 chrome · Phase 5 composition). */

import { appendChildren, div, el } from "../components/dom-utils.js";
import { createTitanLogo, createTitanLogoGlyph } from "../components/titan-logo.js";
import { ROUTES } from "../core/router.js";
import { TITAN_UI_VERSION_LABEL } from "../core/version.js";
import { REGION_IDS } from "../layout/regions.js";

const PRESENCE_LABELS = Object.freeze({
  idle: "Je suis prêt. À tes côtés.",
  listening: "À l'écoute.",
  thinking: "Je réfléchis avec toi.",
  streaming: "Je formule une réponse.",
  speaking: "Je m'exprime.",
  working: "J'exécute.",
  planning: "Je planifie.",
  error: "Une alerte demande attention.",
});

export class SidebarRegion {
  /**
   * @param {import("../layout/shell.js").Shell} shell
   * @param {import("../core/state-store.js").StateStore} store
   * @param {import("../core/router.js").Router} router
   */
  constructor(shell, store, router) {
    this._shell = shell;
    this._store = store;
    this._router = router;
    /** @type {import("../core/cognitive-state-engine.js").CognitiveStateEngine | null} */
    this._brain = null;
    /** @type {ReturnType<typeof setInterval> | null} */
    this._fpsTimer = null;
    /** @type {HTMLElement | null} */
    this._host = null;
    /** @type {boolean} */
    this._peek = false;
  }

  /**
   * @param {import("../core/cognitive-state-engine.js").CognitiveStateEngine} brain
   */
  setBrain(brain) {
    this._brain = brain;
    brain.onStateChanged(() => this._syncPresence());
    brain.onToolActivity(() => this._syncPresence());
    this._syncPresence();
  }

  mount() {
    const host = this._shell.get(REGION_IDS.sidebar);
    if (!host) {
      return;
    }

    this._host = host;
    host.dataset.phase = "10";
    host.dataset.canonical = "final";
    host.replaceChildren(
      this._buildLogo(),
      this._buildNav(),
      this._buildPresence(),
    );

    this._initCollapse(host);

    this._store.subscribe((state) => {
      host.querySelectorAll("[data-route]").forEach((navEl) => {
        const key = navEl.getAttribute("data-route");
        navEl.setAttribute("aria-current", key === state.route ? "page" : "false");
        navEl.classList.toggle("tdl-v2-nav-item--active", key === state.route);
      });
    }, "route");

    this._store.subscribe((state) => {
      const versionEl = document.getElementById("tdl-v2-system-version");
      if (versionEl) {
        versionEl.textContent = state.systemVersion
          ? `v${state.systemVersion}`
          : TITAN_UI_VERSION_LABEL;
      }
    }, "systemVersion");

    this._store.subscribe(() => this._syncPresence(), "presence");
    this._store.subscribe(() => this._syncPresence(), "connectionState");
    this._store.subscribe(() => this._applyCollapseState(), "sidebarPinned");

    this._startFpsTelemetry();
  }

  /**
   * Desktop default is the full sidebar. Collapse remains available for later
   * and for tablet/phone modes.
   * @param {HTMLElement} host
   */
  _initCollapse(host) {
    this._peek = false;
    host.addEventListener("mouseenter", () => {
      if (!this._store.getState().sidebarPinned) {
        this._setPeek(true);
      }
    });
    host.addEventListener("mouseleave", () => this._setPeek(false));
    host.addEventListener("focusin", () => {
      if (!this._store.getState().sidebarPinned) {
        this._setPeek(true);
      }
    });
    host.addEventListener("focusout", (event) => {
      if (!host.contains(/** @type {Node} */ (event.relatedTarget))) {
        this._setPeek(false);
      }
    });
    this._applyCollapseState();
  }

  toggleSidebar() {
    const pinned = !this._store.getState().sidebarPinned;
    this._store.setState({ sidebarPinned: pinned });
  }

  /** @param {boolean} peek */
  _setPeek(peek) {
    if (this._peek === peek) {
      return;
    }
    this._peek = peek;
    this._applyCollapseState();
  }

  _applyCollapseState() {
    const host = this._host;
    if (!host) {
      return;
    }
    const pinned = this._store.getState().sidebarPinned;
    const expanded = pinned || this._peek;
    host.dataset.expanded = String(expanded);
    host.dataset.peek = String(!pinned && this._peek);
    host.dataset.pinned = String(pinned);

    const root = this._shell.root;
    if (root) {
      root.classList.toggle("tdl-v2--sidebar-expanded", pinned);
      root.classList.toggle("tdl-v2--sidebar-collapsed", !pinned);
    }

    const toggle = document.getElementById("tdl-v2-sidebar-toggle");
    if (toggle) {
      toggle.setAttribute("aria-expanded", String(pinned));
      toggle.setAttribute(
        "aria-label",
        pinned ? "Réduire la barre latérale" : "Épingler la barre latérale",
      );
    }

    const collapse = document.getElementById("tdl-v2-sidebar-collapse");
    if (collapse) {
      collapse.textContent = pinned ? "Réduire" : "Étendre";
    }
  }

  destroy() {
    if (this._fpsTimer !== null) {
      window.clearInterval(this._fpsTimer);
      this._fpsTimer = null;
    }
  }

  _buildLogo() {
    const logo = div("tdl-v2-logo");

    const toggle = el("button", "tdl-v2-sidebar-toggle", {
      type: "button",
      id: "tdl-v2-sidebar-toggle",
      "aria-label": "Réduire la barre latérale",
      "aria-expanded": "true",
    });
    toggle.appendChild(createTitanLogoGlyph());
    toggle.addEventListener("click", () => this.toggleSidebar());

    const label = div("tdl-v2-logo__label");
    const wordmark = el("h1", "tdl-v2-logo__wordmark");
    wordmark.innerHTML = 'TITAN <span class="tdl-v2-logo__accent">AI</span>';
    const tagline = el("span", "tdl-v2-logo__tagline", {
      id: "tdl-v2-system-version",
      text: TITAN_UI_VERSION_LABEL,
    });
    label.append(wordmark, tagline);

    logo.append(toggle, label);
    return logo;
  }

  _buildNav() {
    const nav = el("nav", "tdl-v2-sidebar-nav", { "aria-label": "Navigation principale" });

    for (const route of ROUTES.filter((r) => r.nav)) {
      const button = el("button", "tdl-v2-nav-item", {
        type: "button",
        "data-route": route.key,
      });
      if (route.key === "chat") {
        button.classList.add("tdl-v2-nav-item--conversation");
      }
      const label = document.createElement("span");
      label.textContent = route.label;
      button.appendChild(label);

      if (route.placeholder) {
        button.dataset.placeholder = "true";
        const badge = el("span", "tdl-v2-nav-item__badge", { text: "Bientôt" });
        button.appendChild(badge);
      }
      if (route.overlay) {
        button.dataset.overlay = "true";
      }
      button.addEventListener("click", () => {
        this._router.navigate(route.key);
      });
      nav.appendChild(button);
    }

    return nav;
  }

  _buildPresence() {
    const footer = div("tdl-v2-sidebar-footer tdl-v2-sidebar-presence");
    footer.setAttribute("aria-label", "Présence Titan");

    const online = div("tdl-v2-presence-status");
    online.append(
      el("span", "tdl-v2-presence-status__pill tdl-v2-presence-status__pill--online", {
        id: "tdl-v2-bar-system",
        text: "TITAN ONLINE",
      }),
      el("span", "tdl-v2-presence-status__pill tdl-v2-presence-status__pill--brain", {
        id: "tdl-v2-bar-brain",
        text: "CERVEAU ACTIF",
      }),
    );

    // Flattened presence block — part of the rail, not a nested widget.
    const block = div("tdl-v2-presence-card tdl-v2-sidebar-presence__block");
    block.id = "tdl-v2-sidebar-presence-card";

    const cardHead = div("tdl-v2-presence-card__head");
    cardHead.append(
      el("span", "tdl-v2-presence-card__title", { text: "TITAN PRESENCE" }),
      createTitanLogo({
        size: "sm",
        className: "tdl-v2-presence-card__logo tdl-v2-presence-card__orb",
      }),
    );

    const preview = div("tdl-v2-presence-card__preview");
    preview.id = "tdl-v2-sidebar-presence-widget";
    preview.setAttribute("aria-label", "Activité cognitive");
    const waveform = div("tdl-v2-waveform");
    waveform.id = "tdl-v2-presence-waveform";
    for (let i = 0; i < 10; i += 1) {
      const bar = div("tdl-v2-waveform__bar");
      bar.style.height = `${28 + (i % 5) * 14}%`;
      waveform.appendChild(bar);
    }
    const mark = createTitanLogo({
      size: "md",
      className: "tdl-v2-presence-card__mark tdl-v2-mini-core",
    });
    preview.append(waveform, mark);

    const copy = el("p", "tdl-v2-presence-card__copy", {
      id: "tdl-v2-presence-card-copy",
      text: PRESENCE_LABELS.idle,
    });

    block.append(cardHead, preview, copy);

    const collapseBtn = el("button", "tdl-v2-sidebar-collapse", {
      type: "button",
      id: "tdl-v2-sidebar-collapse",
      "aria-label": "Basculer la barre latérale",
      text: "Réduire",
    });
    collapseBtn.addEventListener("click", () => this.toggleSidebar());

    appendChildren(footer, online, block, collapseBtn);
    return footer;
  }

  _syncPresence() {
    const state = this._store.getState();
    const connected =
      state.connectionState === "connected" || state.connectionState === "streaming";
    let presence = state.presence ?? "idle";
    if (presence === "error" && (!connected || !state.lastError)) {
      presence = "idle";
    }
    const copy = PRESENCE_LABELS[presence] ?? PRESENCE_LABELS.idle;

    const copyEl = document.getElementById("tdl-v2-presence-card-copy");
    if (copyEl) {
      copyEl.textContent = copy;
    }

    const widget = document.getElementById("tdl-v2-sidebar-presence-widget");
    if (widget) {
      widget.dataset.presence = presence;
      widget.dataset.active = String(presence !== "idle");
    }

    const online = document.getElementById("tdl-v2-bar-system");
    if (online) {
      const conn = state.connectionState ?? "disconnected";
      const live = conn === "connected" || conn === "streaming";
      online.textContent = live ? "TITAN ONLINE" : conn === "connecting" ? "CONNEXION…" : "HORS LIGNE";
      online.dataset.connection = conn;
    }

    const brain = document.getElementById("tdl-v2-bar-brain");
    if (brain) {
      brain.textContent = presence === "idle" ? "CERVEAU ACTIF" : "CERVEAU EN COURS";
      brain.dataset.presence = presence;
    }
  }

  _startFpsTelemetry() {
    // FPS lives in the bottom system strip; sidebar remains presence-only.
  }
}
