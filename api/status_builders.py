# =====================================
# Titan Web Status Builders
# =====================================

"""JSON status payloads for web API connector and subsystem endpoints."""

from __future__ import annotations

from typing import Any

from config.settings import (
    TITAN_BROWSER_ENABLED,
    TITAN_CALENDAR_ENABLED,
    TITAN_CALENDAR_PROVIDER,
    TITAN_EMAIL_ENABLED,
    TITAN_EMAIL_PROVIDER,
    TITAN_OBSIDIAN_ENABLED,
    TITAN_TRADING_ENABLED,
    TITAN_TRADING_MODE,
    TITAN_TRADING_PROVIDER,
)
from core.titan import Titan
from tools.connectors.browser_connector import BrowserConnector
from tools.connectors.calendar_connector import CalendarConnector
from tools.connectors.email_connector import EmailConnector
from tools.connectors.obsidian_validator import validate_obsidian_config
from tools.connectors.trading_connector import TradingConnector


def build_system_status(titan: Titan) -> dict[str, Any]:
    """Return general Titan operational status."""
    titan.context.refresh()
    mission = titan.mission.get_mission()
    return {
        "name": titan.name,
        "version": titan.version,
        "status": titan.status,
        "creator": titan.creator,
        "user": titan.context.current_user,
        "context": {
            "active_project": titan.context.active_project,
            "current_goal": titan.context.current_goal,
            "current_phase": titan.context.current_phase,
        },
        "mission": {
            "active": mission.get("active", False),
            "title": mission.get("title", ""),
            "current_step": mission.get("current_step", ""),
        },
        "state": titan.state.get_state(),
    }


def build_memory_status(titan: Titan) -> dict[str, Any]:
    """Return memory subsystem status without exposing note contents."""
    document = titan.memory.get_document()
    users = document.get("users", {})
    user_summaries = {
        username: {
            "note_categories": sorted(notes.keys()) if isinstance(notes, dict) else [],
            "category_counts": {
                category: len(items) if isinstance(items, list) else 0
                for category, items in (notes.items() if isinstance(notes, dict) else [])
            },
        }
        for username, notes in users.items()
    }
    return {
        "short_term_notes_count": len(titan.memory.get_session_notes()),
        "long_term_users": sorted(users.keys()),
        "users": user_summaries,
    }


def build_tools_status(titan: Titan) -> dict[str, Any]:
    """Return registered tools and provider dashboard snapshot."""
    return {
        "tools": titan.tools.list_tools(),
        "provider_dashboard": titan.tools.export_provider_dashboard(),
    }


def _connector_status(
    *,
    subsystem: str,
    enabled: bool,
    provider: str,
    healthy: bool,
    message: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "subsystem": subsystem,
        "enabled": enabled,
        "provider": provider,
        "healthy": healthy,
        "message": message,
    }
    if extra:
        payload.update(extra)
    return payload


def build_obsidian_status() -> dict[str, Any]:
    """Return Obsidian connector validation status."""
    validation = validate_obsidian_config()
    return _connector_status(
        subsystem="obsidian",
        enabled=TITAN_OBSIDIAN_ENABLED,
        provider="obsidian",
        healthy=validation.ok,
        message=validation.message,
        extra={
            "code": validation.code.value,
            "vault_path": str(validation.vault_path) if validation.vault_path else None,
            "readable": validation.readable,
            "writable": validation.writable,
        },
    )


def build_browser_status() -> dict[str, Any]:
    """Return Browser connector health status."""
    connector = BrowserConnector()
    healthy, message = connector.health_check()
    return _connector_status(
        subsystem="browser",
        enabled=TITAN_BROWSER_ENABLED,
        provider="playwright",
        healthy=healthy,
        message=message,
    )


def build_calendar_status() -> dict[str, Any]:
    """Return Calendar connector health status."""
    connector = CalendarConnector()
    healthy, message = connector.health_check()
    return _connector_status(
        subsystem="calendar",
        enabled=TITAN_CALENDAR_ENABLED,
        provider=TITAN_CALENDAR_PROVIDER,
        healthy=healthy,
        message=message,
    )


def build_email_status() -> dict[str, Any]:
    """Return Email connector health status."""
    connector = EmailConnector()
    healthy, message = connector.health_check()
    return _connector_status(
        subsystem="email",
        enabled=TITAN_EMAIL_ENABLED,
        provider=TITAN_EMAIL_PROVIDER,
        healthy=healthy,
        message=message,
    )


def build_trading_status() -> dict[str, Any]:
    """Return Trading connector health status."""
    connector = TradingConnector()
    healthy, message = connector.health_check()
    return _connector_status(
        subsystem="trading",
        enabled=TITAN_TRADING_ENABLED,
        provider=TITAN_TRADING_PROVIDER,
        healthy=healthy,
        message=message,
        extra={"mode": TITAN_TRADING_MODE},
    )
