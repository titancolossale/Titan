# =====================================
# Titan Voice Streaming Transport
# =====================================

"""Generic streaming transports for provider-level realtime voice (Phase 20.6)."""

from voice.transport.base import (
    TransportConfig,
    TransportEvent,
    TransportKind,
    TransportMessage,
    TransportState,
    StreamingTransport,
)
from voice.transport.browser_hub import (
    BrowserConnectionState,
    BrowserHubConfig,
    BrowserVoiceHub,
    get_browser_voice_hub,
    reset_browser_voice_hub_for_tests,
)
from voice.transport.browser_protocol import (
    BrowserBackpressureState,
    BrowserFrame,
    BrowserFrameType,
    BrowserReconnectPolicy,
    BrowserStreamSync,
)
from voice.transport.http_fallback import HttpFallbackTransport
from voice.transport.manager import TransportManager, TransportManagerConfig
from voice.transport.memory import InMemoryTransport
from voice.transport.reconnect import ReconnectPolicy, compute_backoff_seconds
from voice.transport.socket_backends import (
    SyncWebSocketBackend,
    create_live_socket_factory,
    prefer_live_transport,
    websocket_client_available,
)
from voice.transport.sse_transport import ServerSentEventsTransport
from voice.transport.websocket_transport import WebSocketTransport

__all__ = [
    "BrowserBackpressureState",
    "BrowserConnectionState",
    "BrowserFrame",
    "BrowserFrameType",
    "BrowserHubConfig",
    "BrowserReconnectPolicy",
    "BrowserStreamSync",
    "BrowserVoiceHub",
    "HttpFallbackTransport",
    "InMemoryTransport",
    "ReconnectPolicy",
    "ServerSentEventsTransport",
    "StreamingTransport",
    "SyncWebSocketBackend",
    "TransportConfig",
    "TransportEvent",
    "TransportKind",
    "TransportManager",
    "TransportManagerConfig",
    "TransportMessage",
    "TransportState",
    "WebSocketTransport",
    "compute_backoff_seconds",
    "create_live_socket_factory",
    "get_browser_voice_hub",
    "prefer_live_transport",
    "reset_browser_voice_hub_for_tests",
    "websocket_client_available",
]
