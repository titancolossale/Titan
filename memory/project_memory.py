# =====================================
# Titan Project Memory
# =====================================

"""Project-scoped memory namespaces with user isolation (Phase 9 — P9-030)."""

from __future__ import annotations

from typing import Any

PROJECT_NAMESPACE_KEYS = ("goals", "notes", "learnings", "metadata")


def empty_namespace() -> dict[str, Any]:
    """Return a fresh project namespace block."""
    return {
        "goals": [],
        "notes": [],
        "learnings": [],
        "metadata": {},
    }


class ProjectMemoryStore:
    """Manages per-user project namespaces inside the long-term memory document."""

    def __init__(self, memory_document: dict) -> None:
        self._memory = memory_document

    def _ensure_user(self, user: str) -> dict:
        users = self._memory.setdefault("users", {})
        if user not in users:
            users[user] = {
                "role": "Utilisateur de Titan",
                "authority": "standard",
                "goals": [],
                "preferences": [],
                "active_projects": [],
                "projects": [],
                "notes": [],
                "project_namespaces": {},
            }
        user_data = users[user]
        user_data.setdefault("project_namespaces", {})
        return user_data

    def get_namespace(self, user: str, project_id: str) -> dict[str, Any]:
        """Return project namespace, creating empty block when missing."""
        user_data = self._ensure_user(user)
        namespaces = user_data["project_namespaces"]
        if project_id not in namespaces:
            namespaces[project_id] = empty_namespace()
        return namespaces[project_id]

    def write_note(self, user: str, project_id: str, content: str) -> None:
        """Append a note to a project namespace."""
        namespace = self.get_namespace(user, project_id)
        namespace["notes"].append(content.strip())

    def write_goal(self, user: str, project_id: str, content: str) -> None:
        """Append a goal to a project namespace."""
        namespace = self.get_namespace(user, project_id)
        namespace["goals"].append(content.strip())

    def write_learning(self, user: str, project_id: str, content: str) -> None:
        """Append a learning to a project namespace."""
        namespace = self.get_namespace(user, project_id)
        namespace["learnings"].append(content.strip())

    def get_all_items(
        self,
        user: str,
        project_id: str,
    ) -> list[tuple[str, str]]:
        """Return labeled items for retrieval scoring."""
        namespace = self.get_namespace(user, project_id)
        items: list[tuple[str, str]] = []
        for key in ("goals", "notes", "learnings"):
            for item in namespace.get(key, []):
                if str(item).strip():
                    items.append((key, str(item)))
        return items

    def format_namespace(self, user: str, project_id: str) -> str:
        """Return formatted project memory for display."""
        namespace = self.get_namespace(user, project_id)
        lines = [f"Mémoire projet « {project_id} » ({user}) :"]
        sections = (
            ("Objectifs", "goals"),
            ("Notes", "notes"),
            ("Apprentissages", "learnings"),
        )
        has_content = False
        for label, key in sections:
            entries = namespace.get(key, [])
            if not entries:
                continue
            has_content = True
            lines.append(f"{label} :")
            for entry in entries:
                lines.append(f"  - {entry}")
        if not has_content:
            return f"Aucune mémoire projet pour « {project_id} »."
        return "\n".join(lines)
