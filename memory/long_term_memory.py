# =====================================
# Titan Long Term Memory
# =====================================

"""JSON-backed durable memory persistence for Titan users and global metadata."""

from __future__ import annotations

import json
from pathlib import Path

from memory.memory_migrator import default_schema, migrate

VALID_CATEGORIES = frozenset({"goals", "preferences", "projects", "notes"})


class LongTermMemory:
    """Load, migrate, and persist the long-term memory JSON document."""

    def __init__(self, file_path: str | Path = "data/long_term_memory.json") -> None:
        self.file_path = Path(file_path)
        self.memory = self.load_memory()

    def load_memory(self) -> dict:
        """Load memory from disk, applying schema migration when needed."""
        if not self.file_path.exists():
            return default_schema()

        with self.file_path.open("r", encoding="utf-8") as file:
            raw = json.load(file)

        migrated = migrate(raw)
        if migrated != raw:
            self.memory = migrated
            self.save_memory()

        return migrated

    def save_memory(self) -> None:
        """Persist the in-memory document to disk."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        with self.file_path.open("w", encoding="utf-8") as file:
            json.dump(self.memory, file, indent=4, ensure_ascii=False)

    def get_memory(self) -> dict:
        """Return the full memory document."""
        return self.memory

    def remember(self, category: str, key: str, value: str) -> None:
        """Store a top-level keyed value (legacy API)."""
        if category not in self.memory:
            self.memory[category] = {}

        self.memory[category][key] = value
        self.save_memory()

    def show_memory(self) -> str:
        """Return the full document as a formatted JSON string."""
        return json.dumps(self.memory, indent=4, ensure_ascii=False)

    def _ensure_user(self, user: str) -> dict:
        """Return user block, creating defaults when missing."""
        if "users" not in self.memory:
            self.memory["users"] = {}

        if user not in self.memory["users"]:
            self.memory["users"][user] = {
                "role": "Utilisateur de Titan",
                "authority": "standard",
                "goals": [],
                "preferences": [],
                "active_projects": [],
                "projects": [],
                "notes": [],
            }

        user_data = self.memory["users"][user]
        for key in ("goals", "preferences", "active_projects", "projects", "notes"):
            user_data.setdefault(key, [])

        return user_data

    def write_categorized(self, user: str, category: str, content: str) -> None:
        """Append content to the user's typed category array (P3-012)."""
        if category not in VALID_CATEGORIES:
            raise ValueError(f"Invalid memory category: {category}")

        user_data = self._ensure_user(user)
        user_data[category].append(content)
        self.save_memory()

    def remember_user_note(self, user: str, note: str) -> None:
        """Legacy write path — delegates to categorized notes storage."""
        self.write_categorized(user, "notes", note)

    def forget_matching(self, user: str, query: str) -> int:
        """Remove memory items containing query (case-insensitive). Returns count removed."""
        user_data = self._ensure_user(user)
        query_lower = query.lower()
        removed = 0

        for key in ("goals", "preferences", "projects", "notes"):
            original = user_data[key]
            kept = [
                item for item in original
                if query_lower not in str(item).lower()
            ]
            removed += len(original) - len(kept)
            user_data[key] = kept

        if removed:
            self.save_memory()

        return removed

    def get_user_memory_text(self, user: str) -> str:
        """Return formatted memory summary for a single user."""
        users = self.memory.get("users", {})
        if user not in users:
            return f"Aucune mémoire enregistrée pour {user}."

        user_data = users[user]
        lines: list[str] = [f"Mémoire de {user} :", ""]

        sections = (
            ("Objectifs", "goals"),
            ("Préférences", "preferences"),
            ("Projets actifs", "active_projects"),
            ("Mémoires projet", "projects"),
            ("Notes", "notes"),
        )
        for label, key in sections:
            items = user_data.get(key, [])
            if not items:
                continue
            lines.append(f"{label} :")
            for item in items:
                lines.append(f"  - {item}")
            lines.append("")

        if len(lines) <= 2:
            return f"Aucune mémoire enregistrée pour {user}."

        return "\n".join(lines).strip()
