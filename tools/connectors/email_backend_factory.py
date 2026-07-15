# =====================================
# Titan Email Backend Factory
# =====================================

"""Select email backend by configuration without leaking Gmail into callers."""

from __future__ import annotations

from config.settings import TITAN_EMAIL_PROVIDER, TITAN_GMAIL_ENABLED
from tools.connectors.email_backend import InMemoryEmailBackend
from tools.connectors.email_backend_protocol import EmailBackend


def create_email_backend(
    *,
    provider: str | None = None,
    gmail_enabled: bool | None = None,
) -> EmailBackend:
    """Return the configured email backend implementation."""
    resolved_provider = (provider or TITAN_EMAIL_PROVIDER).strip().lower()
    use_gmail = TITAN_GMAIL_ENABLED if gmail_enabled is None else gmail_enabled

    if resolved_provider == "gmail":
        if not use_gmail:
            raise ValueError(
                "TITAN_EMAIL_PROVIDER=gmail mais TITAN_GMAIL_ENABLED=false. "
                "Activez Gmail dans .env."
            )
        from tools.connectors.gmail_provider import GmailProvider

        return GmailProvider.from_config()

    if resolved_provider not in {"mock", "memory", "inmemory"}:
        raise ValueError(
            f"Provider email inconnu : {resolved_provider!r}. "
            "Valeurs supportées : mock, gmail (Phase 15.2+)."
        )

    backend = InMemoryEmailBackend()
    backend.provider_name = "mock"
    return backend


def backend_label(backend: EmailBackend) -> str:
    """Return a short provider label for connector warnings and health checks."""
    return getattr(backend, "provider_name", "mock")
