package ratelimiter

import (
	"context"
	"sync"
	"time"

	"golang.org/x/time/rate"
)

// TokenBucketRateLimiter implements token bucket rate limiting algorithm
type TokenBucketRateLimiter struct {
	limiter  *rate.Limiter
	mu       sync.Mutex
	rate     rate.Limit // requests per second
	burst    int         // maximum burst size
	lastSync time.Time
}

// NewTokenBucketRateLimiter creates a new token bucket rate limiter
func NewTokenBucketRateLimiter(requestsPerSecond float64, burstSize int) *TokenBucketRateLimiter {
	// Calculate rate limit (requests per interval)
	r := rate.Limit(requestsPerSecond)
	
	// Create limiter with rate and burst size
	limiter := rate.NewLimiter(r, burstSize)
	
	return &TokenBucketRateLimiter{
		limiter:  limiter,
		rate:     r,
		burst:    burstSize,
		lastSync: time.Now(),
	}
}

// Allow checks if a request is allowed under the rate limit
func (tb *TokenBucketRateLimiter) Allow() bool {
	tb.mu.Lock()
	defer tb.mu.Unlock()
	
	return tb.limiter.Allow()
}

// Wait blocks until a token is available
func (tb *TokenBucketRateLimiter) Wait(ctx context.Context) error {
	tb.mu.Lock()
	defer tb.mu.Unlock()
	
	return tb.limiter.Wait(ctx)
}

// WaitDuration blocks until a token is available, returning the wait time
func (tb *TokenBucketRateLimiter) WaitDuration() time.Duration {
	tb.mu.Lock()
	defer tb.mu.Unlock()
	
	start := time.Now()
	reservation := tb.limiter.Reserve()
	if !reservation.OK() {
		return 0 // Should not happen with proper configuration
	}
	
	delay := reservation.Delay()
	
	// Actually wait if there's a delay
	if delay > 0 {
		time.Sleep(delay)
	}
	
	return time.Since(start)
}

// Tokens returns the number of available tokens
func (tb *TokenBucketRateLimiter) Tokens() float64 {
	tb.mu.Lock()
	defer tb.mu.Unlock()
	
	// Estimate available tokens based on rate and time since last sync
	elapsed := time.Since(tb.lastSync)
	available := float64(tb.burst) - elapsed.Seconds()*float64(tb.rate)
	
	if available < 0 {
		available = 0
	}
	if available > float64(tb.burst) {
		available = float64(tb.burst)
	}
	
	return available
}

// UpdateRate dynamically updates the rate limit
func (tb *TokenBucketRateLimiter) UpdateRate(requestsPerSecond float64) {
	tb.mu.Lock()
	defer tb.mu.Unlock()
	
	tb.rate = rate.Limit(requestsPerSecond)
	tb.limiter.SetLimit(tb.rate)
	tb.lastSync = time.Now()
}

// UpdateBurst dynamically updates the burst size
func (tb *TokenBucketRateLimiter) UpdateBurst(burstSize int) {
	tb.mu.Lock()
	defer tb.mu.Unlock()
	
	tb.burst = burstSize
	tb.limiter.SetBurst(tb.burst)
	tb.lastSync = time.Now()
}

// GetRate returns the current rate limit
func (tb *TokenBucketRateLimiter) GetRate() float64 {
	tb.mu.Lock()
	defer tb.mu.Unlock()
	
	return float64(tb.rate)
}

// GetBurst returns the current burst size
func (tb *TokenBucketRateLimiter) GetBurst() int {
	tb.mu.Lock()
	defer tb.mu.Unlock()
	
	return tb.burst
}

// GetStatistics returns rate limiter statistics
func (tb *TokenBucketRateLimiter) GetStatistics() map[string]interface{} {
	tb.mu.Lock()
	defer tb.mu.Unlock()
	
	return map[string]interface{}{
		"rate_per_second": float64(tb.rate),
		"burst_size":      tb.burst,
		"available_tokens": tb.Tokens(),
		"last_sync":       tb.lastSync.Format(time.RFC3339),
	}
}

// MultiLimiter manages multiple rate limiters for different contexts
type MultiLimiter struct {
	limiters map[string]*TokenBucketRateLimiter
	mu       sync.RWMutex
}

// NewMultiLimiter creates a new multi-limiter
func NewMultiLimiter() *MultiLimiter {
	return &MultiLimiter{
		limiters: make(map[string]*TokenBucketRateLimiter),
	}
}

// GetOrCreate gets an existing limiter or creates a new one
func (ml *MultiLimiter) GetOrCreate(key string, requestsPerSecond float64, burstSize int) *TokenBucketRateLimiter {
	ml.mu.RLock()
	limiter, exists := ml.limiters[key]
	ml.mu.RUnlock()
	
	if exists {
		return limiter
	}
	
	ml.mu.Lock()
	defer ml.mu.Unlock()
	
	// Double-check after acquiring write lock
	if limiter, exists := ml.limiters[key]; exists {
		return limiter
	}
	
	limiter = NewTokenBucketRateLimiter(requestsPerSecond, burstSize)
	ml.limiters[key] = limiter
	return limiter
}

// Remove removes a rate limiter
func (ml *MultiLimiter) Remove(key string) {
	ml.mu.Lock()
	defer ml.mu.Unlock()
	
	delete(ml.limiters, key)
}

// GetAll returns all rate limiters
func (ml *MultiLimiter) GetAll() map[string]*TokenBucketRateLimiter {
	ml.mu.RLock()
	defer ml.mu.RUnlock()
	
	result := make(map[string]*TokenBucketRateLimiter, len(ml.limiters))
	for k, v := range ml.limiters {
		result[k] = v
	}
	return result
}

// GetStatistics returns statistics for all limiters
func (ml *MultiLimiter) GetStatistics() map[string]interface{} {
	ml.mu.RLock()
	defer ml.mu.RUnlock()
	
	stats := make(map[string]interface{})
	for key, limiter := range ml.limiters {
		stats[key] = limiter.GetStatistics()
	}
	
	return stats
}

// SlidingWindowRateLimiter implements sliding window rate limiting
type SlidingWindowRateLimiter struct {
	window    time.Duration
	maxCount  int
	requests  []time.Time
	mu        sync.Mutex
}

// NewSlidingWindowRateLimiter creates a new sliding window rate limiter
func NewSlidingWindowRateLimiter(window time.Duration, maxCount int) *SlidingWindowRateLimiter {
	return &SlidingWindowRateLimiter{
		window:   window,
		maxCount: maxCount,
		requests: make([]time.Time, 0),
	}
}

// Allow checks if a request is allowed under the sliding window limit
func (sw *SlidingWindowRateLimiter) Allow() bool {
	sw.mu.Lock()
	defer sw.mu.Unlock()
	
	now := time.Now()
	
	// Remove requests outside the window
	cutoff := now.Add(-sw.window)
	valid := 0
	for _, req := range sw.requests {
		if req.After(cutoff) {
			sw.requests[valid] = req
			valid++
		}
	}
	sw.requests = sw.requests[:valid]
	
	// Check if we can add a new request
	if len(sw.requests) >= sw.maxCount {
		return false
	}
	
	sw.requests = append(sw.requests, now)
	return true
}

// GetCount returns the number of requests in the current window
func (sw *SlidingWindowRateLimiter) GetCount() int {
	sw.mu.Lock()
	defer sw.mu.Unlock()
	
	now := time.Now()
	cutoff := now.Add(-sw.window)
	count := 0
	for _, req := range sw.requests {
		if req.After(cutoff) {
			count++
		}
	}
	return count
}

// Reset clears all requests in the window
func (sw *SlidingWindowRateLimiter) Reset() {
	sw.mu.Lock()
	defer sw.mu.Unlock()
	
	sw.requests = make([]time.Time, 0)
}