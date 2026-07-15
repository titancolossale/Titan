# =====================================
# Titan TradingView Alert Store
# =====================================

"""JSON-backed persistence for received TradingView alerts (Phase 16.2)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from tools.connectors.tradingview_models import TradingSignal, TradingViewAlertStoreData


class TradingViewAlertStore:
    """Persist and retrieve TradingView alert signals."""

    def __init__(self, file_path: Path | str) -> None:
        self.file_path = Path(file_path)

    def load(self) -> TradingViewAlertStoreData:
        if not self.file_path.exists():
            return TradingViewAlertStoreData()
        with self.file_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict):
            return TradingViewAlertStoreData()
        alerts = raw.get("alerts", [])
        if not isinstance(alerts, list):
            alerts = []
        return TradingViewAlertStoreData(
            version=str(raw.get("version", "1")),
            alerts=[entry for entry in alerts if isinstance(entry, dict)],
        )

    def save(self, data: TradingViewAlertStoreData) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": data.version,
            "alerts": data.alerts,
        }
        with self.file_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=4, ensure_ascii=False)

    def append_signal(self, signal: TradingSignal) -> TradingSignal:
        """Store *signal*, assigning alert_id when missing."""
        alert_id = signal.alert_id or str(uuid.uuid4())
        stored = TradingSignal(
            strategy_name=signal.strategy_name,
            symbol=signal.symbol,
            market=signal.market,
            timeframe=signal.timeframe,
            action=signal.action,
            contracts=signal.contracts,
            price=signal.price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            timestamp=signal.timestamp,
            alert_id=alert_id,
            raw_message=signal.raw_message,
            payload_format=signal.payload_format,
        )
        data = self.load()
        data.alerts.append(stored.to_dict())
        self.save(data)
        return stored

    def list_signals(self, *, limit: int = 50) -> list[TradingSignal]:
        data = self.load()
        entries = data.alerts[-limit:] if limit > 0 else data.alerts
        return [self._dict_to_signal(entry) for entry in reversed(entries)]

    def get_latest_signal(
        self,
        *,
        symbol: str | None = None,
        strategy_name: str | None = None,
    ) -> TradingSignal | None:
        for entry in self.load().alerts[::-1]:
            signal = self._dict_to_signal(entry)
            if symbol and signal.symbol.upper() != symbol.upper():
                continue
            if strategy_name and strategy_name.lower() not in signal.strategy_name.lower():
                continue
            return signal
        return None

    def get_signal_by_id(self, alert_id: str) -> TradingSignal | None:
        for entry in self.load().alerts:
            if str(entry.get("alert_id", "")) == alert_id:
                return self._dict_to_signal(entry)
        return None

    @staticmethod
    def _dict_to_signal(entry: dict) -> TradingSignal:
        return TradingSignal(
            strategy_name=str(entry.get("strategy_name", "")),
            symbol=str(entry.get("symbol", "")),
            market=str(entry.get("market", "")),
            timeframe=str(entry.get("timeframe", "")),
            action=str(entry.get("action", "")),
            contracts=float(entry.get("contracts", 0) or 0),
            price=_optional_float(entry.get("price")),
            stop_loss=_optional_float(entry.get("stop_loss")),
            take_profit=_optional_float(entry.get("take_profit")),
            timestamp=str(entry.get("timestamp", "")),
            alert_id=str(entry.get("alert_id", "")),
            raw_message=str(entry.get("raw_message", "")),
            payload_format=str(entry.get("payload_format", "")),
        )


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
