# =====================================
# Titan Memory Manager
# =====================================

from memory.memory import Memory


class MemoryManager:

    def __init__(self):
        self.memory = Memory()

    def remember(self, information):
        self.memory.remember(information)

    def show_memory(self):
        self.memory.show_memory()

    def get_notes(self) -> list[str]:
        """Return a copy of short-term session notes."""
        return list(self.memory.short_term)