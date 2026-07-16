# =====================================
# Titan Web CLI
# =====================================

"""Start the private Titan web server (Phase 17.1 + Phase 10 cloud readiness)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from config.deployment import (
    DeploymentConfigError,
    apply_deployment_env,
    load_deployment_settings,
)
from config.settings import (
    ENV_FILE_PATH,
    TITAN_NAME,
    TITAN_WEB_DEV_SECRET,
    VERSION,
    reload_env,
)

logger = logging.getLogger(__name__)

WEB_DEV_HOST = "127.0.0.1"
WEB_DEV_PORT = 8000
WEB_REMOTE_HOST = "127.0.0.1"
WEB_REMOTE_PORT = 8765


@dataclass(frozen=True)
class WebRuntimeConfig:
    """Resolved web server settings read at startup (after .env reload)."""

    enabled: bool
    host: str
    port: int
    secret_key: str
    dev_mode: bool
    production_mode: bool
    env_file: Path


def _read_web_config(
    *,
    dev_mode: bool = False,
    remote_mode: bool = False,
    production_mode: bool = False,
) -> WebRuntimeConfig:
    """Reload .env and read current web settings from the environment."""
    env_file = reload_env()
    try:
        deployment = load_deployment_settings(
            dev_mode=dev_mode,
            remote_mode=remote_mode,
            production_mode=production_mode,
            validate=production_mode,
        )
    except DeploymentConfigError:
        raise
    except Exception:
        deployment = load_deployment_settings(
            dev_mode=dev_mode,
            remote_mode=remote_mode,
            production_mode=production_mode,
            validate=False,
        )

    if production_mode:
        os.environ["TITAN_APP_ENV"] = "production"
        os.environ["APP_ENV"] = "production"

    secret_key = deployment.session_secret
    if dev_mode and not secret_key:
        secret_key = TITAN_WEB_DEV_SECRET

    return WebRuntimeConfig(
        enabled=deployment.web_enabled,
        host=deployment.host,
        port=deployment.port,
        secret_key=secret_key,
        dev_mode=deployment.dev_mode,
        production_mode=production_mode,
        env_file=env_file,
    )


def _print_web_disabled_help(config: WebRuntimeConfig) -> None:
    """Explain why the web server did not start and what to add to .env."""
    raw_enabled = os.getenv("TITAN_WEB_ENABLED", "(non défini)")
    print("Interface web désactivée.")
    print(f"Valeur détectée : TITAN_WEB_ENABLED={raw_enabled}")
    print(f"Fichier .env chargé : {config.env_file.resolve()}")
    print("Ajoute ces lignes à ton .env :")
    print("TITAN_WEB_ENABLED=true")
    print("TITAN_WEB_SECRET_KEY=ta-cle-secrete-longue-et-aleatoire")
    print()
    print("Ou démarre en mode développement local (sans modifier .env) :")
    print("python main.py web-dev")


def _apply_runtime_env(config: WebRuntimeConfig) -> None:
    """Publish resolved settings to os.environ before uvicorn imports the API."""
    if config.production_mode:
        os.environ["TITAN_APP_ENV"] = "production"
        os.environ["APP_ENV"] = "production"
    os.environ["TITAN_WEB_ENABLED"] = "true" if config.enabled else "false"
    os.environ["TITAN_WEB_HOST"] = config.host
    os.environ["TITAN_WEB_PORT"] = str(config.port)
    os.environ["PORT"] = str(config.port)
    os.environ["TITAN_WEB_SECRET_KEY"] = config.secret_key
    os.environ["TITAN_WEB_DEV_MODE"] = "true" if config.dev_mode else "false"

    deployment = load_deployment_settings(validate=False)
    apply_deployment_env(deployment)


def _print_remote_tunnel_help(port: int) -> None:
    """Show Cloudflare Tunnel command for private HTTPS access."""
    local_url = f"http://127.0.0.1:{port}"
    print()
    print("Accès distant privé (Cloudflare Tunnel) :")
    print(f"  cloudflared tunnel --url {local_url}")
    print()
    print(
        "Installe cloudflared si nécessaire : "
        "https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    )
    print(
        "Le tunnel affiche une URL HTTPS temporaire — ouvre-la sur ton téléphone "
        "ou un autre appareil."
    )
    print(
        "Entre TITAN_WEB_SECRET_KEY dans l'écran d'authentification Titan "
        "(une fois par appareil)."
    )
    print()


def run_web_server(
    *,
    dev_mode: bool = False,
    remote_mode: bool = False,
    production_mode: bool = False,
) -> int:
    """Start uvicorn with the FastAPI app."""
    try:
        config = _read_web_config(
            dev_mode=dev_mode,
            remote_mode=remote_mode,
            production_mode=production_mode,
        )
    except DeploymentConfigError as exc:
        print(f"Configuration de déploiement invalide : {exc}")
        return 1

    if not config.enabled:
        _print_web_disabled_help(config)
        return 1

    if not config.secret_key:
        print("TITAN_WEB_SECRET_KEY est vide.")
        print(f"Fichier .env chargé : {config.env_file.resolve()}")
        print("Ajoute cette ligne à ton .env :")
        print("TITAN_WEB_SECRET_KEY=ta-cle-secrete-longue-et-aleatoire")
        print()
        print("Ou démarre en mode développement local :")
        print("python main.py web-dev")
        return 1

    try:
        import uvicorn
    except ImportError:
        print("uvicorn n'est pas installé. Exécute : pip install -r requirements.txt")
        return 1

    _apply_runtime_env(config)

    scheme = "http"
    if production_mode and os.getenv("TITAN_PUBLIC_BASE_URL", "").startswith("https://"):
        scheme = "https"
    url = f"{scheme}://{config.host}:{config.port}"
    if config.host == "0.0.0.0":
        url = f"{scheme}://127.0.0.1:{config.port}"

    if config.dev_mode:
        print("Mode développement local — écoute sur 127.0.0.1 uniquement.")
        if config.secret_key == TITAN_WEB_DEV_SECRET:
            print(f"Clé de développement temporaire : {TITAN_WEB_DEV_SECRET}")
            print("Les routes protégées sont accessibles sans Bearer token en mode web-dev.")

    if remote_mode:
        print("Mode accès distant — écoute locale pour Cloudflare Tunnel.")
        print("Authentification obligatoire sur toutes les routes protégées.")
        _print_remote_tunnel_help(config.port)

    if production_mode:
        print("Mode production — reload désactivé, authentification requise.")
        print(f"Écoute sur {config.host}:{config.port}")

    # Canonical UI entry is /app/ (web/v2). Root "/" only redirects there.
    app_url = f"{url.rstrip('/')}/app/"
    print("======================================")
    print(f"{TITAN_NAME} AI v{VERSION} — Interface web privée")
    print(f"Titan Web App running at {app_url}")
    if production_mode:
        print("Mode production — prêt pour conteneur ou hébergeur cloud.")
    elif remote_mode:
        print("Prêt pour tunnel Cloudflare — voir la commande ci-dessus.")
    elif not config.dev_mode:
        print("Accès local — configure TITAN_APP_ENV=production pour le cloud.")
    print("======================================")

    logger.info(
        "Starting Titan web server on %s:%s (dev_mode=%s production=%s)",
        config.host,
        config.port,
        config.dev_mode,
        production_mode,
    )

    uvicorn.run(
        "api.app:app",
        host=config.host,
        port=config.port,
        log_level=os.getenv("TITAN_LOG_LEVEL", "info").lower(),
        reload=False,
    )
    return 0


def dispatch_web_command(command: str) -> int | None:
    """Handle web CLI subcommands."""
    normalized = command.strip().lower()
    if normalized == "web":
        raise SystemExit(run_web_server(dev_mode=False))
    if normalized == "web-dev":
        raise SystemExit(run_web_server(dev_mode=True))
    if normalized == "web-remote":
        raise SystemExit(run_web_server(remote_mode=True))
    if normalized == "web-prod":
        raise SystemExit(run_web_server(production_mode=True))
    return None
