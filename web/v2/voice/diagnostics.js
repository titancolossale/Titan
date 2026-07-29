/** Titan Voice UI — client diagnostics (Phase 20.4). Never logs audio or secrets. */

/** @type {readonly string[]} */
export const VOICE_UI_EVENTS = Object.freeze([
  "VOICE_UI_PERMISSION_REQUESTED",
  "VOICE_UI_PERMISSION_GRANTED",
  "VOICE_UI_PERMISSION_DENIED",
  "VOICE_UI_SESSION_STARTED",
  "VOICE_UI_RECORDING_STARTED",
  "VOICE_UI_AUDIO_CHUNK_SENT",
  "VOICE_UI_RECORDING_STOPPED",
  "VOICE_UI_IDENTITY_CONFIRMATION_SHOWN",
  "VOICE_UI_PLAYBACK_STARTED",
  "VOICE_UI_PLAYBACK_STOPPED",
  "VOICE_UI_BARGE_IN",
  "VOICE_UI_SESSION_CANCELLED",
  "VOICE_UI_SESSION_FAILED",
  "VOICE_UI_SESSION_COMPLETED",
  "VOICE_UI_MIC_CALIBRATION_STARTED",
  "VOICE_UI_MIC_CALIBRATION_COMPLETED",
  "VOICE_UI_MIC_LOW_VOLUME",
  "VOICE_UI_MIC_CLIPPING",
  "VOICE_UI_SESSION_RECOVERED",
]);

const FORBIDDEN = Object.freeze([
  "audio_base64",
  "raw_audio",
  "embedding",
  "embeddings",
  "cookie",
  "csrf",
  "authorization",
  "api_key",
  "password",
  "transcript",
  "prompt",
  "memory",
]);

/**
 * @param {unknown} value
 * @returns {unknown}
 */
function sanitizeValue(value) {
  if (value == null) return value;
  if (typeof value === "string") {
    return value.length > 120 ? `${value.slice(0, 120)}…` : value;
  }
  if (typeof value === "number" || typeof value === "boolean") return value;
  if (Array.isArray(value)) {
    return value.slice(0, 20).map(sanitizeValue);
  }
  if (typeof value === "object") {
    /** @type {Record<string, unknown>} */
    const out = {};
    for (const [key, nested] of Object.entries(value)) {
      const lowered = key.toLowerCase();
      if (FORBIDDEN.some((f) => lowered.includes(f))) continue;
      out[key] = sanitizeValue(nested);
    }
    return out;
  }
  return String(value);
}

/**
 * Emit a privacy-safe voice UI diagnostic event.
 * @param {string} event
 * @param {Record<string, unknown>} [payload]
 */
export function emitVoiceUiDiagnostic(event, payload = {}) {
  const name = String(event || "").trim().toUpperCase();
  if (!VOICE_UI_EVENTS.includes(name) && !name.startsWith("VOICE_UI_")) {
    return;
  }
  const safe = /** @type {Record<string, unknown>} */ (sanitizeValue(payload) || {});
  try {
    const detail = { event: name, ...safe, ts: Date.now() };
    window.dispatchEvent(new CustomEvent("titan:voice-ui-diagnostic", { detail }));
    if (window.localStorage?.getItem("titan-v2-dev") === "1") {
      // eslint-disable-next-line no-console
      console.debug(`[Titan Voice UI] ${name}`, safe);
    }
  } catch {
    /* diagnostics must never break voice UX */
  }
}
