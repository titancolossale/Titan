/** Titan Frontend V2 — Private web authentication (Bearer token, localStorage). */

export const AUTH_STORAGE_KEY = "titan_web_secret_key";

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
 * @returns {Record<string, string>}
 */
export function authHeaders() {
  const key = getStoredToken();
  if (!key) return {};
  return { Authorization: `Bearer ${key}` };
}

/**
 * @returns {Promise<{ auth_required: boolean, dev_mode: boolean, secret_configured?: boolean }>}
 */
export async function fetchAuthStatus() {
  const response = await fetch("/auth/status");
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
      headers: {
        Authorization: `Bearer ${trimmed}`,
      },
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Block boot until the user provides a valid secret (skipped in web-dev mode).
 * @returns {Promise<void>}
 */
export async function ensureAuthenticated() {
  const status = await fetchAuthStatus();
  if (!status.auth_required) {
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

  if (!input || !saveBtn || !logoutBtn) {
    return;
  }

  const syncStatus = () => {
    const hasToken = Boolean(getStoredToken());
    if (statusEl) {
      statusEl.textContent = hasToken ? "Authentifié sur cet appareil." : "Non authentifié.";
    }
    if (!input.value && hasToken) {
      input.value = "••••••••";
    }
  };

  syncStatus();

  saveBtn.addEventListener("click", async () => {
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

  logoutBtn.addEventListener("click", () => {
    clearStoredToken();
    input.value = "";
    if (statusEl) statusEl.textContent = "Clé effacée. Recharge la page pour te réauthentifier.";
    window.location.reload();
  });

  input.addEventListener("focus", () => {
    if (input.value === "••••••••") {
      input.value = "";
    }
  });
}
