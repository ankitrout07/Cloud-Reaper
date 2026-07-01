package scoring

import (
	"fmt"
	"math"
	"sync"
)

// ResourceScorer performs vectorized resource scoring operations
type ResourceScorer struct {
	cpuMatrix     [][]float64
	memoryMatrix  [][]float64
	iopsMatrix    [][]float64
	networkMatrix [][]float64
	mu            sync.RWMutex
	envType       string // "production" or "dev-test"
}

// ScoreResult represents the scoring result for a resource
type ScoreResult struct {
	ResourceIndex int
	Action        string
	Impact        string
	Reason        string
	Metrics       ResourceMetrics
}

// ResourceMetrics holds resource performance metrics
type ResourceMetrics struct {
	AvgCPU    float64
	MaxCPU    float64
	AvgMemory float64
	MaxMemory float64
	AvgIOPS   float64
	MaxIOPS   float64
	AvgNet    float64
	MaxNet    float64
}

// ScoringConfig holds configuration for resource scoring
type ScoringConfig struct {
	EnvType              string
	CPUShutdownThreshold float64
	CPUHighThreshold     float64
	CPUMediumThreshold   float64
	MemoryHighThreshold  float64
	IOPSLowThreshold     float64
}

// DefaultScoringConfig returns sensible defaults
func DefaultScoringConfig(envType string) ScoringConfig {
	if envType == "production" {
		return ScoringConfig{
			EnvType:              "production",
			CPUShutdownThreshold: 5.0,
			CPUHighThreshold:     80.0,
			CPUMediumThreshold:   60.0,
			MemoryHighThreshold:  80.0,
			IOPSLowThreshold:     10.0,
		}
	}
	return ScoringConfig{
		EnvType:              "dev-test",
		CPUShutdownThreshold: 15.0,
		CPUHighThreshold:     70.0,
		CPUMediumThreshold:   50.0,
		MemoryHighThreshold:  70.0,
		IOPSLowThreshold:     10.0,
	}
}

// NewResourceScorer creates a new resource scorer
func NewResourceScorer(cpuMatrix, memoryMatrix [][]float64, envType string) *ResourceScorer {
	return &ResourceScorer{
		cpuMatrix:     cpuMatrix,
		memoryMatrix:  memoryMatrix,
		iopsMatrix:    nil,
		networkMatrix: nil,
		envType:       envType,
	}
}

// SetIOPSMatrix sets the IOPS matrix
func (rs *ResourceScorer) SetIOPSMatrix(matrix [][]float64) {
	rs.mu.Lock()
	defer rs.mu.Unlock()
	rs.iopsMatrix = matrix
}

// SetNetworkMatrix sets the network matrix
func (rs *ResourceScorer) SetNetworkMatrix(matrix [][]float64) {
	rs.mu.Lock()
	defer rs.mu.Unlock()
	rs.networkMatrix = matrix
}

// BatchScoreResources performs batch scoring of all resources
func (rs *ResourceScorer) BatchScoreResources(config ScoringConfig) []ScoreResult {
	rs.mu.RLock()
	defer rs.mu.RUnlock()

	if len(rs.cpuMatrix) == 0 {
		return nil
	}

	numResources := len(rs.cpuMatrix)
	results := make([]ScoreResult, numResources)

	// Vectorized calculations using goroutines
	var wg sync.WaitGroup
	for i := 0; i < numResources; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			results[idx] = rs.scoreResource(idx, config)
		}(i)
	}

	wg.Wait()
	return results
}

// scoreResource scores a single resource
func (rs *ResourceScorer) scoreResource(index int, config ScoringConfig) ScoreResult {
	if index >= len(rs.cpuMatrix) {
		return ScoreResult{
			ResourceIndex: index,
			Action:        "ERROR",
			Impact:        "LOW",
			Reason:        "Invalid resource index",
		}
	}

	cpuData := rs.cpuMatrix[index]
	memData := rs.memoryMatrix[index]
	iopsData := rs.getIOPSData(index)
	netData := rs.getNetworkData(index)

	// Calculate metrics
	metrics := rs.calculateMetrics(cpuData, memData, iopsData, netData)

	// Determine action based on metrics
	action, impact, reason := rs.determineAction(metrics, config)

	return ScoreResult{
		ResourceIndex: index,
		Action:        action,
		Impact:        impact,
		Reason:        reason,
		Metrics:       metrics,
	}
}

// calculateMetrics calculates performance metrics for a resource
func (rs *ResourceScorer) calculateMetrics(cpuData, memData, iopsData, netData []float64) ResourceMetrics {
	metrics := ResourceMetrics{
		AvgCPU:    mean(cpuData),
		MaxCPU:    max(cpuData),
		AvgMemory: mean(memData),
		MaxMemory: max(memData),
		AvgIOPS:   mean(iopsData),
		MaxIOPS:   max(iopsData),
		AvgNet:    mean(netData),
		MaxNet:    max(netData),
	}
	return metrics
}

// determineAction determines the recommended action based on metrics
func (rs *ResourceScorer) determineAction(metrics ResourceMetrics, config ScoringConfig) (string, string, string) {
	// Rule 1: Zero or near-zero utilization - Shutdown
	if metrics.MaxCPU < config.CPUShutdownThreshold {
		return "SHUTDOWN", "HIGH", "Idle resource threshold breach"
	}

	// Rule 2: Low-average / high-peak - Burstable B-Series
	if metrics.AvgCPU < 20.0 && metrics.MaxCPU > 70.0 {
		return "RIGHTSIZE_BURSTABLE", "MEDIUM", "Fits burstable B-Series profile"
	}

	// Rule 3: High utilization - Stay
	if metrics.AvgCPU > config.CPUHighThreshold || metrics.AvgMemory > config.MemoryHighThreshold {
		return "STAY", "LOW", "High utilization - maintain current size"
	}

	// Rule 4: Medium utilization - Consider downscale
	if metrics.AvgCPU < config.CPUMediumThreshold && metrics.MaxCPU < config.CPUHighThreshold {
		return "DOWNSCALE", "MEDIUM", "Low utilization - consider smaller instance"
	}

	// Default: Stay
	return "STAY", "LOW", "Stable operation baseline"
}

// getIOPSData gets IOPS data for a resource
func (rs *ResourceScorer) getIOPSData(index int) []float64 {
	if rs.iopsMatrix != nil && index < len(rs.iopsMatrix) {
		return rs.iopsMatrix[index]
	}
	return []float64{}
}

// getNetworkData gets network data for a resource
func (rs *ResourceScorer) getNetworkData(index int) []float64 {
	if rs.networkMatrix != nil && index < len(rs.networkMatrix) {
		return rs.networkMatrix[index]
	}
	return []float64{}
}

// ZombieScorer performs zombie resource detection
type ZombieScorer struct {
	threshold int
}

// ZombieScore represents zombie resource scoring result
type ZombieScore struct {
	IsZombie bool
	Score    int
	Reasons  []string
}

// NewZombieScorer creates a new zombie scorer
func NewZombieScorer(threshold int) *ZombieScorer {
	return &ZombieScorer{
		threshold: threshold,
	}
}

// ScoreResource scores a single resource for zombie detection
func (zs *ZombieScorer) ScoreResource(resourceData map[string]interface{}) ZombieScore {
	score := 0
	reasons := []string{}

	// Rule 1: Attachment status
	if isUnattached, ok := resourceData["is_unattached"].(bool); ok && isUnattached {
		score += 50
		reasons = append(reasons, "Resource is unattached/orphaned (+50)")
	}

	// Rule 2: IOPS history
	if iopsHistory, ok := resourceData["iops_history"].([]float64); ok {
		if len(iopsHistory) >= 7 {
			allLow := true
			for _, iops := range iopsHistory[len(iopsHistory)-7:] {
				if iops >= 10.0 {
					allLow = false
					break
				}
			}
			if allLow {
				score += 45
				reasons = append(reasons, "Near-zero IOPS for 7 consecutive days (+45)")
			}
		}
	} else if diskIOPS, ok := resourceData["disk_iops"].(float64); ok && diskIOPS < 5.0 {
		score += 20
		reasons = append(reasons, "Current IOPS is negligible (+20)")
	}

	isZombie := score >= zs.threshold

	return ZombieScore{
		IsZombie: isZombie,
		Score:    score,
		Reasons:  reasons,
	}
}

// BatchScoreZombieResources performs batch zombie resource scoring
func (zs *ZombieScorer) BatchScoreZombieResources(resources []map[string]interface{}) []ZombieScore {
	results := make([]ZombieScore, len(resources))

	var wg sync.WaitGroup
	for i, resource := range resources {
		wg.Add(1)
		go func(idx int, res map[string]interface{}) {
			defer wg.Done()
			results[idx] = zs.ScoreResource(res)
		}(i, resource)
	}

	wg.Wait()
	return results
}

// Vectorized utility functions
func mean(data []float64) float64 {
	if len(data) == 0 {
		return 0
	}
	sum := 0.0
	for _, v := range data {
		sum += v
	}
	return sum / float64(len(data))
}

func max(data []float64) float64 {
	if len(data) == 0 {
		return 0
	}
	maxVal := data[0]
	for _, v := range data {
		if v > maxVal {
			maxVal = v
		}
	}
	return maxVal
}

func min(data []float64) float64 {
	if len(data) == 0 {
		return 0
	}
	minVal := data[0]
	for _, v := range data {
		if v < minVal {
			minVal = v
		}
	}
	return minVal
}

// BatchCalculateMeans calculates means for multiple vectors in parallel
func BatchCalculateMeans(matrix [][]float64) []float64 {
	results := make([]float64, len(matrix))

	var wg sync.WaitGroup
	for i, row := range matrix {
		wg.Add(1)
		go func(idx int, data []float64) {
			defer wg.Done()
			results[idx] = mean(data)
		}(i, row)
	}

	wg.Wait()
	return results
}

// BatchCalculateMax calculates max values for multiple vectors in parallel
func BatchCalculateMax(matrix [][]float64) []float64 {
	results := make([]float64, len(matrix))

	var wg sync.WaitGroup
	for i, row := range matrix {
		wg.Add(1)
		go func(idx int, data []float64) {
			defer wg.Done()
			results[idx] = max(data)
		}(i, row)
	}

	wg.Wait()
	return results
}

// MatrixMultiply performs matrix multiplication (optimized for scoring operations)
func MatrixMultiply(a, b [][]float64) ([][]float64, error) {
	if len(a) == 0 || len(b) == 0 {
		return nil, fmt.Errorf("empty matrix")
	}

	rowsA := len(a)
	colsA := len(a[0])
	rowsB := len(b)
	colsB := len(b[0])

	if colsA != rowsB {
		return nil, fmt.Errorf("matrix dimensions incompatible for multiplication")
	}

	result := make([][]float64, rowsA)
	for i := 0; i < rowsA; i++ {
		result[i] = make([]float64, colsB)
	}

	// Parallel computation
	var wg sync.WaitGroup
	for i := 0; i < rowsA; i++ {
		wg.Add(1)
		go func(row int) {
			defer wg.Done()
			for j := 0; j < colsB; j++ {
				sum := 0.0
				for k := 0; k < colsA; k++ {
					sum += a[row][k] * b[k][j]
				}
				result[row][j] = sum
			}
		}(i)
	}

	wg.Wait()
	return result, nil
}
