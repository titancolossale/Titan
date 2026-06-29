# =====================================
# Titan Memory Retriever
# =====================================

"""Relevance engine for long-term memory prompt injection (Phase 3 — P3-023)."""

from __future__ import annotations

from memory.models import RetrievalResult

NO_MATCH_MESSAGE = "Aucune mémoire pertinente trouvée."

CATEGORY_WEIGHTS: dict[str, int] = {
    "goal": 3,
    "objectif": 3,
    "préférence": 2,
    "preference": 2,
    "projet": 2,
    "project": 2,
    "note": 1,
}


class MemoryRetriever:
    """Filter and rank memory items relevant to a user message."""

    def retrieve(
        self,
        memory: dict,
        message: str,
        *,
        user: str | None = None,
    ) -> str:
        """Return formatted relevant memory text (legacy string API)."""
        result = self.retrieve_for_user(memory, message, user=user)
        return result.text

    def retrieve_for_user(
        self,
        memory: dict,
        message: str,
        *,
        user: str | None = None,
        project_id: str | None = None,
    ) -> RetrievalResult:
        """Return structured retrieval filtered by user and optional project (P9-030)."""
        message_lower = message.lower()
        keywords = self._extract_keywords(message_lower)
        scored_items: list[tuple[int, str]] = []

        users = memory.get("users", {})
        target_users = {user: users[user]} if user and user in users else users

        for user_name, user_data in target_users.items():
            for label, items in self._iter_user_items(user_name, user_data):
                for item in items:
                    score = self._score_item(label, item, keywords, message_lower)
                    if score > 0:
                        scored_items.append((score, item))

            if project_id:
                scored_items.extend(
                    self._score_project_namespace(
                        user_name,
                        user_data,
                        project_id,
                        keywords,
                        message_lower,
                    ),
                )

        titan_data = memory.get("titan", {})
        for key, value in titan_data.items():
            if key.lower() in message_lower or str(value).lower() in message_lower:
                line = f"Titan {key} : {value}"
                scored_items.append((2, line))

        if not scored_items:
            return RetrievalResult(text=NO_MATCH_MESSAGE, items=[], user=user or "")

        scored_items.sort(key=lambda pair: pair[0], reverse=True)
        unique_items: list[str] = []
        seen: set[str] = set()
        for _, item in scored_items:
            if item in seen:
                continue
            seen.add(item)
            unique_items.append(item)

        return RetrievalResult(
            text="\n".join(unique_items),
            items=unique_items,
            user=user or "",
        )

    def _iter_user_items(
        self,
        user_name: str,
        user_data: dict,
    ) -> list[tuple[str, list[str]]]:
        """Yield labeled item groups for a user profile."""
        sections = (
            ("objectif", user_data.get("goals", [])),
            ("préférence", user_data.get("preferences", [])),
            ("projet actif", user_data.get("active_projects", [])),
            ("projet", user_data.get("projects", [])),
            ("note", user_data.get("notes", [])),
        )
        result: list[tuple[str, list[str]]] = []
        for label, items in sections:
            formatted = [
                f"{user_name} {label} : {item}"
                for item in items
                if str(item).strip()
            ]
            if formatted:
                result.append((label, formatted))
        return result

    def _extract_keywords(self, message_lower: str) -> list[str]:
        """Return message tokens longer than three characters."""
        return [word for word in message_lower.split() if len(word) > 3]

    def _score_item(
        self,
        label: str,
        item: str,
        keywords: list[str],
        message_lower: str,
    ) -> int:
        """Score an item by keyword overlap and category weight."""
        item_lower = item.lower()
        score = 0
        matched = False

        for word in keywords:
            if word in item_lower:
                score += 2
                matched = True

        if not matched:
            return 0

        label_key = label.split()[0]
        score += CATEGORY_WEIGHTS.get(label_key, 1)

        if label_key in message_lower:
            score += CATEGORY_WEIGHTS.get(label_key, 1)

        return score

    def _score_project_namespace(
        self,
        user_name: str,
        user_data: dict,
        project_id: str,
        keywords: list[str],
        message_lower: str,
    ) -> list[tuple[int, str]]:
        """Score items from a project namespace when project_id is active."""
        namespaces = user_data.get("project_namespaces", {})
        namespace = namespaces.get(project_id, {})
        if not namespace:
            return []

        scored: list[tuple[int, str]] = []
        sections = (
            ("objectif projet", namespace.get("goals", [])),
            ("note projet", namespace.get("notes", [])),
            ("apprentissage projet", namespace.get("learnings", [])),
        )
        for label, items in sections:
            for item in items:
                formatted = f"{user_name} {label} [{project_id}] : {item}"
                score = self._score_item(label, formatted, keywords, message_lower)
                if score > 0:
                    scored.append((score + 1, formatted))
        return scored
