# =====================================
# Titan Tool Decision — Intent Types
# =====================================

"""User intent categories for the Tool Decision Engine (Phase 10B — P10B-001)."""

from __future__ import annotations

from enum import Enum


class Intent(str, Enum):
    """Canonical intent labels consumed by tool ranking and fallback logic."""

    GENERAL_CHAT = "general_chat"
    CODING = "coding"
    WEB_SEARCH = "web_search"
    MEMORY = "memory"
    FILE = "file"
    FILE_LIST = "file_list"
    FILE_SEARCH = "file_search"
    FILE_READ = "file_read"
    FILE_METADATA = "file_metadata"
    DOCUMENT = "document"
    TRADING = "trading"
    CALENDAR = "calendar"
    EMAIL = "email"
    GITHUB = "github"
    OBSIDIAN = "obsidian"
    BROWSER = "browser"
    SYSTEM = "system"
    WORKSPACE_EXPLAIN = "workspace_explain"
    WORKSPACE_MODIFY = "workspace_modify"
    UNKNOWN = "unknown"
