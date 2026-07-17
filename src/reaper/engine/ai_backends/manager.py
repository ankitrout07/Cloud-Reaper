"""Centralized AI backend manager for Cloud-Reaper."""

from __future__ import annotations

import os
from typing import Any

from reaper.engine.ai_backends.base import EmbeddingBackend, GenerationBackend
from reaper.engine.ai_backends.ollama_backend import OllamaBackendFactory


class AIBackendManager:
    """Centralized manager for AI backend selection and fallback logic."""

    def __init__(self):
        self._embedding_backend: EmbeddingBackend | None = None
        self._generation_backend: GenerationBackend | None = None
        self._backend_type = self._determine_backend()
        self._initialize_backends()

    def _determine_backend(self) -> str:
        """Determine which AI backend to use based on configuration."""
        ai_backend = os.getenv("AI_BACKEND", "gemini").lower()
        
        # Validate backend choice
        valid_backends = ["gemini", "openai", "ollama", "ensemble"]
        if ai_backend not in valid_backends:
            print(f"WARN: Invalid AI_BACKEND '{ai_backend}'. Defaulting to 'gemini'.")
            return "gemini"
        
        return ai_backend

    def _initialize_backends(self):
        """Initialize the selected AI backends with fallback logic."""
        backend_type = self._backend_type
        
        if backend_type == "ollama":
            # Try Ollama first
            try:
                self._embedding_backend = OllamaBackendFactory.create_embedding_backend()
                self._generation_backend = OllamaBackendFactory.create_generation_backend()
                
                # Health check
                if not self._embedding_backend.health_check():
                    print("WARN: Ollama embedding backend health check failed.")
                    self._embedding_backend = None
                if not self._generation_backend.health_check():
                    print("WARN: Ollama generation backend health check failed.")
                    self._generation_backend = None
                
                # If both failed, fall back to cloud APIs
                if not self._embedding_backend and not self._generation_backend:
                    print("WARN: Ollama backends unavailable, falling back to cloud APIs.")
                    self._initialize_cloud_backends()
            except Exception as e:
                print(f"WARN: Ollama initialization failed: {e}. Falling back to cloud APIs.")
                self._initialize_cloud_backends()
        
        elif backend_type == "ensemble":
            # Initialize Ollama if available, also prepare cloud APIs
            try:
                if OllamaBackendFactory.check_ollama_available():
                    self._embedding_backend = OllamaBackendFactory.create_embedding_backend()
                    self._generation_backend = OllamaBackendFactory.create_generation_backend()
                    print("INFO: Ollama backend available for ensemble mode.")
                else:
                    print("INFO: Ollama not available, ensemble will use cloud APIs only.")
            except Exception as e:
                print(f"WARN: Ollama ensemble initialization failed: {e}")
            
            # Always initialize cloud APIs for ensemble
            self._initialize_cloud_backends()
        
        else:
            # Use specific cloud backend (gemini/openai)
            self._initialize_cloud_backends()

    def _initialize_cloud_backends(self):
        """Initialize cloud API backends (Gemini/OpenAI)."""
        # This is handled by the individual classes that need cloud APIs
        # We just set them to None here and let the classes handle initialization
        pass

    def get_embedding_backend(self) -> EmbeddingBackend | None:
        """Get the configured embedding backend."""
        return self._embedding_backend

    def get_generation_backend(self) -> GenerationBackend | None:
        """Get the configured generation backend."""
        return self._generation_backend

    def get_backend_type(self) -> str:
        """Get the current backend type."""
        return self._backend_type

    def is_ollama_enabled(self) -> bool:
        """Check if Ollama backend is enabled and healthy."""
        return self._backend_type == "ollama" and self._embedding_backend is not None

    def is_ensemble_enabled(self) -> bool:
        """Check if ensemble mode is enabled."""
        return self._backend_type == "ensemble"

    def get_backend_info(self) -> dict[str, Any]:
        """Get information about current backend configuration."""
        info = {
            "backend_type": self._backend_type,
            "embedding_backend": None,
            "generation_backend": None,
        }
        
        if self._embedding_backend and hasattr(self._embedding_backend, 'get_model_info'):
            info["embedding_backend"] = self._embedding_backend.get_model_info()
        if self._generation_backend and hasattr(self._generation_backend, 'get_model_info'):
            info["generation_backend"] = self._generation_backend.get_model_info()
        
        return info


# Global instance for easy access
_global_backend_manager: AIBackendManager | None = None


def get_backend_manager() -> AIBackendManager:
    """Get the global AI backend manager instance."""
    global _global_backend_manager
    if _global_backend_manager is None:
        _global_backend_manager = AIBackendManager()
    return _global_backend_manager


def reset_backend_manager():
    """Reset the global backend manager (useful for testing)."""
    global _global_backend_manager
    _global_backend_manager = None
