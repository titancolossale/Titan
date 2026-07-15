# Google Calendar Production Validation Report (Phase 14.3)

**Generated:** 2026-07-04T20:55:00-04:00

## Provider

| Property | Value |
|----------|-------|
| Provider | `google` |
| `TITAN_CALENDAR_PROVIDER` | `google` |
| `TITAN_GOOGLE_CALENDAR_ENABLED` | `true` |
| Client secret path | `data/google_client_secret.json` |
| Token path | `data/google_calendar_token.json` |
| Token gitignored | Yes (`.gitignore` lines 6–7) |
| Client secret gitignored | Yes (`.gitignore` line 6) |

## OAuth Setup Status

| Check | Status |
|-------|--------|
| Google client secret file present | **NO** — `data/google_client_secret.json` missing |
| OAuth flow completed | **NO** — blocked until client secret is placed |
| Token saved locally | **NO** — `data/google_calendar_token.json` missing |
| Calendar provider set to google | **YES** — configured in `.env` |

### Required OAuth Steps (Nolan)

1. Open [Google Cloud Console](https://console.cloud.google.com/) → select or create a project.
2. **APIs & Services → Library** → enable **Google Calendar API**.
3. **APIs & Services → Credentials** → **Create Credentials → OAuth client ID**.
   - Application type: **Desktop app**
   - Name: e.g. `Titan Calendar`
4. Download the JSON client file.
5. Save it as:

   ```
   c:\Users\nolan\OneDrive\Desktop\Titan\data\google_client_secret.json
   ```

6. Run OAuth (opens browser for consent):

   ```powershell
   cd c:\Users\nolan\OneDrive\Desktop\Titan
   python main.py calendar-auth
   ```

7. Sign in with the Google account that owns your calendar and accept calendar access.
8. Re-run validation commands below.

## Commands Run

| Command | Exit code | Result |
|---------|-----------|--------|
| `python main.py calendar-health` | 1 | **FAIL** — `google_missing_client_secret` |
| `python main.py calendar-list` | 1 | **FAIL** — config validation blocked |
| `python main.py calendar-smoke-test` | 1 | **FAIL** — config validation blocked |
| `python main.py calendar-auth` | — | **NOT RUN** — requires client secret file first |

### calendar-health output (summary)

```
Statut : ÉCHEC (google_missing_client_secret)
Fichier client OAuth introuvable : data\google_client_secret.json
```

## Calendars Detected

**None** — validation blocked before API connection.

## Smoke Test Plan (after OAuth)

The smoke test (`calendar-smoke-test`) validates:

| Step | Safety |
|------|--------|
| `list_calendars` | Read-only |
| `list_events` (7 days) | Read-only |
| `search_events` | Read-only |
| `detect_conflicts` | Read-only |
| `find_free_time` | Read-only |
| `create_event` without `confirmed` | Must be **blocked** |
| `update_event` without `confirmed` | Must be **blocked** |
| `delete_event` without `confirmed` | Must be **blocked** |
| `create_event` with `confirmed=true` | Temporary test event only |
| `read_event` | Test event only |
| `update_event` with `confirmed=true` | Test event only |
| `search_events` | Search test event title |
| `delete_event` with `confirmed=true` | Cleanup test event |
| Cleanup verification | Confirm event no longer exists |

**Test event marker:** `Titan Calendar Validation Test`  
**Test event window:** `2099-06-15T14:00:00` → `2099-06-15T15:00:00` (far future — no real events modified)

**Safety constraints enforced:**

- Create/update/delete require user confirmation (`confirmed=true`)
- No calendar sharing actions
- No bulk operations
- Only the marked temporary test event is created/modified/deleted

## Test Event

| Property | Value |
|----------|-------|
| Created | **NO** — blocked by missing OAuth |
| Title | `Titan Calendar Validation Test` |
| Deleted | **N/A** |
| Cleanup confirmed | **N/A** |

## Errors

1. **`google_missing_client_secret`** — Place OAuth desktop client JSON at `data/google_client_secret.json`.
2. **`google_missing_token`** — Run `python main.py calendar-auth` after step 1.

## Code Changes (Phase 14.3 prep)

- `.env` updated: `TITAN_CALENDAR_PROVIDER=google`, `TITAN_GOOGLE_CALENDAR_ENABLED=true`
- `calendar-smoke-test` extended: full CRUD cycle for Google provider with confirmation gating and cleanup verification
- Unit tests updated: `tests/test_calendar_cli.py` (7/7 passing)

## Final Verdict

**BLOCKED — OAuth credentials required**

Google Calendar backend is **not yet validated in production**. Configuration and safety gates are in place; validation cannot proceed until Nolan completes OAuth setup (steps above) and re-runs:

```powershell
python main.py calendar-health
python main.py calendar-list
python main.py calendar-smoke-test
```

When all four commands succeed and the smoke test reports `SUCCÈS`, update this report and confirm:

> Google Calendar backend is validated in production.
