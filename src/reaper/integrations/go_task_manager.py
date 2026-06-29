"""
Go Task Manager Bridge
Provides Python interface to the Go-based background task manager
"""

import asyncio
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from reaper.integrations.go_bridge_base import (
    BaseGoBridge,
    GoBridgeError,
    create_bridge_client,
)


class TaskStatus(Enum):
    """Task status matching Go implementation"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskResult:
    """Task result matching Go implementation"""

    task_id: str
    status: TaskStatus
    result: Any | None = None
    error: str | None = None
    progress: float = 0.0
    created_at: float = 0.0
    started_at: float | None = None
    completed_at: float | None = None
    metadata: dict[str, Any] | None = None


class GoTaskManagerBridge(BaseGoBridge):
    """
    Python bridge to the Go-based background task manager.
    Communicates with the Go HTTP server for task management.
    """

    def __init__(self, host: str = "localhost", port: int = 7071, timeout: float = 30.0):
        super().__init__(host=host, port=port, timeout=timeout)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False

    async def submit_task(
        self,
        task_type: str,
        args: list[Any],
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Submit a task to the Go task manager.

        Args:
            task_type: Type of task ("price_scan", "resource_audit", etc.)
            args: Arguments to pass to the task function
            task_id: Optional custom task ID
            metadata: Optional metadata for the task

        Returns:
            Task ID of the submitted task
        """
        payload = {"task_type": task_type, "args": args, "metadata": metadata or {}}

        if task_id:
            payload["task_id"] = task_id

        data = await self._make_request("POST", "/api/tasks/submit", json_data=payload)
        return data["task_id"]

    async def get_task_status(self, task_id: str) -> TaskResult:
        """
        Get the current status of a task.

        Args:
            task_id: ID of the task to check

        Returns:
            TaskResult with current status
        """
        try:
            task_data = await self._make_request("GET", f"/api/tasks/{task_id}")
            return TaskResult(
                task_id=task_data["task_id"],
                status=TaskStatus(task_data["status"]),
                result=task_data.get("result"),
                error=task_data.get("error"),
                progress=task_data.get("progress", 0.0),
                created_at=task_data.get("created_at", 0.0),
                started_at=task_data.get("started_at"),
                completed_at=task_data.get("completed_at"),
                metadata=task_data.get("metadata"),
            )
        except GoBridgeError as e:
            raise ValueError(f"Task {task_id} not found: {e}")

    async def get_all_tasks(self) -> list[TaskResult]:
        """
        Get all tasks from the task manager.

        Returns:
            List of TaskResult objects
        """
        try:
            data = await self._make_request("GET", "/api/tasks")
            tasks = []
            for task_data in data:
                tasks.append(
                    TaskResult(
                        task_id=task_data["task_id"],
                        status=TaskStatus(task_data["status"]),
                        result=task_data.get("result"),
                        error=task_data.get("error"),
                        progress=task_data.get("progress", 0.0),
                        created_at=task_data.get("created_at", 0.0),
                        started_at=task_data.get("started_at"),
                        completed_at=task_data.get("completed_at"),
                        metadata=task_data.get("metadata"),
                    )
                )
            return tasks
        except GoBridgeError as e:
            raise Exception(f"Failed to get tasks: {e}")

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending task.

        Args:
            task_id: ID of the task to cancel

        Returns:
            True if cancellation was successful
        """
        try:
            data = await self._make_request("POST", f"/api/tasks/cancel/{task_id}")
            return True
        except GoBridgeError as e:
            raise Exception(f"Failed to cancel task: {e}")

    async def update_progress(self, task_id: str, progress: float) -> bool:
        """
        Update the progress of a running task.

        Args:
            task_id: ID of the task to update
            progress: Progress value (0.0 to 1.0)

        Returns:
            True if update was successful
        """
        try:
            data = await self._make_request(
                "POST", f"/api/tasks/progress/{task_id}", json_data={"progress": progress}
            )
            return True
        except GoBridgeError as e:
            raise Exception(f"Failed to update progress: {e}")

    async def get_statistics(self) -> dict[str, Any]:
        """
        Get task manager statistics.

        Returns:
            Dictionary with statistics
        """
        try:
            return await self._make_request("GET", "/api/tasks/stats")
        except GoBridgeError as e:
            raise Exception(f"Failed to get statistics: {e}")

    async def cleanup_old_tasks(self, max_age_seconds: int = 3600) -> int:
        """
        Clean up old completed/failed tasks.

        Args:
            max_age_seconds: Maximum age in seconds for tasks to keep

        Returns:
            Number of tasks removed
        """
        try:
            data = await self._make_request(
                "POST", "/api/tasks/cleanup", json_data={"max_age_seconds": max_age_seconds}
            )
            return data["removed_count"]
        except GoBridgeError as e:
            raise Exception(f"Failed to cleanup tasks: {e}")

    async def wait_for_completion(
        self, task_id: str, check_interval: float = 1.0, timeout: float | None = None
    ) -> TaskResult:
        """
        Wait for a task to complete.

        Args:
            task_id: ID of the task to wait for
            check_interval: Seconds between status checks
            timeout: Maximum seconds to wait (None for no timeout)

        Returns:
            Final TaskResult
        """
        start_time = time.time()

        while True:
            result = await self.get_task_status(task_id)

            if result.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return result

            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Task {task_id} did not complete within {timeout} seconds")

            await asyncio.sleep(check_interval)


# Singleton instance for easy access
_global_bridge: GoTaskManagerBridge | None = None
_bridge_lock = threading.Lock()


def get_task_manager_bridge(host: str = "localhost", port: int = 7071) -> GoTaskManagerBridge:
    """Get the singleton task manager bridge instance"""
    global _global_bridge

    with _bridge_lock:
        if _global_bridge is None:
            _global_bridge = create_bridge_client(
                GoTaskManagerBridge, "task_manager", host=host, port=port
            )
        return _global_bridge


# Convenience functions for common operations
async def submit_price_scan(subscription_id: str, regions: list[str]) -> str:
    """
    Submit a price scan task.

    Args:
        subscription_id: Cloud subscription ID
        regions: List of regions to scan

    Returns:
        Task ID for tracking
    """
    bridge = get_task_manager_bridge()
    return await bridge.submit_task(
        task_type="price_scan",
        args=[subscription_id, regions],
        metadata={"subscription_id": subscription_id, "regions": regions},
    )


async def submit_resource_audit(subscription_id: str) -> str:
    """
    Submit a resource audit task.

    Args:
        subscription_id: Cloud subscription ID

    Returns:
        Task ID for tracking
    """
    bridge = get_task_manager_bridge()
    return await bridge.submit_task(
        task_type="resource_audit",
        args=[subscription_id],
        metadata={"subscription_id": subscription_id},
    )


async def submit_cost_analysis(subscription_id: str, days: int = 30) -> str:
    """
    Submit a cost analysis task.

    Args:
        subscription_id: Cloud subscription ID
        days: Number of days to analyze (default: 30)

    Returns:
        Task ID for tracking
    """
    bridge = get_task_manager_bridge()
    return await bridge.submit_task(
        task_type="cost_analysis",
        args=[subscription_id, days],
        metadata={"subscription_id": subscription_id, "days": days},
    )


async def submit_metrics_fetch(resource_ids: list[str]) -> str:
    """
    Submit a metrics fetch task.

    Args:
        resource_ids: List of resource IDs to fetch metrics for

    Returns:
        Task ID for tracking
    """
    bridge = get_task_manager_bridge()
    return await bridge.submit_task(
        task_type="metrics_fetch",
        args=[resource_ids],
        metadata={"resource_count": len(resource_ids)},
    )
