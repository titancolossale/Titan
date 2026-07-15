/** Titan Frontend V2 — Cognitive Satellite system (Sprint 2 · Living Neural Core V1).
 *
 * Presentation layer for Titan's central neural core. Renders the dominant Titan
 * Core label and the ring of cognitive satellites (Memory, Reasoning, …) with
 * neural links back to the core. Satellites are visual representations only in
 * this sprint — they read status from the shared frontend state via the
 * NeuralStatusAdapter and never mutate any backend capability.
 *
 * Phase 5.3 — Reference Scene: Core as gravity point; organic orbits; major
 * neural highways + secondary branches + local synapses (presentation SVG only).
 * Phase 8 — Living Presence: Core heartbeat / energy / waves; occasional
 * inter-satellite light packets (presentation only — no Brain / API changes).
 *
 * Rendering (DOM overlay) is intentionally separate from state adaptation
 * (neural-status-adapter.js) and visual configuration (design/satellites.css).
 */

import { SATELLITE_IDS, SATELLITE_STATUS } from "./neural-status-adapter.js";

const SVG_NS = "http://www.w3.org/2000/svg";

/** Human status labels (English per Sprint 2 spec). */
const STATUS_LABEL = Object.freeze({
  [SATELLITE_STATUS.IDLE]: "IDLE",
  [SATELLITE_STATUS.ACTIVE]: "ACTIVE",
  [SATELLITE_STATUS.WAITING]: "WAITING",
});

/** Titan Core label copy (canonical final reference). */
export const TITAN_CORE_LABEL = Object.freeze({
  title: "TITAN CORE",
  subtitle: "Conscience & Orchestration",
});

/**
 * Reference subsystem satellites. Positions owned by CSS (`design/satellites.css`).
 * @type {readonly { id: string, title: string, role: string }[]}
 */
export const SATELLITE_DEFINITIONS = Object.freeze([
  { id: "memory", title: "MÉMOIRE", role: "Rappel & contexte" },
  { id: "planning", title: "PLANIFICATION", role: "Planification" },
  { id: "browser", title: "NAVIGATION", role: "Recherche web" },
  { id: "obsidian", title: "OBSIDIAN", role: "Vault personnel" },
  { id: "tools", title: "OUTILS", role: "Exécution d'outils" },
  { id: "communication", title: "COMMUNICATION", role: "Langage & réponses" },
  { id: "trading", title: "TRADING", role: "Marchés & risque" },
  { id: "calendar", title: "CALENDAR", role: "Temps & agenda" },
]);

/**
 * A single cognitive satellite (luminous node + label + status + tooltip).
 * Clicking emits a bubbling `titan:satellite-select` event for future panels;
 * it performs no navigation and no business logic in this sprint.
 */
export class CognitiveSatellite {
  /** @param {{ id: string, title: string, role: string }} definition */
  constructor(definition) {
    this.id = definition.id;
    this.title = definition.title;
    this.role = definition.role;
    this.status = SATELLITE_STATUS.IDLE;

    /** @type {HTMLButtonElement} */
    this.el = document.createElement("button");
    this.el.type = "button";
    this.el.className = `tdl-v2-satellite tdl-v2-satellite--${this.id}`;
    this.el.dataset.satellite = this.id;
    this.el.dataset.status = this.status;

    this.el.innerHTML = `
      <span class="tdl-v2-satellite__aura" aria-hidden="true"></span>
      <span class="tdl-v2-satellite__node" aria-hidden="true"></span>
      <span class="tdl-v2-satellite__body">
        <span class="tdl-v2-satellite__title">${this.title}</span>
        <span class="tdl-v2-satellite__status" data-role="status">${STATUS_LABEL[this.status]}</span>
      </span>
      <span class="tdl-v2-satellite__tooltip" role="tooltip">
        <span class="tdl-v2-satellite__tooltip-title">${this.title}</span>
        <span class="tdl-v2-satellite__tooltip-role">${this.role}</span>
        <span class="tdl-v2-satellite__tooltip-status" data-role="tooltip-status">${STATUS_LABEL[this.status]}</span>
      </span>
    `;

    this._statusEl = this.el.querySelector('[data-role="status"]');
    this._tooltipStatusEl = this.el.querySelector('[data-role="tooltip-status"]');
    this._applyAria();

    this._onClick = () => this._emitSelect();
    this.el.addEventListener("click", this._onClick);
  }

  /** @param {string} status one of SATELLITE_STATUS */
  setStatus(status) {
    if (!STATUS_LABEL[status] || status === this.status) {
      return;
    }
    this.status = status;
    this.el.dataset.status = status;
    const label = STATUS_LABEL[status];
    if (this._statusEl) this._statusEl.textContent = label;
    if (this._tooltipStatusEl) this._tooltipStatusEl.textContent = label;
    this._applyAria();
  }

  _applyAria() {
    this.el.setAttribute(
      "aria-label",
      `${this.title} — ${this.role} — ${STATUS_LABEL[this.status]}`,
    );
  }

  _emitSelect() {
    this.el.dispatchEvent(
      new CustomEvent("titan:satellite-select", {
        bubbles: true,
        detail: { id: this.id, title: this.title, role: this.role, status: this.status },
      }),
    );
  }

  destroy() {
    this.el.removeEventListener("click", this._onClick);
    this.el.remove();
  }
}

/**
 * Controller that builds the Titan Core label, the satellite ring, and the SVG
 * neural links, then applies status maps from the NeuralStatusAdapter.
 */
export class CognitiveSatelliteField {
  /** @param {HTMLElement} host label host element (`tdl-v2-neural-labels`) */
  constructor(host) {
    this._host = host;
    /** @type {HTMLElement | null} */
    this._field = null;
    /** @type {HTMLElement | null} */
    this._core = null;
    /** @type {SVGSVGElement | null} */
    this._svg = null;
    /** @type {Map<string, CognitiveSatellite>} */
    this._satellites = new Map();
    /** @type {Map<string, SVGPathElement>} */
    this._links = new Map();
    /** @type {Map<string, SVGPathElement>} */
    this._secondaryLinks = new Map();
    /** @type {Map<string, SVGPathElement>} */
    this._synapseLinks = new Map();
    this._behavior = "IDLE";
    this._layoutRaf = 0;
    this._onResize = () => this._scheduleLayout();
    /** @type {number | null} */
    this._packetTimer = null;
    /** @type {number} */
    this._packetSeed = 1;
    /** @type {SVGSVGElement | null} */
    this._packetSvg = null;
  }

  mount() {
    const field = document.createElement("div");
    field.className = "tdl-v2-satellite-field";
    field.dataset.presence = "8";
    this._field = field;

    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", "tdl-v2-satellite-links");
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("aria-hidden", "true");
    this._svg = svg;

    const packetSvg = document.createElementNS(SVG_NS, "svg");
    packetSvg.setAttribute("class", "tdl-v2-satellite-packet-layer");
    packetSvg.setAttribute("preserveAspectRatio", "none");
    packetSvg.setAttribute("aria-hidden", "true");
    this._packetSvg = packetSvg;

    const core = document.createElement("div");
    core.className = "tdl-v2-satellite-core";
    core.dataset.satellite = "core";
    core.dataset.presence = "8";
    /* Tissue filaments overlay typography so the label reads buried in the organism
       (Phase 5.1 immersive stage — presentation only).
       Phase 8 adds heartbeat / energy / wave markers — presentation only. */
    core.innerHTML = `
      <span class="tdl-v2-satellite-core__gravity" aria-hidden="true"></span>
      <span class="tdl-v2-satellite-core__energy" aria-hidden="true"></span>
      <span class="tdl-v2-satellite-core__halo" aria-hidden="true"></span>
      <span class="tdl-v2-satellite-core__heartbeat" aria-hidden="true"></span>
      <span class="tdl-v2-satellite-core__wave" aria-hidden="true"></span>
      <span class="tdl-v2-satellite-core__wave tdl-v2-satellite-core__wave--b" aria-hidden="true"></span>
      <span class="tdl-v2-satellite-core__nucleus" aria-hidden="true"></span>
      <span class="tdl-v2-satellite-core__attention" aria-hidden="true"></span>
      <span class="tdl-v2-satellite-core__title">${TITAN_CORE_LABEL.title}</span>
      <span class="tdl-v2-satellite-core__subtitle">${TITAN_CORE_LABEL.subtitle}</span>
      <span class="tdl-v2-satellite-core__tissue" aria-hidden="true">
        <svg class="tdl-v2-satellite-core__embed-svg" viewBox="0 0 240 72" preserveAspectRatio="none">
          <path class="tdl-v2-satellite-core__embed-path tdl-v2-satellite-core__embed-path--a" stroke-width="1.6" d="M4 30 C 48 22, 92 40, 136 28 S 188 36, 236 26" />
          <path class="tdl-v2-satellite-core__embed-path tdl-v2-satellite-core__embed-path--b" stroke-width="1.9" d="M6 38 C 54 48, 100 30, 146 42 S 194 34, 236 44" />
          <path class="tdl-v2-satellite-core__embed-path tdl-v2-satellite-core__embed-path--c" stroke-width="1.15" d="M22 22 C 70 12, 118 30, 162 18 S 208 26, 234 16" />
          <path class="tdl-v2-satellite-core__embed-path tdl-v2-satellite-core__embed-path--d" stroke-width="1.25" d="M18 50 C 66 56, 116 44, 164 54 S 210 46, 234 52" />
          <path class="tdl-v2-satellite-core__embed-path tdl-v2-satellite-core__embed-path--e" stroke-width="1.05" d="M58 34 C 96 28, 128 42, 170 32" />
          <path class="tdl-v2-satellite-core__embed-path tdl-v2-satellite-core__embed-path--f" stroke-width="0.9" d="M72 46 C 108 40, 142 52, 178 44" />
        </svg>
      </span>
      <span class="tdl-v2-satellite-core__veil" aria-hidden="true"></span>
    `;
    this._core = core;

    field.append(svg, packetSvg);

    for (const definition of SATELLITE_DEFINITIONS) {
      const satellite = new CognitiveSatellite(definition);
      this._satellites.set(definition.id, satellite);

      /* Phase 5.3 — layered highways: major · secondary · local synapse */
      const major = document.createElementNS(SVG_NS, "path");
      major.setAttribute(
        "class",
        `tdl-v2-satellite-link tdl-v2-satellite-link--${definition.id}`,
      );
      major.dataset.satellite = definition.id;
      major.setAttribute("fill", "none");
      this._links.set(definition.id, major);
      svg.appendChild(major);

      const secondary = document.createElementNS(SVG_NS, "path");
      secondary.setAttribute(
        "class",
        `tdl-v2-satellite-link tdl-v2-satellite-link--secondary tdl-v2-satellite-link--${definition.id}-sec`,
      );
      secondary.dataset.satellite = definition.id;
      secondary.setAttribute("fill", "none");
      this._secondaryLinks.set(definition.id, secondary);
      svg.appendChild(secondary);

      const synapse = document.createElementNS(SVG_NS, "path");
      synapse.setAttribute(
        "class",
        `tdl-v2-satellite-link tdl-v2-satellite-link--synapse tdl-v2-satellite-link--${definition.id}-syn`,
      );
      synapse.dataset.satellite = definition.id;
      synapse.setAttribute("fill", "none");
      this._synapseLinks.set(definition.id, synapse);
      svg.appendChild(synapse);

      field.appendChild(satellite.el);
    }

    field.appendChild(core);
    this._host.appendChild(field);

    window.addEventListener("resize", this._onResize);
    this._scheduleLayout();
    this._startPacketLoop();
  }

  /**
   * Apply a resolved neural status.
   * @param {{ behavior: string, satellites: Record<string, string> }} status
   */
  apply(status) {
    if (!status) return;
    this._behavior = status.behavior;
    this._host.dataset.behavior = status.behavior;
    if (this._field) this._field.dataset.behavior = status.behavior;

    for (const id of SATELLITE_IDS) {
      const satellite = this._satellites.get(id);
      const value = status.satellites?.[id] ?? SATELLITE_STATUS.IDLE;
      satellite?.setStatus(value);
      for (const map of [this._links, this._secondaryLinks, this._synapseLinks]) {
        const link = map.get(id);
        if (link) link.dataset.status = value;
      }
    }
  }

  /**
   * Subtle pointer parallax — translates the whole satellite field for depth.
   * @param {number} nx normalized -1..1
   * @param {number} ny normalized -1..1
   */
  setParallax(nx, ny) {
    if (!this._field) return;
    const range = 10;
    this._field.style.transform = `translate3d(${(nx * range).toFixed(2)}px, ${(ny * range).toFixed(2)}px, 0)`;
  }

  resetParallax() {
    if (this._field) this._field.style.transform = "";
  }

  _scheduleLayout() {
    if (this._layoutRaf) return;
    this._layoutRaf = requestAnimationFrame(() => {
      this._layoutRaf = 0;
      this._layoutLinks();
    });
  }

  /**
   * Build a cubic axon path from satellite → Core with perpendicular bend.
   * @param {number} sx
   * @param {number} sy
   * @param {number} coreX
   * @param {number} coreY
   * @param {number} bendScale
   * @param {number} sign
   */
  _curvePath(sx, sy, coreX, coreY, bendScale, sign) {
    const dx = coreX - sx;
    const dy = coreY - sy;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const bend = dist * bendScale * sign;
    const c1x = sx + dx * 0.28 - (dy / dist) * bend * 0.7;
    const c1y = sy + dy * 0.28 + (dx / dist) * bend * 0.7;
    const c2x = sx + dx * 0.72 - (dy / dist) * bend * 1.15;
    const c2y = sy + dy * 0.72 + (dx / dist) * bend * 1.15;
    return `M ${sx.toFixed(1)} ${sy.toFixed(1)} C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${coreX.toFixed(1)} ${coreY.toFixed(1)}`;
  }

  /** Phase 8 — occasional slow light packets between satellites. */
  _startPacketLoop() {
    if (this._packetTimer != null) return;
    if (typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
    const schedule = () => {
      const delay = 4200 + (this._nextPacketRand() % 6800);
      this._packetTimer = window.setTimeout(() => {
        this._spawnLightPacket();
        schedule();
      }, delay);
    };
    schedule();
  }

  /** Deterministic-ish PRNG so paths vary without tight loops. */
  _nextPacketRand() {
    this._packetSeed = (this._packetSeed * 1103515245 + 12345) & 0x7fffffff;
    return this._packetSeed;
  }

  /**
   * Spawn one light packet along a unique curved path between two satellites.
   * Presentation only — never implies fake tool execution.
   */
  _spawnLightPacket() {
    if (!this._packetSvg || !this._field) return;
    const ids = [...this._satellites.keys()];
    if (ids.length < 2) return;

    const a = ids[this._nextPacketRand() % ids.length];
    let b = ids[this._nextPacketRand() % ids.length];
    if (b === a) {
      b = ids[(ids.indexOf(a) + 1 + (this._nextPacketRand() % (ids.length - 1))) % ids.length];
    }

    const from = this._satelliteNodePoint(a);
    const to = this._satelliteNodePoint(b);
    if (!from || !to) return;

    const hostRect = this._field.getBoundingClientRect();
    this._packetSvg.setAttribute("viewBox", `0 0 ${hostRect.width} ${hostRect.height}`);

    const bend = 0.18 + (this._nextPacketRand() % 22) / 100;
    const sign = this._nextPacketRand() % 2 === 0 ? 1 : -1;
    const d = this._curvePath(from.x, from.y, to.x, to.y, bend, sign);

    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("class", "tdl-v2-satellite-packet-path");
    path.setAttribute("d", d);
    path.setAttribute("fill", "none");
    this._packetSvg.appendChild(path);

    const packet = document.createElementNS(SVG_NS, "circle");
    packet.setAttribute("class", "tdl-v2-satellite-packet");
    packet.setAttribute("r", "1.6");
    packet.setAttribute("cx", String(from.x));
    packet.setAttribute("cy", String(from.y));
    this._packetSvg.appendChild(packet);

    const duration = 5200 + (this._nextPacketRand() % 4200);
    const start = performance.now();
    const ease = (t) => t * t * (3 - 2 * t);

    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const u = ease(t);
      const pt = path.getPointAtLength(u * path.getTotalLength());
      packet.setAttribute("cx", String(pt.x));
      packet.setAttribute("cy", String(pt.y));
      const fade = t < 0.12 ? t / 0.12 : t > 0.85 ? (1 - t) / 0.15 : 1;
      packet.style.opacity = String(0.55 * fade);
      if (t < 1) {
        requestAnimationFrame(step);
      } else {
        packet.remove();
        path.remove();
      }
    };
    requestAnimationFrame(step);
  }

  /** @param {string} id @returns {{ x: number, y: number } | null} */
  _satelliteNodePoint(id) {
    const satellite = this._satellites.get(id);
    if (!satellite || !this._field) return null;
    const hostRect = this._field.getBoundingClientRect();
    const nodeEl = satellite.el.querySelector(".tdl-v2-satellite__node") || satellite.el;
    const rect = nodeEl.getBoundingClientRect();
    return {
      x: rect.left + rect.width / 2 - hostRect.left,
      y: rect.top + rect.height / 2 - hostRect.top,
    };
  }

  /** Measure rendered geometry and draw major / secondary / synapse highways. */
  _layoutLinks() {
    if (!this._svg || !this._core || !this._field) return;
    const hostRect = this._field.getBoundingClientRect();
    if (hostRect.width < 1 || hostRect.height < 1) return;

    this._svg.setAttribute("viewBox", `0 0 ${hostRect.width} ${hostRect.height}`);
    if (this._packetSvg) {
      this._packetSvg.setAttribute("viewBox", `0 0 ${hostRect.width} ${hostRect.height}`);
    }

    const coreRect = this._core.getBoundingClientRect();
    const coreX = coreRect.left + coreRect.width / 2 - hostRect.left;
    const coreY = coreRect.top + coreRect.height / 2 - hostRect.top;

    for (const [id, satellite] of this._satellites) {
      const nodeEl = satellite.el.querySelector(".tdl-v2-satellite__node") || satellite.el;
      const rect = nodeEl.getBoundingClientRect();
      const sx = rect.left + rect.width / 2 - hostRect.left;
      const sy = rect.top + rect.height / 2 - hostRect.top;

      const seed = id.charCodeAt(0);
      const sign = id.length % 2 === 0 ? 1 : -1;
      const majorBend = 0.24 + (seed % 5) * 0.028;
      const secBend = 0.14 + (seed % 4) * 0.02;
      const synBend = 0.32 + (seed % 3) * 0.04;

      const major = this._links.get(id);
      if (major) {
        major.setAttribute("d", this._curvePath(sx, sy, coreX, coreY, majorBend, sign));
      }

      const secondary = this._secondaryLinks.get(id);
      if (secondary) {
        /* Offset secondary branch slightly along the perpendicular for depth. */
        const dx = coreX - sx;
        const dy = coreY - sy;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const ox = (-dy / dist) * 7 * sign;
        const oy = (dx / dist) * 7 * sign;
        secondary.setAttribute(
          "d",
          this._curvePath(sx + ox, sy + oy, coreX + ox * 0.25, coreY + oy * 0.25, secBend, -sign),
        );
      }

      const synapse = this._synapseLinks.get(id);
      if (synapse) {
        /* Local synapse: shorter mid-path wisp, not full Core connection. */
        const mx = sx + (coreX - sx) * 0.42;
        const my = sy + (coreY - sy) * 0.42;
        synapse.setAttribute(
          "d",
          this._curvePath(sx, sy, mx, my, synBend, sign),
        );
      }
    }
  }

  destroy() {
    if (this._layoutRaf) {
      cancelAnimationFrame(this._layoutRaf);
      this._layoutRaf = 0;
    }
    if (this._packetTimer != null) {
      window.clearTimeout(this._packetTimer);
      this._packetTimer = null;
    }
    window.removeEventListener("resize", this._onResize);
    for (const satellite of this._satellites.values()) {
      satellite.destroy();
    }
    this._satellites.clear();
    this._links.clear();
    this._secondaryLinks.clear();
    this._synapseLinks.clear();
    this._packetSvg?.replaceChildren();
    this._field?.remove();
    this._field = null;
    this._svg = null;
    this._packetSvg = null;
    this._core = null;
  }
}
