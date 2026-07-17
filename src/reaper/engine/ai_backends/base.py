"""Base AI backend interface for Cloud-Reaper AI operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class EmbeddingBackend(ABC):
    """Abstract base class for embedding backends."""

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for input text."""
        pass

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for multiple texts."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the embedding backend is healthy and accessible."""
        pass

    @abstractmethod
    def get_model_info(self) -> dict[str, str]:
        """Get information about the current model being used."""
        pass


class GenerationBackend(ABC):
    """Abstract base class for text generation backends."""

    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
    ) -> str:
        """Generate text response for given prompt."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the generation backend is healthy and accessible."""
        pass

    @abstractmethod
    def get_model_info(self) -> dict[str, str]:
        """Get information about the current model being used."""
        pass
