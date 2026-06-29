package background

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"time"
)

// TaskStatus represents the current status of a task
type TaskStatus string

const (
	StatusPending   TaskStatus = "pending"
	StatusRunning   TaskStatus = "running"
	StatusCompleted TaskStatus = "completed"
	StatusFailed    TaskStatus = "failed"
	StatusCancelled TaskStatus = "cancelled"
)

// TaskResult represents the result of a task execution
type TaskResult struct {
	TaskID      string                 `json:"task_id"`
	Status      TaskStatus             `json:"status"`
	Result      interface{}            `json:"result,omitempty"`
	Error       string                 `json:"error,omitempty"`
	Progress    float64                `json:"progress"`
	CreatedAt   time.Time              `json:"created_at"`
	StartedAt   *time.Time             `json:"started_at,omitempty"`
	CompletedAt *time.Time             `json:"completed_at,omitempty"`
	Metadata    map[string]interface{} `json:"metadata,omitempty"`
}

// Task represents a unit of work to be executed
type Task struct {
	ID        string
	Func      TaskFunc
	Args      []interface{}
	Metadata  map[string]interface{}
	CreatedAt time.Time
}

// TaskFunc is the signature for functions that can be executed as tasks
type TaskFunc func(ctx context.Context, args []interface{}) (interface{}, error)

// TaskManager manages background tasks with worker pool pattern
type TaskManager struct {
	maxConcurrent int
	tasks         map[string]*TaskResult
	taskQueue     chan *Task
	runningTasks  map[string]context.CancelFunc
	mu            sync.RWMutex
	wg            sync.WaitGroup
	ctx           context.Context
	cancel        context.CancelFunc
}

// NewTaskManager creates a new background task manager
func NewTaskManager(maxConcurrent int) *TaskManager {
	ctx, cancel := context.WithCancel(context.Background())
	return &TaskManager{
		maxConcurrent: maxConcurrent,
		tasks:         make(map[string]*TaskResult),
		taskQueue:     make(chan *Task, 1000),
		runningTasks:  make(map[string]context.CancelFunc),
		ctx:           ctx,
		cancel:        cancel,
	}
}

// Start begins the task manager worker pool
func (tm *TaskManager) Start() {
	for i := 0; i < tm.maxConcurrent; i++ {
		tm.wg.Add(1)
		go tm.worker()
	}
}

// Stop gracefully shuts down the task manager
func (tm *TaskManager) Stop() {
	tm.cancel()
	close(tm.taskQueue)
	tm.wg.Wait()
}

// worker processes tasks from the queue
func (tm *TaskManager) worker() {
	defer tm.wg.Done()

	for {
		select {
		case <-tm.ctx.Done():
			return
		case task, ok := <-tm.taskQueue:
			if !ok {
				return
			}
			tm.executeTask(task)
		}
	}
}

// executeTask runs a single task with progress tracking
func (tm *TaskManager) executeTask(task *Task) {
	tm.mu.Lock()
	result, exists := tm.tasks[task.ID]
	if !exists {
		tm.mu.Unlock()
		return
	}

	now := time.Now()
	result.Status = StatusRunning
	result.StartedAt = &now

	// Create context for this specific task
	taskCtx, taskCancel := context.WithCancel(tm.ctx)
	tm.runningTasks[task.ID] = taskCancel
	tm.mu.Unlock()

	// Execute the function
	var taskResult interface{}
	var taskErr error

	func() {
		defer func() {
			if r := recover(); r != nil {
				taskErr = fmt.Errorf("task panic: %v", r)
			}
		}()

		taskResult, taskErr = task.Func(taskCtx, task.Args)
	}()

	// Update result
	tm.mu.Lock()
	defer tm.mu.Unlock()

	completedAt := time.Now()
	result.CompletedAt = &completedAt
	result.Progress = 1.0
	delete(tm.runningTasks, task.ID)

	if taskErr != nil {
		result.Status = StatusFailed
		result.Error = taskErr.Error()
	} else {
		result.Status = StatusCompleted
		result.Result = taskResult
	}
}

// SubmitTask adds a new task to the queue
func (tm *TaskManager) SubmitTask(taskID string, fn TaskFunc, args []interface{}, metadata map[string]interface{}) error {
	tm.mu.Lock()
	defer tm.mu.Unlock()

	if _, exists := tm.tasks[taskID]; exists {
		return fmt.Errorf("task %s already exists", taskID)
	}

	now := time.Now()
	result := &TaskResult{
		TaskID:    taskID,
		Status:    StatusPending,
		Progress:  0.0,
		CreatedAt: now,
		Metadata:  metadata,
	}

	tm.tasks[taskID] = result

	task := &Task{
		ID:        taskID,
		Func:      fn,
		Args:      args,
		Metadata:  metadata,
		CreatedAt: now,
	}

	select {
	case tm.taskQueue <- task:
		return nil
	default:
		delete(tm.tasks, taskID)
		return fmt.Errorf("task queue is full")
	}
}

// GetTaskStatus retrieves the current status of a task
func (tm *TaskManager) GetTaskStatus(taskID string) (*TaskResult, error) {
	tm.mu.RLock()
	defer tm.mu.RUnlock()

	result, exists := tm.tasks[taskID]
	if !exists {
		return nil, fmt.Errorf("task %s not found", taskID)
	}

	// Return a copy to avoid race conditions
	resultCopy := *result
	return &resultCopy, nil
}

// GetAllTasks returns all tasks
func (tm *TaskManager) GetAllTasks() []*TaskResult {
	tm.mu.RLock()
	defer tm.mu.RUnlock()

	results := make([]*TaskResult, 0, len(tm.tasks))
	for _, result := range tm.tasks {
		resultCopy := *result
		results = append(results, &resultCopy)
	}

	return results
}

// CancelTask cancels a pending task
func (tm *TaskManager) CancelTask(taskID string) error {
	tm.mu.Lock()
	defer tm.mu.Unlock()

	result, exists := tm.tasks[taskID]
	if !exists {
		return fmt.Errorf("task %s not found", taskID)
	}

	if result.Status != StatusPending {
		return fmt.Errorf("task %s is not pending (current status: %s)", taskID, result.Status)
	}

	// Remove from queue by marking as cancelled
	now := time.Now()
	result.Status = StatusCancelled
	result.CompletedAt = &now

	// Remove from tasks map after a delay
	go func() {
		time.Sleep(5 * time.Minute)
		tm.mu.Lock()
		delete(tm.tasks, taskID)
		tm.mu.Unlock()
	}()

	return nil
}

// UpdateProgress updates the progress of a running task
func (tm *TaskManager) UpdateProgress(taskID string, progress float64) error {
	tm.mu.Lock()
	defer tm.mu.Unlock()

	result, exists := tm.tasks[taskID]
	if !exists {
		return fmt.Errorf("task %s not found", taskID)
	}

	if result.Status != StatusRunning {
		return fmt.Errorf("task %s is not running", taskID)
	}

	if progress < 0 {
		progress = 0
	}
	if progress > 1 {
		progress = 1
	}

	result.Progress = progress
	return nil
}

// CleanupOldTasks removes completed/failed tasks older than maxAge
func (tm *TaskManager) CleanupOldTasks(maxAge time.Duration) int {
	tm.mu.Lock()
	defer tm.mu.Unlock()

	now := time.Now()
	toRemove := make([]string, 0)

	for taskID, result := range tm.tasks {
		if result.Status == StatusCompleted || result.Status == StatusFailed || result.Status == StatusCancelled {
			if result.CompletedAt != nil && now.Sub(*result.CompletedAt) > maxAge {
				toRemove = append(toRemove, taskID)
			}
		}
	}

	for _, taskID := range toRemove {
		delete(tm.tasks, taskID)
	}

	return len(toRemove)
}

// GetStatistics returns task manager statistics
func (tm *TaskManager) GetStatistics() map[string]interface{} {
	tm.mu.RLock()
	defer tm.mu.RUnlock()

	stats := map[string]interface{}{
		"total_tasks":    len(tm.tasks),
		"pending":        0,
		"running":        0,
		"completed":      0,
		"failed":         0,
		"cancelled":      0,
		"queue_size":     len(tm.taskQueue),
		"max_concurrent": tm.maxConcurrent,
	}

	for _, result := range tm.tasks {
		switch result.Status {
		case StatusPending:
			stats["pending"] = stats["pending"].(int) + 1
		case StatusRunning:
			stats["running"] = stats["running"].(int) + 1
		case StatusCompleted:
			stats["completed"] = stats["completed"].(int) + 1
		case StatusFailed:
			stats["failed"] = stats["failed"].(int) + 1
		case StatusCancelled:
			stats["cancelled"] = stats["cancelled"].(int) + 1
		}
	}

	return stats
}

// ToJSON converts task result to JSON
func (tr *TaskResult) ToJSON() (string, error) {
	data, err := json.Marshal(tr)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

// GetRunningTaskCount returns the number of currently running tasks
func (tm *TaskManager) GetRunningTaskCount() int {
	tm.mu.RLock()
	defer tm.mu.RUnlock()

	return len(tm.runningTasks)
}
