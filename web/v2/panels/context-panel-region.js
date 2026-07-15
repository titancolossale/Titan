/** Titan Frontend V3 — Right Context Panel (resizable, hidden by default).
 *
 * Foundation only: renders placeholder inspector surfaces for the cognitive
 * systems that will be wired in later sprints (Context, Memory, World Model,
 * Knowledge, Workflow, Meta-Cognition). It reads/writes no Brain state yet.
 */

import { appendChildren, div, el, svgIcon } from "../components/dom-utils.js";
import { REGION_IDS } from "../layout/regions.js";

/** @type {readonly { id: string, label: string, hint: string }[]} */
const CONTEXT_SECTIONS = Object.freeze([
  { id: "context", label: "Contexte", hint: "Contexte cognitif assemblé pour la demande active." },
  { id: "memory", label: "Mémoire", hint: "Rappels pertinents et mémoire long terme." },
  { id: "world-model", label: "Modèle du monde", hint: "État courant perçu de l'environnement." },
  { id: "knowledge", label: "Connaissances", hint: "Savoirs vérifiés issus de l'expérience." },
  { id: "workflow", label: "Flux de travail", hint: "Étapes et missions orchestrées." },
  { id: "meta-cognition", label: "Méta-cognition", hint: "Confiance, incertitude et auto-évaluation." },
]);

const MIN_WIDTH = 280;
const MAX_WIDTH = 560;

export class ContextPanelRegion {
  /**
   * @param {import("../layout/shell.js").Shell} shell
   * @param {import("../core/state-store.js").StateStore} store
   */
  constructor(shell, store) {
    this._shell = shell;
    this._store = store;
    /** @type {HTMLElement | null} */
    this._host = null;
    this._onPointerMove = this._onPointerMove.bind(this);
    this._onPointerUp = this._onPointerUp.bind(this);
  }

  mount() {
    const host = this._shell.get(REGION_IDS.contextPanel);
    if (!host) {
      return;
    }
    this._host = host;

    host.append(this._buildResizeHandle(), this._buildHeader(), this._buildBody());
    this._applyWidth(this._store.getState().contextPanelWidth);
    this._applyOpenState(this._store.getState().contextPanelOpen);

    this._store.subscribe((state) => this._applyOpenState(state.contextPanelOpen), "contextPanelOpen");
    this._store.subscribe((state) => this._applyWidth(state.contextPanelWidth), "contextPanelWidth");
  }

  _buildResizeHandle() {
    const handle = div("tdl-v2-context-panel__resize");
    handle.setAttribute("role", "separator");
    handle.setAttribute("aria-orientation", "vertical");
    handle.setAttribute("aria-label", "Redimensionner le panneau");
    handle.addEventListener("pointerdown", (event) => this._onPointerDown(event));
    return handle;
  }

  _buildHeader() {
    const header = div("tdl-v2-context-panel__header");
    header.append(
      el("h2", "tdl-v2-context-panel__title", { text: "Contexte" }),
    );

    const close = el("button", "tdl-v2-context-panel__close", {
      type: "button",
      "aria-label": "Fermer le panneau de contexte",
    });
    close.appendChild(
      svgIcon(
        "0 0 24 24",
        '<path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
      ),
    );
    close.addEventListener("click", () => this._store.setState({ contextPanelOpen: false }));
    header.appendChild(close);
    return header;
  }

  _buildBody() {
    const body = div("tdl-v2-context-panel__body");
    for (const section of CONTEXT_SECTIONS) {
      body.appendChild(this._buildSection(section));
    }
    return body;
  }

  /** @param {{ id: string, label: string, hint: string }} section */
  _buildSection(section) {
    const wrap = el("section", "tdl-v2-context-panel__section", {
      "data-section": section.id,
    });

    const head = div("tdl-v2-context-panel__section-head");
    head.append(
      el("h3", "tdl-v2-context-panel__section-title", { text: section.label }),
      el("span", "tdl-v2-context-panel__badge", { text: "Bientôt" }),
    );

    const placeholder = div("tdl-v2-context-panel__placeholder");
    placeholder.append(
      div("tdl-v2-context-panel__placeholder-orb"),
      el("p", "tdl-v2-context-panel__placeholder-text", { text: section.hint }),
    );

    appendChildren(wrap, head, placeholder);
    return wrap;
  }

  /** @param {boolean} open */
  _applyOpenState(open) {
    const host = this._host;
    if (!host) {
      return;
    }
    host.dataset.open = String(Boolean(open));
    host.setAttribute("aria-hidden", String(!open));
    const root = this._shell.root;
    if (root) {
      root.classList.toggle("tdl-v2--context-open", Boolean(open));
    }
  }

  /** @param {number} width */
  _applyWidth(width) {
    const host = this._host;
    if (!host) {
      return;
    }
    const clamped = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(width) || MIN_WIDTH));
    host.style.setProperty("--tdl-context-panel-width", `${clamped}px`);
  }

  /** @param {PointerEvent} event */
  _onPointerDown(event) {
    event.preventDefault();
    this._resizing = true;
    this._host?.classList.add("tdl-v2-context-panel--resizing");
    window.addEventListener("pointermove", this._onPointerMove);
    window.addEventListener("pointerup", this._onPointerUp);
  }

  /** @param {PointerEvent} event */
  _onPointerMove(event) {
    if (!this._resizing) {
      return;
    }
    // Panel is docked to the right edge; width grows as the pointer moves left.
    const width = window.innerWidth - event.clientX;
    this._store.setState({ contextPanelWidth: width });
  }

  _onPointerUp() {
    this._resizing = false;
    this._host?.classList.remove("tdl-v2-context-panel--resizing");
    window.removeEventListener("pointermove", this._onPointerMove);
    window.removeEventListener("pointerup", this._onPointerUp);
  }

  destroy() {
    window.removeEventListener("pointermove", this._onPointerMove);
    window.removeEventListener("pointerup", this._onPointerUp);
  }
}
