"""
Go Bridge Base Module
Provides a unified base class for all Go bridge clients to reduce code duplication
and standardize error handling, configuration, and HTTP client management.
"""

import asyncio
import os
from abc import ABC
from typing import Any

import httpx


class GoBridgeError(Exception):
    """Base exception for Go bridge errors"""

    pass


class GoBridgeConnectionError(GoBridgeError):
    """Exception raised when connection to Go bridge fails"""

    pass


class GoBridgeTimeoutError(GoBridgeError):
    """Exception raised when Go bridge request times out"""

    pass


class GoBridgeResponseError(GoBridgeError):
    """Exception raised when Go bridge returns an error response"""

    pass


class BaseGoBridge(ABC):
    """
    Base class for Go bridge clients.
    Provides common functionality for HTTP client management, error handling,
    and configuration management.
    """

    def __init__(
        self, host: str = "localhost", port: int = 7070, timeout: float = 30.0, enabled: bool = True
    ):
        """
        Initialize the Go bridge client.

        Args:
            host: Go bridge server host
            port: Go bridge server port
            timeout: HTTP request timeout in seconds
            enabled: Whether the bridge is enabled (falls back if disabled)
        """
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self._enabled = enabled
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        """
        Get or create HTTP client with thread-safe initialization.

        Returns:
            HTTP client instance
        """
        async with self._client_lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(timeout=self.timeout)
            return self._client

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make an HTTP request to the Go bridge with standardized error handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON request body

        Returns:
            Response data as dictionary

        Raises:
            GoBridgeConnectionError: If connection fails
            GoBridgeTimeoutError: If request times out
            GoBridgeResponseError: If bridge returns error response
        """
        if not self._enabled:
            raise GoBridgeError(f"{self.__class__.__name__} is disabled")

        try:
            client = await self._get_client()
            url = f"{self.base_url}{endpoint}"

            response = await client.request(method, url, params=params, json=json_data)

            # Handle HTTP errors
            if response.status_code == 404:
                raise GoBridgeResponseError(f"Endpoint not found: {endpoint}")
            if response.status_code >= 500:
                raise GoBridgeConnectionError(f"Server error: {response.status_code}")

            response.raise_for_status()

            data = response.json()

            # Check for application-level errors
            if not data.get("success"):
                error_msg = data.get("error", "Unknown error")
                raise GoBridgeResponseError(error_msg)

            return data.get("data", {})

        except httpx.TimeoutException as e:
            self._enabled = False
            raise GoBridgeTimeoutError(f"Request timed out: {e}")
        except httpx.ConnectError as e:
            self._enabled = False
            raise GoBridgeConnectionError(f"Connection failed: {e}")
        except httpx.HTTPStatusError as e:
            self._enabled = False
            raise GoBridgeResponseError(f"HTTP error: {e}")
        except GoBridgeError:
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            self._enabled = False
            raise GoBridgeError(f"Unexpected error: {e}")

    async def _make_request_safe(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        default_return: Any | None = None,
    ) -> Any:
        """
        Make a request with safe error handling - returns default on error instead of raising.

        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            json_data: JSON request body
            default_return: Value to return on error

        Returns:
            Response data or default_return on error
        """
        try:
            return await self._make_request(method, endpoint, params, json_data)
        except GoBridgeError as e:
            print(f"[{self.__class__.__name__}] Request failed: {e}")
            return default_return

    async def health_check(self) -> bool:
        """
        Check if the Go bridge server is healthy.

        Returns:
            True if server is healthy
        """
        try:
            await self._make_request("GET", "/health")
            return True
        except GoBridgeError:
            return False

    @property
    def enabled(self) -> bool:
        """Check if bridge is enabled"""
        return self._enabled

    def enable(self):
        """Enable the bridge"""
        self._enabled = True

    def disable(self):
        """Disable the bridge (falls back to alternative implementation)"""
        self._enabled = False

    async def close(self):
        """Close the HTTP client connection"""
        async with self._client_lock:
            if self._client and not self._client.is_closed:
                await self._client.aclose()
                self._client = None

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()


class GoBridgeConfig:
    """
    Configuration manager for Go bridges.
    Centralizes configuration from environment variables and defaults.
    """

    # Default ports for different Go services
    DEFAULT_PORTS = {
        "bridge": 7070,
        "task_manager": 7071,
        "websocket": 7072,
        "ratelimiter": 7073,
        "rag": 7074,
        "calculator": 7075,
        "anomaly": 7076,
    }

    @staticmethod
    def get_host(service_name: str = "bridge") -> str:
        """Get host for a Go service from environment or default"""
        env_var = f"GO_{service_name.upper()}_HOST"
        return os.getenv(env_var, "localhost")

    @staticmethod
    def get_port(service_name: str = "bridge") -> int:
        """Get port for a Go service from environment or default.

        When REAPER_GO_UNIFIED=true, all sidecars run collapsed inside the
        single reaper-engine process on the primary bridge port (7070).
        """
        if os.getenv("REAPER_GO_UNIFIED", "false").lower() in ("true", "1", "yes"):
            return int(os.getenv("GO_BRIDGE_PORT", os.getenv("REAPER_GO_BRIDGE_PORT", "7070")))
        env_var = f"GO_{service_name.upper()}_PORT"
        default_port = GoBridgeConfig.DEFAULT_PORTS.get(service_name, 7070)
        return int(os.getenv(env_var, str(default_port)))

    @staticmethod
    def get_timeout(service_name: str = "bridge") -> float:
        """Get timeout for a Go service from environment or default"""
        env_var = f"GO_{service_name.upper()}_TIMEOUT"
        return float(os.getenv(env_var, "30.0"))

    @staticmethod
    def get_enabled(service_name: str = "bridge") -> bool:
        """Get enabled status for a Go service from environment or default"""
        env_var = f"GO_{service_name.upper()}_ENABLED"
        return os.getenv(env_var, "true").lower() == "true"


def create_bridge_client(bridge_class: type, service_name: str, **kwargs) -> BaseGoBridge:
    """
    Factory function to create bridge clients with standardized configuration.

    Args:
        bridge_class: The bridge class to instantiate
        service_name: Name of the service for configuration lookup
        **kwargs: Additional constructor arguments

    Returns:
        Configured bridge instance
    """
    config = {
        "host": kwargs.get("host", GoBridgeConfig.get_host(service_name)),
        "port": kwargs.get("port", GoBridgeConfig.get_port(service_name)),
        "timeout": kwargs.get("timeout", GoBridgeConfig.get_timeout(service_name)),
        "enabled": kwargs.get("enabled", GoBridgeConfig.get_enabled(service_name)),
    }

    return bridge_class(**config)
