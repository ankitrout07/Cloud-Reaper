"""
Go Stream Bridge Client
=======================
Async Python client for the /stream/* endpoints served by the Go engine bridge.

This module provides the Python-side counterpart to the Go streaming processor
and scheduler, following the same bridge-alive-check + graceful-None fallback
pattern established in go_bridge.py.

Architecture
------------

  realtime_refresh.py (Python)
        │
        ▼
  go_stream_bridge.py  ◄── awaitable, releases event loop during I/O wait
        │
        ▼  httpx AsyncClient (non-blocking TCP)
  Go bridge :7070/stream/*
        │
        ├─ DataProcessor (worker pool, 8 goroutines)
        └─ Scheduler (goroutine ticker, per-task intervals)

Usage
-----

  from reaper.integrations.go_stream_bridge import GoStreamBridge

  bridge = GoStreamBridge()
  if await bridge.is_alive():
      await bridge.register_task("my_metrics", interval_s=60, task_type="metrics_fetch")
      await bridge.submit_data_point("metric", "vm-001", {"value": 45.2, ...})
      stats = await bridge.get_stats()
"""

from __future__ import annotations

import os
from typing import Any

_BRIDGE_PORT = int(os.getenv("REAPER_GO_BRIDGE_PORT", "7070"))
_BRIDGE_BASE = f"http://127.0.0.1:{_BRIDGE_PORT}"
_STREAM_BASE = f"{_BRIDGE_BASE}/stream"
_TIMEOUT = float(os.getenv("REAPER_GO_BRIDGE_TIMEOUT", "30"))


class GoStreamBridge:
    """
    Async client for the Go streaming processor bridge.

    All methods are coroutines and release the asyncio event loop during I/O.
    When the Go bridge is not running, methods return None / False gracefully
    rather than raising exceptions, allowing Python fallback paths to activate.
    """

    async def is_alive(self) -> bool:
        """Return True if the Go bridge is up and reachable."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{_BRIDGE_BASE}/health")
                return resp.status_code == 200
        except Exception:
            return False

    async def submit_data_point(
        self,
        data_type: str,
        resource_id: str,
        payload: dict[str, Any],
        *,
        provider: str = "azure",
        region: str = "",
        source_task_id: str = "",
    ) -> dict[str, Any] | None:
        """
        Enqueue a DataPoint for sub-millisecond Go processing.

        Args:
            data_type: One of "price", "metric", "resource", "anomaly", "cost"
            resource_id: Cloud resource identifier
            payload: Type-specific data (see Go DataPoint.Payload docs)
            provider: Cloud provider (default: "azure")
            region: Azure region name (optional)
            source_task_id: ID of the scheduler task that produced this point

        Returns:
            {"status":"queued", "resource_id":..., "type":...} or None on failure
        """
        try:
            import httpx

            body = {
                "type": data_type,
                "resource_id": resource_id,
                "provider": provider,
                "region": region,
                "payload": payload,
                "source_task_id": source_task_id,
            }
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(f"{_STREAM_BASE}/submit", json=body)
                if resp.status_code in (200, 202):
                    return resp.json()
                print(
                    f"[go_stream_bridge] /stream/submit returned {resp.status_code}: "
                    f"{resp.text[:200]}"
                )
                return None
        except Exception as exc:
            print(f"[go_stream_bridge] submit_data_point error: {exc}")
            return None

    async def get_stats(self) -> dict[str, Any] | None:
        """
        Fetch combined processor + scheduler metrics from the Go bridge.

        Returns:
            {
              "processor": { "running":true, "workers":8, "processed_total":...,
                             "errors_total":..., "dropped_total":..., ... },
              "scheduler": { "running":true, "task_count":..., ... }
            }
            or None on failure.
        """
        try:
            import httpx

            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(f"{_STREAM_BASE}/stats")
                if resp.status_code == 200:
                    return resp.json()
        except Exception as exc:
            print(f"[go_stream_bridge] get_stats error: {exc}")
        return None

    async def register_task(
        self,
        task_id: str,
        *,
        interval_s: float,
        task_type: str,
        provider: str = "azure",
        enabled: bool = True,
        callback_url: str = "",
    ) -> bool:
        """
        Register a periodic refresh task with the Go scheduler.

        When task_type matches a built-in Go fetcher (metrics_fetch,
        cost_analysis, price_scan), Go handles data collection natively.
        For custom Python tasks, set callback_url and submit data points
        manually via submit_data_point().

        Args:
            task_id: Unique task identifier
            interval_s: Refresh interval in seconds (e.g. 60.0)
            task_type: Built-in type or custom label
            provider: Cloud provider
            enabled: Whether to start running immediately
            callback_url: Optional Python endpoint for custom fetchers

        Returns:
            True if registered successfully, False otherwise
        """
        try:
            import httpx

            body = {
                "id": task_id,
                "interval_s": interval_s,
                "task_type": task_type,
                "provider": provider,
                "enabled": enabled,
                "callback_url": callback_url,
            }
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(f"{_STREAM_BASE}/task/register", json=body)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    print(
                        f"[go_stream_bridge] Registered task {task_id!r} "
                        f"(interval={interval_s}s, type={task_type})"
                    )
                    return True
                print(
                    f"[go_stream_bridge] register_task failed {resp.status_code}: "
                    f"{resp.text[:200]}"
                )
                return False
        except Exception as exc:
            print(f"[go_stream_bridge] register_task error: {exc}")
            return False

    async def enable_task(self, task_id: str, *, enabled: bool) -> bool:
        """
        Enable or disable a scheduled task at runtime.

        Args:
            task_id: Task to modify
            enabled: New enabled state

        Returns:
            True if updated, False on error
        """
        try:
            import httpx

            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    f"{_STREAM_BASE}/task/enable",
                    json={"id": task_id, "enabled": enabled},
                )
                return resp.status_code == 200
        except Exception as exc:
            print(f"[go_stream_bridge] enable_task error: {exc}")
            return False

    async def set_task_interval(self, task_id: str, interval_s: float) -> bool:
        """
        Update the refresh interval of an existing task.

        Args:
            task_id: Task to modify
            interval_s: New interval in seconds

        Returns:
            True if updated, False on error
        """
        try:
            import httpx

            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    f"{_STREAM_BASE}/task/interval",
                    json={"id": task_id, "interval_s": interval_s},
                )
                return resp.status_code == 200
        except Exception as exc:
            print(f"[go_stream_bridge] set_task_interval error: {exc}")
            return False

    async def list_tasks(self) -> list[dict[str, Any]]:
        """
        Return status snapshots for all registered Go scheduler tasks.

        Returns:
            List of task status dicts:
            [{"id":..., "enabled":..., "interval_s":..., "run_count":...,
              "last_run":..., "error_count":..., "last_error":...}, ...]
        """
        try:
            import httpx

            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(f"{_STREAM_BASE}/tasks")
                if resp.status_code == 200:
                    return resp.json().get("tasks", [])
        except Exception as exc:
            print(f"[go_stream_bridge] list_tasks error: {exc}")
        return []

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        """
        Return status for a single task.

        Args:
            task_id: Task identifier

        Returns:
            Task status dict or None if not found / bridge down
        """
        try:
            import httpx

            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(f"{_STREAM_BASE}/task/{task_id}")
                if resp.status_code == 200:
                    return resp.json()
        except Exception as exc:
            print(f"[go_stream_bridge] get_task error: {exc}")
        return None


# Module-level convenience instance
_default_bridge: GoStreamBridge | None = None


def get_stream_bridge() -> GoStreamBridge:
    """Return the module-level GoStreamBridge singleton."""
    global _default_bridge
    if _default_bridge is None:
        _default_bridge = GoStreamBridge()
    return _default_bridge
