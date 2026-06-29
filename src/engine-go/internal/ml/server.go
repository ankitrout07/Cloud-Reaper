package ml

import (
	"encoding/json"
	"log"
	"net/http"
	"strconv"
	"sync"
)

// Global rightsizing agent instance
var (
	globalAgent *RightsizingAgent
	mlInit      sync.Once
)

// GetRightsizingAgent returns the singleton rightsizing agent instance
func GetRightsizingAgent(environmentType string) *RightsizingAgent {
	mlInit.Do(func() {
		globalAgent = NewRightsizingAgent(environmentType)
		log.Println("[ML Agent] Initialized rightsizing agent")
	})
	return globalAgent
}

// HTTPResponse is a standard response wrapper
type HTTPResponse struct {
	Success bool        `json:"success"`
	Data    interface{} `json:"data,omitempty"`
	Error   string      `json:"error,omitempty"`
}

// EvaluateRequest represents a single evaluation request
type EvaluateRequest struct {
	Metrics         map[string]float64 `json:"metrics"`
	CurrentSKU      string             `json:"current_sku"`
	EnvironmentType string             `json:"environment_type,omitempty"`
}

// BatchEvaluateRequest represents a batch evaluation request
type BatchEvaluateRequest struct {
	MetricsList     []map[string]float64 `json:"metrics_list"`
	CurrentSKUs     []string             `json:"current_skus"`
	EnvironmentType string               `json:"environment_type,omitempty"`
}

// TrainingRequest represents a training request
type TrainingRequest struct {
	State     map[string]float64 `json:"state"`
	Action    int                `json:"action"`
	Reward    float64            `json:"reward"`
	NextState map[string]float64 `json:"next_state"`
}

// ConfigRequest represents a configuration request
type ConfigRequest struct {
	LearningRate    float64 `json:"learning_rate"`
	DiscountFactor  float64 `json:"discount_factor"`
	ExplorationRate float64 `json:"exploration_rate"`
	EnvironmentType string  `json:"environment_type"`
}

// RegisterMLHandlers registers HTTP handlers for ML operations
func RegisterMLHandlers(mux *http.ServeMux, environmentType string) {
	agent := GetRightsizingAgent(environmentType)

	// Health check endpoint
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		sendJSONResponse(w, map[string]string{
			"status":  "healthy",
			"service": "ml_agent",
		})
	})

	// Evaluate migration for single instance
	mux.HandleFunc("/api/ml/evaluate", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req EvaluateRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		result := agent.EvaluateMigration(req.Metrics, req.CurrentSKU, req.EnvironmentType)

		sendJSONResponse(w, result)
	})

	// Batch evaluate migration for multiple instances
	mux.HandleFunc("/api/ml/batch_evaluate", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req BatchEvaluateRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		if len(req.MetricsList) != len(req.CurrentSKUs) {
			sendJSONError(w, "metrics_list and current_skus must have same length", http.StatusBadRequest)
			return
		}

		results := agent.BatchEvaluateMigration(req.MetricsList, req.CurrentSKUs)

		sendJSONResponse(w, map[string]interface{}{
			"results":     results,
			"total_count": len(results),
		})
	})

	// Train the agent with a single experience
	mux.HandleFunc("/api/ml/train", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req TrainingRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		state := agent.GetState(req.State["cpu"], req.State["mem"], req.State["iops"], req.State["net"])
		nextState := agent.GetState(req.NextState["cpu"], req.NextState["mem"], req.NextState["iops"], req.NextState["net"])

		agent.Learn(state, req.Action, req.Reward, nextState)

		sendJSONResponse(w, map[string]string{"status": "trained"})
	})

	// Set configuration
	mux.HandleFunc("/api/ml/config", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req ConfigRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		if req.LearningRate > 0 {
			agent.SetLearningRate(req.LearningRate)
		}
		if req.DiscountFactor > 0 {
			agent.SetDiscountFactor(req.DiscountFactor)
		}
		if req.ExplorationRate >= 0 {
			agent.SetExplorationRate(req.ExplorationRate)
		}
		if req.EnvironmentType != "" {
			agent.environmentType = req.EnvironmentType
			agent.setRiskThresholds()
		}

		sendJSONResponse(w, map[string]interface{}{
			"learning_rate":    agent.learningRate,
			"discount_factor":  agent.discountFactor,
			"exploration_rate": agent.explorationRate,
			"environment_type": agent.environmentType,
		})
	})

	// Get statistics
	mux.HandleFunc("/api/ml/stats", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		sendJSONResponse(w, map[string]interface{}{
			"q_table_size":     agent.GetQTableSize(),
			"learning_rate":    agent.learningRate,
			"discount_factor":  agent.discountFactor,
			"exploration_rate": agent.explorationRate,
			"environment_type": agent.environmentType,
			"risk_thresholds":  agent.riskThresholds,
			"actions":          agent.actions,
		})
	})

	// Reset Q-table
	mux.HandleFunc("/api/ml/reset", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		agent.Reset()

		sendJSONResponse(w, map[string]string{"status": "reset"})
	})
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

// StartMLServer starts the ML agent HTTP server
func StartMLServer(port int, environmentType string) error {
	mux := http.NewServeMux()
	RegisterMLHandlers(mux, environmentType)

	addr := ":" + strconv.Itoa(port)
	log.Printf("Starting ML agent server on %s", addr)
	return http.ListenAndServe(addr, mux)
}
