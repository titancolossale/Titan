/** Titan Frontend V2 — Tool Activity Engine (Phase E5). */

import {
  blendToolRegions,
  blendToolSignatures,
  DEFAULT_TOOL_REGISTRY,
  getToolDefinition,
  normalizeToolId,
  resolveDominantTool,
} from "./tool-registry.js";

export const TOOL_ACTIVITY_EVENTS = Object.freeze({
  ACTIVATED: "tool_activated",
  DEACTIVATED: "tool_deactivated",
  ACTIVITY: "tool_activity",
  BLEND_UPDATED: "blend_updated",
});

/**
 * @typedef {Object} ToolInstance
 * @property {string} id
 * @property {"idle"|"active"|"progress"|"completing"} state
 * @property {number} activity 0–1
 * @property {number} priority
 * @property {number} energy
 * @property {number} focusWeight
 * @property {string} visualRegion
 * @property {object} definition
 * @property {number} activatedAt
 * @property {string} [statusLine]
 */

/**
 * @typedef {Object} ToolActivityBlend
 * @property {object | null} signature
 * @property {Array<{ id: string, strength: number }>} regions
 * @property {ToolInstance | null} dominant
 * @property {ToolInstance[]} active
 * @property {number} blendWeight
 */

/**
 * Event-driven tool activity hub — every visual change maps to real internal activity.
 */
export class ToolActivityEngine {
  /**
   * @param {{ registry?: Record<string, object> }} [options]
   */
  constructor(options = {}) {
    /** @type {Record<string, object>} */
    this._registry = { ...DEFAULT_TOOL_REGISTRY, ...(options.registry ?? {}) };
    /** @type {Map<string, ToolInstance>} */
    this._active = new Map();
    /** @type {Set<(event: object) => void>} */
    this._listeners = new Set();
    /** @type {ToolActivityBlend | null} */
    this._blend = null;
    /** @type {ReturnType<typeof setInterval> | null} */
    this._pulseTimer = null;
  }

  /**
   * Activate a tool — increases neural region activity without abrupt state replacement.
   * @param {string} toolId
   * @param {{ activity?: number, energy?: number, priority?: number, statusLine?: string, state?: ToolInstance["state"] }} [options]
   * @returns {ToolInstance}
   */
  activateTool(toolId, options = {}) {
    const id = normalizeToolId(toolId);
    const def = getToolDefinition(id, this._registry);

    const existing = this._active.get(id);
    if (existing) {
      existing.state = options.state ?? "progress";
      existing.activity = Math.min(1, (options.activity ?? existing.activity) + 0.08);
      existing.energy = options.energy ?? existing.energy;
      this._emitActivity(existing, "reactivate");
      this._recomputeBlend();
      return existing;
    }

    /** @type {ToolInstance} */
    const instance = {
      id,
      state: options.state ?? "active",
      activity: options.activity ?? def.activityBase ?? 0.6,
      priority: options.priority ?? def.priority ?? 5,
      energy: options.energy ?? def.energy ?? 0.6,
      focusWeight: def.focusWeight ?? 0.7,
      visualRegion: def.visualRegion,
      definition: def,
      activatedAt: performance.now(),
      statusLine: options.statusLine ?? def.startLine,
    };

    this._active.set(id, instance);
    this._emit(TOOL_ACTIVITY_EVENTS.ACTIVATED, instance);
    this._emitActivity(instance, "activate");
    this._recomputeBlend();
    this._ensurePulseLoop();

    return instance;
  }

  /**
   * Deactivate a tool — smooth decay; remaining tools keep blended dominance.
   * @param {string} toolId
   * @returns {boolean}
   */
  deactivateTool(toolId) {
    const id = normalizeToolId(toolId);
    const instance = this._active.get(id);
    if (!instance) return false;

    instance.state = "completing";
    this._emitActivity(instance, "deactivate");
    this._active.delete(id);
    this._emit(TOOL_ACTIVITY_EVENTS.DEACTIVATED, instance);
    this._recomputeBlend();

    if (this._active.size === 0) {
      this._stopPulseLoop();
    }

    return true;
  }

  /** @returns {ToolInstance[]} */
  getActiveTools() {
    return Array.from(this._active.values());
  }

  /**
   * @param {string} toolId
   * @returns {ToolInstance | null}
   */
  getTool(toolId) {
    return this._active.get(normalizeToolId(toolId)) ?? null;
  }

  /** @returns {ToolActivityBlend | null} */
  getBlend() {
    return this._blend;
  }

  /**
   * Subscribe to tool activity events.
   * @param {(event: { type: string, tool: ToolInstance | null, blend: ToolActivityBlend | null, timestamp: number }) => void} callback
   * @returns {() => void}
   */
  onToolActivity(callback) {
    this._listeners.add(callback);
    return () => {
      this._listeners.delete(callback);
    };
  }

  /**
   * Register a future tool — plugs in automatically.
   * @param {string} key
   * @param {object} definition
   */
  registerTool(key, definition) {
    const id = normalizeToolId(key);
    this._registry[id] = {
      ...DEFAULT_TOOL_REGISTRY.chat,
      ...definition,
      id,
    };
  }

  /**
   * Ingest sanitized tool_activity record from Python backend.
   * @param {object} record
   */
  ingest(record) {
    if (!record) return;

    const toolId = record.tool || record.tool_key || record.toolKey || "default";
    const statusLine = record.status_line || record.statusLine || record.title;
    const runId = record.run_id || record.runId;

    if (record.state === "error" || record.success === false) {
      this.activateTool(toolId, { statusLine: statusLine ?? "Action interrompue.", state: "progress" });
      window.setTimeout(() => this.deactivateTool(toolId), 600);
      return;
    }

    this.activateTool(toolId, {
      statusLine: statusLine ?? undefined,
      state: record.state === "running" ? "progress" : "active",
    });

    if (record.state === "complete" || record.state === "completed" || record.success !== false) {
      window.setTimeout(() => this.deactivateTool(toolId), runId ? 900 : 600);
    }
  }

  destroy() {
    this._stopPulseLoop();
    for (const id of [...this._active.keys()]) {
      this.deactivateTool(id);
    }
    this._listeners.clear();
  }

  /** @param {ToolInstance} instance @param {string} phase */
  _emitActivity(instance, phase) {
    this._emit(TOOL_ACTIVITY_EVENTS.ACTIVITY, instance, { phase });
  }

  /** @param {string} type @param {ToolInstance | null} tool @param {object} [extra] */
  _emit(type, tool, extra = {}) {
    const event = {
      type,
      tool,
      blend: this._blend,
      timestamp: performance.now(),
      ...extra,
    };

    for (const listener of this._listeners) {
      try {
        listener(event);
      } catch {
        /* subscriber errors must not break tool flow */
      }
    }
  }

  _recomputeBlend() {
    const active = this.getActiveTools();
    const dominant = resolveDominantTool(active);
    const signature = blendToolSignatures(active);
    const regions = blendToolRegions(active);
    const blendWeight = active.length ? Math.min(1, 0.35 + active.length * 0.12) : 0;

    this._blend = {
      signature,
      regions,
      dominant,
      active,
      blendWeight,
    };

    this._emit(TOOL_ACTIVITY_EVENTS.BLEND_UPDATED, dominant, { blend: this._blend });
  }

  _ensurePulseLoop() {
    if (this._pulseTimer !== null) return;

    this._pulseTimer = window.setInterval(() => {
      if (this._active.size === 0) {
        this._stopPulseLoop();
        return;
      }

      for (const inst of this._active.values()) {
        const base = inst.definition.activityBase ?? 0.5;
        const wave = Math.sin(performance.now() / (inst.definition.pulseIntervalMs ?? 1200)) * 0.06;
        inst.activity = Math.max(0.2, Math.min(1, base + wave));
        inst.state = inst.state === "active" ? "progress" : "active";
      }

      this._recomputeBlend();
    }, 180);
  }

  _stopPulseLoop() {
    if (this._pulseTimer !== null) {
      window.clearInterval(this._pulseTimer);
      this._pulseTimer = null;
    }
  }
}

export { DEFAULT_TOOL_REGISTRY };
