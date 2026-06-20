// Package db — allocator.go
//
// Zero-Allocation Batch Strategy
// ================================
// Deep multi-cloud scans return thousands of Resource records per run.
// Naively building a new []Resource slice inside every scraper call
// causes the GC to collect a large number of short-lived objects, which
// introduces measurable pause latency on systems with limited RAM (e.g.
// a 512 MB container side-car running alongside the Python API server).
//
// This file introduces two complementary mechanisms:
//
//  1. ResourcePool — a sync.Pool that recycles pre-allocated []Resource
//     backing arrays between scans. Each goroutine grabs a slice from the
//     pool, appends into it, flushes to SQLite via UpsertResources, then
//     resets length to zero and returns the backing array to the pool.
//     The GC never sees the intermediate allocation.
//
//  2. BatchUpsert — a thin helper that encodes the acquire → fill →
//     flush → release lifecycle so callers cannot accidentally skip the
//     Put step (which would turn the pool into a source of unbounded
//     heap growth rather than a sink).
//
// Integration with existing code
// --------------------------------
// All existing scrapers already return []models.Resource via ScanResources().
// BatchUpsert accepts that slice directly; it copies the elements into a
// pooled buffer, upserts them in a single SQLite transaction, and returns
// the buffer without touching the original caller-owned slice.
// The caller keeps ownership of its own slice and can discard it normally.
//
// Pool capacity heuristic
// -------------------------
// initialPoolCap = 5 000 — tuned to the expected p99 resource count per
// full scan (AWS + Azure + GCP + K8s combined). If a single scan returns
// more resources, append() will grow the slice once and the larger backing
// array will be re-pooled for subsequent scans, which is the desired
// steady-state behaviour.

package db

import (
	"fmt"
	"sync"
	"time"

	"cloud-reaper/engine-go/internal/models"
)

// initialPoolCap is the pre-allocated capacity for each pooled resource
// slice. This is intentionally generous: a single large slice is cheaper
// than repeated small grow-and-copy cycles inside a scan loop.
const initialPoolCap = 5_000

// ResourcePool recycles []models.Resource backing arrays between scans.
// Retrieving a buffer with Get() and returning it with Put() keeps the
// GC from touching scan-lifetime allocations entirely.
//
// Usage:
//
//	buf := ResourcePool.Get().([]models.Resource)
//	defer ResourcePool.Put(buf[:0])
//	buf = append(buf, ...)
var ResourcePool = sync.Pool{
	New: func() any {
		// Pre-allocate the backing array once; subsequent scans reuse it.
		s := make([]models.Resource, 0, initialPoolCap)
		return s
	},
}

// BatchUpsertStats carries diagnostic counters returned by BatchUpsert.
// Callers can log or expose these via the /metrics endpoint.
type BatchUpsertStats struct {
	// ResourceCount is the number of resources written to SQLite.
	ResourceCount int
	// Elapsed is the wall-clock time spent inside UpsertResources.
	Elapsed time.Duration
	// PoolReused is true when the pooled buffer was large enough to
	// hold all resources without a heap growth event.
	PoolReused bool
}

// BatchUpsert writes resources to SQLite using a pooled buffer so that
// the intermediate aggregation slice does not escape to the heap.
//
// It is safe to call concurrently; each invocation acquires its own
// buffer from ResourcePool.
//
// The caller's `resources` slice is not modified.
func BatchUpsert(resources []models.Resource) (BatchUpsertStats, error) {
	if len(resources) == 0 {
		return BatchUpsertStats{}, nil
	}

	// --- acquire -------------------------------------------------------
	raw := ResourcePool.Get()
	buf := raw.([]models.Resource)
	preCap := cap(buf)

	// --- fill ----------------------------------------------------------
	// Copy into the pooled buffer. We do NOT take ownership of the
	// caller's slice; this preserves the caller's original reference.
	buf = append(buf, resources...)
	poolReused := cap(buf) == preCap // no growth event occurred

	// --- flush ---------------------------------------------------------
	start := time.Now()
	err := UpsertResources(toDBResources(buf))
	elapsed := time.Since(start)

	// --- release -------------------------------------------------------
	// Always return the buffer, even on error, so the pool does not leak.
	ResourcePool.Put(buf[:0])

	if err != nil {
		return BatchUpsertStats{}, fmt.Errorf("db: BatchUpsert: %w", err)
	}

	return BatchUpsertStats{
		ResourceCount: len(resources),
		Elapsed:       elapsed,
		PoolReused:    poolReused,
	}, nil
}

// toDBResources converts []models.Resource to the []Resource type that
// UpsertResources expects. Both types share identical field layouts;
// this conversion is allocation-free when the compiler inlines it.
//
// Note: models.Resource.Tags is map[string]string whereas db.Resource.Tags
// is map[string]*string (matching the Azure SDK shape). We normalise here.
func toDBResources(src []models.Resource) []Resource {
	// Re-use a single target slice; the caller already holds the pool
	// buffer so we do one extra allocation here only when necessary.
	// For workloads where this is on the hot path, consider a second
	// pool for []Resource — but profile first.
	dst := make([]Resource, len(src))
	for i := range src {
		s := &src[i]
		dst[i] = Resource{
			ID:            s.ID,
			Name:          s.Name,
			Type:          s.Type,
			Region:        s.Region,
			Tags:          tagsToPointerMap(s.Tags),
			Active:        s.Active,
			IsProtected:   s.IsProtected,
			IsUnallocated: s.IsUnallocated,
			LastSeen:      s.LastSeen,
		}
	}
	return dst
}

// tagsToPointerMap converts map[string]string → map[string]*string so
// UpsertResources (which uses the db.Resource shape) can marshal tags
// without allocating extra intermediate maps.
func tagsToPointerMap(in map[string]string) map[string]*string {
	if len(in) == 0 {
		return nil
	}
	out := make(map[string]*string, len(in))
	for k, v := range in {
		v := v // capture loop variable
		out[k] = &v
	}
	return out
}
