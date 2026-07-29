/** Titan Voice UI — browser audio capture (Phase 20.4).

Prefers AudioContext PCM → Int16 chunks (concat-safe for server wrap_pcm_as_wav).
Falls back to MediaRecorder when AudioContext capture is unavailable.
Never persists raw audio to localStorage / IndexedDB / conversation history.
*/

import { emitVoiceUiDiagnostic } from "./diagnostics.js";
import { normalizeVoiceError } from "./errors.js";
import { releaseMediaStream } from "./microphone.js";

/** @typedef {(chunk: { sequence: number, bytes: Uint8Array, mimeType: string, final?: boolean }) => void} ChunkHandler */

const DEFAULT_CHUNK_MS = 250;
const DEFAULT_SAMPLE_RATE = 16000;
const MAX_BUFFER_BYTES = 2_000_000;

/**
 * Detect a supported MediaRecorder MIME type.
 * @param {string[]} [candidates]
 * @returns {string | null}
 */
export function detectSupportedMimeType(candidates) {
  if (typeof MediaRecorder === "undefined") return null;
  const list = candidates || [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
  ];
  for (const mime of list) {
    try {
      if (MediaRecorder.isTypeSupported(mime)) return mime;
    } catch {
      /* ignore */
    }
  }
  return null;
}

/**
 * Encode Int16 LE PCM as a minimal mono WAV.
 * @param {Int16Array | Uint8Array} pcm
 * @param {number} [sampleRate]
 * @returns {Uint8Array}
 */
export function encodeWavPcm16(pcm, sampleRate = DEFAULT_SAMPLE_RATE) {
  const pcmBytes =
    pcm instanceof Int16Array
      ? new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength)
      : pcm;
  const dataSize = pcmBytes.byteLength;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  const writeStr = (offset, str) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, dataSize, true);
  new Uint8Array(buffer, 44).set(pcmBytes);
  return new Uint8Array(buffer);
}

/**
 * @param {Float32Array} input
 * @returns {Int16Array}
 */
function floatTo16BitPCM(input) {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

/**
 * Downsample Float32 PCM to target rate.
 * @param {Float32Array} input
 * @param {number} fromRate
 * @param {number} toRate
 * @returns {Float32Array}
 */
function downsample(input, fromRate, toRate) {
  if (fromRate === toRate) return input;
  const ratio = fromRate / toRate;
  const newLen = Math.max(1, Math.floor(input.length / ratio));
  const result = new Float32Array(newLen);
  for (let i = 0; i < newLen; i++) {
    result[i] = input[Math.floor(i * ratio)] || 0;
  }
  return result;
}

/**
 * Compute a 0..1 input level from PCM floats.
 * @param {Float32Array} input
 * @returns {number}
 */
export function computeInputLevel(input) {
  if (!input?.length) return 0;
  let sum = 0;
  for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
  const rms = Math.sqrt(sum / input.length);
  return Math.max(0, Math.min(1, rms * 4));
}

/**
 * Estimate noise floor / peak / clipping from a Float32 PCM window (Phase 20.7).
 * @param {Float32Array} input
 * @returns {{ rms: number, peak: number, clippingRatio: number, lowVolume: boolean, clipping: boolean }}
 */
export function estimateMicMetrics(input) {
  if (!input?.length) {
    return { rms: 0, peak: 0, clippingRatio: 0, lowVolume: true, clipping: false };
  }
  let sum = 0;
  let peak = 0;
  let clipped = 0;
  for (let i = 0; i < input.length; i++) {
    const v = Math.abs(input[i]);
    sum += input[i] * input[i];
    if (v > peak) peak = v;
    if (v >= 0.98) clipped += 1;
  }
  const rms = Math.sqrt(sum / input.length);
  const clippingRatio = clipped / input.length;
  return {
    rms,
    peak,
    clippingRatio,
    lowVolume: rms < 0.01,
    clipping: clippingRatio >= 0.02 || peak >= 0.98,
  };
}

/**
 * Recommend a software gain toward a target RMS (clamped).
 * @param {number} rms
 * @param {number} [target=0.12]
 * @returns {number}
 */
export function estimateRecommendedGain(rms, target = 0.12) {
  if (!rms || rms < 1e-6) return 4;
  const gain = target / rms;
  return Math.max(0.5, Math.min(4, gain));
}

/**
 * Apply gain to Int16 PCM without reallocating when gain≈1.
 * @param {Int16Array} pcm
 * @param {number} gain
 * @returns {Int16Array}
 */
export function applyInputGain(pcm, gain) {
  if (!pcm?.length) return pcm;
  if (!gain || Math.abs(gain - 1) < 0.02) return pcm;
  const out = new Int16Array(pcm.length);
  for (let i = 0; i < pcm.length; i++) {
    const v = Math.max(-1, Math.min(1, (pcm[i] / 0x8000) * gain));
    out[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
  }
  return out;
}

/**
 * @param {Uint8Array | ArrayBuffer} bytes
 * @returns {string}
 */
export function bytesToBase64(bytes) {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < arr.length; i += chunk) {
    binary += String.fromCharCode(...arr.subarray(i, i + chunk));
  }
  return btoa(binary);
}

export class AudioCaptureSession {
  /**
   * @param {object} [options]
   * @param {number} [options.chunkDurationMs]
   * @param {number} [options.sampleRate]
   * @param {number} [options.maxBufferBytes]
   * @param {ChunkHandler} [options.onChunk]
   * @param {(level: number) => void} [options.onLevel]
   * @param {(err: { code: string, message: string }) => void} [options.onError]
   */
  constructor(options = {}) {
    this.chunkDurationMs = options.chunkDurationMs ?? DEFAULT_CHUNK_MS;
    this.targetSampleRate = options.sampleRate ?? DEFAULT_SAMPLE_RATE;
    this.maxBufferBytes = options.maxBufferBytes ?? MAX_BUFFER_BYTES;
    this.onChunk = options.onChunk || null;
    this.onLevel = options.onLevel || null;
    this.onError = options.onError || null;

    /** @type {MediaStream | null} */
    this._stream = null;
    /** @type {AudioContext | null} */
    this._audioCtx = null;
    /** @type {ScriptProcessorNode | MediaStreamAudioSourceNode | null} */
    this._processor = null;
    /** @type {MediaStreamAudioSourceNode | null} */
    this._source = null;
    /** @type {MediaRecorder | null} */
    this._recorder = null;
    /** @type {string | null} */
    this._mimeType = "application/octet-stream";
    this._mode = /** @type {"pcm"|"mediarecorder"|"idle"} */ ("idle");
    this._sequence = 0;
    this._active = false;
    /** @type {Int16Array[]} */
    this._pcmQueue = [];
    this._pcmBytes = 0;
    this._flushTimer = null;
    this._seenSequences = new Set();
  }

  /** @returns {boolean} */
  get active() {
    return this._active;
  }

  /** @returns {number} */
  get sequence() {
    return this._sequence;
  }

  /**
   * Start capture from an already-granted MediaStream.
   * @param {MediaStream} stream
   * @returns {Promise<void>}
   */
  async start(stream) {
    if (this._active) return;
    this._stream = stream;
    this._sequence = 0;
    this._seenSequences.clear();
    this._pcmQueue = [];
    this._pcmBytes = 0;
    this._active = true;

    const AudioCtx = window.AudioContext || /** @type {any} */ (window).webkitAudioContext;
    if (AudioCtx) {
      try {
        await this._startPcm(stream, AudioCtx);
        emitVoiceUiDiagnostic("VOICE_UI_RECORDING_STARTED", { mode: "pcm" });
        return;
      } catch (err) {
        this._teardownAudioGraph();
        const mime = detectSupportedMimeType();
        if (!mime) {
          this._active = false;
          const normalized = normalizeVoiceError(err);
          this.onError?.(normalized);
          throw err;
        }
      }
    }

    const mime = detectSupportedMimeType();
    if (!mime) {
      this._active = false;
      const err = normalizeVoiceError("unsupported_format");
      this.onError?.(err);
      throw Object.assign(new Error(err.message), { code: err.code });
    }
    await this._startMediaRecorder(stream, mime);
    emitVoiceUiDiagnostic("VOICE_UI_RECORDING_STARTED", { mode: "mediarecorder", mime });
  }

  /**
   * @param {MediaStream} stream
   * @param {typeof AudioContext} AudioCtx
   */
  async _startPcm(stream, AudioCtx) {
    this._mode = "pcm";
    this._mimeType = "application/octet-stream";
    this._audioCtx = new AudioCtx();
    if (this._audioCtx.state === "suspended") {
      await this._audioCtx.resume();
    }
    this._source = this._audioCtx.createMediaStreamSource(stream);
    const bufferSize = 4096;
    // ScriptProcessor remains the widest-compatible capture path for PCM.
    this._processor = this._audioCtx.createScriptProcessor(bufferSize, 1, 1);
    this._processor.onaudioprocess = (event) => {
      if (!this._active) return;
      const input = event.inputBuffer.getChannelData(0);
      const level = computeInputLevel(input);
      this.onLevel?.(level);
      const down = downsample(input, this._audioCtx.sampleRate, this.targetSampleRate);
      const pcm = floatTo16BitPCM(down);
      this._enqueuePcm(pcm);
    };
    this._source.connect(this._processor);
    this._processor.connect(this._audioCtx.destination);
    this._flushTimer = window.setInterval(() => this._flushPcm(false), this.chunkDurationMs);
  }

  /** @param {Int16Array} pcm */
  _enqueuePcm(pcm) {
    const bytes = pcm.byteLength;
    if (this._pcmBytes + bytes > this.maxBufferBytes) {
      // Drop oldest queued frames to stay bounded.
      while (this._pcmQueue.length && this._pcmBytes + bytes > this.maxBufferBytes) {
        const dropped = this._pcmQueue.shift();
        this._pcmBytes -= dropped?.byteLength || 0;
      }
    }
    this._pcmQueue.push(pcm);
    this._pcmBytes += bytes;
  }

  /** @param {boolean} final */
  _flushPcm(final) {
    if (!this._pcmQueue.length) {
      if (final) {
        this._emitChunk(new Uint8Array(0), true);
      }
      return;
    }
    const total = this._pcmQueue.reduce((n, p) => n + p.length, 0);
    const merged = new Int16Array(total);
    let offset = 0;
    for (const part of this._pcmQueue) {
      merged.set(part, offset);
      offset += part.length;
    }
    this._pcmQueue = [];
    this._pcmBytes = 0;
    const bytes = new Uint8Array(merged.buffer, merged.byteOffset, merged.byteLength);
    this._emitChunk(bytes, final);
  }

  /**
   * @param {MediaStream} stream
   * @param {string} mime
   */
  async _startMediaRecorder(stream, mime) {
    this._mode = "mediarecorder";
    this._mimeType = mime;
    this._recorder = new MediaRecorder(stream, { mimeType: mime });
    this._recorder.ondataavailable = async (event) => {
      if (!event.data || event.data.size === 0) return;
      const buf = new Uint8Array(await event.data.arrayBuffer());
      this._emitChunk(buf, false);
    };
    this._recorder.onerror = () => {
      this.onError?.(normalizeVoiceError("recording_failed"));
    };
    this._recorder.start(this.chunkDurationMs);
  }

  /**
   * @param {Uint8Array} bytes
   * @param {boolean} final
   */
  _emitChunk(bytes, final) {
    if (!final && (!bytes || bytes.length === 0)) return;
    const sequence = this._sequence;
    if (this._seenSequences.has(sequence) && !final) {
      return;
    }
    this._seenSequences.add(sequence);
    this._sequence += 1;
    this.onChunk?.({
      sequence,
      bytes,
      mimeType: this._mimeType || "application/octet-stream",
      final,
    });
  }

  /**
   * Stop capture, flush final chunk, release graph (not necessarily the stream).
   * @param {{ releaseStream?: boolean }} [opts]
   * @returns {Promise<void>}
   */
  async stop(opts = {}) {
    if (!this._active && !this._recorder && !this._processor) {
      if (opts.releaseStream) releaseMediaStream(this._stream);
      this._stream = null;
      return;
    }
    this._active = false;
    if (this._flushTimer != null) {
      clearInterval(this._flushTimer);
      this._flushTimer = null;
    }

    if (this._mode === "pcm") {
      this._flushPcm(true);
      this._teardownAudioGraph();
    } else if (this._recorder) {
      await new Promise((resolve) => {
        const rec = this._recorder;
        if (!rec || rec.state === "inactive") {
          resolve();
          return;
        }
        rec.onstop = () => resolve();
        try {
          rec.requestData?.();
          rec.stop();
        } catch {
          resolve();
        }
      });
      this._recorder = null;
    }

    emitVoiceUiDiagnostic("VOICE_UI_RECORDING_STOPPED", {
      sequences: this._sequence,
      mode: this._mode,
    });
    this._mode = "idle";
    if (opts.releaseStream) {
      releaseMediaStream(this._stream);
      this._stream = null;
    }
  }

  /** Immediate abort — no further chunks. */
  async cancel(opts = {}) {
    this._active = false;
    this._pcmQueue = [];
    this._pcmBytes = 0;
    if (this._flushTimer != null) {
      clearInterval(this._flushTimer);
      this._flushTimer = null;
    }
    if (this._recorder && this._recorder.state !== "inactive") {
      try {
        this._recorder.ondataavailable = null;
        this._recorder.stop();
      } catch {
        /* ignore */
      }
      this._recorder = null;
    }
    this._teardownAudioGraph();
    this._mode = "idle";
    if (opts.releaseStream !== false) {
      releaseMediaStream(this._stream);
      this._stream = null;
    }
  }

  _teardownAudioGraph() {
    try {
      this._processor?.disconnect?.();
    } catch {
      /* ignore */
    }
    try {
      this._source?.disconnect?.();
    } catch {
      /* ignore */
    }
    this._processor = null;
    this._source = null;
    const ctx = this._audioCtx;
    this._audioCtx = null;
    if (ctx) {
      try {
        ctx.close();
      } catch {
        /* ignore */
      }
    }
  }
}
