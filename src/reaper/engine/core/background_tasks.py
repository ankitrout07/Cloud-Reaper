"""
Background Task Manager for Cloud-Reaper
Handles async background tasks for heavy computations and long-running operations
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4


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
    error: Optional[str] = None
    progress: float = 0.0
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


class BackgroundTaskManager:
    """
    Manages background tasks with progress tracking and result caching.
    Uses asyncio for non-blocking task execution.
    """
    
    def __init__(self, max_concurrent_tasks: int = 10):
        self.max_concurrent_tasks = max_concurrent_tasks
        self.tasks: Dict[str, TaskResult] = {}
        self.task_queue: deque = deque()
        self.running_tasks: set = set()
        self.semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
    
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
    
    async def submit_task(
        self,
        func: Callable,
        *args,
        task_id: Optional[str] = None,
        **kwargs
    ) -> str:
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
        
        # Create task record
        self.tasks[task_id] = TaskResult(
            task_id=task_id,
            status=TaskStatus.PENDING
        )
        
        # Add to queue
        self.task_queue.append((task_id, func, args, kwargs))
        
        return task_id
    
    def get_task_status(self, task_id: str) -> Optional[TaskResult]:
        """Get the current status of a task."""
        return self.tasks.get(task_id)
    
    def get_all_tasks(self) -> List[TaskResult]:
        """Get all tasks."""
        return list(self.tasks.values())
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending task.
        Note: Cannot cancel running tasks.
        """
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        
        if task.status == TaskStatus.PENDING:
            # Remove from queue
            self.task_queue = deque(
                item for item in self.task_queue 
                if item[0] != task_id
            )
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
    
    def get_statistics(self) -> Dict[str, Any]:
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
            "max_concurrent": self.max_concurrent_tasks
        }


# Global background task manager instance
background_manager = BackgroundTaskManager(max_concurrent_tasks=10)


# Decorator for easy background task submission
def background_task(task_id: Optional[str] = None):
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
