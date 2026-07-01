package metrics

import (
	"sort"
	"sync"
	"time"
)

// MetricsAggregator provides real-time metrics aggregation with sliding windows
type MetricsAggregator struct {
	windows map[string]*TimeWindow
	mu      sync.RWMutex
}

// TimeWindow represents a sliding time window for metrics
type TimeWindow struct {
	metricName string
	points     []DataPoint
	maxSize    int
	duration   time.Duration
	mu         sync.RWMutex
}

// DataPoint represents a single metric data point
type DataPoint struct {
	Value     float64
	Timestamp time.Time
}

// WindowStats represents statistics for a time window
type WindowStats struct {
	MetricName string
	Count      int
	Sum        float64
	Avg        float64
	Min        float64
	Max        float64
	StdDev     float64
	P50        float64 // Median
	P95        float64 // 95th percentile
	P99        float64 // 99th percentile
	StartTime  time.Time
	EndTime    time.Time
}

// NewMetricsAggregator creates a new metrics aggregator
func NewMetricsAggregator() *MetricsAggregator {
	return &MetricsAggregator{
		windows: make(map[string]*TimeWindow),
	}
}

// RegisterWindow registers a new time window for a metric
func (ma *MetricsAggregator) RegisterWindow(metricName string, maxSize int, duration time.Duration) {
	ma.mu.Lock()
	defer ma.mu.Unlock()

	ma.windows[metricName] = &TimeWindow{
		metricName: metricName,
		points:     make([]DataPoint, 0, maxSize),
		maxSize:    maxSize,
		duration:   duration,
	}
}

// StreamMetric adds a metric value to the appropriate window
func (ma *MetricsAggregator) StreamMetric(metricName string, value float64, timestamp time.Time) {
	ma.mu.RLock()
	window, ok := ma.windows[metricName]
	ma.mu.RUnlock()

	if !ok {
		// Auto-register with defaults
		ma.RegisterWindow(metricName, 1000, time.Hour)
		window = ma.windows[metricName]
	}

	window.AddPoint(value, timestamp)
}

// AddPoint adds a data point to the time window
func (tw *TimeWindow) AddPoint(value float64, timestamp time.Time) {
	tw.mu.Lock()
	defer tw.mu.Unlock()

	// Add new point
	tw.points = append(tw.points, DataPoint{
		Value:     value,
		Timestamp: timestamp,
	})

	// Remove old points outside the window
	cutoff := time.Now().Add(-tw.duration)
	for i, point := range tw.points {
		if point.Timestamp.After(cutoff) {
			tw.points = tw.points[i:]
			break
		}
	}

	// Enforce max size
	if len(tw.points) > tw.maxSize {
		tw.points = tw.points[len(tw.points)-tw.maxSize:]
	}
}

// GetWindowStats returns statistics for a metric's time window
func (ma *MetricsAggregator) GetWindowStats(metricName string) (*WindowStats, error) {
	ma.mu.RLock()
	window, ok := ma.windows[metricName]
	ma.mu.RUnlock()

	if !ok {
		return nil, nil
	}

	return window.GetStats(), nil
}

// GetStats returns statistics for the time window
func (tw *TimeWindow) GetStats() *WindowStats {
	tw.mu.RLock()
	defer tw.mu.RUnlock()

	if len(tw.points) == 0 {
		return &WindowStats{
			MetricName: tw.metricName,
			Count:      0,
		}
	}

	values := make([]float64, len(tw.points))
	for i, point := range tw.points {
		values[i] = point.Value
	}

	stats := &WindowStats{
		MetricName: tw.metricName,
		Count:      len(values),
		Sum:        sum(values),
		Min:        min(values),
		Max:        max(values),
		StartTime:  tw.points[0].Timestamp,
		EndTime:    tw.points[len(tw.points)-1].Timestamp,
	}

	if stats.Count > 0 {
		stats.Avg = stats.Sum / float64(stats.Count)
		stats.StdDev = stdDev(values)
		stats.P50 = percentile(values, 50)
		stats.P95 = percentile(values, 95)
		stats.P99 = percentile(values, 99)
	}

	return stats
}

// GetRecentPoints returns the most recent N points for a metric
func (ma *MetricsAggregator) GetRecentPoints(metricName string, count int) []DataPoint {
	ma.mu.RLock()
	window, ok := ma.windows[metricName]
	ma.mu.RUnlock()

	if !ok {
		return nil
	}

	return window.GetRecentPoints(count)
}

// GetRecentPoints returns the most recent N points
func (tw *TimeWindow) GetRecentPoints(count int) []DataPoint {
	tw.mu.RLock()
	defer tw.mu.RUnlock()

	if len(tw.points) == 0 {
		return nil
	}

	start := len(tw.points) - count
	if start < 0 {
		start = 0
	}

	result := make([]DataPoint, len(tw.points)-start)
	copy(result, tw.points[start:])
	return result
}

// ClearWindow clears all points for a metric window
func (ma *MetricsAggregator) ClearWindow(metricName string) {
	ma.mu.RLock()
	window, ok := ma.windows[metricName]
	ma.mu.RUnlock()

	if ok {
		window.Clear()
	}
}

// Clear clears all points in the window
func (tw *TimeWindow) Clear() {
	tw.mu.Lock()
	defer tw.mu.Unlock()
	tw.points = make([]DataPoint, 0, tw.maxSize)
}

// GetAllMetricNames returns all registered metric names
func (ma *MetricsAggregator) GetAllMetricNames() []string {
	ma.mu.RLock()
	defer ma.mu.RUnlock()

	names := make([]string, 0, len(ma.windows))
	for name := range ma.windows {
		names = append(names, name)
	}
	return names
}

// GetWindowCount returns the number of registered windows
func (ma *MetricsAggregator) GetWindowCount() int {
	ma.mu.RLock()
	defer ma.mu.RUnlock()
	return len(ma.windows)
}

// MultiMetricAggregator aggregates multiple metrics together
type MultiMetricAggregator struct {
	aggregator *MetricsAggregator
}

// NewMultiMetricAggregator creates a new multi-metric aggregator
func NewMultiMetricAggregator() *MultiMetricAggregator {
	return &MultiMetricAggregator{
		aggregator: NewMetricsAggregator(),
	}
}

// StreamMultipleMetrics streams multiple metrics at once
func (mma *MultiMetricAggregator) StreamMultipleMetrics(metrics map[string]float64, timestamp time.Time) {
	for name, value := range metrics {
		mma.aggregator.StreamMetric(name, value, timestamp)
	}
}

// GetAggregateStats returns aggregate statistics across multiple metrics
func (mma *MultiMetricAggregator) GetAggregateStats(metricNames []string) map[string]*WindowStats {
	results := make(map[string]*WindowStats)
	for _, name := range metricNames {
		stats, _ := mma.aggregator.GetWindowStats(name)
		results[name] = stats
	}
	return results
}

// RateCalculator calculates rates (per second) from metrics
type RateCalculator struct {
	previousValues map[string]DataPoint
	mu            sync.RWMutex
}

// NewRateCalculator creates a new rate calculator
func NewRateCalculator() *RateCalculator {
	return &RateCalculator{
		previousValues: make(map[string]DataPoint),
	}
}

// CalculateRate calculates the rate of change for a metric
func (rc *RateCalculator) CalculateRate(metricName string, value float64, timestamp time.Time) float64 {
	rc.mu.Lock()
	defer rc.mu.Unlock()

	prev, exists := rc.previousValues[metricName]
	if !exists {
		rc.previousValues[metricName] = DataPoint{Value: value, Timestamp: timestamp}
		return 0
	}

	timeDiff := timestamp.Sub(prev.Timestamp).Seconds()
	if timeDiff <= 0 {
		return 0
	}

	rate := (value - prev.Value) / timeDiff
	rc.previousValues[metricName] = DataPoint{Value: value, Timestamp: timestamp}

	return rate
}

// Utility functions
func sum(values []float64) float64 {
	total := 0.0
	for _, v := range values {
		total += v
	}
	return total
}

func min(values []float64) float64 {
	if len(values) == 0 {
		return 0
	}
	minVal := values[0]
	for _, v := range values {
		if v < minVal {
			minVal = v
		}
	}
	return minVal
}

func max(values []float64) float64 {
	if len(values) == 0 {
		return 0
	}
	maxVal := values[0]
	for _, v := range values {
		if v > maxVal {
			maxVal = v
		}
	}
	return maxVal
}

func stdDev(values []float64) float64 {
	if len(values) < 2 {
		return 0
	}
	
	mean := sum(values) / float64(len(values))
	sumSqDiff := 0.0
	for _, v := range values {
		diff := v - mean
		sumSqDiff += diff * diff
	}
	
	variance := sumSqDiff / float64(len(values)-1)
	return sqrt(variance)
}

func percentile(values []float64, p float64) float64 {
	if len(values) == 0 {
		return 0
	}

	sorted := make([]float64, len(values))
	copy(sorted, values)
	sort.Float64s(sorted)

	index := p * float64(len(sorted)-1) / 100
	lower := int(index)
	upper := lower + 1
	if upper >= len(sorted) {
		return sorted[len(sorted)-1]
	}

	weight := index - float64(lower)
	return sorted[lower]*(1-weight) + sorted[upper]*weight
}

func sqrt(x float64) float64 {
	// Simple Newton-Raphson square root
	if x == 0 {
		return 0
	}
	z := 1.0
	for i := 0; i < 20; i++ {
		z = (z + x/z) / 2
	}
	return z
}
