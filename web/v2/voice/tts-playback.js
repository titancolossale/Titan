/** Titan Voice UI — ordered TTS playback with barge-in (Phase 20.4). */

import { emitVoiceUiDiagnostic } from "./diagnostics.js";
import { normalizeVoiceError } from "./errors.js";

/**
 * @typedef {{ sequence: number, audio_base64: string, mime_type?: string }} TtsChunk
 */

export class TtsPlaybackQueue {
  constructor() {
    /** @type {TtsChunk[]} */
    this._queue = [];
    /** @type {HTMLAudioElement | null} */
    this._audio = null;
    /** @type {string[]} */
    this._objectUrls = [];
    this._playing = false;
    this._generation = 0;
    this._userGestureUnlocked = false;
    /** @type {((err: { code: string, message: string }) => void) | null} */
    this.onError = null;
    /** @type {(() => void) | null} */
    this.onStarted = null;
    /** @type {(() => void) | null} */
    this.onStopped = null;
  }

  /** Call after an explicit user gesture (mic press) so autoplay is allowed. */
  unlockFromUserGesture() {
    this._userGestureUnlocked = true;
  }

  /** @returns {boolean} */
  get isPlaying() {
    return this._playing;
  }

  /**
   * Enqueue ordered chunks and start playback. Replaces any prior queue.
   * @param {TtsChunk[]} chunks
   */
  async playChunks(chunks) {
    this.stop({ silent: true });
    const ordered = [...(chunks || [])]
      .filter((c) => c && c.audio_base64)
      .sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
    if (!ordered.length) return;
    this._queue = ordered;
    this._generation += 1;
    const gen = this._generation;
    this._playing = true;
    emitVoiceUiDiagnostic("VOICE_UI_PLAYBACK_STARTED", { chunks: ordered.length });
    this.onStarted?.();
    try {
      await this._drainQueue(gen);
    } finally {
      if (gen === this._generation) {
        this._playing = false;
        emitVoiceUiDiagnostic("VOICE_UI_PLAYBACK_STOPPED", { reason: "completed" });
        this.onStopped?.();
        this._cleanupUrls();
      }
    }
  }

  /**
   * Append a streaming TTS chunk without interrupting current playback (Phase 20.5).
   * Prevents overlap by serializing through the same queue drain.
   * @param {TtsChunk} chunk
   */
  enqueueChunk(chunk) {
    if (!chunk?.audio_base64) return;
    const seq = chunk.sequence ?? this._queue.length;
    // Drop stale / duplicate sequences.
    if (this._queue.some((c) => (c.sequence ?? -1) === seq)) return;
    this._queue.push(chunk);
    this._queue.sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
    if (!this._playing) {
      this._generation += 1;
      const gen = this._generation;
      this._playing = true;
      emitVoiceUiDiagnostic("VOICE_UI_PLAYBACK_STARTED", { chunks: 1, streaming: true });
      this.onStarted?.();
      void this._drainQueue(gen).finally(() => {
        if (gen === this._generation) {
          this._playing = false;
          emitVoiceUiDiagnostic("VOICE_UI_PLAYBACK_STOPPED", { reason: "completed" });
          this.onStopped?.();
          this._cleanupUrls();
        }
      });
    }
  }

  /**
   * @param {number} gen
   */
  async _drainQueue(gen) {
    while (this._queue.length && gen === this._generation) {
      const next = this._queue.shift();
      if (!next) break;
      await this._playOne(next, gen);
    }
  }

  /**
   * @param {TtsChunk} chunk
   * @param {number} gen
   */
  async _playOne(chunk, gen) {
    const mime = chunk.mime_type || "audio/mpeg";
    const bytes = _base64ToBytes(chunk.audio_base64);
    const blob = new Blob([bytes], { type: mime });
    const url = URL.createObjectURL(blob);
    this._objectUrls.push(url);
    const audio = new Audio();
    this._audio = audio;
    audio.src = url;
    audio.preload = "auto";
    try {
      await audio.play();
    } catch (err) {
      const normalized = normalizeVoiceError(
        /** @type {any} */ (err)?.name === "NotAllowedError"
          ? "autoplay_blocked"
          : err,
      );
      this.onError?.(normalized);
      throw Object.assign(new Error(normalized.message), { code: normalized.code });
    }
    await new Promise((resolve, reject) => {
      const onEnded = () => {
        cleanup();
        resolve();
      };
      const onError = () => {
        cleanup();
        reject(Object.assign(new Error("tts_failure"), { code: "tts_failure" }));
      };
      const cleanup = () => {
        audio.removeEventListener("ended", onEnded);
        audio.removeEventListener("error", onError);
      };
      audio.addEventListener("ended", onEnded);
      audio.addEventListener("error", onError);
      if (gen !== this._generation) {
        cleanup();
        resolve();
      }
    });
  }

  /**
   * Immediate stop — used for barge-in and cancel.
   * @param {{ silent?: boolean }} [opts]
   */
  stop(opts = {}) {
    this._generation += 1;
    this._queue = [];
    const audio = this._audio;
    this._audio = null;
    if (audio) {
      try {
        audio.pause();
        audio.removeAttribute("src");
        audio.load();
      } catch {
        /* ignore */
      }
    }
    this._cleanupUrls();
    if (this._playing) {
      this._playing = false;
      if (!opts.silent) {
        emitVoiceUiDiagnostic("VOICE_UI_PLAYBACK_STOPPED", { reason: "stopped" });
        this.onStopped?.();
      }
    }
  }

  pause() {
    try {
      this._audio?.pause();
    } catch {
      /* ignore */
    }
  }

  _cleanupUrls() {
    for (const url of this._objectUrls) {
      try {
        URL.revokeObjectURL(url);
      } catch {
        /* ignore */
      }
    }
    this._objectUrls = [];
  }
}

/**
 * @param {string} b64
 * @returns {Uint8Array}
 */
function _base64ToBytes(b64) {
  const binary = atob(b64);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}
