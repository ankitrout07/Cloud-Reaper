"""Ollama local LLM backend implementation for Cloud-Reaper."""

from __future__ import annotations

import os
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from reaper.engine.ai_backends.base import EmbeddingBackend, GenerationBackend


class OllamaEmbeddingBackend(EmbeddingBackend):
    """Ollama-based embedding backend using local models."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ):
        """
        Initialize Ollama embedding backend.

        Args:
            base_url: Ollama server URL (default: from env or localhost:11434)
            model: Embedding model name (default: from env or nomic-embed-text)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for input text using Ollama."""
        try:
            response = self._client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("embedding", [])
        except httpx.HTTPError as e:
            raise RuntimeError(f"Ollama embedding request failed: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Ollama embedding error: {e}") from e

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for multiple texts."""
        embeddings = []
        for text in texts:
            embedding = self.embed_text(text)
            embeddings.append(embedding)
        return embeddings

    def health_check(self) -> bool:
        """Check if Ollama server is accessible and model is available."""
        try:
            # Check if Ollama server is running
            response = self._client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            
            # Check if the specific model is available
            models = response.json().get("models", [])
            model_names = [model.get("name", "").split(":")[0] for model in models]
            return self.model in model_names
        except Exception:
            return False

    def get_model_info(self) -> dict[str, str]:
        """Get information about the current embedding model."""
        return {
            "backend": "ollama",
            "model": self.model,
            "base_url": self.base_url,
        }


class OllamaGenerationBackend(GenerationBackend):
    """Ollama-based text generation backend using local models."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ):
        """
        Initialize Ollama generation backend.

        Args:
            base_url: Ollama server URL (default: from env or localhost:11434)
            model: Generation model name (default: from env or llama3.1)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.1")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
    ) -> str:
        """Generate text response for given prompt using Ollama."""
        try:
            # Build the prompt with system instruction if provided
            full_prompt = prompt
            if system_instruction:
                full_prompt = f"{system_instruction}\n\n{prompt}"

            # Prepare request payload
            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                },
            }

            # Add max_tokens if specified
            if max_tokens:
                payload["options"]["num_predict"] = max_tokens

            # Handle JSON response format if requested
            if response_format and response_format.get("type") == "json_object":
                payload["options"]["num_ctx"] = 4096  # Increase context for JSON
                full_prompt += "\n\nRespond ONLY with valid JSON, no markdown formatting."

            response = self._client.post(
                f"{self.base_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            
            # Extract response text
            response_text = data.get("response", "")
            
            # Clean up response if JSON format was requested
            if response_format and response_format.get("type") == "json_object":
                # Remove markdown code blocks if present
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0].strip()
            
            return response_text.strip()
        except httpx.HTTPError as e:
            raise RuntimeError(f"Ollama generation request failed: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Ollama generation error: {e}") from e

    def health_check(self) -> bool:
        """Check if Ollama server is accessible and model is available."""
        try:
            # Check if Ollama server is running
            response = self._client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            
            # Check if the specific model is available
            models = response.json().get("models", [])
            model_names = [model.get("name", "").split(":")[0] for model in models]
            return self.model in model_names
        except Exception:
            return False

    def get_model_info(self) -> dict[str, str]:
        """Get information about the current generation model."""
        return {
            "backend": "ollama",
            "model": self.model,
            "base_url": self.base_url,
        }


class OllamaBackendFactory:
    """Factory class for creating Ollama backend instances."""

    @staticmethod
    def create_embedding_backend(
        base_url: str | None = None,
        model: str | None = None,
    ) -> OllamaEmbeddingBackend:
        """Create an Ollama embedding backend instance."""
        return OllamaEmbeddingBackend(base_url=base_url, model=model)

    @staticmethod
    def create_generation_backend(
        base_url: str | None = None,
        model: str | None = None,
    ) -> OllamaGenerationBackend:
        """Create an Ollama generation backend instance."""
        return OllamaGenerationBackend(base_url=base_url, model=model)

    @staticmethod
    def check_ollama_available(base_url: str | None = None) -> bool:
        """Check if Ollama server is running and accessible."""
        try:
            url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False
