/** Titan Voice UI — authenticated API client (Phase 20.4). */

import { authHeaders } from "../core/web-auth.js";
import { emitVoiceUiDiagnostic } from "./diagnostics.js";
import { normalizeVoiceError } from "./errors.js";

/**
 * @param {string} path
 * @param {RequestInit} [init]
 */
async function voiceFetch(path, init = {}) {
  let response;
  try {
    response = await fetch(path, {
      credentials: "same-origin",
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...(init.headers || {}),
      },
    });
  } catch {
    const err = Object.assign(new Error(normalizeVoiceError("network_disconnect").message), {
      code: "network_disconnect",
      status: 0,
    });
    throw err;
  }

  if (response.status === 401) {
    const err = Object.assign(new Error(normalizeVoiceError("session_expired").message), {
      code: "session_expired",
      status: 401,
    });
    throw err;
  }

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const detail = data?.detail;
    const code =
      (typeof detail === "object" && detail?.code) ||
      data?.code ||
      (response.status === 504 ? "provider_timeout" : "request_failed");
    const message =
      (typeof detail === "object" && detail?.message) ||
      (typeof detail === "string" ? detail : null) ||
      data?.message ||
      normalizeVoiceError(code).message;
    const err = Object.assign(new Error(String(message)), {
      code: String(code),
      status: response.status,
      detail,
    });
    throw err;
  }
  return data;
}

/** @param {object} [body] */
export async function startVoiceSession(body = {}) {
  const data = await voiceFetch("/voice/session/start", {
    method: "POST",
    body: JSON.stringify({
      capture_mode: "push_to_talk",
      microphone_enabled: true,
      ...body,
    }),
  });
  emitVoiceUiDiagnostic("VOICE_UI_SESSION_STARTED", {
    session_id: data?.session_id,
  });
  return data;
}

/**
 * @param {{ session_id: string, audio_base64: string, sequence: number, timestamp_ms?: number }} payload
 */
export async function sendAudioChunk(payload) {
  const data = await voiceFetch("/voice/session/chunk", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  emitVoiceUiDiagnostic("VOICE_UI_AUDIO_CHUNK_SENT", {
    sequence: payload.sequence,
    duplicate: Boolean(data?.duplicate),
    accepted: data?.accepted !== false,
  });
  return data;
}

/** @param {string} sessionId */
export async function finishUtterance(sessionId) {
  return voiceFetch("/voice/session/finish", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}

/** @param {string} sessionId @param {string} [user] */
export async function confirmIdentity(sessionId, user) {
  return voiceFetch("/voice/session/confirm-identity", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, user: user || null }),
  });
}

/** @param {string} sessionId */
export async function rejectIdentity(sessionId) {
  return voiceFetch("/voice/session/reject-identity", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}

/** @param {string} sessionId */
export async function interruptPlayback(sessionId) {
  const data = await voiceFetch("/voice/session/interrupt", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
  emitVoiceUiDiagnostic("VOICE_UI_BARGE_IN", { session_id: sessionId });
  return data;
}

/** @param {string} sessionId */
export async function cancelVoiceSession(sessionId) {
  const data = await voiceFetch("/voice/session/cancel", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
  emitVoiceUiDiagnostic("VOICE_UI_SESSION_CANCELLED", { session_id: sessionId });
  return data;
}

/** @param {string} sessionId */
export async function getVoiceSessionState(sessionId) {
  return voiceFetch(
    `/voice/session/state?session_id=${encodeURIComponent(sessionId)}`,
  );
}

/**
 * @param {{ recovery_token?: string, conversation_id?: string, capture_mode?: string, microphone_enabled?: boolean }} body
 */
export async function recoverVoiceSession(body = {}) {
  const data = await voiceFetch("/voice/session/recover", {
    method: "POST",
    body: JSON.stringify(body),
  });
  emitVoiceUiDiagnostic("VOICE_UI_SESSION_RECOVERED", {
    session_id: data?.session_id,
    rebound: Boolean(data?.session_still_active) === false && Boolean(data?.recovered),
  });
  return data;
}

/** @param {string} sessionId */
export async function heartbeatVoiceSession(sessionId) {
  return voiceFetch("/voice/session/heartbeat", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}

/** @param {string} sessionId */
export async function drainVoiceEvents(sessionId) {
  return voiceFetch(
    `/voice/session/events?session_id=${encodeURIComponent(sessionId)}`,
  );
}

/** @param {string} sessionId */
export async function startMicCalibration(sessionId) {
  const data = await voiceFetch("/voice/session/calibrate/start", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
  emitVoiceUiDiagnostic("VOICE_UI_MIC_CALIBRATION_STARTED", {
    session_id: sessionId,
  });
  return data;
}

/**
 * @param {{ session_id: string, audio_base64: string, sequence?: number }} payload
 */
export async function sendMicCalibrationChunk(payload) {
  return voiceFetch("/voice/session/calibrate/chunk", {
    method: "POST",
    body: JSON.stringify({
      session_id: payload.session_id,
      audio_base64: payload.audio_base64,
      sequence: payload.sequence ?? 0,
    }),
  });
}

/** @param {string} sessionId */
export async function finishMicCalibration(sessionId) {
  const data = await voiceFetch("/voice/session/calibrate/finish", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
  emitVoiceUiDiagnostic("VOICE_UI_MIC_CALIBRATION_COMPLETED", {
    session_id: sessionId,
    warning: data?.mic_calibration?.warning || null,
  });
  return data;
}

/** @param {string} sessionId */
export async function getVoiceSessionStats(sessionId) {
  return voiceFetch(
    `/voice/session/stats?session_id=${encodeURIComponent(sessionId)}`,
  );
}

/** Enrollment ----------------------------------------------------------- */

/**
 * @param {{
 *   user: string,
 *   locale?: string,
 *   replace_existing?: boolean,
 *   consent_accepted?: boolean,
 *   session_label?: string,
 * }} body
 */
export async function startEnrollment(body) {
  return voiceFetch("/voice/enrollment/start", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * Explicit consent grant for an in-flight enrollment session.
 * @param {{ session_id: string, accepted?: boolean, locale?: string }} body
 */
export async function grantEnrollmentConsent(body) {
  return voiceFetch("/voice/enrollment/consent", {
    method: "POST",
    body: JSON.stringify({
      accepted: true,
      ...body,
    }),
  });
}

/** @param {{ session_id: string, audio_base64: string }} body */
export async function submitEnrollmentSample(body) {
  return voiceFetch("/voice/enrollment/sample", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** @param {string} sessionId */
export async function finishEnrollment(sessionId) {
  return voiceFetch("/voice/enrollment/finish", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}

/** @param {{ session_id: string, audio_base64: string }} body */
export async function verifyEnrollment(body) {
  return voiceFetch("/voice/enrollment/verify", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** @param {string} sessionId */
export async function cancelEnrollment(sessionId) {
  return voiceFetch("/voice/enrollment/cancel", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}

/** @param {{ user: string, profile_id?: string }} body */
export async function revokeEnrollmentProfile(body) {
  return voiceFetch("/voice/enrollment/revoke", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** @param {{ session_id?: string, user?: string }} [query] */
export async function getEnrollmentStatus(query = {}) {
  const params = new URLSearchParams();
  if (query.session_id) params.set("session_id", query.session_id);
  if (query.user) params.set("user", query.user);
  const qs = params.toString();
  return voiceFetch(`/voice/enrollment/status${qs ? `?${qs}` : ""}`);
}

/** Phase 20.10B-1 — production enrollment pre-flight (no recording). */
export async function getEnrollmentPreflight() {
  return voiceFetch("/voice/enrollment/preflight");
}

export async function getVoiceStatus() {
  return voiceFetch("/voice/status");
}
