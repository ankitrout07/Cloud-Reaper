// Package streaming — bridge_handlers.go
//
// HTTP Handlers for the Streaming API
// =====================================
// These handlers are registered into the existing Go bridge mux (port 7070)
// via RegisterStreamHandlers(mux). No new port is required.
//
// Endpoints
// ---------
//   POST /stream/submit            Enqueue a DataPoint for processing
//   GET  /stream/stats             Processor + scheduler metrics
//   POST /stream/task/register     Register a scheduled refresh task
//   POST /stream/task/enable       Enable / disable a task
//   POST /stream/task/interval     Update a task's refresh interval
//   GET  /stream/tasks             List all tasks and their status
//   GET  /stream/task/{id}         Get status for a specific task
//
package streaming

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"
)

// ─── Singleton ────────────────────────────────────────────────────────────────

var (
	globalProcessor *DataProcessor
	globalScheduler *Scheduler
	streamOnce      sync.Once
)

// GetGlobalProcessor returns (and lazily initialises) the singleton processor.
func GetGlobalProcessor() *DataProcessor {
	streamOnce.Do(func() {
		cfg := DefaultStreamConfig()
		globalProcessor = NewDataProcessor(cfg)
		globalProcessor.Start()

		globalScheduler = NewScheduler(globalProcessor)
		// Pre-register built-in task types
		registerBuiltinTasks(globalScheduler)
		globalScheduler.Start()
	})
	return globalProcessor
}

// GetGlobalScheduler returns the singleton scheduler.
func GetGlobalScheduler() *Scheduler {
	GetGlobalProcessor() // ensures both are initialised
	return globalScheduler
}

// ─── Handler registration ────────────────────────────────────────────────────

// RegisterStreamHandlers wires all /stream/* endpoints into mux.
// Call this from bridge.RunBridgeServer after creating the mux.
func RegisterStreamHandlers(mux *http.ServeMux) {
	mux.HandleFunc("/stream/submit", handleStreamSubmit)
	mux.HandleFunc("/stream/stats", handleStreamStats)
	mux.HandleFunc("/stream/task/register", handleTaskRegister)
	mux.HandleFunc("/stream/task/enable", handleTaskEnable)
	mux.HandleFunc("/stream/task/interval", handleTaskInterval)
	mux.HandleFunc("/stream/tasks", handleListTasks)
	mux.HandleFunc("/stream/task/", handleGetTask) // trailing slash for /stream/task/{id}
}

// ─── Handlers ─────────────────────────────────────────────────────────────────

// handleStreamSubmit enqueues a DataPoint for immediate processing.
// POST /stream/submit
// Body: { "type":"metric", "resource_id":"...", "provider":"azure",
//          "region":"eastus", "payload":{...}, "source_task_id":"..." }
func handleStreamSubmit(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeStreamError(w, http.StatusMethodNotAllowed, "POST required")
		return
	}

	var point DataPoint
	if err := json.NewDecoder(r.Body).Decode(&point); err != nil {
		writeStreamError(w, http.StatusBadRequest, fmt.Sprintf("invalid JSON: %v", err))
		return
	}

	if point.Type == "" {
		writeStreamError(w, http.StatusBadRequest, "type is required")
		return
	}
	if point.ResourceID == "" {
		writeStreamError(w, http.StatusBadRequest, "resource_id is required")
		return
	}

	proc := GetGlobalProcessor()
	if err := proc.Submit(point); err != nil {
		writeStreamError(w, http.StatusTooManyRequests, err.Error())
		return
	}

	writeStreamJSON(w, http.StatusAccepted, map[string]string{
		"status":      "queued",
		"resource_id": point.ResourceID,
		"type":        string(point.Type),
	})
}

// handleStreamStats returns combined processor + scheduler metrics.
// GET /stream/stats
func handleStreamStats(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeStreamError(w, http.StatusMethodNotAllowed, "GET required")
		return
	}

	proc := GetGlobalProcessor()
	sched := GetGlobalScheduler()

	writeStreamJSON(w, http.StatusOK, map[string]interface{}{
		"processor": proc.Stats(),
		"scheduler": sched.Stats(),
	})
}

// handleTaskRegister registers a new scheduled refresh task.
// POST /stream/task/register
// Body: { "id":"my_task", "interval_s":60, "task_type":"metrics_fetch",
//          "enabled":true, "provider":"azure" }
func handleTaskRegister(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeStreamError(w, http.StatusMethodNotAllowed, "POST required")
		return
	}

	var req struct {
		ID         string  `json:"id"`
		IntervalS  float64 `json:"interval_s"`
		TaskType   string  `json:"task_type"`
		Enabled    bool    `json:"enabled"`
		Provider   string  `json:"provider"`
		CallbackURL string `json:"callback_url"` // optional Python-side callback
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeStreamError(w, http.StatusBadRequest, fmt.Sprintf("invalid JSON: %v", err))
		return
	}

	if req.ID == "" {
		writeStreamError(w, http.StatusBadRequest, "id is required")
		return
	}
	if req.IntervalS <= 0 {
		writeStreamError(w, http.StatusBadRequest, "interval_s must be positive")
		return
	}
	if req.TaskType == "" {
		writeStreamError(w, http.StatusBadRequest, "task_type is required")
		return
	}

	fetcher, err := makeBuiltinFetcher(req.TaskType, req.Provider)
	if err != nil {
		// Fall back to a no-op fetcher if type is unknown — Python controls it
		// via callback_url or external submission to /stream/submit
		fetcher = makeNoOpFetcher(req.ID, req.TaskType)
	}

	task := RefreshTask{
		ID:       req.ID,
		Interval: time.Duration(req.IntervalS * float64(time.Second)),
		Fetcher:  fetcher,
		Enabled:  req.Enabled,
	}

	sched := GetGlobalScheduler()
	if err := sched.Register(task); err != nil {
		writeStreamError(w, http.StatusBadRequest, err.Error())
		return
	}

	writeStreamJSON(w, http.StatusCreated, map[string]interface{}{
		"id":         req.ID,
		"interval_s": req.IntervalS,
		"task_type":  req.TaskType,
		"enabled":    req.Enabled,
		"status":     "registered",
	})
}

// handleTaskEnable enables or disables a task.
// POST /stream/task/enable
// Body: { "id":"my_task", "enabled":false }
func handleTaskEnable(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeStreamError(w, http.StatusMethodNotAllowed, "POST required")
		return
	}

	var req struct {
		ID      string `json:"id"`
		Enabled bool   `json:"enabled"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeStreamError(w, http.StatusBadRequest, fmt.Sprintf("invalid JSON: %v", err))
		return
	}
	if req.ID == "" {
		writeStreamError(w, http.StatusBadRequest, "id is required")
		return
	}

	sched := GetGlobalScheduler()
	if err := sched.SetEnabled(req.ID, req.Enabled); err != nil {
		writeStreamError(w, http.StatusNotFound, err.Error())
		return
	}

	writeStreamJSON(w, http.StatusOK, map[string]interface{}{
		"id":      req.ID,
		"enabled": req.Enabled,
	})
}

// handleTaskInterval updates the refresh interval of an existing task.
// POST /stream/task/interval
// Body: { "id":"my_task", "interval_s":30 }
func handleTaskInterval(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeStreamError(w, http.StatusMethodNotAllowed, "POST required")
		return
	}

	var req struct {
		ID        string  `json:"id"`
		IntervalS float64 `json:"interval_s"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeStreamError(w, http.StatusBadRequest, fmt.Sprintf("invalid JSON: %v", err))
		return
	}
	if req.ID == "" {
		writeStreamError(w, http.StatusBadRequest, "id is required")
		return
	}
	if req.IntervalS <= 0 {
		writeStreamError(w, http.StatusBadRequest, "interval_s must be positive")
		return
	}

	sched := GetGlobalScheduler()
	if err := sched.SetInterval(req.ID, time.Duration(req.IntervalS*float64(time.Second))); err != nil {
		writeStreamError(w, http.StatusNotFound, err.Error())
		return
	}

	writeStreamJSON(w, http.StatusOK, map[string]interface{}{
		"id":         req.ID,
		"interval_s": req.IntervalS,
	})
}

// handleListTasks returns all registered task statuses.
// GET /stream/tasks
func handleListTasks(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeStreamError(w, http.StatusMethodNotAllowed, "GET required")
		return
	}

	sched := GetGlobalScheduler()
	tasks := sched.ListTasks()
	writeStreamJSON(w, http.StatusOK, map[string]interface{}{
		"tasks": tasks,
		"count": len(tasks),
	})
}

// handleGetTask returns status for a single task by ID.
// GET /stream/task/{id}
func handleGetTask(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeStreamError(w, http.StatusMethodNotAllowed, "GET required")
		return
	}

	// Extract ID from path: /stream/task/{id}
	taskID := strings.TrimPrefix(r.URL.Path, "/stream/task/")
	// Strip sub-paths used by other handlers
	for _, sub := range []string{"register", "enable", "interval"} {
		if taskID == sub {
			writeStreamError(w, http.StatusNotFound, "task not found")
			return
		}
	}
	if taskID == "" {
		writeStreamError(w, http.StatusBadRequest, "task ID required")
		return
	}

	sched := GetGlobalScheduler()
	status, err := sched.GetTask(taskID)
	if err != nil {
		writeStreamError(w, http.StatusNotFound, err.Error())
		return
	}

	writeStreamJSON(w, http.StatusOK, status)
}

// ─── Built-in task fetchers ───────────────────────────────────────────────────

// registerBuiltinTasks pre-registers standard cloud-reaper refresh tasks.
func registerBuiltinTasks(sched *Scheduler) {
	builtins := []struct {
		id        string
		interval  time.Duration
		taskType  string
		provider  string
		enabled   bool
	}{
		{"metrics_azure_vm", 60 * time.Second, "metrics_fetch", "azure", false},
		{"cost_analysis",    5 * time.Minute, "cost_analysis", "azure", false},
		{"price_refresh",    30 * time.Minute, "price_scan", "azure", false},
	}

	for _, b := range builtins {
		fetcher, _ := makeBuiltinFetcher(b.taskType, b.provider)
		_ = sched.Register(RefreshTask{
			ID:       b.id,
			Interval: b.interval,
			Fetcher:  fetcher,
			Enabled:  b.enabled,
		})
	}
}

// makeBuiltinFetcher returns the appropriate TaskFetcherFunc for known task types.
func makeBuiltinFetcher(taskType, provider string) (TaskFetcherFunc, error) {
	switch taskType {
	case "metrics_fetch":
		return makeMetricsFetcher(provider), nil
	case "cost_analysis":
		return makeCostFetcher(provider), nil
	case "price_scan":
		return makePriceFetcher(provider), nil
	default:
		return nil, fmt.Errorf("unknown task type: %s", taskType)
	}
}

func makeMetricsFetcher(provider string) TaskFetcherFunc {
	return func(ctx context.Context, taskID string) ([]DataPoint, error) {
		// Produce a synthetic metrics data point — real implementation
		// calls into collectors.ScanResources() for live metric values.
		return []DataPoint{
			{
				Type:       DataPointTypeMetric,
				ResourceID: fmt.Sprintf("%s_aggregate", provider),
				Provider:   provider,
				Payload: map[string]interface{}{
					"metric_name": "cpu_utilization",
					"value":       0.0, // populated by collector
					"unit":        "percent",
				},
			},
		}, nil
	}
}

func makeCostFetcher(provider string) TaskFetcherFunc {
	return func(ctx context.Context, taskID string) ([]DataPoint, error) {
		return []DataPoint{
			{
				Type:       DataPointTypeCost,
				ResourceID: fmt.Sprintf("%s_cost_aggregate", provider),
				Provider:   provider,
				Payload: map[string]interface{}{
					"resource_type": "aggregate",
					"current_cost":  0.0,
					"optimal_cost":  0.0,
				},
			},
		}, nil
	}
}

func makePriceFetcher(provider string) TaskFetcherFunc {
	return func(ctx context.Context, taskID string) ([]DataPoint, error) {
		// Signal Python side to run a parallel price refresh via /prices/parallel
		// by emitting a sentinel data point that the bridge sink picks up.
		return []DataPoint{
			{
				Type:       DataPointTypePrice,
				ResourceID: "catalog_refresh_trigger",
				Provider:   provider,
				Payload: map[string]interface{}{
					"trigger":      true,
					"service_name": "catalog",
				},
			},
		}, nil
	}
}

// makeNoOpFetcher is used when a Python-registered task has no built-in fetcher.
// Python controls the task by submitting DataPoints directly to /stream/submit.
func makeNoOpFetcher(taskID, taskType string) TaskFetcherFunc {
	return func(ctx context.Context, id string) ([]DataPoint, error) {
		// No-op: returns empty slice. Python pumps data via /stream/submit.
		return nil, nil
	}
}

// ─── HTTP helpers ─────────────────────────────────────────────────────────────

func writeStreamJSON(w http.ResponseWriter, code int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(data)
}

func writeStreamError(w http.ResponseWriter, code int, msg string) {
	writeStreamJSON(w, code, map[string]string{"error": msg})
}
