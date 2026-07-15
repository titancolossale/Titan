# =====================================
# Titan Obsidian Decision Layer
# =====================================

"""Decide when and how Titan uses the user's existing Obsidian vault (Phase 12.5 Batch 2 — P125-007)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from tools.connectors.markdown_editor import NoteUpdateMode
from tools.connectors.obsidian_connector import ObsidianConnector

_NOTE_PATH_PATTERN = re.compile(
    r"(?:[\w./\\-]+[/\\])?[\w.-]+\.md",
    re.IGNORECASE,
)

_CASUAL_KEYWORDS = (
    "bonjour",
    "salut",
    "hello",
    "hi ",
    "hey ",
    "coucou",
    "merci",
    "thanks",
    "lol",
    "haha",
    "blague",
    "joke",
    "comment ça va",
    "how are you",
    "ça va",
)

_EPHEMERAL_KEYWORDS = (
    "juste pour info",
    "temporaire",
    "temporary",
    "for now",
    "cette session",
    "this session",
    "one time",
    "une fois",
    "internal reasoning",
    "raisonnement interne",
)

_WORTHY_KEYWORDS = (
    "projet",
    "project",
    "objectif",
    "goal",
    "documentation",
    "doc ",
    "procédure",
    "procedure",
    "process",
    "checklist",
    "roadmap",
    "rappel",
    "reminder",
    "archiv",
    "knowledge",
    "référence",
    "reference",
    "note permanente",
    "long term",
    "long-term",
    "important",
    "guide",
    "tutorial",
    "spec",
    "architecture",
)

_OBSIDIAN_SIGNALS = (
    "obsidian",
    "vault",
    "titan ai",
    "mes notes",
    "note obsidian",
    "dans le vault",
    "dans obsidian",
    "dans mon vault",
)

_READ_KEYWORDS = (
    "lis la note",
    "lire la note",
    "read note",
    "read the note",
    "ouvre la note",
    "open note",
    "affiche la note",
    "show note",
    "contenu de la note",
)

_SEARCH_KEYWORDS = (
    "cherche dans",
    "cherche les notes",
    "search in",
    "trouve la note",
    "find note",
    "find notes",
    "recherche dans",
    "search notes",
    "search vault",
    "liste les notes",
    "list notes",
    "notes liées",
    "notes liees",
    "liées à",
    "liees a",
    "tag ",
)

_HEALTH_KEYWORDS = (
    "santé du vault",
    "sante du vault",
    "santé de mon vault",
    "sante de mon vault",
    "analyse la santé",
    "analyse la sante",
    "vault health",
    "rapport vault",
    "analyse vault",
    "audit vault",
    "organise le vault",
    "organiser le vault",
    "doublons",
    "duplicates",
    "notes orphelines",
    "orphan notes",
    "notes vides",
    "empty notes",
)

_WRITE_KEYWORDS = (
    "documente",
    "document",
    "ajoute",
    "ajouter",
    "add to",
    "mets à jour",
    "met a jour",
    "update note",
    "crée une note",
    "cree une note",
    "create note",
    "nouvelle note",
    "new note",
    "enregistre",
    "save to obsidian",
    "note dans obsidian",
)

_DELETE_KEYWORDS = (
    "supprime la note",
    "supprimer la note",
    "delete note",
    "delete the note",
    "efface la note",
    "effacer la note",
)

_RENAME_KEYWORDS = (
    "renomme la note",
    "renommer la note",
    "rename note",
    "rename the note",
)

_MOVE_KEYWORDS = (
    "déplace la note",
    "deplace la note",
    "move note",
    "move the note",
    "déplacer vers",
    "move to folder",
)

_BACKLINK_KEYWORDS = (
    "backlink",
    "backlinks",
    "liens entrants",
    "notes qui pointent",
    "notes qui lient",
    "qui référence",
    "qui reference",
)

_OUTLINK_KEYWORDS = (
    "liens sortants",
    "outlink",
    "outlinks",
    "liens de la note",
)

_FRONTMATTER_KEYWORDS = (
    "frontmatter",
    "métadonnées",
    "metadonnees",
    "yaml header",
    "en-tête yaml",
)

_LIST_FOLDERS_KEYWORDS = (
    "liste les dossiers",
    "list folders",
    "lister les dossiers",
)

_LIST_TAGS_KEYWORDS = (
    "liste les tags",
    "list tags",
    "tags du vault",
    "tags obsidian",
)


class ObsidianDecision(str, Enum):
    """Canonical Obsidian vault operation decisions."""

    DO_NOT_USE_OBSIDIAN = "do_not_use_obsidian"
    READ_EXISTING_NOTE = "read_existing_note"
    UPDATE_EXISTING_NOTE = "update_existing_note"
    PATCH_EXISTING_NOTE = "patch_existing_note"
    CREATE_NEW_NOTE = "create_new_note"
    SEARCH_NOTES = "search_notes"
    VAULT_HEALTH = "vault_health"
    DELETE_NOTE = "delete_note"
    RENAME_NOTE = "rename_note"
    MOVE_NOTE = "move_note"
    GET_BACKLINKS = "get_backlinks"
    GET_OUTLINKS = "get_outlinks"
    READ_FRONTMATTER = "read_frontmatter"
    LIST_FOLDERS = "list_folders"
    LIST_TAGS = "list_tags"


class ObsidianSearchMode(str, Enum):
    """Search modes supported by the Obsidian connector."""

    FILENAME = "filename"
    KEYWORD = "keyword"
    TAG = "tag"
    FOLDER = "folder"


@dataclass(frozen=True)
class ObsidianDecisionResult:
    """Structured output from the Obsidian decision layer."""

    decision: ObsidianDecision
    reason: str
    search_mode: ObsidianSearchMode | None = None
    query: str | None = None
    target_path: str | None = None
    content: str | None = None
    folder: str | None = None
    update_mode: str | None = None
    heading: str | None = None
    matched_notes: tuple[str, ...] = ()
    tool_params: tuple[tuple[str, object], ...] = ()

    def tool_params_dict(self) -> dict:
        """Return tool invocation parameters as a plain dict."""
        return dict(self.tool_params)


def is_casual_or_ephemeral(message: str) -> bool:
    """Return True when the message should never produce vault writes."""
    lowered = message.lower().strip()
    if not lowered:
        return True
    if any(keyword in lowered for keyword in _CASUAL_KEYWORDS):
        if not any(keyword in lowered for keyword in _WORTHY_KEYWORDS):
            return True
    if any(keyword in lowered for keyword in _EPHEMERAL_KEYWORDS):
        return True
    return False


def is_worthy_persistence(message: str) -> bool:
    """Return True when content is worth keeping in the user's vault."""
    lowered = message.lower()
    for keyword in _WORTHY_KEYWORDS:
        if len(keyword) <= 4:
            if re.search(rf"\b{re.escape(keyword)}\b", lowered):
                return True
        elif keyword in lowered:
            return True
    if _NOTE_PATH_PATTERN.search(message):
        return True
    if any(signal in lowered for signal in _OBSIDIAN_SIGNALS) and any(
        kw in lowered for kw in _WRITE_KEYWORDS
    ):
        return True
    return False


def infer_search_mode(message: str) -> ObsidianSearchMode:
    """Infer the best search mode from natural-language phrasing."""
    lowered = message.lower()
    if "tag" in lowered or re.search(r"#\w+", message):
        return ObsidianSearchMode.TAG
    if "dossier" in lowered or "folder" in lowered or "répertoire" in lowered:
        return ObsidianSearchMode.FOLDER
    if _NOTE_PATH_PATTERN.search(message) or "fichier" in lowered or "filename" in lowered:
        return ObsidianSearchMode.FILENAME
    return ObsidianSearchMode.KEYWORD


def extract_note_path(message: str) -> str | None:
    """Extract an explicit .md note path from the message, if present."""
    match = _NOTE_PATH_PATTERN.search(message)
    if match:
        return match.group(0).replace("\\", "/")
    return None


def extract_search_query(message: str, mode: ObsidianSearchMode) -> str:
    """Extract a search query from the user message."""
    if mode == ObsidianSearchMode.TAG:
        tag_match = re.search(r"#([\w-]+)", message)
        if tag_match:
            return tag_match.group(1)
        for token in message.split():
            if token.lower().startswith("tag"):
                parts = token.split(":", 1)
                if len(parts) == 2:
                    return parts[1].strip("# ")
    path = extract_note_path(message)
    if path and mode == ObsidianSearchMode.FILENAME:
        return Path(path).stem
    lowered = message.lower()
    for prefix in (
        "cherche ",
        "trouve ",
        "find ",
        "search ",
        "recherche ",
        "tag ",
    ):
        if prefix in lowered:
            idx = lowered.index(prefix)
            return message[idx + len(prefix) :].strip(" :\"'")
    words = [word for word in re.findall(r"[\w-]+", message) if len(word) > 2]
    skip = {
        "obsidian",
        "vault",
        "note",
        "notes",
        "dans",
        "the",
        "dans",
        "pour",
        "with",
        "dossier",
        "folder",
    }
    filtered = [word for word in words if word.lower() not in skip]
    return " ".join(filtered[:5]) if filtered else message.strip()[:80]


def extract_write_content(message: str) -> str:
    """Extract note body content from a write request."""
    markers = ("contenu:", "content:", "texte:", "body:")
    lowered = message.lower()
    for marker in markers:
        if marker in lowered:
            idx = lowered.index(marker)
            return message[idx + len(marker) :].strip()
    return message.strip()


def suggest_note_path(message: str, query: str) -> str:
    """Suggest a vault-relative path for a new note."""
    topic = query or "note"
    slug = re.sub(r"[^\w-]+", "-", topic.lower()).strip("-") or "note"
    if "projet" in message.lower() or "project" in message.lower():
        return f"projects/{slug}.md"
    if "doc" in message.lower() or "documentation" in message.lower():
        return f"docs/{slug}.md"
    return f"notes/{slug}.md"


class ObsidianDecisionEngine:
    """Decide when and how Titan should interact with the Obsidian vault."""

    def __init__(self, connector: ObsidianConnector | None = None) -> None:
        self._connector = connector

    def decide(
        self,
        message: str,
        *,
        connector: ObsidianConnector | None = None,
    ) -> ObsidianDecisionResult:
        """Return the Obsidian operation decision for a user message."""
        active = connector or self._connector
        if active is None or not active.is_configured:
            return ObsidianDecisionResult(
                decision=ObsidianDecision.DO_NOT_USE_OBSIDIAN,
                reason="Vault Obsidian non configuré ou inaccessible.",
            )

        lowered = message.lower()
        has_obsidian_signal = any(signal in lowered for signal in _OBSIDIAN_SIGNALS)
        explicit_path = extract_note_path(message)

        if is_casual_or_ephemeral(message) and not has_obsidian_signal:
            return ObsidianDecisionResult(
                decision=ObsidianDecision.DO_NOT_USE_OBSIDIAN,
                reason="Conversation casual ou contexte éphémère — pas d'écriture vault.",
            )

        if any(kw in lowered for kw in _READ_KEYWORDS) or (
            explicit_path and not any(kw in lowered for kw in _WRITE_KEYWORDS)
        ):
            if explicit_path:
                return ObsidianDecisionResult(
                    decision=ObsidianDecision.READ_EXISTING_NOTE,
                    reason=f"Lecture explicite de la note {explicit_path}.",
                    target_path=explicit_path,
                    tool_params=(
                        ("action", "read_note"),
                        ("path", explicit_path),
                    ),
                )
            return ObsidianDecisionResult(
                decision=ObsidianDecision.SEARCH_NOTES,
                reason="Lecture demandée sans chemin explicite — recherche d'abord.",
                search_mode=ObsidianSearchMode.FILENAME,
                query=extract_search_query(message, ObsidianSearchMode.FILENAME),
                tool_params=self._search_params(
                    ObsidianSearchMode.FILENAME,
                    extract_search_query(message, ObsidianSearchMode.FILENAME),
                ),
            )

        if any(kw in lowered for kw in _HEALTH_KEYWORDS) and has_obsidian_signal:
            return ObsidianDecisionResult(
                decision=ObsidianDecision.VAULT_HEALTH,
                reason="Analyse de santé et organisation du vault demandée.",
                tool_params=(("action", "vault_health"),),
            )

        if any(kw in lowered for kw in _DELETE_KEYWORDS) and (has_obsidian_signal or explicit_path):
            if not explicit_path:
                return ObsidianDecisionResult(
                    decision=ObsidianDecision.SEARCH_NOTES,
                    reason="Suppression demandée — identifier la note d'abord.",
                    search_mode=ObsidianSearchMode.FILENAME,
                    query=extract_search_query(message, ObsidianSearchMode.FILENAME),
                    tool_params=self._search_params(
                        ObsidianSearchMode.FILENAME,
                        extract_search_query(message, ObsidianSearchMode.FILENAME),
                    ),
                )
            return ObsidianDecisionResult(
                decision=ObsidianDecision.DELETE_NOTE,
                reason=f"Suppression de la note {explicit_path}.",
                target_path=explicit_path,
                tool_params=(
                    ("action", "delete_note"),
                    ("path", explicit_path),
                ),
            )

        if any(kw in lowered for kw in _RENAME_KEYWORDS) and (has_obsidian_signal or explicit_path):
            new_path = self._extract_rename_target(message)
            if explicit_path and new_path:
                return ObsidianDecisionResult(
                    decision=ObsidianDecision.RENAME_NOTE,
                    reason=f"Renommage de {explicit_path} vers {new_path}.",
                    target_path=explicit_path,
                    tool_params=(
                        ("action", "rename_note"),
                        ("path", explicit_path),
                        ("new_path", new_path),
                    ),
                )

        if any(kw in lowered for kw in _MOVE_KEYWORDS) and (has_obsidian_signal or explicit_path):
            folder = self._extract_folder(message)
            if explicit_path and folder:
                return ObsidianDecisionResult(
                    decision=ObsidianDecision.MOVE_NOTE,
                    reason=f"Déplacement de {explicit_path} vers {folder}.",
                    target_path=explicit_path,
                    folder=folder,
                    tool_params=(
                        ("action", "move_note"),
                        ("path", explicit_path),
                        ("folder", folder),
                    ),
                )

        if any(kw in lowered for kw in _BACKLINK_KEYWORDS) and (has_obsidian_signal or explicit_path):
            target = explicit_path or extract_search_query(message, ObsidianSearchMode.FILENAME)
            return ObsidianDecisionResult(
                decision=ObsidianDecision.GET_BACKLINKS,
                reason="Recherche de backlinks vers la note cible.",
                target_path=target,
                tool_params=(
                    ("action", "get_backlinks"),
                    ("path", target),
                ),
            )

        if any(kw in lowered for kw in _OUTLINK_KEYWORDS) and explicit_path:
            return ObsidianDecisionResult(
                decision=ObsidianDecision.GET_OUTLINKS,
                reason=f"Liens sortants depuis {explicit_path}.",
                target_path=explicit_path,
                tool_params=(
                    ("action", "get_outlinks"),
                    ("path", explicit_path),
                ),
            )

        if any(kw in lowered for kw in _FRONTMATTER_KEYWORDS) and explicit_path:
            return ObsidianDecisionResult(
                decision=ObsidianDecision.READ_FRONTMATTER,
                reason=f"Lecture du frontmatter de {explicit_path}.",
                target_path=explicit_path,
                tool_params=(
                    ("action", "read_frontmatter"),
                    ("path", explicit_path),
                ),
            )

        if any(kw in lowered for kw in _LIST_FOLDERS_KEYWORDS) and has_obsidian_signal:
            folder = self._extract_folder(message)
            params: list[tuple[str, object]] = [("action", "list_folders")]
            if folder:
                params.append(("folder", folder))
            return ObsidianDecisionResult(
                decision=ObsidianDecision.LIST_FOLDERS,
                reason="Listage des dossiers du vault.",
                folder=folder,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _LIST_TAGS_KEYWORDS) and has_obsidian_signal:
            return ObsidianDecisionResult(
                decision=ObsidianDecision.LIST_TAGS,
                reason="Listage des tags du vault.",
                tool_params=(("action", "list_tags"),),
            )

        if any(kw in lowered for kw in _WRITE_KEYWORDS) or (
            has_obsidian_signal
            and is_worthy_persistence(message)
            and not any(kw in lowered for kw in _SEARCH_KEYWORDS)
        ):
            return self._decide_write(message, active)

        if any(kw in lowered for kw in _SEARCH_KEYWORDS) or (
            has_obsidian_signal and "liste" in lowered
        ):
            mode = infer_search_mode(message)
            query = extract_search_query(message, mode)
            folder = self._extract_folder(message)
            return ObsidianDecisionResult(
                decision=ObsidianDecision.SEARCH_NOTES,
                reason=f"Recherche vault ({mode.value}).",
                search_mode=mode,
                query=query,
                folder=folder,
                tool_params=self._search_params(mode, query, folder),
            )

        if has_obsidian_signal and is_casual_or_ephemeral(message):
            return ObsidianDecisionResult(
                decision=ObsidianDecision.DO_NOT_USE_OBSIDIAN,
                reason="Mention Obsidian sans contenu durable à persister.",
            )

        if has_obsidian_signal:
            mode = ObsidianSearchMode.KEYWORD
            query = extract_search_query(message, mode)
            return ObsidianDecisionResult(
                decision=ObsidianDecision.SEARCH_NOTES,
                reason="Signal Obsidian — explorer le vault avant toute création.",
                search_mode=mode,
                query=query,
                tool_params=self._search_params(mode, query),
            )

        return ObsidianDecisionResult(
            decision=ObsidianDecision.DO_NOT_USE_OBSIDIAN,
            reason="Aucun signal Obsidian actionnable.",
        )

    def _decide_write(
        self,
        message: str,
        connector: ObsidianConnector,
    ) -> ObsidianDecisionResult:
        """Search for an existing note before creating a new one."""
        if not is_worthy_persistence(message):
            return ObsidianDecisionResult(
                decision=ObsidianDecision.DO_NOT_USE_OBSIDIAN,
                reason="Contenu non durable — pas de création ni mise à jour vault.",
            )

        explicit_path = extract_note_path(message)
        if explicit_path:
            if connector.note_exists(explicit_path):
                content = extract_write_content(message)
                update_mode = self._infer_update_mode(message)
                if update_mode != NoteUpdateMode.REPLACE.value:
                    return ObsidianDecisionResult(
                        decision=ObsidianDecision.PATCH_EXISTING_NOTE,
                        reason=f"Note existante — patch {update_mode} : {explicit_path}.",
                        target_path=explicit_path,
                        content=content,
                        update_mode=update_mode,
                        heading=self._extract_heading(message),
                        matched_notes=(explicit_path,),
                        tool_params=self._patch_params(
                            explicit_path,
                            content,
                            update_mode,
                            self._extract_heading(message),
                        ),
                    )
                return ObsidianDecisionResult(
                    decision=ObsidianDecision.UPDATE_EXISTING_NOTE,
                    reason=f"Note existante trouvée : {explicit_path}.",
                    target_path=explicit_path,
                    content=content,
                    matched_notes=(explicit_path,),
                    tool_params=(
                        ("action", "update_note"),
                        ("path", explicit_path),
                        ("content", content),
                    ),
                )
            content = extract_write_content(message)
            return ObsidianDecisionResult(
                decision=ObsidianDecision.CREATE_NEW_NOTE,
                reason=f"Chemin explicite sans note existante : {explicit_path}.",
                target_path=explicit_path,
                content=content,
                tool_params=(
                    ("action", "create_note"),
                    ("path", explicit_path),
                    ("content", content),
                ),
            )

        query = self._extract_write_topic(message)
        matches = connector.find_notes(
            mode=ObsidianSearchMode.KEYWORD.value,
            query=query,
        )
        content = extract_write_content(message)

        if matches:
            best = matches[0]
            update_mode = self._infer_update_mode(message)
            return ObsidianDecisionResult(
                decision=ObsidianDecision.PATCH_EXISTING_NOTE,
                reason=f"Note pertinente existante — patch {update_mode} : {best}.",
                target_path=best,
                content=content,
                update_mode=update_mode,
                query=query,
                matched_notes=tuple(matches),
                tool_params=self._patch_params(best, content, update_mode),
            )

        new_path = suggest_note_path(message, query)
        return ObsidianDecisionResult(
            decision=ObsidianDecision.CREATE_NEW_NOTE,
            reason="Aucune note pertinente — création seulement pour contenu durable.",
            target_path=new_path,
            content=content,
            query=query,
            tool_params=(
                ("action", "create_note"),
                ("path", new_path),
                ("content", content),
            ),
        )

    @staticmethod
    def _extract_write_topic(message: str) -> str:
        """Extract durable topic tokens for search-before-create."""
        lowered = message.lower()
        for marker in ("contenu:", "content:", "texte:", "body:"):
            if marker in lowered:
                message = message[: lowered.index(marker)]
                break
        words = re.findall(r"[\w-]+", message)
        skip = {
            "obsidian",
            "vault",
            "note",
            "notes",
            "documente",
            "document",
            "crée",
            "cree",
            "create",
            "nouvelle",
            "new",
            "dans",
            "the",
            "pour",
            "with",
            "contenu",
            "content",
        }
        topic_words = [word for word in words if word.lower() not in skip and len(word) > 2]
        return " ".join(topic_words[:4]) if topic_words else message.strip()[:80]

    @staticmethod
    def _infer_update_mode(message: str) -> str:
        """Prefer append over full replace to preserve existing formatting."""
        lowered = message.lower()
        if "remplace la section" in lowered or "replace section" in lowered:
            return NoteUpdateMode.REPLACE_SECTION.value
        if "sous la section" in lowered or "under heading" in lowered or "insert under" in lowered:
            return NoteUpdateMode.INSERT_UNDER_HEADING.value
        if "au début" in lowered or "prepend" in lowered or "en tête" in lowered:
            return NoteUpdateMode.PREPEND.value
        if "remplace" in lowered or "replace entire" in lowered or "écrase" in lowered:
            return NoteUpdateMode.REPLACE.value
        return NoteUpdateMode.APPEND.value

    @staticmethod
    def _extract_heading(message: str) -> str | None:
        """Extract a section heading from natural language."""
        patterns = (
            r"sous (?:la section|le titre|heading)\s+[\"']?([^\"'\n]+?)[\"']?(?:\s+dans|\s+contenu|$)",
            r"under heading\s+[\"']?([^\"'\n]+?)[\"']?(?:\s+in|\s+content|$)",
            r"section\s+[\"']?([^\"'\n./\\]+?)[\"']?(?:\s+dans|\s+contenu|$)",
        )
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                heading = match.group(1).strip()
                heading = _NOTE_PATH_PATTERN.sub("", heading).strip()
                return heading or None
        return None

    @staticmethod
    def _patch_params(
        path: str,
        content: str,
        update_mode: str,
        heading: str | None = None,
    ) -> tuple[tuple[str, object], ...]:
        params: list[tuple[str, object]] = [
            ("action", "patch_note"),
            ("path", path),
            ("update_mode", update_mode),
            ("new_content", content),
        ]
        if heading:
            params.append(("heading", heading))
        return tuple(params)

    @staticmethod
    def _search_params(
        mode: ObsidianSearchMode,
        query: str,
        folder: str | None = None,
    ) -> tuple[tuple[str, object], ...]:
        params: list[tuple[str, object]] = [
            ("action", "search_notes"),
            ("mode", mode.value),
            ("query", query),
        ]
        if folder:
            params.append(("folder", folder))
        return tuple(params)

    @staticmethod
    def _extract_folder(message: str) -> str | None:
        lowered = message.lower()
        for prefix in ("dossier ", "folder ", "dans le dossier ", "in folder ", "vers le dossier ", "to folder "):
            if prefix in lowered:
                idx = lowered.index(prefix)
                return message[idx + len(prefix) :].strip(" .\"'")
        return None

    @staticmethod
    def _extract_rename_target(message: str) -> str | None:
        """Extract destination path from rename phrasing."""
        patterns = (
            r"(?:renomme|rename)(?:\s+\w+){0,3}\s+(?:en|as|to|vers)\s+[\"']?([^\s\"']+\.md?)[\"']?",
            r"(?:en|as|to|vers)\s+[\"']?([^\s\"']+\.md?)[\"']?\s*$",
        )
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                target = match.group(1).replace("\\", "/")
                if not target.lower().endswith(".md"):
                    target = f"{target}.md"
                return target
        return None
