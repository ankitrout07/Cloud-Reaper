"""
Real-time Data Refresh Service
Provides periodic data refresh and WebSocket push updates for dashboard metrics.
"""

import asyncio
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from reaper.utils.error_handler import get_logger

logger = get_logger("realtime_refresh")


class RealtimeRefreshService:
    """Service for managing real-time data refresh and WebSocket push updates."""

    def __init__(self, refresh_interval: int = 60):
        """
        Initialize the real-time refresh service.

        Args:
            refresh_interval: Default refresh interval in seconds (default: 60)
        """
        self.refresh_interval = refresh_interval
        self.refresh_tasks: dict[str, dict[str, Any]] = {}
        self.is_running = False
        self.refresh_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        logger.info(f"RealtimeRefreshService initialized with interval: {refresh_interval}s")

    def register_refresh_task(
        self,
        task_id: str,
        data_fetcher: Callable,
        websocket_emitter: Callable | None = None,
        interval: int | None = None,
        enabled: bool = True,
    ):
        """
        Register a data refresh task.

        Args:
            task_id: Unique identifier for the task
            data_fetcher: Async function to fetch data
            websocket_emitter: Optional function to emit data via WebSocket
            interval: Custom refresh interval (uses default if not specified)
            enabled: Whether the task is initially enabled
        """
        self.refresh_tasks[task_id] = {
            "data_fetcher": data_fetcher,
            "websocket_emitter": websocket_emitter,
            "interval": interval or self.refresh_interval,
            "enabled": enabled,
            "last_refresh": None,
            "last_data": None,
            "error_count": 0,
            "last_error": None,
        }
        logger.info(
            f"Registered refresh task: {task_id} (interval: {interval or self.refresh_interval}s)"
        )

    def unregister_refresh_task(self, task_id: str):
        """Unregister a refresh task."""
        if task_id in self.refresh_tasks:
            del self.refresh_tasks[task_id]
            logger.info(f"Unregistered refresh task: {task_id}")

    def enable_task(self, task_id: str):
        """Enable a refresh task."""
        if task_id in self.refresh_tasks:
            self.refresh_tasks[task_id]["enabled"] = True
            logger.info(f"Enabled refresh task: {task_id}")

    def disable_task(self, task_id: str):
        """Disable a refresh task."""
        if task_id in self.refresh_tasks:
            self.refresh_tasks[task_id]["enabled"] = False
            logger.info(f"Disabled refresh task: {task_id}")

    def set_refresh_interval(self, task_id: str, interval: int):
        """Update refresh interval for a specific task."""
        if task_id in self.refresh_tasks:
            self.refresh_tasks[task_id]["interval"] = interval
            logger.info(f"Updated refresh interval for {task_id}: {interval}s")

    async def refresh_task(self, task_id: str) -> Any | None:
        """
        Manually trigger a refresh for a specific task.

        Args:
            task_id: Task identifier to refresh

        Returns:
            Fetched data or None if failed
        """
        if task_id not in self.refresh_tasks:
            logger.warning(f"Task not found: {task_id}")
            return None

        task = self.refresh_tasks[task_id]

        try:
            logger.debug(f"Refreshing task: {task_id}")
            data = await task["data_fetcher"]()

            task["last_data"] = data
            task["last_refresh"] = datetime.now(UTC)
            task["error_count"] = 0
            task["last_error"] = None

            # Emit via WebSocket if emitter is available
            if task["websocket_emitter"]:
                try:
                    await task["websocket_emitter"](data)
                except Exception as e:
                    logger.error(f"WebSocket emit failed for {task_id}: {e}")

            logger.info(f"Successfully refreshed task: {task_id}")
            return data

        except Exception as e:
            task["error_count"] += 1
            task["last_error"] = str(e)
            logger.error(f"Failed to refresh task {task_id}: {e}", exc_info=True)
            return None

    def _refresh_loop(self):
        """Background thread loop for periodic refresh."""
        logger.info("Starting refresh loop")

        while not self._stop_event.is_set():
            start_time = time.time()

            for task_id, task in self.refresh_tasks.items():
                if not task["enabled"]:
                    continue

                # Check if task needs refresh
                if task["last_refresh"] is None:
                    needs_refresh = True
                else:
                    elapsed = (datetime.now(UTC) - task["last_refresh"]).total_seconds()
                    needs_refresh = elapsed >= task["interval"]

                if needs_refresh:
                    try:
                        # Run async task in event loop
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(self.refresh_task(task_id))
                        loop.close()
                    except Exception as e:
                        logger.error(f"Error in refresh loop for {task_id}: {e}")

            # Calculate sleep time to maintain interval
            elapsed = time.time() - start_time
            sleep_time = max(0, self.refresh_interval - elapsed)

            if not self._stop_event.wait(sleep_time):
                break

        logger.info("Refresh loop stopped")

    def start(self):
        """Start the background refresh thread."""
        if self.is_running:
            logger.warning("Refresh service is already running")
            return

        self._stop_event.clear()
        self.refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self.refresh_thread.start()
        self.is_running = True
        logger.info("RealtimeRefreshService started")

    def stop(self):
        """Stop the background refresh thread."""
        if not self.is_running:
            return

        self._stop_event.set()
        if self.refresh_thread:
            self.refresh_thread.join(timeout=5)
        self.is_running = False
        logger.info("RealtimeRefreshService stopped")

    def get_task_status(self, task_id: str) -> dict[str, Any] | None:
        """Get status information for a specific task."""
        if task_id not in self.refresh_tasks:
            return None

        task = self.refresh_tasks[task_id]
        return {
            "task_id": task_id,
            "enabled": task["enabled"],
            "interval": task["interval"],
            "last_refresh": task["last_refresh"].isoformat() if task["last_refresh"] else None,
            "error_count": task["error_count"],
            "last_error": task["last_error"],
            "has_data": task["last_data"] is not None,
        }

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """Get status for all registered tasks."""
        return {task_id: self.get_task_status(task_id) for task_id in self.refresh_tasks}


# Global refresh service instance
refresh_service = RealtimeRefreshService(refresh_interval=60)


def get_refresh_service() -> RealtimeRefreshService:
    """Get the global refresh service instance."""
    return refresh_service
