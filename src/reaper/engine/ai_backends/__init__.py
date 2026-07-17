"""AI backend implementations for Cloud-Reaper."""

from reaper.engine.ai_backends.base import EmbeddingBackend, GenerationBackend
from reaper.engine.ai_backends.manager import AIBackendManager, get_backend_manager, reset_backend_manager
from reaper.engine.ai_backends.ollama_backend import (
    OllamaBackendFactory,
    OllamaEmbeddingBackend,
    OllamaGenerationBackend,
)

__all__ = [
    "EmbeddingBackend",
    "GenerationBackend",
    "AIBackendManager",
    "get_backend_manager",
    "reset_backend_manager",
    "OllamaBackendFactory",
    "OllamaEmbeddingBackend",
    "OllamaGenerationBackend",
]
