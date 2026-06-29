package websocket

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strconv"
	"sync"
	"time"
)

// Global batcher instance
var (
	globalBatcher *WebSocketBatcher
	batcherInit   sync.Once
	emitter       MessageEmitter
)

// SetEmitter sets the global message emitter
func SetEmitter(e MessageEmitter) {
	emitter = e
	batcherInit.Do(func() {
		globalBatcher = NewWebSocketBatcher(e, DefaultBatcherConfig())
		log.Println("[WebSocket Batcher] Initialized with default configuration")
	})
}

// GetBatcher returns the singleton batcher instance
func GetBatcher() *WebSocketBatcher {
	if globalBatcher == nil {
		// Create with mock emitter if none set
		SetEmitter(NewMockEmitter())
	}
	return globalBatcher
}

// HTTPResponse is a standard response wrapper
type HTTPResponse struct {
	Success bool        `json:"success"`
	Data    interface{} `json:"data,omitempty"`
	Error   string      `json:"error,omitempty"`
}

// BatchRequest represents a request to send a batched message
type BatchRequest struct {
	Event string                 `json:"event"`
	Data  map[string]interface{} `json:"data"`
	Room  string                 `json:"room,omitempty"`
}

// ConfigRequest represents a request to update batcher configuration
type ConfigRequest struct {
	BatchIntervalMs int `json:"batch_interval_ms"`
	MaxBatchSize    int `json:"max_batch_size"`
	MaxQueueSize    int `json:"max_queue_size"`
}

// RegisterBatcherHandlers registers HTTP handlers for WebSocket batching
func RegisterBatcherHandlers(mux *http.ServeMux) {
	batcher := GetBatcher()

	// Health check endpoint
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		sendJSONResponse(w, map[string]string{"status": "healthy", "service": "websocket_batcher"})
	})

	// Send a batched message
	mux.HandleFunc("/api/ws/batch/send", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req BatchRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		if err := batcher.Emit(req.Event, req.Data, req.Room); err != nil {
			sendJSONError(w, err.Error(), http.StatusInternalServerError)
			return
		}

		sendJSONResponse(w, map[string]string{"status": "queued"})
	})

	// Flush all pending batches
	mux.HandleFunc("/api/ws/batch/flush", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		if err := batcher.FlushAll(); err != nil {
			sendJSONError(w, err.Error(), http.StatusInternalServerError)
			return
		}

		sendJSONResponse(w, map[string]string{"status": "flushed"})
	})

	// Get batcher statistics
	mux.HandleFunc("/api/ws/batch/stats", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		stats := batcher.GetStatistics()
		sendJSONResponse(w, stats)
	})

	// Update batcher configuration
	mux.HandleFunc("/api/ws/batch/config", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req ConfigRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		batcher.mu.Lock()
		if req.BatchIntervalMs > 0 {
			batcher.config.BatchInterval = time.Duration(req.BatchIntervalMs) * time.Millisecond
		}
		if req.MaxBatchSize > 0 {
			batcher.config.MaxBatchSize = req.MaxBatchSize
		}
		if req.MaxQueueSize > 0 {
			batcher.config.MaxQueueSize = req.MaxQueueSize
		}
		batcher.mu.Unlock()

		sendJSONResponse(w, batcher.GetStatistics())
	})

	// Stop the batcher
	mux.HandleFunc("/api/ws/batch/stop", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		batcher.Stop()
		sendJSONResponse(w, map[string]string{"status": "stopped"})
	})

	// Start the batcher (if stopped)
	mux.HandleFunc("/api/ws/batch/start", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		// Create new batcher if stopped
		if !batcher.running {
			batcher = NewWebSocketBatcher(emitter, DefaultBatcherConfig())
			globalBatcher = batcher
		}

		sendJSONResponse(w, map[string]string{"status": "started"})
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

// StartBatcherServer starts the WebSocket batching HTTP server
func StartBatcherServer(port int) error {
	mux := http.NewServeMux()
	RegisterBatcherHandlers(mux)

	addr := ":" + strconv.Itoa(port)
	log.Printf("Starting WebSocket batching server on %s", addr)
	return http.ListenAndServe(addr, mux)
}