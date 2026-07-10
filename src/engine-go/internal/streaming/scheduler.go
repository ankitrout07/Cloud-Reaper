// Package streaming — scheduler.go
//
// Periodic Task Scheduler
// ========================
// Replaces the Python threading.Thread + asyncio.new_event_loop() pattern in
// realtime_refresh.py with a single goroutine-based ticker loop.
//
// Design decisions
// ----------------
//   - One goroutine per Scheduler (not per task): minimises scheduler overhead
//   - Jitter (±10 %) per task on first fire: avoids thundering herd when many
//     tasks are registered with the same interval
//   - Tasks dispatch into DataProcessor.inputChan (non-blocking): a saturated
//     processor drops the dispatch rather than blocking the scheduler tick
//   - Task fetcher functions are regular Go funcs; Python-owned tasks are
//     proxied through the bridge's HTTP callback mechanism
//
package streaming

import (
	"context"
	"fmt"
	"math/rand"
	"sync"
	"time"
)

// ─── Task types ───────────────────────────────────────────────────────────────

// TaskFetcherFunc is a function that produces DataPoints to be processed.
// It receives a context for cancellation and the task's own ID.
// It should return quickly; heavy work goes into the DataProcessor.
type TaskFetcherFunc func(ctx context.Context, taskID string) ([]DataPoint, error)

// RefreshTask defines a recurring data-fetch job.
type RefreshTask struct {
	// ID uniquely identifies this task.
	ID string

	// Interval is how often the task fires.
	Interval time.Duration

	// Fetcher produces the DataPoints for each tick.
	Fetcher TaskFetcherFunc

	// Enabled gates task execution. Can be toggled at runtime.
	Enabled bool

	// LastRun is the UTC time of the most recent successful dispatch.
	LastRun time.Time

	// RunCount is the total number of times this task has fired.
	RunCount int64

	// ErrorCount tracks consecutive errors; resets on success.
	ErrorCount int64

	// LastError is the most recent error message (empty on success).
	LastError string

	// nextRun is the internal scheduled fire time (includes jitter).
	nextRun time.Time
}

// TaskStatus is the read-only view returned to callers via the bridge API.
type TaskStatus struct {
	ID         string    `json:"id"`
	Enabled    bool      `json:"enabled"`
	IntervalS  float64   `json:"interval_s"`
	LastRun    time.Time `json:"last_run"`
	NextRun    time.Time `json:"next_run"`
	RunCount   int64     `json:"run_count"`
	ErrorCount int64     `json:"error_count"`
	LastError  string    `json:"last_error,omitempty"`
}

// ─── Scheduler ────────────────────────────────────────────────────────────────

// Scheduler manages a set of RefreshTasks and dispatches them into a
// DataProcessor at their configured intervals.
type Scheduler struct {
	processor *DataProcessor

	tasks map[string]*RefreshTask
	mu    sync.RWMutex

	ctx    context.Context
	cancel context.CancelFunc

	tickInterval time.Duration // resolution of the scheduler loop (default: 1s)
	running      bool
	wg           sync.WaitGroup

	// Metrics
	totalDispatched int64
	totalErrors     int64
}

// NewScheduler creates a Scheduler that feeds processed results into processor.
func NewScheduler(processor *DataProcessor) *Scheduler {
	ctx, cancel := context.WithCancel(context.Background())
	return &Scheduler{
		processor:    processor,
		tasks:        make(map[string]*RefreshTask),
		ctx:          ctx,
		cancel:       cancel,
		tickInterval: time.Second,
	}
}

// Start launches the scheduler loop. Call only once.
func (s *Scheduler) Start() {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.running {
		return
	}
	s.running = true

	s.wg.Add(1)
	go s.loop()
}

// Stop signals the scheduler to exit and blocks until it does.
func (s *Scheduler) Stop() {
	s.mu.Lock()
	if !s.running {
		s.mu.Unlock()
		return
	}
	s.running = false
	s.mu.Unlock()

	s.cancel()
	s.wg.Wait()
}

// Register adds or replaces a task. If the scheduler is running, the task
// will fire at its next scheduled time.
func (s *Scheduler) Register(task RefreshTask) error {
	if task.ID == "" {
		return fmt.Errorf("task ID cannot be empty")
	}
	if task.Interval <= 0 {
		return fmt.Errorf("task %q: interval must be positive", task.ID)
	}
	if task.Fetcher == nil {
		return fmt.Errorf("task %q: fetcher cannot be nil", task.ID)
	}

	// Apply ±10 % jitter to spread initial fires
	jitter := time.Duration(rand.Int63n(int64(task.Interval/5))) - task.Interval/10
	task.nextRun = time.Now().Add(jitter)
	if !task.Enabled {
		// Tasks registered as disabled skip the first-fire jitter
		task.nextRun = time.Time{}
	}

	s.mu.Lock()
	s.tasks[task.ID] = &task
	s.mu.Unlock()

	return nil
}

// Unregister removes a task by ID.
func (s *Scheduler) Unregister(taskID string) {
	s.mu.Lock()
	delete(s.tasks, taskID)
	s.mu.Unlock()
}

// SetEnabled enables or disables a task at runtime.
func (s *Scheduler) SetEnabled(taskID string, enabled bool) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	task, ok := s.tasks[taskID]
	if !ok {
		return fmt.Errorf("task %q not found", taskID)
	}
	task.Enabled = enabled
	if enabled && task.nextRun.IsZero() {
		// Schedule the first run with jitter
		jitter := time.Duration(rand.Int63n(int64(task.Interval / 5)))
		task.nextRun = time.Now().Add(jitter)
	}
	return nil
}

// SetInterval updates the refresh interval of a task.
func (s *Scheduler) SetInterval(taskID string, interval time.Duration) error {
	if interval <= 0 {
		return fmt.Errorf("interval must be positive")
	}
	s.mu.Lock()
	defer s.mu.Unlock()

	task, ok := s.tasks[taskID]
	if !ok {
		return fmt.Errorf("task %q not found", taskID)
	}
	task.Interval = interval
	return nil
}

// GetTask returns a snapshot of a task's status.
func (s *Scheduler) GetTask(taskID string) (TaskStatus, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	task, ok := s.tasks[taskID]
	if !ok {
		return TaskStatus{}, fmt.Errorf("task %q not found", taskID)
	}
	return taskToStatus(task), nil
}

// ListTasks returns status snapshots for all registered tasks.
func (s *Scheduler) ListTasks() []TaskStatus {
	s.mu.RLock()
	defer s.mu.RUnlock()

	statuses := make([]TaskStatus, 0, len(s.tasks))
	for _, task := range s.tasks {
		statuses = append(statuses, taskToStatus(task))
	}
	return statuses
}

// Stats returns high-level scheduler statistics.
func (s *Scheduler) Stats() map[string]interface{} {
	s.mu.RLock()
	taskCount := len(s.tasks)
	dispatched := s.totalDispatched
	errors := s.totalErrors
	running := s.running
	s.mu.RUnlock()

	return map[string]interface{}{
		"running":          running,
		"task_count":       taskCount,
		"total_dispatched": dispatched,
		"total_errors":     errors,
	}
}

// ─── Internal ─────────────────────────────────────────────────────────────────

// loop is the single goroutine that checks task schedules and dispatches.
func (s *Scheduler) loop() {
	defer s.wg.Done()

	ticker := time.NewTicker(s.tickInterval)
	defer ticker.Stop()

	for {
		select {
		case <-s.ctx.Done():
			return
		case now := <-ticker.C:
			s.tick(now)
		}
	}
}

// tick iterates all tasks and dispatches those that are due.
func (s *Scheduler) tick(now time.Time) {
	s.mu.Lock()
	due := make([]*RefreshTask, 0)
	for _, task := range s.tasks {
		if task.Enabled && !task.nextRun.IsZero() && now.After(task.nextRun) {
			due = append(due, task)
		}
	}
	s.mu.Unlock()

	// Dispatch outside the lock so fetchers don't deadlock on Register calls
	for _, task := range due {
		go s.dispatch(task)
	}
}

// dispatch calls the task's fetcher and submits results to the processor.
func (s *Scheduler) dispatch(task *RefreshTask) {
	points, err := task.Fetcher(s.ctx, task.ID)

	s.mu.Lock()
	defer s.mu.Unlock()

	// Advance schedule (regardless of error, to prevent spinning on failure)
	task.nextRun = time.Now().Add(task.Interval)

	if err != nil {
		task.ErrorCount++
		task.LastError = err.Error()
		s.totalErrors++
		return
	}

	task.LastRun = time.Now()
	task.RunCount++
	task.ErrorCount = 0
	task.LastError = ""
	s.totalDispatched += int64(len(points))

	// Submit all produced data points (non-blocking; drops counted in processor)
	for _, point := range points {
		point.SourceTaskID = task.ID
		_ = s.processor.Submit(point) // errors are drop-counted, not fatal
	}
}

func taskToStatus(t *RefreshTask) TaskStatus {
	return TaskStatus{
		ID:         t.ID,
		Enabled:    t.Enabled,
		IntervalS:  t.Interval.Seconds(),
		LastRun:    t.LastRun,
		NextRun:    t.nextRun,
		RunCount:   t.RunCount,
		ErrorCount: t.ErrorCount,
		LastError:  t.LastError,
	}
}
