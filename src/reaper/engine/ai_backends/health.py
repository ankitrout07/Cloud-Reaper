"""Health check utilities for AI backends."""

from __future__ import annotations

import os
from typing import Any

import httpx


def check_ollama_health(base_url: str | None = None, timeout: float = 5.0) -> dict[str, Any]:
    """
    Check Ollama server health and available models.
    
    Args:
        base_url: Ollama server URL (default: from env or localhost:11434)
        timeout: Request timeout in seconds
        
    Returns:
        Dictionary with health status and available models
    """
    url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    
    health_info = {
        "status": "unhealthy",
        "backend": "ollama",
        "base_url": url,
        "models": [],
        "error": None,
    }
    
    try:
        with httpx.Client(timeout=timeout) as client:
            # Check if server is running
            response = client.get(f"{url}/api/tags")
            response.raise_for_status()
            
            # Get available models
            data = response.json()
            models = data.get("models", [])
            
            health_info["status"] = "healthy"
            health_info["models"] = [
                {
                    "name": model.get("name"),
                    "size": model.get("size"),
                    "modified_at": model.get("modified_at"),
                }
                for model in models
            ]
            
            # Check if required models are available
            embedding_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
            generation_model = os.getenv("OLLAMA_MODEL", "llama3.1")
            
            model_names = [model.get("name", "").split(":")[0] for model in models]
            health_info["has_embedding_model"] = embedding_model in model_names
            health_info["has_generation_model"] = generation_model in model_names
            
    except httpx.ConnectError as e:
        health_info["error"] = f"Connection failed: {e}"
    except httpx.TimeoutException:
        health_info["error"] = "Connection timeout"
    except Exception as e:
        health_info["error"] = str(e)
    
    return health_info


def check_cloud_api_health(api_type: str) -> dict[str, Any]:
    """
    Check cloud API health (Gemini, OpenAI, etc.).
    
    Args:
        api_type: Type of API to check (gemini, openai, claude)
        
    Returns:
        Dictionary with health status
    """
    health_info = {
        "status": "unhealthy",
        "backend": api_type,
        "error": None,
    }
    
    try:
        if api_type == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key or api_key == "your_gemini_api_key_here":
                health_info["error"] = "API key not configured"
                return health_info
            
            # Try to list models
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url)
                if response.status_code == 200:
                    health_info["status"] = "healthy"
                else:
                    health_info["error"] = f"API returned status {response.status_code}"
        
        elif api_type == "openai":
            from openai import OpenAI
            
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key or api_key == "your_openai_api_key_here":
                health_info["error"] = "API key not configured"
                return health_info
            
            try:
                client = OpenAI(api_key=api_key)
                client.models.list()
                health_info["status"] = "healthy"
            except Exception as e:
                health_info["error"] = str(e)
        
        elif api_type == "claude":
            from anthropic import Anthropic
            
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key or api_key == "your_anthropic_api_key_here":
                health_info["error"] = "API key not configured"
                return health_info
            
            try:
                client = Anthropic(api_key=api_key)
                client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=10,
                    messages=[{"role": "user", "content": "test"}],
                )
                health_info["status"] = "healthy"
            except Exception as e:
                health_info["error"] = str(e)
        
        else:
            health_info["error"] = f"Unknown API type: {api_type}"
    
    except Exception as e:
        health_info["error"] = str(e)
    
    return health_info


def check_all_ai_backends() -> dict[str, Any]:
    """
    Check health of all configured AI backends.
    
    Returns:
        Dictionary with health status of all backends
    """
    ai_backend = os.getenv("AI_BACKEND", "gemini").lower()
    
    health_report = {
        "configured_backend": ai_backend,
        "backends": {},
    }
    
    # Check Ollama if configured or if ensemble mode
    if ai_backend in ["ollama", "ensemble"]:
        health_report["backends"]["ollama"] = check_ollama_health()
    
    # Check cloud APIs
    if ai_backend in ["gemini", "ensemble"]:
        health_report["backends"]["gemini"] = check_cloud_api_health("gemini")
    
    if ai_backend in ["openai", "ensemble"]:
        health_report["backends"]["openai"] = check_cloud_api_health("openai")
    
    if ai_backend in ["ensemble"]:
        health_report["backends"]["claude"] = check_cloud_api_health("claude")
    
    return health_report
