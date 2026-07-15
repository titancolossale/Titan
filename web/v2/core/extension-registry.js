/** Titan Frontend V2 — Extension hook registry (Phase E10 future readiness). */

/**
 * Reserved extension slots — register hooks without modifying shell architecture.
 * @type {readonly string[]}
 */
export const EXTENSION_SLOTS = Object.freeze([
  "voice",
  "trading",
  "browser",
  "obsidian",
  "calendar",
  "projects",
  "agents",
  "plugins",
  "multi-user",
  "mobile",
]);

/**
 * Lightweight registry for future domain modules (Voice, Trading, Browser, etc.).
 * Hooks receive `{ app, brain, store, shell }` at registration time.
 */
export class ExtensionRegistry {
  constructor() {
    /** @type {Map<string, Set<(ctx: object) => void>>} */
    this._hooks = new Map();
  }

  /**
   * Register an extension hook for a reserved slot.
   * @param {string} slot
   * @param {(ctx: object) => void | (() => void)} hook
   * @returns {() => void}
   */
  register(slot, hook) {
    const key = slot.trim().toLowerCase();
    if (!EXTENSION_SLOTS.includes(key)) {
      throw new Error(`[Titan V2] Unknown extension slot: ${slot}`);
    }
    if (!this._hooks.has(key)) {
      this._hooks.set(key, new Set());
    }
    this._hooks.get(key).add(hook);
    return () => {
      this._hooks.get(key)?.delete(hook);
    };
  }

  /**
   * Invoke all hooks registered for a slot.
   * @param {string} slot
   * @param {object} ctx
   */
  invoke(slot, ctx) {
    const key = slot.trim().toLowerCase();
    for (const hook of this._hooks.get(key) ?? []) {
      try {
        hook(ctx);
      } catch {
        /* extension hooks must not break core boot */
      }
    }
  }

  /** @param {string} slot @returns {boolean} */
  has(slot) {
    return (this._hooks.get(slot.trim().toLowerCase())?.size ?? 0) > 0;
  }
}
