"""
Go WebSocket Batcher Bridge
Provides Python interface to the Go-based WebSocket batching system
"""

import asyncio
import inspect
import json
import websockets
from typing import Any, Callable, Coroutine

from reaper.integrations.go_bridge_base import (
    BaseGoBridge,
    GoBridgeError,
    create_bridge_client,
)


class WebSocketClient:
    """
    Direct WebSocket client for connecting to the Go metrics broadcaster.
    Provides real-time streaming of metrics updates.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 7072,
        room: str | None = None,
        client_id: str | None = None,
    ):
        self.host = host
        self.port = port
        self.room = room
        self.client_id = client_id
        self.websocket: websockets.WebSocketClientProtocol | None = None
        self._message_handlers: list[Callable[[dict[str, Any]], Any]] = []
        self._connected = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5

    async def connect(self) -> bool:
        """Connect to the WebSocket server."""
        uri = f"ws://{self.host}:{self.port}/ws/metrics"
        params = []
        if self.room:
            params.append(f"room={self.room}")
        if self.client_id:
            params.append(f"client_id={self.client_id}")

        if params:
            uri += "?" + "&".join(params)

        try:
            self.websocket = await websockets.connect(uri)
            self._connected = True
            self._reconnect_attempts = 0
            return True
        except Exception as e:
            print(f"[WebSocket Client] Connection failed: {e}")
            return False

    async def disconnect(self):
        """Disconnect from the WebSocket server."""
        if self.websocket:
            await self.websocket.close()
            self._connected = False
            self.websocket = None

    async def listen(self):
        """Listen for incoming messages."""
        if not self.websocket or not self._connected:
            raise RuntimeError("WebSocket not connected")

        try:
            async for message in self.websocket:
                data = json.loads(message)
                for handler in self._message_handlers:
                    try:
                        if inspect.iscoroutinefunction(handler):
                            await handler(data)
                        else:
                            handler(data)
                    except Exception as e:
                        print(f"[WebSocket Client] Handler error: {e}")
        except websockets.exceptions.ConnectionClosed:
            print("[WebSocket Client] Connection closed")
            self._connected = False
            await self._handle_reconnect()
        except Exception as e:
            print(f"[WebSocket Client] Listen error: {e}")
            self._connected = False
            await self._handle_reconnect()

    async def _handle_reconnect(self):
        """Handle automatic reconnection."""
        if self._reconnect_attempts < self._max_reconnect_attempts:
            self._reconnect_attempts += 1
            delay = min(2 ** self._reconnect_attempts, 30)  # Exponential backoff
            print(f"[WebSocket Client] Reconnecting in {delay}s...")
            await asyncio.sleep(delay)
            if await self.connect():
                asyncio.create_task(self.listen())

    def add_message_handler(self, handler: Callable):
        """Add a message handler callback."""
        self._message_handlers.append(handler)

    def remove_message_handler(self, handler: Callable):
        """Remove a message handler callback."""
        if handler in self._message_handlers:
            self._message_handlers.remove(handler)

    @property
    def is_connected(self) -> bool:
        """Check if the client is connected."""
        return self._connected

    async def get_connected_clients(self) -> list[dict[str, Any]]:
        """Get information about connected clients from the server."""
        async with websockets.connect(f"ws://{self.host}:{self.port}/ws/metrics") as ws:
            # This is a placeholder - actual implementation would use HTTP API
            return []


class GoWebSocketBatcher(BaseGoBridge):
    """
    Python bridge to the Go-based WebSocket batcher.
    Communicates with the Go HTTP server for batched message management.
    Also supports direct WebSocket connections via the metrics broadcaster.
    """

    def __init__(
        self, host: str = "localhost", port: int = 7072, timeout: float = 30.0, enabled: bool = True
    ):
        super().__init__(host=host, port=port, timeout=timeout, enabled=enabled)
        self._websocket_client: WebSocketClient | None = None

    async def emit(self, event: str, data: dict[str, Any], room: str | None = None) -> bool:
        """
        Queue a message for batched emission.

        Args:
            event: Event name for the message
            data: Message data payload
            room: Optional room name for targeted emission

        Returns:
            True if message was queued successfully
        """
        if not self.enabled:
            return False

        payload = {
            "event": event,
            "data": data,
        }

        if room:
            payload["room"] = room

        try:
            result = await self._make_request("POST", "/api/ws/batch/send", json_data=payload)
            return result.get("success", False)
        except GoBridgeError as e:
            print(f"[Go WebSocket Batcher] Error emitting message: {e}")
            return False

    async def flush_all(self) -> bool:
        """
        Flush all pending batches immediately.

        Returns:
            True if flush was successful
        """
        if not self.enabled:
            return False

        try:
            result = await self._make_request("POST", "/api/ws/batch/flush")
            return result.get("success", False)
        except GoBridgeError as e:
            print(f"[Go WebSocket Batcher] Error flushing batches: {e}")
            return False

    async def get_statistics(self) -> dict[str, Any]:
        """
        Get batcher statistics.

        Returns:
            Dictionary with statistics
        """
        if not self.enabled:
            return {}

        try:
            return await self._make_request("GET", "/api/ws/batch/stats")
        except GoBridgeError as e:
            print(f"[Go WebSocket Batcher] Error getting statistics: {e}")
            return {}

    async def update_config(
        self,
        batch_interval_ms: int | None = None,
        max_batch_size: int | None = None,
        max_queue_size: int | None = None,
        enable_compression: bool | None = None,
        adaptive_batching: bool | None = None,
        max_concurrent_flush: int | None = None,
        buffer_pool_size: int | None = None,
    ) -> dict[str, Any]:
        """
        Update batcher configuration.

        Args:
            batch_interval_ms: New batch interval in milliseconds
            max_batch_size: New maximum batch size
            max_queue_size: New maximum queue size
            enable_compression: Enable/disable compression
            adaptive_batching: Enable/disable adaptive batching
            max_concurrent_flush: Maximum concurrent flush operations
            buffer_pool_size: Size of buffer pool

        Returns:
            Updated configuration
        """
        if not self.enabled:
            return {}

        payload = {}
        if batch_interval_ms is not None:
            payload["batch_interval_ms"] = batch_interval_ms
        if max_batch_size is not None:
            payload["max_batch_size"] = max_batch_size
        if max_queue_size is not None:
            payload["max_queue_size"] = max_queue_size
        if enable_compression is not None:
            payload["enable_compression"] = enable_compression
        if adaptive_batching is not None:
            payload["adaptive_batching"] = adaptive_batching
        if max_concurrent_flush is not None:
            payload["max_concurrent_flush"] = max_concurrent_flush
        if buffer_pool_size is not None:
            payload["buffer_pool_size"] = buffer_pool_size

        if not payload:
            return await self.get_statistics()

        try:
            return await self._make_request("POST", "/api/ws/batch/config", json_data=payload)
        except GoBridgeError as e:
            print(f"[Go WebSocket Batcher] Error updating config: {e}")
            return {}

    async def stop(self) -> bool:
        """
        Stop the batcher.

        Returns:
            True if stop was successful
        """
        if not self.enabled:
            return False

        try:
            result = await self._make_request("POST", "/api/ws/batch/stop")
            if result.get("success"):
                self.disable()
            return result.get("success", False)
        except GoBridgeError as e:
            print(f"[Go WebSocket Batcher] Error stopping batcher: {e}")
            return False

    async def start(self) -> bool:
        """
        Start the batcher (if stopped).

        Returns:
            True if start was successful
        """
        try:
            result = await self._make_request("POST", "/api/ws/batch/start")
            if result.get("success"):
                self.enable()
            return result.get("success", False)
        except GoBridgeError as e:
            print(f"[Go WebSocket Batcher] Error starting batcher: {e}")
            return False

    # WebSocket client methods

    async def create_websocket_client(
        self, room: str | None = None, client_id: str | None = None
    ) -> WebSocketClient:
        """
        Create a direct WebSocket client for real-time metrics streaming.

        Args:
            room: Optional room name for targeted updates
            client_id: Optional client ID for the connection

        Returns:
            WebSocketClient instance
        """
        client = WebSocketClient(
            host=self.host, port=self.port, room=room, client_id=client_id
        )
        return client

    async def get_connected_clients(self) -> list[dict[str, Any]]:
        """
        Get information about connected WebSocket clients.

        Returns:
            List of client information dictionaries
        """
        if not self.enabled:
            return []

        try:
            result = await self._make_request("GET", "/api/ws/clients")
            return result.get("data", {}).get("clients", [])
        except GoBridgeError as e:
            print(f"[Go WebSocket Batcher] Error getting connected clients: {e}")
            return []

    async def broadcast_metric(
        self, metric: str, value: float, room: str | None = None, metadata: dict[str, Any] | None = None
    ) -> bool:
        """
        Broadcast a metric update directly via WebSocket.

        Args:
            metric: Metric name
            value: Metric value
            room: Optional room for targeted broadcast
            metadata: Optional metadata dictionary

        Returns:
            True if broadcast was successful
        """
        if not self.enabled:
            return False

        payload = {
            "metric": metric,
            "value": value,
        }

        if room:
            payload["room"] = room
        if metadata:
            payload["metadata"] = metadata

        try:
            result = await self._make_request("POST", "/api/ws/broadcast", json_data=payload)
            return result.get("success", False)
        except GoBridgeError as e:
            print(f"[Go WebSocket Batcher] Error broadcasting metric: {e}")
            return False


# Singleton instance for easy access
_global_batcher: GoWebSocketBatcher | None = None
_batcher_lock = asyncio.Lock()


async def get_websocket_batcher(host: str = "localhost", port: int = 7072) -> GoWebSocketBatcher:
    """Get the singleton WebSocket batcher instance"""
    global _global_batcher

    async with _batcher_lock:
        if _global_batcher is None:
            _global_batcher = create_bridge_client(
                GoWebSocketBatcher, "websocket", host=host, port=port
            )
        return _global_batcher


# Convenience functions for common operations
async def emit_metric_update(time: str, value: float, room: str | None = None) -> bool:
    """
    Emit a metric update event.

    Args:
        time: Timestamp for the metric
        value: Metric value
        room: Optional room for targeted emission

    Returns:
        True if message was queued successfully
    """
    batcher = await get_websocket_batcher()
    return await batcher.emit(event="metric_update", data={"time": time, "value": value}, room=room)


async def emit_cost_alert(
    alert_type: str, message: str, severity: str, room: str | None = None
) -> bool:
    """
    Emit a cost alert event.

    Args:
        alert_type: Type of cost alert
        message: Alert message
        severity: Alert severity level
        room: Optional room for targeted emission

    Returns:
        True if message was queued successfully
    """
    batcher = await get_websocket_batcher()
    return await batcher.emit(
        event="cost_alert",
        data={
            "alert_type": alert_type,
            "message": message,
            "severity": severity,
            "timestamp": asyncio.get_event_loop().time(),
        },
        room=room,
    )


async def emit_resource_update(resource_id: str, status: str, room: str | None = None) -> bool:
    """
    Emit a resource update event.

    Args:
        resource_id: ID of the resource
        status: Resource status
        room: Optional room for targeted emission

    Returns:
        True if message was queued successfully
    """
    batcher = await get_websocket_batcher()
    return await batcher.emit(
        event="resource_update",
        data={
            "resource_id": resource_id,
            "status": status,
            "timestamp": asyncio.get_event_loop().time(),
        },
        room=room,
    )
