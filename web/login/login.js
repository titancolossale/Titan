/** Titan private login — session authentication (no secrets in client code). */

(function () {
  const form = document.getElementById("titan-login-form");
  const usernameInput = document.getElementById("titan-username");
  const passwordInput = document.getElementById("titan-password");
  const toggleBtn = document.getElementById("titan-password-toggle");
  const errorEl = document.getElementById("titan-login-error");
  const submitBtn = document.getElementById("titan-login-submit");

  if (!form || !usernameInput || !passwordInput || !submitBtn || !errorEl) {
    return;
  }

  function nextTarget() {
    try {
      const params = new URLSearchParams(window.location.search);
      const raw = params.get("next") || "/app/";
      if (!raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\")) {
        return "/app/";
      }
      return raw;
    } catch {
      return "/app/";
    }
  }

  function showError(message) {
    errorEl.textContent = message;
    errorEl.hidden = false;
  }

  function clearError() {
    errorEl.textContent = "";
    errorEl.hidden = true;
  }

  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      const visible = passwordInput.type === "text";
      passwordInput.type = visible ? "password" : "text";
      toggleBtn.setAttribute("aria-pressed", visible ? "false" : "true");
      toggleBtn.setAttribute(
        "aria-label",
        visible ? "Afficher le mot de passe" : "Masquer le mot de passe",
      );
      toggleBtn.textContent = visible ? "Voir" : "Masquer";
      passwordInput.focus();
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();

    const username = usernameInput.value.trim();
    const password = passwordInput.value;

    if (!username || !password) {
      showError("Identifiant et mot de passe requis.");
      return;
    }

    submitBtn.disabled = true;
    const previousLabel = submitBtn.textContent;
    submitBtn.textContent = "CONNEXION…";

    try {
      const response = await fetch("/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          username,
          password,
          next: nextTarget(),
        }),
      });

      let payload = {};
      try {
        payload = await response.json();
      } catch {
        payload = {};
      }

      if (!response.ok) {
        const detail =
          typeof payload.detail === "string"
            ? payload.detail
            : "Identifiants invalides.";
        showError(detail);
        passwordInput.select();
        return;
      }

      const destination =
        typeof payload.next === "string" && payload.next.startsWith("/")
          ? payload.next
          : nextTarget();
      window.location.assign(destination);
    } catch {
      showError("Impossible de contacter Titan. Réessaie.");
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = previousLabel;
    }
  });

  usernameInput.focus();
})();
