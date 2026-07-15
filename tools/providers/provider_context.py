# =====================================
# Titan Provider Context
# =====================================

"""Dependency-injected runtime context for providers (Phase 10B — P10B-304)."""

from __future__ import annotations

from dataclasses import dataclass

from tools.providers.credential_manager import CredentialManager
from tools.providers.provider_configuration import ProviderConfiguration


@dataclass(frozen=True)
class ProviderContext:
    """Shared bootstrap context injected into providers at registration."""

    credential_manager: CredentialManager
    configuration: ProviderConfiguration
