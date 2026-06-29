package anomaly

import (
	"encoding/json"
	"log"
	"net/http"
	"strconv"
	"sync"
	"time"
)

// Global anomaly detector instance
var (
	globalDetector *AnomalyDetector
	anomalyInit    sync.Once
)

// GetAnomalyDetector returns the singleton anomaly detector instance
func GetAnomalyDetector() *AnomalyDetector {
	anomalyInit.Do(func() {
		globalDetector = NewAnomalyDetector()
		log.Println("[Anomaly Detector] Initialized anomaly detection engine")
	})
	return globalDetector
}

// HTTPResponse is a standard response wrapper
type HTTPResponse struct {
	Success bool        `json:"success"`
	Data    interface{} `json:"data,omitempty"`
	Error   string      `json:"error,omitempty"`
}

// DetectRequest represents a single metric detection request
type DetectRequest struct {
	Timestamp  int64             `json:"timestamp"`
	Value      float64           `json:"value"`
	Labels     map[string]string `json:"labels"`
	MetricName string            `json:"metric_name"`
}

// BatchDetectRequest represents a batch detection request
type BatchDetectRequest struct {
	Metrics []DetectRequest `json:"metrics"`
}

// ConfigRequest represents a configuration request
type ConfigRequest struct {
	Threshold  float64 `json:"threshold"`
	WindowSize int     `json:"window_size"`
}

// RegisterAnomalyHandlers registers HTTP handlers for anomaly detection
func RegisterAnomalyHandlers(mux *http.ServeMux) {
	detector := GetAnomalyDetector()

	// Health check endpoint
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		sendJSONResponse(w, map[string]string{
			"status":  "healthy",
			"service": "anomaly_detector",
		})
	})

	// Detect anomaly for single metric
	mux.HandleFunc("/api/anomaly/detect", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req DetectRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		timestamp := time.Now()
		if req.Timestamp > 0 {
			timestamp = time.Unix(req.Timestamp, 0)
		}

		metric := MetricData{
			Timestamp:  timestamp,
			Value:      req.Value,
			Labels:     req.Labels,
			MetricName: req.MetricName,
		}

		result := detector.DetectAnomaly(metric)

		sendJSONResponse(w, result)
	})

	// Batch detect anomalies
	mux.HandleFunc("/api/anomaly/batch_detect", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req BatchDetectRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		metrics := make([]MetricData, len(req.Metrics))
		for i, m := range req.Metrics {
			timestamp := time.Now()
			if m.Timestamp > 0 {
				timestamp = time.Unix(m.Timestamp, 0)
			}

			metrics[i] = MetricData{
				Timestamp:  timestamp,
				Value:      m.Value,
				Labels:     m.Labels,
				MetricName: m.MetricName,
			}
		}

		results := detector.DetectAnomaliesBatch(metrics)

		sendJSONResponse(w, map[string]interface{}{
			"results":       results,
			"total_count":   len(results),
			"anomaly_count": countAnomalies(results),
		})
	})

	// Get metric buffer
	mux.HandleFunc("/api/anomaly/buffer", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		metricName := r.URL.Query().Get("metric_name")
		if metricName == "" {
			sendJSONError(w, "metric_name parameter is required", http.StatusBadRequest)
			return
		}

		buffer := detector.GetMetricBuffer(metricName)

		sendJSONResponse(w, map[string]interface{}{
			"metric_name": metricName,
			"buffer_size": len(buffer),
			"data":        buffer,
		})
	})

	// Clear metric buffer
	mux.HandleFunc("/api/anomaly/clear_buffer", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req struct {
			MetricName string `json:"metric_name"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		if req.MetricName == "" {
			detector.ClearAllBuffers()
			sendJSONResponse(w, map[string]string{"status": "all_cleared"})
		} else {
			detector.ClearBuffer(req.MetricName)
			sendJSONResponse(w, map[string]string{"status": "cleared"})
		}
	})

	// Set configuration
	mux.HandleFunc("/api/anomaly/config", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req ConfigRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		if req.Threshold > 0 {
			detector.SetThreshold(req.Threshold)
		}
		if req.WindowSize > 0 {
			detector.SetWindowSize(req.WindowSize)
		}

		sendJSONResponse(w, map[string]interface{}{
			"threshold":   detector.threshold,
			"window_size": detector.windowSize,
		})
	})

	// Get statistics
	mux.HandleFunc("/api/anomaly/stats", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		stats := detector.statisticalDetector.GetStatistics()

		// Add buffer statistics
		detector.bufferMu.RLock()
		totalMetrics := len(detector.metricBuffer)
		totalDataPoints := 0
		for _, buffer := range detector.metricBuffer {
			totalDataPoints += len(buffer)
		}
		detector.bufferMu.RUnlock()

		stats["total_metrics"] = totalMetrics
		stats["total_data_points"] = totalDataPoints
		stats["buffer_size"] = detector.bufferSize

		sendJSONResponse(w, stats)
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

func countAnomalies(results []AnomalyResult) int {
	count := 0
	for _, result := range results {
		if result.IsAnomaly {
			count++
		}
	}
	return count
}

// StartAnomalyServer starts the anomaly detection HTTP server
func StartAnomalyServer(port int) error {
	mux := http.NewServeMux()
	RegisterAnomalyHandlers(mux)

	addr := ":" + strconv.Itoa(port)
	log.Printf("Starting anomaly detection server on %s", addr)
	return http.ListenAndServe(addr, mux)
}
