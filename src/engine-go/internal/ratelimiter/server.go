package ratelimiter

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strconv"
	"sync"
)

// Global rate limiters
var (
	globalTokenLimiter *TokenBucketRateLimiter
	globalMultiLimiter *MultiLimiter
	limiterInit        sync.Once
)

// InitRateLimiters initializes the global rate limiters
func InitRateLimiters() {
	limiterInit.Do(func() {
		// Default token bucket limiter (20 req/s, burst 20)
		globalTokenLimiter = NewTokenBucketRateLimiter(20.0, 20)

		// Multi-limiter for different contexts
		globalMultiLimiter = NewMultiLimiter()

		// Initialize common rate limiters
		globalMultiLimiter.GetOrCreate("azure", 20.0, 20)
		globalMultiLimiter.GetOrCreate("aws", 20.0, 20)
		globalMultiLimiter.GetOrCreate("gcp", 20.0, 20)
		globalMultiLimiter.GetOrCreate("ai", 10.0, 10)

		log.Println("[Rate Limiter] Initialized global rate limiters")
	})
}

// GetTokenLimiter returns the global token bucket limiter
func GetTokenLimiter() *TokenBucketRateLimiter {
	InitRateLimiters()
	return globalTokenLimiter
}

// GetMultiLimiter returns the global multi-limiter
func GetMultiLimiter() *MultiLimiter {
	InitRateLimiters()
	return globalMultiLimiter
}

// HTTPResponse is a standard response wrapper
type HTTPResponse struct {
	Success bool        `json:"success"`
	Data    interface{} `json:"data,omitempty"`
	Error   string      `json:"error,omitempty"`
}

// RateLimitRequest represents a request to check/update rate limits
type RateLimitRequest struct {
	Key               string  `json:"key,omitempty"`
	RequestsPerSecond float64 `json:"requests_per_second,omitempty"`
	BurstSize         int     `json:"burst_size,omitempty"`
}

// RegisterRateLimiterHandlers registers HTTP handlers for rate limiting
func RegisterRateLimiterHandlers(mux *http.ServeMux) {
	InitRateLimiters()

	// Health check endpoint
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		sendJSONResponse(w, map[string]string{"status": "healthy", "service": "rate_limiter"})
	})

	// Check if request is allowed (default limiter)
	mux.HandleFunc("/api/ratelimit/check", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		allowed := globalTokenLimiter.Allow()
		stats := globalTokenLimiter.GetStatistics()

		sendJSONResponse(w, map[string]interface{}{
			"allowed": allowed,
			"stats":   stats,
		})
	})

	// Wait for rate limit
	mux.HandleFunc("/api/ratelimit/wait", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		waitDuration := globalTokenLimiter.WaitDuration()
		stats := globalTokenLimiter.GetStatistics()

		sendJSONResponse(w, map[string]interface{}{
			"wait_duration_ms": waitDuration.Milliseconds(),
			"stats":            stats,
		})
	})

	// Check if request is allowed for specific context
	mux.HandleFunc("/api/ratelimit/check/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		key := r.URL.Path[len("/api/ratelimit/check/"):]
		if key == "" {
			sendJSONError(w, "Rate limiter key required", http.StatusBadRequest)
			return
		}

		limiter := globalMultiLimiter.GetOrCreate(key, 20.0, 20)
		allowed := limiter.Allow()
		stats := limiter.GetStatistics()

		sendJSONResponse(w, map[string]interface{}{
			"allowed": allowed,
			"stats":   stats,
		})
	})

	// Update rate limit configuration
	mux.HandleFunc("/api/ratelimit/config", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req RateLimitRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		if req.Key != "" {
			// Update specific limiter
			limiter := globalMultiLimiter.GetOrCreate(req.Key, 20.0, 20)
			if req.RequestsPerSecond > 0 {
				limiter.UpdateRate(req.RequestsPerSecond)
			}
			if req.BurstSize > 0 {
				limiter.UpdateBurst(req.BurstSize)
			}
			sendJSONResponse(w, limiter.GetStatistics())
		} else {
			// Update default limiter
			if req.RequestsPerSecond > 0 {
				globalTokenLimiter.UpdateRate(req.RequestsPerSecond)
			}
			if req.BurstSize > 0 {
				globalTokenLimiter.UpdateBurst(req.BurstSize)
			}
			sendJSONResponse(w, globalTokenLimiter.GetStatistics())
		}
	})

	// Get statistics for all limiters
	mux.HandleFunc("/api/ratelimit/stats", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		stats := map[string]interface{}{
			"default": globalTokenLimiter.GetStatistics(),
			"all":     globalMultiLimiter.GetStatistics(),
		}

		sendJSONResponse(w, stats)
	})

	// Reset a specific rate limiter
	mux.HandleFunc("/api/ratelimit/reset/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		key := r.URL.Path[len("/api/ratelimit/reset/"):]
		if key == "" {
			sendJSONError(w, "Rate limiter key required", http.StatusBadRequest)
			return
		}

		// Remove and recreate the limiter
		globalMultiLimiter.Remove(key)
		newLimiter := globalMultiLimiter.GetOrCreate(key, 20.0, 20)

		sendJSONResponse(w, map[string]interface{}{
			"status": "reset",
			"stats":  newLimiter.GetStatistics(),
		})
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

// StartRateLimiterServer starts the rate limiting HTTP server
func StartRateLimiterServer(port int) error {
	mux := http.NewServeMux()
	RegisterRateLimiterHandlers(mux)

	addr := ":" + strconv.Itoa(port)
	log.Printf("Starting rate limiting server on %s", addr)
	return http.ListenAndServe(addr, mux)
}
