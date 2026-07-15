# =====================================
# Titan TradingView Provider
# =====================================

"""TradingView webhook alert provider — receive and understand alerts only (Phase 16.2).

No order execution. Apex, Rithmic, and NinjaTrader are out of scope for this phase.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    TITAN_TRADINGVIEW_ALERT_STORE_PATH,
    TITAN_TRADINGVIEW_WEBHOOK_SECRET,
)
from tools.connectors.trading_provider import (
    StoredAccount,
    StoredOrder,
    StoredPosition,
    StoredQuote,
)
from tools.connectors.tradingview_alert_store import TradingViewAlertStore
from tools.connectors.tradingview_models import (
    AlertPayloadFormat,
    AlertValidationCode,
    AlertValidationResult,
    ParsedAlert,
    TradingSignal,
)

_SYMBOL_ALIASES = {
    "NQ1!": "NQ",
    "ES1!": "ES",
    "YM1!": "YM",
    "RTY1!": "RTY",
    "CL1!": "CL",
    "GC1!": "GC",
}

_ACTION_ALIASES = {
    "long": "buy",
    "short": "sell",
    "exit": "close",
    "flat": "close",
    "close_long": "close",
    "close_short": "close",
}

_STRATEGY_JSON_KEYS = (
    "strategy",
    "strategy_name",
    "strategyName",
    "strategy_id",
    "name",
)

_SYMBOL_JSON_KEYS = ("symbol", "ticker", "instrument", "sym")

_ACTION_JSON_KEYS = ("action", "side", "direction", "signal")

_PLAIN_TEXT_PATTERN = re.compile(
    r"""
    ^(?P<strategy>[^:]+?):\s*
    (?P<action>buy|sell|long|short|close|exit|flat)\s+
    (?P<symbol>[A-Z0-9!]+)
    (?:\s*@\s*(?P<price>[\d.]+))?
    (?:\s*\|\s*SL:\s*(?P<stop_loss>[\d.]+))?
    (?:\s*\|\s*TP:\s*(?P<take_profit>[\d.]+))?
    (?:\s*\|\s*(?P<contracts>[\d.]+)\s*contract)?
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SIMPLE_ACTION_PATTERN = re.compile(
    r"\b(buy|sell|long|short|close|exit)\b.*?\b(NQ1?|ES1?|YM1?|RTY1?|CL1?|GC1?|[A-Z]{2,6})\b",
    re.IGNORECASE,
)


class TradingViewProvider:
    """Receive, validate, parse, and extract TradingView alert signals."""

    provider_name = "tradingview"

    def __init__(
        self,
        *,
        webhook_secret: str | None = None,
        alert_store_path: Path | str | None = None,
    ) -> None:
        self._webhook_secret = (
            webhook_secret
            if webhook_secret is not None
            else TITAN_TRADINGVIEW_WEBHOOK_SECRET
        )
        store_path = alert_store_path or TITAN_TRADINGVIEW_ALERT_STORE_PATH
        self._store = TradingViewAlertStore(store_path)

    @property
    def alert_store(self) -> TradingViewAlertStore:
        return self._store

    # ------------------------------------------------------------------
    # Core alert operations (Phase 16.2)
    # ------------------------------------------------------------------

    def receive_alert(
        self,
        payload: str | bytes | dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        secret: str | None = None,
    ) -> TradingSignal:
        """Validate, parse, identify strategy, extract signal, and persist."""
        validation = self.validate_alert(payload, headers=headers, secret=secret)
        if not validation.ok:
            raise ValueError(validation.message)

        parsed = self.parse_alert(payload)
        strategy_name = self.identify_strategy(parsed)
        signal = self.extract_signal(parsed, strategy_name=strategy_name)
        return self._store.append_signal(signal)

    def parse_alert(self, payload: str | bytes | dict[str, Any]) -> ParsedAlert:
        """Parse JSON, plain text, webhook, or Titan custom payloads."""
        raw_text, data_dict = self._normalize_payload(payload)
        if not raw_text and not data_dict:
            return ParsedAlert(
                format=AlertPayloadFormat.PLAIN_TEXT,
                raw_message="",
                fields={},
            )

        if self._is_titan_payload(data_dict):
            return self._parse_titan_payload(data_dict, raw_text)

        if data_dict:
            payload_format = AlertPayloadFormat.JSON
            if self._looks_like_webhook_wrapper(data_dict):
                payload_format = AlertPayloadFormat.WEBHOOK
            fields = self._flatten_json_fields(data_dict)
            strategy_hint = self._first_string(data_dict, _STRATEGY_JSON_KEYS)
            message = str(data_dict.get("message", data_dict.get("text", ""))).strip()
            if message and payload_format == AlertPayloadFormat.WEBHOOK:
                nested = self._parse_plain_text(message)
                fields.update(nested.fields)
                if not strategy_hint:
                    strategy_hint = nested.strategy_hint
            return ParsedAlert(
                format=payload_format,
                raw_message=raw_text or json.dumps(data_dict, ensure_ascii=False),
                fields=fields,
                strategy_hint=strategy_hint,
            )

        return self._parse_plain_text(raw_text)

    def validate_alert(
        self,
        payload: str | bytes | dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        secret: str | None = None,
    ) -> AlertValidationResult:
        """Validate webhook secret and minimum alert content."""
        raw_text, data_dict = self._normalize_payload(payload)
        if not raw_text and not data_dict:
            return AlertValidationResult(
                ok=False,
                code=AlertValidationCode.EMPTY_PAYLOAD,
                message="Alerte TradingView vide.",
            )

        if self._webhook_secret:
            provided = self._extract_secret(secret, headers, data_dict)
            if provided != self._webhook_secret:
                return AlertValidationResult(
                    ok=False,
                    code=AlertValidationCode.INVALID_SECRET,
                    message="Secret webhook TradingView invalide.",
                )

        parsed = self.parse_alert(payload)
        if not parsed.fields and not parsed.raw_message.strip():
            return AlertValidationResult(
                ok=False,
                code=AlertValidationCode.UNPARSEABLE,
                message="Alerte TradingView illisible.",
            )

        symbol = str(parsed.fields.get("symbol", "")).strip()
        action = str(parsed.fields.get("action", "")).strip()
        if not symbol:
            return AlertValidationResult(
                ok=False,
                code=AlertValidationCode.MISSING_SYMBOL,
                message="Symbole manquant dans l'alerte TradingView.",
            )
        if not action:
            return AlertValidationResult(
                ok=False,
                code=AlertValidationCode.MISSING_ACTION,
                message="Action manquante dans l'alerte TradingView.",
            )

        return AlertValidationResult(
            ok=True,
            code=AlertValidationCode.OK,
            message="Alerte TradingView valide.",
        )

    def identify_strategy(self, parsed: ParsedAlert | dict[str, Any]) -> str:
        """Identify strategy name from parsed alert data."""
        if isinstance(parsed, dict):
            parsed = ParsedAlert(
                format=AlertPayloadFormat.JSON,
                raw_message=str(parsed.get("raw_message", "")),
                fields=dict(parsed.get("fields", parsed)),
                strategy_hint=str(parsed.get("strategy_hint", "")),
            )

        if parsed.strategy_hint:
            return parsed.strategy_hint.strip()

        for key in _STRATEGY_JSON_KEYS:
            value = parsed.fields.get(key)
            if value:
                return str(value).strip()

        if parsed.raw_message:
            if ":" in parsed.raw_message:
                return parsed.raw_message.split(":", 1)[0].strip()
            match = re.match(r"^\[([^\]]+)\]", parsed.raw_message.strip())
            if match:
                return match.group(1).strip()

        return "unknown"

    def extract_signal(
        self,
        parsed: ParsedAlert | dict[str, Any],
        *,
        strategy_name: str = "",
    ) -> TradingSignal:
        """Build a normalized TradingSignal from parsed alert data."""
        if isinstance(parsed, dict):
            if "fields" in parsed:
                parsed_alert = ParsedAlert(
                    format=AlertPayloadFormat(parsed.get("format", "json")),
                    raw_message=str(parsed.get("raw_message", "")),
                    fields=dict(parsed["fields"]),
                    strategy_hint=str(parsed.get("strategy_hint", "")),
                )
            else:
                parsed_alert = ParsedAlert(
                    format=AlertPayloadFormat.JSON,
                    raw_message=json.dumps(parsed, ensure_ascii=False),
                    fields=dict(parsed),
                )
        else:
            parsed_alert = parsed

        resolved_strategy = strategy_name or self.identify_strategy(parsed_alert)
        fields = parsed_alert.fields

        symbol = self._normalize_symbol(
            self._first_string(fields, _SYMBOL_JSON_KEYS),
        )
        action = self._normalize_action(
            self._first_string(fields, _ACTION_JSON_KEYS),
        )
        market = str(fields.get("market", fields.get("exchange", "CME"))).strip()
        timeframe = str(
            fields.get("timeframe", fields.get("interval", "")),
        ).strip()
        contracts = self._to_float(fields.get("contracts", fields.get("qty", 1)), 1.0)
        price = self._optional_float(fields.get("price"))
        stop_loss = self._optional_float(
            fields.get("stop_loss", fields.get("sl", fields.get("stop"))),
        )
        take_profit = self._optional_float(
            fields.get("take_profit", fields.get("tp", fields.get("target"))),
        )
        alert_id = str(
            fields.get("alert_id", fields.get("id", "")),
        ).strip() or str(uuid.uuid4())
        timestamp = str(
            fields.get("timestamp", fields.get("time", "")),
        ).strip() or datetime.now(timezone.utc).isoformat()

        return TradingSignal(
            strategy_name=resolved_strategy,
            symbol=symbol,
            market=market.upper() if market else "CME",
            timeframe=timeframe,
            action=action,
            contracts=contracts,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            timestamp=timestamp,
            alert_id=alert_id,
            raw_message=parsed_alert.raw_message,
            payload_format=parsed_alert.format.value,
        )

    def list_signals(self, *, limit: int = 50) -> list[TradingSignal]:
        return self._store.list_signals(limit=limit)

    def get_latest_signal(
        self,
        *,
        symbol: str | None = None,
        strategy_name: str | None = None,
    ) -> TradingSignal | None:
        return self._store.get_latest_signal(
            symbol=symbol,
            strategy_name=strategy_name,
        )

    # ------------------------------------------------------------------
    # TradingProvider read-only surface (no order execution)
    # ------------------------------------------------------------------

    def list_accounts(self) -> list[StoredAccount]:
        return [
            StoredAccount(
                account_id="tradingview-alerts",
                account_name="TradingView Alerts — read-only",
                provider=self.provider_name,
                balance=0.0,
                margin=0.0,
                status="active",
                market="CME",
            ),
        ]

    def account_status(self, account_id: str) -> StoredAccount | None:
        accounts = self.list_accounts()
        for account in accounts:
            if account.account_id == account_id:
                return account
        return None

    def get_positions(
        self,
        account_id: str,
        *,
        symbol: str | None = None,
    ) -> list[StoredPosition]:
        return []

    def get_orders(
        self,
        account_id: str,
        *,
        symbol: str | None = None,
        status: str | None = None,
    ) -> list[StoredOrder]:
        return []

    def get_price(
        self,
        symbol: str,
        *,
        market: str | None = None,
        timeframe: str | None = None,
    ) -> StoredQuote | None:
        normalized = self._normalize_symbol(symbol)
        latest = self._store.get_latest_signal(symbol=normalized)
        if latest is None or latest.price is None:
            return None
        resolved_market = market or latest.market or "CME"
        resolved_timeframe = timeframe or latest.timeframe or "1m"
        spread = max(latest.price * 0.0001, 0.25)
        return StoredQuote(
            symbol=normalized,
            market=resolved_market,
            timeframe=resolved_timeframe,
            bid=latest.price - spread,
            ask=latest.price + spread,
            last_price=latest.price,
        )

    def get_balance(self, account_id: str) -> tuple[float, float]:
        return 0.0, 0.0

    def get_market_status(self, market: str) -> str:
        return "unknown — TradingView alert feed only"

    def place_order(self, *args: object, **kwargs: object) -> StoredOrder:
        raise ValueError(
            "TradingView ne place pas d'ordres — réception d'alertes uniquement.",
        )

    def modify_order(self, *args: object, **kwargs: object) -> StoredOrder | None:
        raise ValueError(
            "TradingView ne modifie pas d'ordres — réception d'alertes uniquement.",
        )

    def cancel_order(self, order_id: str) -> bool:
        raise ValueError(
            "TradingView n'annule pas d'ordres — réception d'alertes uniquement.",
        )

    def flatten_position(self, *args: object, **kwargs: object) -> StoredOrder | None:
        raise ValueError(
            "TradingView ne ferme pas de positions — réception d'alertes uniquement.",
        )

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_payload(
        payload: str | bytes | dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        if isinstance(payload, dict):
            message = str(payload.get("message", payload.get("text", ""))).strip()
            if not message and len(payload) == 1:
                only_value = next(iter(payload.values()))
                if isinstance(only_value, str):
                    message = only_value.strip()
            return message, dict(payload)

        if isinstance(payload, bytes):
            payload = payload.decode("utf-8", errors="replace")

        text = str(payload).strip()
        if not text:
            return "", {}

        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return text, {}

        if isinstance(decoded, dict):
            message = str(decoded.get("message", decoded.get("text", ""))).strip()
            return message or text, decoded
        return text, {}

    @staticmethod
    def _is_titan_payload(data: dict[str, Any]) -> bool:
        return (
            str(data.get("titan_version", "")).strip() != ""
            or str(data.get("payload_type", "")).lower() == "titan_alert"
        )

    def _parse_titan_payload(
        self,
        data: dict[str, Any],
        raw_text: str,
    ) -> ParsedAlert:
        fields = self._flatten_json_fields(data)
        strategy_hint = str(
            data.get("strategy_name", data.get("strategy", "")),
        ).strip()
        return ParsedAlert(
            format=AlertPayloadFormat.TITAN,
            raw_message=raw_text or json.dumps(data, ensure_ascii=False),
            fields=fields,
            strategy_hint=strategy_hint,
        )

    def _parse_plain_text(self, raw_text: str) -> ParsedAlert:
        match = _PLAIN_TEXT_PATTERN.match(raw_text.strip())
        if match:
            groups = match.groupdict()
            fields = {
                "strategy": groups.get("strategy", "").strip(),
                "action": groups.get("action", "").strip(),
                "symbol": groups.get("symbol", "").strip(),
                "price": groups.get("price"),
                "stop_loss": groups.get("stop_loss"),
                "take_profit": groups.get("take_profit"),
                "contracts": groups.get("contracts") or 1,
            }
            return ParsedAlert(
                format=AlertPayloadFormat.PLAIN_TEXT,
                raw_message=raw_text,
                fields=fields,
                strategy_hint=fields.get("strategy", ""),
            )

        simple = _SIMPLE_ACTION_PATTERN.search(raw_text)
        fields: dict[str, Any] = {"message": raw_text}
        strategy_hint = ""
        if simple:
            fields["action"] = simple.group(1)
            fields["symbol"] = simple.group(2)
        if ":" in raw_text:
            strategy_hint = raw_text.split(":", 1)[0].strip()
            fields["strategy"] = strategy_hint

        return ParsedAlert(
            format=AlertPayloadFormat.PLAIN_TEXT,
            raw_message=raw_text,
            fields=fields,
            strategy_hint=strategy_hint,
        )

    @staticmethod
    def _looks_like_webhook_wrapper(data: dict[str, Any]) -> bool:
        wrapper_keys = {"message", "text", "content", "alert", "payload"}
        return any(key in data for key in wrapper_keys)

    @staticmethod
    def _flatten_json_fields(data: dict[str, Any]) -> dict[str, Any]:
        flattened = dict(data)
        for wrapper_key in ("alert", "payload", "data", "signal"):
            nested = data.get(wrapper_key)
            if isinstance(nested, dict):
                flattened.update(nested)
        message = str(data.get("message", data.get("text", ""))).strip()
        if message and "action" not in flattened:
            nested = TradingViewProvider._parse_embedded_json_message(message)
            if nested:
                flattened.update(nested)
        return flattened

    @staticmethod
    def _parse_embedded_json_message(message: str) -> dict[str, Any]:
        try:
            decoded = json.loads(message)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}

    @staticmethod
    def _first_string(data: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = data.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        cleaned = symbol.strip().upper()
        return _SYMBOL_ALIASES.get(cleaned, cleaned.replace("1!", ""))

    @staticmethod
    def _normalize_action(action: str) -> str:
        cleaned = action.strip().lower()
        return _ACTION_ALIASES.get(cleaned, cleaned)

    @staticmethod
    def _optional_float(value: object) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value: object, default: float) -> float:
        parsed = TradingViewProvider._optional_float(value)
        return default if parsed is None else parsed

    @staticmethod
    def _extract_secret(
        secret: str | None,
        headers: dict[str, str] | None,
        data: dict[str, Any],
    ) -> str:
        if secret:
            return secret.strip()
        header_map = {key.lower(): value for key, value in (headers or {}).items()}
        for header_name in (
            "x-tradingview-secret",
            "x-webhook-secret",
            "x-titan-webhook-secret",
        ):
            if header_name in header_map:
                return str(header_map[header_name]).strip()
        for field_name in ("secret", "webhook_secret", "token"):
            if field_name in data:
                return str(data[field_name]).strip()
        return ""

    @staticmethod
    def hash_payload(payload: str | bytes) -> str:
        """Return a stable hash for deduplication and audit."""
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
