"""
Go WebSocket Batcher Bridge
Provides Python interface to the Go-based WebSocket batching system
"""

import asyncio
from typing import Any

from reaper.web.go_bridge_base import (
    BaseGoBridge,
    GoBridgeError,
    create_bridge_client,
)


class GoWebSocketBatcher(BaseGoBridge):
    """
    Python bridge to the Go-based WebSocket batcher.
    Communicates with the Go HTTP server for batched message management.
    """

    def __init__(self, host: str = "localhost", port: int = 7072, timeout: float = 30.0):
        super().__init__(host=host, port=port, timeout=timeout)

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
    ) -> dict[str, Any]:
        """
        Update batcher configuration.

        Args:
            batch_interval_ms: New batch interval in milliseconds
            max_batch_size: New maximum batch size
            max_queue_size: New maximum queue size

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
