# =====================================
# Titan Credential Manager
# =====================================

"""Central credential resolution for external providers (Phase 10B — P10B-301, P10B-303)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from dotenv import load_dotenv


class CredentialType(str, Enum):
    """Supported credential kinds — extensible without architectural changes (P10B-306)."""

    API_KEY = "api_key"
    OAUTH = "oauth"
    JWT = "jwt"
    REFRESH_TOKEN = "refresh_token"
    SERVICE_ACCOUNT = "service_account"


class CredentialStatus(str, Enum):
    """Credential validation outcome without exposing secret values (P10B-303)."""

    CONFIGURED = "configured"
    MISSING = "missing"
    INVALID = "invalid"
    EXPIRED = "expired"


@dataclass(frozen=True)
class CredentialRequirement:
    """Describes one credential slot for a provider."""

    name: str
    env_var: str
    credential_type: CredentialType = CredentialType.API_KEY
    required: bool = False
    min_length: int = 1
    validator: Callable[[str], bool] | None = None


@dataclass(frozen=True)
class CredentialValidationResult:
    """Redacted credential validation result for health and dashboards."""

    provider_id: str
    status: CredentialStatus
    message: str = ""
    credential_type: CredentialType | None = None
    credential_name: str = ""

    @property
    def configured(self) -> bool:
        """Return True when credentials satisfy provider requirements."""
        return self.status == CredentialStatus.CONFIGURED

    def to_public_dict(self) -> dict[str, str | None]:
        """Serialize without secret values."""
        return {
            "provider_id": self.provider_id,
            "status": self.status.value,
            "message": self.message,
            "credential_type": (
                self.credential_type.value if self.credential_type is not None else None
            ),
            "credential_name": self.credential_name,
            "configured": self.configured,
        }


_PLACEHOLDER_PATTERN = re.compile(
    r"^(your[_-]?|changeme|replace|xxx+|placeholder|dummy|test_key)",
    re.IGNORECASE,
)


def validate_brave_api_key(value: str) -> bool:
    """Validate Brave API key shape without exposing the secret."""
    stripped = value.strip()
    if len(stripped) < 20:
        return False
    if _PLACEHOLDER_PATTERN.match(stripped):
        return False
    return True


def validate_github_token(value: str) -> bool:
    """Validate GitHub personal access token shape without exposing the secret."""
    stripped = value.strip()
    if len(stripped) < 20:
        return False
    if _PLACEHOLDER_PATTERN.match(stripped):
        return False
    return True


_DEFAULT_REQUIREMENTS: dict[str, tuple[CredentialRequirement, ...]] = {
    "web_search": (
        CredentialRequirement(
            name="api_key",
            env_var="TITAN_WEB_SEARCH_API_KEY",
            credential_type=CredentialType.API_KEY,
            required=False,
        ),
    ),
    "brave_search": (
        CredentialRequirement(
            name="api_key",
            env_var="TITAN_BRAVE_SEARCH_API_KEY",
            credential_type=CredentialType.API_KEY,
            required=True,
            min_length=20,
            validator=validate_brave_api_key,
        ),
    ),
    "calendar": (
        CredentialRequirement(
            name="client_id",
            env_var="TITAN_CALENDAR_CLIENT_ID",
            credential_type=CredentialType.OAUTH,
            required=False,
        ),
        CredentialRequirement(
            name="client_secret",
            env_var="TITAN_CALENDAR_CLIENT_SECRET",
            credential_type=CredentialType.OAUTH,
            required=False,
        ),
    ),
    "github": (
        CredentialRequirement(
            name="token",
            env_var="TITAN_GITHUB_TOKEN",
            credential_type=CredentialType.API_KEY,
            required=True,
            min_length=20,
            validator=validate_github_token,
        ),
    ),
}


@dataclass
class CredentialManager:
    """Resolve provider credentials and environment variables — sole .env boundary."""

    env: dict[str, str | None] | None = None
    _requirements: dict[str, tuple[CredentialRequirement, ...]] = field(
        default_factory=lambda: dict(_DEFAULT_REQUIREMENTS)
    )
    _loaded: bool = False

    def __post_init__(self) -> None:
        if self.env is None:
            self._load_environment()
        else:
            self._loaded = True

    def _load_environment(self) -> None:
        """Load .env once; providers must never call this directly."""
        load_dotenv()
        tracked_vars = {
            req.env_var
            for requirements in self._requirements.values()
            for req in requirements
        }
        self.env = {var: os.getenv(var) for var in sorted(tracked_vars)}
        self._loaded = True

    def register_requirements(
        self,
        provider_id: str,
        requirements: tuple[CredentialRequirement, ...],
        *,
        replace: bool = False,
    ) -> None:
        """Register or replace credential requirements for a provider."""
        if provider_id in self._requirements and not replace:
            raise ValueError(f"Credential requirements already registered: {provider_id}")
        self._requirements[provider_id] = requirements

    def get_requirements(self, provider_id: str) -> tuple[CredentialRequirement, ...]:
        """Return credential requirements for a provider."""
        return self._requirements.get(provider_id, ())

    def get_secret(self, provider_id: str, credential_name: str) -> str | None:
        """Return a credential value for internal provider use only — never log this."""
        for requirement in self.get_requirements(provider_id):
            if requirement.name != credential_name:
                continue
            return self._resolve_env(requirement.env_var)
        return None

    def validate(self, provider_id: str) -> CredentialValidationResult:
        """Validate provider credentials without revealing secret values."""
        requirements = self.get_requirements(provider_id)
        if not requirements:
            return CredentialValidationResult(
                provider_id=provider_id,
                status=CredentialStatus.CONFIGURED,
                message="Aucune credential requise.",
            )

        missing_required = False
        for requirement in requirements:
            raw = self._resolve_env(requirement.env_var)
            if raw is None or not raw.strip():
                if requirement.required:
                    missing_required = True
                    return CredentialValidationResult(
                        provider_id=provider_id,
                        status=CredentialStatus.MISSING,
                        message=(
                            f"Credential manquante : {requirement.name} "
                            f"({requirement.env_var})."
                        ),
                        credential_type=requirement.credential_type,
                        credential_name=requirement.name,
                    )
                continue

            value = raw.strip()
            if len(value) < requirement.min_length:
                return CredentialValidationResult(
                    provider_id=provider_id,
                    status=CredentialStatus.INVALID,
                    message=f"Credential invalide : {requirement.name} trop courte.",
                    credential_type=requirement.credential_type,
                    credential_name=requirement.name,
                )

            if _PLACEHOLDER_PATTERN.match(value):
                return CredentialValidationResult(
                    provider_id=provider_id,
                    status=CredentialStatus.INVALID,
                    message=f"Credential invalide : {requirement.name} placeholder détecté.",
                    credential_type=requirement.credential_type,
                    credential_name=requirement.name,
                )

            if requirement.validator is not None and not requirement.validator(value):
                return CredentialValidationResult(
                    provider_id=provider_id,
                    status=CredentialStatus.INVALID,
                    message=f"Credential invalide : {requirement.name} échoue la validation.",
                    credential_type=requirement.credential_type,
                    credential_name=requirement.name,
                )

        if missing_required:
            return CredentialValidationResult(
                provider_id=provider_id,
                status=CredentialStatus.MISSING,
                message="Credentials requises manquantes.",
            )

        configured = any(
            (self._resolve_env(req.env_var) or "").strip()
            for req in requirements
        )
        if configured:
            return CredentialValidationResult(
                provider_id=provider_id,
                status=CredentialStatus.CONFIGURED,
                message="Credentials configurées.",
            )

        return CredentialValidationResult(
            provider_id=provider_id,
            status=CredentialStatus.CONFIGURED,
            message="Mode stub — credentials optionnelles absentes.",
        )

    def validate_all(self) -> dict[str, CredentialValidationResult]:
        """Validate credentials for every registered provider profile."""
        return {
            provider_id: self.validate(provider_id)
            for provider_id in sorted(self._requirements.keys())
        }

    def _resolve_env(self, env_var: str) -> str | None:
        """Read an environment variable from the injected or loaded env snapshot."""
        if self.env is None:
            return os.getenv(env_var)
        return self.env.get(env_var)
