# =====================================
# Titan Providers Package
# =====================================

"""Provider layer for external tool backends (Phase 10A — Batch 5)."""

from tools.providers.base_provider import BaseProvider
from tools.providers.brave_search_provider import BraveSearchProvider
from tools.providers.calendar_provider import (
    CalendarProvider,
    CalendarResponse,
    StubCalendarProvider,
)
from tools.providers.credential_manager import (
    CredentialManager,
    CredentialRequirement,
    CredentialStatus,
    CredentialType,
    CredentialValidationResult,
)
from tools.providers.defaults import register_default_providers
from tools.providers.github_provider import GitHubProvider, GitHubResponse, LiveGitHubProvider
from tools.providers.provider_configuration import (
    ProviderConfiguration,
    ProviderConfigurationStore,
)
from tools.providers.provider_context import ProviderContext
from tools.providers.provider_dashboard import ProviderDashboardSnapshot, build_dashboard_snapshot
from tools.providers.provider_fallback_policy import (
    FallbackDecision,
    FallbackEvaluationContext,
    FallbackPolicyOutcome,
    ProviderFallbackPolicy,
    ProviderFallbackPolicyConfig,
    format_fallback_user_notice,
)
from tools.providers.provider_executor import (
    ProviderExecutor,
    ProviderExecutionContext,
    ProviderExecutionResult,
    provider_outcome_metadata,
)
from tools.providers.provider_metadata import ProviderMetadata
from tools.providers.provider_performance_model import (
    ProviderPerformanceMetrics,
    ProviderPerformanceModel,
    ProviderPerformanceSnapshot,
    ProviderPerformanceWeights,
)
from tools.providers.provider_registry import ProviderRegistry
from tools.providers.provider_telemetry import (
    ProviderExecutionRecord,
    ProviderHealthTransition,
    ProviderTelemetryCollector,
    ProviderTelemetrySnapshot,
    ProviderUsageStats,
)
from tools.providers.telemetry_persistence import (
    TelemetryPersistenceManager,
    TelemetryRetentionPolicy,
    parse_retention_policy,
)
from tools.providers.web_search_provider import (
    FallbackWebSearchProvider,
    FailingWebSearchProvider,
    SearchResponse,
    SearchResult,
    StubWebSearchProvider,
    WebSearchProvider,
)

__all__ = [
    "BaseProvider",
    "BraveSearchProvider",
    "CalendarProvider",
    "CalendarResponse",
    "CredentialManager",
    "CredentialRequirement",
    "CredentialStatus",
    "CredentialType",
    "CredentialValidationResult",
    "FallbackWebSearchProvider",
    "FailingWebSearchProvider",
    "GitHubProvider",
    "GitHubResponse",
    "LiveGitHubProvider",
    "ProviderConfiguration",
    "ProviderConfigurationStore",
    "ProviderContext",
    "ProviderDashboardSnapshot",
    "FallbackDecision",
    "FallbackEvaluationContext",
    "FallbackPolicyOutcome",
    "ProviderFallbackPolicy",
    "ProviderFallbackPolicyConfig",
    "format_fallback_user_notice",
    "ProviderExecutionContext",
    "ProviderExecutionRecord",
    "ProviderExecutionResult",
    "ProviderExecutor",
    "ProviderHealthTransition",
    "provider_outcome_metadata",
    "ProviderMetadata",
    "ProviderPerformanceMetrics",
    "ProviderPerformanceModel",
    "ProviderPerformanceSnapshot",
    "ProviderPerformanceWeights",
    "ProviderRegistry",
    "ProviderTelemetryCollector",
    "ProviderTelemetrySnapshot",
    "ProviderUsageStats",
    "TelemetryPersistenceManager",
    "TelemetryRetentionPolicy",
    "parse_retention_policy",
    "SearchResponse",
    "SearchResult",
    "StubCalendarProvider",
    "StubWebSearchProvider",
    "WebSearchProvider",
    "build_dashboard_snapshot",
    "register_default_providers",
]
