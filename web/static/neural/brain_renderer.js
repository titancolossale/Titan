/**
 * Titan Neural Brain Engine — Canvas2D Renderer
 * Phase 17.4 · Phase 19.1 · Phase 19.2 — five depth layers, contrast fog
 */
(function (global) {
  "use strict";

  var TitanNeural = (global.TitanNeural = global.TitanNeural || {});
  var CONFIG = TitanNeural.CONFIG;
  var COLORS = CONFIG.colors;

  function BrainRenderer(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.width = 0;
    this.height = 0;
    this.dpr = 1;
  }

  BrainRenderer.prototype.resize = function (width, height) {
    this.width = width;
    this.height = height;
    this.dpr = Math.min(window.devicePixelRatio || 1, CONFIG.render.maxDpr);

    this.canvas.width = Math.floor(width * this.dpr);
    this.canvas.height = Math.floor(height * this.dpr);
    this.canvas.style.width = width + "px";
    this.canvas.style.height = height + "px";
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
  };

  BrainRenderer.prototype.renderWithSignals = function (
    camera,
    nodes,
    signals,
    state,
    depthField,
    cognitiveOverlay
  ) {
    var ctx = this.ctx;
    var w = this.width;
    var h = this.height;
    var intensity = state.getIntensity();
    var thinking = state.isThinking();
    var vitality = state.getVitality ? state.getVitality() : 0.15;

    ctx.clearRect(0, 0, w, h);

    if (depthField) {
      depthField.draw(ctx, camera, w, h);
    }

    this._drawAmbient(ctx, w, h, intensity, thinking, vitality);
    this._drawCentralCore(ctx, w, h, intensity, thinking, vitality);
    this._drawEdges(ctx, camera, nodes, thinking);
    this._drawNodes(ctx, camera, nodes, thinking);

    if (signals) {
      this._drawWaves(ctx, camera, signals.getWaves());
      this._drawSignalParticles(ctx, camera, signals);
      this._drawDepthContinuity(ctx, camera, nodes, w, h);
    }

    if (cognitiveOverlay && cognitiveOverlay.draw) {
      var signature = state.getCognitiveSignature ? state.getCognitiveSignature() : null;
      cognitiveOverlay.draw(ctx, w, h, signature);
    }

    var recallDive =
      depthField && depthField.getRecallDive ? depthField.getRecallDive() : 0;

    this._drawDepthFog(ctx, w, h, intensity, recallDive);
    this._drawAtmosphericHaze(ctx, w, h);
    this._drawPanelOcclusion(ctx, w, h);
    this._drawVignette(ctx, w, h);
  };

  BrainRenderer.prototype._layerDepthFade = function (layerIdx) {
    var layers = CONFIG.layers;
    var layerCfg = layers[layerIdx];
    if (layerCfg && layerCfg.fogDim !== undefined) {
      return layerCfg.fogDim;
    }
    return 0.34 + (layerIdx / Math.max(layers.length - 1, 1)) * 0.66;
  };

  BrainRenderer.prototype._layerScreenScale = function (layerIdx) {
    return this._layerDepthFade(layerIdx);
  };

  BrainRenderer.prototype._foregroundLayerIndex = function () {
    return CONFIG.layers.length - 1;
  };

  BrainRenderer.prototype._drawDepthFog = function (ctx, w, h, intensity, recallDive) {
    var strength = CONFIG.render.depthFogStrength || 0.32;
    var cx = w * 0.5;
    var cy = h * 0.48;
    var dive = recallDive || 0;
    var inner = w * (0.02 + dive * 0.04);
    var outer = w * (0.68 + dive * 0.12);

    var fog = ctx.createRadialGradient(cx, cy, inner, cx, cy, outer);
    fog.addColorStop(0, "rgba(0, 0, 0, 0)");
    fog.addColorStop(0.55, "rgba(0, 0, 0, " + strength * (0.14 + dive * 0.08) + ")");
    fog.addColorStop(0.82, "rgba(0, 0, 0, " + (strength * 0.32 + intensity * 0.06 + dive * 0.1) + ")");
    fog.addColorStop(1, "rgba(0, 0, 0, " + (strength * 0.48 + intensity * 0.08 + dive * 0.14) + ")");

    ctx.fillStyle = fog;
    ctx.fillRect(0, 0, w, h);
  };

  BrainRenderer.prototype._drawSignalParticles = function (ctx, camera, signals) {
    if (!signals.getSignalDrawData) return;

    var drawList = signals.getSignalDrawData(camera);
    var particleSize = CONFIG.signals.particleSize || 1.6;
    var trail = CONFIG.signals.particleTrail || 0.35;
    var glowStrength = CONFIG.render.signalParticleGlow || 0.22;

    for (var i = 0; i < drawList.length; i++) {
      var p = drawList[i];
      var alpha = Math.min(p.strength * 0.85, 0.9);

      ctx.beginPath();
      ctx.moveTo(p.x - (p.toX - p.fromX) * trail * 0.08, p.y - (p.toY - p.fromY) * trail * 0.08);
      ctx.lineTo(p.x, p.y);
      ctx.strokeStyle = COLORS.redGlow + (alpha * 0.55) + ")";
      ctx.lineWidth = 0.6;
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(p.x, p.y, particleSize * (0.8 + p.strength * 0.4), 0, Math.PI * 2);
      ctx.fillStyle = COLORS.redGlow + alpha + ")";
      ctx.fill();

      ctx.beginPath();
      ctx.arc(p.x, p.y, particleSize * 3.2, 0, Math.PI * 2);
      ctx.fillStyle = COLORS.redGlow + (alpha * glowStrength) + ")";
      ctx.fill();
    }
  };

  BrainRenderer.prototype._drawDepthContinuity = function (ctx, camera, nodes, w, h) {
    var padX = CONFIG.world.padding * camera.width;
    var padY = CONFIG.world.padding * camera.height;
    var hints = 8;

    ctx.save();
    ctx.globalAlpha = 0.16;
    ctx.strokeStyle = COLORS.redGlow + "0.2)";

    for (var i = 0; i < hints; i++) {
      var nodeList = nodes.nodes;
      if (!nodeList || nodeList.length === 0) {
        continue;
      }
      var nodeId = (i * 11 + 3) % nodeList.length;
      var node = nodes.getNode(nodeId);
      if (!node) {
        continue;
      }

      var screen = camera.worldToScreen(node.x, node.y, node.parallax * 0.65);
      screen.x -= padX;
      screen.y -= padY;

      var offEdge =
        screen.x < -12 ||
        screen.x > w + 12 ||
        screen.y < -12 ||
        screen.y > h + 12;
      if (!offEdge) {
        continue;
      }

      var towardX = w * 0.5 + (screen.x - w * 0.5) * 0.28;
      var towardY = h * 0.45 + (screen.y - h * 0.45) * 0.28;

      var grad = ctx.createLinearGradient(screen.x, screen.y, towardX, towardY);
      grad.addColorStop(0, COLORS.redGlow + "0.28)");
      grad.addColorStop(1, "rgba(0, 0, 0, 0)");

      ctx.beginPath();
      ctx.moveTo(screen.x, screen.y);
      ctx.lineTo(towardX, towardY);
      ctx.strokeStyle = grad;
      ctx.lineWidth = 0.4;
      ctx.stroke();
    }

    ctx.restore();
  };

  BrainRenderer.prototype._drawWaves = function (ctx, camera, waves) {
    if (!waves || waves.length === 0) return;

    var padX = CONFIG.world.padding * camera.width;
    var padY = CONFIG.world.padding * camera.height;

    for (var i = 0; i < waves.length; i++) {
      var w = waves[i];
      var screen = camera.worldToScreen(w.x, w.y, 0.85);
      screen.x -= padX;
      screen.y -= padY;
      var aspectX = w.aspectX || 1;

      ctx.beginPath();
      if (w.shape === "geometric") {
        var half = w.radius * 0.92;
        ctx.rect(screen.x - half, screen.y - half, half * 2, half * 2);
      } else if (aspectX > 1.2) {
        ctx.ellipse(screen.x, screen.y, w.radius * aspectX, w.radius * 0.55, 0, 0, Math.PI * 2);
      } else {
        ctx.arc(screen.x, screen.y, w.radius, 0, Math.PI * 2);
      }
      ctx.strokeStyle = COLORS.redGlow + (w.strength * 0.12) + ")";
      ctx.lineWidth = 0.55;
      ctx.stroke();
    }
  };

  BrainRenderer.prototype._drawCentralCore = function (ctx, w, h, intensity, thinking, vitality) {
    var strength = CONFIG.render.centralCoreStrength || 1;
    var cx = w * 0.5;
    var cy = h * 0.48;
    var pulse = 0.72 + Math.sin(Date.now() * 0.0012) * 0.12 + vitality * 0.18;
    var coreAlpha = (thinking ? 0.58 : 0.38) * pulse * strength + intensity * 0.18;

    var inner = ctx.createRadialGradient(cx, cy, 0, cx, cy, w * 0.16);
    inner.addColorStop(0, "rgba(255, 255, 255, " + Math.min(coreAlpha * 0.95, 0.98) + ")");
    inner.addColorStop(0.15, COLORS.redGlow + Math.min(coreAlpha * 1.5, 0.98) + ")");
    inner.addColorStop(0.4, COLORS.redCore + (coreAlpha * 0.85) + ")");
    inner.addColorStop(0.72, COLORS.redGlow + (coreAlpha * 0.22) + ")");
    inner.addColorStop(1, "rgba(0, 0, 0, 0)");

    ctx.fillStyle = inner;
    ctx.fillRect(0, 0, w, h);

    var halo = ctx.createRadialGradient(cx, cy, w * 0.03, cx, cy, w * 0.38);
    halo.addColorStop(0, COLORS.redGlow + (coreAlpha * 0.35) + ")");
    halo.addColorStop(0.45, COLORS.redCore + (coreAlpha * 0.12) + ")");
    halo.addColorStop(1, "rgba(0, 0, 0, 0)");

    ctx.fillStyle = halo;
    ctx.fillRect(0, 0, w, h);
  };

  BrainRenderer.prototype._drawAmbient = function (ctx, w, h, intensity, thinking, vitality) {
    var strength =
      CONFIG.render.ambientGlowStrength + intensity * 0.08 + vitality * 0.04;
    var cx = w * 0.5;
    var cy = h * 0.44;
    var radius = Math.max(w, h) * 0.88;

    var gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
    gradient.addColorStop(0, COLORS.redCore + (thinking ? strength * 2.1 : strength * 1.4) + ")");
    gradient.addColorStop(0.32, COLORS.redGlow + (strength * 0.32) + ")");
    gradient.addColorStop(0.58, COLORS.redCore + (strength * 0.1) + ")");
    gradient.addColorStop(1, "rgba(0, 0, 0, 0)");

    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, w, h);
  };

  BrainRenderer.prototype._screenPoint = function (camera, node, padX, padY) {
    var screen = camera.worldToScreen(node.x, node.y, node.parallax);
    screen.x -= padX;
    screen.y -= padY;
    return screen;
  };

  BrainRenderer.prototype._drawEdges = function (ctx, camera, nodes, thinking) {
    var edgeList = nodes.edges;
    var nodeList = nodes.nodes;
    var padX = CONFIG.world.padding * camera.width;
    var padY = CONFIG.world.padding * camera.height;
    var useCurves = CONFIG.render.curveEdgesForeground;

    var layerCount = CONFIG.layers.length;
    var fgLayer = this._foregroundLayerIndex();
    var midLayer = Math.max(1, Math.floor(CONFIG.layers.length / 2));

    for (var layer = 0; layer < layerCount; layer++) {
      for (var i = 0; i < edgeList.length; i++) {
        var e = edgeList[i];
        if (!e.visible || e.opacity < 0.012) continue;

        var na = nodeList[e.a];
        var nb = nodeList[e.b];
        if (!na || !nb) continue;

        var edgeLayer = Math.round(e.layerMix);
        if (edgeLayer !== layer) continue;

        var pa = this._screenPoint(camera, na, padX, padY);
        var pb = this._screenPoint(camera, nb, padX, padY);

        var depthFade = this._layerDepthFade(layer);
        var alpha = (e.opacity * e.edgeOpacity + e.glow * 0.38) * depthFade;
        if (e.signalProgress >= 0) {
          alpha += (1 - e.signalProgress) * 0.32 * depthFade;
        }

        ctx.beginPath();
        if (useCurves && layer === fgLayer) {
          var mx = (pa.x + pb.x) * 0.5;
          var my = (pa.y + pb.y) * 0.5 - 8;
          ctx.moveTo(pa.x, pa.y);
          ctx.quadraticCurveTo(mx, my, pb.x, pb.y);
        } else {
          ctx.moveTo(pa.x, pa.y);
          ctx.lineTo(pb.x, pb.y);
        }

        var lineW = 0.42 + depthFade * 0.72;
        var edgeAlpha = Math.min(alpha * 1.15, thinking ? 0.92 : 0.82);
        ctx.strokeStyle = COLORS.redGlow + edgeAlpha + ")";
        ctx.lineWidth = lineW;
        ctx.stroke();

        if (layer >= midLayer && alpha > 0.22) {
          ctx.strokeStyle = COLORS.redGlow + (edgeAlpha * 0.28) + ")";
          ctx.lineWidth = lineW + 1.8;
          ctx.stroke();
        }
      }
    }
  };

  BrainRenderer.prototype._drawNodes = function (ctx, camera, nodes, thinking) {
    var nodeList = nodes.nodes;
    var padX = CONFIG.world.padding * camera.width;
    var padY = CONFIG.world.padding * camera.height;

    var sorted = nodeList.slice().sort(function (a, b) {
      return a.layer - b.layer;
    });

    var fgLayer = this._foregroundLayerIndex();
    var midLayer = Math.max(1, Math.floor(CONFIG.layers.length / 2));

    for (var i = 0; i < sorted.length; i++) {
      var n = sorted[i];
      var screen = this._screenPoint(camera, n, padX, padY);

      var layerDim = this._layerScreenScale(n.layer);
      var isForeground = n.layer === fgLayer;
      var glow =
        n.opacity * (thinking && isForeground ? 1.2 : 1) * layerDim + n.glow * 0.55;
      var color;

      if (isForeground) {
        color = COLORS.redGlow + Math.min(glow, 0.92) + ")";
      } else if (n.layer >= midLayer) {
        color = COLORS.redCore + Math.min(glow, 0.72) + ")";
      } else {
        color = COLORS.whiteDim + Math.min(glow * 0.5, 0.28) + ")";
      }

      if (n.layer >= midLayer && glow > 0.42) {
        ctx.beginPath();
        ctx.arc(screen.x, screen.y, n.radius * 3 * layerDim, 0, Math.PI * 2);
        ctx.fillStyle = COLORS.redGlow + (glow * 0.09) + ")";
        ctx.fill();
      }

      if (n.activation > 0.06) {
        ctx.beginPath();
        ctx.arc(screen.x, screen.y, n.radius * (1.9 + n.activation * 1.1), 0, Math.PI * 2);
        ctx.fillStyle = COLORS.redGlow + (n.activation * 0.2) + ")";
        ctx.fill();
      }

      ctx.beginPath();
      ctx.arc(screen.x, screen.y, n.radius * layerDim, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
    }
  };

  BrainRenderer.prototype._drawAtmosphericHaze = function (ctx, w, h) {
    var strength = CONFIG.render.hazeStrength || 0.28;
    var parallax =
      global.TitanMotion && global.TitanMotion.readToken
        ? parseFloat(global.TitanMotion.readToken("--tdl-depth-parallax", "1")) || 1
        : 1;

    if (parallax <= 0 || strength <= 0) {
      return;
    }

    var gradient = ctx.createRadialGradient(w * 0.5, h * 0.4, w * 0.06, w * 0.5, h * 0.5, w * 0.88);
    gradient.addColorStop(0, "rgba(0, 0, 0, 0)");
    gradient.addColorStop(0.5, "rgba(0, 0, 0, " + strength * 0.32 * parallax + ")");
    gradient.addColorStop(1, "rgba(0, 0, 0, " + strength * parallax + ")");

    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, w, h);
  };

  BrainRenderer.prototype._drawPanelOcclusion = function (ctx, w, h) {
    var strength = CONFIG.render.panelOcclusionStrength || 0.12;

    ctx.save();

    var centerGrad = ctx.createRadialGradient(
      w * 0.5,
      h * 0.46,
      w * 0.08,
      w * 0.5,
      h * 0.48,
      w * 0.72
    );
    centerGrad.addColorStop(0, "rgba(0, 0, 0, 0)");
    centerGrad.addColorStop(0.55, "rgba(0, 0, 0, " + strength * 0.18 + ")");
    centerGrad.addColorStop(1, "rgba(0, 0, 0, " + strength * 0.42 + ")");

    ctx.fillStyle = centerGrad;
    ctx.fillRect(0, 0, w, h);

    ctx.restore();
  };

  BrainRenderer.prototype._drawVignette = function (ctx, w, h) {
    var strength = CONFIG.render.edgeFadeStrength;

    var edgeFade = ctx.createLinearGradient(0, 0, 0, h);
    edgeFade.addColorStop(0, COLORS.vignette + (strength * 0.85) + ")");
    edgeFade.addColorStop(0.12, "rgba(0,0,0,0)");
    edgeFade.addColorStop(0.88, "rgba(0,0,0,0)");
    edgeFade.addColorStop(1, COLORS.vignette + (strength + 0.08) + ")");

    ctx.fillStyle = edgeFade;
    ctx.fillRect(0, 0, w, h);

    var sideFade = ctx.createLinearGradient(0, 0, w, 0);
    sideFade.addColorStop(0, COLORS.vignette + "0.62)");
    sideFade.addColorStop(0.1, "rgba(0,0,0,0)");
    sideFade.addColorStop(0.9, "rgba(0,0,0,0)");
    sideFade.addColorStop(1, COLORS.vignette + "0.62)");

    ctx.fillStyle = sideFade;
    ctx.fillRect(0, 0, w, h);
  };

  TitanNeural.BrainRenderer = BrainRenderer;
})(window);
