/** Titan Voice — native browser WebSocket transport (Phase 20.8).
 *
 * Optional uplink alongside HTTP chunk APIs. Supports persistent connection,
 * automatic reconnect with backoff, heartbeat, backpressure, stream sync,
 * and graceful recover via recovery_token. No UI redesign.
 */

const DEFAULT_HEARTBEAT_MS = 12000;
const DEFAULT_MAX_ATTEMPTS = 8;
const DEFAULT_BASE_DELAY_MS = 300;
const DEFAULT_MAX_DELAY_MS = 10000;

/**
 * @typedef {object} VoiceSocketOptions
 * @property {string} [url]
 * @property {string} [token]
 * @property {(frame: object) => void} [onEvent]
 * @property {(audio: ArrayBuffer) => void} [onTtsAudio]
 * @property {(state: string) => void} [onState]
 * @property {(err: Error) => void} [onError]
 * @property {number} [heartbeatMs]
 * @property {number} [maxAttempts]
 */

export class VoiceSocket {
  /** @param {VoiceSocketOptions} [options] */
  constructor(options = {}) {
    this._options = options;
    /** @type {WebSocket | null} */
    this._ws = null;
    this._state = "idle";
    this._seq = 0;
    this._sessionId = null;
    this._recoveryToken = null;
    this._heartbeatTimer = null;
    this._reconnectAttempt = 0;
    this._closedByUser = false;
    this._pendingAudio = [];
    this._slowdown = false;
  }

  get state() {
    return this._state;
  }

  get sessionId() {
    return this._sessionId;
  }

  /** Build ws(s) URL from current page origin. */
  static defaultUrl(token) {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const base = `${proto}//${window.location.host}/voice/session/ws`;
    if (token) {
      return `${base}?token=${encodeURIComponent(token)}`;
    }
    return base;
  }

  /**
   * @param {{ sessionId?: string, recoveryToken?: string }} [opts]
   */
  async connect(opts = {}) {
    this._closedByUser = false;
    if (opts.sessionId) this._sessionId = opts.sessionId;
    if (opts.recoveryToken) this._recoveryToken = opts.recoveryToken;
    const url =
      this._options.url ||
      VoiceSocket.defaultUrl(this._options.token);
    this._setState("connecting");
    await new Promise((resolve, reject) => {
      let settled = false;
      const ws = new WebSocket(url);
      ws.binaryType = "arraybuffer";
      this._ws = ws;
      ws.onopen = () => {
        this._setState("connected");
        this._reconnectAttempt = 0;
        this._sendJson({
          type: "hello",
          seq: this._nextSeq(),
          session_id: this._sessionId,
          payload: { action: "hello" },
        });
        if (this._sessionId && this._recoveryToken) {
          this._sendJson({
            type: "recover",
            seq: this._nextSeq(),
            session_id: this._sessionId,
            payload: {
              session_id: this._sessionId,
              recovery_token: this._recoveryToken,
              last_client_seq: this._seq,
            },
          });
        }
        this._startHeartbeat();
        if (!settled) {
          settled = true;
          resolve();
        }
      };
      ws.onmessage = (ev) => this._onMessage(ev);
      ws.onerror = () => {
        const err = new Error("Voice WebSocket error");
        this._options.onError?.(err);
        if (!settled) {
          settled = true;
          reject(err);
        }
      };
      ws.onclose = () => {
        this._stopHeartbeat();
        this._setState("closed");
        if (!this._closedByUser) {
          void this._scheduleReconnect();
        }
        if (!settled) {
          settled = true;
          reject(new Error("Voice WebSocket closed before open"));
        }
      };
    });
  }

  /**
   * Start a live voice session over the socket.
   * @param {object} [payload]
   */
  startSession(payload = {}) {
    this._sendJson({
      type: "event",
      seq: this._nextSeq(),
      payload: { action: "start_session", ...payload },
    });
  }

  /**
   * Send uplink PCM/WAV audio bytes.
   * @param {ArrayBuffer | Uint8Array} audio
   */
  sendAudio(audio) {
    if (this._slowdown) {
      // Mild client-side backpressure — drop every other frame when slowed.
      if (this._seq % 2 === 0) return;
    }
    if (!this._ws || this._ws.readyState !== WebSocket.OPEN) {
      if (this._pendingAudio.length < 16) {
        this._pendingAudio.push(audio);
      }
      return;
    }
    const bytes = audio instanceof ArrayBuffer ? new Uint8Array(audio) : audio;
    this._ws.send(bytes);
    this._sendJson({
      type: "audio",
      seq: this._nextSeq(),
      session_id: this._sessionId,
      payload: { bytes: bytes.byteLength || bytes.length },
    });
  }

  finishTurn() {
    this._sendJson({
      type: "event",
      seq: this._nextSeq(),
      session_id: this._sessionId,
      payload: { action: "finish_turn" },
    });
  }

  interrupt() {
    this._sendJson({
      type: "event",
      seq: this._nextSeq(),
      session_id: this._sessionId,
      payload: { action: "interrupt" },
    });
  }

  close() {
    this._closedByUser = true;
    this._stopHeartbeat();
    if (this._ws && this._ws.readyState <= WebSocket.OPEN) {
      try {
        this._sendJson({
          type: "close",
          seq: this._nextSeq(),
          session_id: this._sessionId,
          payload: {},
        });
        this._ws.close(1000, "client_close");
      } catch {
        /* ignore */
      }
    }
    this._ws = null;
    this._setState("closed");
  }

  // --- internals -----------------------------------------------------------

  _nextSeq() {
    this._seq += 1;
    return this._seq;
  }

  _setState(state) {
    this._state = state;
    this._options.onState?.(state);
  }

  _sendJson(frame) {
    if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return;
    this._ws.send(JSON.stringify(frame));
  }

  _onMessage(ev) {
    if (typeof ev.data !== "string") {
      this._options.onTtsAudio?.(ev.data);
      return;
    }
    let frame;
    try {
      frame = JSON.parse(ev.data);
    } catch {
      return;
    }
    const type = frame?.type;
    if (type === "hello_ack" || type === "recover_ack") {
      if (frame.session_id) this._sessionId = frame.session_id;
      // Flush any buffered audio after recover.
      while (this._pendingAudio.length) {
        this.sendAudio(this._pendingAudio.shift());
      }
    }
    if (type === "backpressure") {
      this._slowdown = Boolean(frame.payload?.slowdown);
    }
    if (type === "event" && frame.payload?.result?.session_id) {
      this._sessionId = frame.payload.result.session_id;
      if (frame.payload.result.recovery_token) {
        this._recoveryToken = frame.payload.result.recovery_token;
      }
    }
    if (type === "tts_chunk" && frame.payload?.audio_b64) {
      // Prefer binary path; ignore if present as text.
    }
    this._options.onEvent?.(frame);
  }

  _startHeartbeat() {
    this._stopHeartbeat();
    const ms = this._options.heartbeatMs || DEFAULT_HEARTBEAT_MS;
    this._heartbeatTimer = window.setInterval(() => {
      this._sendJson({
        type: "heartbeat",
        seq: this._nextSeq(),
        session_id: this._sessionId,
        payload: { action: "heartbeat" },
      });
    }, ms);
  }

  _stopHeartbeat() {
    if (this._heartbeatTimer != null) {
      window.clearInterval(this._heartbeatTimer);
      this._heartbeatTimer = null;
    }
  }

  async _scheduleReconnect() {
    const maxAttempts = this._options.maxAttempts ?? DEFAULT_MAX_ATTEMPTS;
    if (this._reconnectAttempt >= maxAttempts) {
      this._setState("failed");
      return;
    }
    this._setState("reconnecting");
    const attempt = this._reconnectAttempt;
    this._reconnectAttempt += 1;
    const base = DEFAULT_BASE_DELAY_MS * 2 ** attempt;
    const delay = Math.min(DEFAULT_MAX_DELAY_MS, base);
    const jitter = delay * 0.2 * (Math.random() * 2 - 1);
    await new Promise((r) => setTimeout(r, Math.max(0, delay + jitter)));
    if (this._closedByUser) return;
    try {
      await this.connect({
        sessionId: this._sessionId || undefined,
        recoveryToken: this._recoveryToken || undefined,
      });
    } catch (err) {
      this._options.onError?.(err instanceof Error ? err : new Error(String(err)));
      void this._scheduleReconnect();
    }
  }
}

/**
 * Feature detection — HTTP fallback remains valid when WS unavailable.
 * @returns {boolean}
 */
export function voiceSocketSupported() {
  return typeof WebSocket !== "undefined";
}
