/** Titan Neural Renderer V3 — Electrical propagation along organic axons. */

import { NEURAL_CONFIG } from "./config.js";
import { sampleEdge } from "./bezier.js";
import { NODE_CLASSES } from "./node-classes.js";
import { rand } from "./utils.js";

export class NeuralSignals {
  /**
   * @param {import("./nodes.js").NeuralNodes} nodes
   */
  constructor(nodes) {
    this.nodes = nodes;
    /** @type {Array<object>} */
    this.signals = [];
    /** @type {Array<object>} */
    this.waves = [];
    this.lastSpawn = 0;
    this.lastIdlePulse = 0;
    this.lastMicroPulse = 0;
    this.lastCorePulse = 0;
  }

  /**
   * @param {number} timestamp
   * @param {number} deltaMs
   * @param {import("./state.js").NeuralState} state
   */
  update(timestamp, deltaMs, state) {
    const intensity = state.getIntensity();
    const thinking = state.isThinking();
    const dt = deltaMs / 16.67;
    const signature = state.getCognitiveSignature();
    const fragmented = Boolean(signature?.signalFragmentation);
    const brightness = signature?.signalBrightness ?? 1;
    const nodeMult = signature?.nodeActivityMult ?? 1;
    const connIntensity = signature?.connectionIntensity ?? 0.72;

    this._spawnSignals(timestamp, intensity, thinking, state, brightness, connIntensity);
    this._spawnCoreEmissions(timestamp, intensity, thinking, state);
    this._updateSignals(dt, thinking, fragmented, nodeMult, signature);
    this._updateWaves(dt);

    this._idlePulse(timestamp, thinking);
    this._microPulse(timestamp, thinking, state);

    const pending = state.consumePendingActivation();
    const waveStyle = state.consumePendingWaveStyle();
    const hookType = state.consumePendingHookType();
    const preferDeep = state.consumePreferDeep();
    const toolPattern = state.consumeToolPattern();

    let originId = pending;
    if (originId === undefined && hookType) {
      if (preferDeep || waveStyle === "deep_central" || waveStyle === "slow") {
        originId = this.nodes.getDeepRecallOrigin();
      } else if (toolPattern === "trading" || toolPattern === "browser") {
        originId = this.nodes.getRandomNode(true, null, NODE_CLASSES.TOOL);
      } else if (hookType === "memory_retrieval") {
        originId = this.nodes.getRandomNode(false, null, NODE_CLASSES.MEMORY);
      } else {
        originId = this.nodes.getRandomNode(thinking);
      }
    }

    if (originId !== undefined) {
      this._activateFromNode(originId, intensity, waveStyle, preferDeep, hookType);
    }
  }

  _spawnSignals(timestamp, intensity, thinking, state, brightness = 1, connIntensity = 0.72) {
    const sigCfg = NEURAL_CONFIG.signals;
    const signature = state.getCognitiveSignature();
    const density = signature.signalDensity ?? state.presenceSignalDensity ?? 0.35;
    const vitality = state.getVitality();
    const maxMult = signature.maxSignalsMult ?? 1;
    const intervalMult = signature.spawnIntervalMult ?? 1;
    const speedMult = signature.speedMult ?? 1;

    const maxActive = thinking
      ? Math.floor(sigCfg.maxActiveThinking * maxMult)
      : Math.max(sigCfg.maxActiveIdle, Math.floor(sigCfg.maxActiveIdle + density * 18));
    let interval = (thinking ? sigCfg.spawnIntervalThinking : sigCfg.spawnIntervalIdle) * intervalMult;
    interval *= 1.08 - vitality * 0.38;

    if (this.signals.length >= maxActive) return;
    if (timestamp - this.lastSpawn < interval) return;

    this.lastSpawn = timestamp;

    let originId = thinking
      ? this.nodes.getRandomNode(true)
      : this.nodes.getRandomNode(Math.random() > 0.28);
    if (signature.distributedExploration) {
      originId = this.nodes.getRandomNode(true, null, NODE_CLASSES.TOOL);
    }
    if (signature.distantRegions && Math.random() < 0.58) {
      originId = this.nodes.getDeepRecallOrigin();
    }
    if (originId < 0) return;

    this._emitSignal(originId, intensity, thinking, brightness, connIntensity, speedMult, signature);
  }

  _spawnCoreEmissions(timestamp, intensity, thinking, state) {
    const interval = thinking ? 180 : 920;
    if (timestamp - this.lastCorePulse < interval) return;
    this.lastCorePulse = timestamp;

    const coreId = this.nodes.core.centerNodeId;
    if (coreId == null) return;

    const sigCfg = NEURAL_CONFIG.signals;
    const connections = this.nodes.getEdgesForNode(coreId);
    if (connections.length === 0) return;

    const burst = thinking ? 2 + Math.floor(intensity * 3) : 1;
    for (let i = 0; i < burst; i++) {
      const pick = connections[Math.floor(Math.random() * connections.length)];
      const originNode = this.nodes.getNode(coreId);
      this.signals.push({
        edgeIndex: pick.edgeIndex,
        fromNode: coreId,
        toNode: pick.other,
        progress: 0,
        speed: rand(sigCfg.speedMin, sigCfg.speedMax) * (thinking ? 1.15 : 0.55),
        strength: (thinking ? 0.82 : 0.38) + intensity * 0.18,
        direction: 1,
        colorKey: "redHot",
        fragmented: false,
        trail: rand(0.35, 0.75),
        length: rand(0.6, 1.0),
      });
      if (originNode) {
        originNode.glow = Math.max(originNode.glow, thinking ? 0.75 : 0.42);
        originNode.activation = Math.max(originNode.activation, thinking ? 0.55 : 0.28);
      }
    }
  }

  _emitSignal(originId, intensity, thinking, brightness, connIntensity, speedMult, signature) {
    const connections = this.nodes.getEdgesForNode(originId);
    if (connections.length === 0) return;

    const pick = connections[Math.floor(Math.random() * connections.length)];
    if (!pick.edge.visible && !thinking && Math.random() > 0.35) return;

    const sigCfg = NEURAL_CONFIG.signals;
    const originNode = this.nodes.getNode(originId);
    this.signals.push({
      edgeIndex: pick.edgeIndex,
      fromNode: originId,
      toNode: pick.other,
      progress: 0,
      speed: rand(sigCfg.speedMin, sigCfg.speedMax) * (thinking ? 1.35 : 0.65) * speedMult,
      strength: (thinking ? 0.72 + intensity * 0.28 : 0.22 + intensity * 0.12) * brightness * connIntensity,
      direction: 1,
      colorKey: originNode?.signalColorKey ?? "redGlow",
      fragmented: Boolean(signature?.signalFragmentation),
      trail: rand(0.28, 0.68),
      length: rand(0.45, 1.0),
      accel: rand(-(sigCfg.accelJitter ?? 0.12), sigCfg.accelJitter ?? 0.12),
    });

    const node = this.nodes.getNode(originId);
    if (node) {
      const sig = this.signals[this.signals.length - 1];
      node.glow = Math.max(node.glow, sig.strength * 0.55);
      node.activation = Math.max(node.activation, sig.strength * 0.38);
      node.state = thinking ? "thinking" : "signaling";
    }

    if (thinking) {
      this.nodes.activateNearby(originId, this.nodes.camera.width, this.nodes.camera.height);
      const waveStyle = signature?.waveStyle ?? "default";
      this._spawnWave(originId, intensity, waveStyle);
      if (signature?.longPaths && Math.random() < 0.48) {
        this._spawnLongPath(originId, intensity, signature);
      }
    }
  }

  /**
   * Quiet convergence of an impulse toward Titan Core — selected paths only.
   * @param {number} fromId @param {number} strength @param {boolean} thinking
   */
  _emitTowardCore(fromId, strength, thinking) {
    const coreId = this.nodes.core.centerNodeId;
    if (coreId == null || fromId === coreId) return;

    const connections = this.nodes.getEdgesForNode(fromId);
    let toward = connections.find((c) => c.other === coreId || this.nodes.getNode(c.other)?.isHub);
    if (!toward && connections.length) {
      toward = connections[Math.floor(Math.random() * connections.length)];
    }
    if (!toward) return;

    this.signals.push({
      edgeIndex: toward.edgeIndex,
      fromNode: fromId,
      toNode: toward.other,
      progress: 0,
      speed: rand(NEURAL_CONFIG.signals.speedMin, NEURAL_CONFIG.signals.speedMax) * (thinking ? 0.95 : 0.55),
      strength: Math.min(0.9, strength + 0.12),
      direction: 1,
      colorKey: "redHot",
      trail: 0.55,
      length: 0.9,
      accel: 0.08,
    });
  }

  _spawnLongPath(originId, intensity, signature) {
    const connections = this.nodes.getEdgesForNode(originId);
    if (connections.length === 0) return;
    const pick = connections[Math.floor(Math.random() * connections.length)];
    const speedMult = signature.speedMult ?? 1;
    const originNode = this.nodes.getNode(originId);
    this.signals.push({
      edgeIndex: pick.edgeIndex,
      fromNode: originId,
      toNode: pick.other,
      progress: 0,
      speed: rand(NEURAL_CONFIG.signals.speedMin, NEURAL_CONFIG.signals.speedMax) * speedMult * 0.68,
      strength: 0.58 + intensity * 0.28,
      direction: 1,
      colorKey: originNode?.signalColorKey ?? "redGlow",
      trail: 0.55,
      length: 1.0,
      accel: 0.05,
    });
  }

  _spawnWave(originId, intensity, waveStyle) {
    const node = this.nodes.getNode(originId);
    if (!node) return;

    const style = waveStyle || "default";
    const sigCfg = NEURAL_CONFIG.signals;
    let maxRadius = sigCfg.waveRadius * (1 + intensity * 0.55);
    let speed = sigCfg.waveSpeed;
    let strength = 0.22 + intensity * 0.38;
    let aspectX = 1;
    let waveShape = "circle";

    if (style === "horizontal") {
      maxRadius *= 1.5;
      aspectX = 2.0;
      speed *= 0.82;
    } else if (style === "central") {
      maxRadius *= 0.65;
      strength *= 1.55;
      speed *= 0.68;
    } else if (style === "deep_central") {
      maxRadius *= 0.42;
      strength *= 1.95;
      speed *= 0.48;
    } else if (style === "slow") {
      maxRadius *= 1.65;
      strength *= 1.35;
      speed *= 0.38;
    } else if (style === "sharp") {
      maxRadius *= 0.48;
      speed *= 1.95;
      strength *= 1.25;
    } else if (style === "distributed") {
      maxRadius *= 0.38;
      strength *= 0.65;
      this._spawnDistributedFlashes(intensity);
    }

    this.waves.push({
      x: node.x,
      y: node.y,
      radius: 0,
      maxRadius,
      strength,
      speed,
      aspectX,
      shape: waveShape,
      colorKey: node.signalColorKey,
    });
  }

  _spawnDistributedFlashes(intensity) {
    const count = 2 + Math.floor(intensity * 3);
    for (let i = 0; i < count; i++) {
      const nodeId = this.nodes.getRandomNode(true, null, NODE_CLASSES.TOOL);
      if (nodeId < 0) continue;
      const node = this.nodes.getNode(nodeId);
      if (!node) continue;
      this.waves.push({
        x: node.x,
        y: node.y,
        radius: 0,
        maxRadius: NEURAL_CONFIG.signals.waveRadius * 0.32,
        strength: 0.16 + intensity * 0.22,
        speed: NEURAL_CONFIG.signals.waveSpeed * 1.35,
        aspectX: 1,
        shape: "circle",
        colorKey: node.signalColorKey,
      });
    }
  }

  _activateFromNode(nodeId, intensity, waveStyle, preferDeep, hookType) {
    const isDeep = preferDeep || waveStyle === "deep_central" || waveStyle === "slow";
    const isMemory = hookType === "memory_retrieval";
    this.nodes.activateNearby(nodeId, this.nodes.camera.width, this.nodes.camera.height, {
      preferDeep: isDeep || isMemory,
      radiusRatio: isDeep ? NEURAL_CONFIG.thinking.nearbyRadiusRatio * 1.45 : isMemory ? 0.32 : undefined,
      glow: isDeep ? NEURAL_CONFIG.thinking.nearbyGlow * 1.25 : isMemory ? 0.95 : undefined,
    });
    this._spawnWave(nodeId, intensity, waveStyle);

    const connections = this.nodes.getEdgesForNode(nodeId);
    const maxBranches = isDeep ? 5 : isMemory ? 6 : 4;
    const originNode = this.nodes.getNode(nodeId);

    for (let i = 0; i < Math.min(connections.length, maxBranches); i++) {
      const pick = connections[Math.floor(Math.random() * connections.length)];
      this.signals.push({
        edgeIndex: pick.edgeIndex,
        fromNode: nodeId,
        toNode: pick.other,
        progress: 0,
        speed: rand(NEURAL_CONFIG.signals.speedMin, NEURAL_CONFIG.signals.speedMax) * (isDeep ? 0.78 : 1.35),
        strength: isDeep ? 0.68 : isMemory ? 0.85 : 0.78,
        direction: 1,
        colorKey: isMemory ? "signalMemory" : originNode?.signalColorKey ?? "redGlow",
        trail: rand(0.35, 0.72),
        length: rand(0.55, 1.0),
        accel: rand(-0.05, 0.08),
      });
    }

    if (isMemory && this.nodes.core.centerNodeId != null) {
      const memToCore = this.nodes.getEdgesForNode(nodeId).find((c) => {
        const other = this.nodes.getNode(c.other);
        return other?.nodeClass === NODE_CLASSES.CORE || c.other === this.nodes.core.centerNodeId;
      });
      if (!memToCore) {
        const coreId = this.nodes.core.centerNodeId;
        const edgeIdx = this.nodes._addEdge(nodeId, coreId, {
          opacity: 0.28,
          targetOpacity: 0.55,
          visible: true,
          isCore: true,
          curveStrength: 0.62,
        });
        if (edgeIdx >= 0) {
          this.signals.push({
            edgeIndex: edgeIdx,
            fromNode: nodeId,
            toNode: coreId,
            progress: 0,
            speed: rand(0.28, 0.52),
            strength: 0.92,
            direction: 1,
            colorKey: "signalMemory",
            trail: 0.62,
            length: 1.0,
          });
        }
      }
    }
  }

  _updateSignals(dt, thinking, fragmented = false, nodeMult = 1, signature = null) {
    const remaining = [];
    const spreadChance = thinking ? NEURAL_CONFIG.thinking.pathSpreadChance : 0.38;
    const sigCfg = NEURAL_CONFIG.signals;

    for (const sig of this.signals) {
      const edge = this.nodes.edges[sig.edgeIndex];
      if (!edge) continue;

      if (fragmented && Math.random() < 0.05 * dt) {
        sig.direction *= -1;
        sig.speed *= 0.75 + Math.random() * 0.45;
      }

      if (sig.accel) {
        const jitter = NEURAL_CONFIG.signals.accelJitter ?? 0.12;
        sig.speed = Math.max(
          sigCfg.speedMin * 0.45,
          Math.min(
            sigCfg.speedMax * 1.35,
            sig.speed + sig.accel * dt * 0.0022 + Math.sin(sig.progress * Math.PI) * jitter * 0.0015 * dt,
          ),
        );
        // Natural ease: accelerate mid-path, slow near ends.
        const ease = 0.65 + Math.sin(Math.min(1, Math.abs(sig.progress)) * Math.PI) * 0.45;
        sig.progress += sig.speed * dt * 0.018 * sig.direction * ease;
      } else {
        sig.progress += sig.speed * dt * 0.018 * sig.direction;
      }
      edge.signalProgress = Math.abs(sig.progress);
      edge.glow = Math.max(edge.glow, sig.strength * (1 - Math.abs(sig.progress)) * 0.85);

      const fromNode = this.nodes.getNode(sig.fromNode);
      const toNode = this.nodes.getNode(sig.toNode);

      if (fromNode) {
        fromNode.glow = Math.max(fromNode.glow, sig.strength * 0.45 * nodeMult * (1 - Math.abs(sig.progress)));
        if (fragmented && Math.random() < 0.025 * dt) {
          fromNode.activation = Math.min(1, fromNode.activation + 0.18);
        }
      }

      if (Math.abs(sig.progress) >= 0.48 && toNode) {
        toNode.glow = Math.max(toNode.glow, sig.strength * 0.62 * nodeMult);
        toNode.activation = Math.max(toNode.activation, sig.strength * 0.35 * nodeMult);
      }

      if (Math.abs(sig.progress) >= 1) {
        edge.signalProgress = -1;
        if (fragmented && Math.random() < 0.32) {
          continue;
        }

        // Soft fade — arriving node retains a brief afterglow.
        if (toNode) {
          toNode.glow = Math.max(toNode.glow, sig.strength * 0.35);
          toNode.activation = Math.max(toNode.activation, sig.strength * 0.2);
        }

        const convergeChance = sigCfg.convergeToCoreChance ?? 0.18;
        if (
          Math.random() < convergeChance &&
          this.nodes.core.centerNodeId != null &&
          sig.toNode !== this.nodes.core.centerNodeId
        ) {
          this._emitTowardCore(sig.toNode, sig.strength * 0.7, thinking);
        }

        if (
          thinking &&
          Math.random() < sigCfg.splitChance &&
          this.signals.length + remaining.length < sigCfg.maxActiveThinking
        ) {
          const nextConnections = this.nodes.getEdgesForNode(sig.toNode);
          if (nextConnections.length > 1) {
            const next = nextConnections[Math.floor(Math.random() * nextConnections.length)];
            remaining.push({
              edgeIndex: next.edgeIndex,
              fromNode: sig.toNode,
              toNode: next.other,
              progress: 0,
              speed: sig.speed * rand(0.7, 1.1),
              strength: sig.strength * 0.62,
              direction: 1,
              colorKey: toNode?.signalColorKey ?? "redGlow",
              trail: sig.trail ?? 0.4,
              length: rand(0.4, 0.85),
              accel: rand(-0.1, 0.12),
            });
          }
        }

        if (toNode && Math.random() < spreadChance) {
          const nextConnections = this.nodes.getEdgesForNode(sig.toNode);
          if (
            nextConnections.length > 0 &&
            this.signals.length + remaining.length < sigCfg.maxActiveThinking
          ) {
            const next = nextConnections[Math.floor(Math.random() * nextConnections.length)];
            remaining.push({
              edgeIndex: next.edgeIndex,
              fromNode: sig.toNode,
              toNode: next.other,
              progress: 0,
              speed: sig.speed * rand(0.78, 1.08),
              strength: sig.strength * 0.68,
              direction: 1,
              colorKey: toNode?.signalColorKey ?? "redGlow",
              trail: rand(0.3, 0.65),
              length: rand(0.45, 0.9),
              accel: rand(-0.08, 0.1),
            });
          }
        }
      } else {
        remaining.push(sig);
      }
    }

    this.signals = remaining;
  }

  _updateWaves(dt) {
    const sigCfg = NEURAL_CONFIG.signals;
    const remaining = [];

    for (const w of this.waves) {
      w.radius += w.speed * dt * 58;
      w.strength -= sigCfg.waveDecay * dt;
      if (w.strength > 0.018 && w.radius < w.maxRadius) {
        this._applyWave(w);
        remaining.push(w);
      }
    }

    this.waves = remaining;
  }

  _applyWave(wave) {
    for (const n of this.nodes.nodes) {
      const dx = n.x - wave.x;
      const dy = n.y - wave.y;
      const aspectX = wave.aspectX || 1;
      const dist = Math.sqrt(dx * dx + (dy * dy) / (aspectX * aspectX));
      const band = 22;
      if (Math.abs(dist - wave.radius) < band) {
        const falloff = 1 - Math.abs(dist - wave.radius) / band;
        n.activation = Math.max(n.activation, wave.strength * falloff * 0.55);
      }
    }
  }

  _idlePulse(timestamp, thinking) {
    if (thinking) return;
    if (timestamp - this.lastIdlePulse < 3200) return;
    this.lastIdlePulse = timestamp;

    const nodeId = this.nodes.getRandomNode(false);
    if (nodeId < 0) return;

    const node = this.nodes.getNode(nodeId);
    if (node) {
      node.glow = Math.max(node.glow, 0.16);
      node.pulse = 0;
    }

    if (Math.random() < 0.42) {
      this._spawnWave(nodeId, 0.12, "central");
    }
  }

  _microPulse(timestamp, thinking, state) {
    const interval = NEURAL_CONFIG.signals.microPulseInterval || 480;
    if (timestamp - this.lastMicroPulse < interval) return;
    this.lastMicroPulse = timestamp;

    const nodeId = this.nodes.getRandomNode(Math.random() > 0.48);
    if (nodeId < 0) return;

    const node = this.nodes.getNode(nodeId);
    if (!node) return;

    const strength = thinking ? 0.22 : 0.1 + state.getVitality() * 0.14;
    node.glow = Math.max(node.glow, strength);

    if (Math.random() < 0.32) {
      const connections = this.nodes.getEdgesForNode(nodeId);
      if (connections.length > 0) {
        const pick = connections[Math.floor(Math.random() * connections.length)];
        this.signals.push({
          edgeIndex: pick.edgeIndex,
          fromNode: nodeId,
          toNode: pick.other,
          progress: 0,
          speed: rand(NEURAL_CONFIG.signals.speedMin, NEURAL_CONFIG.signals.speedMax) * 0.52,
          strength,
          direction: 1,
          colorKey: node.signalColorKey,
          trail: 0.35,
          length: 0.65,
        });
      }
    }
  }

  /** @param {import("./camera.js").NeuralCamera} camera */
  getSignalDrawData(camera) {
    const padX = NEURAL_CONFIG.world.padding * camera.width;
    const padY = NEURAL_CONFIG.world.padding * camera.height;
    const segments = NEURAL_CONFIG.signals.trailSegments ?? 6;
    const result = [];

    for (const sig of this.signals) {
      const fromNode = this.nodes.getNode(sig.fromNode);
      const toNode = this.nodes.getNode(sig.toNode);
      const edge = this.nodes.edges[sig.edgeIndex];
      if (!fromNode || !toNode || !edge) continue;

      const t = Math.min(1, Math.max(0, Math.abs(sig.progress)));
      const worldPt = sampleEdge(edge, fromNode, toNode, t);
      const parallax = (fromNode.parallax + toNode.parallax) * 0.5;
      const screen = camera.worldToScreen(worldPt.x, worldPt.y, parallax);
      screen.x -= padX;
      screen.y -= padY;

      const pa = camera.worldToScreen(fromNode.x, fromNode.y, fromNode.parallax);
      const pb = camera.worldToScreen(toNode.x, toNode.y, toNode.parallax);
      pa.x -= padX;
      pa.y -= padY;
      pb.x -= padX;
      pb.y -= padY;

      const trailLen = (sig.trail ?? NEURAL_CONFIG.signals.particleTrail ?? 0.55) * 0.18;
      const trailStart = Math.max(0, t - trailLen);
      /** @type {Array<{ x: number, y: number }>} */
      const trailPoints = [];
      for (let i = 0; i <= segments; i++) {
        const tt = trailStart + (t - trailStart) * (i / segments);
        const pt = sampleEdge(edge, fromNode, toNode, tt);
        const s = camera.worldToScreen(pt.x, pt.y, parallax);
        trailPoints.push({ x: s.x - padX, y: s.y - padY });
      }

      const trailScreen = trailPoints[0] || screen;

      result.push({
        x: screen.x,
        y: screen.y,
        trailX: trailScreen.x,
        trailY: trailScreen.y,
        trailPoints,
        strength: sig.strength * (1 - t * 0.28) * (sig.length ?? 1),
        fromX: pa.x,
        fromY: pa.y,
        toX: pb.x,
        toY: pb.y,
        progress: t,
        colorKey: sig.colorKey ?? "redGlow",
        edge,
        parallax,
      });
    }

    return result;
  }

  getWaves() {
    return this.waves;
  }

  getActiveCount() {
    return this.signals.length;
  }
}
