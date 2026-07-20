/** Titan Frontend V2 — Durable conversation API client (Phase 12.1). */

import { authHeaders } from "./web-auth.js";

/**
 * @param {string} path
 * @param {RequestInit} [init]
 */
async function convFetch(path, init = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init.headers || {}),
    },
  });
  if (response.status === 401) {
    const err = new Error("Session expirée.");
    err.code = "session_expired";
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
    const message =
      (typeof detail === "object" && detail?.message) ||
      (typeof detail === "string" ? detail : null) ||
      data?.message ||
      response.statusText;
    const err = new Error(message || "Erreur conversation");
    err.code = (typeof detail === "object" && detail?.code) || data?.code || "request_failed";
    err.status = response.status;
    throw err;
  }
  return data;
}

/** @returns {Promise<{ conversations: Array<object>, total: number }>} */
export async function listConversations(limit = 20) {
  const data = await convFetch(`/api/conversations?limit=${limit}&offset=0`);
  return {
    conversations: data.conversations ?? [],
    total: data.total ?? 0,
  };
}

/** @returns {Promise<object>} */
export async function createConversation(title = "Nouvelle conversation") {
  return convFetch("/api/conversations", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

/**
 * @param {string} conversationId
 * @returns {Promise<{ conversation: object, messages: Array<object> }>}
 */
export async function loadConversation(conversationId) {
  const data = await convFetch(
    `/api/conversations/${encodeURIComponent(conversationId)}?limit=200&offset=0`,
  );
  return {
    conversation: data.conversation,
    messages: data.messages ?? [],
  };
}

/**
 * @param {string} conversationId
 * @param {string} title
 */
export async function renameConversation(conversationId, title) {
  return convFetch(`/api/conversations/${encodeURIComponent(conversationId)}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

/**
 * @param {string} conversationId
 * @param {boolean} [archived=true]
 */
export async function archiveConversation(conversationId, archived = true) {
  return convFetch(
    `/api/conversations/${encodeURIComponent(conversationId)}/archive`,
    {
      method: "POST",
      body: JSON.stringify({ archived }),
    },
  );
}
