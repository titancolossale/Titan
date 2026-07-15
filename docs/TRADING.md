# Titan Trading Connector — Architecture (Phase 16.1–16.5)

Phase 16.1 delivers a **provider-independent Trading Connector foundation**. Phase 16.3 adds a dedicated **Broker Connector** layer with paper trading execution. Phase 16.4 adds a **read-only broker provider foundation** for future Apex, Rithmic, Tradovate, and NinjaTrader integrations. Phase 16.5 adds the **Apex/Rithmic read-only adapter scaffold** — credential validation and readiness only, no live SDK connection, no real order execution.

## Scope

**Implemented (16.1):**

- `list_accounts`, `account_status`, `get_positions`, `get_orders`, `get_price`, `get_balance`, `get_market_status` (auto-allowed)
- `place_order`, `modify_order`, `cancel_order`, `flatten_position` (confirmation gating)
- `TradingResult` — structured operation outcome
- `trading_permissions.py` — shared permission tiers
- `TradingDecisionEngine` — Brain NL routing
- `MockTradingProvider` — legacy adapter over paper broker
- Registration in `ToolManager` via `default_tools.py`

**Implemented (16.2):**

- TradingView alert ingestion (`receive_alert`, `parse_alert`, `extract_signal`, etc.)
- `TradingSignal` normalized alert model

**Implemented (16.3):**

- `BrokerConnector` / `BrokerProvider` abstraction
- `PaperBrokerProvider` — in-memory paper trading with simulated fills
- `BrokerOrder` model with signal lineage (`source_signal_id`, stop/take profit, warnings)
- `draft_order_from_signal` / `signal_to_order` — TradingSignal → BrokerOrder draft (no execution)
- `execute_signal_order` — place order from signal (confirmation required)
- Live mode blocked: `TITAN_TRADING_MODE=paper`, `TITAN_TRADING_LIVE_ENABLED=false`

**Implemented (16.4):**

- `ReadOnlyBrokerProvider` base — real broker stubs with read-only contract
- `real_broker_stubs.py` — Apex, Rithmic, Tradovate, NinjaTrader readiness stubs (no SDK)
- Read operations: `get_pnl`, `get_margin` (plus existing read actions)
- Write operations **always BLOCKED** on real providers — even with `confirmed=true`
- `TITAN_BROKER_READ_ONLY=true` — required to select a real broker provider
- Provider readiness reports (configured, credentials, read-only, execution=false)
- `python main.py broker-health` — safety and readiness CLI

**Implemented (16.5):**

- `ApexRithmicProvider` — read-only Apex/Rithmic adapter scaffold (`tools/connectors/apex_rithmic_provider.py`)
- Credential validation only — reports missing/present credentials, provider disabled, read-only active, execution disabled
- Supported read operations scaffolded: `list_accounts`, `account_status`, `get_positions`, `get_orders`, `get_balance`, `get_market_status`, `get_pnl`, `get_margin` (raise until SDK lands)
- Write operations **always BLOCKED** — `place_order`, `modify_order`, `cancel_order`, `flatten_position` (even with `confirmed=true`)
- Config: `TITAN_BROKER_PROVIDER=apex_rithmic`, `TITAN_RITHMIC_ENABLED`, Rithmic credential env vars
- Broker health extended for Apex/Rithmic safety flags

**Not implemented:**

- Live Apex / Rithmic / Tradovate / NinjaTrader SDK connections
- Real capital execution
- Backtesting engine (future phase)

## Layered Architecture

```
TradingSignal (TradingView / Brain)
    ↓
tools/trading_tool.py                              ← BaseTool facade
    ↓
tools/connectors/trading_connector.py              ← Alerts + quotes + broker dispatch
    ↓
tools/connectors/broker_connector.py               ← Permission gating + broker actions
    ↓
tools/connectors/paper_broker_provider.py          ← PaperBrokerProvider (Phase 16.3)
    ↓
tools/connectors/read_only_broker_provider.py      ← ReadOnlyBrokerProvider (Phase 16.4)
tools/connectors/real_broker_stubs.py              ← Apex/Rithmic/Tradovate/NinjaTrader stubs
tools/connectors/apex_rithmic_provider.py          ← ApexRithmicProvider scaffold (Phase 16.5)
    ↓
(future: live Rithmic SDK read APIs behind TITAN_RITHMIC_ENABLED + credential gates)
```

Supporting modules:

| Module | Role |
|--------|------|
| `broker_models.py` | `BrokerOrder`, `BrokerResult`, `BrokerAccount`, `BrokerPosition` |
| `broker_provider_protocol.py` | `BrokerProvider` interface |
| `broker_provider_factory.py` | Provider selection; paper vs read-only real stubs |
| `read_only_broker_provider.py` | Read-only base; blocks all write methods |
| `real_broker_stubs.py` | Future real broker stubs + credential readiness |
| `apex_rithmic_provider.py` | Apex/Rithmic read-only scaffold + credential validation (Phase 16.5) |
| `broker_readiness.py` | Aggregate readiness and safety snapshot |
| `signal_to_order.py` | `draft_order_from_signal()` conversion |
| `trading_permissions.py` | Shared permission tiers |
| `tradingview_provider.py` | Alert ingestion only (no order execution) |

Broker SDK imports must exist **only** in future live provider modules. Upstream layers depend on `BrokerConnector` and `BrokerProvider` — never on broker-specific types.

## Orchestration Path

```
Brain (Reasoning)
  → NaturalLanguagePlanner
  → ReasoningLoop
  → ToolOrchestrator
  → PermissionManager
  → ToolManager
  → ToolRuntime
  → TradingTool → TradingConnector → BrokerConnector → PaperBrokerProvider
```

## Safety Model (Phase 16.5)

Titan enforces **defense in depth** before any future live trading:

| Layer | Policy |
|-------|--------|
| Config | `TITAN_TRADING_MODE=paper` (default), `TITAN_TRADING_LIVE_ENABLED=false`, `TITAN_RITHMIC_ENABLED=false` |
| Broker | `TITAN_BROKER_READ_ONLY=true` (default), `TITAN_BROKER_PROVIDER=apex_rithmic` for Apex/Rithmic |
| Factory | Rejects `mode=live`; real providers require read-only flag |
| Connector | Blocks write actions on `ReadOnlyBrokerProvider` before provider call |
| Provider | `place_order`, `modify_order`, `cancel_order`, `flatten_position` raise `BrokerWriteBlockedError` |

**Paper mode** continues simulated execution with confirmation gating — it does not touch real brokers.

**Read-only broker mode** allows querying account state from future real providers once SDK adapters land. Stubs today report credential readiness only.

**Live trading** remains disabled (`TITAN_TRADING_LIVE_ENABLED=false`). Even if set to `true`, Phase 16.5 factory rejects live mode.

## Apex / Rithmic Read-Only Adapter (Phase 16.5)

1. Set `TITAN_BROKER_PROVIDER=apex_rithmic` (or `TITAN_TRADING_PROVIDER=apex_rithmic`)
2. Set `TITAN_RITHMIC_ENABLED=true` when ready to validate credentials
3. Keep `TITAN_BROKER_READ_ONLY=true` and `TITAN_TRADING_LIVE_ENABLED=false`
4. Configure Rithmic credential env vars (see Configuration table)
5. Run `python main.py broker-health` — reports credentials missing/present, provider disabled, read-only active, execution disabled
6. Future phase: connect Rithmic SDK for real read APIs (still read-only)
7. Live execution requires a future phase with explicit multi-step approval and risk limits

Readiness status values: `provider_disabled`, `credentials_missing`, `scaffold_ready`, `blocked`.

## Future Apex / Rithmic Integration Path (legacy stubs)

1. Set `TITAN_TRADING_PROVIDER=apex` (or `rithmic`, `tradovate`, `ninjatrader`)
2. Keep `TITAN_BROKER_READ_ONLY=true` and `TITAN_TRADING_LIVE_ENABLED=false`
3. Configure provider credential env vars (see `real_broker_stubs.py`)
4. Run `python main.py broker-health` to verify readiness
5. Prefer `TITAN_BROKER_PROVIDER=apex_rithmic` for the unified Apex/Rithmic adapter (Phase 16.5)

Credential env vars (readiness checks only):

| Provider | Required env vars |
|----------|-------------------|
| Apex | `TITAN_APEX_USERNAME`, `TITAN_APEX_PASSWORD` |
| Rithmic | `TITAN_RITHMIC_USERNAME`, `TITAN_RITHMIC_PASSWORD` |
| Tradovate | `TITAN_TRADOVATE_USERNAME`, `TITAN_TRADOVATE_PASSWORD` |
| NinjaTrader | `TITAN_NINJATRADER_ACCOUNT` |

## Permission Model

| Tier | Actions |
|------|---------|
| `AUTO_ALLOWED` | `list_accounts`, `account_status`, `get_positions`, `get_orders`, `get_price`, `get_balance`, `get_market_status`, `get_pnl`, `get_margin`, `draft_order_from_signal`, TradingView read actions |
| `CONFIRMATION_REQUIRED` | `place_order`, `modify_order`, `cancel_order`, `flatten_position`, `execute_signal_order` (paper provider only) |
| `BLOCKED` | Write actions on read-only real providers (always); `configure_provider`, `reset_account`, `bulk_close_all` |

Write actions require `confirmed=true` in tool params for **paper** provider only. Read-only real providers block writes even when confirmed.

## BrokerOrder Fields

| Field | Description |
|-------|-------------|
| `order_id` | Broker-assigned order identifier (empty for drafts) |
| `account_id` | Target trading account |
| `symbol` | Instrument symbol (e.g. `NQ`, `ES`) |
| `market` | Exchange/market (e.g. `CME`) |
| `side` | `buy`, `sell`, or `close` (draft from exit signals) |
| `order_type` | `market`, `limit`, etc. |
| `quantity` | Contract/share quantity |
| `entry_price` | Limit price or fill price |
| `stop_loss` | Stop loss level (from signal or manual) |
| `take_profit` | Take profit level |
| `status` | `draft`, `submitted`, `working`, `filled`, `cancelled` |
| `timestamp` | ISO-8601 UTC timestamp |
| `source_signal_id` | Originating TradingView alert ID |
| `warnings` | Policy and provider warnings |

## Signal-to-Order Flow

1. TradingView alert → `TradingSignal` (Phase 16.2)
2. `draft_order_from_signal` → `BrokerOrder` with `status=draft` (auto-allowed, no execution)
3. User confirms → `execute_signal_order` with `confirmed=true` → `place_order` on paper broker

```python
from tools.connectors.signal_to_order import draft_order_from_signal

draft = draft_order_from_signal(signal, account_id="paper-nq-001")
# draft.status == "draft" — nothing executed
```

## Supported Broker Actions

### Read (AUTO_ALLOWED)

| Action | Description |
|--------|-------------|
| `list_accounts` | List configured trading accounts |
| `account_status` | Status and summary for one account |
| `get_positions` | Open positions for an account |
| `get_orders` | Working and recent orders |
| `get_balance` | Balance and margin |
| `get_market_status` | Market open/closed status |
| `get_pnl` | Realized/unrealized PnL summary |
| `get_margin` | Margin requirement for an account |
| `draft_order_from_signal` | Convert signal params to order draft |

### Write (CONFIRMATION_REQUIRED — paper only)

| Action | Description |
|--------|-------------|
| `place_order` | Submit a new order |
| `modify_order` | Change quantity, price, stop, or take profit |
| `cancel_order` | Cancel a working order |
| `flatten_position` | Close an open position at market |
| `execute_signal_order` | Place order from TradingSignal (requires confirmation) |

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `TITAN_TRADING_ENABLED` | `true` | Enable/disable connector |
| `TITAN_TRADING_PROVIDER` | `mock` | Provider: `mock`, `paper`, `apex_rithmic`, `apex`, `rithmic`, `tradovate`, `ninjatrader` |
| `TITAN_TRADING_MODE` | `paper` | Execution mode — must stay `paper` in Phase 16.5 |
| `TITAN_TRADING_LIVE_ENABLED` | `false` | Gate for live trading — must stay `false` until future approval phase |
| `TITAN_BROKER_READ_ONLY` | `true` | Required for real broker providers; enforces read-only access |
| `TITAN_BROKER_PROVIDER` | *(empty)* | Overrides trading provider for broker layer; use `apex_rithmic` for Apex/Rithmic |
| `TITAN_RITHMIC_ENABLED` | `false` | Enable Apex/Rithmic credential validation scaffold |
| `TITAN_TRADING_TIMEOUT_SECONDS` | `30` | Operation timeout budget |
| `TITAN_TRADING_RETRY_COUNT` | `2` | Reserved for future provider retries |

## Broker Health CLI

```bash
python main.py broker-health
```

Reports trading safety flags, active provider readiness, and future provider credential status.

## Default Paper Data

The paper broker seeds:

- **Paper NQ — Nolan** (`paper-nq-001`): $100,000 balance, 1 long NQ @ 18450.25
- **Paper NQ — Ibrahim** (`paper-nq-002`): $75,000 balance, flat
- **NQ quote**: bid 18475.00 / ask 18475.50 / last 18475.25
- **Working order**: sell limit 1 NQ @ 18500

## Testing

```bash
pytest tests/test_broker_connector.py tests/test_broker_read_only.py tests/test_apex_rithmic_provider.py tests/test_trading_tool.py tests/test_trading_decision.py tests/test_trading_orchestration.py tests/test_trading_brain_flow.py -v
python main.py broker-health
```

## Future Phases

- **16.6+**: Live Rithmic SDK read APIs (still read-only)
- **17.x**: Backtest engine integration with mission steps
- Live trading requires explicit multi-step approval and risk limit configuration

See also: `docs/TRADINGVIEW.md` (Phase 16.2 alert ingestion).
