# Gmail Production Validation Report (Phase 15.3)

**Generated:** 2026-07-04T22:10:00-04:00

## Provider

| Property | Value |
|----------|-------|
| Provider (configured) | `mock` (default — Gmail not selected) |
| Provider (target) | `gmail` |
| `TITAN_EMAIL_ENABLED` | `true` (default) |
| `TITAN_EMAIL_PROVIDER` | `mock` (not set in `.env`) |
| `TITAN_GMAIL_ENABLED` | `false` (not set in `.env`) |
| Client secret path | `data/google_gmail_client_secret.json` |
| Token path | `data/google_gmail_token.json` |
| Token gitignored | **NO** — should be added to `.gitignore` alongside Calendar tokens |
| Client secret gitignored | **NO** — should be added to `.gitignore` |

> Gmail OAuth uses **separate** paths from Calendar (`TITAN_GMAIL_*` vs `TITAN_GOOGLE_*`). Calendar credentials at `data/google_client_secret.json` are not reused automatically.

## OAuth Setup Status

| Check | Status |
|-------|--------|
| `.env` Gmail variables configured | **NO** — `TITAN_EMAIL_PROVIDER`, `TITAN_GMAIL_ENABLED` absent |
| Gmail client secret file present | **NO** — `data/google_gmail_client_secret.json` missing |
| OAuth flow completed | **NO** — blocked until client secret is placed |
| Token saved locally | **NO** — `data/google_gmail_token.json` missing |

### Required OAuth Steps (Nolan)

1. Open [Google Cloud Console](https://console.cloud.google.com/) → select or create a project.
2. **APIs & Services → Library** → enable **Gmail API**.
3. **APIs & Services → Credentials** → **Create Credentials → OAuth client ID**.
   - Application type: **Desktop app**
   - Name: e.g. `Titan Gmail`
4. Download the JSON client file.
5. Save it as:

   ```
   c:\Users\nolan\OneDrive\Desktop\Titan\data\google_gmail_client_secret.json
   ```

6. Add to `.env`:

   ```env
   TITAN_EMAIL_ENABLED=true
   TITAN_EMAIL_PROVIDER=gmail
   TITAN_GMAIL_ENABLED=true
   TITAN_GMAIL_CLIENT_SECRET_PATH=data/google_gmail_client_secret.json
   TITAN_GMAIL_TOKEN_PATH=data/google_gmail_token.json
   ```

7. Run OAuth (opens browser for consent). On Windows PowerShell, set UTF-8 first to avoid a console encoding crash:

   ```powershell
   cd c:\Users\nolan\OneDrive\Desktop\Titan
   $env:PYTHONIOENCODING = "utf-8"
   python main.py email-auth
   ```

8. Sign in with Nolan's Gmail account and accept Gmail access (read, compose, send, modify).
9. Re-run validation commands below.

## Commands Run

| Command | Exit code | Result |
|---------|-----------|--------|
| `python main.py email-health` | 0 | **PASS** — mock backend only |
| `python main.py email-auth` | 1 | **FAIL** — `gmail_missing_client_secret` |
| `python main.py email-list` | 0 | **PASS** — mock inbox (3 emails), not real Gmail |
| `python main.py email-smoke-test` | 0 | **PASS** — mock backend; permission gates verified |

### Simulated Gmail health (env override, no `.env` change)

With `TITAN_EMAIL_PROVIDER=gmail` and `TITAN_GMAIL_ENABLED=true`:

| Command | Exit code | Result |
|---------|-----------|--------|
| `python main.py email-health` | 1 | **FAIL** — `gmail_missing_client_secret` |

### email-health output (current — mock)

```
Statut : PRÊT (ok)
Connecteur Email prêt (backend mock, timeout=30.0s).
Backend mock en mémoire — aucune connexion Gmail.
Health check : OK — 4 email(s) accessible(s).
```

### email-auth output (summary)

```
Fichier client OAuth Gmail introuvable : data\google_gmail_client_secret.json.
Téléchargez les identifiants OAuth 2.0 (application de bureau) depuis Google Cloud Console.
```

### email-list output (mock — not production Gmail)

```
Provider : mock
Nombre : 3

1. Revue Phase 14 — Calendar [non lu]
   De : ibrahim@example.com
   ID : msg-7a42d05a
2. [Titan] PR #42 merged
   De : notifications@github.com
   ID : msg-184d687a
3. Weekly digest — AI tools [non lu]
   De : newsletter@example.com
   ID : msg-b93556a8
```

### email-smoke-test output (mock)

```
  [OK] list_emails — 3 email(s)
  [OK] search_emails — 1 résultat(s)
  [OK] read_email — Revue Phase 14 — Calendar
  [OK] send_email (confirmation requise)
  [OK] compose_email (confirmation requise)
  [OK] compose_email sans confirmation — bloqué comme attendu
  [OK] compose_email (mock)
  [OK] send_email (mock — non disponible) — bloqué comme attendu

Smoke test : SUCCÈS
```

## Recent Email Listing (Production Gmail)

**None** — validation blocked before Gmail API connection. The listing above is from the in-memory mock backend.

## Permission Validation

Validated via `PermissionManager`, `evaluate_email_permission`, and `pytest tests/test_email_tool.py -k permission` (11/11 passed).

| Action | Expected tier | Observed |
|--------|---------------|----------|
| `list_emails` | `AUTO_ALLOWED` | `auto_allowed` ✓ |
| `search_emails` | `AUTO_ALLOWED` | `auto_allowed` ✓ |
| `read_email` | `AUTO_ALLOWED` | `auto_allowed` ✓ |
| `compose_email` | `CONFIRMATION_REQUIRED` | `confirmation_required` ✓ |
| `send_email` | `CONFIRMATION_REQUIRED` | `confirmation_required` ✓ |
| `delete_email` | `CONFIRMATION_REQUIRED` | `confirmation_required` ✓ |
| `archive_email` | `CONFIRMATION_REQUIRED` | `confirmation_required` ✓ |
| `mark_read` | `CONFIRMATION_REQUIRED` | `confirmation_required` ✓ |
| `mark_unread` | `CONFIRMATION_REQUIRED` | `confirmation_required` ✓ |
| `configure_account` | `BLOCKED` | `blocked` ✓ |

### Connector enforcement (smoke test)

| Check | Result |
|-------|--------|
| `compose_email` without `confirmed` | **Blocked** ✓ |
| `send_email` without `confirmed` | **Blocked** ✓ |
| No email sent during this run | **Confirmed** — mock backend; send unavailable |
| No emails modified or deleted during this run | **Confirmed** — Gmail path not reached |

### Gmail smoke test note (after OAuth)

When `TITAN_EMAIL_PROVIDER=gmail`, `email-smoke-test` will additionally:

- Create a **Gmail draft** (`compose_email` with `confirmed=true`) — does **not** send
- Verify `send_email` without confirmation is blocked

The draft is addressed to `validation@example.com` with subject `Titan Email Validation Test`. Delete it manually in Gmail drafts if undesired. No send, delete, or archive operations are executed by the smoke test.

## Safety Constraints

| Constraint | Status |
|------------|--------|
| Read/search/list auto-allowed | ✓ Verified in code + tests |
| Compose/send/delete/archive require confirmation | ✓ Verified in code + tests |
| No email sent during validation | ✓ No send attempted (mock only) |
| No emails modified or deleted | ✓ No Gmail connection; mock compose only |

## Errors

1. **`gmail_missing_client_secret`** — Place OAuth desktop client JSON at `data/google_gmail_client_secret.json`.
2. **`gmail_missing_token`** — Run `python main.py email-auth` after step 1.
3. **`.env` not configured for Gmail** — Add `TITAN_EMAIL_PROVIDER=gmail` and `TITAN_GMAIL_ENABLED=true`.
4. **Windows console encoding** — `email-auth` setup guide prints Unicode arrows (`→`); set `$env:PYTHONIOENCODING = "utf-8"` before running on PowerShell.

## Final Verdict

**BLOCKED — OAuth credentials required**

Gmail backend is **not yet validated in production**. The connector, permission model, and mock smoke test pass; validation cannot proceed against Nolan's real Gmail until OAuth setup is completed (steps above) and these commands are re-run:

```powershell
$env:PYTHONIOENCODING = "utf-8"
python main.py email-health
python main.py email-list
python main.py email-smoke-test
```

When `email-health` reports Gmail backend connected, `email-list` returns real recent messages, and `email-smoke-test` reports `SUCCÈS`, update this report and confirm:

> Gmail backend is validated in production.
