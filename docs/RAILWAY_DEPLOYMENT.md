# Titan — Railway Production Deployment (Phase 10.2)

**Provider:** Railway (fixed)  
**Status:** Repository is Railway-ready — Nolan deploys from the dashboard  
**Does not require:** AWS, Azure, GCP, DigitalOcean, Fly.io, Render, VPS, or Heroku  
**This guide assumes:** you have never deployed an app before

Titan already includes a production Docker image (`Dockerfile`) that runs:

```text
python main.py web-prod
```

Railway builds that image, injects `PORT`, terminates HTTPS, and gives you a public URL.

**Do not put API keys or secrets in this document or in Git.** Set them only in the Railway Variables UI.

---

## 1. What you will have when finished

| Item | Result |
|------|--------|
| Public HTTPS URL | e.g. `https://titan-production-xxxx.up.railway.app` |
| Web App | `https://<your-url>/app/` |
| Liveness | `https://<your-url>/health` → HTTP 200 |
| Readiness | `https://<your-url>/ready` → HTTP 200 |
| Auth | Same Bearer secret as local (`TITAN_WEB_SECRET_KEY`) |

Estimated time for a first deploy: **15–30 minutes** (mostly account + env vars).

---

## 2. Railway readiness audit (repo)

| Check | Status |
|-------|--------|
| `Dockerfile` with `CMD ["python", "main.py", "web-prod"]` | Ready |
| Binds `0.0.0.0` in production | Ready (`TITAN_WEB_HOST` / `web-prod`) |
| Reads provider `PORT` | Ready (`config/deployment.py`) |
| `GET /health` (public) | Ready |
| `GET /ready` (public) | Ready |
| Static frontend at `/app` | Ready (`web/v2/`) |
| `.dockerignore` excludes `.env` and secrets | Ready |
| `railway.json` (Docker builder + `/health`) | Ready (Phase 10.2) |
| Procfile | **Not required** (Dockerfile CMD is enough) |

No application redesign was required for this step.

---

## 3. Production runtime (verified)

| Item | Value |
|------|--------|
| Start command | `python main.py web-prod` (Dockerfile `CMD`) |
| ASGI app | `api.app:app` |
| Listen address | `0.0.0.0` |
| Port | Railway injects `PORT` — Titan reads it automatically |
| Healthcheck | `GET /health` → 200 (configured in `railway.json`) |
| Readiness | `GET /ready` → 200 when core is ready |
| HTTPS | Provided by Railway (you do not install certificates) |

---

## 4. Environment variables (complete checklist)

Set these in **Railway → your service → Variables**.  
Use either the `TITAN_*` name or the shorter alias — both work.

### 4.1 Required (service will not start safely without these)

| Variable | Example / notes | Secret? |
|----------|-----------------|---------|
| `OPENAI_API_KEY` | Your OpenAI key (same as local `.env`) | **Yes** |
| `TITAN_WEB_SECRET_KEY` | Long random string ≥16 chars (or alias `SESSION_SECRET`) | **Yes** |
| `TITAN_APP_ENV` | `production` (alias `APP_ENV`) | No |
| `TITAN_WEB_ENABLED` | `true` | No |
| `TITAN_COOKIE_SECURE` | `true` (alias `COOKIE_SECURE`) | No |
| `TITAN_WEB_HOST` | `0.0.0.0` (alias `HOST`) — Dockerfile already sets this | No |

`PORT` is injected by Railway. **Do not hardcode a fixed PORT** unless Railway support asks you to.

### 4.2 Strongly recommended after first public URL exists

| Variable | How to set on Railway | Notes |
|----------|----------------------|-------|
| `TITAN_PUBLIC_BASE_URL` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | Alias `PUBLIC_BASE_URL` |
| `TITAN_ALLOWED_HOSTS` | `${{RAILWAY_PUBLIC_DOMAIN}},healthcheck.railway.app` | Alias `ALLOWED_HOSTS` — **must** include `healthcheck.railway.app` when hosts are restricted |
| `TITAN_CORS_ALLOWED_ORIGINS` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | Alias `CORS_ALLOWED_ORIGINS` |

`${{RAILWAY_PUBLIC_DOMAIN}}` is Railway template syntax. Railway expands it to your real hostname (for example `titan-production-xxxx.up.railway.app`).

**First deploy tip:** you may leave `TITAN_ALLOWED_HOSTS` empty until the service is healthy. Then add the hosts above and redeploy. Empty hosts means TrustedHost middleware is off (acceptable for private personal use while you finish setup).

### 4.3 Optional but useful

| Variable | Recommended Railway value | Notes |
|----------|---------------------------|-------|
| `TITAN_AUTH_REQUIRED` | `true` (alias `AUTH_REQUIRED`) | Default is auth on when secret is set |
| `TITAN_LOG_LEVEL` | `INFO` (alias `LOG_LEVEL`) | Use `DEBUG` only while troubleshooting |
| `TITAN_DATA_DIR` | `/app/data` or volume mount path | Persist JSON state |
| `TITAN_MEMORY_DIR` | same as data (or leave empty) | Long-term memory JSON |
| `TITAN_OBSIDIAN_ENABLED` | `false` | Cloud cannot see your PC vault |
| `TITAN_BROWSER_ENABLED` | `false` | Playwright is heavy; keep off initially |
| `TITAN_VOICE_ENABLED` | `true` | Browser STT/TTS (client-side) |
| `TITAN_TRADING_ENABLED` | `true` | Mock/paper defaults — no live broker setup in this step |
| `TITAN_DATABASE_URL` | leave empty | Not used yet (JSON persistence) |

### 4.4 Generate a strong secret (Windows PowerShell)

Run locally (do **not** commit the result):

```powershell
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 48 | ForEach-Object { [char]$_ })
```

Paste the output into Railway as `TITAN_WEB_SECRET_KEY`.

### 4.5 Copy-paste starter set (no secret values)

Paste into Railway Variables (then fill the two secrets yourself):

```text
TITAN_APP_ENV=production
TITAN_WEB_ENABLED=true
TITAN_WEB_HOST=0.0.0.0
TITAN_COOKIE_SECURE=true
TITAN_AUTH_REQUIRED=true
TITAN_LOG_LEVEL=INFO
TITAN_OBSIDIAN_ENABLED=false
TITAN_BROWSER_ENABLED=false
TITAN_VOICE_ENABLED=true
TITAN_TRADING_ENABLED=true
TITAN_PUBLIC_BASE_URL=https://${{RAILWAY_PUBLIC_DOMAIN}}
TITAN_ALLOWED_HOSTS=${{RAILWAY_PUBLIC_DOMAIN}},healthcheck.railway.app
TITAN_CORS_ALLOWED_ORIGINS=https://${{RAILWAY_PUBLIC_DOMAIN}}
```

Then add separately (from your machine / password manager):

- `OPENAI_API_KEY=...`
- `TITAN_WEB_SECRET_KEY=...`

---

## 5. Beginner deployment guide (Nolan)

Follow these steps in order. Do not skip.

### Step A — Push Titan to GitHub

1. Create a GitHub account if you do not have one: https://github.com/signup  
2. Create a **private** repository (recommended) named e.g. `Titan`.  
3. From your Titan folder on Windows, push the code (if not already connected):

```powershell
cd C:\Users\nolan\OneDrive\Desktop\Titan
git status
git remote -v
```

If there is no remote yet, create the repo on GitHub and follow GitHub’s “push an existing repository” instructions.  
**Never commit** `.env`, API keys, or Google OAuth token files.

### Step B — Create a Railway account

1. Open https://railway.com  
2. Click **Login** / **Start a New Project**  
3. Prefer **Login with GitHub** (simplest)  
4. Accept the free trial / Hobby onboarding prompts Railway shows you  
5. You do **not** need enterprise features for Titan

### Step C — Create a project from GitHub

1. In Railway: **New Project**  
2. Choose **Deploy from GitHub repo**  
3. Authorize Railway to access your GitHub if asked  
4. Select the **Titan** repository  
5. Railway should detect the **Dockerfile** automatically  
6. Confirm the service is created (you may see a first build start)

If Railway asks for a root directory, leave it as the repository root (where `Dockerfile` and `railway.json` live).

### Step D — Configure environment variables

1. Open your service  
2. Go to the **Variables** tab  
3. Add every variable from §4.1 and the starter set in §4.5  
4. Save / apply variables (Railway will often redeploy automatically)

### Step E — Enable public networking (HTTPS URL)

1. Open the service **Settings** (or **Networking**)  
2. Find **Public Networking** / **Generate Domain**  
3. Click **Generate Domain**  
4. Copy the URL (looks like `https://….up.railway.app`)

That HTTPS URL is your public Titan address. Railway handles TLS for you.

### Step F — Wait for a successful deploy

1. Open the **Deployments** tab  
2. Wait until the latest deployment is **Success** / **Active**  
3. If it fails, open **View Logs** and jump to §7 Troubleshooting

### Step G — Validate endpoints

In a browser (or PowerShell), replace `YOUR_URL` with your Railway domain:

```text
https://YOUR_URL/health
https://YOUR_URL/ready
https://YOUR_URL/app/
```

Expected:

| URL | Expected |
|-----|----------|
| `/health` | JSON with `"status": "ok"` |
| `/ready` | JSON with `"status": "ready"` (HTTP 200) |
| `/app/` | Titan Web App HTML loads |

PowerShell example:

```powershell
Invoke-WebRequest -Uri "https://YOUR_URL/health" -UseBasicParsing | Select-Object StatusCode, Content
Invoke-WebRequest -Uri "https://YOUR_URL/ready" -UseBasicParsing | Select-Object StatusCode, Content
Invoke-WebRequest -Uri "https://YOUR_URL/app/" -UseBasicParsing | Select-Object StatusCode
```

### Step H — Sign in to the Web App

1. Open `https://YOUR_URL/app/`  
2. Enter the same value as `TITAN_WEB_SECRET_KEY` when Titan asks for authentication  
3. Send a short test message (requires a valid `OPENAI_API_KEY`)

### Step I — Read logs

1. Railway → your service → **Deployments** → latest → **Logs**  
2. Look for lines mentioning uvicorn / `Mode production` / listening on `0.0.0.0`  
3. Errors about missing secrets usually appear immediately at startup

### Step J — Restart

1. Railway → service → **Deployments** (or the service ⋮ menu)  
2. Choose **Restart** (or trigger a redeploy)  
3. Wait for `/health` to return 200 again

### Step K — Update Titan later

1. Commit and push to the GitHub branch Railway watches (usually `main`)  
2. Railway rebuilds and redeploys automatically  
3. Re-check `/health`, `/ready`, `/app/`

### Step L — Persistent data (optional, recommended)

Without a volume, JSON under `/app/data` can be **lost on redeploy**.

When your Railway plan allows volumes:

1. Service → **Settings** → **Volumes** (or add volume from the canvas)  
2. Mount path: `/app/data`  
3. Set `TITAN_DATA_DIR=/app/data`  
4. Redeploy  

This step is **optional** for a first smoke test. It is **recommended** before you rely on cloud memory/missions.

---

## 6. Final deployment checklist (print / follow)

Use this as a do-not-guess checklist.

### Before Railway

- [ ] Titan runs locally with `python main.py web-dev` or `web-prod`
- [ ] Code is on GitHub (private repo preferred)
- [ ] `.env` is **not** committed (`git status` clean of secrets)
- [ ] You have an `OPENAI_API_KEY`
- [ ] You generated a new production `TITAN_WEB_SECRET_KEY` (≥16 chars)

### On Railway

- [ ] Account created (GitHub login)
- [ ] Project created from Titan GitHub repo
- [ ] Dockerfile build selected (automatic via `railway.json`)
- [ ] Variables from §4.1 set
- [ ] Starter variables from §4.5 set
- [ ] Public domain generated
- [ ] Deployment status = Success

### After deploy

- [ ] `GET /health` → 200
- [ ] `GET /ready` → 200
- [ ] `GET /app/` → 200
- [ ] Login with production secret works
- [ ] One chat message succeeds
- [ ] (Optional) Volume mounted at `/app/data`
- [ ] `TITAN_OBSIDIAN_ENABLED=false` on cloud
- [ ] Bookmark the public HTTPS URL

### Do not

- [ ] Do not set `TITAN_WEB_DEV_MODE=true` on Railway
- [ ] Do not use secret `titan-local-dev-only`
- [ ] Do not put secrets in Git
- [ ] Do not expect Obsidian PC vault access from Railway
- [ ] Do not enable browser automation until you intentionally install Playwright support

---

## 7. Troubleshooting guide

### Deployment fails (build error)

**Symptoms:** Red failed deployment; build logs show pip/Docker errors.  
**Checks:**

1. Confirm `Dockerfile` and `requirements.txt` exist at repo root  
2. Confirm Railway builder is **DOCKERFILE** (see `railway.json`)  
3. Read the **Build** logs for the first real Python error  
4. Ensure you pushed the latest commit to GitHub  

**Common cause:** incomplete push; wrong root directory.

### Container won’t start

**Symptoms:** Build succeeds, deploy crashes in seconds.  
**Checks:**

1. Open **Deploy Logs** (runtime, not build)  
2. Look for `Configuration de déploiement invalide` or missing secret messages  
3. Confirm `TITAN_WEB_SECRET_KEY` is set and ≥16 characters  
4. Confirm `TITAN_COOKIE_SECURE=true`  
5. Confirm `TITAN_APP_ENV=production`  
6. Confirm `TITAN_WEB_HOST=0.0.0.0` (not `127.0.0.1`)

### Health check fails

**Symptoms:** Railway reports healthcheck timeout / unhealthy.  
**Checks:**

1. App must listen on Railway’s `PORT` (Titan already does via `web-prod`)  
2. Health path must be `/health` (set in `railway.json`)  
3. If `TITAN_ALLOWED_HOSTS` is set, include **`healthcheck.railway.app`**  
4. Increase patience: cold start can take ~30–90s on free/trial capacity  
5. Hit `/health` yourself via the public URL once networking is enabled  

### Wrong PORT

**Symptoms:** App seems up in logs but Railway can’t reach it.  
**Fix:** Remove any manual `PORT=8000` override unless you know you need it. Let Railway inject `PORT`. Titan maps it automatically.

### Environment variables missing

**Symptoms:** Startup error about secret, cookie secure, or web disabled.  
**Fix:** Re-open Variables and compare against §4.1. After changes, wait for redeploy.

### Static files / `/app` missing

**Symptoms:** `/health` works but `/app/` is 404.  
**Checks:**

1. Confirm `web/v2/` is in the GitHub repo (not gitignored)  
2. Rebuild after ensuring frontend files are committed  
3. Try `/v2/` as a secondary check (same sources)

### Docker build fails on Railway

**Symptoms:** Failure during `pip install -r requirements.txt`.  
**Checks:**

1. Compare with a clean local `pip install -r requirements.txt`  
2. Confirm `requirements.txt` is valid UTF-8 and committed  
3. Retry deploy (transient network failures happen)

### Authentication issues

**Symptoms:** Web App rejects the secret; API returns 401.  
**Checks:**

1. The browser secret must **exactly** match `TITAN_WEB_SECRET_KEY` on Railway  
2. Do not use the local-dev secret on Railway  
3. Clear site data / local storage for the Railway domain and try again  
4. Confirm `TITAN_WEB_DEV_MODE` is unset/false  

### `/ready` returns 503

**Symptoms:** `/health` OK, `/ready` not ready.  
**Checks:**

1. Read JSON body — which check failed?  
2. `auth_configured` fails → secret missing  
3. `data_directory` fails → filesystem permissions / bad `TITAN_DATA_DIR`  
4. Optional tools (Obsidian, browser) should **not** fail readiness when disabled  

### Obsidian unavailable

**Expected on Railway.** Your vault lives on your PC. Keep `TITAN_OBSIDIAN_ENABLED=false` until you deliberately mount a synced vault path.

### Chat fails after UI loads

**Checks:**

1. `OPENAI_API_KEY` present and valid  
2. Runtime logs for OpenAI/API errors  
3. You are authenticated (Bearer / login gate)

---

## 8. Architecture preserved (Phase 10.2 scope)

This step does **not** change:

- Titan Brain
- REST/SSE APIs
- Web UI
- Voice Runtime internals
- Trading Runtime internals

It only packages and documents Railway deployment around the existing `web-prod` path.

---

## 9. Related documents

| Document | Role |
|----------|------|
| [`CLOUD_DEPLOYMENT_READINESS.md`](CLOUD_DEPLOYMENT_READINESS.md) | Phase 10.1 provider-neutral audit |
| [`REMOTE_ACCESS.md`](REMOTE_ACCESS.md) | Local Cloudflare Tunnel (alternative to cloud host) |
| [`WEB_APP.md`](WEB_APP.md) | API surface |
| `.env.example` | Full local env template |
| `Dockerfile` | Production image |
| `railway.json` | Railway build/deploy config |

---

## 10. Exact next action for Nolan

1. Push the latest Titan commit (including `railway.json` and this guide) to GitHub.  
2. Open https://railway.com → **New Project** → **Deploy from GitHub repo** → select Titan.  
3. Add the variables in §4.5 plus `OPENAI_API_KEY` and `TITAN_WEB_SECRET_KEY`.  
4. Generate a public domain.  
5. Verify `/health`, `/ready`, and `/app/`.

**Do not ask the coding agent to deploy for you** — Railway requires your GitHub login and your secrets.
