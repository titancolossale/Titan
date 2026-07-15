# =====================================
# Titan Web Readiness
# =====================================

"""Readiness checks for cloud deployment probes."""

from __future__ import annotations

from typing import Any

from config.deployment import check_data_directory_ready, load_deployment_settings
from config.settings import TITAN_NAME, VERSION, env_bool, get_web_secret_key, is_web_dev_mode
from tools.connectors.obsidian_validator import validate_obsidian_config


def _optional_subsystem_status(
    *,
    name: str,
    enabled: bool,
    healthy: bool,
    message: str,
) -> dict[str, Any]:
    if not enabled:
        return {
            "name": name,
            "status": "disabled",
            "required": False,
            "healthy": None,
            "message": message,
        }
    return {
        "name": name,
        "status": "available" if healthy else "unavailable",
        "required": False,
        "healthy": healthy,
        "message": message,
    }


def build_readiness_payload(*, include_subsystems: bool = True) -> dict[str, Any]:
    """Build an honest readiness report for GET /ready."""
    dev_mode = is_web_dev_mode()
    web_enabled = env_bool("TITAN_WEB_ENABLED")
    secret_configured = bool(get_web_secret_key())
    auth_required = not dev_mode and secret_configured

    data_ok, data_message = check_data_directory_ready()
    core_ready = web_enabled and data_ok
    if auth_required and not secret_configured:
        core_ready = False

    checks: dict[str, Any] = {
        "web_enabled": {"ok": web_enabled, "required": True},
        "data_directory": {"ok": data_ok, "required": True, "message": data_message},
        "auth_configured": {
            "ok": secret_configured or dev_mode,
            "required": auth_required,
        },
    }

    optional_subsystems: list[dict[str, Any]] = []
    if include_subsystems:
        try:
            settings = load_deployment_settings(validate=False)
        except Exception:
            settings = None

        obsidian = validate_obsidian_config()
        optional_subsystems.append(
            _optional_subsystem_status(
                name="obsidian",
                enabled=obsidian.code.value != "obsidian_disabled",
                healthy=obsidian.ok,
                message=obsidian.message,
            )
        )

        if settings is not None:
            optional_subsystems.extend(
                [
                    {
                        "name": "browser",
                        "status": (
                            "disabled"
                            if not settings.browser_tool_enabled
                            else "enabled"
                        ),
                        "required": False,
                        "healthy": None,
                        "message": (
                            "Browser connector disabled."
                            if not settings.browser_tool_enabled
                            else "Browser connector enabled; health not probed at readiness."
                        ),
                    },
                    _optional_subsystem_status(
                        name="voice",
                        enabled=settings.voice_runtime_enabled,
                        healthy=True,
                        message=(
                            "Voice runtime disabled."
                            if not settings.voice_runtime_enabled
                            else "Voice runtime enabled (server-side mock/browser STT)."
                        ),
                    ),
                    _optional_subsystem_status(
                        name="trading",
                        enabled=settings.trading_runtime_enabled,
                        healthy=True,
                        message=(
                            "Trading runtime disabled."
                            if not settings.trading_runtime_enabled
                            else "Trading runtime enabled (mock/paper default)."
                        ),
                    ),
                ]
            )

    status = "ready" if core_ready else "not_ready"
    http_status = 200 if core_ready else 503

    return {
        "status": status,
        "http_status": http_status,
        "name": TITAN_NAME,
        "version": VERSION,
        "dev_mode": dev_mode,
        "auth_required": auth_required,
        "checks": checks,
        "optional_subsystems": optional_subsystems,
    }
