/**
 * Titan Neural Brain Engine — Signals & Waves
 * Phase 17.4 · Phase 19.1 — biological propagation, tool patterns, deep recall
 */
(function (global) {
  "use strict";

  var TitanNeural = (global.TitanNeural = global.TitanNeural || {});
  var CONFIG = TitanNeural.CONFIG;
  var rand = TitanNeural.rand;

  function BrainSignals(nodes) {
    this.nodes = nodes;
    this.signals = [];
    this.waves = [];
    this.lastSpawn = 0;
    this.lastIdlePulse = 0;
    this.lastMicroPulse = 0;
  }

  BrainSignals.prototype.update = function (timestamp, deltaMs, state) {
    var intensity = state.getIntensity();
    var thinking = state.isThinking();
    var sigCfg = CONFIG.signals;
    var dt = deltaMs / 16.67;

    this._spawnSignals(timestamp, intensity, thinking, state);
    this._updateSignals(dt, thinking);
    this._updateWaves(dt);
    this._idlePulse(timestamp, thinking);
    this._microPulse(timestamp, thinking, state);

    var pending = state.consumePendingActivation();
    var waveStyle = state.consumePendingWaveStyle();
    var hookType = state.consumePendingHookType();
    var preferDeep = state.consumePreferDeep();
    var toolPattern = state.consumeToolPattern();

    if (pending === undefined && hookType) {
      if (preferDeep || waveStyle === "deep_central" || waveStyle === "slow") {
        pending = this.nodes.getDeepRecallOrigin();
      } else if (toolPattern === "trading" || toolPattern === "browser") {
        pending = this.nodes.getRandomNode(true);
      } else {
        pending = this.nodes.getRandomNode(thinking);
      }
    }

    if (pending !== undefined) {
      this._activateFromNode(pending, intensity, waveStyle, preferDeep);
    }
  };

  BrainSignals.prototype._spawnSignals = function (timestamp, intensity, thinking, state) {
    var sigCfg = CONFIG.signals;
    var signature = state && state.getCognitiveSignature ? state.getCognitiveSignature() : null;
    var density =
      signature && signature.signalDensity !== undefined
        ? signature.signalDensity
        : state && state.presenceSignalDensity !== undefined
          ? state.presenceSignalDensity
          : 0.35;
    var vitality = state && state.getVitality ? state.getVitality() : 0.15;
    var maxMult = signature && signature.maxSignalsMult ? signature.maxSignalsMult : 1;
    var intervalMult =
      signature && signature.spawnIntervalMult ? signature.spawnIntervalMult : 1;
    var speedMult = signature && signature.speedMult ? signature.speedMult : 1;

    var maxActive = thinking
      ? Math.floor(sigCfg.maxActiveThinking * maxMult)
      : Math.max(sigCfg.maxActiveIdle, Math.floor(sigCfg.maxActiveIdle + density * 2));
    var interval = (thinking ? sigCfg.spawnIntervalThinking : sigCfg.spawnIntervalIdle) * intervalMult;
    interval *= 1.1 - vitality * 0.35;

    if (this.signals.length >= maxActive) return;
    if (timestamp - this.lastSpawn < interval) return;

    this.lastSpawn = timestamp;

    var originId = thinking
      ? this.nodes.getRandomNode(true)
      : this.nodes.getRandomNode(Math.random() > 0.35);
    if (signature && signature.distributedExploration) {
      originId = this.nodes.getRandomNode(true);
    }
    if (signature && signature.distantRegions && Math.random() < 0.55) {
      originId = this.nodes.getDeepRecallOrigin();
    }
    if (originId < 0) return;

    var connections = this.nodes.getEdgesForNode(originId);
    if (connections.length === 0) return;

    var pick = connections[Math.floor(Math.random() * connections.length)];
    if (!pick.edge.visible && !thinking) return;

    this.signals.push({
      edgeIndex: pick.edgeIndex,
      fromNode: originId,
      toNode: pick.other,
      progress: 0,
      speed: rand(sigCfg.speedMin, sigCfg.speedMax) * (thinking ? 1.3 : 0.7) * speedMult,
      strength: thinking ? 0.7 + intensity * 0.3 : 0.25,
      direction: 1,
    });

    var node = this.nodes.getNode(originId);
    if (node) {
      node.glow = Math.max(node.glow, this.signals[this.signals.length - 1].strength * 0.5);
      node.activation = Math.max(node.activation, this.signals[this.signals.length - 1].strength * 0.35);
    }

    if (thinking) {
      this.nodes.activateNearby(originId, this.nodes.camera.width, this.nodes.camera.height);
      var waveStyle = signature && signature.waveStyle ? signature.waveStyle : "default";
      this._spawnWave(originId, intensity, waveStyle);
      if (signature && signature.longPaths && Math.random() < 0.42) {
        this._spawnLongPath(originId, intensity, signature);
      }
    }
  };

  BrainSignals.prototype._spawnLongPath = function (originId, intensity, signature) {
    var connections = this.nodes.getEdgesForNode(originId);
    if (connections.length === 0) {
      return;
    }

    var pick = connections[Math.floor(Math.random() * connections.length)];
    var speedMult = signature && signature.speedMult ? signature.speedMult : 1;
    this.signals.push({
      edgeIndex: pick.edgeIndex,
      fromNode: originId,
      toNode: pick.other,
      progress: 0,
      speed: rand(CONFIG.signals.speedMin, CONFIG.signals.speedMax) * speedMult * 0.72,
      strength: 0.55 + intensity * 0.25,
      direction: 1,
    });
  };

  BrainSignals.prototype._spawnWave = function (originId, intensity, waveStyle) {
    var node = this.nodes.getNode(originId);
    if (!node) return;

    var style = waveStyle || "default";
    var sigCfg = CONFIG.signals;
    var maxRadius = sigCfg.waveRadius * (1 + intensity * 0.5);
    var speed = sigCfg.waveSpeed;
    var strength = 0.25 + intensity * 0.35;
    var aspectX = 1;
    var waveShape = "circle";

    if (style === "horizontal") {
      maxRadius *= 1.55;
      aspectX = 2.1;
      speed *= 0.85;
    } else if (style === "central") {
      maxRadius *= 0.72;
      strength *= 1.45;
      speed *= 0.75;
    } else if (style === "deep_central") {
      maxRadius *= 0.48;
      strength *= 1.85;
      speed *= 0.55;
    } else if (style === "slow") {
      maxRadius *= 1.75;
      strength *= 1.3;
      speed *= 0.42;
    } else if (style === "geometric") {
      maxRadius *= 0.9;
      strength *= 1.15;
      speed *= 0.82;
      waveShape = "geometric";
    } else if (style === "sharp") {
      maxRadius *= 0.55;
      speed *= 1.85;
      strength *= 1.2;
    } else if (style === "circular") {
      maxRadius *= 1.1;
      speed *= 0.95;
    } else if (style === "distributed") {
      maxRadius *= 0.45;
      strength *= 0.7;
      this._spawnDistributedFlashes(intensity);
    }

    this.waves.push({
      x: node.x,
      y: node.y,
      radius: 0,
      maxRadius: maxRadius,
      strength: strength,
      speed: speed,
      aspectX: aspectX,
      shape: waveShape || "circle",
    });
  };

  BrainSignals.prototype._spawnDistributedFlashes = function (intensity) {
    var count = 2 + Math.floor(intensity * 2);
    for (var i = 0; i < count; i++) {
      var nodeId = this.nodes.getRandomNode(true);
      if (nodeId < 0) {
        continue;
      }
      var node = this.nodes.getNode(nodeId);
      if (!node) {
        continue;
      }
      this.waves.push({
        x: node.x,
        y: node.y,
        radius: 0,
        maxRadius: CONFIG.signals.waveRadius * 0.35,
        strength: 0.18 + intensity * 0.2,
        speed: CONFIG.signals.waveSpeed * 1.4,
        aspectX: 1,
      });
    }
  };

  BrainSignals.prototype._activateFromNode = function (nodeId, intensity, waveStyle, preferDeep) {
    var isDeep = preferDeep || waveStyle === "deep_central" || waveStyle === "slow";
    this.nodes.activateNearby(
      nodeId,
      this.nodes.camera.width,
      this.nodes.camera.height,
      {
        preferDeep: isDeep,
        radiusRatio: isDeep ? CONFIG.thinking.nearbyRadiusRatio * 1.35 : undefined,
        glow: isDeep ? CONFIG.thinking.nearbyGlow * 1.2 : undefined,
      }
    );
    this._spawnWave(nodeId, intensity, waveStyle);

    var connections = this.nodes.getEdgesForNode(nodeId);
    var spread = CONFIG.thinking.pathSpreadChance || 0.45;
    var maxBranches = isDeep ? 4 : 3;

    for (var i = 0; i < Math.min(connections.length, maxBranches); i++) {
      var pick = connections[Math.floor(Math.random() * connections.length)];
      this.signals.push({
        edgeIndex: pick.edgeIndex,
        fromNode: nodeId,
        toNode: pick.other,
        progress: 0,
        speed: rand(CONFIG.signals.speedMin, CONFIG.signals.speedMax) * (isDeep ? 0.85 : 1.4),
        strength: isDeep ? 0.65 : 0.8,
        direction: 1,
      });
    }

    if (isDeep && global.TitanNeural && global.TitanNeural.DepthField) {
      /* depth boost handled by engine */
    }
  };

  BrainSignals.prototype._updateSignals = function (dt, thinking) {
    var remaining = [];
    var spreadChance = thinking ? (CONFIG.thinking.pathSpreadChance || 0.45) : 0.32;

    for (var i = 0; i < this.signals.length; i++) {
      var sig = this.signals[i];
      var edge = this.nodes.edges[sig.edgeIndex];
      if (!edge) continue;

      sig.progress += sig.speed * dt * 0.016;

      edge.signalProgress = sig.progress;
      edge.glow = Math.max(edge.glow, sig.strength * (1 - sig.progress) * 0.8);

      var fromNode = this.nodes.getNode(sig.fromNode);
      var toNode = this.nodes.getNode(sig.toNode);

      if (fromNode) {
        fromNode.glow = Math.max(fromNode.glow, sig.strength * 0.4 * (1 - sig.progress));
      }

      if (sig.progress >= 0.5 && toNode) {
        toNode.glow = Math.max(toNode.glow, sig.strength * 0.55);
        toNode.activation = Math.max(toNode.activation, sig.strength * 0.3);
      }

      if (sig.progress >= 1) {
        edge.signalProgress = -1;

        if (toNode && Math.random() < spreadChance) {
          var nextConnections = this.nodes.getEdgesForNode(sig.toNode);
          if (nextConnections.length > 0 && this.signals.length + remaining.length < CONFIG.signals.maxActiveThinking) {
            var next = nextConnections[Math.floor(Math.random() * nextConnections.length)];
            remaining.push({
              edgeIndex: next.edgeIndex,
              fromNode: sig.toNode,
              toNode: next.other,
              progress: 0,
              speed: sig.speed * rand(0.85, 1.1),
              strength: sig.strength * 0.75,
              direction: 1,
            });
          }
        }
      } else {
        remaining.push(sig);
      }
    }

    this.signals = remaining;
  };

  BrainSignals.prototype._updateWaves = function (dt) {
    var sigCfg = CONFIG.signals;
    var remaining = [];

    for (var i = 0; i < this.waves.length; i++) {
      var w = this.waves[i];
      w.radius += w.speed * dt * 60;
      w.strength -= sigCfg.waveDecay * dt;

      if (w.strength > 0.02 && w.radius < w.maxRadius) {
        this._applyWave(w);
        remaining.push(w);
      }
    }

    this.waves = remaining;
  };

  BrainSignals.prototype._applyWave = function (wave) {
    var nodes = this.nodes.nodes;
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      var dx = n.x - wave.x;
      var dy = n.y - wave.y;
      var aspectX = wave.aspectX || 1;
      var dist = Math.sqrt(dx * dx + (dy * dy) / (aspectX * aspectX));
      var band = 18;

      if (Math.abs(dist - wave.radius) < band) {
        var falloff = 1 - Math.abs(dist - wave.radius) / band;
        n.activation = Math.max(n.activation, wave.strength * falloff * 0.5);
      }
    }
  };

  BrainSignals.prototype._idlePulse = function (timestamp, thinking) {
    if (thinking) return;
    if (timestamp - this.lastIdlePulse < 3800) return;

    this.lastIdlePulse = timestamp;

    var nodeId = this.nodes.getRandomNode(false);
    if (nodeId < 0) return;

    var node = this.nodes.getNode(nodeId);
    if (node) {
      node.glow = Math.max(node.glow, 0.14);
      node.pulse = 0;
    }

    if (Math.random() < 0.38) {
      this._spawnWave(nodeId, 0.1, "central");
    }
  };

  BrainSignals.prototype._microPulse = function (timestamp, thinking, state) {
    var interval = CONFIG.signals.microPulseInterval || 1100;
    if (timestamp - this.lastMicroPulse < interval) return;

    this.lastMicroPulse = timestamp;

    var nodeId = this.nodes.getRandomNode(Math.random() > 0.55);
    if (nodeId < 0) return;

    var node = this.nodes.getNode(nodeId);
    if (!node) return;

    var strength = thinking ? 0.18 : 0.08 + (state.getVitality ? state.getVitality() * 0.12 : 0.06);
    node.glow = Math.max(node.glow, strength);

    if (!thinking && Math.random() < 0.22) {
      var connections = this.nodes.getEdgesForNode(nodeId);
      if (connections.length > 0) {
        var pick = connections[Math.floor(Math.random() * connections.length)];
        this.signals.push({
          edgeIndex: pick.edgeIndex,
          fromNode: nodeId,
          toNode: pick.other,
          progress: 0,
          speed: rand(CONFIG.signals.speedMin, CONFIG.signals.speedMax) * 0.55,
          strength: strength,
          direction: 1,
        });
      }
    }
  };

  BrainSignals.prototype.getSignalDrawData = function (camera) {
    var padX = CONFIG.world.padding * camera.width;
    var padY = CONFIG.world.padding * camera.height;
    var result = [];

    for (var i = 0; i < this.signals.length; i++) {
      var sig = this.signals[i];
      var fromNode = this.nodes.getNode(sig.fromNode);
      var toNode = this.nodes.getNode(sig.toNode);
      if (!fromNode || !toNode) continue;

      var pa = camera.worldToScreen(fromNode.x, fromNode.y, fromNode.parallax);
      var pb = camera.worldToScreen(toNode.x, toNode.y, toNode.parallax);
      pa.x -= padX;
      pa.y -= padY;
      pb.x -= padX;
      pb.y -= padY;

      var t = Math.min(1, Math.max(0, sig.progress));
      result.push({
        x: pa.x + (pb.x - pa.x) * t,
        y: pa.y + (pb.y - pa.y) * t,
        strength: sig.strength * (1 - t * 0.35),
        fromX: pa.x,
        fromY: pa.y,
        toX: pb.x,
        toY: pb.y,
        progress: t,
      });
    }

    return result;
  };

  BrainSignals.prototype.getWaves = function () {
    return this.waves;
  };

  BrainSignals.prototype.getActiveCount = function () {
    return this.signals.length;
  };

  TitanNeural.BrainSignals = BrainSignals;
})(window);
