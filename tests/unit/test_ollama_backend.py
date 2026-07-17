"""Unit tests for Ollama backend integration."""

from __future__ import annotations

import os
import pytest
from unittest.mock import Mock, patch

from reaper.engine.ai_backends.ollama_backend import (
    OllamaEmbeddingBackend,
    OllamaGenerationBackend,
    OllamaBackendFactory,
)


class TestOllamaEmbeddingBackend:
    """Tests for Ollama embedding backend."""

    def test_initialization_with_defaults(self):
        """Test backend initialization with default values."""
        backend = OllamaEmbeddingBackend()
        assert backend.base_url == "http://localhost:11434"
        assert backend.model == "nomic-embed-text"
        assert backend.timeout == 30.0

    def test_initialization_with_custom_values(self):
        """Test backend initialization with custom values."""
        backend = OllamaEmbeddingBackend(
            base_url="http://custom:11434",
            model="custom-model",
            timeout=60.0,
        )
        assert backend.base_url == "http://custom:11434"
        assert backend.model == "custom-model"
        assert backend.timeout == 60.0

    def test_initialization_with_env_vars(self):
        """Test backend initialization with environment variables."""
        with patch.dict(os.environ, {
            "OLLAMA_BASE_URL": "http://env:11434",
            "OLLAMA_EMBEDDING_MODEL": "env-model",
        }):
            backend = OllamaEmbeddingBackend()
            assert backend.base_url == "http://env:11434"
            assert backend.model == "env-model"

    @patch("reaper.engine.ai_backends.ollama_backend.httpx.Client")
    def test_embed_text_success(self, mock_client):
        """Test successful text embedding."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json = Mock(return_value={"embedding": [0.1, 0.2, 0.3]})
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response

        backend = OllamaEmbeddingBackend()
        embedding = backend.embed_text("test text")

        assert embedding == [0.1, 0.2, 0.3]

    @patch("reaper.engine.ai_backends.ollama_backend.httpx.Client")
    def test_embed_text_failure(self, mock_client):
        """Test text embedding failure handling."""
        mock_client.return_value.__enter__.return_value.post.side_effect = Exception("Connection error")

        backend = OllamaEmbeddingBackend()
        with pytest.raises(RuntimeError, match="Ollama embedding error"):
            backend.embed_text("test text")

    @patch("reaper.engine.ai_backends.ollama_backend.httpx.Client")
    def test_health_check_success(self, mock_client):
        """Test successful health check."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json = Mock(return_value={
            "models": [
                {"name": "nomic-embed-text:latest"},
                {"name": "llama3.1:latest"},
            ]
        })
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        backend = OllamaEmbeddingBackend()
        assert backend.health_check() is True

    @patch("reaper.engine.ai_backends.ollama_backend.httpx.Client")
    def test_health_check_model_not_found(self, mock_client):
        """Test health check when model is not available."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json = Mock(return_value={
            "models": [
                {"name": "llama3.1:latest"},
            ]
        })
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        backend = OllamaEmbeddingBackend()
        assert backend.health_check() is False

    @patch("reaper.engine.ai_backends.ollama_backend.httpx.Client")
    def test_health_check_connection_failure(self, mock_client):
        """Test health check when connection fails."""
        mock_client.return_value.__enter__.return_value.get.side_effect = Exception("Connection error")

        backend = OllamaEmbeddingBackend()
        assert backend.health_check() is False

    def test_get_model_info(self):
        """Test getting model information."""
        backend = OllamaEmbeddingBackend(
            base_url="http://test:11434",
            model="test-model",
        )
        info = backend.get_model_info()
        assert info["backend"] == "ollama"
        assert info["model"] == "test-model"
        assert info["base_url"] == "http://test:11434"


class TestOllamaGenerationBackend:
    """Tests for Ollama generation backend."""

    def test_initialization_with_defaults(self):
        """Test backend initialization with default values."""
        backend = OllamaGenerationBackend()
        assert backend.base_url == "http://localhost:11434"
        assert backend.model == "llama3.1"
        assert backend.timeout == 60.0

    def test_initialization_with_custom_values(self):
        """Test backend initialization with custom values."""
        backend = OllamaGenerationBackend(
            base_url="http://custom:11434",
            model="custom-model",
            timeout=120.0,
        )
        assert backend.base_url == "http://custom:11434"
        assert backend.model == "custom-model"
        assert backend.timeout == 120.0

    def test_initialization_with_env_vars(self):
        """Test backend initialization with environment variables."""
        with patch.dict(os.environ, {
            "OLLAMA_BASE_URL": "http://env:11434",
            "OLLAMA_MODEL": "env-model",
        }):
            backend = OllamaGenerationBackend()
            assert backend.base_url == "http://env:11434"
            assert backend.model == "env-model"

    @patch("reaper.engine.ai_backends.ollama_backend.httpx.Client")
    def test_generate_text_success(self, mock_client):
        """Test successful text generation."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json = Mock(return_value={"response": "Generated text"})
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response

        backend = OllamaGenerationBackend()
        response = backend.generate_text("test prompt")

        assert response == "Generated text"

    @patch("reaper.engine.ai_backends.ollama_backend.httpx.Client")
    def test_generate_text_with_system_instruction(self, mock_client):
        """Test text generation with system instruction."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json = Mock(return_value={"response": "Generated text"})
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response

        backend = OllamaGenerationBackend()
        response = backend.generate_text(
            "test prompt",
            system_instruction="You are a helpful assistant",
        )

        assert response == "Generated text"

    @patch("reaper.engine.ai_backends.ollama_backend.httpx.Client")
    def test_generate_text_json_mode(self, mock_client):
        """Test text generation in JSON mode."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json = Mock(return_value={"response": '{"key": "value"}'})
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response

        backend = OllamaGenerationBackend()
        response = backend.generate_text(
            "test prompt",
            response_format={"type": "json_object"},
        )

        assert response == '{"key": "value"}'

    @patch("reaper.engine.ai_backends.ollama_backend.httpx.Client")
    def test_generate_text_failure(self, mock_client):
        """Test text generation failure handling."""
        mock_client.return_value.__enter__.return_value.post.side_effect = Exception("Connection error")

        backend = OllamaGenerationBackend()
        with pytest.raises(RuntimeError, match="Ollama generation error"):
            backend.generate_text("test prompt")

    @patch("reaper.engine.ai_backends.ollama_backend.httpx.Client")
    def test_health_check_success(self, mock_client):
        """Test successful health check."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json = Mock(return_value={
            "models": [
                {"name": "llama3.1:latest"},
                {"name": "nomic-embed-text:latest"},
            ]
        })
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        backend = OllamaGenerationBackend()
        assert backend.health_check() is True

    @patch("reaper.engine.ai_backends.ollama_backend.httpx.Client")
    def test_health_check_model_not_found(self, mock_client):
        """Test health check when model is not available."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json = Mock(return_value={
            "models": [
                {"name": "nomic-embed-text:latest"},
            ]
        })
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        backend = OllamaGenerationBackend()
        assert backend.health_check() is False

    def test_get_model_info(self):
        """Test getting model information."""
        backend = OllamaGenerationBackend(
            base_url="http://test:11434",
            model="test-model",
        )
        info = backend.get_model_info()
        assert info["backend"] == "ollama"
        assert info["model"] == "test-model"
        assert info["base_url"] == "http://test:11434"


class TestOllamaBackendFactory:
    """Tests for Ollama backend factory."""

    def test_create_embedding_backend(self):
        """Test creating embedding backend."""
        backend = OllamaBackendFactory.create_embedding_backend()
        assert isinstance(backend, OllamaEmbeddingBackend)

    def test_create_generation_backend(self):
        """Test creating generation backend."""
        backend = OllamaBackendFactory.create_generation_backend()
        assert isinstance(backend, OllamaGenerationBackend)

    def test_create_embedding_backend_with_params(self):
        """Test creating embedding backend with parameters."""
        backend = OllamaBackendFactory.create_embedding_backend(
            base_url="http://custom:11434",
            model="custom-model",
        )
        assert backend.base_url == "http://custom:11434"
        assert backend.model == "custom-model"

    def test_create_generation_backend_with_params(self):
        """Test creating generation backend with parameters."""
        backend = OllamaBackendFactory.create_generation_backend(
            base_url="http://custom:11434",
            model="custom-model",
        )
        assert backend.base_url == "http://custom:11434"
        assert backend.model == "custom-model"

    @patch("reaper.engine.ai_backends.ollama_backend.httpx.Client")
    def test_check_ollama_available_success(self, mock_client):
        """Test checking Ollama availability when available."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        assert OllamaBackendFactory.check_ollama_available() is True

    @patch("reaper.engine.ai_backends.ollama_backend.httpx.Client")
    def test_check_ollama_available_failure(self, mock_client):
        """Test checking Ollama availability when not available."""
        mock_client.return_value.__enter__.return_value.get.side_effect = Exception("Connection error")

        assert OllamaBackendFactory.check_ollama_available() is False


@pytest.mark.integration
class TestOllamaIntegration:
    """Integration tests for Ollama backend (requires running Ollama server)."""

    @pytest.mark.skipif(
        not os.getenv("OLLAMA_BASE_URL"),
        reason="Ollama not configured for integration tests"
    )
    def test_real_ollama_connection(self):
        """Test real connection to Ollama server."""
        backend = OllamaEmbeddingBackend()
        if backend.health_check():
            # If Ollama is available, test a real embedding
            embedding = backend.embed_text("test")
            assert len(embedding) > 0
        else:
            pytest.skip("Ollama server not healthy")

    @pytest.mark.skipif(
        not os.getenv("OLLAMA_BASE_URL"),
        reason="Ollama not configured for integration tests"
    )
    def test_real_ollama_generation(self):
        """Test real text generation from Ollama server."""
        backend = OllamaGenerationBackend()
        if backend.health_check():
            # If Ollama is available, test real generation
            response = backend.generate_text("Say hello", max_tokens=10)
            assert len(response) > 0
        else:
            pytest.skip("Ollama server not healthy")
