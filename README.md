# Titan

Personal agentic AI system — modular monolith with Brain, Agents, Memory, Tools, State, and Missions.

## Prerequisites

- **Python 3.10+** (3.14 tested on Windows)
- An [OpenAI API key](https://platform.openai.com/api-keys)

## Setup

From the project root in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configure `.env`

Copy the example file and add your API key:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set `OPENAI_API_KEY`. Optional variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `TITAN_LOG_LEVEL` | `INFO` | Logging verbosity |
| `TITAN_DEBUG_BRAIN` | `false` | Verbose Brain pipeline logging |
| `TITAN_OBSIDIAN_ENABLED` | `false` | Enable Obsidian vault connector |
| `TITAN_OBSIDIAN_VAULT_PATH` | *(empty)* | Absolute path to existing Obsidian vault folder |

See `.env.example` for the full template. Never commit `.env`.

### Obsidian vault (optional)

Titan can read and maintain your **existing** Obsidian vault (recommended name: **Titan AI**). Titan never creates a new vault.

1. Create or open the vault in Obsidian first (e.g. folder `Titan AI` in your Obsidian vault location).
2. In `.env`, set:

```env
TITAN_OBSIDIAN_ENABLED=true
TITAN_OBSIDIAN_VAULT_PATH=C:\Users\YOU\path\to\Titan AI
```

Use the **absolute path** to the vault folder on disk (the folder that contains your `.md` notes). On Windows, a typical OneDrive path looks like:

```env
TITAN_OBSIDIAN_VAULT_PATH=C:\Users\nolan\OneDrive\Documents\Titan AI
```

Replace with your actual vault folder path.

3. Validate configuration:

```powershell
python main.py obsidian-health
```

4. Run an end-to-end smoke test (creates and removes a temporary note under `_titan_smoke_test/`):

```powershell
python main.py obsidian-smoke-test
```

Natural-language examples in the REPL (after validation passes):

- « Analyse la santé de mon vault Obsidian. »
- « Ajoute une note de test dans Obsidian. »
- « Cherche les notes liées à Titan. »
- « Ajoute cette information dans la bonne note Obsidian. »

### Google Calendar (optional, Phase 14.2)

Titan can connect to your **Google Calendar** via local OAuth. Brain and orchestration layers stay provider-independent — only the calendar backend talks to Google APIs.

1. In [Google Cloud Console](https://console.cloud.google.com/), enable the **Google Calendar API** and create OAuth 2.0 credentials (Desktop app). Download the client JSON.

2. In `.env`, set:

```env
TITAN_CALENDAR_PROVIDER=google
TITAN_GOOGLE_CALENDAR_ENABLED=true
TITAN_GOOGLE_CLIENT_SECRET_PATH=data/google_client_secret.json
TITAN_GOOGLE_TOKEN_PATH=data/google_calendar_token.json
```

Place the downloaded client JSON at `data/google_client_secret.json` (or your chosen path).

3. Authenticate locally (opens browser):

```powershell
python main.py calendar-auth
```

4. Validate and smoke-test:

```powershell
python main.py calendar-health
python main.py calendar-list
python main.py calendar-smoke-test
```

See [`docs/CALENDAR.md`](docs/CALENDAR.md) for architecture and permissions. Never commit `data/google_calendar_token.json` or client secrets.

Natural-language examples in the REPL (after validation passes):

- « Quels événements ai-je demain ? »
- « Trouve un créneau libre de 30 minutes vendredi après-midi. »
- « Crée une réunion demain à 14h » (confirmation required before write)

## Run

From the project root (with the virtual environment activated):

```powershell
python main.py
```

Exit the session with `exit`, `quit`, `stop`, or `bye`.

Logs are written to `logs/titan.log`.

### Private web interface (optional, Phase 17.1)

Titan can run a **local-only** web UI on top of the same Core as the REPL. Disabled by default.

1. In `.env`:

```env
TITAN_WEB_ENABLED=true
TITAN_WEB_SECRET_KEY=your-long-random-secret
TITAN_WEB_HOST=127.0.0.1
TITAN_WEB_PORT=8000
```

2. Start the web server:

```powershell
python main.py web
```

3. Open the interface and enter your secret key in the page:
   - `http://127.0.0.1:8000/app/` — the redesigned Titan OS interface (Web App Finalization).
   - `http://127.0.0.1:8000/` — legacy interface (stable fallback).

Do not expose this server to the public internet without following
[`docs/RAILWAY_DEPLOYMENT.md`](docs/RAILWAY_DEPLOYMENT.md). See
[`docs/CLOUD_DEPLOYMENT_READINESS.md`](docs/CLOUD_DEPLOYMENT_READINESS.md) for the
Phase 10.1 audit, [`docs/WEB_APP.md`](docs/WEB_APP.md) for API endpoints, and
[`docs/WEB_APP_LAYOUT.md`](docs/WEB_APP_LAYOUT.md) for the desktop OS layout.

### Cloud deployment (Phase 10.2 — Railway)

Production host is **Railway**. Beginner checklist and troubleshooting:
[`docs/RAILWAY_DEPLOYMENT.md`](docs/RAILWAY_DEPLOYMENT.md).

Production-like local validation:

```powershell
$env:TITAN_WEB_SECRET_KEY="your-long-random-production-secret"
$env:TITAN_COOKIE_SECURE="true"
$env:PORT="8110"
python main.py web-prod
```

Container: `Dockerfile` + `railway.json`.

## Architecture

Official execution path and layer boundaries (Brain → Planner → Reasoning Loop → Tool Orchestrator → Tool Runtime) are documented in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Core cognitive integration validation: [`docs/CORE_SYSTEM_VALIDATION.md`](docs/CORE_SYSTEM_VALIDATION.md). Phase roadmap: [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Run tests

From the project root:

```powershell
python -m pytest tests/ -v
```

## PYTHONPATH

Titan imports assume the **project root** is on `PYTHONPATH`. Running `python main.py` or `python -m pytest tests/ -v` from the repo root satisfies this. If you import modules from another working directory, set:

```powershell
$env:PYTHONPATH = "C:\path\to\Titan"
```

Replace the path with your local clone location.
