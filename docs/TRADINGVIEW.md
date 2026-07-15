# Titan TradingView Webhook Backend — Architecture (Phase 16.2)

Phase 16.2 delivers Titan's **TradingView webhook backend**: receive, validate, parse, and extract trading signals from TradingView alerts. **No order execution** — Titan only receives and understands alerts.

Apex, Rithmic, and NinjaTrader are **not** in scope for this phase.

## Scope

**Implemented (16.2):**

- `TradingViewProvider` — webhook receive, validation, parsing, strategy identification, signal extraction
- `TradingSignal` model — normalized alert representation
- Payload support: JSON, plain text, webhook wrapper, future Titan custom payload
- `TradingViewAlertStore` — JSON persistence in `data/tradingview_alerts.json`
- `handle_tradingview_webhook()` — HTTP-agnostic entry point for future API servers
- Integration with `TradingConnector`, `TradingTool`, `PermissionManager`, `TradingDecisionEngine` (Brain), Planner, ReasoningLoop
- Read-only `TradingProvider` surface (`get_price` from latest alert; write methods blocked)

**Not implemented:**

- Order placement or broker execution
- Apex, Rithmic, NinjaTrader connectors
- Dedicated HTTP server (FastAPI module deferred — handler ready for wiring)
- Live TradingView chart/data API subscription

## Layered Architecture

```
TradingView (alert webhook POST)
    └── tools/connectors/tradingview_webhook.py     ← HTTP-agnostic handler
            └── tools/connectors/tradingview_provider.py
                    ├── tradingview_models.py       ← TradingSignal, ParsedAlert
                    └── tradingview_alert_store.py  ← JSON persistence

Brain / Orchestration (same pipeline as Phase 16.1):
    Brain (Reasoning + TradingDecisionEngine)
      → NaturalLanguagePlanner
      → ReasoningLoop
      → ToolOrchestrator
      → PermissionManager
      → ToolManager
      → TradingTool → TradingConnector → TradingViewProvider
```

## TradingSignal Model

| Field | Type | Description |
|-------|------|-------------|
| `strategy_name` | str | Strategy that emitted the alert |
| `symbol` | str | Normalized instrument (e.g. `NQ` from `NQ1!`) |
| `market` | str | Exchange/market (default `CME`) |
| `timeframe` | str | Chart interval (e.g. `5m`, `1h`) |
| `action` | str | `buy`, `sell`, or `close` |
| `contracts` | float | Position size |
| `price` | float \| null | Entry or alert price |
| `stop_loss` | float \| null | Stop loss level |
| `take_profit` | float \| null | Take profit level |
| `timestamp` | str | ISO-8601 UTC receipt time |
| `alert_id` | str | Unique alert identifier (UUID if not provided) |
| `raw_message` | str | Original payload text |
| `payload_format` | str | `json`, `plain_text`, `webhook`, or `titan` |

## Supported Payloads

### 1. JSON (structured alert)

```json
{
  "strategy": "NQ Breakout",
  "symbol": "NQ1!",
  "market": "CME",
  "timeframe": "5m",
  "action": "buy",
  "contracts": 1,
  "price": 18450.25,
  "stop_loss": 18400,
  "take_profit": 18500
}
```

### 2. Plain text (TradingView message field)

```
NQ Breakout: BUY NQ1! @ 18450.25 | SL: 18400 | TP: 18500 | 1 contract
```

### 3. Webhook wrapper (POST body)

```json
{
  "message": "NQ Breakout: BUY NQ1! @ 18450.25"
}
```

Or raw text body: `NQ Breakout: BUY NQ1! @ 18450.25`

### 4. Titan custom payload (future-ready)

```json
{
  "titan_version": "1",
  "payload_type": "titan_alert",
  "strategy_name": "NQ Breakout",
  "symbol": "NQ",
  "action": "buy",
  "contracts": 1,
  "price": 18450.25,
  "alert_id": "custom-id-001"
}
```

## Provider Operations

| Operation | Description | Permission |
|-----------|-------------|------------|
| `receive_alert` | Validate → parse → identify → extract → persist | AUTO_ALLOWED |
| `parse_alert` | Parse payload to intermediate `ParsedAlert` | AUTO_ALLOWED |
| `validate_alert` | Check secret + minimum fields | AUTO_ALLOWED |
| `identify_strategy` | Resolve strategy name from parsed alert | AUTO_ALLOWED |
| `extract_signal` | Build `TradingSignal` without persisting | AUTO_ALLOWED |
| `list_alerts` | List stored signals | AUTO_ALLOWED |
| `get_latest_alert` | Latest signal (optional symbol/strategy filter) | AUTO_ALLOWED |

Write operations (`place_order`, etc.) raise `ValueError` on `TradingViewProvider` — no orders are placed.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `TITAN_TRADING_PROVIDER` | `mock` | Set to `tradingview` for alert-first backend |
| `TITAN_TRADINGVIEW_ENABLED` | `true` | Enable TradingView provider validation |
| `TITAN_TRADINGVIEW_WEBHOOK_SECRET` | `""` | Optional shared secret (empty = no check) |
| `TITAN_TRADINGVIEW_ALERT_STORE_PATH` | `data/tradingview_alerts.json` | Alert persistence file |

## Webhook Validation

When `TITAN_TRADINGVIEW_WEBHOOK_SECRET` is set, the provider checks (in order):

1. Explicit `secret` / `webhook_secret` param
2. Header: `X-TradingView-Secret`, `X-Webhook-Secret`, or `X-Titan-Webhook-Secret`
3. JSON field: `secret`, `webhook_secret`, or `token`

Mismatch returns `401` from `handle_tradingview_webhook()`.

## Orchestration Path

TradingView alert requests use the same orchestration pipeline as other connectors:

```
User: "Liste les alertes TradingView"
  → Brain Reasoning (Intent.TRADING)
  → TradingDecisionEngine → action=list_alerts
  → NaturalLanguagePlanner → PlanStep(required_tool=trading, selected_action=list_alerts)
  → ReasoningLoop → permission sync
  → ToolOrchestrator → PermissionManager (AUTO_ALLOWED)
  → TradingTool.run(action=list_alerts)
  → TradingConnector.execute
  → TradingViewProvider.list_signals()
```

## Future Provider Flow

```
Phase 16.2 (current)  TradingView alerts → signal store → Brain awareness
Phase 16.3+           Optional HTTP server (FastAPI) exposing /webhook/tradingview
Phase 16.x            Apex / Rithmic execution (separate providers, confirmation gates)
Phase 16.x            Strategy registry linking alert strategy_name → risk rules
Phase 16.x            Mission triggers: alert received → Brain mission step advance
```

Execution providers will consume `TradingSignal` from the alert store — never directly from raw webhook text — preserving a single normalized signal contract.

## Security Notes

- Webhook secret validation is recommended in production
- Alert store lives in `data/` — treat as sensitive (strategy signals)
- No broker credentials in TradingView provider
- Order actions remain CONFIRMATION_REQUIRED on mock/paper providers; blocked on TradingView provider

## Related Files

| Path | Role |
|------|------|
| `tools/connectors/tradingview_provider.py` | Core provider |
| `tools/connectors/tradingview_models.py` | `TradingSignal`, `ParsedAlert` |
| `tools/connectors/tradingview_alert_store.py` | JSON persistence |
| `tools/connectors/tradingview_webhook.py` | Webhook handler |
| `tools/connectors/trading_connector.py` | Action dispatch |
| `tools/trading_tool.py` | Tool facade |
| `tools/decision/trading_decision.py` | Brain NL routing |
| `tests/test_tradingview_provider.py` | Phase 16.2 tests |

See also: `docs/TRADING.md` (Phase 16.1 foundation).
