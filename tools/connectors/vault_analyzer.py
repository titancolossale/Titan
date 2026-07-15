# =====================================
# Titan Vault Analyzer
# =====================================

"""Vault organization analysis and health reporting (Phase 12.5 Batch 3 — P125-013).

Recommendations only — never auto-delete or auto-merge notes.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from tools.connectors.markdown_parser import extract_wikilinks, parse_markdown, split_frontmatter

_DEFAULT_ABANDONED_DAYS = 180
_MIN_CONTENT_CHARS = 20
_DUPLICATE_SIMILARITY_THRESHOLD = 0.72


@dataclass(frozen=True)
class DuplicateTopicGroup:
    """Notes that likely cover the same topic."""

    topic: str
    notes: tuple[str, ...]
    similarity: float
    recommendation: str


@dataclass(frozen=True)
class MergeSuggestion:
    """Suggested merge without performing it."""

    source_notes: tuple[str, ...]
    reason: str
    recommendation: str


@dataclass(frozen=True)
class AbandonedNote:
    """Note with signs of neglect."""

    path: str
    last_modified: str
    days_since_edit: int
    reason: str


@dataclass(frozen=True)
class MissingTagNote:
    """Note that may benefit from tagging."""

    path: str
    suggestion: str


@dataclass(frozen=True)
class FolderIssue:
    """Note placed inconsistently relative to peers."""

    path: str
    current_folder: str
    issue: str
    recommendation: str


@dataclass(frozen=True)
class NamingIssue:
    """Filename or title inconsistency."""

    path: str
    issue: str
    recommendation: str


@dataclass
class VaultHealthReport:
    """Structured vault health analysis."""

    vault_root: str
    total_notes: int
    analyzed_at: str
    duplicated_topics: list[DuplicateTopicGroup] = field(default_factory=list)
    merge_suggestions: list[MergeSuggestion] = field(default_factory=list)
    orphan_notes: list[str] = field(default_factory=list)
    empty_notes: list[str] = field(default_factory=list)
    abandoned_notes: list[AbandonedNote] = field(default_factory=list)
    missing_tags: list[MissingTagNote] = field(default_factory=list)
    inconsistent_folders: list[FolderIssue] = field(default_factory=list)
    naming_inconsistencies: list[NamingIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Serialize report for tool output and tests."""
        return asdict(self)

    def format_summary(self) -> str:
        """Human-readable French summary for connector/tool responses."""
        lines = [
            f"Rapport santé vault ({self.total_notes} notes) — {self.analyzed_at}",
            "",
            f"• Sujets dupliqués : {len(self.duplicated_topics)}",
            f"• Suggestions fusion : {len(self.merge_suggestions)}",
            f"• Notes orphelines : {len(self.orphan_notes)}",
            f"• Notes vides : {len(self.empty_notes)}",
            f"• Notes abandonnées : {len(self.abandoned_notes)}",
            f"• Tags manquants : {len(self.missing_tags)}",
            f"• Placement dossier incohérent : {len(self.inconsistent_folders)}",
            f"• Nommage incohérent : {len(self.naming_inconsistencies)}",
        ]
        if self.duplicated_topics:
            lines.append("")
            lines.append("Sujets dupliqués (recommandations) :")
            for group in self.duplicated_topics[:5]:
                notes = ", ".join(group.notes)
                lines.append(f"  - {group.topic} [{notes}] — {group.recommendation}")
        if self.merge_suggestions:
            lines.append("")
            lines.append("Fusions suggérées (aucune action automatique) :")
            for suggestion in self.merge_suggestions[:5]:
                notes = ", ".join(suggestion.source_notes)
                lines.append(f"  - {notes} — {suggestion.recommendation}")
        if self.empty_notes:
            lines.append("")
            lines.append("Notes vides :")
            for note in self.empty_notes[:10]:
                lines.append(f"  - {note}")
        if self.orphan_notes:
            lines.append("")
            lines.append("Notes orphelines (sans liens entrants) :")
            for note in self.orphan_notes[:10]:
                lines.append(f"  - {note}")
        return "\n".join(lines)


@dataclass
class _NoteRecord:
    relative_path: str
    stem: str
    folder: str
    content: str
    body: str
    tags: set[str]
    wikilinks: list[str]
    mtime: float
    word_count: int


class VaultAnalyzer:
    """Analyze an Obsidian vault and produce recommendations only."""

    def __init__(
        self,
        vault_root: Path,
        *,
        abandoned_days: int = _DEFAULT_ABANDONED_DAYS,
    ) -> None:
        self._vault_root = vault_root
        self._abandoned_days = abandoned_days

    def analyze(self) -> VaultHealthReport:
        """Scan the vault and return a structured health report."""
        records = self._collect_notes()
        now = datetime.now(timezone.utc)
        report = VaultHealthReport(
            vault_root=str(self._vault_root),
            total_notes=len(records),
            analyzed_at=now.isoformat(),
        )
        if not records:
            return report

        report.empty_notes = self._find_empty_notes(records)
        report.abandoned_notes = self._find_abandoned_notes(records, now)
        report.duplicated_topics, report.merge_suggestions = self._find_duplicates(records)
        report.orphan_notes = self._find_orphans(records)
        report.missing_tags = self._find_missing_tags(records)
        report.inconsistent_folders = self._find_folder_issues(records)
        report.naming_inconsistencies = self._find_naming_issues(records)
        return report

    def _collect_notes(self) -> list[_NoteRecord]:
        records: list[_NoteRecord] = []
        for path in sorted(self._vault_root.rglob("*.md")):
            if not path.is_file():
                continue
            rel = path.relative_to(self._vault_root).as_posix()
            try:
                content = path.read_text(encoding="utf-8")
                mtime = path.stat().st_mtime
            except OSError:
                continue
            _, body = split_frontmatter(content)
            parsed = parse_markdown(content)
            records.append(
                _NoteRecord(
                    relative_path=rel,
                    stem=path.stem.lower(),
                    folder=path.parent.relative_to(self._vault_root).as_posix()
                    if path.parent != self._vault_root
                    else "",
                    content=content,
                    body=body.strip(),
                    tags=parsed.tags,
                    wikilinks=extract_wikilinks(body),
                    mtime=mtime,
                    word_count=len(re.findall(r"\w+", body)),
                )
            )
        return records

    @staticmethod
    def _find_empty_notes(records: list[_NoteRecord]) -> list[str]:
        empty: list[str] = []
        for record in records:
            if len(record.body) < _MIN_CONTENT_CHARS and record.word_count < 3:
                empty.append(record.relative_path)
        return empty

    def _find_abandoned_notes(
        self,
        records: list[_NoteRecord],
        now: datetime,
    ) -> list[AbandonedNote]:
        abandoned: list[AbandonedNote] = []
        for record in records:
            modified = datetime.fromtimestamp(record.mtime, tz=timezone.utc)
            days = (now - modified).days
            if days < self._abandoned_days:
                continue
            if record.word_count < 15 and not record.wikilinks:
                abandoned.append(
                    AbandonedNote(
                        path=record.relative_path,
                        last_modified=modified.date().isoformat(),
                        days_since_edit=days,
                        reason="Peu de contenu et aucun lien — candidat révision ou archivage manuel.",
                    )
                )
            elif days >= self._abandoned_days * 2 and record.word_count < 40:
                abandoned.append(
                    AbandonedNote(
                        path=record.relative_path,
                        last_modified=modified.date().isoformat(),
                        days_since_edit=days,
                        reason="Non modifiée depuis longtemps avec contenu minimal.",
                    )
                )
        return abandoned

    def _find_duplicates(
        self,
        records: list[_NoteRecord],
    ) -> tuple[list[DuplicateTopicGroup], list[MergeSuggestion]]:
        by_stem: dict[str, list[_NoteRecord]] = {}
        for record in records:
            by_stem.setdefault(record.stem, []).append(record)

        duplicated: list[DuplicateTopicGroup] = []
        merges: list[MergeSuggestion] = []

        for stem, group in by_stem.items():
            if len(group) > 1:
                paths = tuple(item.relative_path for item in group)
                duplicated.append(
                    DuplicateTopicGroup(
                        topic=stem,
                        notes=paths,
                        similarity=1.0,
                        recommendation=(
                            "Plusieurs notes partagent le même nom de fichier — "
                            "vérifier le dossier et fusionner manuellement si doublon."
                        ),
                    )
                )
                merges.append(
                    MergeSuggestion(
                        source_notes=paths,
                        reason=f"Noms identiques : {stem}",
                        recommendation=(
                            f"Fusionner le contenu dans une seule note « {stem} » "
                            "et rediriger les liens — action manuelle requise."
                        ),
                    )
                )

        for index, left in enumerate(records):
            for right in records[index + 1 :]:
                if left.relative_path == right.relative_path:
                    continue
                if left.stem == right.stem:
                    continue
                similarity = _content_similarity(left.body, right.body)
                if similarity < _DUPLICATE_SIMILARITY_THRESHOLD:
                    title_sim = SequenceMatcher(None, left.stem, right.stem).ratio()
                    if title_sim < 0.8:
                        continue
                    similarity = max(similarity, title_sim)
                if similarity >= _DUPLICATE_SIMILARITY_THRESHOLD:
                    topic = left.stem
                    duplicated.append(
                        DuplicateTopicGroup(
                            topic=topic,
                            notes=(left.relative_path, right.relative_path),
                            similarity=round(similarity, 2),
                            recommendation=(
                                "Contenu ou titre très similaire — comparer et fusionner "
                                "manuellement si redondant."
                            ),
                        )
                    )
                    merges.append(
                        MergeSuggestion(
                            source_notes=(left.relative_path, right.relative_path),
                            reason=f"Similarité {similarity:.0%}",
                            recommendation=(
                                f"Envisager fusion manuelle : garder la note la plus complète "
                                f"({left.relative_path} vs {right.relative_path})."
                            ),
                        )
                    )
        return duplicated, merges

    @staticmethod
    def _find_orphans(records: list[_NoteRecord]) -> list[str]:
        all_paths = {record.relative_path for record in records}
        stems = {Path(record.relative_path).stem.lower(): record.relative_path for record in records}
        linked: set[str] = set()
        for record in records:
            for target in record.wikilinks:
                normalized = target.replace("\\", "/").lower()
                if normalized in all_paths:
                    linked.add(normalized)
                    continue
                stem = Path(normalized).stem.lower()
                if stem in stems:
                    linked.add(stems[stem])
        orphans = [
            record.relative_path
            for record in records
            if record.relative_path not in linked and record.relative_path not in {
                "index.md",
                "readme.md",
                "home.md",
            }
        ]
        return orphans

    @staticmethod
    def _find_missing_tags(records: list[_NoteRecord]) -> list[MissingTagNote]:
        missing: list[MissingTagNote] = []
        for record in records:
            if record.word_count < 30:
                continue
            if record.tags:
                continue
            if record.relative_path in {"index.md", "readme.md"}:
                continue
            missing.append(
                MissingTagNote(
                    path=record.relative_path,
                    suggestion="Ajouter des tags YAML ou inline pour faciliter la recherche.",
                )
            )
        return missing

    @staticmethod
    def _find_folder_issues(records: list[_NoteRecord]) -> list[FolderIssue]:
        issues: list[FolderIssue] = []
        folder_topics: dict[str, set[str]] = {}
        for record in records:
            folder_topics.setdefault(record.folder or ".", set()).add(record.stem)

        project_like = {"projet", "project", "roadmap", "spec", "architecture"}
        for record in records:
            stem_tokens = set(re.findall(r"[\w-]+", record.stem))
            if not stem_tokens & project_like:
                continue
            if record.folder in ("", ".", "notes") and record.word_count > 40:
                issues.append(
                    FolderIssue(
                        path=record.relative_path,
                        current_folder=record.folder or ".",
                        issue="Note projet dans un dossier générique.",
                        recommendation="Déplacer vers projects/ ou un dossier thématique dédié.",
                    )
                )
        return issues

    @staticmethod
    def _find_naming_issues(records: list[_NoteRecord]) -> list[NamingIssue]:
        issues: list[NamingIssue] = []
        for record in records:
            name = Path(record.relative_path).name
            if " " in name:
                issues.append(
                    NamingIssue(
                        path=record.relative_path,
                        issue="Espaces dans le nom de fichier.",
                        recommendation="Préférer kebab-case (ex. mon-sujet.md).",
                    )
                )
            if name != name.lower() and not re.search(r"^[A-Z][a-z]+(?:-[a-z]+)*\.md$", name):
                if re.search(r"[A-Z]", name):
                    issues.append(
                        NamingIssue(
                            path=record.relative_path,
                            issue="Casse mixte incohérente.",
                            recommendation="Uniformiser en minuscules ou Title-Case cohérent.",
                        )
                    )
            if "__" in name or "--" in name:
                issues.append(
                    NamingIssue(
                        path=record.relative_path,
                        issue="Séparateurs répétés dans le nom.",
                        recommendation="Nettoyer le slug (un seul tiret entre mots).",
                    )
                )
        return issues


def _content_similarity(left: str, right: str) -> float:
    left_norm = re.sub(r"\s+", " ", left.lower()).strip()
    right_norm = re.sub(r"\s+", " ", right.lower()).strip()
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()
