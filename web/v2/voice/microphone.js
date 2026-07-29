/** Titan Voice UI — microphone permission handling (Phase 20.4). */

import { emitVoiceUiDiagnostic } from "./diagnostics.js";
import { normalizeVoiceError } from "./errors.js";

/** @typedef {"prompt"|"granted"|"denied"|"unavailable"|"none"|"insecure"|"revoked"|"unknown"} MicPermissionState */

/**
 * @returns {boolean}
 */
export function isSecureMicContext() {
  try {
    return Boolean(window.isSecureContext);
  } catch {
    return false;
  }
}

/**
 * @returns {boolean}
 */
export function hasMediaDevices() {
  return Boolean(navigator.mediaDevices?.getUserMedia);
}

/**
 * Query permission state without prompting (when Permissions API exists).
 * @returns {Promise<MicPermissionState>}
 */
export async function queryMicrophonePermission() {
  if (!isSecureMicContext()) return "insecure";
  if (!hasMediaDevices()) return "unavailable";
  try {
    if (!navigator.permissions?.query) return "unknown";
    const status = await navigator.permissions.query({
      name: /** @type {PermissionName} */ ("microphone"),
    });
    if (status.state === "granted") return "granted";
    if (status.state === "denied") return "denied";
    if (status.state === "prompt") return "prompt";
    return "unknown";
  } catch {
    return "unknown";
  }
}

/**
 * Request microphone access only after explicit user action.
 * Never retries in a loop — caller decides when to ask again.
 * Prefers constraints that help noise floor / echo without always-listening.
 * @param {MediaStreamConstraints} [constraints]
 * @returns {Promise<{ ok: true, stream: MediaStream } | { ok: false, state: MicPermissionState, error: { code: string, message: string } }>}
 */
export async function requestMicrophone(constraints) {
  if (!isSecureMicContext()) {
    emitVoiceUiDiagnostic("VOICE_UI_PERMISSION_DENIED", { reason: "insecure_context" });
    return {
      ok: false,
      state: "insecure",
      error: normalizeVoiceError("insecure_context"),
    };
  }
  if (!hasMediaDevices()) {
    emitVoiceUiDiagnostic("VOICE_UI_PERMISSION_DENIED", { reason: "unavailable" });
    return {
      ok: false,
      state: "unavailable",
      error: normalizeVoiceError("microphone_unavailable"),
    };
  }

  emitVoiceUiDiagnostic("VOICE_UI_PERMISSION_REQUESTED", {});
  try {
    const stream = await navigator.mediaDevices.getUserMedia(
      constraints || {
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
        video: false,
      },
    );
    emitVoiceUiDiagnostic("VOICE_UI_PERMISSION_GRANTED", {
      tracks: stream.getAudioTracks().length,
      label: stream.getAudioTracks()[0]?.label || "",
    });
    return { ok: true, stream };
  } catch (err) {
    const normalized = normalizeVoiceError(err);
    let state = /** @type {MicPermissionState} */ ("denied");
    const name = String(/** @type {any} */ (err)?.name || "").toLowerCase();
    if (name === "notfounderror") state = "none";
    else if (name === "notreadableerror" || name === "overconstrainederror") {
      state = "unavailable";
    } else if (name === "securityerror") {
      state = "insecure";
    }
    emitVoiceUiDiagnostic("VOICE_UI_PERMISSION_DENIED", {
      reason: state,
      code: normalized.code,
    });
    return { ok: false, state, error: normalized };
  }
}

/**
 * Soft permission preflight for UX copy (never prompts by itself).
 * @returns {Promise<{ state: MicPermissionState, canPrompt: boolean, secure: boolean }>}
 */
export async function microphonePermissionFlow() {
  const secure = isSecureMicContext();
  if (!secure) {
    return { state: "insecure", canPrompt: false, secure: false };
  }
  if (!hasMediaDevices()) {
    return { state: "unavailable", canPrompt: false, secure: true };
  }
  const state = await queryMicrophonePermission();
  return {
    state,
    canPrompt: state === "prompt" || state === "unknown" || state === "granted",
    secure: true,
  };
}

/**
 * Stop all tracks on a MediaStream (safe idempotent cleanup).
 * @param {MediaStream | null | undefined} stream
 */
export function releaseMediaStream(stream) {
  if (!stream) return;
  try {
    for (const track of stream.getTracks()) {
      try {
        track.stop();
      } catch {
        /* ignore */
      }
    }
  } catch {
    /* ignore */
  }
}

/**
 * Watch for permission revocation / ended tracks during an active session.
 * @param {MediaStream} stream
 * @param {(reason: string) => void} onRevoked
 * @returns {() => void} unbind
 */
export function watchMicrophoneRevocation(stream, onRevoked) {
  const tracks = stream.getAudioTracks();
  /** @type {Array<() => void>} */
  const cleanups = [];
  for (const track of tracks) {
    const handler = () => {
      emitVoiceUiDiagnostic("VOICE_UI_PERMISSION_DENIED", { reason: "revoked" });
      onRevoked("permission_revoked");
    };
    track.addEventListener("ended", handler);
    cleanups.push(() => track.removeEventListener("ended", handler));
  }
  return () => {
    for (const fn of cleanups) fn();
  };
}
