/**
 * Titan Neural Brain — Depth Field & Infinite Neural Space
 * Phase 19.1 · Phase 19.2 — parallax bands, streaming ghosts, recall dive
 */
(function (global) {
  "use strict";

  var TitanNeural = (global.TitanNeural = global.TitanNeural || {});
  var CONFIG = TitanNeural.CONFIG;
  var rand = TitanNeural.rand;

  var PHASE_19_2_HOOKS = {
    INFINITE_SCROLL: "depth_infinite_scroll",
    PARALLAX_LAYERS: "depth_parallax_layers",
    DEEP_RECALL_CAMERA: "depth_deep_recall_camera",
    FIELD_EXPANSION: "depth_field_expansion",
  };

  function DepthField() {
    this.parallaxBands = [];
    this.voidLines = [];
    this._hookListeners = {};
    this._infiniteEnabled =
      !CONFIG.infiniteSpace || CONFIG.infiniteSpace.enabled !== false;
    this._depthBudget = 1;
    this._recallDepthBoost = 0;
    this._lastBuildW = 0;
    this._lastBuildH = 0;
    this._streamPhase = Math.random() * Math.PI * 2;
  }

  DepthField.prototype.on = function (hookName, callback) {
    if (!this._hookListeners[hookName]) {
      this._hookListeners[hookName] = [];
    }
    this._hookListeners[hookName].push(callback);
  };

  DepthField.prototype.off = function (hookName, callback) {
    var list = this._hookListeners[hookName];
    if (!list) return;
    var idx = list.indexOf(callback);
    if (idx !== -1) list.splice(idx, 1);
  };

  DepthField.prototype._emit = function (hookName, payload) {
    var list = this._hookListeners[hookName];
    if (!list) return;
    for (var i = 0; i < list.length; i++) {
      try {
        list[i](payload);
      } catch (_err) {
        /* depth hooks must not break render loop */
      }
    }
  };

  DepthField.prototype.setInfiniteEnabled = function (enabled) {
    this._infiniteEnabled = !!enabled;
    this._emit(PHASE_19_2_HOOKS.INFINITE_SCROLL, { enabled: this._infiniteEnabled });
  };

  DepthField.prototype.setDepthBudget = function (budget) {
    this._depthBudget = Math.max(0, Math.min(1, budget || 1));
    this._emit(PHASE_19_2_HOOKS.PARALLAX_LAYERS, { budget: this._depthBudget });
  };

  DepthField.prototype.getHooks = function () {
    return PHASE_19_2_HOOKS;
  };

  DepthField.prototype.getRecallDive = function () {
    return this._recallDepthBoost;
  };

  DepthField.prototype.boostRecallDepth = function (amount) {
    this._recallDepthBoost = Math.min(1, this._recallDepthBoost + (amount || 0.35));
    this._emit(PHASE_19_2_HOOKS.DEEP_RECALL_CAMERA, {
      boost: this._recallDepthBoost,
    });
  };

  DepthField.prototype._spawnStreamNode = function (band, camera, edge) {
    var bounds = camera.getWorldBounds();
    var w = camera.width;
    var h = camera.height;
    var margin =
      (CONFIG.depth && CONFIG.depth.streamRespawnMargin) || 0.18;
    var gx;
    var gy;

    if (edge === 0) {
      gx = rand(-margin * w, bounds.width + margin * w);
      gy = rand(-margin * h * 1.2, -margin * h * 0.2);
    } else if (edge === 1) {
      gx = rand(bounds.width + margin * w * 0.2, bounds.width + margin * w * 1.2);
      gy = rand(-margin * h * 0.2, bounds.height + margin * h * 0.2);
    } else if (edge === 2) {
      gx = rand(-margin * w, bounds.width + margin * w);
      gy = rand(bounds.height + margin * h * 0.2, bounds.height + margin * h * 1.2);
    } else {
      gx = rand(-margin * w * 1.2, -margin * w * 0.2);
      gy = rand(-margin * h * 0.2, bounds.height + margin * h * 0.2);
    }

    var speed = band.speedMult * rand(0.008, 0.022);
    var angle = rand(0, Math.PI * 2);

    return {
      x: gx,
      y: gy,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      radius: rand(band.radiusMin, band.radiusMax),
      depth: band.parallax,
      pulse: rand(0, Math.PI * 2),
      pulseSpeed: rand(0.002, 0.006),
      opacity: rand(band.opacityMin, band.opacityMax),
      currentOpacity: 0,
      bandId: band.id,
    };
  };

  DepthField.prototype.build = function (camera) {
    if (!camera) return;

    var w = camera.width;
    var h = camera.height;
    if (w === this._lastBuildW && h === this._lastBuildH && this.parallaxBands.length > 0) {
      return;
    }

    this._lastBuildW = w;
    this._lastBuildH = h;
    var depthCfg = CONFIG.depth || {};
    var bandDefs = depthCfg.parallaxBands || [];
    var bounds = camera.getWorldBounds();

    this.parallaxBands = [];
    this.voidLines = [];

    for (var b = 0; b < bandDefs.length; b++) {
      var def = bandDefs[b];
      var band = {
        id: def.id,
        parallax: def.parallax,
        speedMult: def.speedMult,
        nodes: [],
      };

      for (var i = 0; i < def.nodeCount; i++) {
        band.nodes.push(this._spawnStreamNode(def, camera, i % 4));
      }

      this.parallaxBands.push(band);
    }

    var lineCount = depthCfg.voidLineCount || 18;
    for (var j = 0; j < lineCount; j++) {
      var bandIdx = j % Math.max(this.parallaxBands.length, 1);
      var srcBand = this.parallaxBands[bandIdx];
      if (!srcBand || srcBand.nodes.length === 0) continue;

      var node = srcBand.nodes[j % srcBand.nodes.length];
      var angle = rand(0, Math.PI * 2);
      var length = rand(w * 0.1, w * 0.42);

      this.voidLines.push({
        x: node.x,
        y: node.y,
        dx: Math.cos(angle) * length,
        dy: Math.sin(angle) * length,
        depth: node.depth,
        parallax: srcBand.parallax,
        opacity: rand(0.025, 0.11),
        bandIdx: bandIdx,
      });
    }

    this._emit(PHASE_19_2_HOOKS.FIELD_EXPANSION, {
      width: w,
      height: h,
      bands: this.parallaxBands.length,
    });
  };

  DepthField.prototype._respawnIfNeeded = function (node, band, camera) {
    var padX = CONFIG.world.padding * camera.width;
    var padY = CONFIG.world.padding * camera.height;
    var screen = camera.worldToScreen(node.x, node.y, band.parallax);
    screen.x -= padX;
    screen.y -= padY;

    var margin = 60;
    var off =
      screen.x < -margin ||
      screen.x > camera.width + margin ||
      screen.y < -margin ||
      screen.y > camera.height + margin;

    if (!off) return;

    var bandDef = null;
    var bandDefs = CONFIG.depth.parallaxBands || [];
    for (var d = 0; d < bandDefs.length; d++) {
      if (bandDefs[d].id === band.id) {
        bandDef = bandDefs[d];
        break;
      }
    }
    if (!bandDef) return;

    var edge = Math.floor(Math.random() * 4);
    var fresh = this._spawnStreamNode(bandDef, camera, edge);
    node.x = fresh.x;
    node.y = fresh.y;
    node.vx = fresh.vx;
    node.vy = fresh.vy;
    node.radius = fresh.radius;
    node.opacity = fresh.opacity;
    node.pulse = fresh.pulse;
  };

  DepthField.prototype.update = function (deltaMs, camera, state) {
    if (!camera) return;

    this.build(camera);

    var dt = deltaMs / 16.67;
    var breathe = state && state.getBreathe ? state.getBreathe() : 0.5;
    var intensity = state && state.getIntensity ? state.getIntensity() : 0;
    var parallaxCfg = CONFIG.parallax || {};
    var movementSpread = parallaxCfg.movementSpread || 1.35;

    this._recallDepthBoost = Math.max(0, this._recallDepthBoost - 0.0038 * dt);
    this._streamPhase += 0.0012 * dt;

    var cameraOffset = camera.getOffset();
    var driftInfluence = Math.sqrt(
      cameraOffset.x * cameraOffset.x + cameraOffset.y * cameraOffset.y
    );

    for (var b = 0; b < this.parallaxBands.length; b++) {
      var band = this.parallaxBands[b];
      var parallaxMove = band.parallax * movementSpread;

      for (var i = 0; i < band.nodes.length; i++) {
        var g = band.nodes[i];
        g.x += g.vx * dt * parallaxMove * (0.55 + breathe * 0.45);
        g.y += g.vy * dt * parallaxMove * (0.55 + breathe * 0.45);
        g.pulse += g.pulseSpeed * dt;

        if (this._infiniteEnabled) {
          this._respawnIfNeeded(g, band, camera);
        }

        var pulseWave = (Math.sin(g.pulse + this._streamPhase) + 1) * 0.5;
        var farDim = 1 - band.parallax * (1 - (parallaxCfg.farDimFactor || 0.42));
        g.currentOpacity =
          g.opacity *
          farDim *
          (0.65 + pulseWave * 0.35) *
          (1 + intensity * 0.22 + this._recallDepthBoost * 0.55);
      }
    }

    for (var j = 0; j < this.voidLines.length; j++) {
      var line = this.voidLines[j];
      var srcBand = this.parallaxBands[line.bandIdx];
      if (srcBand && srcBand.nodes.length > 0) {
        var anchor = srcBand.nodes[j % srcBand.nodes.length];
        line.x = anchor.x;
        line.y = anchor.y;
      }
      line.depth = line.parallax + driftInfluence * 0.00008;
    }

    if (this._recallDepthBoost > 0.05) {
      this._emit(PHASE_19_2_HOOKS.DEEP_RECALL_CAMERA, {
        dive: this._recallDepthBoost,
      });
    }
  };

  DepthField.prototype.draw = function (ctx, camera, w, h) {
    if (!ctx || !camera || this._depthBudget <= 0) return;

    var COLORS = CONFIG.colors;
    var padX = CONFIG.world.padding * camera.width;
    var padY = CONFIG.world.padding * camera.height;
    var budget = this._depthBudget * (0.82 + this._recallDepthBoost * 0.42);
    var fadeStrength = (CONFIG.depth && CONFIG.depth.voidLineFadeStrength) || 0.88;
    var parallaxCfg = CONFIG.parallax || {};

    ctx.save();

    for (var li = 0; li < this.voidLines.length; li++) {
      var line = this.voidLines[li];
      var lineParallax = 0.28 + line.depth * 0.55;
      var start = camera.worldToScreen(line.x, line.y, lineParallax);
      start.x -= padX;
      start.y -= padY;

      var endX = start.x + line.dx * (0.35 + line.depth * 0.45);
      var endY = start.y + line.dy * (0.35 + line.depth * 0.45);

      var lineAlpha = line.opacity * budget * (0.5 + line.depth * 0.5);
      var grad = ctx.createLinearGradient(start.x, start.y, endX, endY);
      grad.addColorStop(0, COLORS.redGlow + lineAlpha * 0.55 + ")");
      grad.addColorStop(0.25, COLORS.redCore + lineAlpha * 0.22 + ")");
      grad.addColorStop(0.55, COLORS.redGlow + lineAlpha * 0.08 + ")");
      grad.addColorStop(1, "rgba(0, 0, 0, " + fadeStrength + ")");

      ctx.beginPath();
      ctx.moveTo(start.x, start.y);
      ctx.lineTo(endX, endY);
      ctx.strokeStyle = grad;
      ctx.lineWidth = 0.28 + line.depth * 0.22;
      ctx.stroke();
    }

    for (var b = 0; b < this.parallaxBands.length; b++) {
      var band = this.parallaxBands[b];
      var nearBoost =
        band.parallax > 0.55 ? parallaxCfg.nearBrightnessBoost || 1.18 : 1;

      for (var j = 0; j < band.nodes.length; j++) {
        var g = band.nodes[j];
        var screenParallax = 0.22 + g.depth * 0.62;
        var screen = camera.worldToScreen(g.x, g.y, screenParallax);
        screen.x -= padX;
        screen.y -= padY;

        var alpha = Math.min(g.currentOpacity * budget * nearBoost, 0.24);
        var fogDim = 1 - g.depth * (1 - (parallaxCfg.farDimFactor || 0.42));

        ctx.beginPath();
        ctx.arc(screen.x, screen.y, g.radius * (0.85 + g.depth * 0.35), 0, Math.PI * 2);
        ctx.fillStyle = COLORS.whiteDim + alpha * fogDim + ")";
        ctx.fill();
      }
    }

    this._drawInfiniteVoid(ctx, w, h, budget);
    ctx.restore();
  };

  DepthField.prototype._drawInfiniteVoid = function (ctx, w, h, budget) {
    var COLORS = CONFIG.colors;
    var cx = w * 0.5;
    var cy = h * 0.44;
    var recallPull = this._recallDepthBoost * 0.06;

    var voidGrad = ctx.createRadialGradient(
      cx,
      cy,
      w * (0.04 + recallPull),
      cx,
      cy,
      w * (0.92 + recallPull * 0.08)
    );
    voidGrad.addColorStop(0, "rgba(0, 0, 0, 0)");
    voidGrad.addColorStop(0.48, "rgba(0, 0, 0, " + 0.06 * budget + ")");
    voidGrad.addColorStop(0.72, "rgba(0, 0, 0, " + 0.22 * budget + ")");
    voidGrad.addColorStop(0.9, "rgba(0, 0, 0, " + 0.38 * budget + ")");
    voidGrad.addColorStop(1, COLORS.vignette + 0.58 * budget + ")");

    ctx.fillStyle = voidGrad;
    ctx.fillRect(0, 0, w, h);

    if (this._infiniteEnabled) {
      this._drawEdgeContinuity(ctx, w, h, budget);
    }
  };

  DepthField.prototype._drawEdgeContinuity = function (ctx, w, h, budget) {
    var COLORS = CONFIG.colors;
    var edges = [
      { x0: 0, y0: 0, x1: w * 0.22, y1: 0 },
      { x0: w, y0: 0, x1: w * 0.78, y1: 0 },
      { x0: 0, y0: 0, x1: 0, y1: h * 0.18 },
      { x0: 0, y0: h, x1: 0, y1: h * 0.82 },
      { x0: w, y0: h, x1: w, y1: h * 0.82 },
      { x0: w, y0: 0, x1: w, y1: h * 0.18 },
    ];

    ctx.save();
    ctx.globalAlpha = 0.14 * budget;

    for (var i = 0; i < edges.length; i++) {
      var e = edges[i];
      var grad = ctx.createLinearGradient(e.x0, e.y0, e.x1, e.y1);
      grad.addColorStop(0, COLORS.redGlow + "0.18)");
      grad.addColorStop(1, "rgba(0, 0, 0, 0)");

      ctx.beginPath();
      ctx.moveTo(e.x0, e.y0);
      ctx.lineTo(e.x1, e.y1);
      ctx.strokeStyle = grad;
      ctx.lineWidth = 1.2;
      ctx.stroke();
    }

    ctx.restore();
  };

  TitanNeural.DepthField = DepthField;
  TitanNeural.DEPTH_HOOKS = PHASE_19_2_HOOKS;
})(window);
