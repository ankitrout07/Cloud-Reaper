"""
Real-time Data Refresh Service
================================
Periodic data refresh and WebSocket push updates for dashboard metrics.

All scheduling is now handled by the Go streaming processor
(internal/streaming/scheduler.go) via the bridge API on :7070.

Usage
-----
    from reaper.services.realtime_refresh import get_refresh_service

    svc = get_refresh_service()

    # Register a task (Go scheduler takes ownership automatically)
    svc.register_refresh_task(
        "metrics_azure",
        data_fetcher=my_fetcher,
        interval=60,
        task_type="metrics_fetch",   # native Go type → Go handles data collection
    )

    # Activate Go mode (call once at app startup)
    await svc.start_go_streaming()

    # One-shot manual refresh (still available for ad-hoc use)
    data = await svc.refresh_task("metrics_azure")
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from reaper.utils.error_handler import get_logger

logger = get_logger("realtime_refresh")

# Task types with native Go fetchers in internal/streaming/bridge_handlers.go.
# Tasks of these types are executed entirely inside the Go process.
_GO_NATIVE_TASK_TYPES = frozenset({"price_scan", "metrics_fetch", "cost_analysis"})


class RealtimeRefreshService:
    """
    Real-time refresh service backed by the Go streaming scheduler.

    Tasks registered here are proxied to the Go bridge scheduler
    (POST /stream/task/register).  The Go process runs them at the requested
    interval using goroutine-based workers — replacing the old Python
    threading.Thread loop.

    For one-shot ad-hoc refreshes, call refresh_task() directly.
    """

    def __init__(self, refresh_interval: int = 60):
        """
        Args:
            refresh_interval: Default interval in seconds (default: 60).
        """
        self.refresh_interval = refresh_interval
        self.refresh_tasks: dict[str, dict[str, Any]] = {}
        self.is_running = False

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
            task_id: Unique task identifier.
            data_fetcher: Async callable that returns the refreshed data.
            websocket_emitter: Optional async callable to push data via WebSocket.
            interval: Refresh interval in seconds (uses default if omitted).
            enabled: Whether the task starts active.
            task_type: 'price_scan', 'metrics_fetch', 'cost_analysis', or 'custom'.
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
            f"Registered task: {task_id!r} "
            f"(interval={interval or self.refresh_interval}s, type={task_type})"
        )

        # Sync immediately if Go mode is already active
        if self._go_mode_active and enabled:
            asyncio.create_task(self._sync_task_to_go(task_id, self.refresh_tasks[task_id]))

    def unregister_refresh_task(self, task_id: str):
        """Remove a task from the service and disable it on the Go scheduler."""
        if task_id in self.refresh_tasks:
            del self.refresh_tasks[task_id]
            self._go_synced_tasks.discard(task_id)
            logger.info(f"Unregistered task: {task_id!r}")

    def enable_task(self, task_id: str):
        """Enable a task (propagated to Go scheduler)."""
        if task_id in self.refresh_tasks:
            self.refresh_tasks[task_id]["enabled"] = True
            if self._go_mode_active:
                asyncio.create_task(self._go_enable_task(task_id, True))
            logger.info(f"Enabled task: {task_id!r}")

    def disable_task(self, task_id: str):
        """Disable a task (propagated to Go scheduler)."""
        if task_id in self.refresh_tasks:
            self.refresh_tasks[task_id]["enabled"] = False
            if self._go_mode_active:
                asyncio.create_task(self._go_enable_task(task_id, False))
            logger.info(f"Disabled task: {task_id!r}")

    def set_refresh_interval(self, task_id: str, interval: int):
        """Update interval for a task (propagated to Go scheduler)."""
        if task_id in self.refresh_tasks:
            self.refresh_tasks[task_id]["interval"] = interval
            if self._go_mode_active and task_id in self._go_synced_tasks:
                asyncio.create_task(self._go_set_interval(task_id, interval))
            logger.info(f"Updated interval for {task_id!r}: {interval}s")

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    async def start_go_streaming(self) -> bool:
        """
        Register all enabled tasks with the Go scheduler and activate Go mode.

        Call once at application startup (e.g. in the FastAPI lifespan handler).

        Returns:
            True if Go mode activated, False if the bridge is unreachable.
        """
        from reaper.integrations.go_stream_bridge import get_stream_bridge

        bridge = get_stream_bridge()
        if not await bridge.is_alive():
            logger.warning(
                "Go bridge unreachable — realtime refresh disabled. "
                "Start the Go engine with --mode serve to activate."
            )
            return False

        logger.info("Go bridge reachable — registering tasks with Go scheduler")
        for task_id, task in self.refresh_tasks.items():
            if task["enabled"]:
                await self._sync_task_to_go(task_id, task)

        self._go_mode_active = True
        self.is_running = True
        logger.info(
            f"Go streaming active — {len(self._go_synced_tasks)} task(s) registered"
        )
        return True

    def start(self):
        """No-op stub kept for API compatibility. Use start_go_streaming() instead."""
        logger.warning(
            "start() called — Python threading loop removed. "
            "Call 'await start_go_streaming()' to activate the Go scheduler."
        )

    async def stop_go_streaming(self):
        """Disable all Go-managed tasks and mark the service as stopped."""
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
        logger.info("Go streaming stopped")

    def stop(self):
        """Synchronous stop — schedules stop_go_streaming() if a loop is running."""
        if not self.is_running:
            return
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.stop_go_streaming())
            else:
                loop.run_until_complete(self.stop_go_streaming())
        except Exception:
            self._go_mode_active = False
            self.is_running = False

    # ─── One-shot manual refresh ──────────────────────────────────────────────

    async def refresh_task(self, task_id: str) -> Any | None:
        """
        Manually trigger a single refresh cycle for task_id.

        Useful for ad-hoc data pulls independent of the scheduler interval.

        Args:
            task_id: Registered task identifier.

        Returns:
            Fetched data or None on failure.
        """
        if task_id not in self.refresh_tasks:
            logger.warning(f"refresh_task: {task_id!r} not found")
            return None

        task = self.refresh_tasks[task_id]
        try:
            data = await task["data_fetcher"]()
            task["last_data"] = data
            task["last_refresh"] = datetime.now(UTC)
            task["error_count"] = 0
            task["last_error"] = None

            if task["websocket_emitter"]:
                try:
                    await task["websocket_emitter"](data)
                except Exception as e:
                    logger.error(f"WebSocket emit failed for {task_id!r}: {e}")

            logger.info(f"Refreshed task: {task_id!r}")
            return data
        except Exception as e:
            task["error_count"] += 1
            task["last_error"] = str(e)
            logger.error(f"Failed to refresh {task_id!r}: {e}", exc_info=True)
            return None

    # ─── Observability ────────────────────────────────────────────────────────

    def get_task_status(self, task_id: str) -> dict[str, Any] | None:
        """Return a status snapshot for task_id."""
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
        """Return status snapshots for all registered tasks."""
        return {tid: self.get_task_status(tid) for tid in self.refresh_tasks}

    async def get_go_stats(self) -> dict[str, Any] | None:
        """
        Return live processor + scheduler metrics from the Go bridge.

        Returns:
            {"processor": {...}, "scheduler": {...}} or None if Go mode is off.
        """
        if not self._go_mode_active:
            return None
        from reaper.integrations.go_stream_bridge import get_stream_bridge

        return await get_stream_bridge().get_stats()

    @property
    def go_mode_active(self) -> bool:
        """True when the Go scheduler is managing task dispatch."""
        return self._go_mode_active

    # ─── Go bridge helpers ────────────────────────────────────────────────────

    async def _sync_task_to_go(self, task_id: str, task: dict[str, Any]) -> bool:
        from reaper.integrations.go_stream_bridge import get_stream_bridge

        bridge = get_stream_bridge()
        task_type = task.get("task_type", "custom")
        go_task_type = task_type if task_type in _GO_NATIVE_TASK_TYPES else "custom"

        ok = await bridge.register_task(
            task_id,
            interval_s=float(task["interval"]),
            task_type=go_task_type,
            enabled=task["enabled"],
        )
        if ok:
            self._go_synced_tasks.add(task_id)
            logger.debug(f"Synced {task_id!r} → Go scheduler (type={go_task_type})")
        else:
            logger.warning(f"Failed to sync {task_id!r} to Go scheduler")
        return ok

    async def _go_enable_task(self, task_id: str, enabled: bool) -> None:
        from reaper.integrations.go_stream_bridge import get_stream_bridge

        bridge = get_stream_bridge()
        if await bridge.is_alive():
            await bridge.enable_task(task_id, enabled=enabled)

    async def _go_set_interval(self, task_id: str, interval: int) -> None:
        from reaper.integrations.go_stream_bridge import get_stream_bridge

        bridge = get_stream_bridge()
        if await bridge.is_alive():
            await bridge.set_task_interval(task_id, float(interval))


# ─── Module-level singleton ────────────────────────────────────────────────────

refresh_service = RealtimeRefreshService(refresh_interval=60)


def get_refresh_service() -> RealtimeRefreshService:
    """Return the module-level RealtimeRefreshService singleton."""
    return refresh_service
