/** Titan Frontend V2 — Floating cards and cognitive float regions. */

export class CardsLayer {
  /**
   * @param {import("../layout/shell.js").Shell} shell
   */
  constructor(shell) {
    this._shell = shell;
    /** @type {HTMLElement | null} */
    this._layer = null;
  }

  mount() {
    this._layer = this._shell.get("tdl-v2-cards-layer");
    if (!this._layer) {
      return;
    }

    this._layer.dataset.layer = "floating-cards";
    this._layer.dataset.active = "false";

    this._seedFloatingRegions();
  }

  _seedFloatingRegions() {
    const tools = this._shell.get("tdl-v2-float-tools");
    const memory = this._shell.get("tdl-v2-float-memory");
    const orchestrator = this._shell.get("tdl-v2-float-orchestrator");

    // Idle seeds stay empty — ephemeral floats appear only when activity mounts
    // a real card. Avoid reference-composition clutter from placeholder floats.
    tools?.replaceChildren();
    memory?.replaceChildren();
    orchestrator?.replaceChildren();
  }

  /** @param {string} title @param {string} body */
  _floatCard(title, body) {
    const card = document.createElement("div");
    card.className = "tdl-v2-ephemeral-float";
    card.innerHTML = `
      <div class="tdl-v2-ephemeral-float__title">${title}</div>
      <div class="tdl-v2-ephemeral-float__body">${body}</div>
    `;
    return card;
  }

  /** @param {HTMLElement} card */
  mountCard(card) {
    if (!this._layer) {
      return;
    }
    this._layer.dataset.active = "true";
    card.dataset.floating = "true";
    this._layer.appendChild(card);
  }

  clear() {
    if (!this._layer) {
      return;
    }
    const tools = this._shell.get("tdl-v2-float-tools");
    const memory = this._shell.get("tdl-v2-float-memory");
    const orchestrator = this._shell.get("tdl-v2-float-orchestrator");
    tools?.replaceChildren();
    memory?.replaceChildren();
    orchestrator?.replaceChildren();
    this._seedFloatingRegions();
    this._layer.dataset.active = "false";
  }
}
