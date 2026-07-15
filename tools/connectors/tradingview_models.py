# =====================================
# Titan TradingView Models
# =====================================

"""Structured alert and signal models for TradingView webhook backend (Phase 16.2)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AlertPayloadFormat(str, Enum):
    """Detected TradingView alert payload format."""

    JSON = "json"
    PLAIN_TEXT = "plain_text"
    WEBHOOK = "webhook"
    TITAN = "titan"


class AlertValidationCode(str, Enum):
    """Machine-readable alert validation status."""

    OK = "ok"
    EMPTY_PAYLOAD = "empty_payload"
    INVALID_SECRET = "invalid_secret"
    UNPARSEABLE = "unparseable"
    MISSING_SYMBOL = "missing_symbol"
    MISSING_ACTION = "missing_action"


@dataclass(frozen=True)
class AlertValidationResult:
    """Outcome of webhook / alert validation."""

    ok: bool
    code: AlertValidationCode
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "code": self.code.value,
            "message": self.message,
        }


@dataclass(frozen=True)
class ParsedAlert:
    """Intermediate representation after parse_alert."""

    format: AlertPayloadFormat
    raw_message: str
    fields: dict[str, Any]
    strategy_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format.value,
            "raw_message": self.raw_message,
            "fields": dict(self.fields),
            "strategy_hint": self.strategy_hint,
        }


@dataclass(frozen=True)
class TradingSignal:
    """Normalized trading signal extracted from a TradingView alert."""

    strategy_name: str = ""
    symbol: str = ""
    market: str = ""
    timeframe: str = ""
    action: str = ""
    contracts: float = 0.0
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    timestamp: str = ""
    alert_id: str = ""
    raw_message: str = ""
    payload_format: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            object.__setattr__(
                self,
                "timestamp",
                datetime.now(timezone.utc).isoformat(),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "market": self.market,
            "timeframe": self.timeframe,
            "action": self.action,
            "contracts": self.contracts,
            "price": self.price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "timestamp": self.timestamp,
            "alert_id": self.alert_id,
            "raw_message": self.raw_message,
            "payload_format": self.payload_format,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def format_summary(self) -> str:
        """Return a concise French summary for tool output."""
        lines = [
            f"Stratégie : {self.strategy_name or 'inconnue'}",
            f"Symbole : {self.symbol or '—'}",
            f"Action : {self.action or '—'}",
        ]
        if self.market:
            lines.append(f"Marché : {self.market}")
        if self.timeframe:
            lines.append(f"Timeframe : {self.timeframe}")
        if self.contracts:
            lines.append(f"Contrats : {self.contracts}")
        if self.price is not None:
            lines.append(f"Prix : {self.price}")
        if self.stop_loss is not None:
            lines.append(f"Stop loss : {self.stop_loss}")
        if self.take_profit is not None:
            lines.append(f"Take profit : {self.take_profit}")
        if self.alert_id:
            lines.append(f"Alert ID : {self.alert_id}")
        lines.append(f"Reçu : {self.timestamp}")
        return "\n".join(lines)


@dataclass
class TradingViewAlertStoreData:
    """JSON persistence schema for received alerts."""

    version: str = "1"
    alerts: list[dict[str, Any]] = field(default_factory=list)
