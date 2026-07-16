/** Titan Frontend V2 — Application bootstrap (Phase E10 Production). */

import { StateStore } from "./state-store.js";
import { Router } from "./router.js";
import { RenderPipeline } from "./render-pipeline.js";
import { CognitiveStateEngine } from "./cognitive-state-engine.js";
import { ExtensionRegistry } from "./extension-registry.js";
import { TITAN_PRODUCT_VERSION } from "./version.js";
import { LayoutEngine } from "../layout/layout-engine.js";
import { Shell } from "../layout/shell.js";
import { PanelRegistry } from "../panels/panel-registry.js";
import { PanelMount } from "../panels/panel-mount.js";
import { AnimationEngine } from "../animation/animation-engine.js";
import { ResponsiveEngine } from "../hooks/use-responsive.js";
import { registerPanelLayouts } from "../panels/layouts/index.js";
import { SidebarRegion } from "../sidebar/sidebar-region.js";
import { TopbarRegion } from "../center/topbar-region.js";
import { CenterRegion } from "../center/center-region.js";
import { OrchestratorRegion } from "../orchestrator/orchestrator-region.js";
import { ComposerRegion } from "../composer/composer-region.js";
import { StatusRegion } from "../status/status-region.js";
import { ContextPanelRegion } from "../panels/context-panel-region.js";
import { CardsLayer } from "../cards/cards-layer.js";
import { NeuralStage } from "../neural/stage.js";
import { ConversationManager } from "../conversation/conversation-manager.js";
import { attachBackendBridge } from "./backend-bridge.js";
import { wireVisualQualitySettings } from "./settings-performance.js";
import { wireSettingsAuthControls } from "./web-auth.js";

const NEURAL_BOOT_MS = 1000;

export class TitanAppV2 {
  constructor() {
    this._store = new StateStore({ systemVersion: TITAN_PRODUCT_VERSION });
    this._animationEngine = new AnimationEngine();
    this._shell = new Shell();
    this._layoutEngine = new LayoutEngine(this._shell);
    this._panelRegistry = new PanelRegistry();
    this._panelMount = new PanelMount(this._panelRegistry, this._animationEngine);
    this._router = new Router(this._store);
    this._responsive = new ResponsiveEngine(this._store);
    this._extensions = new ExtensionRegistry();
    this._renderPipeline = new RenderPipeline({
      store: this._store,
      layoutEngine: this._layoutEngine,
      panelMount: this._panelMount,
      animationEngine: this._animationEngine,
    });

    this._regions = {
      neural: new NeuralStage(this._shell),
      sidebar: new SidebarRegion(this._shell, this._store, this._router),
      topbar: new TopbarRegion(this._shell, this._store),
      center: new CenterRegion(this._shell, this._store),
      orchestrator: new OrchestratorRegion(this._shell, this._store),
      composer: new ComposerRegion(this._shell),
      status: new StatusRegion(this._shell, this._store),
      contextPanel: new ContextPanelRegion(this._shell, this._store),
      cards: new CardsLayer(this._shell),
    };

    /** @type {CognitiveStateEngine | null} */
    this.brain = null;
    /** @type {ConversationManager | null} */
    this.conversation = null;
    /** @type {ExtensionRegistry} */
    this.extensions = this._extensions;
    /** @type {boolean} */
    this._started = false;
  }

  async start() {
    // Idempotent boot — never double-bind chat listeners or EventSource.
    if (this._started) {
      this.conversation?.refreshDom?.();
      return;
    }
    this._started = true;

    registerPanelLayouts(this._panelRegistry);

    this._shell.mount(document.getElementById("titan-v2-root"));
    this._layoutEngine.init();
    wireSettingsAuthControls();

    for (const region of Object.values(this._regions)) {
      region.mount();
    }

    this._unwireQuality = wireVisualQualitySettings({
      store: this._store,
      neuralStage: this._regions.neural,
    });

    this.brain = new CognitiveStateEngine({
      neuralStage: this._regions.neural,
      store: this._store,
    });

    attachBackendBridge(this.brain, this._store);

    this._regions.sidebar.setBrain(this.brain);
    this._regions.composer.setBrain(this.brain);
    this._regions.composer.setNeuralStage?.(this._regions.neural);
    this._regions.center.setBrain(this.brain);
    this._regions.status.setBrain(this.brain);
    this._regions.orchestrator.setBrain(this.brain);
    this._regions.topbar.setBrain(this.brain);

    this.conversation = new ConversationManager({
      brain: this.brain,
      store: this._store,
      neural: this._regions.neural,
    });

    const reduced = this._store.getState().reducedMotion;
    this.brain.getConversationEngine()?.setReducedMotion(reduced);

    // Subscribe before first navigate so the chat panel mounts.
    this._responsive.start();
    this._renderPipeline.start();
    this._router.start();

    this._syncReducedMotionPref();
    this._reducedMotionMedia = window.matchMedia("(prefers-reduced-motion: reduce)");
    this._onReducedMotionChange = () => this._syncReducedMotionPref();
    this._reducedMotionMedia.addEventListener("change", this._onReducedMotionChange);

    this._regions.neural.setMasterState("BOOTING");
    setTimeout(() => {
      this._regions.neural.setMasterState("AWAKE");
      setTimeout(() => {
        this.brain?.setState("idle", { source: "boot", force: true });
        // SSE only after auth-gated boot (ensureAuthenticated already ran).
        this.brain?.connect?.();
      }, 400);
    }, NEURAL_BOOT_MS);

    this._router.navigate("chat", { replace: true });
    // Bind chat after navigate so #tdl-v2-chat-messages exists (or remounts soon).
    this.conversation.bindDom();
    // Expose for logout SSE teardown (no secrets).
    /** @type {any} */
    (window).__titanAppV2 = this;
    // Panel transition may be async — re-resolve container after paint.
    requestAnimationFrame(() => {
      this.conversation?.refreshDom?.();
      setTimeout(() => this.conversation?.refreshDom?.(), 400);
    });

    await this._renderPipeline.boot();

    for (const slot of ["voice", "trading", "browser", "obsidian", "calendar", "projects", "agents"]) {
      if (this._extensions.has(slot)) {
        this._extensions.invoke(slot, {
          app: this,
          brain: this.brain,
          store: this._store,
          shell: this._shell,
        });
      }
    }
  }

  _syncReducedMotionPref() {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this._animationEngine.setReducedMotion(reduced);
    this._store.setState({ reducedMotion: reduced });
    this.brain?.getConversationEngine()?.setReducedMotion(reduced);
  }

  destroy() {
    this._reducedMotionMedia?.removeEventListener("change", this._onReducedMotionChange);
    this._unwireQuality?.();
    this.conversation?.destroy();
    this.conversation = null;
    this.brain?.disconnect?.();
    this.brain?.destroyBridge?.();
    this.brain?.getToolEngine()?.destroy?.();
    this.brain?.getMemoryEngine()?.destroy?.();
    this.brain?.getConversationEngine()?.destroy?.();
    this._router.stop();
    this._responsive.stop();
    this._renderPipeline.destroy();
    this._animationEngine.destroy();
    this._regions.status.destroy?.();
    this._regions.sidebar.destroy?.();
    this._regions.center.destroy?.();
    this._regions.contextPanel.destroy?.();
    this._regions.neural.destroy?.();
    this._shell.unmount();
    this.brain = null;
    this._started = false;
  }
}
