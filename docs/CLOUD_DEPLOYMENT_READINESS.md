# Titan Cloud Deployment Readiness (Phase 10.1)

**Status:** Audit complete. **Provider selected in Phase 10.2: Railway.**  
**Version audited:** 0.43.0  
**Date:** July 15, 2026

This document records what is required to deploy Titan's private Web App to a Linux
cloud host. For the step-by-step Railway guide, use
[`docs/RAILWAY_DEPLOYMENT.md`](RAILWAY_DEPLOYMENT.md).

---

## 1. Canonical application entrypoint

| Item | Value |
|------|--------|
| ASGI module | `api.app:app` |
| Factory | `create_app()` in `api/app.py` |
| CLI launcher | `core/web_cli.py` → `run_web_server()` |
| Root dispatcher | `main.py` → `dispatch_web_command()` |

### Production start command

```bash
python main.py web-prod
```

Equivalent direct uvicorn (after env is set):

```bash
uvicorn api.app:app --host 0.0.0.0 --port ${PORT:-8000} --log-level info
```

### Local development command (unchanged)

```bash
python main.py web-dev
```

Opens `http://127.0.0.1:8000/app/` with auth bypass and ephemeral dev secret.

### Local authenticated command (localhost)

```bash
python main.py web
```

Requires `TITAN_WEB_ENABLED=true` and `TITAN_WEB_SECRET_KEY` in `.env`.

### Cloudflare Tunnel command (unchanged)

```bash
python main.py web-remote
```

---

## 2. Routes and runtime behavior

| Route | Purpose | Auth |
|-------|---------|------|
| `GET /health` | Liveness — process alive | Public |
| `GET /ready` | Readiness — core subsystems | Public |
| `GET /app/` | Production frontend (`web/v2/`) | Public (static) |
| `GET /v2/` | Same sources as `/app` | Public (static) |
| `GET /static/` | Legacy V1 assets | Public |
| `POST /api/chat/message` | Canonical chat | Bearer |
| `POST /chat/stream` | SSE cognitive stream | Bearer |
| `GET /events/stream` | Persistent SSE hub | Token query or Bearer |

**WebSockets:** not implemented (SSE only).  
**Background workers:** none started with the web server (`JobRunner` exists but is not ticked).  
**Browser auto-open:** not used by web CLI (OAuth CLIs use browser locally only).

---

## 3. Environment configuration

Central module: `config/deployment.py` (`DeploymentSettings`, `load_deployment_settings()`).  
Path helpers: `config/paths.py`.

### Required for production (`TITAN_APP_ENV=production`)

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | LLM (existing) |
| `TITAN_WEB_SECRET_KEY` | Bearer auth (≥16 chars) |
| `TITAN_COOKIE_SECURE=true` | Secure cookie policy |
| `TITAN_WEB_HOST=0.0.0.0` | Default in `web-prod` |
| `PORT` or `TITAN_WEB_PORT` | Provider port |

### Recommended for public deployment (next steps)

| Variable | Purpose |
|----------|---------|
| `TITAN_PUBLIC_BASE_URL` | e.g. `https://titan.example.com` |
| `TITAN_ALLOWED_HOSTS` | Comma-separated hostnames |
| `TITAN_CORS_ALLOWED_ORIGINS` | Frontend origin if split |
| `TITAN_DATA_DIR` | Persistent volume mount path |

### Optional

| Variable | Default | Notes |
|----------|---------|-------|
| `TITAN_APP_ENV` | `development` | `production` for cloud |
| `TITAN_DATA_DIR` | `data` | Must persist in cloud |
| `TITAN_MEMORY_DIR` | same as data | Long-term memory JSON |
| `TITAN_LOG_DIR` | `logs` | Application logs |
| `TITAN_OBSIDIAN_VAULT_PATH` | empty | Local vault only |
| `TITAN_BROWSER_ENABLED` | `false` | Playwright heavy in cloud |
| `TITAN_VOICE_ENABLED` | `true` | Browser STT/TTS client-side |
| `TITAN_TRADING_ENABLED` | `true` | Mock/paper default |
| `TITAN_DATABASE_URL` | empty | Not used yet (JSON persistence) |

Alias names accepted: `APP_ENV`, `HOST`, `SESSION_SECRET`, `PUBLIC_BASE_URL`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `AUTH_REQUIRED`, `COOKIE_SECURE`, `DATABASE_URL`, `OBSIDIAN_VAULT_PATH`, `BROWSER_TOOL_ENABLED`, `VOICE_RUNTIME_ENABLED`, `TRADING_RUNTIME_ENABLED`.

See `.env.example` for the full template.

---

## 4. Persistent data requirements

| Path | Persists? | Sensitive? | Cloud strategy |
|------|-----------|------------|----------------|
| `data/long_term_memory.json` | **Yes** | **Yes** | Volume mount |
| `data/titan_state.json` | **Yes** | Yes | Volume mount |
| `data/titan_mission.json` | **Yes** | Moderate | Volume mount |
| `data/learning_memory.json` | Yes | Moderate | Volume mount |
| `data/knowledge_learning.json` | Yes | Moderate | Volume mount |
| `data/development_sessions.json` | Yes | Moderate | Volume mount |
| `data/voice_sessions.json` | Yes | Moderate | Volume mount |
| `data/scheduled_jobs.json` | Yes | Low | Volume mount |
| `data/tool_runs.json` | Optional | Low | Volume if persist enabled |
| `data/google_*_token.json` | Yes | **Secrets** | Volume + never commit |
| `logs/titan.log` | Optional | May contain PII | Ephemeral or rotated |
| `logs/tools_audit.jsonl` | Optional | Moderate | Volume if audit enabled |
| Python runtime temp workspace | No | Low | Ephemeral |
| Playwright browser cache | No | Low | Ephemeral / optional |

Configure with `TITAN_DATA_DIR=/var/lib/titan/data` (or provider volume path).

---

## 5. Obsidian cloud limitation

Obsidian integration reads Nolan's **local filesystem vault** via `TITAN_OBSIDIAN_VAULT_PATH`. It does **not** use Obsidian Sync API or a plugin API.

**A cloud server cannot access Nolan's PC filesystem** unless the vault is separately mounted (e.g. Synology/NFS, rclone, dedicated sync sidecar).

Current behavior:

- Path is configurable and cross-platform (`pathlib`).
- `/obsidian/status` and `/ready` report `disabled` or `unavailable` honestly when the vault is missing.
- Local Obsidian access is unchanged.

**Later deployment options (Step 10.2+):**

1. Disable Obsidian on cloud (`TITAN_OBSIDIAN_ENABLED=false`) — recommended initially.
2. Mount a synced vault directory into the container volume.
3. Replace with a remote note API (future architecture — not in scope).

---

## 6. Windows / localhost dependency audit

| Finding | Location | Classification |
|---------|----------|----------------|
| `127.0.0.1:8000` default bind | `config/settings.py`, docs | Development-only / configurable |
| `web-dev` forces localhost | `core/web_cli.py` | Development-only (safe) |
| Auth bypass in dev mode | `api/auth.py` | Development-only |
| Dev secret `titan-local-dev-only` | `config/settings.py` | Development-only — blocked in production |
| Windows vault path in README examples | `README.md` | Documentation — use env var |
| `C:\Users\...` in user `.env` | local only | Must become configurable (done via env) |
| OAuth `open_browser=True` | `google_oauth.py`, `gmail_oauth.py` | Local CLI only — not web server |
| Screenshot scripts bind localhost | `scripts/capture_*.py` | Development-only |
| Frontend uses relative API URLs | `web/v2/core/*.js` | **Safe for production** |
| Playwright dependency | `requirements.txt` | External — optional in cloud |
| Personal data tracked in Git | `data/long_term_memory.json`, etc. | **Security risk** — manual review required |
| No CORS by default | `api/app.py` | Safe locally — must configure for public |
| No TrustedHost by default | `api/app.py` | Must configure `TITAN_ALLOWED_HOSTS` |
| Bearer shared secret only | `api/auth.py` | Blocker for multi-user public launch |
| SSE auth via query token | `/events/stream` | Required before login launch — token in URL |
| No rate limiting | API layer | Recommended hardening |
| OpenAPI `/docs` when web enabled | `api/app.py` | Disable or protect in production |

---

## 7. Security checklist

### Blockers before public deployment

- [ ] Deploy behind HTTPS (reverse proxy or provider TLS)
- [ ] Set strong `TITAN_WEB_SECRET_KEY` (≥16 chars, not dev default)
- [ ] Set `TITAN_ALLOWED_HOSTS` and `TITAN_CORS_ALLOWED_ORIGINS`
- [ ] Remove or protect `/docs` in production
- [ ] Untrack personal data from Git (`data/long_term_memory.json`, etc.)
- [ ] Confirm `.env` never committed

### Required before multi-device login launch

- [ ] Session model beyond shared Bearer secret (Phase 10.2+)
- [ ] SSE authentication without long-lived token in query string
- [ ] CSRF strategy if cookies added
- [ ] Rate limiting on `/api/chat/message` and auth routes

### Recommended hardening

- [ ] Disable `TITAN_BROWSER_ENABLED` on cloud unless Playwright installed
- [ ] Restrict terminal/python tool execution in cloud profile
- [ ] Structured logging without secret leakage
- [ ] Volume encryption at rest

### Later improvements

- [ ] Proper user accounts (Nolan / Ibrahim isolation at web layer)
- [ ] Database migration from JSON
- [ ] WAF / DDoS protection at edge

---

## 8. Health and readiness

### `GET /health`

Returns 200 quickly:

```json
{
  "status": "ok",
  "name": "Titan",
  "version": "0.43.0",
  "web_enabled": true,
  "dev_mode": false,
  "auth_required": true
}
```

No secrets exposed.

### `GET /ready`

Returns 200 when core is ready; 503 when not:

```json
{
  "status": "ready",
  "checks": {
    "web_enabled": {"ok": true, "required": true},
    "data_directory": {"ok": true, "required": true, "message": "ok"},
    "auth_configured": {"ok": true, "required": true}
  },
  "optional_subsystems": [
    {"name": "obsidian", "status": "disabled", "required": false, ...}
  ]
}
```

Optional tools (Obsidian, Browser, Voice, Trading) do **not** fail readiness when unavailable.

---

## 9. Dependencies

| Item | Detail |
|------|--------|
| Python | **3.10+** (3.12 in Dockerfile; 3.14 tested locally on Windows) |
| Install | `pip install -r requirements.txt` |
| Node.js | **Not required at runtime** — frontend is prebuilt static JS in `web/v2/` |
| System packages | Playwright needs Chromium if `TITAN_BROWSER_ENABLED=true` |
| Lock file | None — `requirements.txt` only |
| `pyproject.toml` | Pytest config only |

---

## 10. Container instructions

```bash
docker build -t titan-web .
docker run --rm -p 8000:8000 \
  -e OPENAI_API_KEY=your_key \
  -e TITAN_WEB_SECRET_KEY=your-long-random-production-secret \
  -v titan-data:/app/data \
  titan-web
```

Image runs as non-root user `titan`, CMD `python main.py web-prod`, healthcheck on `/health`.

---

## 11. Local production-mode validation

```powershell
$env:TITAN_APP_ENV="production"
$env:TITAN_WEB_ENABLED="true"
$env:TITAN_WEB_SECRET_KEY="local-production-test-secret-32"
$env:TITAN_COOKIE_SECURE="true"
$env:PORT="8110"
python main.py web-prod
```

Verify:

- `http://127.0.0.1:8110/health` → 200
- `http://127.0.0.1:8110/ready` → 200
- `http://127.0.0.1:8110/app/` → 200 HTML
- No browser opens; no reload process

---

## 12. Remaining items after Railway packaging (Step 10.3+)

1. ~~Provider selection and TLS termination~~ — **Railway** (Phase 10.2)
2. Persistent volume provisioning on Railway (optional but recommended)
3. Multi-user authentication (beyond shared secret)
4. Obsidian strategy for cloud (disable initially — documented)
5. Git cleanup of tracked personal JSON in `data/`
6. Production secret rotation procedure
7. Playwright/browser tooling decision for cloud

---

## 13. Recommended next step

**Follow [`docs/RAILWAY_DEPLOYMENT.md`](RAILWAY_DEPLOYMENT.md)** — create a Railway
project from GitHub, set production env vars, generate the public HTTPS domain,
and validate `/health`, `/ready`, and `/app/`. Step 10.3 covers further auth/domain
hardening after the first successful deploy.
