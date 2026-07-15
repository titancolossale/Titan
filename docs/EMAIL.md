# Titan Email Connector — Architecture (Phase 15.1 + 15.2)

Phase 15.1 delivers a **provider-independent Email Connector foundation** on an in-memory mock backend. Phase 15.2 adds a **real Gmail backend** via Google Gmail API and OAuth.

## Scope

**Implemented (15.1):**

- `list_emails`, `search_emails`, `read_email` (auto-allowed)
- `compose_email`, `send_email`, `delete_email`, `archive_email`, `mark_read`, `mark_unread` (confirmation gating)
- `EmailResult` — structured operation outcome with sender, recipients, subject, preview, body, attachments, labels, unread, received_time, warnings, status
- `email_permissions.py` — shared permission tiers
- `EmailDecisionEngine` — Brain NL routing
- `InMemoryEmailBackend` — mock storage for tests and development
- Registration in `ToolManager` via `default_tools.py`

**Implemented (15.2):**

- `GmailProvider` — real Gmail API backend (`tools/connectors/gmail_provider.py`)
- Gmail OAuth (`tools/connectors/gmail_oauth.py`) with separate token paths from Calendar
- Real `send_email`, `compose_email` (draft), `delete_email`, `archive_email`, `mark_read`, `mark_unread` on Gmail
- CLI: `email-auth`, `email-health`, `email-list`, `email-smoke-test`

**Not implemented:**

- IMAP / Outlook providers
- Multiple concurrent providers

## Layered Architecture

```
tools/email_tool.py                           ← BaseTool facade (schema + dispatch)
    └── tools/connectors/email_connector.py   ← Session + action dispatch (public API)
            ├── email_permissions.py          ← Permission tiers
            ├── email_backend_factory.py      ← Provider selection (mock | gmail)
            ├── email_backend.py              ← InMemoryEmailBackend (mock)
            ├── gmail_provider.py             ← GmailProvider (Phase 15.2)
            ├── gmail_oauth.py                ← Gmail OAuth (Phase 15.2)
            ├── email_backend_protocol.py     ← EmailBackend Protocol
            ├── email_models.py               ← EmailResult, EmailMessage
            └── email_validator.py            ← Config validation
tools/decision/email_decision.py            ← WHEN/HOW to invoke (Brain integration)
```

Gmail imports exist **only** in `gmail_provider.py` and `gmail_oauth.py`. Upstream layers depend on `EmailConnector` and the backend interface — never on Gmail SDK types.

## Orchestration Path

Email requests follow the same pipeline as Obsidian, Browser, and Calendar:

```
Brain (Reasoning)
  → NaturalLanguagePlanner
  → ReasoningLoop
  → ToolOrchestrator
  → PermissionManager
  → ToolManager
  → ToolRuntime
  → EmailTool → EmailConnector → Backend (mock | GmailProvider)
```

## Permission Model

| Tier | Actions |
|------|---------|
| `AUTO_ALLOWED` | `list_emails`, `search_emails`, `read_email` |
| `CONFIRMATION_REQUIRED` | `compose_email`, `send_email`, `delete_email`, `archive_email`, `mark_read`, `mark_unread` |
| `BLOCKED` | `configure_account`, `account_configuration`, destructive bulk (`bulk_delete`, `bulk_archive`), `export_all`, `forward_all` |

Write actions require `confirmed=true` in tool params (set by ToolOrchestrator after user approval). The connector enforces this gate before mutating mailboxes.

On the **mock backend**, `send_email` returns an error even with confirmation — use Gmail for real delivery.

## EmailResult Fields

| Field | Description |
|-------|-------------|
| `sender` | From address |
| `recipients` | To / CC / BCC list |
| `subject` | Email subject line |
| `preview` | Short body preview |
| `body` | Full message body |
| `attachments` | Attachment filenames |
| `labels` | Folder / label tags |
| `unread` | Unread flag |
| `received_time` | ISO timestamp |
| `warnings` | Provider or policy warnings |
| `status` | Operation status (`ok`, `draft`, `sent`, `deleted`, `archived`, `read`, `unread`) |

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `TITAN_EMAIL_ENABLED` | `true` | Enable/disable connector |
| `TITAN_EMAIL_PROVIDER` | `mock` | Backend: `mock` or `gmail` |
| `TITAN_GMAIL_ENABLED` | `false` | Enable Gmail backend when provider=gmail |
| `TITAN_GMAIL_CLIENT_SECRET_PATH` | `data/google_gmail_client_secret.json` | OAuth client JSON |
| `TITAN_GMAIL_TOKEN_PATH` | `data/google_gmail_token.json` | Stored OAuth token |
| `TITAN_EMAIL_TIMEOUT_SECONDS` | `30` | Operation timeout budget |
| `TITAN_EMAIL_RETRY_COUNT` | `2` | Reserved for future provider retries |

### Gmail setup (.env)

```env
TITAN_EMAIL_ENABLED=true
TITAN_EMAIL_PROVIDER=gmail
TITAN_GMAIL_ENABLED=true
TITAN_GMAIL_CLIENT_SECRET_PATH=data/google_gmail_client_secret.json
TITAN_GMAIL_TOKEN_PATH=data/google_gmail_token.json
```

### OAuth flow

1. Google Cloud Console → enable Gmail API → create OAuth 2.0 Desktop client
2. Download client JSON to `TITAN_GMAIL_CLIENT_SECRET_PATH`
3. Run `python main.py email-auth`
4. Verify with `python main.py email-health`

Gmail uses **separate** OAuth paths from Calendar (`TITAN_GOOGLE_*` vs `TITAN_GMAIL_*`).

## CLI Commands

| Command | Purpose |
|---------|---------|
| `python main.py email-health` | Validate config + backend connectivity |
| `python main.py email-auth` | Gmail OAuth setup |
| `python main.py email-list` | List recent emails |
| `python main.py email-smoke-test` | End-to-end read + permission checks |

## Development Usage

Mock backend is active by default — no external account required:

```powershell
python -c "from tools.tool_manager import ToolManager; m=ToolManager(); print(m.run('email', {'action': 'list_emails'}))"
```

Gmail backend (after OAuth):

```powershell
python main.py email-list
```

## Supported Operations

| Operation | Mock | Gmail |
|-----------|------|-------|
| `list_emails` | ✓ | ✓ |
| `search_emails` | ✓ | ✓ |
| `read_email` | ✓ | ✓ |
| `compose_email` | ✓ (local draft) | ✓ (Gmail draft) |
| `send_email` | ✗ | ✓ |
| `delete_email` | ✓ (trash) | ✓ (trash) |
| `archive_email` | ✓ | ✓ |
| `mark_read` | ✓ | ✓ |
| `mark_unread` | ✓ | ✓ |

All write operations require `confirmed=true`.

## Testing

```powershell
pytest tests/test_email_tool.py tests/test_email_decision.py tests/test_email_brain_flow.py tests/test_email_orchestration.py tests/test_gmail_provider.py -v
```
