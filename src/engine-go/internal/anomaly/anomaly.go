package anomaly

import (
	"math"
	"sync"
	"time"
)

// MetricData represents a single metric data point
type MetricData struct {
	Timestamp  time.Time         `json:"timestamp"`
	Value      float64           `json:"value"`
	Labels     map[string]string `json:"labels"`
	MetricName string            `json:"metric_name"`
}

// AnomalyResult represents the result of anomaly detection
type AnomalyResult struct {
	IsAnomaly     bool      `json:"is_anomaly"`
	Confidence    float64   `json:"confidence"`
	AnomalyScore  float64   `json:"anomaly_score"`
	ExpectedValue float64   `json:"expected_value"`
	ActualValue   float64   `json:"actual_value"`
	Deviation     float64   `json:"deviation"`
	Method        string    `json:"method"`
	Timestamp     time.Time `json:"timestamp"`
}

// AnomalyDetector represents the anomaly detection engine
type AnomalyDetector struct {
	// Statistical methods
	statisticalDetector *StatisticalDetector

	// Real-time processing
	bufferSize   int
	metricBuffer map[string][]MetricData
	bufferMu     sync.RWMutex

	// Configuration
	threshold  float64
	windowSize int
}

// StatisticalDetector implements statistical anomaly detection
type StatisticalDetector struct {
	mu sync.RWMutex

	// Rolling statistics
	mean   float64
	stdDev float64
	count  int
	sum    float64
	sumSq  float64

	// Configuration
	zScoreThreshold float64
	iqrMultiplier   float64
	windowSize      int
}

// NewAnomalyDetector creates a new anomaly detection engine
func NewAnomalyDetector() *AnomalyDetector {
	return &AnomalyDetector{
		statisticalDetector: NewStatisticalDetector(),
		bufferSize:          1000,
		metricBuffer:        make(map[string][]MetricData),
		threshold:           0.95,
		windowSize:          100,
	}
}

// NewStatisticalDetector creates a new statistical anomaly detector
func NewStatisticalDetector() *StatisticalDetector {
	return &StatisticalDetector{
		zScoreThreshold: 3.0, // 3 standard deviations
		iqrMultiplier:   1.5, // 1.5 * IQR
		windowSize:      100,
	}
}

// DetectAnomaly performs real-time anomaly detection on a metric
func (ad *AnomalyDetector) DetectAnomaly(metric MetricData) AnomalyResult {
	ad.bufferMu.Lock()
	defer ad.bufferMu.Unlock()

	// Add to buffer
	metricKey := metric.MetricName
	ad.metricBuffer[metricKey] = append(ad.metricBuffer[metricKey], metric)

	// Maintain buffer size
	if len(ad.metricBuffer[metricKey]) > ad.bufferSize {
		ad.metricBuffer[metricKey] = ad.metricBuffer[metricKey][1:]
	}

	// Update statistical model
	ad.statisticalDetector.Update(metric.Value)

	// Detect anomaly using Z-score
	result := ad.statisticalDetector.DetectZScore(metric.Value)
	result.Timestamp = metric.Timestamp
	result.Method = "zscore"

	// If Z-score doesn't detect anomaly, try IQR method
	if !result.IsAnomaly {
		iqrResult := ad.statisticalDetector.DetectIQR(metric.Value)
		if iqrResult.IsAnomaly {
			result = iqrResult
			result.Method = "iqr"
		}
	}

	return result
}

// DetectAnomaliesBatch performs batch anomaly detection on multiple metrics
func (ad *AnomalyDetector) DetectAnomaliesBatch(metrics []MetricData) []AnomalyResult {
	results := make([]AnomalyResult, len(metrics))

	var wg sync.WaitGroup
	var resultsMu sync.Mutex
	
	for i, metric := range metrics {
		wg.Add(1)
		go func(idx int, m MetricData) {
			defer wg.Done()
			anomaly := ad.DetectAnomaly(m)
			
			// Protect results slice write with mutex
			resultsMu.Lock()
			results[idx] = anomaly
			resultsMu.Unlock()
		}(i, metric)
	}

	wg.Wait()
	return results
}

// Update updates the statistical model with new data
func (sd *StatisticalDetector) Update(value float64) {
	sd.mu.Lock()
	defer sd.mu.Unlock()

	sd.count++
	sd.sum += value
	sd.sumSq += value * value

	sd.mean = sd.sum / float64(sd.count)

	// Calculate standard deviation
	variance := (sd.sumSq / float64(sd.count)) - (sd.mean * sd.mean)
	if variance > 0 {
		sd.stdDev = math.Sqrt(variance)
	} else {
		sd.stdDev = 0
	}
}

// DetectZScore detects anomalies using Z-score method
func (sd *StatisticalDetector) DetectZScore(value float64) AnomalyResult {
	sd.mu.RLock()
	defer sd.mu.RUnlock()

	if sd.count < 2 || sd.stdDev == 0 {
		return AnomalyResult{
			IsAnomaly:     false,
			Confidence:    0.0,
			ExpectedValue: sd.mean,
			ActualValue:   value,
			Deviation:     0.0,
		}
	}

	zScore := math.Abs(value-sd.mean) / sd.stdDev
	isAnomaly := zScore > sd.zScoreThreshold

	// Calculate confidence based on how far the Z-score is from the threshold
	confidence := math.Min(1.0, (zScore-sd.zScoreThreshold+1)/2)
	if !isAnomaly {
		confidence = 0.0
	}

	return AnomalyResult{
		IsAnomaly:     isAnomaly,
		Confidence:    confidence,
		AnomalyScore:  zScore,
		ExpectedValue: sd.mean,
		ActualValue:   value,
		Deviation:     math.Abs(value - sd.mean),
	}
}

// DetectIQR detects anomalies using Interquartile Range method
func (sd *StatisticalDetector) DetectIQR(value float64) AnomalyResult {
	sd.mu.RLock()
	defer sd.mu.RUnlock()

	if sd.count < 4 {
		return AnomalyResult{
			IsAnomaly:     false,
			Confidence:    0.0,
			ExpectedValue: sd.mean,
			ActualValue:   value,
			Deviation:     0.0,
		}
	}

	// Calculate IQR bounds (simplified approach using mean and stdDev)
	lowerBound := sd.mean - (sd.iqrMultiplier * sd.stdDev)
	upperBound := sd.mean + (sd.iqrMultiplier * sd.stdDev)

	isAnomaly := value < lowerBound || value > upperBound

	// Calculate confidence based on distance from bounds
	var confidence float64
	if isAnomaly {
		if value < lowerBound {
			confidence = math.Min(1.0, (lowerBound-value)/sd.stdDev)
		} else {
			confidence = math.Min(1.0, (value-upperBound)/sd.stdDev)
		}
	}

	return AnomalyResult{
		IsAnomaly:     isAnomaly,
		Confidence:    confidence,
		ExpectedValue: sd.mean,
		ActualValue:   value,
		Deviation:     math.Abs(value - sd.mean),
	}
}

// GetStatistics returns current statistics
func (sd *StatisticalDetector) GetStatistics() map[string]interface{} {
	sd.mu.RLock()
	defer sd.mu.RUnlock()

	return map[string]interface{}{
		"count":       sd.count,
		"mean":        sd.mean,
		"std_dev":     sd.stdDev,
		"z_threshold": sd.zScoreThreshold,
		"iqr_mult":    sd.iqrMultiplier,
	}
}

// Reset resets the statistical model
func (sd *StatisticalDetector) Reset() {
	sd.mu.Lock()
	defer sd.mu.Unlock()

	sd.mean = 0
	sd.stdDev = 0
	sd.count = 0
	sd.sum = 0
	sd.sumSq = 0
}

// SetThreshold sets the anomaly detection threshold
func (ad *AnomalyDetector) SetThreshold(threshold float64) {
	ad.threshold = threshold
}

// SetWindowSize sets the window size for statistical calculations
func (ad *AnomalyDetector) SetWindowSize(size int) {
	ad.windowSize = size
	ad.statisticalDetector.windowSize = size
}

// GetMetricBuffer returns the current metric buffer for a specific metric
func (ad *AnomalyDetector) GetMetricBuffer(metricName string) []MetricData {
	ad.bufferMu.RLock()
	defer ad.bufferMu.RUnlock()

	if buffer, exists := ad.metricBuffer[metricName]; exists {
		result := make([]MetricData, len(buffer))
		copy(result, buffer)
		return result
	}

	return []MetricData{}
}

// ClearBuffer clears the metric buffer for a specific metric
func (ad *AnomalyDetector) ClearBuffer(metricName string) {
	ad.bufferMu.Lock()
	defer ad.bufferMu.Unlock()

	delete(ad.metricBuffer, metricName)
}

// ClearAllBuffers clears all metric buffers
func (ad *AnomalyDetector) ClearAllBuffers() {
	ad.bufferMu.Lock()
	defer ad.bufferMu.Unlock()

	ad.metricBuffer = make(map[string][]MetricData)
	ad.statisticalDetector.Reset()
}
