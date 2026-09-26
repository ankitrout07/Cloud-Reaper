// Package classifier — workload.go
//
// Workload Classifier
// ====================
// Go port of scheduler.py WorkloadClassifier.
// Classifies cloud resources into "production" or "dev-test" buckets by
// inspecting their tags and name patterns.  All classification work is pure
// string matching — zero allocations on the hot path beyond map reads.
//
// Concurrency
// -----------
// ClassifyBatch fans out into a goroutine per resource when the batch size
// exceeds batchParallelThreshold, giving linear scaling on large subscriptions.
// Each goroutine is lightweight (< 4 KB stack) — no OS thread pool needed.
//
// Bridge integration
// -------------------
// The bridge server (bridge/server.go) exposes:
//
//   POST /api/v1/classifier/classify
//   Body: {"resources": [{...}]}
//   Returns: {"classifications": {"<id>": "production"|"dev-test"}, "production_count": N, "dev_test_count": N}
//
// Python side
// ------------
// Replace WorkloadClassifier.batch_classify() in scheduler.py with a call
// to go_classifier_bridge.classify_batch(resources).

package classifier

import (
	"strings"
	"sync"
)

// ─── Constants ────────────────────────────────────────────────────────────────

// productionKeywords matches the same list as Python's WorkloadClassifier.
var productionKeywords = []string{"prod", "production", "live", "main", "master"}

// devTestKeywords matches the same list as Python's WorkloadClassifier.
var devTestKeywords = []string{"dev", "test", "staging", "sandbox", "demo", "poc"}

// tagKeyVariations is the same mapping as Python's tag_key_mapping.
var tagKeyVariations = []string{"env", "environment", "tier", "workload", "app", "application"}

// batchParallelThreshold is the minimum batch size before we fan out to
// goroutines. Below this the goroutine overhead exceeds the classification
// cost.
const batchParallelThreshold = 50

// ─── Types ───────────────────────────────────────────────────────────────────

// EnvironmentType is the classification result for a single resource.
type EnvironmentType string

const (
	EnvProduction EnvironmentType = "production"
	EnvDevTest    EnvironmentType = "dev-test"
)

// Resource is the minimal resource descriptor required for classification.
// It intentionally mirrors the subset of models.Resource used by Python's
// batch_classify().
type Resource struct {
	ID   string            `json:"id"`
	Name string            `json:"name"`
	Tags map[string]string `json:"tags"`
}

// ClassifyRequest is the POST body for /api/v1/classifier/classify.
type ClassifyRequest struct {
	Resources []Resource `json:"resources"`
}

// ClassifyResponse is the JSON response from the classifier endpoint.
type ClassifyResponse struct {
	// Classifications maps resource ID → environment type.
	Classifications map[string]EnvironmentType `json:"classifications"`
	ProductionCount int                        `json:"production_count"`
	DevTestCount    int                        `json:"dev_test_count"`
}

// ─── Classifier ──────────────────────────────────────────────────────────────

// Classifier is stateless and safe for concurrent use.
type Classifier struct{}

// NewClassifier creates a new Classifier.
func NewClassifier() *Classifier { return &Classifier{} }

// Classify classifies a single resource. Defaults to "production" on ambiguity
// (conservative — same as Python).
func (c *Classifier) Classify(r Resource) EnvironmentType {
	// 1. Tag-based check (most reliable signal)
	for tagKey, tagVal := range r.Tags {
		normKey := strings.ToLower(tagKey)
		normVal := strings.ToLower(tagVal)

		// Only check tags whose keys match one of our known environment key variations
		if !isEnvTagKey(normKey) {
			continue
		}

		if containsAny(normVal, productionKeywords) {
			return EnvProduction
		}
		if containsAny(normVal, devTestKeywords) {
			return EnvDevTest
		}
	}

	// 2. Name-based fallback
	normName := strings.ToLower(r.Name)
	if containsAny(normName, productionKeywords) {
		return EnvProduction
	}
	if containsAny(normName, devTestKeywords) {
		return EnvDevTest
	}

	// 3. Default to production (conservative threshold safety)
	return EnvProduction
}

// ClassifyBatch classifies multiple resources. For batches larger than
// batchParallelThreshold it fans out into one goroutine per resource.
func (c *Classifier) ClassifyBatch(resources []Resource) ClassifyResponse {
	n := len(resources)
	result := make(map[string]EnvironmentType, n)

	if n == 0 {
		return ClassifyResponse{Classifications: result}
	}

	if n < batchParallelThreshold {
		// Serial path for small batches (avoids goroutine overhead)
		for _, r := range resources {
			id := resourceID(r)
			result[id] = c.Classify(r)
		}
	} else {
		// Parallel fan-out for large batches
		type kv struct {
			id  string
			env EnvironmentType
		}

		ch := make(chan kv, n)
		var wg sync.WaitGroup

		for _, r := range resources {
			wg.Add(1)
			go func(r Resource) {
				defer wg.Done()
				ch <- kv{id: resourceID(r), env: c.Classify(r)}
			}(r)
		}

		go func() {
			wg.Wait()
			close(ch)
		}()

		for kv := range ch {
			result[kv.id] = kv.env
		}
	}

	// Count categories
	var prod, devTest int
	for _, env := range result {
		if env == EnvProduction {
			prod++
		} else {
			devTest++
		}
	}

	return ClassifyResponse{
		Classifications: result,
		ProductionCount: prod,
		DevTestCount:    devTest,
	}
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

// resourceID returns the canonical ID for a resource, falling back to Name.
func resourceID(r Resource) string {
	if r.ID != "" {
		return r.ID
	}
	return r.Name
}

// isEnvTagKey returns true if the normalised tag key is one of the known
// environment-classification keys.
func isEnvTagKey(key string) bool {
	for _, v := range tagKeyVariations {
		if key == v {
			return true
		}
	}
	return false
}

// containsAny returns true if s contains any of the substrings in keywords.
func containsAny(s string, keywords []string) bool {
	for _, kw := range keywords {
		if strings.Contains(s, kw) {
			return true
		}
	}
	return false
}
