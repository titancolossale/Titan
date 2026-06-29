# =====================================
# Titan Memory Decider
# =====================================

"""Decides whether a user message should be persisted to long-term memory."""

from __future__ import annotations

import re

EXPLICIT_REMEMBER_PHRASES = (
    "souviens-toi",
    "rappelle-toi",
    "remember",
    "garde en mémoire",
    "mets en mémoire",
)

PREFERENCE_PHRASES = (
    "mon objectif",
    "ma préférence",
    "j'aime",
    "je préfère",
)

EXPLICIT_REMEMBER_PATTERN = re.compile(
    r"(?:souviens-toi de|rappelle-toi de|remember)\s+(.+)",
    re.IGNORECASE,
)

FORGET_PATTERN = re.compile(
    r"(?:oublie|forget)\s+(.+)",
    re.IGNORECASE,
)

SHOW_MEMORY_PHRASES = (
    "montre ma mémoire",
    "montre-moi ma mémoire",
    "show my memory",
    "affiche ma mémoire",
)


class MemoryDecider:
    """Gate and classify memory writes with user attribution (P3-020)."""

    def should_remember(self, message: str) -> bool:
        """Return True only for explicit remember triggers (P3-021)."""
        message_lower = message.lower().strip()

        if self.parse_remember_content(message) is not None:
            return True

        for phrase in EXPLICIT_REMEMBER_PHRASES:
            if phrase in message_lower:
                return True

        for phrase in PREFERENCE_PHRASES:
            if phrase in message_lower:
                return True

        return False

    def resolve_user(self, message: str, session_user: str) -> str:
        """Resolve target user from message content or session default."""
        classified = self.classify_memory(message)
        if classified in ("Nolan", "Ibrahim"):
            return classified
        return session_user

    def classify_memory(self, message: str) -> str:
        """Detect whether message refers to Nolan, Ibrahim, or Titan metadata."""
        message_lower = message.lower()

        if "ibrahim" in message_lower:
            return "Ibrahim"

        if "nolan" in message_lower:
            return "Nolan"

        if "titan" in message_lower:
            return "titan"

        return "general"

    def is_show_memory_command(self, message: str) -> bool:
        """Return True when user asks to display their stored memory."""
        message_lower = message.lower().strip()
        return any(phrase in message_lower for phrase in SHOW_MEMORY_PHRASES)

    def parse_remember_content(self, message: str) -> str | None:
        """Extract explicit remember payload from souviens-toi de / remember."""
        match = EXPLICIT_REMEMBER_PATTERN.search(message.strip())
        if not match:
            return None
        content = match.group(1).strip()
        return content or None

    def parse_forget_query(self, message: str) -> str | None:
        """Extract forget target from oublie / forget commands."""
        match = FORGET_PATTERN.search(message.strip())
        if not match:
            return None
        content = match.group(1).strip()
        return content or None
