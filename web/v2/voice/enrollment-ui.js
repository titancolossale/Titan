/** Titan Voice UI — guided enrollment panel (Phase 20.4). */

import { emitVoiceUiDiagnostic } from "./diagnostics.js";
import { normalizeVoiceError, voiceErrorMessage } from "./errors.js";
import * as api from "./voice-api.js";
import { recordSampleWav, stopSampleRecording } from "./voice-controller.js";

const CONSENT_FR = `Les échantillons vocaux servent uniquement à reconnaître Nolan ou Ibrahim.
L'audio brut est temporaire par défaut — seul le profil dérivé est conservé.
La reconnaissance vocale n'autorise jamais seule une action destructive.
Tu peux révoquer ou remplacer ton profil à tout moment.`;

const CONSENT_EN = `Voice samples are used only to recognize Nolan or Ibrahim.
Raw audio is temporary by default — only the derived profile is retained.
Voice recognition is never sole authorization for destructive actions.
You can revoke or replace your profile at any time.`;

/**
 * Build / refresh the Voice center panel enrollment UI.
 * @param {HTMLElement} root
 * @param {object} ctx
 * @param {import("../core/state-store.js").StateStore} ctx.store
 */
export function mountEnrollmentPanel(root, ctx) {
  const store = ctx.store;
  root.innerHTML = "";
  root.classList.add("tdl-v2-voice-panel");

  const header = document.createElement("header");
  header.className = "tdl-v2-screen-header";
  header.innerHTML = `
    <h2 class="tdl-v2-screen-header__title">Voice</h2>
    <p class="tdl-v2-screen-header__subtitle">Enrollment et session vocale — Nolan &amp; Ibrahim</p>
  `;

  const body = document.createElement("div");
  body.className = "tdl-v2-screen-body tdl-v2-voice-panel__body";
  body.innerHTML = `
    <section class="tdl-v2-voice-enroll" aria-label="Enrollment vocal">
      <div class="tdl-v2-voice-enroll__locale">
        <label for="tdl-v2-voice-locale">Langue</label>
        <select id="tdl-v2-voice-locale" aria-label="Langue d'enrollment">
          <option value="fr-FR" selected>Français</option>
          <option value="en-US">English</option>
        </select>
      </div>
      <div class="tdl-v2-voice-enroll__user">
        <p class="tdl-v2-voice-enroll__label">Identité à enrôler</p>
        <div class="tdl-v2-voice-enroll__user-row">
          <button type="button" class="tdl-v2-btn tdl-v2-btn--ghost" data-user="Nolan">Nolan</button>
          <button type="button" class="tdl-v2-btn tdl-v2-btn--ghost" data-user="Ibrahim">Ibrahim</button>
        </div>
      </div>
      <div class="tdl-v2-voice-enroll__status" id="tdl-v2-voice-enroll-status" aria-live="polite">
        Chargement du statut…
      </div>
      <div class="tdl-v2-voice-enroll__preflight" id="tdl-v2-voice-preflight" aria-live="polite">
        Pre-flight production…
      </div>
      <div class="tdl-v2-voice-enroll__consent" id="tdl-v2-voice-consent" hidden>
        <p class="tdl-v2-voice-enroll__consent-text" id="tdl-v2-voice-consent-text"></p>
        <label class="tdl-v2-voice-enroll__consent-check">
          <input type="checkbox" id="tdl-v2-voice-consent-check" />
          <span>J’accepte — démarrer l’enrollment</span>
        </label>
        <button type="button" class="tdl-v2-btn tdl-v2-btn--primary" id="tdl-v2-voice-consent-start" disabled>
          Continuer
        </button>
      </div>
      <div class="tdl-v2-voice-enroll__wizard" id="tdl-v2-voice-wizard" hidden>
        <p class="tdl-v2-voice-enroll__progress" id="tdl-v2-voice-progress"></p>
        <blockquote class="tdl-v2-voice-enroll__phrase" id="tdl-v2-voice-phrase"></blockquote>
        <p class="tdl-v2-voice-enroll__feedback" id="tdl-v2-voice-feedback" role="status"></p>
        <div class="tdl-v2-voice-enroll__actions">
          <button type="button" class="tdl-v2-btn tdl-v2-btn--primary" id="tdl-v2-voice-record-sample">
            Enregistrer
          </button>
          <button type="button" class="tdl-v2-btn tdl-v2-btn--ghost" id="tdl-v2-voice-stop-sample" hidden>
            Stop
          </button>
          <button type="button" class="tdl-v2-btn tdl-v2-btn--ghost" id="tdl-v2-voice-finish" hidden>
            Terminer
          </button>
          <button type="button" class="tdl-v2-btn tdl-v2-btn--ghost" id="tdl-v2-voice-verify" hidden>
            Vérifier
          </button>
          <button type="button" class="tdl-v2-btn tdl-v2-btn--ghost" id="tdl-v2-voice-cancel-enroll">
            Annuler
          </button>
        </div>
      </div>
      <div class="tdl-v2-voice-enroll__revoke">
        <button type="button" class="tdl-v2-btn tdl-v2-btn--ghost" id="tdl-v2-voice-revoke" hidden>
          Révoquer le profil actif
        </button>
      </div>
    </section>
    <section class="tdl-v2-voice-live-hint" aria-label="Session vocale">
      <p>Utilise le micro du compositeur pour le push-to-talk. Le mode écoute continue n’est pas activé.</p>
      <p class="tdl-v2-voice-live-hint__state" id="tdl-v2-voice-session-hint"></p>
    </section>
  `;

  root.append(header, body);

  /** @type {string | null} */
  let selectedUser = null;
  /** @type {string | null} */
  let sessionId = null;
  /** @type {object | null} */
  let script = null;
  let consented = false;
  let recording = false;

  const localeEl = /** @type {HTMLSelectElement} */ (body.querySelector("#tdl-v2-voice-locale"));
  const statusEl = body.querySelector("#tdl-v2-voice-enroll-status");
  const preflightEl = body.querySelector("#tdl-v2-voice-preflight");
  const consentBox = body.querySelector("#tdl-v2-voice-consent");
  const consentText = body.querySelector("#tdl-v2-voice-consent-text");
  const consentCheck = /** @type {HTMLInputElement} */ (body.querySelector("#tdl-v2-voice-consent-check"));
  const consentStart = /** @type {HTMLButtonElement} */ (body.querySelector("#tdl-v2-voice-consent-start"));
  const wizard = body.querySelector("#tdl-v2-voice-wizard");
  const phraseEl = body.querySelector("#tdl-v2-voice-phrase");
  const progressEl = body.querySelector("#tdl-v2-voice-progress");
  const feedbackEl = body.querySelector("#tdl-v2-voice-feedback");
  const recordBtn = /** @type {HTMLButtonElement} */ (body.querySelector("#tdl-v2-voice-record-sample"));
  const stopBtn = /** @type {HTMLButtonElement} */ (body.querySelector("#tdl-v2-voice-stop-sample"));
  const finishBtn = /** @type {HTMLButtonElement} */ (body.querySelector("#tdl-v2-voice-finish"));
  const verifyBtn = /** @type {HTMLButtonElement} */ (body.querySelector("#tdl-v2-voice-verify"));
  const cancelBtn = body.querySelector("#tdl-v2-voice-cancel-enroll");
  const revokeBtn = /** @type {HTMLButtonElement} */ (body.querySelector("#tdl-v2-voice-revoke"));
  const sessionHint = body.querySelector("#tdl-v2-voice-session-hint");

  function locale() {
    return localeEl.value || "fr-FR";
  }

  function setFeedback(msg, kind = "info") {
    if (!feedbackEl) return;
    feedbackEl.textContent = msg || "";
    feedbackEl.dataset.kind = kind;
  }

  async function refreshStatus(user) {
    try {
      const data = await api.getEnrollmentStatus(user ? { user } : {});
      const active = data?.active_profile;
      const ws = data?.workspace || {};
      store.setState({
        voiceEnrollmentStatus: ws.voice_enrollment_status || active?.enrollment_status || null,
        voiceSamplesCollected: ws.voice_samples_collected ?? null,
        voiceSamplesRequired: ws.voice_samples_required ?? null,
        voiceVerificationStatus: ws.voice_verification_status || null,
        workspaceState: {
          ...(store.getState().workspaceState || {}),
          ...ws,
        },
      });
      if (statusEl) {
        if (active?.active) {
          statusEl.textContent = `Profil actif : ${active.display_name || active.user_id} (${active.enrollment_status})`;
          revokeBtn.hidden = false;
          revokeBtn.dataset.user = active.user_id;
        } else {
          statusEl.textContent = user
            ? `Aucun profil actif pour ${user}.`
            : "Sélectionne Nolan ou Ibrahim pour commencer.";
          revokeBtn.hidden = true;
        }
      }
    } catch (err) {
      if (statusEl) {
        statusEl.textContent = normalizeVoiceError(err).message;
      }
    }
  }

  async function refreshPreflight() {
    if (!preflightEl) return;
    try {
      const report = await api.getEnrollmentPreflight();
      const overall = report?.overall_status || "UNKNOWN";
      const ready = Boolean(report?.ready_for_real_enrollment);
      const blocking = Array.isArray(report?.blocking_checks)
        ? report.blocking_checks.join(", ")
        : "";
      preflightEl.textContent = ready
        ? `Pre-flight ${overall} — environnement prêt (aucun enregistrement encore).`
        : `Pre-flight ${overall} — bloqué: ${blocking || "voir diagnostics"}.`;
      preflightEl.dataset.ready = ready ? "true" : "false";
      emitVoiceUiDiagnostic("VOICE_UI_ENROLLMENT_PREFLIGHT", {
        overall,
        ready,
        blocking_count: Array.isArray(report?.blocking_checks)
          ? report.blocking_checks.length
          : 0,
      });
    } catch (err) {
      preflightEl.textContent = `Pre-flight indisponible: ${normalizeVoiceError(err).message}`;
      preflightEl.dataset.ready = "false";
    }
  }

  function showConsent(user) {
    selectedUser = user;
    consented = false;
    consentCheck.checked = false;
    consentStart.disabled = true;
    if (consentText) {
      consentText.textContent = locale().startsWith("en") ? CONSENT_EN : CONSENT_FR;
    }
    consentBox.hidden = false;
    wizard.hidden = true;
  }

  body.querySelectorAll("[data-user]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const user = btn.getAttribute("data-user");
      body.querySelectorAll("[data-user]").forEach((b) => b.classList.remove("is-selected"));
      btn.classList.add("is-selected");
      showConsent(user);
      void refreshStatus(user);
    });
  });

  consentCheck.addEventListener("change", () => {
    consentStart.disabled = !consentCheck.checked;
  });

  consentStart.addEventListener("click", async () => {
    if (!consentCheck.checked || !selectedUser) {
      setFeedback(voiceErrorMessage("consent_required"), "error");
      return;
    }
    consented = true;
    try {
      const data = await api.startEnrollment({
        user: selectedUser,
        locale: locale(),
        replace_existing: true,
      });
      sessionId = data.session?.session_id || null;
      script = data.script || null;
      consentBox.hidden = true;
      wizard.hidden = false;
      updateWizard(data.session, data.next_phrase);
      store.setState({
        voiceEnrollmentStatus: data.session?.status || "COLLECTING",
        voiceSamplesCollected: data.session?.samples_collected ?? 0,
        voiceSamplesRequired: data.session?.samples_required ?? 3,
      });
    } catch (err) {
      setFeedback(normalizeVoiceError(err).message, "error");
    }
  });

  function updateWizard(session, nextPhrase) {
    const collected = session?.samples_collected ?? 0;
    const required = session?.samples_required ?? 3;
    if (progressEl) {
      progressEl.textContent = `Échantillons : ${collected} / ${required}`;
    }
    const phrase =
      nextPhrase?.text ||
      script?.phrases?.[collected]?.text ||
      script?.phrases?.[collected] ||
      "Lis la phrase à voix haute.";
    if (phraseEl) phraseEl.textContent = typeof phrase === "string" ? phrase : String(phrase);
    finishBtn.hidden = !(session?.samples_collected >= session?.samples_required);
    verifyBtn.hidden = session?.status !== "VERIFYING" && !session?.pending_profile_id;
    if (session?.status === "VERIFYING" || session?.pending_profile_id) {
      verifyBtn.hidden = false;
      if (phraseEl) {
        phraseEl.textContent =
          locale().startsWith("en")
            ? "Record a fresh verification phrase."
            : "Enregistre une phrase de vérification (nouvelle).";
      }
    }
  }

  recordBtn.addEventListener("click", async () => {
    if (!consented || !sessionId) {
      setFeedback(voiceErrorMessage("consent_required"), "error");
      return;
    }
    if (recording) return;
    recording = true;
    recordBtn.disabled = true;
    stopBtn.hidden = false;
    setFeedback(locale().startsWith("en") ? "Recording…" : "Enregistrement…", "info");
    try {
      // Fixed window; Stop ends early.
      const samplePromise = recordSampleWav(7000);
      const sample = await samplePromise;
      if (verifyBtn && !verifyBtn.hidden && sessionId) {
        const result = await api.verifyEnrollment({
          session_id: sessionId,
          audio_base64: sample.audio_base64,
        });
        if (result.ok && result.activated) {
          setFeedback(
            locale().startsWith("en")
              ? "Verification succeeded — profile active."
              : "Vérification réussie — profil activé.",
            "ok",
          );
          store.setState({
            voiceEnrollmentStatus: "ENROLLED",
            voiceVerificationStatus: "passed",
          });
          wizard.hidden = true;
          await refreshStatus(selectedUser);
        } else {
          setFeedback(
            result.verification?.reason ||
              (locale().startsWith("en")
                ? "Verification failed — you can retry."
                : "Vérification échouée — tu peux réessayer."),
            "error",
          );
          store.setState({ voiceVerificationStatus: "failed" });
        }
      } else {
        const result = await api.submitEnrollmentSample({
          session_id: sessionId,
          audio_base64: sample.audio_base64,
        });
        if (result.accepted) {
          setFeedback(
            locale().startsWith("en") ? "Sample accepted." : "Échantillon accepté.",
            "ok",
          );
          updateWizard(result.session, result.next_phrase);
          store.setState({
            voiceSamplesCollected: result.session?.samples_collected ?? null,
            voiceEnrollmentStatus: result.session?.status || null,
          });
          if (result.ready_to_finish) finishBtn.hidden = false;
        } else {
          const reason =
            result.validation?.reason ||
            voiceErrorMessage(result.validation?.reject_code || "malformed_audio");
          setFeedback(
            locale().startsWith("en")
              ? `Sample rejected: ${reason}`
              : `Échantillon refusé : ${reason}`,
            "error",
          );
        }
      }
    } catch (err) {
      setFeedback(normalizeVoiceError(err).message, "error");
    } finally {
      recording = false;
      recordBtn.disabled = false;
      stopBtn.hidden = true;
    }
  });

  stopBtn.addEventListener("click", () => stopSampleRecording());

  finishBtn.addEventListener("click", async () => {
    if (!sessionId) return;
    try {
      const result = await api.finishEnrollment(sessionId);
      setFeedback(
        result.message ||
          (locale().startsWith("en")
            ? "Profile built — record a verification sample."
            : "Profil créé — enregistre une vérification."),
        "ok",
      );
      updateWizard(result.session, null);
      verifyBtn.hidden = false;
      finishBtn.hidden = true;
    } catch (err) {
      setFeedback(normalizeVoiceError(err).message, "error");
    }
  });

  verifyBtn.addEventListener("click", () => {
    // Verification uses the same record button path when verify is visible.
    setFeedback(
      locale().startsWith("en")
        ? "Press Record for a fresh verification sample."
        : "Appuie sur Enregistrer pour la vérification.",
      "info",
    );
  });

  cancelBtn?.addEventListener("click", async () => {
    if (sessionId) {
      try {
        await api.cancelEnrollment(sessionId);
      } catch {
        /* ignore */
      }
    }
    sessionId = null;
    consented = false;
    wizard.hidden = true;
    consentBox.hidden = true;
    setFeedback("");
    await refreshStatus(selectedUser);
  });

  revokeBtn.addEventListener("click", async () => {
    const user = revokeBtn.dataset.user || selectedUser;
    if (!user) return;
    try {
      await api.revokeEnrollmentProfile({ user });
      setFeedback(
        locale().startsWith("en") ? "Profile revoked." : "Profil révoqué.",
        "ok",
      );
      await refreshStatus(user);
    } catch (err) {
      setFeedback(normalizeVoiceError(err).message, "error");
    }
  });

  store.subscribe((state) => {
    if (!sessionHint) return;
    const phase = state.voiceUiPhase || "idle";
    const speaker = state.voiceCurrentSpeaker || "—";
    sessionHint.textContent = `État session : ${state.voiceSessionState || "IDLE"} · UI : ${phase} · Locuteur : ${speaker}`;
  });

  void refreshStatus();
  void refreshPreflight();
  emitVoiceUiDiagnostic("VOICE_UI_SESSION_STARTED", { surface: "enrollment_panel" });
}
