# Titan Private Authentication (Phase 10.3)

This document explains how to lock Titan behind private username/password authentication on Railway.

Titan must not be publicly usable by anyone who only knows the URL. Access requires a successful login that creates a secure HttpOnly session cookie.

---

## 1. Generate Nolan’s password hash locally

Never type a plaintext password into Railway, GitHub, `.env`, or chat logs.

From the Titan project root on your machine:

```bash
python scripts/generate_titan_password_hash.py
```

The script will:

1. Prompt for a password (hidden input)
2. Ask for confirmation
3. Reject mismatched passwords
4. Reject weak passwords (minimum 14 characters, upper, lower, number, special character)
5. Print **only** the Argon2id hash and Railway instructions

It never writes the plaintext password to disk and never commits anything to Git.

Copy the printed hash. You will paste it into Railway only.

---

## 2. Railway Variables to create

In Railway → your Titan service → **Variables**, set:

| Variable | Value |
|----------|--------|
| `AUTH_REQUIRED` | `true` |
| `TITAN_AUTH_USERNAME` | Nolan’s chosen username (example: `nolan`) |
| `TITAN_AUTH_PASSWORD_HASH` | The Argon2id hash from the script |
| `TITAN_WEB_SECRET_KEY` | Already configured strong secret (session signing / legacy) |
| `TITAN_SESSION_IDLE_MINUTES` | `60` |
| `TITAN_SESSION_MAX_HOURS` | `24` |
| `COOKIE_SECURE` | `true` |
| `TITAN_COOKIE_SECURE` | `true` |
| `PUBLIC_BASE_URL` | `https://titan-production-e377.up.railway.app` |
| `ALLOWED_HOSTS` | `titan-production-e377.up.railway.app` |
| `CORS_ALLOWED_ORIGINS` | `https://titan-production-e377.up.railway.app` |
| `TITAN_APP_ENV` | `production` |

Also keep existing production variables (`PORT` is injected by Railway, `TITAN_WEB_ENABLED=true`, etc.).

**Do not** put plaintext passwords in Variables.  
**Do not** commit these values to Git.

Aliases accepted:

- `AUTH_REQUIRED` ↔ `TITAN_AUTH_REQUIRED`
- `COOKIE_SECURE` ↔ `TITAN_COOKIE_SECURE`
- `PUBLIC_BASE_URL` ↔ `TITAN_PUBLIC_BASE_URL`
- `ALLOWED_HOSTS` ↔ `TITAN_ALLOWED_HOSTS`
- `CORS_ALLOWED_ORIGINS` ↔ `TITAN_CORS_ALLOWED_ORIGINS`

---

## 3. Redeploy

1. Commit and push the Phase 10.3 code (auth layer, login UI, tests, docs).
2. Confirm Railway Variables from section 2 are saved.
3. Trigger a redeploy (push to the connected branch, or Railway **Deploy**).
4. Wait until `/health` returns `200`.

---

## 4. Test login

1. Open `https://titan-production-e377.up.railway.app/app/`
2. You should be redirected to `/login`
3. Enter Nolan’s username and password
4. Click **ENTRER DANS TITAN** (or press Enter)
5. You should land on `/app/` with Titan loaded
6. Reload the page — you should remain authenticated

Incorrect credentials must show only:

> Identifiants invalides.

The UI must not say whether the username or the password was wrong.

---

## 5. Test logout

1. Open Titan settings
2. Click **Déconnexion**
3. You should return to `/login`
4. Visiting `/app/` again should redirect to `/login`
5. Protected APIs such as `/status` should return `401` without a session

---

## 6. Change the password later

1. Run `python scripts/generate_titan_password_hash.py` again with the new password
2. Update `TITAN_AUTH_PASSWORD_HASH` in Railway Variables
3. Redeploy (or restart) the service
4. Old sessions become invalid after restart (in-memory sessions) or after idle/absolute expiry
5. Log in with the new password

Never update the password by writing plaintext into Railway.

---

## 7. Recover access safely

If Nolan is locked out:

1. Confirm `TITAN_AUTH_USERNAME` matches the username being typed
2. Generate a **new** hash locally and replace `TITAN_AUTH_PASSWORD_HASH`
3. Redeploy / restart
4. If rate-limited (“Trop de tentatives”), wait ~15 minutes or restart the service to clear the in-memory limiter
5. Do **not** temporarily set `AUTH_REQUIRED=false` on a public URL unless the service is fully private/offline

If the hash variable is missing or malformed, production startup validation fails on purpose.

---

## 8. Add Ibrahim later (no rewrite)

Phase 10.3 already supports a second authorized user via environment variables:

```text
TITAN_AUTH_USERNAME_2=<ibrahim_username>
TITAN_AUTH_PASSWORD_HASH_2=<argon2id_hash_for_ibrahim>
```

Steps:

1. Ibrahim generates his own hash locally with the same script (on his machine)
2. Nolan (or ops) adds the two Railway variables
3. Redeploy
4. Ibrahim logs in at `/login` with his own username/password

Each user gets a separate session. Memory isolation rules in Titan still apply at the product layer — authentication only gates access.

---

## 9. Public routes (and why)

These remain reachable **without** login:

| Route | Why |
|-------|-----|
| `/health` | Railway / uptime liveness probe |
| `/ready` | Readiness probe for deploy health |
| `/login` | Login page |
| `/login/*` | Login CSS/JS/logo assets only |
| `/auth/status` | Public auth policy (no secrets) |
| `/auth/login` | Credential check endpoint |
| `/auth/logout` | Idempotent logout / cookie clear |

Everything else is protected when session auth is enabled, including:

- `/`, `/app`, `/app/*`, `/v2/*`
- Chat, memory, tools, Brain, status APIs
- SSE `/events/stream` and `/chat/stream`
- `/docs` and diagnostic endpoints

Unauthenticated browser page requests → redirect to `/login`  
Unauthenticated API requests → HTTP `401` JSON

---

## 10. Troubleshooting

### Login loop

- Confirm `COOKIE_SECURE=true` and you are on **HTTPS**
- Confirm `PUBLIC_BASE_URL` / `ALLOWED_HOSTS` match the Railway domain
- Clear site cookies for the domain, then retry
- Check that login response sets `titan_session` with `HttpOnly; Secure; SameSite=Lax`

### Cookies not sticking behind Railway

- Do **not** set `COOKIE_SECURE=false` in production
- Titan trusts `X-Forwarded-Proto` from Railway’s proxy
- Secure cookies require the public HTTPS origin

### 401 on APIs after login

- Ensure requests use `credentials: "same-origin"` (the V2 frontend does)
- Ensure the CSRF cookie `titan_csrf` is present for POST requests
- Re-login if the session idle timeout (`TITAN_SESSION_IDLE_MINUTES`) expired

### “Trop de tentatives”

- Login is rate-limited after repeated failures
- Wait for the lockout window (~15 minutes) or restart the service

### Open redirect fears

- `next` / redirect targets are restricted to same-site relative paths starting with `/`
- External URLs are rejected and fall back to `/app/`

---

## Security model (summary)

- Passwords verified with **Argon2id** (bcrypt hashes also accepted)
- Server-side sessions with unpredictable IDs
- Session cookie: HttpOnly + Secure + SameSite=Lax + expiration
- Idle timeout + absolute max lifetime
- Logout revokes the server session
- Brute-force lockout on `/auth/login`
- Generic invalid-credentials message
- CSRF checks on authenticated state-changing requests
- No plaintext password in source, frontend JS, HTML, logs, or Git

### Remaining limitations (honest)

- Sessions are **in-memory** per process — a Railway restart logs everyone out (safe, but not sticky across multiple instances)
- Multi-instance horizontal scaling would need a shared session store (Redis, etc.) — not in this phase
- Rate limiting is in-memory (same restart caveat)
- Legacy local Bearer-token mode still exists when session auth is **not** configured (local/dev); production must enable session auth via the Variables above
