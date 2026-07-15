/** Titan Frontend V2 — Conversation session persistence (Web Runtime V1). */

const CONVERSATION_STORAGE_KEY = "titan_v2_conversation_id";
const REQUEST_STORAGE_KEY = "titan_v2_last_request_id";

/** @returns {string | null} */
export function getStoredConversationId() {
  try {
    return localStorage.getItem(CONVERSATION_STORAGE_KEY);
  } catch {
    return null;
  }
}

/** @param {string | null | undefined} conversationId */
export function saveConversationId(conversationId) {
  if (!conversationId) return;
  try {
    localStorage.setItem(CONVERSATION_STORAGE_KEY, conversationId);
  } catch {
    /* storage unavailable */
  }
}

/** @returns {string | null} */
export function getStoredRequestId() {
  try {
    return localStorage.getItem(REQUEST_STORAGE_KEY);
  } catch {
    return null;
  }
}

/** @param {string | null | undefined} requestId */
export function saveRequestId(requestId) {
  if (!requestId) return;
  try {
    localStorage.setItem(REQUEST_STORAGE_KEY, requestId);
  } catch {
    /* storage unavailable */
  }
}

/** Clear persisted conversation identity (new session). */
export function clearConversationSession() {
  try {
    localStorage.removeItem(CONVERSATION_STORAGE_KEY);
    localStorage.removeItem(REQUEST_STORAGE_KEY);
  } catch {
    /* storage unavailable */
  }
}

/**
 * @param {string} [prefix="req"]
 * @returns {string}
 */
export function createClientRequestId(prefix = "req") {
  const stamp = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 8);
  return `${prefix}-${stamp}-${rand}`;
}
