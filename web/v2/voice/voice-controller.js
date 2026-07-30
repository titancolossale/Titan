/** Titan Voice UI — push-to-talk + continuous conversation (Phase 20.4/20.5). */

import {
  AudioCaptureSession,
  bytesToBase64,
  encodeWavPcm16,
} from "./audio-capture.js";
import { emitVoiceUiDiagnostic } from "./diagnostics.js";
import { normalizeVoiceError, voiceErrorMessage } from "./errors.js";
import {
  queryMicrophonePermission,
  releaseMediaStream,
  requestMicrophone,
  watchMicrophoneRevocation,
} from "./microphone.js";
import { TtsPlaybackQueue } from "./tts-playback.js";
import * as api from "./voice-api.js";

/** @typedef {"idle"|"listening"|"recording"|"transcribing"|"identifying"|"confirming"|"thinking"|"speaking"|"interrupted"|"failed"} VoiceUiPhase */

const HOLD_CLICK_MS = 280;
const RECOVERY_STORAGE_KEY = "titan.voice.recovery";
const HEARTBEAT_MS = 30000;

export class VoiceController {
  /**
   * @param {object} ctx
   * @param {import("../core/state-store.js").StateStore} ctx.store
   * @param {import("../core/cognitive-state-engine.js").CognitiveStateEngine | null} [ctx.brain]
   * @param {import("../neural/stage.js").NeuralStage | null} [ctx.neural]
   */
  constructor(ctx) {
    this._store = ctx.store;
    this._brain = ctx.brain || null;
    this._neural = ctx.neural || null;
    /** @type {string | null} */
    this._sessionId = null;
    /** @type {MediaStream | null} */
    this._stream = null;
    /** @type {(() => void) | null} */
    this._unwatchMic = null;
    this._capture = new AudioCaptureSession({
      onChunk: (chunk) => this._onCaptureChunk(chunk),
      onLevel: (level) => this._setVoiceState({ voiceInputLevel: level }),
      onError: (err) => this._fail(err),
    });
    this._playback = new TtsPlaybackQueue();
    this._playback.onError = (err) => this._announce(err.message);
    this._playback.onStarted = () => {
      this._setPhase("speaking");
      this._setVoiceState({ voiceTtsStatus: "running", voiceInterrupted: false });
      this._brain?.setState?.("voice", { source: "voice-ui", force: true });
    };
    this._playback.onStopped = () => {
      if (this._phase === "speaking") {
        this._setPhase("idle");
        this._setVoiceState({ voiceTtsStatus: "completed" });
        this._brain?.setState?.("idle", { source: "voice-ui" });
      }
      this._syncMicChrome();
    };

    /** @type {VoiceUiPhase} */
    this._phase = "idle";
    this._pressMode = /** @type {"hold"|"toggle"|null} */ (null);
    this._pressStartedAt = 0;
    this._pointerId = null;
    this._uploadChain = Promise.resolve();
    this._chunkQueue = [];
    this._bound = false;
    this._hiddenHandler = null;
    this._turnGeneration = 0;
    /** @type {string | null} */
    this._recoveryToken = null;
    /** @type {string | null} */
    this._conversationId = null;
    /** @type {number | null} */
    this._heartbeatTimer = null;
    this._captureMode = "push_to_talk";
  }

  /** Wire mic button, interrupt control, visibility cleanup. Idempotent. */
  bind() {
    if (this._bound) return;
    this._bound = true;
    const mic = document.getElementById("tdl-v2-voice-mic");
    if (mic) {
      mic.addEventListener("pointerdown", (e) => this._onPointerDown(e));
      mic.addEventListener("pointerup", (e) => this._onPointerUp(e));
      mic.addEventListener("pointercancel", (e) => this._onPointerUp(e));
      mic.addEventListener("keydown", (e) => this._onMicKeyDown(e));
      mic.addEventListener("keyup", (e) => this._onMicKeyUp(e));
      mic.addEventListener("click", (e) => {
        // Click-to-toggle fallback when press was too short / accessibility.
        if (this._pressMode === "toggle") return;
        if (Date.now() - this._pressStartedAt < HOLD_CLICK_MS && this._phase === "idle") {
          e.preventDefault();
          this._pressMode = "toggle";
          void this.beginListening();
        }
      });
    }

    this._ensureChrome();
    this._hiddenHandler = () => {
      if (document.hidden) {
        // Soft park for refresh recovery — do not hard-cancel the conversation.
        this._persistRecovery();
        void this._softPark({ reason: "page_hidden" });
      }
    };
    document.addEventListener("visibilitychange", this._hiddenHandler);
    window.addEventListener("pagehide", this._hiddenHandler);

    this._store.subscribe(() => this._renderFromStore(), "voiceSessionState");
    this._store.subscribe(() => this._renderFromStore(), "voicePendingConfirmation");
    this._store.subscribe(() => this._renderFromStore(), "voiceUiError");
    this._store.subscribe(() => this._syncMicChrome(), "voiceEnrollmentCollecting");
    this._setVoiceState({
      voiceSessionState: "IDLE",
      voiceMicPermission: "unknown",
      voiceUiPhase: "idle",
    });
    void queryMicrophonePermission().then((state) => {
      this._setVoiceState({ voiceMicPermission: state });
    });
    void this._tryRecoverOnLoad();
  }

  /** Full teardown for logout / navigation away. */
  async destroy() {
    document.removeEventListener("visibilitychange", this._hiddenHandler);
    window.removeEventListener("pagehide", this._hiddenHandler);
    this._stopHeartbeat();
    await this.cancel({ reason: "destroy", silent: true });
    this._bound = false;
  }

  // ---------------------------------------------------------------------------
  // Push-to-talk
  // ---------------------------------------------------------------------------

  /** @param {PointerEvent} event */
  async _onPointerDown(event) {
    if (event.button != null && event.button !== 0) return;
    const mic = /** @type {HTMLElement} */ (event.currentTarget);
    this._pressStartedAt = Date.now();
    this._pointerId = event.pointerId;
    try {
      mic.setPointerCapture?.(event.pointerId);
    } catch {
      /* ignore */
    }
    event.preventDefault();

    if (this._phase === "speaking" || this._playback.isPlaying) {
      await this.bargeIn();
      return;
    }

    if (this._pressMode === "toggle" && this._phase === "recording") {
      await this.endListening();
      this._pressMode = null;
      return;
    }

    this._pressMode = "hold";
    this._playback.unlockFromUserGesture();
    await this.beginListening();
  }

  /** @param {PointerEvent} event */
  async _onPointerUp(event) {
    if (this._pointerId != null && event.pointerId !== this._pointerId) return;
    this._pointerId = null;
    const heldMs = Date.now() - this._pressStartedAt;
    if (this._pressMode === "hold") {
      if (heldMs < HOLD_CLICK_MS && this._phase === "recording") {
        // Convert to click-to-stop mode.
        this._pressMode = "toggle";
        this._announce("Enregistrement en cours — appuie à nouveau pour envoyer.");
        return;
      }
      await this.endListening();
      this._pressMode = null;
    }
  }

  /** @param {KeyboardEvent} event */
  async _onMicKeyDown(event) {
    if (event.repeat) return;
    if (event.key !== " " && event.key !== "Enter") return;
    event.preventDefault();
    this._playback.unlockFromUserGesture();
    if (this._phase === "speaking") {
      await this.bargeIn();
      return;
    }
    if (this._phase === "recording") {
      await this.endListening();
      return;
    }
    this._pressMode = "toggle";
    await this.beginListening();
  }

  /** @param {KeyboardEvent} event */
  _onMicKeyUp(event) {
    if (event.key !== " " && event.key !== "Enter") return;
    // Keyboard uses click-to-toggle semantics (accessibility).
  }

  async beginListening() {
    if (this._store.getState().voiceEnrollmentCollecting) {
      this._announce(voiceErrorMessage("enrollment_use_enregistrer"));
      return;
    }
    if (this._phase !== "idle" && this._phase !== "interrupted" && this._phase !== "failed") {
      return;
    }
    this._turnGeneration += 1;
    const gen = this._turnGeneration;
    this._playback.unlockFromUserGesture();
    this._setPhase("listening");
    this._setVoiceState({ voiceUiError: null, voiceInterrupted: false });

    try {
      if (!this._sessionId) {
        const conversationId =
          this._conversationId || this._store.getState().conversationId || null;
        const started = await api.startVoiceSession({
          conversation_id: conversationId,
          capture_mode: this._captureMode || "push_to_talk",
        });
        if (gen !== this._turnGeneration) return;
        this._sessionId = started.session_id;
        this._conversationId = started.conversation_id || conversationId;
        this._recoveryToken = started.recovery_token || null;
        this._persistRecovery();
        this._startHeartbeat();
        this._applySafeState(started);
      }

      const mic = await requestMicrophone();
      if (gen !== this._turnGeneration) {
        if (mic.ok) releaseMediaStream(mic.stream);
        return;
      }
      if (!mic.ok) {
        this._fail(mic.error, mic.state);
        return;
      }
      this._stream = mic.stream;
      this._unwatchMic?.();
      this._unwatchMic = watchMicrophoneRevocation(mic.stream, () => {
        void this.cancel({ reason: "permission_revoked" });
      });
      this._setVoiceState({ voiceMicPermission: "granted" });

      this._setPhase("recording");
      this._brain?.setState?.("listening", { source: "voice-ui", force: true });
      this._neural?.trigger?.("voice", { intensity: 0.4 });
      await this._capture.start(mic.stream);
    } catch (err) {
      this._fail(normalizeVoiceError(err));
    }
  }

  async endListening() {
    if (this._phase !== "recording" && this._phase !== "listening") return;
    const gen = this._turnGeneration;
    const sessionId = this._sessionId;
    if (!sessionId) {
      await this._capture.cancel({ releaseStream: true });
      this._setPhase("idle");
      return;
    }

    try {
      await this._capture.stop({ releaseStream: true });
      this._stream = null;
      this._unwatchMic?.();
      this._unwatchMic = null;

      // Wait for in-flight chunk uploads.
      await this._uploadChain;
      if (gen !== this._turnGeneration) return;

      this._setPhase("transcribing");
      this._brain?.setState?.("thinking", { source: "voice-ui", force: true });
      const result = await api.finishUtterance(sessionId);
      if (gen !== this._turnGeneration) return;
      await this._handleTurnResult(result, gen);
    } catch (err) {
      this._fail(normalizeVoiceError(err));
    }
  }

  /**
   * Interrupt Titan speech and optionally start a new capture.
   */
  async bargeIn() {
    const sessionId = this._sessionId;
    this._playback.stop();
    this._setPhase("interrupted");
    this._setVoiceState({ voiceInterrupted: true, voiceTtsStatus: "interrupted" });
    emitVoiceUiDiagnostic("VOICE_UI_BARGE_IN", { session_id: sessionId });
    if (sessionId) {
      try {
        const state = await api.interruptPlayback(sessionId);
        this._applySafeState(state);
      } catch {
        /* still continue local interrupt */
      }
    }
    // Start a fresh recording turn without creating a duplicate assistant message.
    this._pressMode = "hold";
    this._setPhase("idle");
    await this.beginListening();
  }

  /**
   * @param {{ reason?: string, silent?: boolean }} [opts]
   */
  async cancel(opts = {}) {
    this._turnGeneration += 1;
    const sessionId = this._sessionId;
    this._stopHeartbeat();
    this._playback.stop({ silent: true });
    await this._capture.cancel({ releaseStream: true });
    this._stream = null;
    this._unwatchMic?.();
    this._unwatchMic = null;
    this._sessionId = null;
    this._pressMode = null;
    this._recoveryToken = null;
    this._clearRecovery();
    if (sessionId) {
      try {
        await api.cancelVoiceSession(sessionId);
      } catch {
        /* ignore network on cancel */
      }
    }
    this._setPhase("idle");
    this._setVoiceState({
      voiceSessionState: "IDLE",
      voiceSpeechDetected: false,
      voiceInputLevel: 0,
      voiceInterrupted: false,
      voicePendingConfirmation: null,
      voiceTtsStatus: null,
      voiceTranscriptionStatus: null,
      voiceBrainStatus: null,
      voicePartialTranscript: null,
    });
    if (!opts.silent) {
      emitVoiceUiDiagnostic("VOICE_UI_SESSION_CANCELLED", { reason: opts.reason || "cancel" });
    }
    this._brain?.setState?.("idle", { source: "voice-ui" });
    this._syncMicChrome();
  }

  /**
   * Soft park for tab hide / refresh — keeps recovery token, stops local audio.
   * @param {{ reason?: string }} [opts]
   */
  async _softPark(opts = {}) {
    this._turnGeneration += 1;
    this._playback.stop({ silent: true });
    await this._capture.cancel({ releaseStream: true });
    this._stream = null;
    this._unwatchMic?.();
    this._unwatchMic = null;
    this._pressMode = null;
    this._stopHeartbeat();
    // Keep sessionId + recovery for reconnect; server may still hold session briefly.
    this._setPhase("idle");
    this._setVoiceState({
      voiceSpeechDetected: false,
      voiceInputLevel: 0,
      voiceInterrupted: false,
    });
    emitVoiceUiDiagnostic("VOICE_UI_SESSION_PARKED", { reason: opts.reason || "park" });
    this._brain?.setState?.("idle", { source: "voice-ui" });
    this._syncMicChrome();
  }

  // ---------------------------------------------------------------------------
  // Turn handling
  // ---------------------------------------------------------------------------

  /**
   * @param {object} chunk
   */
  _onCaptureChunk(chunk) {
    if (!this._sessionId || !chunk?.bytes?.length) return;
    const sessionId = this._sessionId;
    const payload = {
      session_id: sessionId,
      audio_base64: bytesToBase64(chunk.bytes),
      sequence: chunk.sequence,
      timestamp_ms: Date.now(),
    };
    this._uploadChain = this._uploadChain
      .then(async () => {
        if (this._sessionId !== sessionId) return;
        const res = await api.sendAudioChunk(payload);
        if (res?.duplicate) return;
        this._applySafeState(res);
        if (res?.barge_in) {
          this._setVoiceState({ voiceInterrupted: true });
        }
      })
      .catch((err) => {
        this._fail(normalizeVoiceError(err));
      });
  }

  /**
   * @param {object} result
   * @param {number} gen
   */
  async _handleTurnResult(result, gen) {
    this._applySafeState(result);
    const pending = result?.pending_identity_confirmation;
    if (pending) {
      this._setPhase("confirming");
      emitVoiceUiDiagnostic("VOICE_UI_IDENTITY_CONFIRMATION_SHOWN", {
        band: pending.confidence_band,
        predicted: pending.predicted_user,
      });
      this._setVoiceState({ voicePendingConfirmation: pending });
      this._renderConfirmBanner(pending);
      if (Array.isArray(result.tts_audio_chunks) && result.tts_audio_chunks.length) {
        try {
          await this._playback.playChunks(result.tts_audio_chunks);
        } catch {
          /* prompt playback optional */
        }
      }
      return;
    }

    const band = result?.voice_identity_confidence_band;
    if (band === "low" || (!result?.voice_current_speaker && band)) {
      // Unknown / restricted — never expose private context in UI chrome.
      this._announce(voiceErrorMessage("speaker_unknown"));
    }

    this._setPhase("thinking");
    this._setVoiceState({ voiceBrainStatus: result?.voice_brain_status || "completed" });

    if (Array.isArray(result.tts_audio_chunks) && result.tts_audio_chunks.length) {
      this._setPhase("speaking");
      try {
        await this._playback.playChunks(result.tts_audio_chunks);
        if (gen === this._turnGeneration) {
          emitVoiceUiDiagnostic("VOICE_UI_SESSION_COMPLETED", {
            session_id: this._sessionId,
          });
          // Keep session alive for continuous multi-turn conversation.
          this._setPhase("idle");
          this._persistRecovery();
        }
      } catch (err) {
        this._announce(normalizeVoiceError(err).message);
        this._setPhase("idle");
      }
    } else {
      this._setPhase("idle");
      emitVoiceUiDiagnostic("VOICE_UI_SESSION_COMPLETED", {
        session_id: this._sessionId,
      });
    }
    this._brain?.setState?.("idle", { source: "voice-ui" });
  }

  /**
   * Confirm medium-confidence identity from UI.
   * @param {string} [user]
   */
  async confirmPendingIdentity(user) {
    if (!this._sessionId) return;
    const gen = this._turnGeneration;
    try {
      this._setPhase("thinking");
      const result = await api.confirmIdentity(this._sessionId, user);
      this._setVoiceState({ voicePendingConfirmation: null });
      this._clearConfirmBanner();
      if (gen !== this._turnGeneration) return;
      await this._handleTurnResult(result, gen);
    } catch (err) {
      this._fail(normalizeVoiceError(err));
    }
  }

  async rejectPendingIdentity() {
    if (!this._sessionId) return;
    try {
      const result = await api.rejectIdentity(this._sessionId);
      this._setVoiceState({
        voicePendingConfirmation: null,
        voiceCurrentSpeaker: null,
      });
      this._clearConfirmBanner();
      this._applySafeState(result);
      this._announce("Identité rejetée — mode restreint.");
      if (Array.isArray(result.tts_audio_chunks) && result.tts_audio_chunks.length) {
        await this._playback.playChunks(result.tts_audio_chunks);
      }
      this._setPhase("idle");
    } catch (err) {
      this._fail(normalizeVoiceError(err));
    }
  }

  // ---------------------------------------------------------------------------
  // State / chrome
  // ---------------------------------------------------------------------------

  /** @param {VoiceUiPhase} phase */
  _setPhase(phase) {
    this._phase = phase;
    this._setVoiceState({ voiceUiPhase: phase });
    this._syncMicChrome();
  }

  /** @param {Partial<import("../core/state-store.js").AppState>} patch */
  _setVoiceState(patch) {
    this._store.setState(patch);
  }

  /** @param {object} safe */
  _applySafeState(safe) {
    if (!safe || typeof safe !== "object") return;
    /** @type {Record<string, unknown>} */
    const patch = {};
    if (safe.voice_session_state != null) patch.voiceSessionState = safe.voice_session_state;
    if (safe.voice_input_level != null) patch.voiceInputLevel = safe.voice_input_level;
    if (safe.voice_speech_detected != null) {
      patch.voiceSpeechDetected = safe.voice_speech_detected;
    }
    if ("voice_current_speaker" in safe) {
      patch.voiceCurrentSpeaker = safe.voice_current_speaker;
    }
    if ("voice_identity_confidence_band" in safe) {
      patch.voiceIdentityConfidenceBand = safe.voice_identity_confidence_band;
    }
    if ("voice_transcription_status" in safe) {
      patch.voiceTranscriptionStatus = safe.voice_transcription_status;
    }
    if ("voice_brain_status" in safe) patch.voiceBrainStatus = safe.voice_brain_status;
    if ("voice_tts_status" in safe) patch.voiceTtsStatus = safe.voice_tts_status;
    if ("voice_interrupted" in safe) patch.voiceInterrupted = safe.voice_interrupted;
    if ("pending_identity_confirmation" in safe) {
      patch.voicePendingConfirmation = safe.pending_identity_confirmation;
    }
    if (safe.last_transcript_preview) {
      patch.voiceTranscriptPreview = safe.last_transcript_preview;
    }
    if (safe.partial_transcript_preview != null) {
      patch.voicePartialTranscript = safe.partial_transcript_preview;
    }
    if (safe.stable_transcript_preview != null) {
      patch.voiceStableTranscript = safe.stable_transcript_preview;
    }
    if (safe.recovery_token) {
      this._recoveryToken = safe.recovery_token;
      this._persistRecovery();
    }
    if (safe.conversation_id) {
      this._conversationId = safe.conversation_id;
    }
    if (safe.continuous_conversation != null) {
      patch.voiceContinuousConversation = Boolean(safe.continuous_conversation);
    }
    // Mirror into workspaceState without duplicating independent stores.
    const ws = { ...(this._store.getState().workspaceState || {}) };
    for (const [k, v] of Object.entries(safe)) {
      if (k.startsWith("voice_") || k === "pending_identity_confirmation") {
        ws[k] = v;
      }
    }
    patch.workspaceState = ws;
    this._store.setState(/** @type {any} */ (patch));
  }

  /**
   * @param {{ code?: string, message?: string } | string} err
   * @param {string} [micState]
   */
  _fail(err, micState) {
    const normalized = typeof err === "string" ? normalizeVoiceError(err) : normalizeVoiceError(err);
    emitVoiceUiDiagnostic("VOICE_UI_SESSION_FAILED", { code: normalized.code });
    void this._capture.cancel({ releaseStream: true });
    this._stream = null;
    this._playback.stop({ silent: true });
    this._unwatchMic?.();
    this._unwatchMic = null;
    this._sessionId = null;
    this._pressMode = null;
    this._setPhase("failed");
    this._setVoiceState({
      voiceUiError: normalized.message,
      voiceMicPermission: micState || this._store.getState().voiceMicPermission,
      voiceSessionState: "FAILED",
    });
    this._announce(normalized.message);
    this._brain?.setState?.("idle", { source: "voice-ui" });
    // Recoverable — return to idle after announcing.
    window.setTimeout(() => {
      if (this._phase === "failed") {
        this._setPhase("idle");
        this._setVoiceState({ voiceSessionState: "IDLE" });
      }
    }, 1200);
  }

  /** @param {string} message */
  _announce(message) {
    const live = document.getElementById("tdl-v2-voice-live");
    if (live) live.textContent = message;
    this._setVoiceState({ voiceUiError: message });
  }

  _ensureChrome() {
    if (!document.getElementById("tdl-v2-voice-live")) {
      const live = document.createElement("div");
      live.id = "tdl-v2-voice-live";
      live.className = "tdl-v2-voice-live";
      live.setAttribute("role", "status");
      live.setAttribute("aria-live", "polite");
      document.body.appendChild(live);
    }
    if (!document.getElementById("tdl-v2-voice-interrupt")) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.id = "tdl-v2-voice-interrupt";
      btn.className = "tdl-v2-voice-interrupt";
      btn.hidden = true;
      btn.textContent = "Interrompre";
      btn.setAttribute("aria-label", "Interrompre Titan");
      btn.addEventListener("click", () => void this.bargeIn());
      const composer = document.getElementById("tdl-v2-chat-composer");
      (composer?.parentElement || document.body).appendChild(btn);
    }
    if (!document.getElementById("tdl-v2-voice-identity-badge")) {
      const badge = document.createElement("div");
      badge.id = "tdl-v2-voice-identity-badge";
      badge.className = "tdl-v2-voice-identity-badge";
      badge.hidden = true;
      badge.setAttribute("aria-live", "polite");
      const topbar = document.getElementById("tdl-v2-region-topbar");
      (topbar || document.body).appendChild(badge);
    }
    if (!document.getElementById("tdl-v2-voice-confirm")) {
      const bar = document.createElement("div");
      bar.id = "tdl-v2-voice-confirm";
      bar.className = "tdl-v2-voice-confirm";
      bar.hidden = true;
      bar.innerHTML = `
        <p class="tdl-v2-voice-confirm__text" id="tdl-v2-voice-confirm-text"></p>
        <div class="tdl-v2-voice-confirm__actions">
          <button type="button" class="tdl-v2-btn tdl-v2-btn--primary" id="tdl-v2-voice-confirm-yes">Confirmer</button>
          <button type="button" class="tdl-v2-btn tdl-v2-btn--ghost" id="tdl-v2-voice-confirm-no">Rejeter</button>
        </div>
      `;
      document.body.appendChild(bar);
      bar.querySelector("#tdl-v2-voice-confirm-yes")?.addEventListener("click", () => {
        const pending = this._store.getState().voicePendingConfirmation;
        void this.confirmPendingIdentity(pending?.predicted_user);
      });
      bar.querySelector("#tdl-v2-voice-confirm-no")?.addEventListener("click", () => {
        void this.rejectPendingIdentity();
      });
    }
    // Level meter inside mic ring
    const mic = document.getElementById("tdl-v2-voice-mic");
    if (mic && !mic.querySelector(".tdl-v2-voice-mic__level")) {
      const level = document.createElement("span");
      level.className = "tdl-v2-voice-mic__level";
      level.setAttribute("aria-hidden", "true");
      mic.appendChild(level);
    }
  }

  _syncMicChrome() {
    const mic = document.getElementById("tdl-v2-voice-mic");
    const interrupt = document.getElementById("tdl-v2-voice-interrupt");
    if (!mic) return;
    const enrollmentLock = Boolean(this._store.getState().voiceEnrollmentCollecting);
    mic.classList.remove(
      "tdl-v2-voice-mic--idle",
      "tdl-v2-voice-mic--listening",
      "tdl-v2-voice-mic--recording",
      "tdl-v2-voice-mic--busy",
      "tdl-v2-voice-mic--error",
      "tdl-v2-voice-mic--enrollment-locked",
    );
    if (enrollmentLock) {
      mic.classList.add("tdl-v2-voice-mic--idle", "tdl-v2-voice-mic--enrollment-locked");
      mic.toggleAttribute("disabled", true);
      mic.setAttribute("aria-disabled", "true");
      mic.setAttribute("aria-pressed", "false");
      mic.setAttribute(
        "aria-label",
        "Désactivé pendant l’enrollment — utilise Enregistrer",
      );
      mic.title = "Désactivé pendant l’enrollment — utilise Enregistrer";
      if (interrupt) interrupt.hidden = true;
      return;
    }
    mic.removeAttribute("disabled");
    mic.setAttribute("aria-disabled", "false");
    const phase = this._phase;
    let cls = "tdl-v2-voice-mic--idle";
    let label = "Maintenir pour parler";
    let pressed = "false";
    if (phase === "listening" || phase === "recording") {
      cls = phase === "recording" ? "tdl-v2-voice-mic--recording" : "tdl-v2-voice-mic--listening";
      label = phase === "recording" ? "Relâcher pour envoyer" : "Écoute…";
      pressed = "true";
    } else if (phase === "speaking") {
      cls = "tdl-v2-voice-mic--busy";
      label = "Interrompre Titan";
    } else if (phase === "transcribing" || phase === "thinking" || phase === "identifying" || phase === "confirming") {
      cls = "tdl-v2-voice-mic--busy";
      label = "Traitement vocal…";
    } else if (phase === "failed") {
      cls = "tdl-v2-voice-mic--error";
      label = "Erreur — réessayer";
    }
    mic.classList.add(cls);
    mic.setAttribute("aria-pressed", pressed);
    mic.setAttribute("aria-label", label);
    mic.title = label;
    if (interrupt) {
      interrupt.hidden = phase !== "speaking";
    }

    const level = this._store.getState().voiceInputLevel || 0;
    const levelEl = mic.querySelector(".tdl-v2-voice-mic__level");
    if (levelEl instanceof HTMLElement) {
      levelEl.style.transform = `scaleY(${0.15 + level * 0.85})`;
    }

    // Titan Core subtle pulse while listening.
    const core = document.querySelector(".tdl-v2-satellite-core");
    if (core) {
      core.classList.toggle(
        "tdl-v2-satellite-core--voice-listening",
        phase === "listening" || phase === "recording",
      );
      core.classList.toggle("tdl-v2-satellite-core--voice-speaking", phase === "speaking");
    }
  }

  _renderFromStore() {
    const state = this._store.getState();
    const badge = document.getElementById("tdl-v2-voice-identity-badge");
    if (badge) {
      const speaker = state.voiceCurrentSpeaker;
      const band = state.voiceIdentityConfidenceBand;
      const pending = state.voicePendingConfirmation;
      if (pending) {
        badge.hidden = false;
        badge.dataset.state = "confirm";
        badge.textContent = pending.predicted_user
          ? `Confirmation — ${pending.predicted_user}`
          : "Confirmation requise";
      } else if (speaker === "Nolan" || speaker === "Ibrahim") {
        badge.hidden = false;
        badge.dataset.state = "known";
        badge.textContent = speaker;
      } else if (band === "low" || state.voiceSessionState === "IDENTIFYING_SPEAKER") {
        badge.hidden = false;
        badge.dataset.state = "unknown";
        badge.textContent = "Inconnu";
      } else if (!speaker && (state.voiceUiPhase === "recording" || state.voiceUiPhase === "speaking")) {
        badge.hidden = false;
        badge.dataset.state = "unknown";
        badge.textContent = "Inconnu";
      } else {
        badge.hidden = true;
      }
    }
    this._syncMicChrome();
  }

  /** @param {object} pending */
  _renderConfirmBanner(pending) {
    const bar = document.getElementById("tdl-v2-voice-confirm");
    const text = document.getElementById("tdl-v2-voice-confirm-text");
    if (!bar || !text) return;
    const who = pending.predicted_user || "un locuteur connu";
    const band = pending.confidence_band === "ambiguous" ? "ambigüe" : "moyenne";
    text.textContent = `Identité ${band} : ${who}. Confirmer ?`;
    bar.hidden = false;
  }

  _clearConfirmBanner() {
    const bar = document.getElementById("tdl-v2-voice-confirm");
    if (bar) bar.hidden = true;
  }

  // ---------------------------------------------------------------------------
  // Phase 20.5 — continuity / recovery / heartbeat
  // ---------------------------------------------------------------------------

  _persistRecovery() {
    if (!this._recoveryToken && !this._conversationId) return;
    try {
      sessionStorage.setItem(
        RECOVERY_STORAGE_KEY,
        JSON.stringify({
          recovery_token: this._recoveryToken,
          conversation_id: this._conversationId,
          session_id: this._sessionId,
          capture_mode: this._captureMode,
        }),
      );
    } catch {
      /* private mode / quota */
    }
  }

  _clearRecovery() {
    try {
      sessionStorage.removeItem(RECOVERY_STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }

  async _tryRecoverOnLoad() {
    let raw = null;
    try {
      raw = sessionStorage.getItem(RECOVERY_STORAGE_KEY);
    } catch {
      return;
    }
    if (!raw) return;
    let saved;
    try {
      saved = JSON.parse(raw);
    } catch {
      this._clearRecovery();
      return;
    }
    if (!saved?.recovery_token && !saved?.conversation_id) return;
    try {
      const recovered = await api.recoverVoiceSession({
        recovery_token: saved.recovery_token || null,
        conversation_id: saved.conversation_id || null,
        capture_mode: saved.capture_mode || "push_to_talk",
      });
      this._sessionId = recovered.session_id;
      this._conversationId = recovered.conversation_id || saved.conversation_id;
      this._recoveryToken = recovered.recovery_token || saved.recovery_token;
      this._applySafeState(recovered);
      this._persistRecovery();
      this._startHeartbeat();
      emitVoiceUiDiagnostic("VOICE_UI_SESSION_RECOVERED", {
        session_id: this._sessionId,
      });
    } catch {
      this._clearRecovery();
    }
  }

  _startHeartbeat() {
    this._stopHeartbeat();
    this._heartbeatTimer = window.setInterval(() => {
      const sessionId = this._sessionId;
      if (!sessionId) {
        this._stopHeartbeat();
        return;
      }
      void api.heartbeatVoiceSession(sessionId).catch((err) => {
        if (err?.code === "session_error" || err?.status === 404) {
          this._sessionId = null;
          this._stopHeartbeat();
        }
      });
    }, HEARTBEAT_MS);
  }

  _stopHeartbeat() {
    if (this._heartbeatTimer != null) {
      window.clearInterval(this._heartbeatTimer);
      this._heartbeatTimer = null;
    }
  }
}

/**
 * Record a single enrollment / verification sample as WAV base64.
 * @param {number} [maxMs]
 * @returns {Promise<{ audio_base64: string, duration_ms: number }>}
 */
export async function recordSampleWav(maxMs = 8000) {
  const mic = await requestMicrophone();
  if (!mic.ok) {
    throw Object.assign(new Error(mic.error.message), { code: mic.error.code });
  }
  const pcmChunks = [];
  let sampleRate = 16000;
  const capture = new AudioCaptureSession({
    sampleRate: 16000,
    chunkDurationMs: 200,
    onChunk: (chunk) => {
      if (chunk.bytes?.length) pcmChunks.push(chunk.bytes);
    },
  });
  try {
    await capture.start(mic.stream);
    await new Promise((resolve) => {
      const timer = window.setTimeout(resolve, maxMs);
      // Caller can stop early via returned controller — for wizard we use fixed window
      // plus an optional stop button that clears this promise externally.
      /** @type {any} */ (recordSampleWav)._stop = () => {
        clearTimeout(timer);
        resolve();
      };
    });
    await capture.stop({ releaseStream: true });
    const total = pcmChunks.reduce((n, c) => n + c.length, 0);
    const merged = new Uint8Array(total);
    let offset = 0;
    for (const part of pcmChunks) {
      merged.set(part, offset);
      offset += part.length;
    }
    // PCM mode emits Int16 bytes — encode as WAV for enrollment validators.
    const wav = encodeWavPcm16(merged, sampleRate);
    return {
      audio_base64: bytesToBase64(wav),
      duration_ms: Math.round((merged.byteLength / 2 / sampleRate) * 1000),
    };
  } finally {
    releaseMediaStream(mic.stream);
    /** @type {any} */ (recordSampleWav)._stop = null;
  }
}

export function stopSampleRecording() {
  /** @type {any} */ (recordSampleWav)._stop?.();
}
