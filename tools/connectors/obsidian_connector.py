# =====================================
# Titan Obsidian Connector
# =====================================

"""Obsidian vault connector — access the user's existing vault via TITAN_OBSIDIAN_VAULT_PATH.

Obsidian is the user's personal note space (e.g. vault « Titan AI »), not Titan memory.
Titan must never create a new vault; prefer list/read/update on existing notes.
"""

from __future__ import annotations

from pathlib import Path

from tools.connectors.base_connector import BaseExternalConnector, ConnectorResult
from tools.connectors.obsidian_validator import validate_obsidian_config
from tools.connectors.markdown_editor import (
    MarkdownEditError,
    NoteUpdateMode,
    SUPPORTED_UPDATE_MODES,
    apply_note_update,
)
from tools.connectors.markdown_parser import parse_markdown, split_frontmatter
from tools.connectors.vault_analyzer import VaultAnalyzer
from tools.connectors.vault_link_index import (
    build_backlink_index,
    collect_outlink_stems,
    collect_vault_tags,
    note_display_name,
    rewrite_wikilinks_after_rename,
    wikilink_target_stem,
)
from tools.connectors.vault_path_guard import (
    VaultPathGuardError,
    relative_vault_path,
    resolve_vault_path,
)

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

_SEARCH_MODES = frozenset({"filename", "keyword", "tag", "folder"})


class ObsidianConnector(BaseExternalConnector):
    """Operate on markdown notes inside the user's existing Obsidian vault."""

    @property
    def connector_id(self) -> str:
        return "obsidian"

    def configuration_error(self) -> str:
        """Return a French error when the existing user vault is not configured."""
        if not self._enabled:
            return validate_obsidian_config(enabled=False).message
        if self._vault_root is None:
            return validate_obsidian_config(enabled=True, vault_path="").message
        result = validate_obsidian_config(
            enabled=self._enabled,
            vault_path=self._vault_root,
        )
        return result.message

    def health_check(self) -> tuple[bool, str]:
        """Probe connector readiness without mutating external state."""
        if not self._enabled:
            result = validate_obsidian_config(enabled=False)
        elif self._vault_root is None:
            result = validate_obsidian_config(enabled=True, vault_path="")
        else:
            result = validate_obsidian_config(
                enabled=self._enabled,
                vault_path=self._vault_root,
            )
        if result.ok:
            return True, result.message
        return False, result.message

    def supported_actions(self) -> frozenset[str]:
        return _SUPPORTED_ACTIONS

    def _execute_action(self, action: str, params: dict) -> ConnectorResult:
        dispatch = {
            "read_note": self._read_note,
            "create_note": self._create_note,
            "update_note": self._update_note,
            "patch_note": self._patch_note,
            "delete_note": self._delete_note,
            "rename_note": self._rename_note,
            "move_note": self._move_note,
            "create_folder": self._create_folder,
            "list_notes": self._list_notes,
            "list_folders": self._list_folders,
            "search_notes": self._search_notes,
            "get_backlinks": self._get_backlinks,
            "get_outlinks": self._get_outlinks,
            "read_frontmatter": self._read_frontmatter,
            "update_frontmatter": self._update_frontmatter,
            "list_tags": self._list_tags,
            "vault_health": self._vault_health,
        }
        handler = dispatch[action]
        return handler(params)

    def _read_note(self, params: dict) -> ConnectorResult:
        path = str(params.get("path", "")).strip()
        try:
            resolved = self._resolve_note_path(path, must_exist=True, expect_file=True)
            content = resolved.read_text(encoding="utf-8")
        except VaultPathGuardError as exc:
            return self._error("read_note", str(exc))
        except OSError as exc:
            return self._error("read_note", f"Lecture impossible : {exc}")
        rel = relative_vault_path(resolved, self._vault_root)  # type: ignore[arg-type]
        return ConnectorResult(
            success=True,
            action="read_note",
            data=content,
            target_path=rel,
        )

    def _create_note(self, params: dict) -> ConnectorResult:
        path = str(params.get("path", "")).strip()
        content = str(params.get("content", ""))
        if not path:
            return self._error("create_note", "Chemin de note requis.")
        try:
            resolved = self._resolve_note_path(path, must_exist=False)
            if resolved.exists():
                return self._error(
                    "create_note",
                    f"La note existe déjà : {resolved.name}",
                )
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
        except VaultPathGuardError as exc:
            return self._error("create_note", str(exc))
        except OSError as exc:
            return self._error("create_note", f"Création impossible : {exc}")
        rel = relative_vault_path(resolved, self._vault_root)  # type: ignore[arg-type]
        return ConnectorResult(
            success=True,
            action="create_note",
            data=f"Note créée : {rel}",
            target_path=rel,
        )

    def _update_note(self, params: dict) -> ConnectorResult:
        path = str(params.get("path", "")).strip()
        content = str(params.get("content", ""))
        update_mode = str(params.get("update_mode", NoteUpdateMode.REPLACE.value)).strip().lower()
        if not path:
            return self._error("update_note", "Chemin de note requis.")
        if update_mode != NoteUpdateMode.REPLACE.value:
            patch_params = dict(params)
            patch_params["update_mode"] = update_mode
            patch_params["new_content"] = content
            return self._patch_note(patch_params)
        try:
            resolved = self._resolve_note_path(path, must_exist=True, expect_file=True)
            resolved.write_text(content, encoding="utf-8")
        except VaultPathGuardError as exc:
            return self._error("update_note", str(exc))
        except OSError as exc:
            return self._error("update_note", f"Mise à jour impossible : {exc}")
        rel = relative_vault_path(resolved, self._vault_root)  # type: ignore[arg-type]
        return ConnectorResult(
            success=True,
            action="update_note",
            data=f"Note mise à jour : {rel}",
            target_path=rel,
        )

    def _patch_note(self, params: dict) -> ConnectorResult:
        """Apply a formatting-preserving smart update (Phase 12.5 Batch 3 — P125-012)."""
        path = str(params.get("path", "")).strip()
        update_mode = str(
            params.get("update_mode", NoteUpdateMode.APPEND.value),
        ).strip().lower()
        if not path:
            return self._error("patch_note", "Chemin de note requis.")
        if update_mode not in SUPPORTED_UPDATE_MODES:
            return self._error(
                "patch_note",
                f"Mode non supporté : {update_mode!r}. "
                f"Modes : {', '.join(sorted(SUPPORTED_UPDATE_MODES))}.",
            )
        try:
            resolved = self._resolve_note_path(path, must_exist=True, expect_file=True)
            current = resolved.read_text(encoding="utf-8")
            updated = apply_note_update(
                current,
                update_mode,
                new_content=str(params.get("new_content", params.get("content", ""))),
                heading=str(params.get("heading", "")),
                checklist_item=str(params.get("checklist_item", "")),
                checked=params.get("checked") if "checked" in params else None,
                table_row=int(params.get("table_row", -1)),
                table_col=int(params.get("table_col", -1)),
                cell_value=str(params.get("cell_value", "")),
                table_index=int(params.get("table_index", 0)),
            )
            resolved.write_text(updated, encoding="utf-8")
        except MarkdownEditError as exc:
            return self._error("patch_note", str(exc))
        except VaultPathGuardError as exc:
            return self._error("patch_note", str(exc))
        except (OSError, ValueError) as exc:
            return self._error("patch_note", f"Mise à jour impossible : {exc}")
        rel = relative_vault_path(resolved, self._vault_root)  # type: ignore[arg-type]
        return ConnectorResult(
            success=True,
            action="patch_note",
            data=f"Note patchée ({update_mode}) : {rel}",
            target_path=rel,
        )

    def _vault_health(self, params: dict) -> ConnectorResult:
        """Return structured vault health report — recommendations only (P125-013)."""
        _ = params
        try:
            analyzer = VaultAnalyzer(self._vault_root)  # type: ignore[arg-type]
            report = analyzer.analyze()
        except OSError as exc:
            return self._error("vault_health", f"Analyse impossible : {exc}")
        return ConnectorResult(
            success=True,
            action="vault_health",
            data=report.format_summary(),
            target_path=".",
        )

    def vault_health_report(self) -> dict[str, object]:
        """Return structured health report dict for programmatic use."""
        if not self.is_configured:
            return {}
        analyzer = VaultAnalyzer(self._vault_root)  # type: ignore[arg-type]
        return analyzer.analyze().to_dict()

    def _delete_note(self, params: dict) -> ConnectorResult:
        path = str(params.get("path", "")).strip()
        if not path:
            return self._error("delete_note", "Chemin de note requis.")
        try:
            resolved = self._resolve_note_path(path, must_exist=True, expect_file=True)
            resolved.unlink()
        except VaultPathGuardError as exc:
            return self._error("delete_note", str(exc))
        except OSError as exc:
            return self._error("delete_note", f"Suppression impossible : {exc}")
        rel = relative_vault_path(resolved, self._vault_root)  # type: ignore[arg-type]
        return ConnectorResult(
            success=True,
            action="delete_note",
            data=f"Note supprimée : {rel}",
            target_path=rel,
        )

    def _create_folder(self, params: dict) -> ConnectorResult:
        folder = str(params.get("folder", params.get("path", ""))).strip()
        if not folder:
            return self._error("create_folder", "Chemin de dossier requis.")
        try:
            resolved = resolve_vault_path(folder, self._vault_root)  # type: ignore[arg-type]
            if resolved.exists() and not resolved.is_dir():
                return self._error(
                    "create_folder",
                    f"Un fichier existe déjà à cet emplacement : {resolved.name}",
                )
            resolved.mkdir(parents=True, exist_ok=True)
        except VaultPathGuardError as exc:
            return self._error("create_folder", str(exc))
        except OSError as exc:
            return self._error("create_folder", f"Création impossible : {exc}")
        rel = relative_vault_path(resolved, self._vault_root)  # type: ignore[arg-type]
        return ConnectorResult(
            success=True,
            action="create_folder",
            data=f"Dossier créé : {rel}",
            target_path=rel,
        )

    def note_exists(self, raw_path: str) -> bool:
        """Return True when a note path resolves to an existing file in the vault."""
        if not self.is_configured:
            return False
        try:
            self._resolve_note_path(raw_path, must_exist=True, expect_file=True)
            return True
        except (VaultPathGuardError, OSError):
            return False

    def find_notes(
        self,
        *,
        mode: str,
        query: str = "",
        folder: str = "",
    ) -> list[str]:
        """Return relative vault paths matching search criteria (P125-008)."""
        if not self.is_configured:
            return []
        normalized_mode = mode.strip().lower()
        if normalized_mode not in _SEARCH_MODES:
            return []
        try:
            base = self._search_base(folder)
            candidates = self._collect_notes(base, recursive=True)
        except (VaultPathGuardError, OSError):
            return []
        return self._filter_notes(candidates, normalized_mode, query.strip())

    def _search_notes(self, params: dict) -> ConnectorResult:
        mode = str(params.get("mode", "keyword")).strip().lower()
        query = str(params.get("query", "")).strip()
        folder = str(params.get("folder", "")).strip()
        if mode not in _SEARCH_MODES:
            return self._error(
                "search_notes",
                f"Mode de recherche non supporté : {mode!r}",
            )
        matches = self.find_notes(mode=mode, query=query, folder=folder)
        if not matches:
            scope = folder or "."
            return ConnectorResult(
                success=True,
                action="search_notes",
                data=f"Aucun résultat ({mode}) pour {query!r} dans {scope}.",
                target_path=folder or ".",
            )
        lines = [f"Résultats recherche ({mode}, {len(matches)}) :"]
        lines.extend(f"  - {note}" for note in matches)
        return ConnectorResult(
            success=True,
            action="search_notes",
            data="\n".join(lines),
            target_path=folder or ".",
        )

    def _list_notes(self, params: dict) -> ConnectorResult:
        folder = str(params.get("folder", "")).strip()
        recursive = bool(params.get("recursive", False))
        try:
            if folder:
                base = resolve_vault_path(
                    folder,
                    self._vault_root,  # type: ignore[arg-type]
                    must_exist=True,
                    expect_dir=True,
                )
            else:
                base = self._vault_root  # type: ignore[assignment]
            notes = self._collect_notes(base, recursive=recursive)
        except VaultPathGuardError as exc:
            return self._error("list_notes", str(exc))
        except OSError as exc:
            return self._error("list_notes", f"Listage impossible : {exc}")

        if not notes:
            scope = folder or "."
            return ConnectorResult(
                success=True,
                action="list_notes",
                data=f"Aucune note markdown dans {scope}.",
                target_path=folder or ".",
            )

        lines = [f"Notes markdown ({len(notes)}) :"]
        lines.extend(f"  - {note}" for note in notes)
        return ConnectorResult(
            success=True,
            action="list_notes",
            data="\n".join(lines),
            target_path=folder or ".",
        )

    def _resolve_note_path(
        self,
        raw_path: str,
        *,
        must_exist: bool,
        expect_file: bool = False,
    ) -> Path:
        normalized = self._normalize_note_path(raw_path)
        return resolve_vault_path(
            normalized,
            self._vault_root,  # type: ignore[arg-type]
            must_exist=must_exist,
            expect_file=expect_file,
        )

    @staticmethod
    def _normalize_note_path(raw_path: str) -> str:
        """Ensure note paths use a .md extension for vault consistency."""
        path = Path(raw_path.strip())
        if path.suffix.lower() != ".md":
            return f"{path.as_posix()}.md"
        return path.as_posix()

    def _search_base(self, folder: str) -> Path:
        if folder:
            return resolve_vault_path(
                folder,
                self._vault_root,  # type: ignore[arg-type]
                must_exist=True,
                expect_dir=True,
            )
        return self._vault_root  # type: ignore[return-value]

    def _collect_notes(self, base: Path, *, recursive: bool) -> list[str]:
        root = self._vault_root  # type: ignore[assignment]
        pattern = "**/*.md" if recursive else "*.md"
        notes: list[str] = []
        for item in sorted(base.glob(pattern)):
            if item.is_file():
                notes.append(relative_vault_path(item, root))
        return notes

    def _filter_notes(self, candidates: list[str], mode: str, query: str) -> list[str]:
        if mode == "folder":
            prefix = query.replace("\\", "/").strip("/")
            if not prefix:
                return candidates
            return [
                note
                for note in candidates
                if note == prefix
                or note.startswith(f"{prefix}/")
                or f"/{prefix}/" in f"/{note}/"
            ]

        if mode == "filename":
            lowered = query.lower()
            if not lowered:
                return candidates
            return [note for note in candidates if lowered in Path(note).name.lower()]

        if mode == "tag":
            tag = query.lstrip("#").lower()
            if not tag:
                return []
            return [
                note
                for note in candidates
                if self._note_has_tag(note, tag)
            ]

        if mode == "keyword":
            lowered = query.lower()
            if not lowered:
                return []
            return [
                note
                for note in candidates
                if self._note_contains_keyword(note, lowered)
            ]

        return []

    def _rename_note(self, params: dict) -> ConnectorResult:
        """Rename a note within the vault and rewrite inbound wikilinks (Phase 22.0)."""
        path = str(params.get("path", "")).strip()
        new_path = str(params.get("new_path", params.get("destination", ""))).strip()
        if not path or not new_path:
            return self._error("rename_note", "Chemin source et destination requis.")
        try:
            resolved = self._resolve_note_path(path, must_exist=True, expect_file=True)
            target = self._resolve_note_path(new_path, must_exist=False)
            if target.exists():
                return self._error(
                    "rename_note",
                    f"Une note existe déjà sous le nom {note_display_name(new_path)}.",
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            resolved.rename(target)
            old_stem = Path(path).stem
            new_stem = Path(new_path).stem
            if old_stem.lower() != new_stem.lower():
                self._rewrite_vault_wikilinks(old_stem, new_stem, exclude=target)
        except VaultPathGuardError as exc:
            return self._error("rename_note", str(exc))
        except OSError as exc:
            return self._error("rename_note", f"Renommage impossible : {exc}")
        rel = relative_vault_path(target, self._vault_root)  # type: ignore[arg-type]
        return ConnectorResult(
            success=True,
            action="rename_note",
            data=f"Note renommée : {note_display_name(rel)}",
            target_path=rel,
        )

    def _move_note(self, params: dict) -> ConnectorResult:
        """Move a note to another folder within the vault (Phase 22.0)."""
        path = str(params.get("path", "")).strip()
        folder = str(params.get("folder", params.get("destination", ""))).strip()
        if not path or not folder:
            return self._error("move_note", "Chemin de note et dossier cible requis.")
        try:
            resolved = self._resolve_note_path(path, must_exist=True, expect_file=True)
            dest_dir = resolve_vault_path(
                folder,
                self._vault_root,  # type: ignore[arg-type]
                must_exist=False,
                expect_dir=True,
            )
            dest_dir.mkdir(parents=True, exist_ok=True)
            target = dest_dir / resolved.name
            if target.exists() and target.resolve() != resolved.resolve():
                return self._error(
                    "move_note",
                    f"Une note existe déjà dans ce dossier : {note_display_name(target.name)}.",
                )
            if target.resolve() != resolved.resolve():
                resolved.rename(target)
        except VaultPathGuardError as exc:
            return self._error("move_note", str(exc))
        except OSError as exc:
            return self._error("move_note", f"Déplacement impossible : {exc}")
        rel = relative_vault_path(target, self._vault_root)  # type: ignore[arg-type]
        return ConnectorResult(
            success=True,
            action="move_note",
            data=f"Note déplacée : {note_display_name(rel)}",
            target_path=rel,
        )

    def _list_folders(self, params: dict) -> ConnectorResult:
        """List subfolders in the vault or under a parent folder (Phase 22.0)."""
        folder = str(params.get("folder", "")).strip()
        recursive = bool(params.get("recursive", False))
        try:
            if folder:
                base = resolve_vault_path(
                    folder,
                    self._vault_root,  # type: ignore[arg-type]
                    must_exist=True,
                    expect_dir=True,
                )
            else:
                base = self._vault_root  # type: ignore[assignment]
            folders = self._collect_folders(base, recursive=recursive)
        except VaultPathGuardError as exc:
            return self._error("list_folders", str(exc))
        except OSError as exc:
            return self._error("list_folders", f"Listage impossible : {exc}")

        if not folders:
            return ConnectorResult(
                success=True,
                action="list_folders",
                data="Aucun dossier trouvé.",
                target_path=folder or ".",
            )
        labels = [
            Path(item.replace("\\", "/")).name.replace("-", " ").replace("_", " ")
            for item in folders
        ]
        lines = [f"Dossiers ({len(folders)}) :"]
        lines.extend(f"  - {label}" for label in labels)
        return ConnectorResult(
            success=True,
            action="list_folders",
            data="\n".join(lines),
            target_path=folder or ".",
        )

    def _get_backlinks(self, params: dict) -> ConnectorResult:
        """Return notes that link to the target note (Phase 22.0)."""
        path = str(params.get("path", params.get("query", ""))).strip()
        if not path:
            return self._error("get_backlinks", "Note cible requise.")
        try:
            resolved = self._resolve_note_path(path, must_exist=True, expect_file=True)
            rel = relative_vault_path(resolved, self._vault_root)  # type: ignore[arg-type]
            target_stem = Path(rel).stem.lower()
            all_notes = self._collect_notes(self._vault_root, recursive=True)  # type: ignore[arg-type]
            index = build_backlink_index(all_notes, self._read_note_content)
            sources = index.get(target_stem, [])
        except VaultPathGuardError as exc:
            return self._error("get_backlinks", str(exc))
        except OSError as exc:
            return self._error("get_backlinks", f"Analyse impossible : {exc}")

        target_label = note_display_name(rel)
        if not sources:
            return ConnectorResult(
                success=True,
                action="get_backlinks",
                data=f"Aucun backlink vers {target_label}.",
                target_path=rel,
            )
        lines = [f"Backlinks vers {target_label} ({len(sources)}) :"]
        lines.extend(f"  - {note_display_name(note)}" for note in sources)
        return ConnectorResult(
            success=True,
            action="get_backlinks",
            data="\n".join(lines),
            target_path=rel,
        )

    def _get_outlinks(self, params: dict) -> ConnectorResult:
        """Return wikilinks from a note to other notes (Phase 22.0)."""
        path = str(params.get("path", "")).strip()
        if not path:
            return self._error("get_outlinks", "Chemin de note requis.")
        try:
            resolved = self._resolve_note_path(path, must_exist=True, expect_file=True)
            content = resolved.read_text(encoding="utf-8")
            rel = relative_vault_path(resolved, self._vault_root)  # type: ignore[arg-type]
            stems = collect_outlink_stems(content)
        except VaultPathGuardError as exc:
            return self._error("get_outlinks", str(exc))
        except OSError as exc:
            return self._error("get_outlinks", f"Lecture impossible : {exc}")

        source_label = note_display_name(rel)
        if not stems:
            return ConnectorResult(
                success=True,
                action="get_outlinks",
                data=f"Aucun lien sortant depuis {source_label}.",
                target_path=rel,
            )
        lines = [f"Liens sortants depuis {source_label} ({len(stems)}) :"]
        lines.extend(f"  - {stem.replace('-', ' ').title()}" for stem in stems)
        return ConnectorResult(
            success=True,
            action="get_outlinks",
            data="\n".join(lines),
            target_path=rel,
        )

    def _read_frontmatter(self, params: dict) -> ConnectorResult:
        """Read YAML frontmatter from a note (Phase 22.0)."""
        path = str(params.get("path", "")).strip()
        if not path:
            return self._error("read_frontmatter", "Chemin de note requis.")
        try:
            resolved = self._resolve_note_path(path, must_exist=True, expect_file=True)
            content = resolved.read_text(encoding="utf-8")
            frontmatter, _body = split_frontmatter(content)
            rel = relative_vault_path(resolved, self._vault_root)  # type: ignore[arg-type]
        except VaultPathGuardError as exc:
            return self._error("read_frontmatter", str(exc))
        except OSError as exc:
            return self._error("read_frontmatter", f"Lecture impossible : {exc}")

        label = note_display_name(rel)
        if not frontmatter:
            return ConnectorResult(
                success=True,
                action="read_frontmatter",
                data=f"Aucun frontmatter pour {label}.",
                target_path=rel,
            )
        block = frontmatter.strip("-\n").strip()
        return ConnectorResult(
            success=True,
            action="read_frontmatter",
            data=f"Frontmatter — {label} :\n{block}",
            target_path=rel,
        )

    def _update_frontmatter(self, params: dict) -> ConnectorResult:
        """Merge key/value pairs into note frontmatter (Phase 22.0)."""
        path = str(params.get("path", "")).strip()
        updates = params.get("frontmatter") or params.get("metadata") or {}
        if not path:
            return self._error("update_frontmatter", "Chemin de note requis.")
        if not isinstance(updates, dict) or not updates:
            return self._error("update_frontmatter", "Métadonnées frontmatter requises.")
        try:
            resolved = self._resolve_note_path(path, must_exist=True, expect_file=True)
            content = resolved.read_text(encoding="utf-8")
            updated = self._merge_frontmatter(content, updates)
            resolved.write_text(updated, encoding="utf-8")
            rel = relative_vault_path(resolved, self._vault_root)  # type: ignore[arg-type]
        except VaultPathGuardError as exc:
            return self._error("update_frontmatter", str(exc))
        except OSError as exc:
            return self._error("update_frontmatter", f"Mise à jour impossible : {exc}")
        return ConnectorResult(
            success=True,
            action="update_frontmatter",
            data=f"Frontmatter mis à jour : {note_display_name(rel)}",
            target_path=rel,
        )

    def _list_tags(self, params: dict) -> ConnectorResult:
        """List tags used across the vault (Phase 22.0)."""
        _ = params
        try:
            all_notes = self._collect_notes(self._vault_root, recursive=True)  # type: ignore[arg-type]
            tag_index = collect_vault_tags(all_notes, self._read_note_content)
        except OSError as exc:
            return self._error("list_tags", f"Analyse impossible : {exc}")

        if not tag_index:
            return ConnectorResult(
                success=True,
                action="list_tags",
                data="Aucun tag trouvé dans le vault.",
                target_path=".",
            )
        lines = [f"Tags ({len(tag_index)}) :"]
        for tag in sorted(tag_index):
            count = len(tag_index[tag])
            lines.append(f"  - #{tag} ({count} note{'s' if count != 1 else ''})")
        return ConnectorResult(
            success=True,
            action="list_tags",
            data="\n".join(lines),
            target_path=".",
        )

    def _read_note_content(self, relative_path: str) -> str:
        resolved = self._resolve_note_path(relative_path, must_exist=True, expect_file=True)
        return resolved.read_text(encoding="utf-8")

    def _collect_folders(self, base: Path, *, recursive: bool) -> list[str]:
        root = self._vault_root  # type: ignore[assignment]
        folders: list[str] = []
        if recursive:
            for item in sorted(base.rglob("*")):
                if item.is_dir() and item != base:
                    folders.append(relative_vault_path(item, root))
        else:
            for item in sorted(base.iterdir()):
                if item.is_dir():
                    folders.append(relative_vault_path(item, root))
        return folders

    def _rewrite_vault_wikilinks(
        self,
        old_stem: str,
        new_stem: str,
        *,
        exclude: Path,
    ) -> None:
        """Rewrite wikilinks across the vault after a rename."""
        all_notes = self._collect_notes(self._vault_root, recursive=True)  # type: ignore[arg-type]
        for note_path in all_notes:
            resolved = self._resolve_note_path(note_path, must_exist=True, expect_file=True)
            if resolved.resolve() == exclude.resolve():
                continue
            content = resolved.read_text(encoding="utf-8")
            updated = rewrite_wikilinks_after_rename(content, old_stem, new_stem)
            if updated != content:
                resolved.write_text(updated, encoding="utf-8")

    @staticmethod
    def _merge_frontmatter(content: str, updates: dict) -> str:
        frontmatter, body = split_frontmatter(content)
        lines: list[str] = []
        existing_keys: set[str] = set()

        if frontmatter:
            block = frontmatter.strip("-\n")
            for line in block.splitlines():
                if ":" in line:
                    key = line.split(":", 1)[0].strip()
                    existing_keys.add(key.lower())
                    if key.lower() in {str(k).lower() for k in updates}:
                        continue
                lines.append(line)

        for key, value in updates.items():
            if isinstance(value, list):
                formatted = ", ".join(str(item) for item in value)
                lines.append(f"{key}: [{formatted}]")
            else:
                lines.append(f"{key}: {value}")

        fm_block = "---\n" + "\n".join(lines) + "\n---"
        if body.startswith("\n"):
            return fm_block + body
        return f"{fm_block}\n{body}"

    def _note_has_tag(self, relative_path: str, tag: str) -> bool:
        try:
            resolved = self._resolve_note_path(relative_path, must_exist=True, expect_file=True)
            content = resolved.read_text(encoding="utf-8")
        except (VaultPathGuardError, OSError):
            return False
        if f"#{tag}" in content.lower():
            return True
        frontmatter = self._parse_frontmatter_tags(content)
        return tag in frontmatter

    def _note_contains_keyword(self, relative_path: str, keyword: str) -> bool:
        tokens = [token for token in keyword.lower().split() if len(token) > 2]
        if not tokens:
            tokens = [keyword.lower()] if keyword else []
        try:
            resolved = self._resolve_note_path(relative_path, must_exist=True, expect_file=True)
            content = resolved.read_text(encoding="utf-8").lower()
        except (VaultPathGuardError, OSError):
            return False
        stem = Path(relative_path).stem.lower()
        return any(token in content or token in stem for token in tokens)

    @staticmethod
    def _parse_frontmatter_tags(content: str) -> set[str]:
        if not content.startswith("---"):
            return set()
        end = content.find("\n---", 3)
        if end == -1:
            return set()
        block = content[3:end]
        tags: set[str] = set()
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("tags:"):
                value = stripped.split(":", 1)[1].strip()
                if value.startswith("[") and value.endswith("]"):
                    inner = value[1:-1]
                    for item in inner.split(","):
                        cleaned = item.strip().strip("\"'")
                        if cleaned:
                            tags.add(cleaned.lower())
                else:
                    tags.add(value.strip("# ").lower())
        return tags

    @staticmethod
    def _error(action: str, message: str) -> ConnectorResult:
        return ConnectorResult(success=False, action=action, error=message)
