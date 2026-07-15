# =====================================
# Titan Provider Health Resolver
# =====================================

"""Map configuration and credential state to provider health (Phase 10B — P10B-305)."""

from __future__ import annotations

from tools.provider_version import ProviderHealth
from tools.providers.credential_manager import CredentialManager, CredentialStatus
from tools.providers.provider_configuration import ProviderConfiguration
from tools.providers.provider_context import ProviderContext
from tools.tool_enums import ExecutionMode, ToolHealthState


def resolve_provider_health(
    provider_id: str,
    *,
    context: ProviderContext | None,
    default_health: ProviderHealth,
    require_credentials_in_live: bool = False,
) -> ProviderHealth:
    """Combine provider probe with configuration and credential validation."""
    if context is None:
        return default_health

    config = context.configuration
    if not config.enabled:
        return ProviderHealth(
            state=ToolHealthState.DISABLED,
            message=f"Provider {provider_id!r} désactivé par configuration.",
        )

    errors = config.validation_errors()
    if errors:
        return ProviderHealth(
            state=ToolHealthState.MISCONFIGURED,
            message=f"Configuration invalide : {'; '.join(errors)}.",
        )

    credential_health = _credential_health(
        provider_id,
        context.credential_manager,
        config,
        require_credentials_in_live=require_credentials_in_live,
    )
    if credential_health is not None:
        return credential_health

    return default_health


def reconcile_probe_health(
    provider_id: str,
    probed: ProviderHealth,
    *,
    credential_manager: CredentialManager | None,
    configuration: ProviderConfiguration | None,
    require_credentials_in_live: bool = False,
) -> ProviderHealth:
    """Reconcile a provider health_check with registry-level config and credentials."""
    if configuration is not None:
        if not configuration.enabled:
            return ProviderHealth(
                state=ToolHealthState.DISABLED,
                message=f"Provider {provider_id!r} désactivé par configuration.",
            )
        errors = configuration.validation_errors()
        if errors:
            return ProviderHealth(
                state=ToolHealthState.MISCONFIGURED,
                message=f"Configuration invalide : {'; '.join(errors)}.",
            )

    if credential_manager is not None:
        credential_health = _credential_health(
            provider_id,
            credential_manager,
            configuration,
            require_credentials_in_live=require_credentials_in_live,
        )
        if credential_health is not None:
            return credential_health

    return probed


def _credential_health(
    provider_id: str,
    credential_manager: CredentialManager,
    configuration: ProviderConfiguration | None,
    *,
    require_credentials_in_live: bool,
) -> ProviderHealth | None:
    """Return health override from credential validation, or None to keep probe result."""
    validation = credential_manager.validate(provider_id)
    requirements = credential_manager.get_requirements(provider_id)
    live_mode = (
        configuration is not None
        and configuration.execution_mode == ExecutionMode.LIVE
    )
    force_required = require_credentials_in_live or (
        live_mode
        and configuration is not None
        and bool(configuration.settings.get("require_credentials"))
    )

    if validation.status == CredentialStatus.EXPIRED:
        return ProviderHealth(
            state=ToolHealthState.MISSING_CREDENTIALS,
            message=validation.message or "Credentials expirées.",
        )

    if validation.status == CredentialStatus.INVALID:
        return ProviderHealth(
            state=ToolHealthState.MISCONFIGURED,
            message=validation.message or "Credentials invalides.",
        )

    if validation.status == CredentialStatus.MISSING:
        if force_required or any(req.required for req in requirements):
            return ProviderHealth(
                state=ToolHealthState.MISSING_CREDENTIALS,
                message=validation.message or "Credentials requises manquantes.",
            )
        return None

    return None
