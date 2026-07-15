/**
 * Titan Neural Brain Engine — Nodes & Edges
 * Phase 17.4 · Phase 19.1 · Phase 19.2 — infinite wrap, five depth layers
 */
(function (global) {
  "use strict";

  var TitanNeural = (global.TitanNeural = global.TitanNeural || {});
  var CONFIG = TitanNeural.CONFIG;
  var rand = TitanNeural.rand;

  function BrainNodes(camera) {
    this.camera = camera;
    this.nodes = [];
    this.edges = [];
    this.lastNewConnection = 0;
    this.density = CONFIG.nodes.densityDefault;
  }

  BrainNodes.prototype.setDensity = function (density) {
    this.density = density || CONFIG.nodes.densityDefault;
  };

  BrainNodes.prototype.build = function (viewportWidth, viewportHeight) {
    var count = TitanNeural.computeNodeCount(viewportWidth, viewportHeight, this.density);
    var bounds = this.camera.getWorldBounds();
    var layers = CONFIG.layers;
    var nodeCfg = CONFIG.nodes;

    this.nodes = [];
    this.edges = [];

    for (var i = 0; i < count; i++) {
      var layerIdx = this._pickLayer(layers);
      var layer = layers[layerIdx];
      var driftMult = layer.driftMult;

      this.nodes.push({
        id: i,
        x: rand(0, bounds.width),
        y: rand(0, bounds.height),
        vx: rand(nodeCfg.driftSpeedMin, nodeCfg.driftSpeedMax) * driftMult * (Math.random() > 0.5 ? 1 : -1),
        vy: rand(nodeCfg.driftSpeedMin, nodeCfg.driftSpeedMax) * driftMult * (Math.random() > 0.5 ? 1 : -1),
        radius: rand(layer.radiusMin, layer.radiusMax),
        layer: layerIdx,
        depth: layer.depth,
        parallax: layer.parallax,
        baseOpacity: layer.baseOpacity,
        opacity: layer.baseOpacity,
        pulse: rand(0, Math.PI * 2),
        pulseSpeed: rand(nodeCfg.pulseSpeedMin, nodeCfg.pulseSpeedMax),
        glow: 0,
        activation: 0,
      });
    }

    this._buildEdges(viewportWidth, viewportHeight);
  };

  BrainNodes.prototype._wrapNode = function (n, bounds) {
    var margin =
      (CONFIG.infiniteSpace && CONFIG.infiniteSpace.wrapMargin) || 28;
    var spanX = bounds.width + margin * 2;
    var spanY = bounds.height + margin * 2;

    if (n.x < -margin) n.x += spanX;
    if (n.x > bounds.width + margin) n.x -= spanX;
    if (n.y < -margin) n.y += spanY;
    if (n.y > bounds.height + margin) n.y -= spanY;
  };

  BrainNodes.prototype._isDeepLayer = function (layerIdx) {
    return layerIdx <= 1;
  };

  BrainNodes.prototype._isForegroundLayer = function (layerIdx) {
    var layers = CONFIG.layers;
    return layerIdx >= layers.length - 2;
  };

  BrainNodes.prototype._pickLayer = function (layers) {
    var roll = Math.random();
    var cumulative = 0;
    for (var i = 0; i < layers.length; i++) {
      cumulative += layers[i].weight;
      if (roll <= cumulative) return i;
    }
    return layers.length - 1;
  };

  BrainNodes.prototype._buildEdges = function (viewportWidth, viewportHeight) {
    var worldCfg = CONFIG.world;
    var maxDist = Math.min(viewportWidth, viewportHeight) * worldCfg.connectionMaxDistRatio;
    var connectionCounts = {};

    for (var a = 0; a < this.nodes.length; a++) {
      connectionCounts[a] = 0;
    }

    for (var i = 0; i < this.nodes.length; i++) {
      var candidates = [];

      for (var j = i + 1; j < this.nodes.length; j++) {
        var na = this.nodes[i];
        var nb = this.nodes[j];
        var dx = na.x - nb.x;
        var dy = na.y - nb.y;
        var dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < maxDist) {
          candidates.push({ index: j, dist: dist });
        }
      }

      candidates.sort(function (a, b) {
        return a.dist - b.dist;
      });

      for (var c = 0; c < candidates.length; c++) {
        if (connectionCounts[i] >= worldCfg.maxConnectionsPerNode) break;
        var cand = candidates[c];
        if (connectionCounts[cand.index] >= worldCfg.maxConnectionsPerNode) continue;

        if (Math.random() < worldCfg.connectionProbability) {
          var na2 = this.nodes[i];
          var nb2 = this.nodes[cand.index];
          var layerMix = (na2.layer + nb2.layer) / 2;
          var layerCfg = CONFIG.layers[Math.round(layerMix)];

          this.edges.push({
            a: i,
            b: cand.index,
            opacity: rand(0.04, 0.18),
            targetOpacity: rand(0.06, 0.22),
            fadeSpeed: rand(0.0015, 0.005),
            visible: Math.random() > 0.25,
            glow: 0,
            signalProgress: -1,
            layerMix: layerMix,
            edgeOpacity: layerCfg ? layerCfg.edgeOpacity : 0.7,
          });

          connectionCounts[i]++;
          connectionCounts[cand.index]++;
        }
      }
    }
  };

  BrainNodes.prototype.trySpawnConnection = function (timestamp, intensity) {
    var worldCfg = CONFIG.world;
    var interval = intensity > 0.3
      ? worldCfg.newConnectionInterval * 0.4
      : worldCfg.newConnectionInterval;

    if (timestamp - this.lastNewConnection < interval) return;
    if (Math.random() > worldCfg.newConnectionChance) return;

    this.lastNewConnection = timestamp;

    if (this.edges.length === 0) return;

    var edge = this.edges[Math.floor(Math.random() * this.edges.length)];
    edge.visible = true;
    edge.opacity = 0.02;
    edge.targetOpacity = 0.15 + intensity * 0.25;
    edge.glow = 0.1 + intensity * 0.2;
  };

  BrainNodes.prototype.update = function (deltaMs, state) {
    var bounds = this.camera.getWorldBounds();
    var breathe = state.getBreathe();
    var intensity = state.getIntensity();
    var thinking = state.isThinking();
    var nodeCfg = CONFIG.nodes;
    var thinkCfg = CONFIG.thinking;
    var driftBoost = thinking ? thinkCfg.driftBoost : 1;
    var dt = deltaMs / 16.67;

    for (var i = 0; i < this.nodes.length; i++) {
      var n = this.nodes[i];
      var layer = CONFIG.layers[n.layer];

      n.x += n.vx * driftBoost * dt;
      n.y += n.vy * driftBoost * dt;
      n.pulse += n.pulseSpeed * (thinking ? thinkCfg.activityBoost : 1) * dt;

      this._wrapNode(n, bounds);

      var pulseWave = (Math.sin(n.pulse) + 1) * 0.5;
      var breatheMod = 1 + (breathe - 0.5) * nodeCfg.breatheAmplitude;
      var glowMod = n.glow + n.activation * 0.6;
      n.opacity = Math.min(
        0.95,
        (n.baseOpacity + pulseWave * (thinking ? 0.22 : 0.1) + glowMod * 0.4) * breatheMod
      );

      n.glow = Math.max(0, n.glow - CONFIG.signals.nodeGlowDecay * dt * (thinking ? 0.6 : 1));
      n.activation = Math.max(0, n.activation - CONFIG.signals.nodeGlowDecay * 0.7 * dt);
    }

    for (var j = 0; j < this.edges.length; j++) {
      var e = this.edges[j];

      if (!e.visible && Math.random() < 0.0004 * dt) {
        e.visible = true;
        e.opacity = 0.02;
        e.targetOpacity = rand(0.05, 0.15);
      }

      if (e.visible) {
        var diff = e.targetOpacity - e.opacity;
        e.opacity += diff * e.fadeSpeed * (thinking ? 1.8 : 1) * dt;

        if (Math.abs(diff) < 0.008) {
          e.targetOpacity = rand(0.04, thinking ? 0.28 : 0.16);
        }

        if (e.opacity < 0.015 && e.targetOpacity < 0.03 && e.glow < 0.02) {
          e.visible = false;
        }
      }

      e.glow = Math.max(0, e.glow - CONFIG.signals.edgeGlowDecay * dt);
      if (e.signalProgress >= 0) {
        e.glow = Math.max(e.glow, 0.35);
      }
    }
  };

  BrainNodes.prototype.activateNearby = function (originId, viewportWidth, viewportHeight, options) {
    if (originId === undefined || originId < 0 || originId >= this.nodes.length) return;

    var opts = options || {};
    var origin = this.nodes[originId];
    var radius =
      Math.min(viewportWidth, viewportHeight) *
      (opts.radiusRatio || CONFIG.thinking.nearbyRadiusRatio);
    var glow = opts.glow !== undefined ? opts.glow : CONFIG.thinking.nearbyGlow;
    var preferDeep = opts.preferDeep || false;

    for (var i = 0; i < this.nodes.length; i++) {
      var n = this.nodes[i];
      if (preferDeep && !this._isDeepLayer(n.layer)) {
        continue;
      }

      var dx = n.x - origin.x;
      var dy = n.y - origin.y;
      var dist = Math.sqrt(dx * dx + dy * dy);

      if (dist < radius) {
        var falloff = 1 - dist / radius;
        var layerBoost = preferDeep && this._isDeepLayer(n.layer) ? 1.35 : 1;
        n.activation = Math.max(n.activation, glow * falloff * layerBoost);
        n.glow = Math.max(n.glow, glow * falloff * 0.75 * layerBoost);
      }
    }
  };

  BrainNodes.prototype.getNode = function (id) {
    return this.nodes[id];
  };

  BrainNodes.prototype.getRandomNode = function (preferForeground, preferLayer) {
    if (this.nodes.length === 0) return -1;

    if (preferLayer !== undefined && preferLayer !== null) {
      var layerMatches = [];
      for (var k = 0; k < this.nodes.length; k++) {
        if (this.nodes[k].layer === preferLayer) {
          layerMatches.push(k);
        }
      }
      if (layerMatches.length > 0) {
        return layerMatches[Math.floor(Math.random() * layerMatches.length)];
      }
    }

    if (preferForeground) {
      var foreground = [];
      for (var i = 0; i < this.nodes.length; i++) {
        if (this._isForegroundLayer(this.nodes[i].layer)) foreground.push(i);
      }
      if (foreground.length > 0) {
        return foreground[Math.floor(Math.random() * foreground.length)];
      }
    }

    if (preferForeground === false) {
      var background = [];
      for (var j = 0; j < this.nodes.length; j++) {
        if (this._isDeepLayer(this.nodes[j].layer)) background.push(j);
      }
      if (background.length > 0) {
        return background[Math.floor(Math.random() * background.length)];
      }
    }

    return Math.floor(Math.random() * this.nodes.length);
  };

  BrainNodes.prototype.getDeepRecallOrigin = function () {
    var deep = [];
    for (var i = 0; i < this.nodes.length; i++) {
      if (this._isDeepLayer(this.nodes[i].layer)) deep.push(i);
    }
    if (deep.length === 0) {
      return this.getRandomNode(false);
    }
    return deep[Math.floor(Math.random() * deep.length)];
  };

  BrainNodes.prototype.getEdgesForNode = function (nodeId) {
    var result = [];
    for (var i = 0; i < this.edges.length; i++) {
      var e = this.edges[i];
      if (e.a === nodeId || e.b === nodeId) {
        result.push({ edge: e, edgeIndex: i, other: e.a === nodeId ? e.b : e.a });
      }
    }
    return result;
  };

  TitanNeural.BrainNodes = BrainNodes;
})(window);
