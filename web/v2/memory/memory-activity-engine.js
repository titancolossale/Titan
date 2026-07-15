/** Titan Frontend V2 — Memory Activity Engine (Phase E6). */

import {
  blendMemorySignatures,
  DEFAULT_MEMORY_REGISTRY,
  getMemoryDefinition,
  mapMemoryToRegions,
  MEMORY_ACTIVITY_EVENTS,
  normalizeMemoryType,
} from "./memory-registry.js";

export { MEMORY_ACTIVITY_EVENTS, DEFAULT_MEMORY_REGISTRY, MEMORY_TYPES } from "./memory-registry.js";

/**
 * @typedef {Object} MemoryRecord
 * @property {string} id
 * @property {string} type
 * @property {number} importance 0–1
 * @property {number} age ms since creation
 * @property {string} source
 * @property {number} energy 0–1
 * @property {string[]} relationships
 * @property {number} focusWeight 0–1
 * @property {number} createdAt
 * @property {"active"|"archived"|"fading"|"pending_delete"} [state]
 */

/**
 * @typedef {Object} MemoryActivityBlend
 * @property {object | null} signature
 * @property {Array<{ id: string, strength: number }>} regions
 * @property {MemoryRecord | null} dominant
 * @property {MemoryRecord[]} active
 * @property {string | null} eventType
 * @property {number} blendWeight
 * @property {string} [statusLine]
 * @property {string} [hook]
 */

let _memoryIdCounter = 0;

/** @returns {string} */
function nextMemoryId() {
  _memoryIdCounter += 1;
  return `mem-${Date.now().toString(36)}-${_memoryIdCounter}`;
}

/**
 * Event-driven memory activity hub — memory is a living cognitive process, not a panel.
 */
export class MemoryActivityEngine {
  /**
   * @param {{ registry?: Record<string, object> }} [options]
   */
  constructor(options = {}) {
    /** @type {Record<string, object>} */
    this._registry = { ...DEFAULT_MEMORY_REGISTRY, ...(options.registry ?? {}) };
    /** @type {Map<string, MemoryRecord>} */
    this._memories = new Map();
    /** @type {Array<{ eventType: string, memory: MemoryRecord, weight: number, startedAt: number }>} */
    this._activeEvents = [];
    /** @type {Set<(event: object) => void>} */
    this._listeners = new Set();
    /** @type {MemoryActivityBlend | null} */
    this._blend = null;
    /** @type {ReturnType<typeof setInterval> | null} */
    this._pulseTimer = null;
    /** @type {Map<string, ReturnType<typeof setTimeout>>} */
    this._fadeTimers = new Map();
  }

  /**
   * Create a new memory — pulse expands outward; nearby nodes acknowledge.
   * @param {{ type?: string, source?: string, importance?: number, energy?: number, focusWeight?: number, relationships?: string[] }} [options]
   * @returns {MemoryRecord}
   */
  create(options = {}) {
    const type = normalizeMemoryType(options.type ?? options.source ?? "long_term");
    const def = getMemoryDefinition(type, this._registry);
    const now = performance.now();

    /** @type {MemoryRecord} */
    const memory = {
      id: options.id ?? nextMemoryId(),
      type,
      importance: options.importance ?? def.importanceBase ?? 0.6,
      age: 0,
      source: options.source ?? type,
      energy: options.energy ?? def.importanceBase ?? 0.6,
      relationships: options.relationships ?? [],
      focusWeight: options.focusWeight ?? def.focusWeight ?? 0.65,
      createdAt: now,
      state: "active",
    };

    this._memories.set(memory.id, memory);
    this._trackEvent(MEMORY_ACTIVITY_EVENTS.CREATED, memory, 0.85);
    this._emit(MEMORY_ACTIVITY_EVENTS.CREATED, memory, {
      statusLine: `${def.icon} ${def.title} — nouveau souvenir`,
    });
    return memory;
  }

  /**
   * Update an existing memory.
   * @param {string} memoryId
   * @param {{ importance?: number, energy?: number, focusWeight?: number, relationships?: string[], type?: string }} [patch]
   * @returns {MemoryRecord | null}
   */
  update(memoryId, patch = {}) {
    const memory = this._memories.get(memoryId);
    if (!memory || memory.state === "pending_delete") return null;

    if (patch.type) memory.type = normalizeMemoryType(patch.type);
    if (patch.importance !== undefined) memory.importance = patch.importance;
    if (patch.energy !== undefined) memory.energy = patch.energy;
    if (patch.focusWeight !== undefined) memory.focusWeight = patch.focusWeight;
    if (patch.relationships) memory.relationships = patch.relationships;
    memory.age = performance.now() - memory.createdAt;

    const def = getMemoryDefinition(memory.type, this._registry);
    this._trackEvent(MEMORY_ACTIVITY_EVENTS.UPDATED, memory, 0.65);
    this._emit(MEMORY_ACTIVITY_EVENTS.UPDATED, memory, {
      statusLine: `${def.icon} ${def.title} — mis à jour`,
    });
    return memory;
  }

  /**
   * Recall a memory — deep recall waves, camera dive, ghost activity.
   * @param {string} memoryId
   * @param {{ source?: string }} [options]
   * @returns {MemoryRecord | null}
   */
  recall(memoryId, options = {}) {
    let memory = this._memories.get(memoryId);
    if (!memory) {
      memory = this.create({
        id: memoryId,
        type: options.source ?? "long_term",
        source: options.source,
      });
    }
    if (memory.state === "archived") {
      memory.state = "active";
    }
    memory.age = performance.now() - memory.createdAt;
    memory.energy = Math.min(1, memory.energy + 0.12);

    const def = getMemoryDefinition(memory.type, this._registry);
    this._trackEvent(MEMORY_ACTIVITY_EVENTS.RECALLED, memory, 0.95);
    this._emit(MEMORY_ACTIVITY_EVENTS.RECALLED, memory, {
      statusLine: def.statusLine ?? "Souvenirs retrouvés…",
      hook: "memory_retrieval",
    });
    return memory;
  }

  /**
   * Search memories — wide distributed exploration, scanning pulses.
   * @param {string} [query]
   * @param {{ type?: string, source?: string }} [options]
   * @returns {MemoryRecord}
   */
  search(query = "", options = {}) {
    const type = normalizeMemoryType(options.type ?? options.source ?? "long_term");
    const def = getMemoryDefinition(type, this._registry);

    /** @type {MemoryRecord} */
    const probe = {
      id: nextMemoryId(),
      type,
      importance: 0.42,
      age: 0,
      source: options.source ?? type,
      energy: 0.55,
      relationships: [],
      focusWeight: 0.48,
      createdAt: performance.now(),
      state: "active",
    };

    this._trackEvent(MEMORY_ACTIVITY_EVENTS.SEARCH, probe, 0.72);
    this._emit(MEMORY_ACTIVITY_EVENTS.SEARCH, probe, {
      statusLine: query ? `${def.searchLine ?? def.statusLine} « ${query.slice(0, 48)} »` : def.statusLine,
      query,
      hook: "memory_retrieval",
    });
    return probe;
  }

  /**
   * Link two memories — bright connections, relationship graph glow.
   * @param {string} memoryIdA
   * @param {string} memoryIdB
   * @param {{ strength?: number }} [options]
   * @returns {{ a: MemoryRecord, b: MemoryRecord } | null}
   */
  link(memoryIdA, memoryIdB, options = {}) {
    const a = this._memories.get(memoryIdA);
    const b = this._memories.get(memoryIdB);
    if (!a || !b) return null;

    if (!a.relationships.includes(memoryIdB)) a.relationships.push(memoryIdB);
    if (!b.relationships.includes(memoryIdA)) b.relationships.push(memoryIdA);

    const strength = options.strength ?? 0.75;
    a.energy = Math.min(1, a.energy + strength * 0.08);
    b.energy = Math.min(1, b.energy + strength * 0.08);

    const bridge = a.focusWeight >= b.focusWeight ? a : b;
    this._trackEvent(MEMORY_ACTIVITY_EVENTS.LINKED, bridge, strength);
    this._emit(MEMORY_ACTIVITY_EVENTS.LINKED, bridge, {
      linkedWith: memoryIdB,
      statusLine: "◈ Connexions mémorielles — graphe actif",
    });
    return { a, b };
  }

  /**
   * Summarize multiple memories — signals merge into stable cluster.
   * @param {string[]} memoryIds
   * @param {{ label?: string }} [options]
   * @returns {MemoryRecord | null}
   */
  summarize(memoryIds = [], options = {}) {
    const sources = memoryIds
      .map((id) => this._memories.get(id))
      .filter(Boolean);

    /** @type {MemoryRecord} */
    const summary = {
      id: nextMemoryId(),
      type: "long_term",
      importance: 0.82,
      age: 0,
      source: "summary",
      energy: 0.78,
      relationships: memoryIds.slice(),
      focusWeight: 0.85,
      createdAt: performance.now(),
      state: "active",
    };

    this._memories.set(summary.id, summary);
    const avgImportance =
      sources.length > 0
        ? sources.reduce((s, m) => s + m.importance, 0) / sources.length
        : 0.7;
    summary.importance = avgImportance;

    this._trackEvent(MEMORY_ACTIVITY_EVENTS.SUMMARY, summary, 0.88);
    this._emit(MEMORY_ACTIVITY_EVENTS.SUMMARY, summary, {
      sourceCount: sources.length,
      statusLine: options.label ?? "◈ Synthèse mémorielle — cluster stable",
    });
    return summary;
  }

  /**
   * Archive a memory — node fades deeper into background layers.
   * @param {string} memoryId
   * @returns {MemoryRecord | null}
   */
  archive(memoryId) {
    const memory = this._memories.get(memoryId);
    if (!memory) return null;

    memory.state = "archived";
    memory.energy *= 0.35;
    memory.focusWeight *= 0.4;

    this._trackEvent(MEMORY_ACTIVITY_EVENTS.ARCHIVED, memory, 0.55, 4200);
    this._emit(MEMORY_ACTIVITY_EVENTS.ARCHIVED, memory, {
      statusLine: "◌ Archivé — recul dans les profondeurs",
    });

    this._scheduleEventDecay(memoryId, MEMORY_ACTIVITY_EVENTS.ARCHIVED, 4200);
    return memory;
  }

  /**
   * Delete a memory — fade only after confirmation; never abrupt.
   * @param {string} memoryId
   * @param {{ confirmed?: boolean }} [options]
   * @returns {MemoryRecord | null}
   */
  delete(memoryId, options = {}) {
    const memory = this._memories.get(memoryId);
    if (!memory) return null;

    if (!options.confirmed) {
      memory.state = "pending_delete";
      memory.energy *= 0.5;
      this._trackEvent(MEMORY_ACTIVITY_EVENTS.DELETED, memory, 0.35, 2800);
      this._emit(MEMORY_ACTIVITY_EVENTS.DELETED, memory, {
        pending: true,
        statusLine: "◌ Effacement en attente de confirmation…",
      });
      return memory;
    }

    memory.state = "fading";
    memory.energy *= 0.15;
    this._trackEvent(MEMORY_ACTIVITY_EVENTS.DELETED, memory, 0.45, 3600);
    this._emit(MEMORY_ACTIVITY_EVENTS.DELETED, memory, {
      confirmed: true,
      statusLine: "◌ Souvenir effacé — dissolution lente",
    });

    const timer = window.setTimeout(() => {
      this._memories.delete(memoryId);
      this._activeEvents = this._activeEvents.filter((e) => e.memory.id !== memoryId);
      this._recomputeBlend();
      this._fadeTimers.delete(memoryId);
    }, 3600);
    this._fadeTimers.set(memoryId, timer);

    this._scheduleEventDecay(memoryId, MEMORY_ACTIVITY_EVENTS.DELETED, 3600);
    return memory;
  }

  /** @returns {MemoryRecord[]} */
  getActiveMemories() {
    return Array.from(this._memories.values()).filter(
      (m) => m.state === "active" || m.state === "fading",
    );
  }

  /** @param {string} memoryId @returns {MemoryRecord | null} */
  getMemory(memoryId) {
    return this._memories.get(memoryId) ?? null;
  }

  /** @returns {MemoryActivityBlend | null} */
  getBlend() {
    return this._blend;
  }

  /**
   * Subscribe to memory activity events.
   * @param {(event: { type: string, memory: MemoryRecord | null, blend: MemoryActivityBlend | null, timestamp: number }) => void} callback
   * @returns {() => void}
   */
  onMemoryActivity(callback) {
    this._listeners.add(callback);
    return () => {
      this._listeners.delete(callback);
    };
  }

  /**
   * Register a future memory source — plugs in automatically.
   * @param {string} key
   * @param {object} definition
   */
  registerSource(key, definition) {
    const id = normalizeMemoryType(key);
    this._registry[id] = {
      ...DEFAULT_MEMORY_REGISTRY.default,
      ...definition,
      id,
    };
  }

  /**
   * Ingest sanitized memory_activity record from Python backend.
   * @param {object} record
   */
  ingest(record) {
    if (!record) return;

    const phase = record.phase || "search";
    const source = record.source || "long_term";
    const statusLine = record.status_line || record.statusLine;

    if (phase === "search") {
      this.search(record.title || statusLine || "", {
        source,
        type: source,
      });
      return;
    }

    if (phase === "recall") {
      const memory = this.recall(source, { source });
      if (statusLine) {
        this._emit(MEMORY_ACTIVITY_EVENTS.RECALLED, memory, {
          statusLine,
          hook: "memory_retrieval",
          cards: record.cards,
        });
      }
      return;
    }

    if (phase === "complete" || record.state === "complete") {
      this._activeEvents = [];
      this._recomputeBlend();
    }
  }

  destroy() {
    this._stopPulseLoop();
    for (const timer of this._fadeTimers.values()) {
      window.clearTimeout(timer);
    }
    this._fadeTimers.clear();
    this._memories.clear();
    this._activeEvents = [];
    this._blend = null;
    this._listeners.clear();
  }

  /** @param {string} eventType @param {MemoryRecord} memory @param {number} weight @param {number} [durationMs] */
  _trackEvent(eventType, memory, weight, durationMs = 3200) {
    this._activeEvents.push({
      eventType,
      memory,
      weight,
      startedAt: performance.now(),
    });

    this._recomputeBlend();
    this._ensurePulseLoop();
    this._scheduleEventDecay(memory.id, eventType, durationMs);
  }

  /** @param {string} memoryId @param {string} eventType @param {number} durationMs */
  _scheduleEventDecay(memoryId, eventType, durationMs) {
    window.setTimeout(() => {
      this._activeEvents = this._activeEvents.filter(
        (e) => !(e.memory.id === memoryId && e.eventType === eventType),
      );
      if (this._activeEvents.length === 0) {
        this._stopPulseLoop();
      }
      this._recomputeBlend();
      this._emit(MEMORY_ACTIVITY_EVENTS.BLEND_UPDATED, this._blend?.dominant ?? null, {
        phase: "decay",
      });
    }, durationMs);
  }

  /** @param {string} type @param {MemoryRecord | null} memory @param {object} [extra] */
  _emit(type, memory, extra = {}) {
    const event = {
      type,
      memory,
      blend: this._blend,
      timestamp: performance.now(),
      ...extra,
    };

    for (const listener of this._listeners) {
      try {
        listener(event);
      } catch {
        /* subscriber errors must not break memory flow */
      }
    }
  }

  _recomputeBlend() {
    const now = performance.now();
    const activeEvents = this._activeEvents.filter((e) => now - e.startedAt < 8000);

    if (activeEvents.length !== this._activeEvents.length) {
      this._activeEvents = activeEvents;
    }

    const signature = blendMemorySignatures(activeEvents);
    const dominantEntry = activeEvents.reduce(
      (best, cur) => ((cur.weight ?? 0) > (best?.weight ?? 0) ? cur : best),
      /** @type {typeof activeEvents[0] | null} */ (null),
    );
    const dominant = dominantEntry?.memory ?? null;
    const eventType = dominantEntry?.eventType ?? null;

    let regions = [];
    if (dominant) {
      regions = mapMemoryToRegions(dominant.type);
      if (dominantEntry?.eventType === MEMORY_ACTIVITY_EVENTS.LINKED) {
        regions.push({ id: "memory", strength: 0.95 });
        regions.push({ id: "core", strength: 0.35 });
      }
    }

    const blendWeight = activeEvents.length
      ? Math.min(1, 0.38 + activeEvents.length * 0.14)
      : 0;

    const def = dominant ? getMemoryDefinition(dominant.type, this._registry) : null;
    let hook = null;
    if (
      eventType === MEMORY_ACTIVITY_EVENTS.RECALLED ||
      eventType === MEMORY_ACTIVITY_EVENTS.SEARCH
    ) {
      hook = "memory_retrieval";
    }

    this._blend = {
      signature,
      regions,
      dominant,
      active: this.getActiveMemories(),
      eventType,
      blendWeight,
      statusLine: def?.statusLine ?? "Mémoire active…",
      hook,
    };
  }

  _ensurePulseLoop() {
    if (this._pulseTimer !== null) return;

    this._pulseTimer = window.setInterval(() => {
      if (this._activeEvents.length === 0) {
        this._stopPulseLoop();
        return;
      }

      for (const mem of this._memories.values()) {
        if (mem.state !== "active" && mem.state !== "fading") continue;
        mem.age = performance.now() - mem.createdAt;
        const wave = Math.sin(performance.now() / 1400) * 0.04;
        mem.energy = Math.max(0.08, Math.min(1, mem.energy + wave * 0.02));
      }

      this._recomputeBlend();
    }, 200);
  }

  _stopPulseLoop() {
    if (this._pulseTimer !== null) {
      window.clearInterval(this._pulseTimer);
      this._pulseTimer = null;
    }
  }
}
