"""
Background Task Manager for Cloud-Reaper
Handles async background tasks for heavy computations and long-running operations
Now supports both Python asyncio and Go-based task management for improved performance
"""

import asyncio
import os
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

# Try to import Go task manager bridge for enhanced performance
try:
    from reaper.engine.core.go_task_manager import (
        GoTaskManagerBridge,
        get_task_manager_bridge,
        TaskStatus as GoTaskStatus
    )
    GO_TASK_MANAGER_AVAILABLE = True
except ImportError:
    GO_TASK_MANAGER_AVAILABLE = False


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskResult:
    task_id: str
    status: TaskStatus
    result: Any = None
    error: str | None = None
    progress: float = 0.0
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None


class BackgroundTaskManager:
    """
    Manages background tasks with progress tracking and result caching.
    Uses asyncio for non-blocking task execution, with optional Go backend for enhanced performance.
    """

    def __init__(self, max_concurrent_tasks: int = 10, use_go_backend: bool = True):
        self.max_concurrent_tasks = max_concurrent_tasks
        self.tasks: dict[str, TaskResult] = {}
        self.task_queue: deque = deque()
        self.running_tasks: set = set()
        self.semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._running = False
        self._worker_task: asyncio.Task | None = None
        
        # Try to use Go backend if available and enabled
        self.use_go_backend = use_go_backend and GO_TASK_MANAGER_AVAILABLE
        self.go_bridge: GoTaskManagerBridge | None = None
        
        if self.use_go_backend:
            try:
                # Get Go task manager host/port from environment or use defaults
                go_host = os.getenv("GO_TASK_MANAGER_HOST", "localhost")
                go_port = int(os.getenv("GO_TASK_MANAGER_PORT", "7071"))
                self.go_bridge = get_task_manager_bridge(host=go_host, port=go_port)
                print("[Go Task Manager] Using Go backend for enhanced performance")
            except Exception as e:
                print(f"[Go Task Manager] Failed to initialize Go backend: {e}")
                self.use_go_backend = False
                self.go_bridge = None

    async def start(self):
        """Start the background task worker."""
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._worker())

    async def stop(self):
        """Stop the background task worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
        # Close Go bridge connection if used
        if self.go_bridge:
            try:
                await self.go_bridge.close()
            except Exception as e:
                print(f"[Go Task Manager] Error closing Go bridge: {e}")

    async def _worker(self):
        """Worker coroutine that processes queued tasks."""
        while self._running:
            try:
                if self.task_queue:
                    task_id, func, args, kwargs = self.task_queue.popleft()
                    asyncio.create_task(self._execute_task(task_id, func, args, kwargs))
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"[!] Background task worker error: {e}")

    async def _execute_task(self, task_id: str, func: Callable, args: tuple, kwargs: dict):
        """Execute a single task with progress tracking."""
        async with self.semaphore:
            if task_id not in self.tasks:
                return

            task = self.tasks[task_id]
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()
            self.running_tasks.add(task_id)

            try:
                # Execute the function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                task.status = TaskStatus.COMPLETED
                task.result = result
                task.progress = 1.0
                task.completed_at = time.time()
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.completed_at = time.time()
            finally:
                self.running_tasks.discard(task_id)

    async def submit_task(self, func: Callable, *args, task_id: str | None = None, **kwargs) -> str:
        """
        Submit a task for background execution.

        Args:
            func: The function to execute
            *args: Positional arguments for the function
            task_id: Optional custom task ID (auto-generated if not provided)
            **kwargs: Keyword arguments for the function

        Returns:
            Task ID for tracking
        """
        if task_id is None:
            task_id = str(uuid4())

        # Try to use Go backend if available and the function is a known task type
        if self.use_go_backend and self.go_bridge:
            try:
                # Check if this is a known Go task type
                task_type = self._get_go_task_type(func)
                if task_type:
                    go_task_id = await self.go_bridge.submit_task(
                        task_type=task_type,
                        args=list(args),
                        task_id=task_id,
                        metadata=kwargs
                    )
                    # Create task record with Go backend reference
                    self.tasks[task_id] = TaskResult(
                        task_id=task_id, 
                        status=TaskStatus.PENDING,
                        metadata={"backend": "go", "go_task_id": go_task_id}
                    )
                    return task_id
            except Exception as e:
                print(f"[Go Task Manager] Failed to submit task to Go backend: {e}")
                # Fall back to Python execution

        # Create task record
        self.tasks[task_id] = TaskResult(task_id=task_id, status=TaskStatus.PENDING)

        # Add to queue
        self.task_queue.append((task_id, func, args, kwargs))

        return task_id
    
    def _get_go_task_type(self, func: Callable) -> str | None:
        """Map Python functions to Go task types"""
        # This could be enhanced with decorators or function metadata
        func_name = getattr(func, "__name__", "")
        
        # Map known functions to Go task types
        task_mappings = {
            "price_scan_task": "price_scan",
            "resource_audit_task": "resource_audit", 
            "cost_analysis_task": "cost_analysis",
            "metrics_fetch_task": "metrics_fetch",
        }
        
        return task_mappings.get(func_name)

    async def get_task_status(self, task_id: str) -> TaskResult | None:
        """Get the current status of a task (async version with Go backend support)."""
        local_task = self.tasks.get(task_id)
        
        # If task is managed by Go backend, fetch latest status
        if local_task and local_task.metadata and local_task.metadata.get("backend") == "go":
            if self.use_go_backend and self.go_bridge:
                try:
                    go_result = await self.go_bridge.get_task_status(task_id)
                    # Update local task with Go result
                    local_task.status = TaskStatus(go_result.status.value)
                    local_task.result = go_result.result
                    local_task.error = go_result.error
                    local_task.progress = go_result.progress
                    local_task.started_at = go_result.started_at
                    local_task.completed_at = go_result.completed_at
                    return local_task
                except Exception as e:
                    print(f"[Go Task Manager] Failed to get task status from Go: {e}")
        
        return local_task

    async def get_all_tasks(self) -> list[TaskResult]:
        """Get all tasks."""
        # If using Go backend, try to fetch all tasks from there
        if self.use_go_backend and self.go_bridge:
            try:
                go_tasks = await self.go_bridge.get_all_tasks()
                # Update local tasks with Go data
                for go_task in go_tasks:
                    if go_task.task_id not in self.tasks:
                        self.tasks[go_task.task_id] = TaskResult(
                            task_id=go_task.task_id,
                            status=TaskStatus(go_task.status.value),
                            result=go_task.result,
                            error=go_task.error,
                            progress=go_task.progress,
                            created_at=go_task.created_at,
                            started_at=go_task.started_at,
                            completed_at=go_task.completed_at,
                            metadata={"backend": "go"}
                        )
                    else:
                        # Update existing task
                        local_task = self.tasks[go_task.task_id]
                        local_task.status = TaskStatus(go_task.status.value)
                        local_task.result = go_task.result
                        local_task.error = go_task.error
                        local_task.progress = go_task.progress
                        local_task.started_at = go_task.started_at
                        local_task.completed_at = go_task.completed_at
            except Exception as e:
                print(f"[Go Task Manager] Failed to get all tasks from Go: {e}")
        
        return list(self.tasks.values())

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending task.
        Note: Cannot cancel running tasks.
        """
        if task_id not in self.tasks:
            return False

        task = self.tasks[task_id]

        # If task is managed by Go backend, try to cancel it there
        if task.metadata and task.metadata.get("backend") == "go":
            if self.use_go_backend and self.go_bridge:
                try:
                    success = await self.go_bridge.cancel_task(task_id)
                    if success:
                        task.status = TaskStatus.CANCELLED
                        task.completed_at = time.time()
                        return True
                except Exception as e:
                    print(f"[Go Task Manager] Failed to cancel task in Go: {e}")
                    # Fall through to local cancellation

        if task.status == TaskStatus.PENDING:
            # Remove from queue
            self.task_queue = deque(item for item in self.task_queue if item[0] != task_id)
            task.status = TaskStatus.CANCELLED
            task.completed_at = time.time()
            return True

        return False

    def cleanup_old_tasks(self, max_age_seconds: float = 3600):
        """Remove completed/failed tasks older than max_age_seconds."""
        current_time = time.time()
        to_remove = []

        for task_id, task in self.tasks.items():
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                if task.completed_at and (current_time - task.completed_at) > max_age_seconds:
                    to_remove.append(task_id)

        for task_id in to_remove:
            del self.tasks[task_id]

        return len(to_remove)

    def get_statistics(self) -> dict[str, Any]:
        """Get task manager statistics."""
        total = len(self.tasks)
        pending = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING)
        running = sum(1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING)
        completed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)
        cancelled = sum(1 for t in self.tasks.values() if t.status == TaskStatus.CANCELLED)

        return {
            "total_tasks": total,
            "pending": pending,
            "running": running,
            "completed": completed,
            "failed": failed,
            "cancelled": cancelled,
            "queue_size": len(self.task_queue),
            "max_concurrent": self.max_concurrent_tasks,
        }


# Global background task manager instance
background_manager = BackgroundTaskManager(
    max_concurrent_tasks=10, 
    use_go_backend=True  # Enable Go backend by default for enhanced performance
)


# Decorator for easy background task submission
def background_task(task_id: str | None = None):
    """
    Decorator to mark a function as a background task.

    Usage:
        @background_task(task_id="my_task")
        async def my_heavy_computation(arg1, arg2):
            # Heavy computation here
            return result
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            actual_task_id = task_id or str(uuid4())
            return await background_manager.submit_task(
                func, *args, task_id=actual_task_id, **kwargs
            )

        return wrapper

    return decorator


# Progress tracking helper
class ProgressTracker:
    """Helper class for tracking progress within a task."""

    def __init__(self, task_id: str, manager: BackgroundTaskManager):
        self.task_id = task_id
        self.manager = manager

    def update_progress(self, progress: float):
        """Update task progress (0.0 to 1.0)."""
        if self.task_id in self.manager.tasks:
            self.manager.tasks[self.task_id].progress = min(1.0, max(0.0, progress))

    def increment_progress(self, amount: float = 0.1):
        """Increment task progress by amount."""
        if self.task_id in self.manager.tasks:
            current = self.manager.tasks[self.task_id].progress
            self.manager.tasks[self.task_id].progress = min(1.0, current + amount)
