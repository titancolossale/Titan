/** Titan Frontend V2 — DOM shell builder.
 * Phase 5 — Reference Layout Reconstruction.
 * Phase 5.1 — Immersive Neural Stage (presentation atmosphere only).
 * Phase 5.2 — Cinematic Living Intelligence (galaxies · voids · depth · idle life).
 * Phase 5.3 — Reference Scene Reconstruction (Core gravity · orbits · highways).
 * Phase 5.4 — Floating Cognitive Workspaces (lower dock cards only).
 * Phase 6 — Living Cognitive Orchestrator (right panel presentation only).
 * Phase 7 — Living Runtime Experience (atmosphere + local UI life only).
 * Phase 8 — Living Presence (entity presence · packets · atmosphere only).
 * Phase 9 — Cognitive Operating System (honest telemetry surfaces only).
 * Phase 10 — Canonical Final Reference (attached approved visual specification).
 * Visual authority: docs/design/screenshots/titan-final-canonical-reference.png
 * Region IDs preserved so all existing mounts reconnect unchanged.
 */

import { LAYER_IDS, REGION_IDS } from "./regions.js";

export class Shell {
  constructor() {
    /** @type {HTMLElement | null} */
    this.root = null;
    /** @type {Map<string, HTMLElement>} */
    this.elements = new Map();
  }

  /** @param {HTMLElement} mountPoint */
  mount(mountPoint) {
    mountPoint.innerHTML = "";
    mountPoint.className = "tdl-v2-root";
    mountPoint.dataset.phase = "10";
    mountPoint.dataset.layout = "canonical-final";
    mountPoint.dataset.canonical = "final";
    mountPoint.dataset.living = "10";
    mountPoint.dataset.cognitiveOs = "9";
    mountPoint.dataset.presence = "idle";
    mountPoint.dataset.runtime = "idle";

    const neuralLayer = this._createLayer(LAYER_IDS.neural, "tdl-v2-layer tdl-v2-layer--neural");
    neuralLayer.appendChild(this._createNeuralHost());

    const glowLayer = this._createLayer(LAYER_IDS.glow, "tdl-v2-layer tdl-v2-layer--glow");
    const glowAmbient = document.createElement("div");
    glowAmbient.className =
      "tdl-v2-glow-ambient tdl-v2-glow-ambient--living tdl-v2-glow-ambient--presence";
    glowAmbient.setAttribute("aria-hidden", "true");
    glowLayer.appendChild(glowAmbient);
    glowLayer.appendChild(this._createLivingComms());
    glowLayer.appendChild(this._createLivingPresence());

    const workspaceLayer = this._createLayer(LAYER_IDS.workspace, "tdl-v2-layer tdl-v2-layer--workspace");
    workspaceLayer.append(this._createCompositionFrame(), this._createContextPanelRegion());

    const floatingLayer = this._createLayer(LAYER_IDS.floating, "tdl-v2-layer tdl-v2-layer--floating");
    floatingLayer.id = "tdl-v2-cards-layer";
    this._mountFloatingRegions(floatingLayer);

    const overlayLayer = this._createLayer(LAYER_IDS.overlay, "tdl-v2-layer tdl-v2-layer--overlay");
    overlayLayer.id = "tdl-v2-overlay-layer";
    overlayLayer.dataset.active = "false";
    overlayLayer.appendChild(this._createSettingsOverlay());

    mountPoint.append(neuralLayer, glowLayer, workspaceLayer, floatingLayer, overlayLayer);
    this.root = mountPoint;
    this._indexElements(mountPoint);
  }

  unmount() {
    this.root?.replaceChildren();
    this.root = null;
    this.elements.clear();
  }

  /** @param {string} id */
  get(id) {
    return this.elements.get(id) ?? document.getElementById(id) ?? null;
  }

  _indexElements(root) {
    root.querySelectorAll("[id]").forEach((el) => {
      if (el.id) {
        this.elements.set(el.id, /** @type {HTMLElement} */ (el));
      }
    });
  }

  /** @param {string} id @param {string} className */
  _createLayer(id, className) {
    const layer = document.createElement("div");
    layer.id = id;
    layer.className = className;
    layer.setAttribute("aria-hidden", id === LAYER_IDS.neural ? "true" : "false");
    return layer;
  }

  /** Phase 7 — subtle neural communication markers (presentation only). */
  _createLivingComms() {
    const wrap = document.createElement("div");
    wrap.className = "tdl-v2-living-comms";
    wrap.setAttribute("aria-hidden", "true");
    wrap.dataset.role = "living-comms";
    for (let i = 0; i < 3; i += 1) {
      const node = document.createElement("span");
      node.className = "tdl-v2-living-comms__node";
      wrap.appendChild(node);
    }
    const orbit = document.createElement("div");
    orbit.className = "tdl-v2-living-comms__orbit";
    wrap.appendChild(orbit);
    return wrap;
  }

  /** Phase 8 — tiny floating particles + distant flashes (presentation only). */
  _createLivingPresence() {
    const wrap = document.createElement("div");
    wrap.className = "tdl-v2-living-presence";
    wrap.setAttribute("aria-hidden", "true");
    wrap.dataset.role = "living-presence";
    wrap.dataset.phase = "8";
    for (let i = 0; i < 8; i += 1) {
      const particle = document.createElement("span");
      particle.className = "tdl-v2-living-presence__particle";
      wrap.appendChild(particle);
    }
    for (let i = 0; i < 3; i += 1) {
      const flash = document.createElement("span");
      flash.className = "tdl-v2-living-presence__flash";
      wrap.appendChild(flash);
    }
    return wrap;
  }

  /**
   * Phase 5 composition frame:
   * LEFT sidebar | CENTER workspace (topbar + neural stage) | RIGHT orchestrator
   * BOTTOM floating dock (cards · lines · composer · telemetry)
   */
  _createCompositionFrame() {
    const composition = document.createElement("div");
    composition.id = "tdl-v2-composition";
    composition.className = "tdl-v2-composition";
    composition.dataset.phase = "5";
    composition.dataset.layout = "reference";

    const grid = document.createElement("div");
    grid.className = "tdl-v2-workspace-grid";
    grid.id = "tdl-v2-workspace-grid";
    grid.dataset.role = "command-columns";

    grid.appendChild(this._createSidebarRegion());
    grid.appendChild(this._createMainRegion());
    grid.appendChild(this._createOrchestratorRegion());

    composition.append(grid, this._createDockRegion());
    return composition;
  }

  _createNeuralHost() {
    const host = document.createElement("div");
    host.id = "tdl-v2-neural-host";
    host.className = "tdl-v2-neural-host";
    host.setAttribute("data-neural-ready", "pending");

    const camera = document.createElement("div");
    camera.className = "tdl-v2-neural-camera";
    camera.dataset.layer = "camera";

    const canvas = document.createElement("canvas");
    canvas.id = "tdl-v2-neural-canvas";
    canvas.className = "tdl-v2-neural-canvas";
    canvas.setAttribute("aria-hidden", "true");

    const depthLayers = document.createElement("div");
    depthLayers.className = "tdl-v2-neural-depth-layers";
    depthLayers.dataset.layer = "depth";
    for (const band of ["void", "far", "distant", "horizon"]) {
      const bandEl = document.createElement("div");
      bandEl.className = `tdl-v2-neural-depth-band tdl-v2-neural-depth-band--${band}`;
      bandEl.dataset.band = band;
      depthLayers.appendChild(bandEl);
    }

    const nodeLayer = document.createElement("div");
    nodeLayer.className = "tdl-v2-neural-node-layer";
    nodeLayer.dataset.layer = "nodes";

    const signalLayer = document.createElement("div");
    signalLayer.className = "tdl-v2-neural-signal-layer";
    signalLayer.dataset.layer = "signals";

    const ghostLayer = document.createElement("div");
    ghostLayer.className = "tdl-v2-neural-ghost-layer";
    ghostLayer.dataset.layer = "ghosts";

    const coreLayer = document.createElement("div");
    coreLayer.className = "tdl-v2-neural-core-layer";
    coreLayer.dataset.layer = "core";

    const vignette = document.createElement("div");
    vignette.className = "tdl-v2-neural-vignette";
    vignette.dataset.layer = "vignette";

    camera.append(canvas, depthLayers, nodeLayer, signalLayer, ghostLayer, coreLayer, vignette);

    const toolRegions = document.createElement("div");
    toolRegions.className = "tdl-v2-neural-tool-regions";
    toolRegions.id = "tdl-v2-neural-tool-regions";
    for (const region of ["browser", "tools", "obsidian", "trading", "calendar"]) {
      const anchor = document.createElement("div");
      anchor.className = `tdl-v2-neural-region-anchor tdl-v2-neural-region-anchor--${region}`;
      anchor.dataset.region = region;
      toolRegions.appendChild(anchor);
    }

    const memoryRegions = document.createElement("div");
    memoryRegions.className = "tdl-v2-neural-memory-regions";
    memoryRegions.id = "tdl-v2-neural-memory-regions";
    for (const region of ["memory", "communication"]) {
      const anchor = document.createElement("div");
      anchor.className = `tdl-v2-neural-region-anchor tdl-v2-neural-region-anchor--${region}`;
      anchor.dataset.region = region;
      memoryRegions.appendChild(anchor);
    }

    const focusRegions = document.createElement("div");
    focusRegions.className = "tdl-v2-neural-focus-regions";
    focusRegions.id = "tdl-v2-neural-focus-regions";
    for (const region of ["core", "planning"]) {
      const anchor = document.createElement("div");
      anchor.className = `tdl-v2-neural-region-anchor tdl-v2-neural-region-anchor--${region}`;
      anchor.dataset.region = region;
      focusRegions.appendChild(anchor);
    }

    host.append(camera, toolRegions, memoryRegions, focusRegions);
    return host;
  }

  /** @param {HTMLElement} layer */
  _mountFloatingRegions(layer) {
    const tools = document.createElement("div");
    tools.id = "tdl-v2-float-tools";
    tools.className = "tdl-v2-float-tools";
    tools.dataset.region = "floating-tools";

    const memory = document.createElement("div");
    memory.id = "tdl-v2-float-memory";
    memory.className = "tdl-v2-float-memory";
    memory.dataset.region = "floating-memory";

    const orchestrator = document.createElement("div");
    orchestrator.id = "tdl-v2-float-orchestrator";
    orchestrator.className = "tdl-v2-float-orchestrator";
    orchestrator.dataset.region = "floating-orchestrator";

    layer.append(tools, memory, orchestrator);
  }

  _createSidebarRegion() {
    const region = document.createElement("aside");
    region.id = REGION_IDS.sidebar;
    region.className =
      "tdl-v2-region tdl-v2-region--sidebar tdl-v2-glass-panel tdl-v2-stagger-sidebar";
    region.setAttribute("aria-label", "Navigation");
    region.dataset.region = "sidebar";
    region.dataset.column = "left";
    return region;
  }

  _createMainRegion() {
    const region = document.createElement("main");
    region.id = REGION_IDS.main;
    region.className = "tdl-v2-region tdl-v2-region--main tdl-v2-stagger-main";
    region.dataset.region = "main";
    region.dataset.column = "center";
    region.dataset.role = "workspace";

    const topbar = document.createElement("header");
    topbar.id = REGION_IDS.topbar;
    topbar.className = "tdl-v2-topbar";
    topbar.dataset.region = "topbar";

    const centerStack = document.createElement("div");
    centerStack.className = "tdl-v2-center-stack";
    centerStack.dataset.role = "neural-workspace";

    const moduleLabels = document.createElement("div");
    moduleLabels.id = "tdl-v2-neural-labels";
    moduleLabels.className = "tdl-v2-neural-labels";
    moduleLabels.setAttribute("role", "group");
    moduleLabels.setAttribute("aria-label", "Noyau neural Titan");

    const center = document.createElement("div");
    center.id = REGION_IDS.center;
    center.className = "tdl-v2-center-viewport";
    center.dataset.role = "stage";

    const floatingInCenter = document.createElement("div");
    floatingInCenter.className = "tdl-v2-floating-regions";
    floatingInCenter.id = "tdl-v2-center-floating";

    const slot = document.createElement("div");
    slot.id = REGION_IDS.centerSlot;
    slot.className = "tdl-v2-panel-slot";
    slot.dataset.slot = "center";
    slot.dataset.transition = "active";

    center.append(floatingInCenter, slot);
    centerStack.append(moduleLabels, center);
    region.append(topbar, centerStack);
    return region;
  }

  _createOrchestratorRegion() {
    const region = document.createElement("aside");
    region.id = REGION_IDS.orchestrator;
    region.className =
      "tdl-v2-region tdl-v2-region--orchestrator tdl-v2-glass-panel tdl-v2-stagger-orchestrator";
    region.setAttribute("aria-label", "Orchestrateur cognitif");
    region.dataset.region = "orchestrator";
    region.dataset.column = "right";
    region.dataset.role = "command-center";
    return region;
  }

  _createDockRegion() {
    const dock = document.createElement("footer");
    dock.id = REGION_IDS.dock;
    dock.className =
      "tdl-v2-region tdl-v2-region--dock tdl-v2-stagger-dock tdl-v2-dock--floating";
    dock.setAttribute("aria-label", "Commande et statut");
    dock.dataset.region = "dock";
    dock.dataset.role = "floating-workspaces";

    const cards = document.createElement("div");
    cards.id = REGION_IDS.dockStatusCards;
    cards.className = "tdl-v2-dock-status-cards";
    cards.dataset.role = "workspace-cards";

    const lines = document.createElement("div");
    lines.id = REGION_IDS.dockStatusLines;
    lines.className = "tdl-v2-dock-status-lines";
    lines.dataset.role = "status-lines";

    const composer = document.createElement("div");
    composer.id = REGION_IDS.dockComposer;
    composer.className = "tdl-v2-dock-composer";
    composer.dataset.region = "composer";

    const telemetry = document.createElement("div");
    telemetry.id = REGION_IDS.dockTelemetry;
    telemetry.className = "tdl-v2-dock-telemetry";
    telemetry.setAttribute("aria-label", "Télémétrie système");

    dock.append(cards, lines, composer, telemetry);
    return dock;
  }

  _createContextPanelRegion() {
    const panel = document.createElement("aside");
    panel.id = REGION_IDS.contextPanel;
    panel.className = "tdl-v2-context-panel tdl-v2-glass-panel";
    panel.setAttribute("aria-label", "Panneau de contexte");
    panel.dataset.region = "context-panel";
    panel.dataset.open = "false";
    panel.setAttribute("aria-hidden", "true");
    return panel;
  }

  _createSettingsOverlay() {
    const overlay = document.createElement("div");
    overlay.className = "tdl-v2-settings-overlay";
    overlay.id = "tdl-v2-settings-overlay";
    overlay.innerHTML = `
      <div class="tdl-v2-settings-card" role="dialog" aria-labelledby="tdl-v2-settings-title">
        <h2 class="tdl-v2-settings-card__title" id="tdl-v2-settings-title">Paramètres</h2>
        <p class="tdl-v2-settings-card__subtitle">Configuration Titan — interface V2.</p>
        <div class="tdl-v2-settings-section">
          <label class="tdl-v2-settings-auth__label" for="tdl-v2-visual-quality">Qualité visuelle</label>
          <select class="tdl-v2-settings-auth__input" id="tdl-v2-visual-quality" aria-label="Qualité visuelle">
            <option value="auto" selected>Auto</option>
            <option value="performance">Performance</option>
            <option value="balanced">Balanced</option>
            <option value="cinematic">Cinematic</option>
          </select>
          <p class="tdl-v2-settings-hint">Auto (défaut) — budgets conservateurs, bascule en urgence si le FPS reste bas.</p>
          <label class="tdl-v2-settings-check">
            <input type="checkbox" id="tdl-v2-reduce-motion-pref" />
            Réduire les animations
          </label>
          <label class="tdl-v2-settings-check tdl-v2-settings-check--debug" id="tdl-v2-fps-toggle-wrap" hidden>
            <input type="checkbox" id="tdl-v2-show-fps" />
            Afficher FPS (debug)
          </label>
        </div>
        <div class="tdl-v2-settings-auth">
          <label class="tdl-v2-settings-auth__label" for="tdl-v2-secret-key">Clé secrète</label>
          <input
            class="tdl-v2-settings-auth__input"
            id="tdl-v2-secret-key"
            type="password"
            placeholder="TITAN_WEB_SECRET_KEY"
            autocomplete="off"
            spellcheck="false"
          >
          <p class="tdl-v2-settings-auth__status" id="tdl-v2-auth-status"></p>
          <div class="tdl-v2-settings-auth__actions">
            <button type="button" class="tdl-v2-settings-auth__btn" id="tdl-v2-save-auth">Enregistrer</button>
            <button type="button" class="tdl-v2-settings-auth__btn tdl-v2-settings-auth__btn--ghost" id="tdl-v2-logout-auth">
              Déconnexion
            </button>
          </div>
        </div>
      </div>
    `;
    return overlay;
  }
}
