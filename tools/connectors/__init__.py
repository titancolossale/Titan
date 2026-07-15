# =====================================
# Titan External Tool Connectors
# =====================================

"""Reusable connector pattern for user-owned external systems (Phase 12.5)."""

from tools.connectors.base_connector import BaseExternalConnector, ConnectorResult
from tools.connectors.markdown_editor import MarkdownEditError, NoteUpdateMode, apply_note_update
from tools.connectors.markdown_parser import parse_markdown
from tools.connectors.obsidian_connector import ObsidianConnector
from tools.connectors.vault_analyzer import VaultAnalyzer, VaultHealthReport
from tools.connectors.vault_path_guard import VaultPathGuardError, resolve_vault_path

__all__ = [
    "BaseExternalConnector",
    "ConnectorResult",
    "MarkdownEditError",
    "NoteUpdateMode",
    "ObsidianConnector",
    "VaultAnalyzer",
    "VaultHealthReport",
    "VaultPathGuardError",
    "apply_note_update",
    "parse_markdown",
    "resolve_vault_path",
]
