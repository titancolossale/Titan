# =====================================
# Titan Obsidian Tool
# =====================================

"""Production Obsidian integration — bounded vault read/write for Titan tools."""

from __future__ import annotations

import logging
from pathlib import Path

from core.actions.action import Action
from core.actions.action_registry import ActionRegistry
from core.actions.action_result import ActionResult
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.tools.base_tool import BaseTool
from core.tools.obsidian.exceptions import (
    ObsidianConfigurationError,
    ObsidianNotConnectedError,
    ObsidianPermissionDeniedError,
)
from core.tools.obsidian.obsidian_client import ObsidianClient
from core.tools.obsidian.obsidian_config import ObsidianConfig
from core.tools.obsidian.vault_helpers import EditMode

logger = logging.getLogger(__name__)

PERMISSION_READ_NOTE = "obsidian.read_note"
PERMISSION_LIST_NOTES = "obsidian.list_notes"
PERMISSION_LIST_FOLDERS = "obsidian.list_folders"
PERMISSION_CREATE_NOTE = "obsidian.create_note"
PERMISSION_EDIT_NOTE = "obsidian.edit_note"
PERMISSION_DELETE_NOTE = "obsidian.delete_note"
PERMISSION_MANAGE_FOLDERS = "obsidian.manage_folders"
PERMISSION_DELETE_FOLDER = "obsidian.delete_folder"

CAPABILITY_READ_NOTES = "read_notes"
CAPABILITY_LIST_NOTES = "list_notes"
CAPABILITY_LIST_FOLDERS = "list_folders"
CAPABILITY_METADATA = "metadata"
CAPABILITY_CREATE_NOTE = "create_note"
CAPABILITY_EDIT_NOTE = "edit_note"
CAPABILITY_APPEND_NOTE = "append_note"
CAPABILITY_REPLACE_NOTE = "replace_note"
CAPABILITY_DELETE_NOTE = "delete_note"
CAPABILITY_RENAME_NOTE = "rename_note"
CAPABILITY_MOVE_NOTE = "move_note"
CAPABILITY_CREATE_FOLDER = "create_folder"
CAPABILITY_DELETE_FOLDER = "delete_folder"

_CAPABILITY_PERMISSIONS: dict[str, str] = {
    CAPABILITY_READ_NOTES: PERMISSION_READ_NOTE,
    CAPABILITY_LIST_NOTES: PERMISSION_LIST_NOTES,
    CAPABILITY_LIST_FOLDERS: PERMISSION_LIST_FOLDERS,
    CAPABILITY_METADATA: PERMISSION_READ_NOTE,
    CAPABILITY_CREATE_NOTE: PERMISSION_CREATE_NOTE,
    CAPABILITY_EDIT_NOTE: PERMISSION_EDIT_NOTE,
    CAPABILITY_APPEND_NOTE: PERMISSION_EDIT_NOTE,
    CAPABILITY_REPLACE_NOTE: PERMISSION_EDIT_NOTE,
    CAPABILITY_DELETE_NOTE: PERMISSION_DELETE_NOTE,
    CAPABILITY_RENAME_NOTE: PERMISSION_EDIT_NOTE,
    CAPABILITY_MOVE_NOTE: PERMISSION_EDIT_NOTE,
    CAPABILITY_CREATE_FOLDER: PERMISSION_MANAGE_FOLDERS,
    CAPABILITY_DELETE_FOLDER: PERMISSION_DELETE_FOLDER,
}

_ACTION_CAPABILITY_MAP: dict[str, str] = {
    "read_note": CAPABILITY_READ_NOTES,
    "read_notes": CAPABILITY_READ_NOTES,
    "list_notes": CAPABILITY_LIST_NOTES,
    "list_files": CAPABILITY_LIST_NOTES,
    "list_folders": CAPABILITY_LIST_FOLDERS,
    "metadata": CAPABILITY_METADATA,
    "get_note_metadata": CAPABILITY_METADATA,
    "note_exists": CAPABILITY_READ_NOTES,
    "create_note": CAPABILITY_CREATE_NOTE,
    "edit_note": CAPABILITY_EDIT_NOTE,
    "append_note": CAPABILITY_APPEND_NOTE,
    "replace_note": CAPABILITY_REPLACE_NOTE,
    "delete_note": CAPABILITY_DELETE_NOTE,
    "rename_note": CAPABILITY_RENAME_NOTE,
    "move_note": CAPABILITY_MOVE_NOTE,
    "create_folder": CAPABILITY_CREATE_FOLDER,
    "delete_folder": CAPABILITY_DELETE_FOLDER,
}

_ACTION_ALIASES: dict[str, str] = {
    "read_notes": "read_note",
    "list_files": "list_notes",
    "get_note_metadata": "metadata",
}

_DEFAULT_PERMISSIONS: tuple[Permission, ...] = (
    Permission(
        id=PERMISSION_READ_NOTE,
        name="Read Obsidian Note",
        description="Read note content and metadata from the user's vault.",
        level=PermissionLevel.SAFE,
    ),
    Permission(
        id=PERMISSION_LIST_NOTES,
        name="List Obsidian Notes",
        description="List readable notes in the user's vault.",
        level=PermissionLevel.SAFE,
    ),
    Permission(
        id=PERMISSION_LIST_FOLDERS,
        name="List Obsidian Folders",
        description="List folders in the user's vault.",
        level=PermissionLevel.SAFE,
    ),
    Permission(
        id=PERMISSION_CREATE_NOTE,
        name="Create Obsidian Note",
        description="Create a new note in the user's vault.",
        level=PermissionLevel.CONFIRMATION_REQUIRED,
    ),
    Permission(
        id=PERMISSION_EDIT_NOTE,
        name="Edit Obsidian Note",
        description="Modify, append, replace, rename, or move notes in the vault.",
        level=PermissionLevel.CONFIRMATION_REQUIRED,
    ),
    Permission(
        id=PERMISSION_DELETE_NOTE,
        name="Delete Obsidian Note",
        description="Delete a note from the user's vault.",
        level=PermissionLevel.BLOCKED,
    ),
    Permission(
        id=PERMISSION_MANAGE_FOLDERS,
        name="Manage Obsidian Folders",
        description="Create folders inside the user's vault.",
        level=PermissionLevel.CONFIRMATION_REQUIRED,
    ),
    Permission(
        id=PERMISSION_DELETE_FOLDER,
        name="Delete Obsidian Folder",
        description="Delete an empty folder from the user's vault.",
        level=PermissionLevel.BLOCKED,
    ),
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SAMPLE_VAULT_PATH = _PROJECT_ROOT / "sample_vault"

_PATH_PARAMETER = {
    "path": {
        "type": "string",
        "required": False,
        "description": "Vault-relative note or folder path.",
    },
    "relative_path": {
        "type": "string",
        "required": False,
        "description": "Alias for path.",
    },
}


def _build_obsidian_actions(tool_id: str) -> tuple[Action, ...]:
    """Return the canonical Obsidian actions registered in the action framework."""
    return (
        Action(
            id="read_note",
            name="Read Note",
            description="Read note content from the configured vault.",
            tool_id=tool_id,
            permission_id=PERMISSION_READ_NOTE,
            parameters=_PATH_PARAMETER,
            metadata={"capability": CAPABILITY_READ_NOTES},
        ),
        Action(
            id="list_notes",
            name="List Notes",
            description="List readable markdown notes in the vault.",
            tool_id=tool_id,
            permission_id=PERMISSION_LIST_NOTES,
            parameters={},
            metadata={"capability": CAPABILITY_LIST_NOTES},
        ),
        Action(
            id="list_folders",
            name="List Folders",
            description="List folders in the vault.",
            tool_id=tool_id,
            permission_id=PERMISSION_LIST_FOLDERS,
            parameters={},
            metadata={"capability": CAPABILITY_LIST_FOLDERS},
        ),
        Action(
            id="metadata",
            name="Note Metadata",
            description="Return filesystem metadata for a vault note.",
            tool_id=tool_id,
            permission_id=PERMISSION_READ_NOTE,
            parameters=_PATH_PARAMETER,
            metadata={"capability": CAPABILITY_METADATA},
        ),
        Action(
            id="create_note",
            name="Create Note",
            description="Create a new markdown note in the vault.",
            tool_id=tool_id,
            permission_id=PERMISSION_CREATE_NOTE,
            parameters={
                **_PATH_PARAMETER,
                "content": {
                    "type": "string",
                    "required": False,
                    "description": "Initial note body.",
                },
            },
            metadata={"capability": CAPABILITY_CREATE_NOTE},
        ),
        Action(
            id="edit_note",
            name="Edit Note",
            description="Overwrite an existing note with new content.",
            tool_id=tool_id,
            permission_id=PERMISSION_EDIT_NOTE,
            parameters={
                **_PATH_PARAMETER,
                "content": {
                    "type": "string",
                    "required": True,
                    "description": "Replacement note body.",
                },
                "mode": {
                    "type": "string",
                    "required": False,
                    "description": "Edit mode: overwrite (default).",
                },
            },
            metadata={"capability": CAPABILITY_EDIT_NOTE},
        ),
        Action(
            id="append_note",
            name="Append Note",
            description="Append content to an existing note.",
            tool_id=tool_id,
            permission_id=PERMISSION_EDIT_NOTE,
            parameters={
                **_PATH_PARAMETER,
                "content": {
                    "type": "string",
                    "required": True,
                    "description": "Content to append.",
                },
            },
            metadata={"capability": CAPABILITY_APPEND_NOTE},
        ),
        Action(
            id="replace_note",
            name="Replace Note Text",
            description="Replace the first occurrence of selected text in a note.",
            tool_id=tool_id,
            permission_id=PERMISSION_EDIT_NOTE,
            parameters={
                **_PATH_PARAMETER,
                "search": {
                    "type": "string",
                    "required": True,
                    "description": "Text to find in the note body.",
                },
                "replacement": {
                    "type": "string",
                    "required": False,
                    "description": "Replacement text.",
                },
                "content": {
                    "type": "string",
                    "required": False,
                    "description": "Alias for replacement.",
                },
            },
            metadata={"capability": CAPABILITY_REPLACE_NOTE},
        ),
        Action(
            id="delete_note",
            name="Delete Note",
            description="Delete a note after creating a timestamped backup.",
            tool_id=tool_id,
            permission_id=PERMISSION_DELETE_NOTE,
            parameters=_PATH_PARAMETER,
            metadata={"capability": CAPABILITY_DELETE_NOTE},
        ),
        Action(
            id="rename_note",
            name="Rename Note",
            description="Rename a note within the vault after creating a backup.",
            tool_id=tool_id,
            permission_id=PERMISSION_EDIT_NOTE,
            parameters={
                **_PATH_PARAMETER,
                "new_path": {
                    "type": "string",
                    "required": False,
                    "description": "Destination note path.",
                },
                "destination": {
                    "type": "string",
                    "required": False,
                    "description": "Alias for new_path.",
                },
            },
            metadata={"capability": CAPABILITY_RENAME_NOTE},
        ),
        Action(
            id="move_note",
            name="Move Note",
            description="Move a note into another vault folder after creating a backup.",
            tool_id=tool_id,
            permission_id=PERMISSION_EDIT_NOTE,
            parameters={
                **_PATH_PARAMETER,
                "folder": {
                    "type": "string",
                    "required": False,
                    "description": "Destination folder path.",
                },
                "destination": {
                    "type": "string",
                    "required": False,
                    "description": "Alias for folder.",
                },
            },
            metadata={"capability": CAPABILITY_MOVE_NOTE},
        ),
        Action(
            id="create_folder",
            name="Create Folder",
            description="Create a folder inside the vault.",
            tool_id=tool_id,
            permission_id=PERMISSION_MANAGE_FOLDERS,
            parameters={
                "folder": {
                    "type": "string",
                    "required": False,
                    "description": "Vault-relative folder path.",
                },
                "path": {
                    "type": "string",
                    "required": False,
                    "description": "Alias for folder.",
                },
            },
            metadata={"capability": CAPABILITY_CREATE_FOLDER},
        ),
        Action(
            id="delete_folder",
            name="Delete Folder",
            description="Delete an empty folder after creating a backup.",
            tool_id=tool_id,
            permission_id=PERMISSION_DELETE_FOLDER,
            parameters={
                "folder": {
                    "type": "string",
                    "required": False,
                    "description": "Vault-relative folder path.",
                },
                "path": {
                    "type": "string",
                    "required": False,
                    "description": "Alias for folder.",
                },
            },
            metadata={"capability": CAPABILITY_DELETE_FOLDER},
        ),
    )


class ObsidianTool(BaseTool):
    """Obsidian vault tool backed by the core permission and action systems.

    Obsidian is an external note space — not Titan memory. This tool performs
    bounded read and write operations through the action layer.
    """

    def __init__(
        self,
        config: ObsidianConfig | None = None,
        client: ObsidianClient | None = None,
        permission_manager: PermissionManager | None = None,
        action_registry: ActionRegistry | None = None,
        *,
        auto_connect: bool = False,
    ) -> None:
        super().__init__()
        self._permission_manager = permission_manager or PermissionManager()
        self._register_default_permissions()

        if config is None:
            config = ObsidianConfig.for_vault(_SAMPLE_VAULT_PATH)

        self._client = client or ObsidianClient(config)
        self._actions = _build_obsidian_actions(self.id)

        if action_registry is not None:
            self._register_actions(action_registry)

        if auto_connect:
            self.connect()

    @property
    def id(self) -> str:
        return "obsidian"

    @property
    def name(self) -> str:
        return "Obsidian"

    @property
    def description(self) -> str:
        return (
            "Bounded read/write access to the user's existing Obsidian vault. "
            "Obsidian is external personal notes — not Titan memory."
        )

    @property
    def version(self) -> str:
        return "1.1.0"

    @property
    def category(self) -> str:
        return "notes"

    @property
    def requires_confirmation(self) -> bool:
        return True

    @property
    def capabilities(self) -> list[str]:
        return list(_CAPABILITY_PERMISSIONS.keys())

    @property
    def client(self) -> ObsidianClient:
        """Return the underlying vault client."""
        return self._client

    @property
    def permission_manager(self) -> PermissionManager:
        """Return the permission manager used by this tool."""
        return self._permission_manager

    def list_actions(self) -> list[Action]:
        """Return the Obsidian actions exposed by this tool."""
        return list(self._actions)

    def connect(self) -> None:
        """Connect the underlying client to the configured vault."""
        self._client.connect()

    def disconnect(self) -> None:
        """Disconnect the underlying vault client."""
        self._client.disconnect()

    def is_connected(self) -> bool:
        """Return True when the vault client is connected."""
        return self._client.is_connected()

    def execute_action(self, action_id: str, **kwargs: object) -> ActionResult:
        """Execute a registered Obsidian action without performing permission checks.

        Permission verification is owned by ``ActionDispatcher``. Connection and
        parameter validation remain tool responsibilities.
        """
        normalized = _ACTION_ALIASES.get(action_id, action_id)
        registered_ids = {action.id for action in self._actions}

        if normalized not in registered_ids:
            message = f"Unsupported Obsidian action: {action_id}"
            logger.warning(message)
            return ActionResult(
                success=False,
                message=message,
                errors=[message],
                metadata={"action_id": action_id},
            )

        if not self.is_connected():
            message = "Obsidian client is not connected to a vault."
            logger.warning("Obsidian action blocked: %s", message)
            return ActionResult(
                success=False,
                message=message,
                errors=[message],
                metadata={"action_id": normalized},
            )

        try:
            data = self._dispatch_action(normalized, kwargs)
        except Exception as exc:
            message = str(exc)
            logger.exception(
                "Obsidian action failed: action=%s error=%s",
                normalized,
                message,
            )
            return ActionResult(
                success=False,
                message=message,
                errors=[message],
                metadata={"action_id": normalized},
            )

        logger.info("Obsidian action completed: action=%s", normalized)
        return ActionResult(
            success=True,
            data=data,
            message=f"Obsidian action '{normalized}' completed successfully.",
            metadata={"action_id": normalized},
        )

    def execute(self, **kwargs: object) -> object:
        """Dispatch an Obsidian action after permission checks.

        Legacy callers pass ``action`` in kwargs. Registered actions delegate to
        ``execute_action`` after authorization; legacy-only actions remain here.
        """
        action = str(kwargs.get("action", "")).strip().lower()
        if not action:
            raise ObsidianConfigurationError("Missing required parameter: action")

        capability = _ACTION_CAPABILITY_MAP.get(action)
        if capability is None:
            raise ObsidianConfigurationError(f"Unsupported Obsidian action: {action}")

        self._require_permission(capability)

        if action == "note_exists":
            if not self.is_connected():
                raise ObsidianNotConnectedError()
            relative_path = kwargs.get("relative_path", kwargs.get("path", ""))
            exists = self._client.note_exists(str(relative_path))
            return {
                "action": action,
                "relative_path": self._client.normalize_relative_path(str(relative_path)),
                "exists": exists,
            }

        result = self.execute_action(action, **kwargs)
        if not result.success:
            self._raise_for_failed_action(action, result)

        return result.data

    def _dispatch_action(self, action_id: str, kwargs: dict[str, object]) -> dict[str, object]:
        relative_path = str(kwargs.get("relative_path", kwargs.get("path", "")))

        if action_id == "read_note":
            note = self._client.read_note(relative_path)
            return {"action": action_id, "note": note.to_dict()}

        if action_id == "list_notes":
            files = self._client.list_files()
            return {"action": action_id, "files": files, "count": len(files)}

        if action_id == "list_folders":
            folders = self._client.list_folders()
            return {"action": action_id, "folders": folders, "count": len(folders)}

        if action_id == "metadata":
            metadata = self._client.get_note_metadata(relative_path)
            return {"action": action_id, "metadata": metadata.to_dict()}

        if action_id == "create_note":
            content = str(kwargs.get("content", ""))
            note = self._client.create_note(relative_path, content)
            return {"action": action_id, "note": note.to_dict(), "created": True}

        if action_id == "edit_note":
            content = str(kwargs.get("content", ""))
            mode = str(kwargs.get("mode", EditMode.OVERWRITE.value))
            note = self._client.edit_note(relative_path, content, mode=mode)
            return {"action": action_id, "note": note.to_dict(), "mode": mode}

        if action_id == "append_note":
            content = str(kwargs.get("content", ""))
            note = self._client.append_note(relative_path, content)
            return {"action": action_id, "note": note.to_dict()}

        if action_id == "replace_note":
            search = str(kwargs.get("search", ""))
            replacement = str(kwargs.get("replacement", kwargs.get("content", "")))
            note = self._client.replace_note(
                relative_path,
                search=search,
                replacement=replacement,
            )
            return {
                "action": action_id,
                "note": note.to_dict(),
                "search": search,
                "replacement": replacement,
            }

        if action_id == "delete_note":
            result = self._client.delete_note(relative_path)
            return {"action": action_id, **result}

        if action_id == "rename_note":
            new_path = str(kwargs.get("new_path", kwargs.get("destination", "")))
            result = self._client.rename_note(relative_path, new_path)
            return {"action": action_id, **result}

        if action_id == "move_note":
            folder = str(kwargs.get("folder", kwargs.get("destination", "")))
            result = self._client.move_note(relative_path, folder)
            return {"action": action_id, **result}

        if action_id == "create_folder":
            folder = str(kwargs.get("folder", kwargs.get("path", "")))
            result = self._client.create_folder(folder)
            return {"action": action_id, **result}

        if action_id == "delete_folder":
            folder = str(kwargs.get("folder", kwargs.get("path", "")))
            result = self._client.delete_folder(folder)
            return {"action": action_id, **result}

        raise ObsidianConfigurationError(f"Unsupported Obsidian action: {action_id}")

    def _register_actions(self, registry: ActionRegistry) -> None:
        for action in self._actions:
            if registry.action_exists(action.tool_id, action.id):
                continue
            registry.register_action(action)

    def _register_default_permissions(self) -> None:
        for permission in _DEFAULT_PERMISSIONS:
            if self._permission_manager.permission_exists(permission.id):
                continue
            self._permission_manager.register_permission(permission)
            logger.info("Registered Obsidian permission: %s", permission.id)

    def _require_permission(self, capability: str) -> None:
        permission_id = _CAPABILITY_PERMISSIONS[capability]
        result = self._permission_manager.check_permission(permission_id)
        if not result.allowed:
            logger.warning(
                "Obsidian permission denied: capability=%s permission=%s reason=%s",
                capability,
                permission_id,
                result.reason,
            )
            raise ObsidianPermissionDeniedError(permission_id, result.reason)

    @staticmethod
    def _raise_for_failed_action(action: str, result: ActionResult) -> None:
        if "not connected" in result.message.lower():
            raise ObsidianNotConnectedError()
        if "permission" in result.message.lower():
            permission_id = str(result.metadata.get("permission_id", "unknown"))
            raise ObsidianPermissionDeniedError(permission_id, result.message)
        raise ObsidianConfigurationError(result.message or f"Obsidian action failed: {action}")
