/** Titan Voice UI — French-first user-facing error messages (Phase 20.4). */

/** @type {Record<string, string>} */
const FR_ERRORS = Object.freeze({
  microphone_denied:
    "Accès au microphone refusé. Autorise Titan dans les paramètres du navigateur, puis réessaie.",
  microphone_unavailable:
    "Aucun microphone disponible sur cet appareil.",
  no_microphone:
    "Aucun microphone trouvé. Branche un micro, puis réessaie.",
  insecure_context:
    "Le microphone nécessite une connexion sécurisée (HTTPS ou localhost).",
  permission_revoked:
    "L’accès au microphone a été révoqué pendant la session. Réactive-le pour continuer.",
  malformed_audio:
    "Audio illisible. Réessaie d’enregistrer clairement.",
  sample_too_short:
    "Échantillon trop court. Parle un peu plus longtemps.",
  too_much_silence:
    "Trop de silence détecté. Rapproche-toi du micro et réessaie.",
  low_volume:
    "Niveau micro trop bas. Rapproche-toi du micro ou augmente le gain.",
  clipping:
    "Audio saturé. Éloigne-toi un peu du micro et réessaie.",
  false_speech:
    "Bruit trop court ignoré. Parle un peu plus clairement.",
  long_pause:
    "Longue pause détectée. Reprends quand tu es prêt.",
  unsupported_format:
    "Format audio non supporté par ce navigateur.",
  speaker_unknown:
    "Locuteur non reconnu. Le mode restreint est actif — aucune mémoire personnelle.",
  identity_ambiguous:
    "Identité ambiguë. Confirme si tu es Nolan ou Ibrahim.",
  stt_failure:
    "La transcription a échoué. Réessaie dans un instant.",
  tts_failure:
    "La synthèse vocale a échoué. La réponse texte reste disponible.",
  provider_timeout:
    "Le fournisseur vocal a expiré. Réessaie.",
  brain_busy:
    "Titan réfléchit déjà. Attends la fin du tour, ou interromps.",
  session_expired:
    "Session expirée. Reconnecte-toi pour continuer.",
  network_disconnect:
    "Connexion interrompue. L’état vocal a été réinitialisé.",
  session_failed:
    "La session vocale a échoué. Tu peux réessayer.",
  autoplay_blocked:
    "La lecture audio est bloquée par le navigateur. Interagis à nouveau pour entendre Titan.",
  always_listening_disabled:
    "Le mode écoute continue n’est pas activé. Utilise le bouton micro (push-to-talk).",
  consent_required:
    "Le consentement est requis avant l’enregistrement d’échantillons vocaux.",
  enrollment_use_enregistrer:
    "Enrollment biométrique actif — utilise le bouton Enregistrer (pas le micro du compositeur).",
  recording_failed:
    "Échec de l’enregistrement. Réessaie.",
  default:
    "Une erreur vocale s’est produite. L’interface a été réinitialisée.",
});

/**
 * Map API / browser error codes to French copy.
 * @param {string | null | undefined} code
 * @param {string | null | undefined} [fallback]
 * @returns {string}
 */
export function voiceErrorMessage(code, fallback) {
  const key = String(code || "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  const aliases = {
    notallowederror: "microphone_denied",
    notfounderror: "no_microphone",
    notreadableerror: "microphone_unavailable",
    securityerror: "insecure_context",
    overconstrainederror: "microphone_unavailable",
    abortederror: "recording_failed",
    rejected_audio: "malformed_audio",
    empty_chunk: "malformed_audio",
    empty: "sample_too_short",
    too_short: "sample_too_short",
    pure_silence: "too_much_silence",
    unsupported_audio_format: "unsupported_format",
    unsupported_audio: "unsupported_format",
    empty_transcript: "stt_failure",
    unauthorized: "session_expired",
    internal: "session_failed",
    voice_error: "session_failed",
    live_session_error: "session_failed",
    session_error: "session_failed",
    provider_timeout: "provider_timeout",
    network: "network_disconnect",
    request_failed: "network_disconnect",
    low_volume: "low_volume",
    false_speech: "false_speech",
    long_pause: "long_pause",
  };
  const mapped = aliases[key] || key;
  return FR_ERRORS[mapped] || fallback || FR_ERRORS.default;
}

/**
 * @param {unknown} err
 * @returns {{ code: string, message: string }}
 */
export function normalizeVoiceError(err) {
  if (!err) {
    return { code: "default", message: FR_ERRORS.default };
  }
  const code =
    (typeof err === "object" && (err.code || err.name)) ||
    (typeof err === "string" ? err : "default");
  const rawMessage =
    typeof err === "object" && err.message ? String(err.message) : "";
  return {
    code: String(code),
    message: voiceErrorMessage(code, rawMessage || undefined),
  };
}
