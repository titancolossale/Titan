# Titan Calendar Connector — Architecture (Phase 14.1–14.2)

Phase 14.1 delivered a **provider-independent Calendar Connector foundation** on an in-memory mock backend. Phase 14.2 adds a **real Google Calendar backend** via OAuth — without coupling Brain, Planner, ReasoningLoop, ToolOrchestrator, PermissionManager, or ToolManager to Google APIs.

## Scope

**Implemented (14.1 + 14.2):**

- `list_calendars`, `list_events`, `read_event`, `search_events`
- `create_event`, `update_event`, `delete_event` (with confirmation gating)
- `detect_conflicts` — scheduling overlap detection
- `find_free_time` — availability lookup in a time window
- `CalendarResult` — structured operation outcome
- `calendar_permissions.py` — shared permission tiers
- `CalendarDecisionEngine` — Brain NL routing
- `GoogleCalendarProvider` — Google Calendar API v3 backend (Phase 14.2)
- OAuth local setup flow (`calendar-auth` CLI)
- Mock backend (`InMemoryCalendarBackend`) for tests and development

**Deferred (future phases):**

- Outlook and Apple Calendar providers
- Recurring events, advanced time zones, attendee RSVP
- External invite/send flows

## Layered Architecture

```
tools/calendar_tool.py                      ← BaseTool facade (schema + dispatch)
    └── tools/connectors/calendar_connector.py   ← Session + action dispatch (public API)
            ├── calendar_permissions.py          ← Permission tiers
            ├── calendar_backend_factory.py      ← Provider selection (mock | google)
            ├── calendar_backend.py              ← InMemoryCalendarBackend (mock)
            ├── google_calendar_provider.py      ← Google Calendar API (Phase 14.2)
            ├── google_oauth.py                  ← OAuth setup (Phase 14.2)
            ├── calendar_models.py               ← CalendarResult, CalendarEvent
            └── calendar_validator.py            ← Config validation
tools/decision/calendar_decision.py         ← WHEN/HOW to invoke (Brain integration)
```

Google imports exist **only** in `google_calendar_provider.py` and `google_oauth.py`. Upstream layers depend on `CalendarConnector` and the backend interface — never on Google SDK types.

## Orchestration Path

Calendar requests follow the same pipeline as Obsidian and Browser:

```
Brain (Reasoning)
  → NaturalLanguagePlanner
  → ReasoningLoop
  → ToolOrchestrator
  → PermissionManager
  → ToolManager
  → ToolRuntime
  → CalendarTool → CalendarConnector → Backend (mock | GoogleCalendarProvider)
```

## Permission Model

| Tier | Actions |
|------|---------|
| `AUTO_ALLOWED` | `list_calendars`, `list_events`, `read_event`, `search_events`, `detect_conflicts`, `find_free_time` |
| `CONFIRMATION_REQUIRED` | `create_event`, `update_event`, `delete_event` |
| `BLOCKED` | `share_calendar`, `calendar_sharing`, `configure_account`, `account_configuration`, destructive bulk (`bulk_delete`, `bulk_update`, `bulk_clear`) |

Write actions require `confirmed=true` in tool params (set by ToolOrchestrator after user approval). The connector enforces this gate before mutating calendars.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `TITAN_CALENDAR_ENABLED` | `true` | Enable/disable connector |
| `TITAN_CALENDAR_PROVIDER` | `mock` | Backend: `mock` or `google` |
| `TITAN_GOOGLE_CALENDAR_ENABLED` | `false` | Enable Google backend when provider=google |
| `TITAN_GOOGLE_CLIENT_SECRET_PATH` | `data/google_client_secret.json` | OAuth client JSON from Google Cloud |
| `TITAN_GOOGLE_TOKEN_PATH` | `data/google_calendar_token.json` | Stored OAuth token (local, gitignored) |
| `TITAN_CALENDAR_TIMEOUT_SECONDS` | `30` | Operation timeout budget |
| `TITAN_CALENDAR_RETRY_COUNT` | `2` | Reserved for future provider retries |

Legacy Phase 10B vars `TITAN_CALENDAR_CLIENT_ID` / `TITAN_CALENDAR_CLIENT_SECRET` remain in CredentialManager but are **not** used by the connector path.

## Google Calendar Setup (OAuth)

1. **Google Cloud Console**
   - Create or select a project
   - Enable **Google Calendar API**
   - Create OAuth 2.0 credentials (type **Desktop app**)
   - Download the client JSON

2. **Place credentials locally**

```env
TITAN_CALENDAR_PROVIDER=google
TITAN_GOOGLE_CALENDAR_ENABLED=true
TITAN_GOOGLE_CLIENT_SECRET_PATH=data/google_client_secret.json
TITAN_GOOGLE_TOKEN_PATH=data/google_calendar_token.json
```

3. **Authenticate locally**

```powershell
python main.py calendar-auth
```

A browser opens for Google consent. The token is saved to `TITAN_GOOGLE_TOKEN_PATH` (never commit this file).

4. **Validate**

```powershell
python main.py calendar-health
python main.py calendar-list
python main.py calendar-smoke-test
```

## CLI Commands

| Command | Purpose |
|---------|---------|
| `python main.py calendar-health` | Validate config and probe backend |
| `python main.py calendar-auth` | Run Google OAuth setup flow |
| `python main.py calendar-list` | List accessible calendars |
| `python main.py calendar-smoke-test` | End-to-end read tests; mock also tests CRUD |

## CalendarResult

Structured outcome for all connector operations:

```json
{
  "calendar_id": "primary",
  "event_id": "uuid",
  "title": "Réunion",
  "description": "",
  "start_time": "2026-07-04T10:00:00",
  "end_time": "2026-07-04T11:00:00",
  "attendees": ["nolan@example.com"],
  "location": "Visio",
  "status": "ok",
  "warnings": [],
  "events": [],
  "calendars": [],
  "free_slots": [],
  "conflicts": []
}
```

## Testing

```
tests/test_calendar_tool.py           — connector ops, permissions, ToolManager
tests/test_calendar_decision.py       — decision layer keyword routing
tests/test_calendar_brain_flow.py     — Brain → ToolRequest end-to-end
tests/test_calendar_validator.py      — config validation
tests/test_google_calendar_provider.py — mocked Google Calendar API (Phase 14.2)
tests/test_calendar_cli.py            — CLI commands (Phase 14.2)
tests/test_permission_manager.py      — calendar permission tiers
```

Run:

```bash
pytest tests/test_calendar_tool.py tests/test_calendar_decision.py tests/test_calendar_brain_flow.py tests/test_calendar_validator.py tests/test_google_calendar_provider.py tests/test_calendar_cli.py tests/test_permission_manager.py -v
```

## Migration Note

`CalendarTool` previously routed through `ProviderExecutor` and `StubCalendarProvider` (Phase 10B). Phase 14.1 replaced the runtime path with the connector architecture. Phase 14.2 adds Google Calendar without changing the orchestration path. The provider stub remains registered for health monitoring but is not the default execution path.
