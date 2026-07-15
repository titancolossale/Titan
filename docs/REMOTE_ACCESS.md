# Titan Remote Access (Private HTTPS)

Access Titan from any device through a **private HTTPS URL** using Cloudflare Tunnel, with mandatory authentication on every device.

Titan stays bound to **localhost** on your machine. The tunnel provides HTTPS without opening a public port on your router. Authentication is enforced by `TITAN_WEB_SECRET_KEY` — the secret never appears in frontend source code.

---

## Prerequisites

1. Titan dependencies installed:

```powershell
pip install -r requirements.txt
```

2. A strong secret in `.env`:

```env
TITAN_WEB_SECRET_KEY=your-secret-password
```

Use a long random string (32+ characters) in production. The same value is entered once per device in the Titan login screen and stored in that device's `localStorage`.

3. [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) installed on the machine running Titan.

---

## Quick start (recommended)

### Terminal 1 — Start Titan for remote access

```powershell
python main.py web-remote
```

This command:

- Binds to `127.0.0.1:8765` (override with `TITAN_WEB_REMOTE_PORT` in `.env`)
- Requires `TITAN_WEB_SECRET_KEY` (refuses to start without it)
- Keeps authentication enabled (unlike `web-dev`)
- Prints the Cloudflare Tunnel command to run

Expected output:

```
Mode accès distant — écoute locale pour Cloudflare Tunnel.
Titan Web App running at http://127.0.0.1:8765

Accès distant privé (Cloudflare Tunnel) :
  cloudflared tunnel --url http://127.0.0.1:8765
```

### Terminal 2 — Start Cloudflare Tunnel

```powershell
cloudflared tunnel --url http://127.0.0.1:8765
```

cloudflared prints a temporary HTTPS URL, for example:

```
https://something-random.trycloudflare.com
```

### On your phone or another device

1. Open the HTTPS URL from cloudflared.
2. Enter your `TITAN_WEB_SECRET_KEY` on the Titan login screen.
3. Use Titan normally. The key is saved in that browser's `localStorage` only.

To sign out on a device: **Settings → Déconnexion** (clears the stored key and reloads the page).

---

## Local development (unchanged)

Local-only development without remote access:

```powershell
python main.py web-dev
```

- Binds `127.0.0.1:8000`
- Skips authentication on protected API routes
- No secret required in `.env`

Standard local mode with authentication:

```powershell
python main.py web
```

- Uses `TITAN_WEB_HOST` and `TITAN_WEB_PORT` from `.env` (default `127.0.0.1:8000`)
- Requires `TITAN_WEB_ENABLED=true` and `TITAN_WEB_SECRET_KEY`

Open locally:

- V1 interface: `http://127.0.0.1:8000/`
- V2 interface: `http://127.0.0.1:8000/v2/`

---

## Configuration reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `TITAN_WEB_SECRET_KEY` | *(empty)* | Server-side secret; Bearer token for all protected routes |
| `TITAN_WEB_REMOTE_PORT` | `8765` | Port used by `web-remote` |
| `TITAN_WEB_HOST` | `127.0.0.1` | Bind address for `web` mode |
| `TITAN_WEB_PORT` | `8000` | Port for `web` mode |

Example `.env` for remote access:

```env
TITAN_WEB_ENABLED=true
TITAN_WEB_SECRET_KEY=your-secret-password
TITAN_WEB_REMOTE_PORT=8765
```

---

## Authentication model

### Server (`.env`)

`TITAN_WEB_SECRET_KEY` is loaded only by the Python backend. It is never embedded in JavaScript bundles or HTML.

### Client (browser)

1. On first visit, the UI calls `GET /auth/status` to check if auth is required.
2. If required and no valid token is in `localStorage`, a login gate appears.
3. The user enters the secret; the client calls `POST /auth/verify` with `Authorization: Bearer <secret>`.
4. On success, the token is saved under `localStorage` key `titan_web_secret_key`.
5. All API, chat, SSE, and stream requests include the Bearer header (SSE uses `?token=` because `EventSource` cannot send headers).

### Protected routes

When auth is required, these reject unauthenticated requests with `401`:

| Method | Path |
|--------|------|
| POST | `/chat` |
| POST | `/chat/stream` |
| GET | `/events/stream` |
| GET | `/status`, `/tools`, `/memory/status`, … |
| POST | `/auth/verify` |

Public routes (no secret):

| Method | Path |
|--------|------|
| GET | `/health` |
| GET | `/auth/status` |
| GET | `/`, `/v2/`, static assets |

`web-dev` mode disables auth checks for local development only.

---

## Security notes

- **Do not deploy without authentication.** Always set `TITAN_WEB_SECRET_KEY` before using `web-remote` or exposing a tunnel.
- **Do not use `web-dev` behind a tunnel.** Dev mode skips auth.
- The Cloudflare quick tunnel URL is unlisted but not secret — treat `TITAN_WEB_SECRET_KEY` as the real access control.
- For long-term use, configure a named Cloudflare Tunnel with access policies in the Cloudflare Zero Trust dashboard.
- Titan binds to localhost only; remote access always goes through a tunnel or reverse proxy you control.

---

## Troubleshooting

### `TITAN_WEB_SECRET_KEY est vide`

Add the secret to `.env` and restart Titan.

### Tunnel URL loads but Titan shows login every time

Clear site data or use Settings → Déconnexion, then re-enter the correct secret.

### `401 Unauthorized` on chat or SSE

- Confirm the secret in `.env` matches what you entered in the UI.
- In dev tools → Application → Local Storage, check `titan_web_secret_key`.
- Sign out and sign in again from Settings.

### Port already in use

Change `TITAN_WEB_REMOTE_PORT` in `.env` and update the cloudflared command:

```powershell
cloudflared tunnel --url http://127.0.0.1:YOUR_PORT
```

### cloudflared not found

Install from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

---

## Alternative: manual port setup

Instead of `web-remote`, you can set the port in `.env` and use normal `web` mode:

```env
TITAN_WEB_ENABLED=true
TITAN_WEB_PORT=8765
TITAN_WEB_SECRET_KEY=your-secret-password
```

```powershell
python main.py web
cloudflared tunnel --url http://127.0.0.1:8765
```

---

## Related docs

- [WEB_APP.md](./WEB_APP.md) — Web API, endpoints, and local setup
- [.env.example](../.env.example) — Environment variable reference
