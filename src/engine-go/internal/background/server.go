package background

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strconv"
	"sync"
	"time"
)

// Global task manager instance
var (
	globalTaskManager *TaskManager
	taskManagerInit   sync.Once
)

// GetTaskManager returns the singleton task manager instance
func GetTaskManager() *TaskManager {
	taskManagerInit.Do(func() {
		globalTaskManager = NewTaskManager(10) // Default 10 concurrent workers
		globalTaskManager.Start()
	})
	return globalTaskManager
}

// HTTPResponse is a standard response wrapper
type HTTPResponse struct {
	Success bool        `json:"success"`
	Data    interface{} `json:"data,omitempty"`
	Error   string      `json:"error,omitempty"`
}

// TaskRequest represents a request to submit a task
type TaskRequest struct {
	TaskID   string                 `json:"task_id"`
	TaskType string                 `json:"task_type"` // "price_scan", "resource_audit", etc.
	Args     []interface{}          `json:"args"`
	Metadata map[string]interface{} `json:"metadata"`
}

// RegisterTaskHandlers registers HTTP handlers for task management
func RegisterTaskHandlers(mux *http.ServeMux) {
	tm := GetTaskManager()

	// Health check endpoint
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		sendJSONResponse(w, map[string]string{"status": "healthy", "service": "task_manager"})
	})

	// Submit a new task
	mux.HandleFunc("/api/tasks/submit", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req TaskRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		// Map task type to actual function
		taskFunc, err := getTaskFunction(req.TaskType)
		if err != nil {
			sendJSONError(w, err.Error(), http.StatusBadRequest)
			return
		}

		// Generate task ID if not provided
		taskID := req.TaskID
		if taskID == "" {
			taskID = fmt.Sprintf("task_%d", time.Now().UnixNano())
		}

		if err := tm.SubmitTask(taskID, taskFunc, req.Args, req.Metadata); err != nil {
			sendJSONError(w, err.Error(), http.StatusInternalServerError)
			return
		}

		sendJSONResponse(w, map[string]string{"task_id": taskID, "status": "pending"})
	})

	// Get task status
	mux.HandleFunc("/api/tasks/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		// Extract task ID from URL path
		taskID := r.URL.Path[len("/api/tasks/"):]
		if taskID == "" {
			sendJSONError(w, "Task ID required", http.StatusBadRequest)
			return
		}

		result, err := tm.GetTaskStatus(taskID)
		if err != nil {
			sendJSONError(w, err.Error(), http.StatusNotFound)
			return
		}

		sendJSONResponse(w, result)
	})

	// Get all tasks
	mux.HandleFunc("/api/tasks", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		tasks := tm.GetAllTasks()
		sendJSONResponse(w, tasks)
	})

	// Cancel task
	mux.HandleFunc("/api/tasks/cancel/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		taskID := r.URL.Path[len("/api/tasks/cancel/"):]
		if taskID == "" {
			sendJSONError(w, "Task ID required", http.StatusBadRequest)
			return
		}

		if err := tm.CancelTask(taskID); err != nil {
			sendJSONError(w, err.Error(), http.StatusBadRequest)
			return
		}

		sendJSONResponse(w, map[string]string{"task_id": taskID, "status": "cancelled"})
	})

	// Update task progress
	mux.HandleFunc("/api/tasks/progress/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		taskID := r.URL.Path[len("/api/tasks/progress/"):]
		if taskID == "" {
			sendJSONError(w, "Task ID required", http.StatusBadRequest)
			return
		}

		var req struct {
			Progress float64 `json:"progress"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		if err := tm.UpdateProgress(taskID, req.Progress); err != nil {
			sendJSONError(w, err.Error(), http.StatusBadRequest)
			return
		}

		sendJSONResponse(w, map[string]interface{}{"task_id": taskID, "progress": req.Progress})
	})

	// Get statistics
	mux.HandleFunc("/api/tasks/stats", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		stats := tm.GetStatistics()
		sendJSONResponse(w, stats)
	})

	// Cleanup old tasks
	mux.HandleFunc("/api/tasks/cleanup", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req struct {
			MaxAgeSeconds int `json:"max_age_seconds"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			// Use default max age if not provided
			req.MaxAgeSeconds = 3600
		}

		removed := tm.CleanupOldTasks(time.Duration(req.MaxAgeSeconds) * time.Second)
		sendJSONResponse(w, map[string]interface{}{"removed_count": removed})
	})
}

// getTaskFunction maps task types to actual implementations
func getTaskFunction(taskType string) (TaskFunc, error) {
	switch taskType {
	case "price_scan":
		return priceScanTask, nil
	case "resource_audit":
		return resourceAuditTask, nil
	case "cost_analysis":
		return costAnalysisTask, nil
	case "metrics_fetch":
		return metricsFetchTask, nil
	default:
		return nil, fmt.Errorf("unknown task type: %s", taskType)
	}
}

// Example task implementations
func priceScanTask(ctx context.Context, args []interface{}) (interface{}, error) {
	// Simulate price scanning work
	log.Printf("Starting price scan task with args: %v", args)

	// Simulate progress updates
	for i := 0; i <= 10; i++ {
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		default:
			time.Sleep(100 * time.Millisecond)
			// In a real implementation, we'd update progress here
		}
	}

	result := map[string]interface{}{
		"skus_scanned": 150,
		"regions":      []string{"eastus", "westus2", "westeurope"},
		"timestamp":    time.Now().Unix(),
	}

	return result, nil
}

func resourceAuditTask(ctx context.Context, args []interface{}) (interface{}, error) {
	log.Printf("Starting resource audit task with args: %v", args)

	// Simulate resource auditing
	time.Sleep(500 * time.Millisecond)

	result := map[string]interface{}{
		"resources_audited": 75,
		"issues_found":      12,
		"timestamp":         time.Now().Unix(),
	}

	return result, nil
}

func costAnalysisTask(ctx context.Context, args []interface{}) (interface{}, error) {
	log.Printf("Starting cost analysis task with args: %v", args)

	// Simulate cost analysis
	time.Sleep(300 * time.Millisecond)

	result := map[string]interface{}{
		"total_cost":    1250.50,
		"savings_found": 342.75,
		"timestamp":     time.Now().Unix(),
	}

	return result, nil
}

func metricsFetchTask(ctx context.Context, args []interface{}) (interface{}, error) {
	log.Printf("Starting metrics fetch task with args: %v", args)

	// Simulate metrics fetching
	time.Sleep(200 * time.Millisecond)

	result := map[string]interface{}{
		"cpu_utilization": 45.2,
		"memory_usage":    68.5,
		"timestamp":       time.Now().Unix(),
	}

	return result, nil
}

// Helper functions for HTTP responses
func sendJSONResponse(w http.ResponseWriter, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(HTTPResponse{
		Success: true,
		Data:    data,
	})
}

func sendJSONError(w http.ResponseWriter, message string, statusCode int) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	json.NewEncoder(w).Encode(HTTPResponse{
		Success: false,
		Error:   message,
	})
}

// StartTaskServer starts the task management HTTP server
func StartTaskServer(port int) error {
	mux := http.NewServeMux()
	RegisterTaskHandlers(mux)

	addr := ":" + strconv.Itoa(port)
	log.Printf("Starting task management server on %s", addr)
	return http.ListenAndServe(addr, mux)
}
