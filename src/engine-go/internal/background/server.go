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

	"cloud-reaper/engine-go/internal/collectors"
	"cloud-reaper/engine-go/internal/db"
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

		// Validate task type
		if req.TaskType == "" {
			sendJSONError(w, "task_type is required", http.StatusBadRequest)
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

		// Validate task ID format (basic check)
		if len(taskID) > 100 {
			sendJSONError(w, "task_id must be less than 100 characters", http.StatusBadRequest)
			return
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

		// Validate progress value
		if req.Progress < 0 || req.Progress > 1 {
			sendJSONError(w, "progress must be between 0 and 1", http.StatusBadRequest)
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

// Real task implementations using actual collectors and database operations
func priceScanTask(ctx context.Context, args []interface{}) (interface{}, error) {
	log.Printf("Starting price scan task with args: %v", args)

	// Extract provider from args
	provider := "azure" // default
	if len(args) > 0 {
		if p, ok := args[0].(string); ok {
			provider = p
		}
	}

	// Create provider scraper
	cloudProvider, err := collectors.NewProvider(provider)
	if err != nil {
		return nil, fmt.Errorf("failed to create provider: %w", err)
	}

	// Get credentials from environment or args
	creds := make(map[string]string)
	if len(args) > 1 {
		if argsMap, ok := args[1].(map[string]interface{}); ok {
			for k, v := range argsMap {
				creds[k] = fmt.Sprintf("%v", v)
			}
		}
	}

	// Authenticate
	if err := cloudProvider.Authenticate(creds); err != nil {
		return nil, fmt.Errorf("authentication failed: %w", err)
	}

	// Scan resources to get SKUs
	resources, err := cloudProvider.ScanResources()
	if err != nil {
		return nil, fmt.Errorf("resource scan failed: %w", err)
	}

	// Collect unique SKUs and regions
	skuSet := make(map[string]bool)
	regionSet := make(map[string]bool)

	for _, resource := range resources {
		if resource.SKU != "" {
			skuSet[resource.SKU] = true
		}
		if resource.Region != "" {
			regionSet[resource.Region] = true
		}
	}

	// Convert to slices
	skus := make([]string, 0, len(skuSet))
	regions := make([]string, 0, len(regionSet))

	for sku := range skuSet {
		skus = append(skus, sku)
	}
	for region := range regionSet {
		regions = append(regions, region)
	}

	result := map[string]interface{}{
		"skus_scanned": len(skus),
		"regions":      regions,
		"skus":         skus,
		"timestamp":    time.Now().Unix(),
		"provider":     provider,
	}

	log.Printf("Price scan completed: %d SKUs across %d regions", len(skus), len(regions))
	return result, nil
}

func resourceAuditTask(ctx context.Context, args []interface{}) (interface{}, error) {
	log.Printf("Starting resource audit task with args: %v", args)

	// Extract provider from args
	provider := "azure" // default
	if len(args) > 0 {
		if p, ok := args[0].(string); ok {
			provider = p
		}
	}

	// Create provider scraper
	cloudProvider, err := collectors.NewProvider(provider)
	if err != nil {
		return nil, fmt.Errorf("failed to create provider: %w", err)
	}

	// Get credentials from environment or args
	creds := make(map[string]string)
	if len(args) > 1 {
		if argsMap, ok := args[1].(map[string]interface{}); ok {
			for k, v := range argsMap {
				creds[k] = fmt.Sprintf("%v", v)
			}
		}
	}

	// Authenticate
	if err := cloudProvider.Authenticate(creds); err != nil {
		return nil, fmt.Errorf("authentication failed: %w", err)
	}

	// Scan resources
	resources, err := cloudProvider.ScanResources()
	if err != nil {
		return nil, fmt.Errorf("resource scan failed: %w", err)
	}

	// Perform audit checks
	issuesFound := 0
	auditedResources := len(resources)

	for _, resource := range resources {
		// Check for common issues
		if resource.Tags == nil || len(resource.Tags) == 0 {
			issuesFound++ // Missing tags
		}
		if resource.Active && resource.Usage > 80.0 {
			// Check for expensive running instances with high utilization
			issuesFound++
		}
	}

	result := map[string]interface{}{
		"resources_audited": auditedResources,
		"issues_found":      issuesFound,
		"timestamp":         time.Now().Unix(),
		"provider":          provider,
	}

	log.Printf("Resource audit completed: %d resources audited, %d issues found", auditedResources, issuesFound)
	return result, nil
}

func costAnalysisTask(ctx context.Context, args []interface{}) (interface{}, error) {
	log.Printf("Starting cost analysis task with args: %v", args)

	// Connect to database
	database, err := db.Connect()
	if err != nil {
		return nil, fmt.Errorf("database connection failed: %w", err)
	}
	defer database.Close()

	// Get resources from database
	resources, err := db.GetAllResources(database)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch resources: %w", err)
	}

	// Calculate total cost and potential savings
	totalCost := 0.0
	potentialSavings := 0.0

	for _, resource := range resources {
		if resource.HourlyPrice > 0 {
			// Estimate monthly cost (720 hours)
			monthlyCost := resource.HourlyPrice * 720
			totalCost += monthlyCost

			// Simple savings estimation
			if resource.State == "running" && resource.HourlyPrice > 0.5 {
				// Potential savings from rightsizing or stopping
				potentialSavings += monthlyCost * 0.2 // Assume 20% potential savings
			}
		}
	}

	result := map[string]interface{}{
		"total_cost":      totalCost,
		"savings_found":   potentialSavings,
		"resources_count": len(resources),
		"timestamp":       time.Now().Unix(),
	}

	log.Printf("Cost analysis completed: total cost $%.2f, potential savings $%.2f", totalCost, potentialSavings)
	return result, nil
}

func metricsFetchTask(ctx context.Context, args []interface{}) (interface{}, error) {
	log.Printf("Starting metrics fetch task with args: %v", args)

	// Extract provider from args
	provider := "azure" // default
	if len(args) > 0 {
		if p, ok := args[0].(string); ok {
			provider = p
		}
	}

	// Create provider scraper
	cloudProvider, err := collectors.NewProvider(provider)
	if err != nil {
		return nil, fmt.Errorf("failed to create provider: %w", err)
	}

	// Get credentials from environment or args
	creds := make(map[string]string)
	if len(args) > 1 {
		if argsMap, ok := args[1].(map[string]interface{}); ok {
			for k, v := range argsMap {
				creds[k] = fmt.Sprintf("%v", v)
			}
		}
	}

	// Authenticate
	if err := cloudProvider.Authenticate(creds); err != nil {
		return nil, fmt.Errorf("authentication failed: %w", err)
	}

	// Scan resources to get metrics
	resources, err := cloudProvider.ScanResources()
	if err != nil {
		return nil, fmt.Errorf("resource scan failed: %w", err)
	}

	// Calculate aggregate metrics
	totalResources := len(resources)
	runningResources := 0
	totalHourlyCost := 0.0

	for _, resource := range resources {
		if resource.Active {
			runningResources++
		}
		// Simplified cost estimation based on usage
		totalHourlyCost += resource.Usage * 0.1 // Placeholder cost calculation
	}

	// Calculate utilization metrics
	cpuUtilization := 0.0
	memoryUsage := 0.0

	if totalResources > 0 {
		cpuUtilization = float64(runningResources) / float64(totalResources) * 100
		memoryUsage = cpuUtilization * 0.8 // Simplified memory estimation
	}

	result := map[string]interface{}{
		"total_resources":   totalResources,
		"running_resources": runningResources,
		"cpu_utilization":   cpuUtilization,
		"memory_usage":      memoryUsage,
		"total_hourly_cost": totalHourlyCost,
		"timestamp":         time.Now().Unix(),
		"provider":          provider,
	}

	log.Printf("Metrics fetch completed: %d total resources, %d running, %.1f%% CPU utilization",
		totalResources, runningResources, cpuUtilization)
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
