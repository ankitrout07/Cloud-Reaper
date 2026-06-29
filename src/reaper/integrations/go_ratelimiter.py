"""
Go Rate Limiter Bridge
Provides Python interface to the Go-based token bucket rate limiting system
"""

import asyncio
from typing import Any

from reaper.integrations.go_bridge_base import (
    BaseGoBridge,
    GoBridgeError,
    create_bridge_client,
)


class GoRateLimiter(BaseGoBridge):
    """
    Python bridge to the Go-based token bucket rate limiter.
    Communicates with the Go HTTP server for rate limiting operations.
    """

    def __init__(self, host: str = "localhost", port: int = 7073, timeout: float = 30.0):
        super().__init__(host=host, port=port, timeout=timeout)
        self._cache: dict[str, float] = {}  # Cache for rate limit decisions

    async def allow(self, key: str | None = None) -> bool:
        """
        Check if a request is allowed under the rate limit.

        Args:
            key: Optional rate limiter key (for multi-limiter)

        Returns:
            True if request is allowed
        """
        if not self.enabled:
            return True  # Fallback to allowing all requests

        endpoint = f"/api/ratelimit/check/{key}" if key else "/api/ratelimit/check"

        try:
            data = await self._make_request("GET", endpoint)
            return data.get("allowed", True)
        except GoBridgeError as e:
            print(f"[Go Rate Limiter] Error checking rate limit: {e}")
            return True  # Fallback to allowing all requests

    async def wait(self, key: str | None = None) -> float:
        """
        Wait until rate limit allows proceeding.

        Args:
            key: Optional rate limiter key (for multi-limiter)

        Returns:
            Wait duration in milliseconds
        """
        if not self.enabled:
            return 0.0

        try:
            data = await self._make_request("POST", "/api/ratelimit/wait")
            return data.get("wait_duration_ms", 0.0)
        except GoBridgeError as e:
            print(f"[Go Rate Limiter] Error waiting for rate limit: {e}")
            return 0.0

    async def get_statistics(self, key: str | None = None) -> dict[str, Any]:
        """
        Get rate limiter statistics.

        Args:
            key: Optional rate limiter key (for multi-limiter)

        Returns:
            Dictionary with statistics
        """
        if not self.enabled:
            return {}

        try:
            data = await self._make_request("GET", "/api/ratelimit/stats")
            if key and "all" in data:
                return data["all"].get(key, {})
            return data.get("default", {})
        except GoBridgeError as e:
            print(f"[Go Rate Limiter] Error getting statistics: {e}")
            return {}

    async def update_config(
        self,
        key: str | None = None,
        requests_per_second: float | None = None,
        burst_size: int | None = None,
    ) -> dict[str, Any]:
        """
        Update rate limiter configuration.

        Args:
            key: Optional rate limiter key (for multi-limiter)
            requests_per_second: New rate limit
            burst_size: New burst size

        Returns:
            Updated configuration
        """
        if not self.enabled:
            return {}

        payload = {}
        if key:
            payload["key"] = key
        if requests_per_second is not None:
            payload["requests_per_second"] = requests_per_second
        if burst_size is not None:
            payload["burst_size"] = burst_size

        if not payload:
            return await self.get_statistics(key)

        try:
            return await self._make_request("POST", "/api/ratelimit/config", json_data=payload)
        except GoBridgeError as e:
            print(f"[Go Rate Limiter] Error updating config: {e}")
            return {}

    async def reset(self, key: str) -> bool:
        """
        Reset a specific rate limiter.

        Args:
            key: Rate limiter key to reset

        Returns:
            True if reset was successful
        """
        if not self.enabled:
            return False

        try:
            data = await self._make_request("POST", f"/api/ratelimit/reset/{key}")
            return data.get("success", False)
        except GoBridgeError as e:
            print(f"[Go Rate Limiter] Error resetting rate limiter: {e}")
            return False


# Singleton instances for easy access
_global_rate_limiter: GoRateLimiter | None = None
_rate_limiters: dict[str, GoRateLimiter] = {}
_rate_limiter_lock = asyncio.Lock()


async def get_rate_limiter(host: str = "localhost", port: int = 7073) -> GoRateLimiter:
    """Get the singleton rate limiter instance"""
    global _global_rate_limiter

    async with _rate_limiter_lock:
        if _global_rate_limiter is None:
            _global_rate_limiter = create_bridge_client(
                GoRateLimiter, "ratelimiter", host=host, port=port
            )
        return _global_rate_limiter


async def get_azure_rate_limiter() -> GoRateLimiter:
    """Get rate limiter for Azure API calls"""
    return await get_rate_limiter()


async def get_aws_rate_limiter() -> GoRateLimiter:
    """Get rate limiter for AWS API calls"""
    return await get_rate_limiter()


async def get_gcp_rate_limiter() -> GoRateLimiter:
    """Get rate limiter for GCP API calls"""
    return await get_rate_limiter()


async def get_ai_rate_limiter() -> GoRateLimiter:
    """Get rate limiter for AI API calls"""
    return await get_rate_limiter()


# Convenience functions for common operations
async def allow_azure_request() -> bool:
    """
    Check if Azure API request is allowed.

    Returns:
        True if request is allowed under rate limit
    """
    limiter = await get_azure_rate_limiter()
    return await limiter.allow("azure")


async def allow_aws_request() -> bool:
    """
    Check if AWS API request is allowed.

    Returns:
        True if request is allowed under rate limit
    """
    limiter = await get_aws_rate_limiter()
    return await limiter.allow("aws")


async def allow_gcp_request() -> bool:
    """
    Check if GCP API request is allowed.

    Returns:
        True if request is allowed under rate limit
    """
    limiter = await get_gcp_rate_limiter()
    return await limiter.allow("gcp")


async def allow_ai_request() -> bool:
    """
    Check if AI API request is allowed.

    Returns:
        True if request is allowed under rate limit
    """
    limiter = await get_ai_rate_limiter()
    return await limiter.allow("ai")


async def wait_for_rate_limit(key: str | None = None) -> float:
    """
    Wait until rate limit allows proceeding.

    Args:
        key: Optional rate limiter key

    Returns:
        Wait duration in milliseconds
    """
    limiter = await get_rate_limiter()
    return await limiter.wait(key)
