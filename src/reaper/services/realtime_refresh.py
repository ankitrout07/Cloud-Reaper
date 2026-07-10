"""
Real-time Data Refresh Service
Provides periodic data refresh and WebSocket push updates for dashboard metrics.

Fast Path (when Go bridge is running)
--------------------------------------
Tasks registered via register_refresh_task() are proxied into the Go streaming
processor (bridge/server.go → internal/streaming/). The Go scheduler replaces
the Python threading.Thread loop with goroutine-based workers that dispatch in
sub-millisecond latency vs 10-50 ms in Python.

Fallback Path (when Go bridge is absent)
-----------------------------------------
The original threading.Thread loop is used unchanged, so existing behaviour is
preserved in environments that haven't built the Go binary.
"""

import asyncio
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from reaper.utils.error_handler import get_logger

logger = get_logger("realtime_refresh")

# Built-in task types that have native Go fetchers in the streaming package.
# Tasks with these types are handed off entirely to the Go scheduler.
_GO_NATIVE_TASK_TYPES = frozenset({"price_scan", "metrics_fetch", "cost_analysis"})


class RealtimeRefreshService:
    """Service for managing real-time data refresh and WebSocket push updates.

    Two operating modes, selected automatically at runtime:

    1. **Go mode** (preferred): tasks are registered with the Go streaming
       scheduler over the bridge HTTP API. The Python threading loop is idle.
    2. **Python mode** (fallback): original threading.Thread loop runs
       when the Go bridge binary is not present or not started.
    """

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

        # Go streaming bridge state
        self._go_mode_active = False
        self._go_synced_tasks: set[str] = set()

        logger.info(f"RealtimeRefreshService initialized with interval: {refresh_interval}s")

    # ─── Task registration ────────────────────────────────────────────────────

    def register_refresh_task(
        self,
        task_id: str,
        data_fetcher: Callable,
        websocket_emitter: Callable | None = None,
        interval: int | None = None,
        enabled: bool = True,
        task_type: str = "custom",
    ):
        """
        Register a data refresh task.

        Args:
            task_id: Unique identifier for the task
            data_fetcher: Async function to fetch data
            websocket_emitter: Optional function to emit data via WebSocket
            interval: Custom refresh interval (uses default if not specified)
            enabled: Whether the task is initially enabled
            task_type: Hint for Go scheduler ('price_scan', 'metrics_fetch',
                       'cost_analysis', or 'custom')
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
            "task_type": task_type,
        }
        logger.info(
            f"Registered refresh task: {task_id} "
            f"(interval: {interval or self.refresh_interval}s)"
        )

        # If already in Go mode, sync the new task immediately
        if self._go_mode_active and enabled:
            asyncio.create_task(self._sync_task_to_go(task_id, self.refresh_tasks[task_id]))

    def unregister_refresh_task(self, task_id: str):
        """Unregister a refresh task."""
        if task_id in self.refresh_tasks:
            del self.refresh_tasks[task_id]
            self._go_synced_tasks.discard(task_id)
            logger.info(f"Unregistered refresh task: {task_id}")

    def enable_task(self, task_id: str):
        """Enable a refresh task."""
        if task_id in self.refresh_tasks:
            self.refresh_tasks[task_id]["enabled"] = True
            logger.info(f"Enabled refresh task: {task_id}")
            if self._go_mode_active:
                asyncio.create_task(self._go_enable_task(task_id, True))

    def disable_task(self, task_id: str):
        """Disable a refresh task."""
        if task_id in self.refresh_tasks:
            self.refresh_tasks[task_id]["enabled"] = False
            logger.info(f"Disabled refresh task: {task_id}")
            if self._go_mode_active:
                asyncio.create_task(self._go_enable_task(task_id, False))

    def set_refresh_interval(self, task_id: str, interval: int):
        """Update refresh interval for a specific task."""
        if task_id in self.refresh_tasks:
            self.refresh_tasks[task_id]["interval"] = interval
            logger.info(f"Updated refresh interval for {task_id}: {interval}s")
            if self._go_mode_active and task_id in self._go_synced_tasks:
                asyncio.create_task(self._go_set_interval(task_id, interval))

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    def start(self):
        """Start the background refresh thread (Python fallback mode)."""
        if self.is_running:
            logger.warning("Refresh service is already running")
            return

        self._stop_event.clear()
        self.refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self.refresh_thread.start()
        self.is_running = True
        logger.info("RealtimeRefreshService started (Python mode)")

    async def start_go_streaming(self) -> bool:
        """
        Attempt to offload all registered tasks to the Go streaming scheduler.

        When successful:
        - All enabled tasks are registered with the Go bridge scheduler
        - The Python threading loop is stopped (avoids double-work)
        - self._go_mode_active is set to True

        Returns:
            True if Go mode was activated, False if the bridge is unavailable
            (Python loop continues as fallback in that case).
        """
        from reaper.integrations.go_stream_bridge import get_stream_bridge

        bridge = get_stream_bridge()

        if not await bridge.is_alive():
            logger.info(
                "Go bridge not reachable — using Python refresh loop (fallback mode)"
            )
            return False

        logger.info("Go bridge reachable — migrating tasks to Go streaming scheduler")

        # Stop Python loop if it was running
        if self.is_running and not self._go_mode_active:
            self.stop()

        # Register all current tasks with Go
        for task_id, task in self.refresh_tasks.items():
            if task["enabled"]:
                await self._sync_task_to_go(task_id, task)

        self._go_mode_active = True
        self.is_running = True  # Mark service as "running" (via Go mode)
        logger.info(
            f"Go streaming mode active — "
            f"{len(self._go_synced_tasks)} tasks registered with Go scheduler"
        )
        return True

    def stop(self):
        """Stop the background refresh thread."""
        if not self.is_running:
            return

        self._stop_event.set()
        if self.refresh_thread:
            self.refresh_thread.join(timeout=5)
        self.is_running = False
        self._go_mode_active = False
        logger.info("RealtimeRefreshService stopped")

    async def stop_go_streaming(self):
        """Disable all Go-managed tasks and reset to Python mode."""
        if not self._go_mode_active:
            return

        from reaper.integrations.go_stream_bridge import get_stream_bridge

        bridge = get_stream_bridge()
        if await bridge.is_alive():
            for task_id in list(self._go_synced_tasks):
                await bridge.enable_task(task_id, enabled=False)

        self._go_mode_active = False
        self._go_synced_tasks.clear()
        self.is_running = False
        logger.info("Go streaming stopped — revert to Python mode with start()")

    # ─── Manual refresh ───────────────────────────────────────────────────────

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

    # ─── Status / observability ───────────────────────────────────────────────

    def get_task_status(self, task_id: str) -> dict[str, Any] | None:
        """Get status information for a specific task."""
        if task_id not in self.refresh_tasks:
            return None

        task = self.refresh_tasks[task_id]
        return {
            "task_id": task_id,
            "enabled": task["enabled"],
            "interval": task["interval"],
            "last_refresh": (
                task["last_refresh"].isoformat() if task["last_refresh"] else None
            ),
            "error_count": task["error_count"],
            "last_error": task["last_error"],
            "has_data": task["last_data"] is not None,
            "go_managed": task_id in self._go_synced_tasks,
        }

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """Get status for all registered tasks."""
        return {task_id: self.get_task_status(task_id) for task_id in self.refresh_tasks}

    async def get_go_stats(self) -> dict[str, Any] | None:
        """
        Fetch real-time processor + scheduler metrics from the Go bridge.

        Returns:
            Combined stats dict or None if Go mode is not active.
        """
        if not self._go_mode_active:
            return None
        from reaper.integrations.go_stream_bridge import get_stream_bridge

        return await get_stream_bridge().get_stats()

    @property
    def go_mode_active(self) -> bool:
        """True when the Go streaming scheduler is handling task dispatch."""
        return self._go_mode_active

    # ─── Python fallback loop (unchanged behaviour) ───────────────────────────

    def _refresh_loop(self):
        """Background thread loop for periodic refresh (Python fallback)."""
        logger.info("Starting Python refresh loop (fallback mode)")

        while not self._stop_event.is_set():
            start_time = time.time()

            for task_id, task in self.refresh_tasks.items():
                if not task["enabled"]:
                    continue
                # Skip tasks already managed by Go to avoid double-work
                if task_id in self._go_synced_tasks:
                    continue

                # Check if task needs refresh
                if task["last_refresh"] is None:
                    needs_refresh = True
                else:
                    elapsed = (datetime.now(UTC) - task["last_refresh"]).total_seconds()
                    needs_refresh = elapsed >= task["interval"]

                if needs_refresh:
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(self.refresh_task(task_id))
                        loop.close()
                    except Exception as e:
                        logger.error(f"Error in refresh loop for {task_id}: {e}")

            elapsed = time.time() - start_time
            sleep_time = max(0, self.refresh_interval - elapsed)

            if not self._stop_event.wait(sleep_time):
                break

        logger.info("Python refresh loop stopped")

    # ─── Go bridge helpers ────────────────────────────────────────────────────

    async def _sync_task_to_go(self, task_id: str, task: dict[str, Any]) -> bool:
        """
        Register a single Python task with the Go scheduler.

        For native task types (price_scan, metrics_fetch, cost_analysis), Go
        handles data collection internally.  For custom Python tasks, the task
        is registered as a no-op Go task; Python drives it by submitting
        DataPoints to /stream/submit at appropriate times.
        """
        from reaper.integrations.go_stream_bridge import get_stream_bridge

        bridge = get_stream_bridge()
        task_type = task.get("task_type", "custom")

        # Map to a Go-native type if possible; fall back to "custom"
        go_task_type = task_type if task_type in _GO_NATIVE_TASK_TYPES else "custom"

        ok = await bridge.register_task(
            task_id,
            interval_s=float(task["interval"]),
            task_type=go_task_type,
            enabled=task["enabled"],
        )
        if ok:
            self._go_synced_tasks.add(task_id)
            logger.debug(f"Task {task_id!r} synced to Go scheduler (type={go_task_type})")
        else:
            logger.warning(f"Failed to sync task {task_id!r} to Go scheduler")
        return ok

    async def _go_enable_task(self, task_id: str, enabled: bool) -> None:
        """Enable / disable a task on the Go scheduler."""
        from reaper.integrations.go_stream_bridge import get_stream_bridge

        bridge = get_stream_bridge()
        if await bridge.is_alive():
            await bridge.enable_task(task_id, enabled=enabled)

    async def _go_set_interval(self, task_id: str, interval: int) -> None:
        """Update a task's interval on the Go scheduler."""
        from reaper.integrations.go_stream_bridge import get_stream_bridge

        bridge = get_stream_bridge()
        if await bridge.is_alive():
            await bridge.set_task_interval(task_id, float(interval))


# Global refresh service instance
refresh_service = RealtimeRefreshService(refresh_interval=60)


def get_refresh_service() -> RealtimeRefreshService:
    """Get the global refresh service instance."""
    return refresh_service
