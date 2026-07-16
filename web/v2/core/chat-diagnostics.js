/** Titan Frontend V2 — Safe chat correlation / diagnostic logging (Phase 11.1B). */

/**
 * Concise lifecycle logs — no message content, no secrets.
 * Gated by localStorage `titan_chat_diag` !== "0" (default on).
 */

/** @returns {boolean} */
export function isChatDiagEnabled() {
  try {
    return localStorage.getItem("titan_chat_diag") !== "0";
  } catch {
    return true;
  }
}

/**
 * @param {string} event
 * @param {Record<string, string | number | boolean | null | undefined>} [fields]
 */
export function chatDiag(event, fields = {}) {
  if (!isChatDiagEnabled()) return;
  const safe = {};
  for (const [key, value] of Object.entries(fields)) {
    if (value === undefined) continue;
    safe[key] = value;
  }
  // Structured single-line log for Railway/browser correlation.
  console.info(`[TitanChat] ${event}`, safe);
}
