# =====================================
# Titan Memory Service
# =====================================

"""Unified memory facade — sole entry point for Brain and composition root (P3-011)."""

from __future__ import annotations

from memory.long_term_memory import LongTermMemory
from memory.memory_classifier import MemoryClassifier
from memory.memory_decider import MemoryDecider
from memory.memory_manager import MemoryManager
from memory.memory_retriever import MemoryRetriever
from memory.models import RetrievalResult
from memory.project_memory import ProjectMemoryStore


class MemoryService:
    """Orchestrates short-term notes, long-term persistence, and retrieval."""

    def __init__(
        self,
        short_term: MemoryManager,
        long_term: LongTermMemory,
        decider: MemoryDecider | None = None,
        classifier: MemoryClassifier | None = None,
        retriever: MemoryRetriever | None = None,
    ) -> None:
        self._short_term = short_term
        self._long_term = long_term
        self._decider = decider or MemoryDecider()
        self._classifier = classifier or MemoryClassifier()
        self._retriever = retriever or MemoryRetriever()

    @property
    def long_term(self) -> LongTermMemory:
        """Expose long-term store for composition-root identity checks."""
        return self._long_term

    def remember_session(self, note: str) -> None:
        """Store a session note in short-term memory."""
        self._short_term.remember(note)

    def get_session_notes(self) -> list[str]:
        """Return short-term session notes for Memory Agent summarization (P5-050)."""
        return self._short_term.get_notes()

    def store_categorized(self, user: str, category: str, content: str) -> None:
        """Persist a categorized note to long-term memory."""
        self._long_term.write_categorized(user, category, content)

    def show_session_memory(self) -> None:
        """Display short-term session notes."""
        self._short_term.show_memory()

    def get_document(self) -> dict:
        """Return the full long-term memory document."""
        return self._long_term.get_memory()

    def get_long_term(self) -> dict:
        """Backward-compatible alias for get_document() (P1-122)."""
        return self.get_document()

    def retrieve(
        self,
        user: str,
        message: str,
        project_id: str | None = None,
    ) -> RetrievalResult:
        """Retrieve relevant long-term memory for prompt injection (P3-022, P9-030)."""
        memory = self._long_term.get_memory()
        return self._retriever.retrieve_for_user(
            memory,
            message,
            user=user,
            project_id=project_id,
        )

    def write_project_note(self, user: str, project_id: str, content: str) -> None:
        """Persist a note to a project namespace (P9-030)."""
        store = ProjectMemoryStore(self._long_term.get_memory())
        store.write_note(user, project_id, content)
        self._long_term.save_memory()

    def get_project_memory_text(self, user: str, project_id: str) -> str:
        """Return formatted project-scoped memory."""
        store = ProjectMemoryStore(self._long_term.get_memory())
        return store.format_namespace(user, project_id)

    def maybe_remember(self, user: str, message: str) -> bool:
        """Run decider + classifier pipeline; persist when appropriate."""
        target_user = self._decider.resolve_user(message, user)

        explicit_content = self._decider.parse_remember_content(message)
        if explicit_content is not None:
            category = self._classifier.classify(explicit_content)
            self._long_term.write_categorized(target_user, category, explicit_content)
            return True

        if not self._decider.should_remember(message):
            return False

        category = self._classifier.classify(message)
        self._long_term.write_categorized(target_user, category, message)
        return True

    def handle_command(self, user: str, message: str) -> str | None:
        """Handle explicit memory commands; return response or None (P3-030)."""
        if self._decider.is_show_memory_command(message):
            return self._long_term.get_user_memory_text(user)

        forget_query = self._decider.parse_forget_query(message)
        if forget_query is not None:
            removed = self._long_term.forget_matching(user, forget_query)
            if removed:
                return f"C'est fait — j'ai retiré {removed} élément(s) contenant « {forget_query} »."
            return f"Je n'ai rien trouvé contenant « {forget_query} » dans ta mémoire."

        explicit_content = self._decider.parse_remember_content(message)
        if explicit_content is not None:
            target_user = self._decider.resolve_user(message, user)
            category = self._classifier.classify(explicit_content)
            self._long_term.write_categorized(target_user, category, explicit_content)
            return f"C'est noté — je retiendrai : {explicit_content}"

        return None

    def remember_conversation_summary(self, user: str, summary: str) -> bool:
        """Persist extractive session summary to long-term notes (P7-050)."""
        cleaned = summary.strip()
        if not cleaned:
            return False
        self._long_term.write_categorized(user, "notes", f"[session] {cleaned}")
        return True
