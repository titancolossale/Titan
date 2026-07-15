# =====================================
# Titan Gmail OAuth
# =====================================

"""Local OAuth setup flow for Gmail (Phase 15.2)."""

from __future__ import annotations

import json
from pathlib import Path

GMAIL_SCOPES = ("https://www.googleapis.com/auth/gmail.modify",)


def resolve_gmail_client_secret_path(path: Path | None = None) -> Path:
    """Return the configured Gmail OAuth client secret JSON path."""
    if path is not None:
        return path.expanduser()
    from config.settings import TITAN_GMAIL_CLIENT_SECRET_PATH

    return TITAN_GMAIL_CLIENT_SECRET_PATH


def resolve_gmail_token_path(path: Path | None = None) -> Path:
    """Return the configured Gmail OAuth token storage path."""
    if path is not None:
        return path.expanduser()
    from config.settings import TITAN_GMAIL_TOKEN_PATH

    return TITAN_GMAIL_TOKEN_PATH


def load_gmail_credentials(
    *,
    client_secret_path: Path | None = None,
    token_path: Path | None = None,
    scopes: tuple[str, ...] = GMAIL_SCOPES,
):
    """Load stored Gmail credentials or return None when auth is required."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    secret_path = resolve_gmail_client_secret_path(client_secret_path)
    token_file = resolve_gmail_token_path(token_path)
    if not token_file.exists():
        return None

    creds = Credentials.from_authorized_user_file(str(token_file), list(scopes))
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_gmail_credentials(creds, token_path=token_file)
        return creds
    return None


def save_gmail_credentials(
    credentials,
    *,
    token_path: Path | None = None,
) -> Path:
    """Persist Gmail OAuth credentials to the configured token path."""
    token_file = resolve_gmail_token_path(token_path)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(credentials.to_json(), encoding="utf-8")
    return token_file


def validate_gmail_client_secret_file(
    client_secret_path: Path | None = None,
) -> tuple[bool, str]:
    """Verify the Gmail OAuth client secret file exists and has expected shape."""
    secret_path = resolve_gmail_client_secret_path(client_secret_path)
    if not secret_path.exists():
        return (
            False,
            f"Fichier client OAuth Gmail introuvable : {secret_path}. "
            "Téléchargez les identifiants OAuth 2.0 (application de bureau) depuis "
            "Google Cloud Console et définissez TITAN_GMAIL_CLIENT_SECRET_PATH.",
        )
    try:
        payload = json.loads(secret_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"Fichier client OAuth Gmail illisible : {exc}"

    if "installed" not in payload and "web" not in payload:
        return (
            False,
            "Format OAuth invalide — le JSON doit contenir une section "
            "'installed' (application de bureau) ou 'web'.",
        )
    return True, f"Client OAuth Gmail valide : {secret_path}"


def run_gmail_oauth_setup(
    *,
    client_secret_path: Path | None = None,
    token_path: Path | None = None,
    scopes: tuple[str, ...] = GMAIL_SCOPES,
) -> tuple[bool, str]:
    """Guide the user through local Gmail OAuth and save the token."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    secret_path = resolve_gmail_client_secret_path(client_secret_path)
    token_file = resolve_gmail_token_path(token_path)

    ok, message = validate_gmail_client_secret_file(secret_path)
    if not ok:
        return False, message

    existing = load_gmail_credentials(
        client_secret_path=secret_path,
        token_path=token_file,
        scopes=scopes,
    )
    if existing is not None and existing.valid:
        return True, (
            f"Token Gmail déjà valide : {token_file}. "
            "Supprimez ce fichier pour ré-authentifier."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(secret_path),
        scopes=list(scopes),
    )
    print("")
    print("=== Authentification Gmail ===")
    print("")
    print("1. Un navigateur va s'ouvrir pour autoriser Titan.")
    print("2. Connecte-toi avec le compte Gmail à utiliser.")
    print("3. Accepte l'accès Gmail (lecture, composition, envoi, modification).")
    print("4. Reviens ici une fois l'autorisation terminée.")
    print("")

    credentials = flow.run_local_server(port=0, open_browser=True)
    saved_path = save_gmail_credentials(credentials, token_path=token_file)
    return True, f"Authentification réussie. Token enregistré : {saved_path}"


def format_gmail_oauth_setup_guide() -> str:
    """Return French setup instructions for Gmail OAuth."""
    from config.settings import (
        TITAN_GMAIL_CLIENT_SECRET_PATH,
        TITAN_GMAIL_TOKEN_PATH,
    )

    return "\n".join(
        [
            "=== Configuration Gmail (OAuth) ===",
            "",
            "1. Google Cloud Console → APIs & Services → Credentials",
            "2. Crée un identifiant OAuth 2.0 (type « Application de bureau »)",
            "3. Active l'API Gmail pour le projet",
            "4. Télécharge le JSON client et place-le sur disque, par ex. :",
            f"   {TITAN_GMAIL_CLIENT_SECRET_PATH}",
            "5. Dans .env :",
            "   TITAN_EMAIL_ENABLED=true",
            "   TITAN_EMAIL_PROVIDER=gmail",
            "   TITAN_GMAIL_ENABLED=true",
            f"   TITAN_GMAIL_CLIENT_SECRET_PATH={TITAN_GMAIL_CLIENT_SECRET_PATH}",
            f"   TITAN_GMAIL_TOKEN_PATH={TITAN_GMAIL_TOKEN_PATH}",
            "6. Lance : python main.py email-auth",
            "",
            "Le token est stocké localement dans data/ — ne le commite pas.",
        ],
    )
