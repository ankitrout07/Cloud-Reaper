"""Health check utilities for AI backends."""

from __future__ import annotations

import os
from typing import Any

import httpx


def check_cloud_api_health(api_type: str) -> dict[str, Any]:
    """
    Check cloud API health (Gemini, OpenAI, Claude).

    Args:
        api_type: Type of API to check (gemini, openai, claude)

    Returns:
        Dictionary with health status
    """
    health_info: dict[str, Any] = {
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
    Check health of all configured cloud AI backends.

    Returns:
        Dictionary with health status of all backends
    """
    ai_backend = os.getenv("AI_BACKEND", "gemini").lower()

    health_report: dict[str, Any] = {
        "configured_backend": ai_backend,
        "backends": {},
    }

    if ai_backend in ("gemini",):
        health_report["backends"]["gemini"] = check_cloud_api_health("gemini")

    if ai_backend in ("openai",):
        health_report["backends"]["openai"] = check_cloud_api_health("openai")

    return health_report
