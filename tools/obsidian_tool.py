# =====================================
# Titan Obsidian Tool
# =====================================

"""Obsidian vault tool — external connector to the user's existing vault (Phase 22.0)."""

from __future__ import annotations

from pathlib import Path

from config.settings import TITAN_OBSIDIAN_ENABLED, TITAN_OBSIDIAN_VAULT_PATH
from tools.base_tool import BaseTool, ToolParameter, ToolSchema
from tools.connectors.obsidian_connector import ObsidianConnector
from tools.tool_result import ToolResult

_SUPPORTED_ACTIONS = frozenset({
    "read_note",
    "create_note",
    "update_note",
    "patch_note",
    "delete_note",
    "rename_note",
    "move_note",
    "create_folder",
    "list_notes",
    "list_folders",
    "search_notes",
    "get_backlinks",
    "get_outlinks",
    "read_frontmatter",
    "update_frontmatter",
    "list_tags",
    "vault_health",
})


_OBSIDIAN_TOOL_DESCRIPTION = (
    "Accède au vault Obsidian personnel existant de l'utilisateur (ex. « Titan AI »), "
    "configuré via TITAN_OBSIDIAN_VAULT_PATH. "
    "Obsidian n'est pas la mémoire ni le cerveau de Titan — c'est un espace de notes "
    "externe que Titan peut lire et maintenir intelligemment. "
    "Ne jamais créer un nouveau vault. "
    "Préférer search_notes, list_notes, read_note, get_backlinks, read_frontmatter, "
    "patch_note et update_note pour préserver le formatage. "
    "rename_note et move_note pour réorganiser ; delete_note avec prudence. "
    "vault_health pour un rapport de santé (recommandations uniquement). "
    "Toujours rechercher une note existante avant d'en créer une nouvelle."
)


class ObsidianTool(BaseTool):
    """Read and maintain markdown notes in the user's existing Obsidian vault."""

    def __init__(
        self,
        *,
        vault_path: Path | str | None = None,
        enabled: bool | None = None,
        connector: ObsidianConnector | None = None,
    ) -> None:
        configured_path = vault_path if vault_path is not None else TITAN_OBSIDIAN_VAULT_PATH
        resolved_path = Path(configured_path).expanduser() if configured_path else None
        is_enabled = TITAN_OBSIDIAN_ENABLED if enabled is None else enabled
        self._connector = connector or ObsidianConnector(
            resolved_path,
            enabled=is_enabled,
        )

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="obsidian",
            description=_OBSIDIAN_TOOL_DESCRIPTION,
            parameters=[
                ToolParameter(
                    name="action",
                    param_type="string",
                    description=(
                        "Action vault : search_notes, list_notes, list_folders, read_note, "
                        "get_backlinks, get_outlinks, read_frontmatter, list_tags, vault_health ; "
                        "patch_note pour mises à jour intelligentes ; update_note pour remplacement ; "
                        "create_note / rename_note / move_note / delete_note si nécessaire."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="path",
                    param_type="string",
                    description="Chemin relatif de la note dans le vault (.md ajouté si absent).",
                    required=False,
                ),
                ToolParameter(
                    name="new_path",
                    param_type="string",
                    description="Nouveau chemin relatif pour rename_note.",
                    required=False,
                ),
                ToolParameter(
                    name="destination",
                    param_type="string",
                    description="Dossier ou chemin cible pour move_note ou rename_note.",
                    required=False,
                ),
                ToolParameter(
                    name="content",
                    param_type="string",
                    description="Contenu markdown pour create_note, update_note ou patch_note.",
                    required=False,
                ),
                ToolParameter(
                    name="update_mode",
                    param_type="string",
                    description=(
                        "Mode patch_note / update_note : replace, append, prepend, "
                        "insert_under_heading, replace_section, update_checklist, update_table."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="heading",
                    param_type="string",
                    description="Titre de section pour insert_under_heading, replace_section, update_checklist/table.",
                    required=False,
                ),
                ToolParameter(
                    name="checklist_item",
                    param_type="string",
                    description="Texte de l'élément checklist pour update_checklist.",
                    required=False,
                ),
                ToolParameter(
                    name="checked",
                    param_type="boolean",
                    description="État coché pour update_checklist.",
                    required=False,
                ),
                ToolParameter(
                    name="table_row",
                    param_type="integer",
                    description="Index de ligne (0-based, hors en-tête) pour update_table.",
                    required=False,
                ),
                ToolParameter(
                    name="table_col",
                    param_type="integer",
                    description="Index de colonne pour update_table.",
                    required=False,
                ),
                ToolParameter(
                    name="cell_value",
                    param_type="string",
                    description="Nouvelle valeur de cellule pour update_table.",
                    required=False,
                ),
                ToolParameter(
                    name="table_index",
                    param_type="integer",
                    description="Index de table dans la note (0 par défaut).",
                    required=False,
                    default=0,
                ),
                ToolParameter(
                    name="frontmatter",
                    param_type="object",
                    description="Paires clé/valeur YAML pour update_frontmatter.",
                    required=False,
                ),
                ToolParameter(
                    name="folder",
                    param_type="string",
                    description="Dossier cible pour list_notes, list_folders, move_note ou create_folder.",
                    required=False,
                ),
                ToolParameter(
                    name="recursive",
                    param_type="boolean",
                    description="Lister récursivement notes ou dossiers.",
                    required=False,
                    default=False,
                ),
                ToolParameter(
                    name="mode",
                    param_type="string",
                    description=(
                        "Mode search_notes : filename, keyword, tag ou folder."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="query",
                    param_type="string",
                    description="Terme de recherche pour search_notes ou get_backlinks.",
                    required=False,
                ),
            ],
        )

    def run(self, **params: object) -> ToolResult:
        action = str(params.get("action", "")).strip()
        if not action:
            return self._result(success=False, error="Paramètre action requis.")
        if action not in _SUPPORTED_ACTIONS:
            return self._result(
                success=False,
                error=f"Action non supportée : {action!r}",
            )

        exec_params = {
            key: value
            for key, value in params.items()
            if not str(key).startswith("_")
        }
        outcome = self._connector.execute(action, exec_params)
        metadata = {
            "connector": self._connector.connector_id,
            "action": action,
            "target_path": outcome.target_path,
            "vault_configured": self._connector.is_configured,
        }
        return ToolResult(
            tool_name=self.name,
            success=outcome.success,
            data=outcome.format_for_tool(),
            error=outcome.error if not outcome.success else "",
            source="obsidian",
            metadata=metadata,
        )

    # Future-ready facade API (Phase 22.0) — stable entry points for orchestration layers.

    def read(self, path: str) -> ToolResult:
        """Read a note by vault-relative path."""
        return self.run(action="read_note", path=path)

    def write(
        self,
        path: str,
        content: str,
        *,
        mode: str = "replace",
    ) -> ToolResult:
        """Write or patch note content while preserving formatting when possible."""
        if mode == "replace":
            return self.run(action="update_note", path=path, content=content)
        return self.run(
            action="patch_note",
            path=path,
            content=content,
            update_mode=mode,
        )

    def create(self, path: str, content: str = "") -> ToolResult:
        """Create a new note in the vault."""
        return self.run(action="create_note", path=path, content=content)

    def delete(self, path: str) -> ToolResult:
        """Delete a note from the vault."""
        return self.run(action="delete_note", path=path)

    def move(self, path: str, folder: str) -> ToolResult:
        """Move a note to another folder."""
        return self.run(action="move_note", path=path, folder=folder)

    def search(
        self,
        query: str,
        *,
        mode: str = "keyword",
        folder: str = "",
    ) -> ToolResult:
        """Search the vault by filename, keyword, tag, or folder."""
        return self.run(action="search_notes", mode=mode, query=query, folder=folder)

    def list_folders(self, folder: str = "", *, recursive: bool = False) -> ToolResult:
        """List folders in the vault."""
        return self.run(action="list_folders", folder=folder, recursive=recursive)

    def list_notes(self, folder: str = "", *, recursive: bool = False) -> ToolResult:
        """List markdown notes in the vault."""
        return self.run(action="list_notes", folder=folder, recursive=recursive)
