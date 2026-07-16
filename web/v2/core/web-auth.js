/** Titan Frontend V2 — Authentication (session cookies + legacy bearer). */

export const AUTH_STORAGE_KEY = "titan_web_secret_key";
export const CSRF_COOKIE_NAME = "titan_csrf";

/**
 * @returns {string}
 */
export function getStoredToken() {
  try {
    return localStorage.getItem(AUTH_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

/**
 * @param {string} token
 */
export function saveStoredToken(token) {
  try {
    const value = (token ?? "").trim();
    if (value) {
      localStorage.setItem(AUTH_STORAGE_KEY, value);
    } else {
      localStorage.removeItem(AUTH_STORAGE_KEY);
    }
  } catch {
    /* ignore storage errors */
  }
}

export function clearStoredToken() {
  saveStoredToken("");
}

/**
 * Read a cookie value by name (used for CSRF double-submit).
 * @param {string} name
 * @returns {string}
 */
export function readCookie(name) {
  try {
    const parts = document.cookie.split(";");
    for (const part of parts) {
      const [rawKey, ...rest] = part.trim().split("=");
      if (rawKey === name) {
        return decodeURIComponent(rest.join("=") || "");
      }
    }
  } catch {
    /* ignore */
  }
  return "";
}

/**
 * @returns {string}
 */
export function getCsrfToken() {
  return readCookie(CSRF_COOKIE_NAME);
}

/**
 * Headers for authenticated API calls.
 * Session mode relies on cookies + CSRF; bearer mode uses Authorization.
 * @returns {Record<string, string>}
 */
export function authHeaders() {
  /** @type {Record<string, string>} */
  const headers = {};
  const csrf = getCsrfToken();
  if (csrf) {
    headers["X-CSRF-Token"] = csrf;
  }
  const key = getStoredToken();
  if (key) {
    headers.Authorization = `Bearer ${key}`;
  }
  return headers;
}

/**
 * Default fetch init for Titan API calls (send cookies in session mode).
 * @param {RequestInit} [init]
 * @returns {RequestInit}
 */
export function authFetchInit(init = {}) {
  const headers = {
    ...(init.headers || {}),
    ...authHeaders(),
  };
  return {
    credentials: "same-origin",
    ...init,
    headers,
  };
}

/**
 * @returns {Promise<{
 *   auth_required: boolean,
 *   auth_mode?: string,
 *   dev_mode: boolean,
 *   secret_configured?: boolean,
 *   session_auth?: boolean,
 *   authenticated?: boolean,
 *   username?: string | null
 * }>}
 */
export async function fetchAuthStatus() {
  const response = await fetch("/auth/status", { credentials: "same-origin" });
  if (!response.ok) {
    throw new Error("Impossible de contacter le serveur Titan.");
  }
  return response.json();
}

/**
 * @param {string} token
 * @returns {Promise<boolean>}
 */
export async function verifyToken(token) {
  const trimmed = (token ?? "").trim();
  if (!trimmed) return false;

  try {
    const response = await fetch("/auth/verify", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Authorization: `Bearer ${trimmed}`,
        ...authHeaders(),
      },
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * @returns {Promise<boolean>}
 */
export async function verifySession() {
  try {
    const response = await fetch("/auth/verify", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        ...authHeaders(),
      },
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Server-side logout — destroys session cookie when session auth is active.
 * @returns {Promise<void>}
 */
export async function logoutSession() {
  try {
    await fetch("/auth/logout", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        ...authHeaders(),
      },
    });
  } catch {
    /* ignore network errors — clear local state anyway */
  }
  clearStoredToken();
}

/**
 * Block boot until the user is authenticated.
 * Session mode: middleware redirects unauthenticated /app to /login.
 * Bearer mode: overlay gate (legacy local/remote).
 * @returns {Promise<void>}
 */
export async function ensureAuthenticated() {
  const status = await fetchAuthStatus();
  if (!status.auth_required) {
    return;
  }

  if (status.auth_mode === "session" || status.session_auth) {
    if (status.authenticated) {
      return;
    }
    if (await verifySession()) {
      return;
    }
    const next = encodeURIComponent(`${window.location.pathname}${window.location.search}`);
    window.location.assign(`/login?next=${next || "%2Fapp%2F"}`);
    // Keep the promise pending while navigation occurs.
    await new Promise(() => {});
    return;
  }

  const stored = getStoredToken();
  if (stored && (await verifyToken(stored))) {
    return;
  }

  if (stored) {
    clearStoredToken();
  }

  await showAuthGate();
}

/**
 * @returns {Promise<void>}
 */
function showAuthGate() {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "tdl-v2-auth-gate";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-labelledby", "tdl-v2-auth-gate-title");
    overlay.innerHTML = `
      <div class="tdl-v2-auth-gate__card">
        <h1 class="tdl-v2-auth-gate__title" id="tdl-v2-auth-gate-title">Accès privé Titan</h1>
        <p class="tdl-v2-auth-gate__subtitle">
          Entre ta clé secrète pour accéder à Titan. Elle reste sur cet appareil uniquement.
        </p>
        <label class="tdl-v2-auth-gate__label" for="tdl-v2-auth-gate-input">Clé secrète</label>
        <input
          class="tdl-v2-auth-gate__input"
          id="tdl-v2-auth-gate-input"
          type="password"
          placeholder="TITAN_WEB_SECRET_KEY"
          autocomplete="off"
          spellcheck="false"
        >
        <p class="tdl-v2-auth-gate__error" id="tdl-v2-auth-gate-error" hidden></p>
        <button type="button" class="tdl-v2-auth-gate__submit" id="tdl-v2-auth-gate-submit">
          Accéder à Titan
        </button>
      </div>
    `;

    document.body.appendChild(overlay);

    const input = /** @type {HTMLInputElement} */ (overlay.querySelector("#tdl-v2-auth-gate-input"));
    const errorEl = /** @type {HTMLElement} */ (overlay.querySelector("#tdl-v2-auth-gate-error"));
    const submitBtn = /** @type {HTMLButtonElement} */ (overlay.querySelector("#tdl-v2-auth-gate-submit"));

    const dismiss = () => {
      overlay.remove();
      resolve();
    };

    const submit = async () => {
      const token = input.value.trim();
      if (!token) {
        errorEl.textContent = "La clé secrète est requise.";
        errorEl.hidden = false;
        input.focus();
        return;
      }

      submitBtn.disabled = true;
      errorEl.hidden = true;

      const ok = await verifyToken(token);
      if (!ok) {
        errorEl.textContent = "Clé secrète incorrecte.";
        errorEl.hidden = false;
        submitBtn.disabled = false;
        input.select();
        return;
      }

      saveStoredToken(token);
      dismiss();
    };

    submitBtn.addEventListener("click", () => {
      submit();
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        submit();
      }
    });

    input.focus();
  });
}

/**
 * Wire secret key save and logout controls inside the settings overlay.
 */
export function wireSettingsAuthControls() {
  const input = /** @type {HTMLInputElement | null} */ (
    document.getElementById("tdl-v2-secret-key")
  );
  const saveBtn = document.getElementById("tdl-v2-save-auth");
  const logoutBtn = document.getElementById("tdl-v2-logout-auth");
  const statusEl = document.getElementById("tdl-v2-auth-status");
  const labelEl = document.querySelector('label[for="tdl-v2-secret-key"]');

  if (!logoutBtn) {
    return;
  }

  let sessionMode = false;

  const syncStatus = async () => {
    try {
      const status = await fetchAuthStatus();
      sessionMode = Boolean(status.auth_mode === "session" || status.session_auth);
      if (sessionMode) {
        if (labelEl) labelEl.textContent = "Session";
        if (input) {
          input.disabled = true;
          input.placeholder = "Authentification par session";
          input.value = status.username ? status.username : "";
          input.type = "text";
        }
        if (saveBtn) saveBtn.hidden = true;
        if (statusEl) {
          statusEl.textContent = status.authenticated
            ? `Connecté${status.username ? ` — ${status.username}` : ""}.`
            : "Non authentifié.";
        }
        return;
      }
    } catch {
      /* fall through to bearer UI */
    }

    const hasToken = Boolean(getStoredToken());
    if (statusEl) {
      statusEl.textContent = hasToken ? "Authentifié sur cet appareil." : "Non authentifié.";
    }
    if (input && !input.value && hasToken) {
      input.value = "••••••••";
    }
  };

  syncStatus();

  if (saveBtn && input) {
    saveBtn.addEventListener("click", async () => {
      if (sessionMode) return;
      const raw = input.value.trim();
      if (!raw || raw === "••••••••") {
        if (statusEl) statusEl.textContent = "Entre une nouvelle clé secrète.";
        input.focus();
        return;
      }

      const ok = await verifyToken(raw);
      if (!ok) {
        if (statusEl) statusEl.textContent = "Clé secrète incorrecte.";
        return;
      }

      saveStoredToken(raw);
      input.value = "••••••••";
      if (statusEl) statusEl.textContent = "Clé enregistrée sur cet appareil.";
    });
  }

  logoutBtn.addEventListener("click", async () => {
    await logoutSession();
    if (input) input.value = "";
    if (statusEl) statusEl.textContent = "Déconnecté.";
    window.location.assign("/login");
  });

  if (input) {
    input.addEventListener("focus", () => {
      if (input.value === "••••••••") {
        input.value = "";
      }
    });
  }
}
