/** Titan Neural Renderer V3 — Living neural civilization (Architecture Reconstruction). */

import { NEURAL_CONFIG } from "./config.js";
import { traceEdge, traceStrand } from "./bezier.js";
import { NODE_CLASSES } from "./node-classes.js";
import { rand } from "./utils.js";

export class NeuralRenderer {
  /**
   * @param {HTMLCanvasElement} canvas
   */
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = /** @type {CanvasRenderingContext2D} */ (canvas.getContext("2d", { alpha: false }));
    this.width = 0;
    this.height = 0;
    this.dpr = 1;
    this._time = 0;
    /** @type {Array<{ x: number, y: number, vx: number, vy: number, r: number, a: number }>} */
    this._dust = [];
    /** @type {Array<{ x: number, y: number, vx: number, vy: number, r: number, a: number, soft: boolean }>} */
    this._bokeh = [];
    /** Shared tissue stroke budget for the current frame. */
    this._tissueBudget = 0;
    /** @type {ReturnType<import("./quality-controller.js").QualityController["getBudgets"]> | null} */
    this._budgets = null;
    /** Reused per-frame band lists to avoid GC. */
    this._highwayFirst = [];
    this._bandStrands = [];
    this._maxEdgesDrawn = NEURAL_CONFIG.performance.maxEdgesDrawn;
    /** @type {HTMLCanvasElement | OffscreenCanvas | null} */
    this._staticCanvas = null;
    /** @type {CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D | null} */
    this._staticCtx = null;
    this._staticDirty = true;
    this._staticRebuildCount = 0;
    this._staticWidth = 0;
    this._staticHeight = 0;
    this._staticDpr = 0;
    this._staticRebuildPending = false;
    /** Reused foreground fog node list (avoids per-frame filter alloc). */
    this._fgNodeScratch = [];
    /** Cached vignette size key. */
    this._vignetteKey = "";
    this._lastDeltaMs = 16.7;
    this._farFieldPhase = 0;
  }

  /** Invalidate cached far-field neural layers (rebuild on next draw). */
  invalidateStaticCache() {
    this._staticDirty = true;
  }

  /**
   * Keep last valid cache visible while a quality/size rebuild is staged.
   */
  markStaticRebuildPending() {
    this._staticRebuildPending = true;
    this._staticDirty = true;
  }

  getStaticRebuildCount() {
    return this._staticRebuildCount;
  }

  isStaticCacheDirty() {
    return this._staticDirty;
  }

  /**
   * @param {number} width
   * @param {number} height
   * @param {ReturnType<import("./quality-controller.js").QualityController["getBudgets"]> | null} [budgets]
   * @param {{ invalidateStatic?: boolean, stageCache?: boolean }} [options]
   */
  resize(width, height, budgets = null, options = {}) {
    this.width = width;
    this.height = height;
    this._budgets = budgets;
    const maxDpr = budgets?.maxDpr ?? NEURAL_CONFIG.render.maxDpr;
    const nextDpr = Math.min(window.devicePixelRatio || 1, maxDpr);
    const dprChanged = Math.abs(nextDpr - this.dpr) > 0.01;
    this.dpr = nextDpr;
    this.canvas.width = Math.floor(width * this.dpr);
    this.canvas.height = Math.floor(height * this.dpr);
    this.canvas.style.width = `${width}px`;
    this.canvas.style.height = `${height}px`;
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this._rebuildDust(budgets?.dustCount);
    this._rebuildBokeh(budgets?.bokehCount);
    this._vignetteKey = "";
    if (options.invalidateStatic !== false || dprChanged) {
      if (options.stageCache) {
        this.markStaticRebuildPending();
      } else {
        this.invalidateStaticCache();
      }
    }
  }

  /** @param {number} [count] */
  _rebuildDust(count) {
    const atm = NEURAL_CONFIG.atmosphere || {};
    const n = count ?? atm.dustCount ?? 96;
    this._dust = [];
    for (let i = 0; i < n; i++) {
      this._dust.push({
        x: Math.random() * this.width,
        y: Math.random() * this.height,
        vx: rand(atm.dustSpeedMin ?? 0.008, atm.dustSpeedMax ?? 0.035) * (Math.random() > 0.5 ? 1 : -1),
        vy: rand(atm.dustSpeedMin ?? 0.008, atm.dustSpeedMax ?? 0.035) * (Math.random() > 0.5 ? 1 : -1),
        r: rand(0.35, 1.45),
        a: rand(0.06, atm.dustOpacity ?? 0.22),
      });
    }
  }

  /** @param {number} [count] */
  _rebuildBokeh(count) {
    const atm = NEURAL_CONFIG.atmosphere || {};
    const n = count ?? atm.foregroundBokehCount ?? 36;
    this._bokeh = [];
    for (let i = 0; i < n; i++) {
      this._bokeh.push({
        x: Math.random() * this.width,
        y: Math.random() * this.height,
        vx: rand(0.0015, 0.008) * (Math.random() > 0.5 ? 1 : -1),
        vy: rand(0.0015, 0.008) * (Math.random() > 0.5 ? 1 : -1),
        r: rand(1.6, 4.8),
        a: rand(0.04, 0.14),
        soft: Math.random() > 0.35,
      });
    }
  }

  /**
   * Minimal frame used when chat input needs main-thread priority.
   * Keeps last valid static blit + Core continuous (delta-time).
   * @param {import("./camera.js").NeuralCamera} camera
   * @param {import("./nodes.js").NeuralNodes} nodes
   * @param {import("./state.js").NeuralState} state
   * @param {ReturnType<import("./quality-controller.js").QualityController["getBudgets"]> | null} [budgets]
   * @param {number} [deltaMs]
   */
  renderLight(camera, nodes, state, budgets = null, deltaMs = 16.7) {
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;
    const COLORS = NEURAL_CONFIG.colors;
    const q = budgets ?? this._budgets;
    this._lastDeltaMs = deltaMs;
    this._time += deltaMs / 1000;
    // Prefer last valid cache while rebuild pending — never flash void.
    if (q?.useStaticCache && this._staticCanvas && (!this._staticDirty || this._staticRebuildPending)) {
      this._blitStatic(ctx);
    } else if (q?.useStaticCache && this._staticDirty && !this._staticCanvas) {
      this._rebuildStaticCache(camera, nodes, state, q, COLORS);
      this._blitStatic(ctx);
    } else {
      ctx.fillStyle = NEURAL_CONFIG.render.voidColor;
      ctx.fillRect(0, 0, w, h);
      this._drawAmbientGlow(ctx, w, h, state.getIntensity(), false, state.getVitality(), COLORS, 1);
    }
    this._drawNeuralCore(ctx, camera, nodes, state.getIntensity(), false, state.getVitality(), COLORS);
    this._drawVignette(ctx, w, h, COLORS);
  }

  /**
   * @param {number} cssW
   * @param {number} cssH
   * @param {number} dpr
   */
  _ensureStaticSurface(cssW, cssH, dpr) {
    const pw = Math.max(1, Math.floor(cssW * dpr));
    const ph = Math.max(1, Math.floor(cssH * dpr));
    if (
      this._staticCanvas &&
      this._staticWidth === pw &&
      this._staticHeight === ph &&
      this._staticDpr === dpr
    ) {
      return;
    }
    const canOffscreen = typeof OffscreenCanvas !== "undefined";
    this._staticCanvas = canOffscreen
      ? new OffscreenCanvas(pw, ph)
      : document.createElement("canvas");
    if (!canOffscreen) {
      /** @type {HTMLCanvasElement} */ (this._staticCanvas).width = pw;
      /** @type {HTMLCanvasElement} */ (this._staticCanvas).height = ph;
    }
    this._staticCtx = /** @type {CanvasRenderingContext2D} */ (
      this._staticCanvas.getContext("2d", { alpha: false })
    );
    this._staticWidth = pw;
    this._staticHeight = ph;
    this._staticDpr = dpr;
    this._staticDirty = true;
  }

  /**
   * Far-field architecture baked once — not redrawn every frame.
   * @param {import("./camera.js").NeuralCamera} camera
   * @param {import("./nodes.js").NeuralNodes} nodes
   * @param {import("./state.js").NeuralState} state
   * @param {object} q
   * @param {object} COLORS
   */
  _rebuildStaticCache(camera, nodes, state, q, COLORS) {
    this._ensureStaticSurface(this.width, this.height, this.dpr);
    const sctx = this._staticCtx;
    if (!sctx || !this._staticCanvas) return;

    sctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    const w = this.width;
    const h = this.height;
    const vitality = state.getVitality();
    const brightness = 1;
    const thinking = false;
    const prevBudgets = this._budgets;
    const prevTissue = this._tissueBudget;
    this._budgets = q;
    this._maxEdgesDrawn = q?.maxEdgesDrawn ?? this._maxEdgesDrawn;
    this._tissueBudget = q?.maxTissueDrawn ?? 800;

    sctx.fillStyle = NEURAL_CONFIG.render.voidColor;
    sctx.fillRect(0, 0, w, h);
    this._drawAmbientGlow(
      sctx,
      w,
      h,
      0.35,
      false,
      vitality,
      COLORS,
      Math.min(2, q?.ambientPatchCount ?? 2),
    );

    this._drawFieldTissue(sctx, camera, nodes, "veryFar", thinking, vitality, COLORS, brightness);
    this._drawFieldTissue(sctx, camera, nodes, "far", thinking, vitality, COLORS, brightness);
    this._drawFieldTissue(sctx, camera, nodes, "mid", thinking, vitality, COLORS, brightness);

    const layerCount = NEURAL_CONFIG.layers.length;
    const startLayer = 1;
    for (let layer = startLayer; layer < layerCount; layer++) {
      this._drawLayerEdges(sctx, camera, nodes, layer, thinking, COLORS, brightness);
    }
    this._drawFieldTissue(sctx, camera, nodes, "bridge", thinking, vitality, COLORS, brightness);
    for (let layer = startLayer; layer < layerCount; layer++) {
      this._drawLayerNodes(sctx, camera, nodes, layer, thinking, COLORS, brightness);
    }

    // Static dust speckles (no per-frame motion).
    if ((q?.dustCount ?? 0) > 0 && this._dust.length) {
      sctx.save();
      sctx.globalCompositeOperation = "lighter";
      for (let i = 0; i < this._dust.length; i++) {
        const d = this._dust[i];
        sctx.fillStyle = `rgba(248, 113, 113, ${d.a * 0.55})`;
        sctx.beginPath();
        sctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
        sctx.fill();
      }
      sctx.restore();
    }

    this._budgets = prevBudgets;
    this._tissueBudget = prevTissue;
    this._staticDirty = false;
    this._staticRebuildPending = false;
    this._staticRebuildCount += 1;
  }

  /** @param {CanvasRenderingContext2D} ctx */
  _blitStatic(ctx) {
    if (!this._staticCanvas) return;
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(/** @type {CanvasImageSource} */ (this._staticCanvas), 0, 0);
    ctx.restore();
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
  }

  /**
   * @param {import("./camera.js").NeuralCamera} camera
   * @param {import("./nodes.js").NeuralNodes} nodes
   * @param {import("./signals.js").NeuralSignals} signals
   * @param {import("./state.js").NeuralState} state
   * @param {import("./depth.js").DepthField | null} depthField
   * @param {import("./cognitive.js").CognitiveOverlay | null} cognitiveOverlay
   * @param {import("./ghosts.js").GhostLayer | null} ghostLayer
   * @param {ReturnType<import("./quality-controller.js").QualityController["getBudgets"]> | null} [budgets]
   * @param {number} [deltaMs]
   * @param {number} [frameIndex]
   */
  render(
    camera,
    nodes,
    signals,
    state,
    depthField,
    cognitiveOverlay,
    ghostLayer,
    budgets = null,
    deltaMs = 16.7,
    frameIndex = 0,
  ) {
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;
    const intensity = state.getIntensity();
    const rawThinking = state.isThinking();
    const q = budgets ?? this._budgets;
    this._budgets = q;
    // Thinking must not inflate decorative brightness when lightenThinking is on.
    const thinking = rawThinking && !q?.lightenThinking;
    const vitality = state.getVitality();
    const brightness = thinking ? NEURAL_CONFIG.render.thinkingBrightness : 1;
    const COLORS = NEURAL_CONFIG.colors;
    const recallDive = depthField?.getRecallDive?.() ?? 0;
    this._maxEdgesDrawn = q?.maxEdgesDrawn ?? NEURAL_CONFIG.performance.maxEdgesDrawn;

    // Delta-time clock — never advance by fixed 1/60 per paint.
    this._lastDeltaMs = deltaMs;
    this._time += Math.max(0, deltaMs) / 1000;
    this._tissueBudget = q?.maxTissueDrawn ?? NEURAL_CONFIG.performance.maxTissueDrawn ?? 1600;

    const useCache = Boolean(q?.useStaticCache);
    const farCadence = Math.max(1, q?.farFieldCadence ?? 1);
    const farDue = frameIndex % farCadence === 0;
    if (useCache) {
      if ((this._staticDirty || !this._staticCanvas) && (!this._staticRebuildPending || farDue || !this._staticCanvas)) {
        this._rebuildStaticCache(camera, nodes, state, q, COLORS);
      }
      if (this._staticCanvas) {
        this._blitStatic(ctx);
      }
    } else {
      ctx.fillStyle = NEURAL_CONFIG.render.voidColor;
      ctx.fillRect(0, 0, w, h);

      this._drawAmbientGlow(
        ctx,
        w,
        h,
        intensity,
        thinking,
        vitality,
        COLORS,
        q?.ambientPatchCount ?? 6,
      );

      this._drawFieldTissue(ctx, camera, nodes, "veryFar", thinking, vitality, COLORS, brightness);
      this._drawFieldTissue(ctx, camera, nodes, "far", thinking, vitality, COLORS, brightness);
      this._drawFieldTissue(ctx, camera, nodes, "mid", thinking, vitality, COLORS, brightness);

      const layerCount = NEURAL_CONFIG.layers.length;
      const startLayer = q?.softHaloFarLayers === false ? 1 : 0;
      for (let layer = startLayer; layer < layerCount; layer++) {
        this._drawLayerEdges(ctx, camera, nodes, layer, thinking, COLORS, brightness);
      }

      this._drawFieldTissue(ctx, camera, nodes, "bridge", thinking, vitality, COLORS, brightness);
      this._drawFieldTissue(ctx, camera, nodes, "near", thinking, vitality, COLORS, brightness);
      this._drawFieldTissue(ctx, camera, nodes, "foreground", thinking, vitality, COLORS, brightness);

      for (let layer = startLayer; layer < layerCount; layer++) {
        this._drawLayerNodes(ctx, camera, nodes, layer, thinking, COLORS, brightness);
      }
    }

    // Dynamic foreground — Core, live signals, restrained pulse.
    if (useCache) {
      this._drawFieldTissue(ctx, camera, nodes, "near", thinking, vitality, COLORS, brightness * 0.85);
      this._drawFieldTissue(
        ctx,
        camera,
        nodes,
        "foreground",
        thinking,
        vitality,
        COLORS,
        brightness * 0.85,
      );
    }

    this._drawNeuralCore(ctx, camera, nodes, intensity, rawThinking, vitality, COLORS);

    if (ghostLayer?.isActive() && !q?.emergency && !q?.chatPending) {
      this._drawGhosts(ctx, camera, ghostLayer, COLORS);
    }

    if (signals) {
      this._drawSignalTrails(ctx, camera, signals, COLORS, thinking);
      this._drawSignalParticles(ctx, camera, signals, COLORS, thinking);
    }

    if (cognitiveOverlay && !q?.emergency) {
      cognitiveOverlay.draw(ctx, w, h, state.getCognitiveSignature(), COLORS);
    }

    if (!useCache && (q?.dustCount ?? 0) > 0) {
      this._drawDust(ctx, thinking, vitality, COLORS);
    }
    this._drawCoreFrontTissue(ctx, camera, nodes, intensity, thinking, vitality, COLORS);
    if (q?.enableBokeh) {
      this._drawForegroundBokeh(ctx, thinking, vitality, COLORS);
    }
    if (q?.enableVolumetricHaze) {
      this._drawVolumetricHaze(ctx, w, h, intensity, thinking, COLORS, q?.hazePatchCount);
    }
    if (q?.enableAtmosphericFog) {
      this._drawAtmosphericFog(ctx, w, h, intensity, thinking, COLORS, q?.fogPatchCount);
    }
    if (q?.enableLightShafts) {
      this._drawLightShafts(ctx, w, h, intensity, thinking, vitality, COLORS);
    }
    if (!q?.emergency) {
      this._drawDepthFog(ctx, w, h, intensity, recallDive);
    }
    if (q?.enableForegroundFog) {
      this._drawForegroundFog(ctx, camera, nodes, w, h);
    }
    if (q?.enableBloom) {
      this._drawRestrainedBloom(ctx, camera, nodes, thinking, COLORS, q?.bloomSpotCount);
    }
    if (q?.enableLensDiffusion) {
      this._drawLensDiffusion(ctx, w, h, intensity, COLORS);
    }
    this._drawVignette(ctx, w, h, COLORS);
  }

  _layerCfg(layerIdx) {
    return NEURAL_CONFIG.layers[layerIdx] ?? NEURAL_CONFIG.layers[0];
  }

  _screenPoint(camera, node, padX, padY) {
    return this._screenXY(camera, node.x, node.y, node.parallax, padX, padY);
  }

  /**
   * Project an arbitrary world point to screen space using the same transform as
   * node endpoints. Used to project edge control points so Bezier axons stay
   * anchored to their nodes.
   */
  _screenXY(camera, wx, wy, parallax, padX, padY) {
    const screen = camera.worldToScreen(wx, wy, parallax);
    screen.x -= padX;
    screen.y -= padY;
    return screen;
  }

  _edgeControls(camera, edge, na, nb, padX, padY) {
    if (edge.cp1x == null || edge.cp2x == null) return null;
    return {
      c1: this._screenXY(camera, edge.cp1x, edge.cp1y, na.parallax, padX, padY),
      c2: this._screenXY(camera, edge.cp2x, edge.cp2y, nb.parallax, padX, padY),
    };
  }

  _redColor(node, COLORS, glow) {
    const hue = node.redHue ?? 0.85;
    const bright = node.brightness ?? 1;
    const a = Math.min(glow * bright, 0.98);
    // Identity nucleus — white-hot peak (layered shells drawn separately).
    if (node.isCenter) return `${COLORS.whiteCore}${Math.min(a * 0.85, 0.9)})`;
    if (hue > 0.88) return `${COLORS.redHot}${Math.min(a, 0.92)})`;
    if (hue > 0.72) return `${COLORS.redGlow}${Math.min(a, 0.88)})`;
    if (hue > 0.58) return `${COLORS.redCrimson}${Math.min(a, 0.78)})`;
    return `${COLORS.redDeep}${Math.min(a * 0.72, 0.55)})`;
  }

  _drawAmbientGlow(ctx, w, h, intensity, thinking, vitality, COLORS, patchLimit = 6) {
    // Multiple uneven haze patches — never a single circular spotlight / brain object.
    const strength =
      (NEURAL_CONFIG.atmosphere?.ambientGlowStrength ?? 0.028) *
      (0.5 + vitality * 0.35 + intensity * 0.2);
    const asym = NEURAL_CONFIG.core?.asymmetry || {};
    const patches = [
      { x: 0.5 + (asym.x ?? -0.14) * 0.04, y: 0.46 + (asym.y ?? 0.09) * 0.04, r: 0.62, a: 0.58 },
      { x: 0.26, y: 0.3, r: 0.4, a: 0.24 },
      { x: 0.74, y: 0.58, r: 0.44, a: 0.22 },
      { x: 0.16, y: 0.7, r: 0.34, a: 0.15 },
      { x: 0.84, y: 0.26, r: 0.32, a: 0.13 },
      { x: 0.58, y: 0.22, r: 0.28, a: 0.1 },
    ];
    const limit = Math.max(1, Math.min(patches.length, patchLimit));
    for (let i = 0; i < limit; i++) {
      const p = patches[i];
      const cx = w * p.x;
      const cy = h * p.y;
      const r = Math.min(w, h) * p.r * (thinking ? 1.08 : 1);
      const grad = ctx.createRadialGradient(cx, cy, r * 0.08, cx, cy, r);
      grad.addColorStop(0, `${COLORS.hazeRed}${strength * p.a})`);
      grad.addColorStop(0.45, `${COLORS.hazeRed}${strength * p.a * 0.45})`);
      grad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);
    }
  }

  _drawLayerEdges(ctx, camera, nodes, layer, thinking, COLORS, brightness) {
    const padX = NEURAL_CONFIG.world.padding * camera.width;
    const padY = NEURAL_CONFIG.world.padding * camera.height;
    const layerCfg = this._layerCfg(layer);
    const depthFade = layerCfg.fogDim ?? 0.5;
    const maxDraw = this._maxEdgesDrawn;
    const markIntersections = this._budgets?.intersectionMarks !== false;
    let drawn = 0;

    ctx.save();
    ctx.globalCompositeOperation = "lighter";

    for (const e of nodes.edges) {
      if (drawn >= maxDraw) break;
      if (!e.visible || e.opacity < 0.008) continue;
      const edgeLayer = Math.round(e.layerMix);
      if (edgeLayer !== layer) continue;

      const na = nodes.nodes[e.a];
      const nb = nodes.nodes[e.b];
      if (!na || !nb) continue;

      // Skip edges fully outside the viewport (cheap AABB).
      const pa = this._screenPoint(camera, na, padX, padY);
      const pb = this._screenPoint(camera, nb, padX, padY);
      if (
        (pa.x < -40 && pb.x < -40) ||
        (pa.x > this.width + 40 && pb.x > this.width + 40) ||
        (pa.y < -40 && pb.y < -40) ||
        (pa.y > this.height + 40 && pb.y > this.height + 40)
      ) {
        continue;
      }

      let alpha = (e.opacity * (e.edgeOpacity ?? 0.7) + e.glow * 0.42) * depthFade * brightness;
      if (e.signalProgress >= 0) {
        alpha += (1 - Math.min(1, e.signalProgress)) * 0.38 * depthFade;
      }
      // Core edges are drawn lightly here; the consciousness pass owns their glow.
      if (e.isCore) alpha *= 0.72;
      if (e.isDendrite) alpha *= 0.7;
      alpha = Math.min(alpha, thinking ? 0.78 : 0.62);
      if (alpha < 0.006) continue;

      const colorBase = COLORS[e.signalColorKey] ?? COLORS.redGlow;
      const lineW = (e.width ?? 0.55) * (0.42 + depthFade * 0.85) * (e.isCore ? 1.05 : e.isDendrite ? 0.68 : 1);
      const controls = this._edgeControls(camera, e, na, nb, padX, padY);

      ctx.beginPath();
      traceEdge(ctx, pa, pb, controls?.c1, controls?.c2);
      ctx.strokeStyle = `${colorBase}${alpha})`;
      ctx.lineWidth = lineW;
      ctx.stroke();

      // Brighter synapses at active / near-node intersections.
      const intersectBoost = NEURAL_CONFIG.render.intersectionBoost ?? 0.5;
      if (markIntersections && (e.glow > 0.18 || e.signalProgress >= 0) && !e.isDendrite) {
        ctx.beginPath();
        ctx.arc(pa.x, pa.y, 1.1 + e.glow * 1.6, 0, Math.PI * 2);
        ctx.fillStyle = `${COLORS.redHot}${Math.min(alpha * intersectBoost * 0.55, 0.45)})`;
        ctx.fill();
        ctx.beginPath();
        ctx.arc(pb.x, pb.y, 1.1 + e.glow * 1.6, 0, Math.PI * 2);
        ctx.fillStyle = `${COLORS.redHot}${Math.min(alpha * intersectBoost * 0.55, 0.45)})`;
        ctx.fill();
      }

      if (alpha > 0.38 && layer >= NEURAL_CONFIG.layers.length - 1 && !e.isDendrite && !e.isCore) {
        ctx.strokeStyle = `${COLORS.redHot}${alpha * 0.08})`;
        ctx.lineWidth = lineW + 0.45;
        ctx.stroke();
      }

      drawn++;
    }

    ctx.restore();
  }

  _drawLayerNodes(ctx, camera, nodes, layer, thinking, COLORS, brightness) {
    const padX = NEURAL_CONFIG.world.padding * camera.width;
    const padY = NEURAL_CONFIG.world.padding * camera.height;
    const layerCfg = this._layerCfg(layer);
    const depthFade = layerCfg.fogDim ?? 0.5;
    const isForeground = layer >= NEURAL_CONFIG.layers.length - 1;
    const softHalo =
      (this._budgets?.softHaloFarLayers !== false && layer <= 2) ||
      (this._budgets?.nodeHaloEnabled !== false && layer >= 2);
    const halosEnabled = this._budgets?.nodeHaloEnabled !== false;

    const layerNodes = nodes.getNodesForLayer?.(layer) ??
      nodes.nodes.filter((n) => n.layer === layer && !n.isCenter);

    for (const n of layerNodes) {
      const screen = this._screenPoint(camera, n, padX, padY);
      if (
        screen.x < -20 ||
        screen.y < -20 ||
        screen.x > this.width + 20 ||
        screen.y > this.height + 20
      ) {
        continue;
      }
      const classBoost =
        n.nodeClass === NODE_CLASSES.CORE ? 1.4 : n.nodeClass === NODE_CLASSES.MEMORY ? 1.15 : n.isHub ? 1.28 : 1;
      const glow =
        (n.opacity * (thinking && isForeground ? 1.28 : 1) * depthFade + n.glow * 0.58) *
        classBoost *
        brightness *
        (n.brightness ?? 1);

      if (halosEnabled && glow > 0.12 && (layer >= 2 || softHalo)) {
        const haloR = n.radius * (softHalo ? 5.5 : n.isHub ? 4.4 : 2.9) * depthFade;
        ctx.beginPath();
        ctx.arc(screen.x, screen.y, haloR, 0, Math.PI * 2);
        ctx.fillStyle = `${COLORS.redGlow}${glow * (softHalo ? 0.045 : 0.07)})`;
        ctx.fill();
      }

      if (n.activation > 0.05) {
        const actColor = COLORS[n.signalColorKey] ?? COLORS.redGlow;
        ctx.beginPath();
        ctx.arc(screen.x, screen.y, n.radius * (1.8 + n.activation * 1.2) * depthFade, 0, Math.PI * 2);
        ctx.fillStyle = `${actColor}${n.activation * 0.24})`;
        ctx.fill();
      }

      const r = n.radius * depthFade * (0.88 + n.energy * 0.18);
      ctx.beginPath();
      ctx.arc(screen.x, screen.y, r, 0, Math.PI * 2);
      ctx.fillStyle = this._redColor(n, COLORS, Math.min(glow, 0.95));
      ctx.fill();

      if (isForeground && glow > 0.35) {
        ctx.beginPath();
        ctx.arc(screen.x, screen.y, r * 0.42, 0, Math.PI * 2);
        ctx.fillStyle = `${COLORS.whiteDim}${Math.min(glow * 0.35, 0.55)})`;
        ctx.fill();
      }
    }
  }

  _drawNeuralCore(ctx, camera, nodes, intensity, thinking, vitality, COLORS) {
    // Titan Core Identity — layered living nucleus inside continuous tissue.
    // White-hot heart · plasma shell · darker falloff · soft atmosphere.
    const padX = NEURAL_CONFIG.world.padding * camera.width;
    const padY = NEURAL_CONFIG.world.padding * camera.height;
    const core = nodes.core;
    const pulse = core.pulse;
    const drawStrength = NEURAL_CONFIG.render.coreDrawStrength ?? 1;
    const breathe = 0.94 + pulse * 0.045 + vitality * 0.03;
    const coreIntensity =
      ((thinking ? 0.88 : 0.7) * breathe + intensity * 0.16) * drawStrength;

    const asym = NEURAL_CONFIG.core?.asymmetry || {};
    const focusScreen = camera.worldToScreen(
      core.cx + (asym.x ?? 0) * 8,
      core.cy + (asym.y ?? 0) * 8,
      1,
    );
    const focusCx = focusScreen.x - padX;
    const focusCy = focusScreen.y - padY;

    // Local contrast: slightly darken the surrounding field so Core owns the eye.
    this._drawCoreFieldDarken(ctx, focusCx, focusCy, breathe);

    ctx.save();
    ctx.globalCompositeOperation = "lighter";

    // 0) Soft layered white-red aura — volumetric lighting stack, not an orb plate.
    this._drawCoreAura(ctx, camera, core, padX, padY, breathe, coreIntensity, COLORS, thinking);

    // 1) Deep → mid → bright tissue (front tier drawn later for near-field depth).
    this._drawCoreTissue(ctx, camera, core, padX, padY, breathe, coreIntensity, COLORS);

    // 2) Short local hub synapses — biological bridges only.
    for (const edgeIdx of core.branchEdgeIndices) {
      const e = nodes.edges[edgeIdx];
      if (!e?.visible || e.opacity < 0.03) continue;
      const na = nodes.nodes[e.a];
      const nb = nodes.nodes[e.b];
      if (!na || !nb) continue;
      const pa = this._screenPoint(camera, na, padX, padY);
      const pb = this._screenPoint(camera, nb, padX, padY);
      const controls = this._edgeControls(camera, e, na, nb, padX, padY);
      const alpha = Math.min((e.opacity * 0.85 + e.glow * 0.28) * breathe * 0.82, 0.62);
      ctx.beginPath();
      traceEdge(ctx, pa, pb, controls?.c1, controls?.c2);
      ctx.strokeStyle = `${COLORS.redGlow}${alpha})`;
      ctx.lineWidth = (e.width ?? 0.4) * (0.95 + pulse * 0.12);
      ctx.stroke();
    }

    // 3) Microscopic neurons — collective brightness without a light source.
    this._drawMicroNeurons(ctx, camera, core, padX, padY, breathe, coreIntensity, COLORS, thinking);

    // 4) Local energy packets — tight orbits + near-Core filament sparks.
    this._drawCoreEnergyPackets(ctx, camera, core, padX, padY, breathe, coreIntensity, COLORS);

    // 5) Hub points — tiny neurons blended into tissue.
    for (const hubId of core.hubNodeIds) {
      const n = nodes.nodes[hubId];
      if (!n || n.isCenter) continue;
      const screen = this._screenPoint(camera, n, padX, padY);
      const glow = (n.glow + n.activation * 0.32 + pulse * 0.12) * (thinking ? 1.12 : 0.82);
      ctx.beginPath();
      ctx.arc(screen.x, screen.y, n.radius * 1.85, 0, Math.PI * 2);
      ctx.fillStyle = `${COLORS.redGlow}${Math.min(glow * 0.08, 0.16)})`;
      ctx.fill();
      ctx.beginPath();
      ctx.arc(screen.x, screen.y, n.radius * (0.78 + pulse * 0.06), 0, Math.PI * 2);
      ctx.fillStyle = `${COLORS.redHot}${Math.min(glow * 0.58, 0.68)})`;
      ctx.fill();
      if (glow > 0.62) {
        ctx.beginPath();
        ctx.arc(screen.x, screen.y, n.radius * 0.24, 0, Math.PI * 2);
        ctx.fillStyle = `${COLORS.whiteDim}${Math.min(glow * 0.12, 0.22)})`;
        ctx.fill();
      }
    }

    // 6) Layered identity nucleus — brightest object in the application.
    this._drawCoreNucleus(ctx, focusCx, focusCy, pulse, breathe, coreIntensity, COLORS, thinking);

    const centerNode = core.centerNodeId != null ? nodes.nodes[core.centerNodeId] : null;
    if (centerNode) {
      centerNode.glow = Math.max(centerNode.glow, coreIntensity * 1.15);
    }

    ctx.restore();
  }

  /**
   * Mid-ring darkening around Core — surrounding field slightly darker so the
   * nucleus becomes the undeniable focal lock.
   */
  _drawCoreFieldDarken(ctx, cx, cy, breathe) {
    const strength = NEURAL_CONFIG.core?.fieldDarkenStrength ?? 0.14;
    if (strength < 0.02) return;
    const base = Math.min(this.width, this.height);
    const r = base * 0.55 * (0.98 + (breathe - 1) * 0.4);
    ctx.save();
    ctx.globalCompositeOperation = "source-over";
    const grad = ctx.createRadialGradient(cx, cy, r * 0.12, cx, cy, r);
    grad.addColorStop(0, "rgba(0, 0, 0, 0)");
    grad.addColorStop(0.28, "rgba(0, 0, 0, " + strength * 0.35 + ")");
    grad.addColorStop(0.55, "rgba(0, 0, 0, " + strength * 0.85 + ")");
    grad.addColorStop(0.78, "rgba(0, 0, 0, " + strength * 0.4 + ")");
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.ellipse(cx, cy, r * 1.25, r * 0.82, -0.1, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  /**
   * Layered Titan Core nucleus — conscious center, not a particle emitter.
   * Soft elliptic stack: white-hot · bright red plasma · darker shell.
   */
  _drawCoreNucleus(ctx, cx, cy, pulse, breathe, coreIntensity, COLORS, thinking) {
    const base = Math.min(this.width, this.height);
    const life = coreIntensity * (thinking ? 1.12 : 1);
    // Almost imperceptible breath — expand / contract / light.
    const breathScale = 0.97 + (pulse - 0.78) * 0.55 + breathe * 0.02;
    const whiteR = base * 0.0095 * breathScale * (NEURAL_CONFIG.core?.whiteCenterRadius ?? 1);

    // Darker surrounding shell — absolute scale held while nucleus shrinks.
    // Plasma/shell multipliers offset whiteCenterRadius balance (~0.8 vs 1.15).
    const shellScale = 1.44;
    ctx.save();
    ctx.globalCompositeOperation = "source-over";
    const shell = ctx.createRadialGradient(
      cx,
      cy,
      whiteR * 3.5 * shellScale,
      cx,
      cy,
      whiteR * 12 * shellScale,
    );
    shell.addColorStop(0, "rgba(0, 0, 0, 0)");
    shell.addColorStop(0.25, "rgba(25, 2, 4, 0.32)");
    shell.addColorStop(0.55, "rgba(8, 0, 1, 0.36)");
    shell.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = shell;
    ctx.beginPath();
    ctx.ellipse(cx, cy, whiteR * 13 * shellScale, whiteR * 8.5 * shellScale, -0.12, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
    ctx.globalCompositeOperation = "lighter";

    // Soft atmospheric glow — low exposure so tissue near Core stays readable
    ctx.globalCompositeOperation = "lighter";
    const atmos = ctx.createRadialGradient(
      cx,
      cy,
      whiteR * 0.4 * shellScale,
      cx,
      cy,
      whiteR * 11 * shellScale,
    );
    atmos.addColorStop(0, `${COLORS.redHot}${0.08 * life})`);
    atmos.addColorStop(0.35, `${COLORS.redGlow}${0.045 * life})`);
    atmos.addColorStop(0.7, `${COLORS.redCore}${0.018 * life})`);
    atmos.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = atmos;
    ctx.beginPath();
    ctx.ellipse(
      cx,
      cy,
      whiteR * 12 * shellScale,
      whiteR * 7.8 * shellScale,
      -0.1,
      0,
      Math.PI * 2,
    );
    ctx.fill();

    // Cut additive wash just outside the nucleus so plasma can read as red.
    ctx.globalCompositeOperation = "source-over";
    const cut = ctx.createRadialGradient(cx, cy, whiteR * 1.2, cx, cy, whiteR * 4.2 * shellScale);
    cut.addColorStop(0, "rgba(0, 0, 0, 0)");
    cut.addColorStop(0.35, "rgba(12, 0, 1, 0.22)");
    cut.addColorStop(0.7, "rgba(6, 0, 1, 0.12)");
    cut.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = cut;
    ctx.beginPath();
    ctx.ellipse(cx, cy, whiteR * 4.4 * shellScale, whiteR * 2.9 * shellScale, -0.08, 0, Math.PI * 2);
    ctx.fill();

    // Bright red plasma shell — source-over so it won't bleach into white
    const plasma = ctx.createRadialGradient(
      cx,
      cy,
      whiteR * 0.85,
      cx,
      cy,
      whiteR * 5.2 * shellScale,
    );
    plasma.addColorStop(0, "rgba(255, 110, 90, " + 0.55 * life + ")");
    plasma.addColorStop(0.28, `${COLORS.redHot}${0.72 * life})`);
    plasma.addColorStop(0.55, `${COLORS.redGlow}${0.48 * life})`);
    plasma.addColorStop(0.82, `${COLORS.redCrimson}${0.22 * life})`);
    plasma.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = plasma;
    ctx.beginPath();
    ctx.ellipse(
      cx,
      cy,
      whiteR * 5.6 * shellScale,
      whiteR * 3.7 * shellScale,
      -0.08,
      0,
      Math.PI * 2,
    );
    ctx.fill();

    // White-hot nucleus — compact peak, controlled exposure (source-over)
    const nucleus = ctx.createRadialGradient(cx, cy, 0, cx, cy, whiteR * 1.85);
    nucleus.addColorStop(0, "rgba(255, 255, 255, " + Math.min(0.92, 0.78 + pulse * 0.08) + ")");
    nucleus.addColorStop(0.3, "rgba(255, 245, 240, " + 0.7 * life + ")");
    nucleus.addColorStop(0.55, `${COLORS.whiteDim}${0.38 * life})`);
    nucleus.addColorStop(0.78, `${COLORS.redHot}${0.5 * life})`);
    nucleus.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = nucleus;
    ctx.beginPath();
    ctx.ellipse(cx, cy, whiteR * 1.9, whiteR * 1.35, -0.06, 0, Math.PI * 2);
    ctx.fill();

    // Micro light pulse at the absolute center
    const pin = whiteR * (0.32 + pulse * 0.05);
    ctx.beginPath();
    ctx.arc(cx, cy, pin, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255, 255, 255, " + (0.82 + pulse * 0.05) + ")";
    ctx.fill();
    ctx.globalCompositeOperation = "lighter";
  }

  /**
   * Soft layered aura around Titan Core — volumetric lighting stack:
   * atmospheric glow → darker surround → bright red plasma → white-hot peak.
   * Elliptic / asymmetric — not a hard circular ornament.
   */
  _drawCoreAura(ctx, camera, core, padX, padY, breathe, coreIntensity, COLORS, thinking) {
    const asym = NEURAL_CONFIG.core?.asymmetry || {};
    const outerMult = NEURAL_CONFIG.core?.outerGlowMult ?? 0.9;
    const screen = camera.worldToScreen(
      core.cx + (asym.x ?? 0) * 8,
      core.cy + (asym.y ?? 0) * 8,
      1,
    );
    const cx = screen.x - padX;
    const cy = screen.y - padY;
    const base = Math.min(this.width, this.height);
    const life = coreIntensity * breathe * (thinking ? 1.14 : 1);
    // Subtle breath scale on the entire aura stack.
    const breathScale = 0.97 + (core.pulse - 0.78) * 0.35;
    // Elliptic asymmetric layers — red body first; white peak stays tight.
    const layers = [
      { rx: 0.48, ry: 0.32, a: 0.045 * outerMult, hue: "redDeep", rot: -0.18 },
      { rx: 0.32, ry: 0.21, a: 0.09 * outerMult, hue: "redCore", rot: -0.14 },
      { rx: 0.2, ry: 0.13, a: 0.16 * outerMult, hue: "redGlow", rot: -0.12 },
      { rx: 0.11, ry: 0.07, a: 0.26 * outerMult, hue: "redHot", rot: -0.1 },
      { rx: 0.04, ry: 0.026, a: 0.2 * outerMult, hue: "whiteDim", rot: -0.08 },
      { rx: 0.015, ry: 0.01, a: 0.28 * outerMult, hue: "whiteCore", rot: -0.06 },
    ];
    for (const L of layers) {
      const rx = base * L.rx * breathScale * (0.94 + breathe * 0.06);
      const ry = base * L.ry * breathScale * (0.94 + breathe * 0.06);
      const ox = (asym.x ?? 0) * base * 0.012;
      const oy = (asym.y ?? 0) * base * 0.01;
      const grad = ctx.createRadialGradient(
        cx + ox,
        cy + oy,
        Math.min(rx, ry) * 0.04,
        cx + ox,
        cy + oy,
        Math.max(rx, ry),
      );
      const color = COLORS[L.hue] ?? COLORS.redGlow;
      grad.addColorStop(0, `${color}${L.a * life})`);
      grad.addColorStop(0.38, `${color}${L.a * life * 0.42})`);
      grad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(L.rot);
      ctx.scale(1.32, 0.72);
      ctx.translate(-cx, -cy);
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    // Soft dark outer shell — deep tissue falloff into the void (source-over).
    ctx.save();
    ctx.globalCompositeOperation = "source-over";
    const darkR = base * 0.68 * breathScale;
    const dark = ctx.createRadialGradient(cx, cy, base * 0.18, cx, cy, darkR);
    dark.addColorStop(0, "rgba(0, 0, 0, 0)");
    dark.addColorStop(0.5, "rgba(0, 0, 0, 0.06)");
    dark.addColorStop(1, "rgba(0, 0, 0, 0.18)");
    ctx.fillStyle = dark;
    ctx.beginPath();
    ctx.ellipse(cx, cy, darkR * 1.15, darkR * 0.78, -0.12, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
    ctx.globalCompositeOperation = "lighter";
  }

  /**
   * Draw atmospheric field tissue for a depth band (far / mid / near / bridge).
   */
  _drawFieldTissue(ctx, camera, nodes, band, thinking, vitality, COLORS, brightness) {
    const tissue = nodes.core?.fieldTissue;
    if (!tissue?.length || this._tissueBudget <= 0) return;

    const padX = NEURAL_CONFIG.world.padding * camera.width;
    const padY = NEURAL_CONFIG.world.padding * camera.height;
    const fades = NEURAL_CONFIG.core?.bandFade || {};
    const bandFade =
      band === "veryFar"
        ? fades.veryFar ?? 0.12
        : band === "far"
          ? fades.far ?? 0.26
          : band === "mid"
            ? fades.mid ?? 0.68
            : band === "bridge"
              ? fades.bridge ?? 0.78
              : band === "foreground"
                ? fades.foreground ?? 1.32
                : fades.near ?? 1.15;
    const life = 0.85 + vitality * 0.22 + (thinking ? 0.1 : 0);
    const highwaySheath = NEURAL_CONFIG.render?.highwaySheath ?? 0.14;
    const highwayGravity = NEURAL_CONFIG.render?.highwayCoreGravity ?? 0.45;
    const densScale =
      Math.min(camera.width, camera.height) * (NEURAL_CONFIG.core?.clusterRadiusRatio ?? 0.36);
    const coreCx = nodes.core?.cx ?? 0;
    const coreCy = nodes.core?.cy ?? 0;

    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    // Depth layer contrast: far haze soft / near sharp / foreground crisp.
    if (band === "veryFar") ctx.globalAlpha = 0.32;
    else if (band === "far") ctx.globalAlpha = 0.55;
    else if (band === "mid") ctx.globalAlpha = 0.88;
    else if (band === "foreground") ctx.globalAlpha = 1;
    else if (band === "near") ctx.globalAlpha = 1;

    // Architecture priority: highways first so budget never erases civilization map.
    // Reuse arrays — avoid per-band allocations every frame.
    const highwayFirst = this._highwayFirst;
    const bandStrands = this._bandStrands;
    highwayFirst.length = 0;
    bandStrands.length = 0;
    for (const strand of tissue) {
      if (strand.band !== band) continue;
      if (strand.kind === "pathway") highwayFirst.push(strand);
      else bandStrands.push(strand);
    }

    for (let pass = 0; pass < 2; pass++) {
      const list = pass === 0 ? highwayFirst : bandStrands;
      for (const strand of list) {
        if (this._tissueBudget <= 0) break;
        const parallax =
          strand.parallax ??
          (band === "veryFar"
            ? 0.05
            : band === "far"
              ? 0.14
              : band === "mid"
                ? 0.46
                : band === "bridge"
                  ? 0.5
                  : band === "foreground"
                    ? 1.12
                    : 0.9);
        const pts = this._projectStrand(camera, strand.pts, parallax, padX, padY);
        if (pts.length < 2) continue;

        const wave = 0.88 + Math.sin(strand.phase) * 0.12;
        const kindBoost =
          strand.kind === "pathway"
            ? strand.artery
              ? 1.55
              : 1.38
            : strand.kind === "colony"
              ? 1.18
              : strand.kind === "secondary"
                ? 1.1
                : strand.kind === "tertiary"
                  ? 0.88
                  : strand.kind === "bridge"
                    ? 1.05
                    : 1;
        // Gravitational pull: highways brighten as they converge on the Core.
        let gravityBoost = 1;
        if (strand.kind === "pathway" && strand.pts?.length) {
          const mid = strand.pts[Math.floor(strand.pts.length / 2)];
          const dx = mid.x - coreCx;
          const dy = mid.y - coreCy;
          const prox = 1 - Math.min(1, Math.sqrt(dx * dx + dy * dy) / (densScale * 2.8));
          gravityBoost = 1 + prox * highwayGravity * (strand.artery ? 1.25 : 1);
        }
        const alpha = Math.min(
          strand.opacity * bandFade * life * brightness * wave * kindBoost * gravityBoost,
          0.78,
        );
        if (alpha < 0.008) continue;

        const color =
          strand.hue > 0.78
            ? COLORS.redHot
            : strand.hue > 0.55
              ? COLORS.redGlow
              : COLORS.redDeep;
        ctx.beginPath();
        traceStrand(ctx, pts, strand.phase);
        ctx.strokeStyle = `${color}${alpha})`;
        const bandWidth =
          band === "veryFar"
            ? 0.48
            : band === "far"
              ? 0.66
              : band === "near"
                ? 1.22
                : band === "foreground"
                  ? 1.38
                  : 1;
        ctx.lineWidth =
          strand.width *
          bandWidth *
          wave *
          (strand.kind === "pathway"
            ? strand.artery
              ? 1.42
              : 1.28
            : strand.kind === "tertiary"
              ? 0.82
              : 1);
        ctx.stroke();

        // Major highways carry a luminous organic sheath.
        if (strand.kind === "pathway" && alpha > 0.1) {
          ctx.beginPath();
          traceStrand(ctx, pts, strand.phase + 0.2);
          ctx.strokeStyle = `${COLORS.whiteDim}${alpha * highwaySheath})`;
          ctx.lineWidth = strand.width * (strand.artery ? 0.48 : 0.32) * wave;
          ctx.stroke();
        }
        this._tissueBudget--;
      }
      if (this._tissueBudget <= 0) break;
    }

    ctx.restore();
  }

  /**
   * Overlapping microscopic tissue in the dense cognitive region.
   * Hundreds of short local strands — light emerges from density, not a bloom.
   * Filaments are pre-sorted / partitioned at build time (no per-frame sort).
   */
  _drawCoreTissue(ctx, camera, core, padX, padY, breathe, coreIntensity, COLORS, filaments) {
    const list = filaments ?? core.filaments;
    if (!list?.length) return;

    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    const scale = this._budgets?.filamentDrawScale ?? 1;
    const stride = scale >= 0.95 ? 1 : Math.max(1, Math.round(1 / Math.max(0.2, scale)));

    for (let i = 0; i < list.length; i += stride) {
      const f = list[i];
      const tier = f.depthTier || "mid";
      const parallax = f.parallax ?? (tier === "front" ? 1.14 : tier === "deep" ? 0.72 : 1);
      const pts = this._projectStrand(camera, f.pts, parallax, padX, padY);
      if (pts.length < 2) continue;
      const wave = 0.9 + Math.sin(f.phase) * 0.1;
      const tierBoost =
        tier === "deep"
          ? 0.62
          : tier === "labelBack"
            ? 1.48
            : tier === "bright"
              ? 1.22
              : tier === "front"
                ? 0.95
                : 1;
      const alpha = Math.min(f.opacity * coreIntensity * breathe * wave * 1.05 * tierBoost, 0.78);
      if (alpha < 0.01) continue;
      const color = f.hue > 0.88 ? COLORS.redHot : f.hue > 0.72 ? COLORS.redGlow : COLORS.redCrimson;

      ctx.beginPath();
      traceStrand(ctx, pts, f.phase);
      ctx.strokeStyle = `${color}${alpha})`;
      ctx.lineWidth =
        f.width *
        (0.82 + breathe * 0.14) *
        wave *
        (tier === "front" ? 1.15 : tier === "deep" ? 0.78 : 1);
      ctx.stroke();

      // Hot filaments / label-back density carry a faint white spark.
      if (alpha > 0.32 && (f.hue > 0.84 || tier === "labelBack" || tier === "bright")) {
        ctx.beginPath();
        traceStrand(ctx, pts, f.phase + 0.35);
        ctx.strokeStyle = `${COLORS.whiteDim}${alpha * (tier === "labelBack" ? 0.16 : 0.12)})`;
        ctx.lineWidth = f.width * 0.35;
        ctx.stroke();
      }
    }
  }

  /**
   * Sparse near-camera Core filaments — volumetric foreground depth.
   */
  _drawCoreFrontTissue(ctx, camera, nodes, intensity, thinking, vitality, COLORS) {
    const core = nodes.core;
    if (!core?.filamentsFront?.length) return;
    const padX = NEURAL_CONFIG.world.padding * camera.width;
    const padY = NEURAL_CONFIG.world.padding * camera.height;
    const breathe = 0.9 + (core.pulse ?? 0.7) * 0.06 + vitality * 0.04;
    const coreIntensity =
      ((thinking ? 0.82 : 0.64) * breathe + intensity * 0.12) *
      (NEURAL_CONFIG.render.coreDrawStrength ?? 1) *
      0.88;

    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    this._drawCoreTissue(ctx, camera, core, padX, padY, breathe, coreIntensity, COLORS, core.filamentsFront);
    ctx.restore();
  }

  /**
   * Tiny synaptic energy packets — orbit close to the nucleus or ride Core filaments.
   * Never across the whole screen; Core-local only.
   */
  _drawCoreEnergyPackets(ctx, camera, core, padX, padY, breathe, coreIntensity, COLORS) {
    const packets = core.energyPackets;
    if (!packets?.length) return;
    const asym = NEURAL_CONFIG.core?.asymmetry || {};
    const densScale =
      Math.min(camera.width, camera.height) * (NEURAL_CONFIG.core?.clusterRadiusRatio ?? 0.3);

    for (const p of packets) {
      let x;
      let y;
      if (p.kind === "orbit") {
        const screen = camera.worldToScreen(
          core.cx + (asym.x ?? 0) * densScale * 0.2 + Math.cos(p.angle) * p.radius * p.stretchX,
          core.cy + (asym.y ?? 0) * densScale * 0.2 + Math.sin(p.angle) * p.radius * p.stretchY,
          1,
        );
        x = screen.x - padX;
        y = screen.y - padY;
      } else {
        const t = (p.t + this._time * p.speed) % 1;
        const filament = core.filaments[p.filamentIndex];
        if (!filament?.pts?.length) continue;
        // Prefer near-Core filaments: skip packets that start far from focus.
        const p0 = filament.pts[0];
        const dx0 = p0.x - core.cx;
        const dy0 = p0.y - core.cy;
        if (Math.sqrt(dx0 * dx0 + dy0 * dy0) > densScale * 0.85) continue;
        const pts = this._projectStrand(camera, filament.pts, filament.parallax ?? 1, padX, padY);
        if (pts.length < 2) continue;
        const idx = Math.min(pts.length - 2, Math.floor(t * (pts.length - 1)));
        const localT = t * (pts.length - 1) - idx;
        x = pts[idx].x + (pts[idx + 1].x - pts[idx].x) * localT;
        y = pts[idx].y + (pts[idx + 1].y - pts[idx].y) * localT;
      }
      const flicker = 0.78 + Math.sin(this._time * 2.0 + p.phase) * 0.22;
      const a = Math.min(p.a * coreIntensity * breathe * flicker * (p.kind === "orbit" ? 1.05 : 1), 0.55);
      ctx.beginPath();
      ctx.arc(x, y, p.r * (0.85 + breathe * 0.12), 0, Math.PI * 2);
      ctx.fillStyle = `${COLORS.redHot}${a})`;
      ctx.fill();
      if (a > 0.34) {
        ctx.beginPath();
        ctx.arc(x, y, p.r * 0.28, 0, Math.PI * 2);
        ctx.fillStyle = `${COLORS.whiteDim}${a * 0.28})`;
        ctx.fill();
      }
    }
  }

  /**
   * Microscopic neuron dust — density creates brightness without an orb.
   */
  _drawMicroNeurons(ctx, camera, core, padX, padY, breathe, coreIntensity, COLORS, thinking) {
    const micros = core.microNeurons;
    if (!micros?.length) return;
    const densScale =
      Math.min(camera.width, camera.height) * (NEURAL_CONFIG.core?.clusterRadiusRatio ?? 0.3);
    const scale = this._budgets?.microNeuronDrawScale ?? 1;
    const stride = scale >= 0.95 ? 1 : Math.max(1, Math.round(1 / Math.max(0.2, scale)));

    for (let i = 0; i < micros.length; i += stride) {
      const m = micros[i];
      const screen = camera.worldToScreen(m.x, m.y, 1);
      screen.x -= padX;
      screen.y -= padY;
      const dx = m.x - core.cx;
      const dy = m.y - core.cy;
      const dist = Math.sqrt(dx * dx + dy * dy);
      const proximity = Math.max(0, 1 - dist / (densScale * 1.8));
      const flicker = 0.85 + Math.sin(m.phase) * 0.15;
      // Near-core micros stay dense but avoid white wash stacking under lighter.
      const a = Math.min(
        m.a * coreIntensity * breathe * flicker * (thinking ? 1.08 : 1) * (0.68 + proximity * 0.42),
        0.72,
      );
      ctx.beginPath();
      ctx.arc(screen.x, screen.y, m.r * (0.9 + breathe * 0.1 + proximity * 0.1), 0, Math.PI * 2);
      ctx.fillStyle = `${COLORS.redHot}${a})`;
      ctx.fill();
      if (a > 0.48 && proximity > 0.42 && proximity < 0.88) {
        ctx.beginPath();
        ctx.arc(screen.x, screen.y, m.r * 0.28, 0, Math.PI * 2);
        ctx.fillStyle = `${COLORS.whiteDim}${a * (0.1 + proximity * 0.08)})`;
        ctx.fill();
      }
    }
  }

  /**
   * @param {import("./camera.js").NeuralCamera} camera
   * @param {Array<{ x: number, y: number }>} worldPts
   * @param {number} parallax
   * @param {number} padX
   * @param {number} padY
   */
  _projectStrand(camera, worldPts, parallax, padX, padY) {
    /** @type {Array<{ x: number, y: number }>} */
    const out = [];
    for (const p of worldPts) {
      const s = camera.worldToScreen(p.x, p.y, parallax);
      out.push({ x: s.x - padX, y: s.y - padY });
    }
    return out;
  }

  _drawSignalTrails(ctx, camera, signals, COLORS, thinking) {
    const drawList = signals.getSignalDrawData(camera);
    ctx.save();
    ctx.globalCompositeOperation = "lighter";

    for (const p of drawList) {
      const colorBase = COLORS[p.colorKey] ?? COLORS.redGlow;
      const alpha = Math.min(p.strength * 0.72, 0.88);
      const trail = p.trailPoints;
      if (trail?.length > 1) {
        ctx.beginPath();
        ctx.moveTo(trail[0].x, trail[0].y);
        for (let i = 1; i < trail.length; i++) {
          ctx.lineTo(trail[i].x, trail[i].y);
        }
        ctx.strokeStyle = `${colorBase}${alpha * 0.42})`;
        ctx.lineWidth = 0.55 + p.strength * (thinking ? 1.05 : 0.75);
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.stroke();
        ctx.strokeStyle = `${COLORS.whiteDim}${alpha * 0.18})`;
        ctx.lineWidth = 0.35 + p.strength * 0.4;
        ctx.stroke();
      } else {
        ctx.beginPath();
        ctx.moveTo(p.trailX, p.trailY);
        ctx.lineTo(p.x, p.y);
        ctx.strokeStyle = `${colorBase}${alpha * 0.55})`;
        ctx.lineWidth = 0.5 + p.strength * 0.85;
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  _drawSignalParticles(ctx, camera, signals, COLORS, thinking) {
    const drawList = signals.getSignalDrawData(camera);
    const particleSize = NEURAL_CONFIG.signals.particleSize || 1.5;
    const glowStrength = NEURAL_CONFIG.render.signalParticleGlow || 0.85;

    ctx.save();
    ctx.globalCompositeOperation = "lighter";

    for (const p of drawList) {
      const colorBase = COLORS[p.colorKey] ?? COLORS.redGlow;
      const alpha = Math.min(p.strength * 0.95, 0.96);
      const size = particleSize * (0.8 + p.strength * 0.55);

      ctx.beginPath();
      ctx.arc(p.x, p.y, size * 3.8, 0, Math.PI * 2);
      ctx.fillStyle = `${colorBase}${alpha * glowStrength * 0.22})`;
      ctx.fill();

      ctx.beginPath();
      ctx.arc(p.x, p.y, size * (1.05 + p.progress * 0.25), 0, Math.PI * 2);
      ctx.fillStyle = `${COLORS.whiteDim}${alpha * 0.48})`;
      ctx.fill();

      ctx.beginPath();
      ctx.arc(p.x, p.y, size * 0.55, 0, Math.PI * 2);
      ctx.fillStyle = `${COLORS.whiteCore}${Math.min(alpha * 0.9, 0.95)})`;
      ctx.fill();
    }

    ctx.restore();
  }

  _drawDust(ctx, thinking, vitality, COLORS) {
    if (!this._dust.length) return;
    const speed = thinking ? 1.35 : 0.85 + vitality * 0.4;
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    for (const d of this._dust) {
      d.x += d.vx * speed;
      d.y += d.vy * speed;
      if (d.x < -4) d.x = this.width + 4;
      if (d.x > this.width + 4) d.x = -4;
      if (d.y < -4) d.y = this.height + 4;
      if (d.y > this.height + 4) d.y = -4;
      ctx.beginPath();
      ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
      ctx.fillStyle = `${COLORS.dust}${d.a * (thinking ? 1.25 : 1)})`;
      ctx.fill();
    }
    ctx.restore();
  }

  /**
   * Soft foreground bokeh sparks — near-camera depth without smoke/clouds.
   */
  _drawForegroundBokeh(ctx, thinking, vitality, COLORS) {
    if (!this._bokeh?.length) return;
    const speed = thinking ? 1.15 : 0.7 + vitality * 0.35;
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    for (const b of this._bokeh) {
      b.x += b.vx * speed;
      b.y += b.vy * speed;
      if (b.x < -8) b.x = this.width + 8;
      if (b.x > this.width + 8) b.x = -8;
      if (b.y < -8) b.y = this.height + 8;
      if (b.y > this.height + 8) b.y = -8;
      const a = b.a * (thinking ? 1.2 : 1);
      if (b.soft) {
        const halo = ctx.createRadialGradient(b.x, b.y, 0, b.x, b.y, b.r * 2.2);
        halo.addColorStop(0, `${COLORS.redHot}${a * 0.55})`);
        halo.addColorStop(0.45, `${COLORS.redGlow}${a * 0.22})`);
        halo.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = halo;
        ctx.beginPath();
        ctx.arc(b.x, b.y, b.r * 2.2, 0, Math.PI * 2);
        ctx.fill();
      } else {
        ctx.beginPath();
        ctx.arc(b.x, b.y, b.r * 0.55, 0, Math.PI * 2);
        ctx.fillStyle = `${COLORS.redHot}${a})`;
        ctx.fill();
        if (a > 0.08) {
          ctx.beginPath();
          ctx.arc(b.x, b.y, b.r * 0.22, 0, Math.PI * 2);
          ctx.fillStyle = `${COLORS.whiteDim}${a * 0.45})`;
          ctx.fill();
        }
      }
    }
    ctx.restore();
  }

  _drawVolumetricHaze(ctx, w, h, intensity, thinking, COLORS, patchLimit = 3) {
    const strength =
      (NEURAL_CONFIG.atmosphere?.hazeStrength ?? NEURAL_CONFIG.render.hazeStrength ?? 0.045) *
      (0.55 + intensity * 0.25 + (thinking ? 0.08 : 0));
    const asym = NEURAL_CONFIG.core?.asymmetry || {};
    // Wide soft veil patches — depth atmosphere without carving a center object.
    const patches = [
      { x: 0.5 + (asym.x ?? -0.14) * 0.03, y: 0.46 + (asym.y ?? 0.09) * 0.03, r: 0.85, a: 0.35 },
      { x: 0.22, y: 0.4, r: 0.5, a: 0.18 },
      { x: 0.78, y: 0.55, r: 0.48, a: 0.16 },
    ];
    const limit = Math.max(0, Math.min(patches.length, patchLimit ?? patches.length));
    for (let i = 0; i < limit; i++) {
      const p = patches[i];
      const cx = w * p.x;
      const cy = h * p.y;
      const grad = ctx.createRadialGradient(cx, cy, w * 0.08, cx, cy, w * p.r);
      grad.addColorStop(0, "rgba(0, 0, 0, 0)");
      grad.addColorStop(0.55, `${COLORS.hazeRed}${strength * p.a * 0.35})`);
      grad.addColorStop(1, `${COLORS.hazeRed}${strength * p.a * 0.55})`);
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);
    }
  }

  _drawRestrainedBloom(ctx, camera, nodes, thinking, COLORS, spotLimit = 5) {
    // Soft volumetric bloom from Core — micro bloom, never blown out.
    const bloom = NEURAL_CONFIG.atmosphere?.bloomStrength ?? 0.032;
    if (bloom <= 0.008 || spotLimit <= 0) return;
    const padX = NEURAL_CONFIG.world.padding * camera.width;
    const padY = NEURAL_CONFIG.world.padding * camera.height;
    const core = nodes.core;
    const asym = NEURAL_CONFIG.core?.asymmetry || {};
    const pulse = core.pulse ?? 0.8;
    const breath = 0.96 + (pulse - 0.78) * 0.4;
    const spots = [
      { ox: asym.x ?? -0.035, oy: asym.y ?? 0.012, scale: 0.14 * breath, a: 1.05, white: true },
      { ox: 0.04, oy: -0.03, scale: 0.1, a: 0.4, white: false },
      { ox: -0.05, oy: 0.05, scale: 0.085, a: 0.3, white: false },
      { ox: 0.1, oy: 0.04, scale: 0.07, a: 0.2, white: false },
      { ox: -0.09, oy: -0.06, scale: 0.06, a: 0.15, white: false },
    ];
    const limit = Math.max(0, Math.min(spots.length, spotLimit));
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    for (let i = 0; i < limit; i++) {
      const s = spots[i];
      const wx = core.cx + s.ox * Math.min(camera.width, camera.height) * 0.05;
      const wy = core.cy + s.oy * Math.min(camera.width, camera.height) * 0.05;
      const screen = camera.worldToScreen(wx, wy, 1);
      screen.x -= padX;
      screen.y -= padY;
      const r = Math.min(this.width, this.height) * s.scale * (thinking ? 1.04 : 1);
      const grad = ctx.createRadialGradient(screen.x, screen.y, r * 0.08, screen.x, screen.y, r);
      if (s.white) {
        grad.addColorStop(0, `${COLORS.whiteCore}${bloom * s.a * (thinking ? 0.14 : 0.1)})`);
        grad.addColorStop(0.2, `${COLORS.redHot}${bloom * s.a * 0.14})`);
      } else {
        grad.addColorStop(0, `${COLORS.redHot}${bloom * s.a * (thinking ? 0.1 : 0.07)})`);
      }
      grad.addColorStop(0.42, `${COLORS.redGlow}${bloom * s.a * 0.08})`);
      grad.addColorStop(0.75, `${COLORS.redCore}${bloom * s.a * 0.03})`);
      grad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = grad;
      ctx.fillRect(screen.x - r, screen.y - r, r * 2, r * 2);
    }
    ctx.restore();
  }

  /**
   * Deep red atmospheric fog — soft crimson volume in the void.
   * @param {CanvasRenderingContext2D} ctx
   * @param {number} w @param {number} h
   * @param {number} intensity @param {boolean} thinking
   * @param {object} COLORS
   */
  _drawAtmosphericFog(ctx, w, h, intensity, thinking, COLORS, patchLimit = 5) {
    const strength =
      (NEURAL_CONFIG.atmosphere?.fogRedStrength ?? 0.055) *
      (0.7 + intensity * 0.25 + (thinking ? 0.1 : 0));
    const patches = [
      { x: 0.48, y: 0.44, rx: 0.58, ry: 0.42, a: 0.62 },
      { x: 0.22, y: 0.58, rx: 0.36, ry: 0.28, a: 0.3 },
      { x: 0.78, y: 0.35, rx: 0.34, ry: 0.3, a: 0.26 },
      { x: 0.62, y: 0.72, rx: 0.42, ry: 0.26, a: 0.22 },
      { x: 0.36, y: 0.28, rx: 0.3, ry: 0.22, a: 0.16 },
    ];
    const limit = Math.max(0, Math.min(patches.length, patchLimit ?? patches.length));
    ctx.save();
    for (let i = 0; i < limit; i++) {
      const p = patches[i];
      const cx = w * p.x;
      const cy = h * p.y;
      const rx = w * p.rx;
      const ry = h * p.ry;
      const grad = ctx.createRadialGradient(cx, cy, Math.min(rx, ry) * 0.1, cx, cy, Math.max(rx, ry));
      grad.addColorStop(0, `${COLORS.hazeRed}${strength * p.a})`);
      grad.addColorStop(0.5, `${COLORS.hazeRed}${strength * p.a * 0.4})`);
      grad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  /**
   * Soft light shafts — subtle volumetric beams from the dense region.
   * @param {CanvasRenderingContext2D} ctx
   * @param {number} w @param {number} h
   * @param {number} intensity @param {boolean} thinking @param {number} vitality
   * @param {object} COLORS
   */
  _drawLightShafts(ctx, w, h, intensity, thinking, vitality, COLORS) {
    const strength =
      (NEURAL_CONFIG.atmosphere?.lightShaftStrength ?? 0.028) *
      (0.55 + vitality * 0.3 + intensity * 0.2);
    if (strength < 0.004) return;
    const asym = NEURAL_CONFIG.core?.asymmetry || {};
    const oyRatio = NEURAL_CONFIG.core?.yRatio ?? 0.48;
    const ox = w * (0.5 + (asym.x ?? -0.05) * 0.04);
    const oy = h * (oyRatio + (asym.y ?? 0.02) * 0.04);
    const shafts = [
      { angle: -0.55, len: 0.55, width: 0.045, a: 0.7 },
      { angle: 0.35, len: 0.48, width: 0.038, a: 0.5 },
      { angle: 1.15, len: 0.42, width: 0.032, a: 0.35 },
      { angle: 2.4, len: 0.38, width: 0.028, a: 0.28 },
      { angle: -1.8, len: 0.4, width: 0.03, a: 0.3 },
    ];
    const pulse = 0.85 + Math.sin(this._time * 0.35) * 0.15;
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    for (const s of shafts) {
      const len = Math.min(w, h) * s.len * (thinking ? 1.08 : 1);
      const half = Math.min(w, h) * s.width;
      const cos = Math.cos(s.angle);
      const sin = Math.sin(s.angle);
      const ex = ox + cos * len;
      const ey = oy + sin * len;
      const px = -sin * half;
      const py = cos * half;
      const grad = ctx.createLinearGradient(ox, oy, ex, ey);
      grad.addColorStop(0, `${COLORS.redHot}${strength * s.a * 0.35 * pulse})`);
      grad.addColorStop(0.35, `${COLORS.redGlow}${strength * s.a * 0.18 * pulse})`);
      grad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.moveTo(ox + px * 0.3, oy + py * 0.3);
      ctx.lineTo(ox - px * 0.3, oy - py * 0.3);
      ctx.lineTo(ex - px, ey - py);
      ctx.lineTo(ex + px, ey + py);
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();
  }

  /**
   * Very subtle lens diffusion — soft optical veil.
   * @param {CanvasRenderingContext2D} ctx
   * @param {number} w @param {number} h
   * @param {number} intensity
   * @param {object} COLORS
   */
  _drawLensDiffusion(ctx, w, h, intensity, COLORS) {
    const strength = NEURAL_CONFIG.atmosphere?.lensDiffusion ?? 0.012;
    if (strength <= 0.002) return;
    const cx = w * 0.5;
    const cy = h * 0.46;
    const r = Math.min(w, h) * 0.62;
    const grad = ctx.createRadialGradient(cx, cy, r * 0.2, cx, cy, r);
    grad.addColorStop(0, `${COLORS.whiteDim}${strength * (0.35 + intensity * 0.15)})`);
    grad.addColorStop(0.45, `${COLORS.redHot}${strength * 0.12})`);
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);
    ctx.restore();
  }

  _drawGhosts(ctx, camera, ghostLayer, COLORS) {
    const padX = NEURAL_CONFIG.world.padding * camera.width;
    const padY = NEURAL_CONFIG.world.padding * camera.height;
    const opacity = ghostLayer.getOpacity();

    ctx.save();
    ctx.globalCompositeOperation = "lighter";

    for (const g of ghostLayer.ghosts) {
      const screen = camera.worldToScreen(g.x, g.y, g.parallax);
      screen.x -= padX;
      screen.y -= padY;
      const alpha = g.fadeIn * opacity * 0.48;
      const pulse = (Math.sin(g.pulse) + 1) * 0.5;
      ctx.beginPath();
      ctx.arc(screen.x, screen.y, g.radius * (1.4 + pulse * 0.35), 0, Math.PI * 2);
      ctx.fillStyle = `${COLORS.signalMemory}${alpha * 0.32})`;
      ctx.fill();
      ctx.beginPath();
      ctx.arc(screen.x, screen.y, g.radius * 0.55, 0, Math.PI * 2);
      ctx.fillStyle = `${COLORS.redGlow}${alpha * (0.55 + pulse * 0.25)})`;
      ctx.fill();
    }

    ctx.restore();
  }

  _drawDepthFog(ctx, w, h, intensity, recallDive) {
    // Soft atmospheric dimming — wide and uneven so it never carves a core circle.
    const strength = NEURAL_CONFIG.render.depthFogStrength || 0.18;
    const asym = NEURAL_CONFIG.core?.asymmetry || {};
    const cx = w * (0.48 + (asym.x ?? -0.14) * 0.02);
    const cy = h * (0.5 + (asym.y ?? 0.09) * 0.02);
    const dive = recallDive || 0;

    ctx.save();
    for (let i = 0; i < 3; i++) {
      const t = i / 2;
      const ox = (i - 1) * w * 0.06;
      const oy = ((i % 2) * 2 - 1) * h * 0.04;
      const inner = w * (0.18 + t * 0.14 + dive * 0.03);
      const outer = w * (0.72 + t * 0.18 + dive * 0.06);
      const fog = ctx.createRadialGradient(cx + ox, cy + oy, inner, cx + ox, cy + oy, outer);
      fog.addColorStop(0, "rgba(0, 0, 0, 0)");
      fog.addColorStop(0.55, `rgba(0, 0, 0, ${strength * (0.05 + t * 0.04 + dive * 0.03)})`);
      fog.addColorStop(1, `rgba(0, 0, 0, ${strength * (0.12 + t * 0.07 + intensity * 0.03)})`);
      ctx.fillStyle = fog;
      ctx.fillRect(0, 0, w, h);
    }
    ctx.restore();
  }

  _drawForegroundFog(ctx, camera, nodes, w, h) {
    const padX = NEURAL_CONFIG.world.padding * camera.width;
    const padY = NEURAL_CONFIG.world.padding * camera.height;
    const layerCut = NEURAL_CONFIG.layers.length - 2;
    const scratch = this._fgNodeScratch;
    scratch.length = 0;
    const src = nodes.nodes;
    for (let i = 0; i < src.length; i++) {
      const n = src[i];
      if (n.layer >= layerCut && !n.isCenter) scratch.push(n);
    }
    if (!scratch.length) return;

    ctx.save();
    ctx.globalCompositeOperation = "source-over";

    const limit = Math.min(scratch.length, 28);
    for (let i = 0; i < limit; i++) {
      const n = scratch[(i * 17 + 5) % scratch.length];
      const screen = this._screenPoint(camera, n, padX, padY);
      const r = 42 + n.radius * 8;
      const grad = ctx.createRadialGradient(screen.x, screen.y, 0, screen.x, screen.y, r);
      grad.addColorStop(0, "rgba(0, 0, 0, 0.06)");
      grad.addColorStop(0.5, "rgba(0, 0, 0, 0.02)");
      grad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = grad;
      ctx.fillRect(screen.x - r, screen.y - r, r * 2, r * 2);
    }

    ctx.restore();
  }

  _drawVignette(ctx, w, h, COLORS) {
    const strength =
      NEURAL_CONFIG.atmosphere?.vignetteStrength ??
      NEURAL_CONFIG.render.vignetteStrength ??
      NEURAL_CONFIG.render.edgeFadeStrength;
    // Soft edge falloff only — tissue must remain visible at the periphery.
    const edgeFade = ctx.createLinearGradient(0, 0, 0, h);
    edgeFade.addColorStop(0, `${COLORS.vignette}${strength * 0.55})`);
    edgeFade.addColorStop(0.08, "rgba(0,0,0,0)");
    edgeFade.addColorStop(0.92, "rgba(0,0,0,0)");
    edgeFade.addColorStop(1, `${COLORS.vignette}${strength * 0.7})`);
    ctx.fillStyle = edgeFade;
    ctx.fillRect(0, 0, w, h);

    const sideFade = ctx.createLinearGradient(0, 0, w, 0);
    sideFade.addColorStop(0, `${COLORS.vignette}0.42)`);
    sideFade.addColorStop(0.07, "rgba(0,0,0,0)");
    sideFade.addColorStop(0.93, "rgba(0,0,0,0)");
    sideFade.addColorStop(1, `${COLORS.vignette}0.42)`);
    ctx.fillStyle = sideFade;
    ctx.fillRect(0, 0, w, h);
  }
}
