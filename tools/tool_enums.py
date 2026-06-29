# =====================================
# Titan Tool Enums
# =====================================

"""Shared enumerations for the tool runtime (Phase 10A — P10A-003)."""

from __future__ import annotations

from enum import Enum


class ToolHealthState(str, Enum):
    """Operational readiness of a tool or provider."""

    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class InvocationMode(str, Enum):
    """How a tool invocation is delivered to the runtime."""

    SYNC = "sync"
    ASYNC = "async"
    STREAM = "stream"
    BACKGROUND = "background"


class ExecutionMode(str, Enum):
    """Side-effect envelope for tool and provider execution."""

    LIVE = "live"
    PAPER = "paper"
    SIMULATION = "simulation"
    MOCK = "mock"


class RiskLevel(str, Enum):
    """Risk classification driving permission and confirmation defaults."""

    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
