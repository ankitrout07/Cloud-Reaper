package ratelimiter

import (
	"context"
	"sync"
	"testing"
	"time"
)

func TestTokenBucketRateLimiter_ConcurrentWait(t *testing.T) {
	// 50 requests per second, burst of 10
	limiter := NewTokenBucketRateLimiter(50.0, 10)

	start := time.Now()
	var wg sync.WaitGroup
	workers := 10

	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
			defer cancel()
			if err := limiter.Wait(ctx); err != nil {
				t.Errorf("limiter.Wait failed: %v", err)
			}
		}()
	}

	wg.Wait()
	elapsed := time.Since(start)

	// With burst 10, all 10 should acquire immediately without serializing
	if elapsed > 1*time.Second {
		t.Fatalf("Concurrent wait took too long: %v (expected < 1s with burst 10)", elapsed)
	}
}

func TestTokenBucketRateLimiter_AdjustForRetryAfter(t *testing.T) {
	limiter := NewTokenBucketRateLimiter(20.0, 10)
	initialRate := limiter.GetRate()
	if initialRate != 20.0 {
		t.Fatalf("expected initial rate 20, got %f", initialRate)
	}

	limiter.AdjustForRetryAfter(5 * time.Second)
	adjustedRate := limiter.GetRate()
	if adjustedRate >= initialRate {
		t.Fatalf("expected rate to decrease after Retry-After, got %f", adjustedRate)
	}
	if adjustedRate != 10.0 {
		t.Fatalf("expected rate to be halved to 10.0, got %f", adjustedRate)
	}
}

func TestTokenBucketRateLimiter_Allow(t *testing.T) {
	limiter := NewTokenBucketRateLimiter(1.0, 2)
	if !limiter.Allow() {
		t.Fatal("expected first Allow() to be true")
	}
	if !limiter.Allow() {
		t.Fatal("expected second Allow() to be true (within burst)")
	}
	if limiter.Allow() {
		t.Fatal("expected third Allow() to be false (burst exhausted)")
	}
}
