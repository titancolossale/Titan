# =====================================
# Titan LLM Provider Interface
# =====================================

"""Abstract LLM gateway — enables multi-provider support in later phases."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Contract for all Titan LLM backends."""

    @abstractmethod
    def ask(self, prompt: str) -> str:
        """Send a user prompt and return the model's text response."""

    @property
    @abstractmethod
    def system_instructions(self) -> str:
        """Return the assembled system instructions sent to the provider."""
