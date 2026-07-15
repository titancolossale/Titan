/** Titan Frontend V2 — Client router (Master Blueprint Screen Index). */

/** @typedef {import("./state-store.js").RouteKey} RouteKey */

/**
 * Route definitions from Master Blueprint §Screen Index + Sprint 2.7 nav.
 * Settings is overlay — not a center swap route.
 * Placeholder routes are marked BIENTÔT in the sidebar (no fake backends).
 */
export const ROUTES = Object.freeze([
  {
    key: "chat",
    path: "/chat",
    hash: "#chat",
    label: "Chat",
    nav: true,
    centerPanel: "chat",
    orchestratorFocus: ["state", "plan", "tools", "sparkline"],
    cognitiveModules: ["core"],
  },
  {
    key: "projects",
    path: "/projects",
    hash: "#projects",
    label: "Projects",
    nav: true,
    centerPanel: "projects",
    orchestratorFocus: ["state", "mission", "agents", "tools"],
    cognitiveModules: ["planification"],
  },
  {
    key: "memory",
    path: "/memory",
    hash: "#memory",
    label: "Memory",
    nav: true,
    centerPanel: "memory",
    orchestratorFocus: ["state", "retrieval", "writes", "sparkline"],
    cognitiveModules: ["memoire"],
  },
  {
    key: "browser",
    path: "/browser",
    hash: "#browser",
    label: "Exploration",
    nav: true,
    centerPanel: "browser",
    orchestratorFocus: ["health", "urls", "fetch", "timeline"],
    cognitiveModules: ["browser"],
  },
  {
    key: "obsidian",
    path: "/obsidian",
    hash: "#obsidian",
    label: "Obsidian",
    nav: true,
    centerPanel: "obsidian",
    orchestratorFocus: ["connector", "operation", "decision", "timeline"],
    cognitiveModules: ["obsidian"],
  },
  {
    key: "calendar",
    path: "/calendar",
    hash: "#calendar",
    label: "Calendar",
    nav: true,
    placeholder: true,
    centerPanel: "calendar",
    orchestratorFocus: ["planning", "conflicts", "tool"],
    cognitiveModules: ["calendar", "planification"],
  },
  {
    key: "trading",
    path: "/trading",
    hash: "#trading",
    label: "Trading",
    nav: true,
    placeholder: true,
    centerPanel: "trading",
    orchestratorFocus: ["analysis", "broker", "orders", "risk"],
    cognitiveModules: ["trading"],
  },
  {
    key: "tools",
    path: "/tools",
    hash: "#tools",
    label: "Tools",
    nav: true,
    placeholder: true,
    centerPanel: "tools",
    orchestratorFocus: ["tools", "health"],
    cognitiveModules: ["tools"],
  },
  {
    key: "voice",
    path: "/voice",
    hash: "#voice",
    label: "Voice",
    nav: false,
    centerPanel: "voice",
    orchestratorFocus: ["state"],
    cognitiveModules: ["core", "communication"],
  },
  {
    key: "settings",
    path: "/settings",
    hash: "#settings",
    label: "Settings",
    nav: true,
    overlay: true,
    centerPanel: null,
    orchestratorFocus: [],
    cognitiveModules: [],
  },
]);

/** @type {Map<RouteKey, typeof ROUTES[number]>} */
const ROUTE_BY_KEY = new Map(ROUTES.map((route) => [route.key, route]));

export class Router {
  /**
   * @param {import("./state-store.js").StateStore} store
   * @param {{ onNavigate?: (route: typeof ROUTES[number]) => void }} [options]
   */
  constructor(store, options = {}) {
    this._store = store;
    this._onNavigate = options.onNavigate ?? (() => {});
    this._boundPopState = this._handlePopState.bind(this);
  }

  start() {
    window.addEventListener("hashchange", this._boundPopState);
    window.addEventListener("popstate", this._boundPopState);
    this._syncFromLocation(false);
  }

  stop() {
    window.removeEventListener("hashchange", this._boundPopState);
    window.removeEventListener("popstate", this._boundPopState);
  }

  /** @param {RouteKey} key @param {{ replace?: boolean }} [options] */
  navigate(key, options = {}) {
    const route = ROUTE_BY_KEY.get(key);
    if (!route) {
      return;
    }

    const hash = route.hash;
    if (options.replace) {
      history.replaceState({ route: key }, "", hash);
    } else {
      history.pushState({ route: key }, "", hash);
    }

    this._applyRoute(route);
  }

  /** @returns {typeof ROUTES[number] | undefined} */
  getCurrentRoute() {
    return ROUTE_BY_KEY.get(this._store.getState().route);
  }

  /** @param {RouteKey} key */
  resolveRoute(key) {
    return ROUTE_BY_KEY.get(key);
  }

  _handlePopState() {
    this._syncFromLocation(true);
  }

  /** @param {boolean} fromHistory */
  _syncFromLocation(fromHistory) {
    const hash = window.location.hash || "#chat";
    const route = ROUTES.find((entry) => entry.hash === hash) ?? ROUTE_BY_KEY.get("chat");
    if (!route) {
      return;
    }
    this._applyRoute(route, fromHistory);
  }

  /** @param {typeof ROUTES[number]} route @param {boolean} [fromHistory] */
  _applyRoute(route, fromHistory = false) {
    if (route.overlay) {
      this._store.setState({
        route: route.key,
        settingsOpen: true,
      });
    } else {
      this._store.setState({
        route: route.key,
        settingsOpen: false,
        activePanelId: route.centerPanel,
      });
    }

    this._onNavigate(route, { fromHistory });
  }
}

export { ROUTE_BY_KEY };
