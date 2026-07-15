# Titan Private Web App

Phases **17.1–17.3** — local, private web interface on top of Titan Core.

- **17.1** — FastAPI foundation, Bearer auth, minimal placeholder UI
- **17.2** — Titan Design Language (tokens, components, `/design` preview)
- **17.3** — Titan Interface V1 at `/` (TDL layout, canvas neural network, context panels)

Titan remains a **CLI-first** system. The web layer is optional, disabled by default, and bound to localhost. It does not replace the REPL.

## Architecture

```
Web UI (web/static/)
    ↓ HTTP
FastAPI (api/app.py)
    ↓
Titan Core (core/titan.py)
    ↓
Brain → Planner → ReasoningLoop → ToolOrchestrator → Tools
```

The web API uses the **same composition root** as `python main.py`. No duplicate `Brain`, `ToolManager`, or memory instances.

## Configuration

Titan loads `.env` from the **project root** (`config/settings.py` → `ENV_FILE_PATH`) before reading any `TITAN_*` variable.

Add to `.env` (see `.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `TITAN_WEB_ENABLED` | `false` | Must be `true` to start with `python main.py web` |
| `TITAN_WEB_HOST` | `127.0.0.1` | Bind address (local only) |
| `TITAN_WEB_PORT` | `8000` | HTTP port |
| `TITAN_WEB_SECRET_KEY` | *(empty)* | Bearer token for protected routes |

**Security notes:**

- Do **not** expose this server to the public internet.
- Set a strong `TITAN_WEB_SECRET_KEY` before enabling the web UI in normal mode.
- `/health` and `/` are public; API routes require `Authorization: Bearer <secret>` in normal mode.
- `web-dev` mode binds **only** to `127.0.0.1` and relaxes auth for local development.

## Run — normal mode

1. Install dependencies (includes FastAPI and uvicorn):

```powershell
pip install -r requirements.txt
```

2. Enable web mode in `.env`:

```env
TITAN_WEB_ENABLED=true
TITAN_WEB_SECRET_KEY=your-long-random-secret
```

Use a long random string for `TITAN_WEB_SECRET_KEY` (for example 32+ characters). This value is entered once in the web UI **Settings** and stored in `localStorage`.

3. Start the server:

```powershell
python main.py web
```

4. Open `http://127.0.0.1:8000/` in a browser.

On success you should see:

```
Titan Web App running at http://127.0.0.1:8000
```

## Run — development mode (no .env changes)

For quick local testing without editing `.env`:

```powershell
python main.py web-dev
```

`web-dev`:

- Starts even when `TITAN_WEB_ENABLED=false`
- Binds **only** to `127.0.0.1:8000` (never a public interface)
- Uses a temporary dev secret (`titan-local-dev-only`) when `TITAN_WEB_SECRET_KEY` is missing
- Allows protected API routes **without** a Bearer token (local development only)

Then open `http://127.0.0.1:8000/` and verify:

```powershell
curl http://127.0.0.1:8000/health
```

Expected: `{"status":"ok",...}`

## Troubleshooting — connection refused

If `http://127.0.0.1:8000` shows **ERR_CONNECTION_REFUSED**:

1. **Confirm the server is running** — you should see `Titan Web App running at http://127.0.0.1:8000` in the terminal. If the process exited, read the message above it.

2. **`TITAN_WEB_ENABLED` is false or missing** — `python main.py web` prints:
   - the detected value of `TITAN_WEB_ENABLED`
   - the exact `.env` file path being loaded
   - the lines to add

   Fix by adding to `.env`:

   ```env
   TITAN_WEB_ENABLED=true
   TITAN_WEB_SECRET_KEY=your-long-random-secret
   ```

   Or use `python main.py web-dev` instead.

3. **`TITAN_WEB_SECRET_KEY` is empty** — normal `web` mode refuses to start. Set a secret in `.env` or use `web-dev`.

4. **Wrong directory** — run commands from the Titan project root so `.env` is found at `<project>/.env`.

5. **Port in use** — change `TITAN_WEB_PORT` in `.env` or stop the other process on port 8000.

## CLI REPL (unchanged)

```powershell
python main.py
```

Preview TDL components at `http://127.0.0.1:8000/design` when the server is running.

## API Endpoints

| Method | Path | Auth (normal) | Auth (web-dev) | Description |
|--------|------|---------------|----------------|-------------|
| GET | `/health` | No | No | Liveness probe |
| GET | `/` | No | No | Titan Interface V1 (Phase 17.3) |
| GET | `/design` | No | No | TDL component preview (Phase 17.2) |
| POST | `/chat` | Yes | No | Send message to `Brain.think()` |
| GET | `/status` | Yes | No | Titan system status |
| GET | `/tools` | Yes | No | Registered tools + provider dashboard |
| GET | `/memory/status` | Yes | No | Memory subsystem summary |
| GET | `/obsidian/status` | Yes | No | Obsidian connector validation |
| GET | `/browser/status` | Yes | No | Browser connector health |
| GET | `/calendar/status` | Yes | No | Calendar connector health |
| GET | `/email/status` | Yes | No | Email connector health |
| GET | `/trading/status` | Yes | No | Trading connector health |

### Chat request

```json
POST /chat
Authorization: Bearer <TITAN_WEB_SECRET_KEY>

{
  "message": "Bonjour Titan",
  "user": "Nolan"
}
```

Response:

```json
{
  "response": "...",
  "user": "Nolan"
}
```

## Module layout

| Path | Role |
|------|------|
| `api/app.py` | FastAPI app and routes |
| `api/auth.py` | Bearer token verification |
| `api/titan_service.py` | Shared Titan instance + chat handler |
| `api/status_builders.py` | JSON status payloads |
| `core/web_cli.py` | `python main.py web` and `web-dev` entry |
| `config/settings.py` | `.env` loading and `TITAN_WEB_*` settings |
| `web/static/index.html` | Titan Interface V1 shell |
| `web/static/app.js` | UI logic, chat, status polling |
| `web/static/neural-network.js` | Canvas neural network animation |
| `web/static/design/tokens.css` | TDL design tokens |
| `web/static/design/titan-ui.css` | TDL component classes |
| `web/static/design.html` | TDL preview page |

## Tests

```powershell
python -m pytest tests/test_web_api.py -v
```

## Out of scope (Phase 17.3)

- Public deployment or reverse proxy setup
- Voice interface
- Browser, Calendar, Trading UI (placeholders only)
- WebSocket streaming
- Multi-user session cookies (Bearer token only for now)
- Final dashboard / full feature parity with CLI

Future phases may add HTTPS, tunneling for private phone access, WebGL neural layers, and dedicated subsystem views.
