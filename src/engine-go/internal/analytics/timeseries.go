package analytics

import (
	"fmt"
	"math"
	"sort"
	"sync"
	"time"
)

// TimeSeriesEngine provides fast time-series analytics operations
type TimeSeriesEngine struct {
	data []float64
	mu   sync.RWMutex
}

// DecompositionResult represents seasonal decomposition results
type DecompositionResult struct {
	Trend     []float64
	Seasonal  []float64
	Residual  []float64
	Period    int
	Strength  float64
}

// ForecastResult represents forecasting results
type ForecastResult struct {
	Forecast      []float64
	Confidence    []float64
	Steps         int
	Method        string
	ConfidenceLevel string
}

// NewTimeSeriesEngine creates a new time-series engine
func NewTimeSeriesEngine(data []float64) *TimeSeriesEngine {
	return &TimeSeriesEngine{
		data: data,
	}
}

// SetData updates the time-series data
func (tse *TimeSeriesEngine) SetData(data []float64) {
	tse.mu.Lock()
	defer tse.mu.Unlock()
	tse.data = data
}

// GetData returns the current time-series data
func (tse *TimeSeriesEngine) GetData() []float64 {
	tse.mu.RLock()
	defer tse.mu.RUnlock()
	return append([]float64{}, tse.data...)
}

// Mean calculates the mean of the data
func (tse *TimeSeriesEngine) Mean() float64 {
	tse.mu.RLock()
	defer tse.mu.RUnlock()
	
	if len(tse.data) == 0 {
		return 0
	}
	
	sum := 0.0
	for _, v := range tse.data {
		sum += v
	}
	return sum / float64(len(tse.data))
}

// StdDev calculates the standard deviation
func (tse *TimeSeriesEngine) StdDev() float64 {
	tse.mu.RLock()
	defer tse.mu.RUnlock()
	
	if len(tse.data) < 2 {
		return 0
	}
	
	mean := tse.Mean()
	sumSqDiff := 0.0
	for _, v := range tse.data {
		diff := v - mean
		sumSqDiff += diff * diff
	}
	
	variance := sumSqDiff / float64(len(tse.data)-1)
	return math.Sqrt(variance)
}

// MovingAverage calculates simple moving average
func (tse *TimeSeriesEngine) MovingAverage(window int) []float64 {
	tse.mu.RLock()
	defer tse.mu.RUnlock()
	
	if len(tse.data) < window || window < 1 {
		return nil
	}
	
	result := make([]float64, len(tse.data)-window+1)
	for i := window - 1; i < len(tse.data); i++ {
		sum := 0.0
		for j := i - window + 1; j <= i; j++ {
			sum += tse.data[j]
		}
		result[i-window+1] = sum / float64(window)
	}
	
	return result
}

// ExponentialMovingAverage calculates exponential moving average
func (tse *TimeSeriesEngine) ExponentialMovingAverage(alpha float64) []float64 {
	tse.mu.RLock()
	defer tse.mu.RUnlock()
	
	if len(tse.data) == 0 || alpha <= 0 || alpha > 1 {
		return nil
	}
	
	result := make([]float64, len(tse.data))
	result[0] = tse.data[0]
	
	for i := 1; i < len(tse.data); i++ {
		result[i] = alpha*tse.data[i] + (1-alpha)*result[i-1]
	}
	
	return result
}

// SeasonalDecompose performs additive seasonal decomposition
func (tse *TimeSeriesEngine) SeasonalDecompose(period int) (*DecompositionResult, error) {
	tse.mu.RLock()
	defer tse.mu.RUnlock()
	
	if len(tse.data) < period*2 {
		return nil, fmt.Errorf("insufficient data for seasonal decomposition (need at least %d points)", period*2)
	}
	
	n := len(tse.data)
	
	// Calculate trend using moving average
	trendWindow := period
	if trendWindow%2 == 0 {
		trendWindow++
	}
	
	trend := make([]float64, n)
	for i := 0; i < n; i++ {
		start := max(0, i-trendWindow/2)
		end := min(n, i+trendWindow/2+1)
		
		sum := 0.0
		count := 0
		for j := start; j < end; j++ {
			sum += tse.data[j]
			count++
		}
		trend[i] = sum / float64(count)
	}
	
	// Calculate detrended data
	detrended := make([]float64, n)
	for i := 0; i < n; i++ {
		detrended[i] = tse.data[i] - trend[i]
	}
	
	// Calculate seasonal component by averaging each period position
	seasonal := make([]float64, period)
	counts := make([]int, period)
	
	for i := 0; i < n; i++ {
		pos := i % period
		seasonal[pos] += detrended[i]
		counts[pos]++
	}
	
	// Normalize seasonal component
	for i := 0; i < period; i++ {
		if counts[i] > 0 {
			seasonal[i] /= float64(counts[i])
		}
	}
	
	// Center seasonal component
	seasonalMean := 0.0
	for _, v := range seasonal {
		seasonalMean += v
	}
	seasonalMean /= float64(period)
	
	for i := 0; i < period; i++ {
		seasonal[i] -= seasonalMean
	}
	
	// Extend seasonal component to full length
	fullSeasonal := make([]float64, n)
	for i := 0; i < n; i++ {
		fullSeasonal[i] = seasonal[i%period]
	}
	
	// Calculate residual
	residual := make([]float64, n)
	for i := 0; i < n; i++ {
		residual[i] = tse.data[i] - trend[i] - fullSeasonal[i]
	}
	
	// Calculate seasonality strength
	varSeasonal := 0.0
	varResidual := 0.0
	
	for i := 0; i < n; i++ {
		varSeasonal += fullSeasonal[i] * fullSeasonal[i]
		varResidual += residual[i] * residual[i]
	}
	
	strength := 0.0
	if varSeasonal+varResidual > 0 {
		strength = varSeasonal / (varSeasonal + varResidual)
	}
	
	return &DecompositionResult{
		Trend:    trend,
		Seasonal: fullSeasonal,
		Residual: residual,
		Period:   period,
		Strength: strength,
	}, nil
}

// ARIMAForecast performs ARIMA forecasting (simplified implementation)
func (tse *TimeSeriesEngine) ARIMAForecast(steps int, p int, d int, q int) (*ForecastResult, error) {
	tse.mu.RLock()
	defer tse.mu.RUnlock()
	
	if len(tse.data) < 5 {
		return nil, fmt.Errorf("insufficient data for ARIMA forecasting (need at least 5 points)")
	}
	
	// Simplified ARIMA(1,1,1) implementation
	// For production, use a proper ARIMA library
	
	// Difference the data (d=1)
	diff := make([]float64, len(tse.data)-1)
	for i := 1; i < len(tse.data); i++ {
		diff[i-1] = tse.data[i] - tse.data[i-1]
	}
	
	// Simple AR(1) model on differenced data
	if len(diff) < 2 {
		return nil, fmt.Errorf("insufficient data after differencing")
	}
	
	// Estimate AR coefficient using simple linear regression
	n := len(diff)
	sumX := 0.0
	sumY := 0.0
	sumXY := 0.0
	sumX2 := 0.0
	
	for i := 1; i < n; i++ {
		x := diff[i-1]
		y := diff[i]
		sumX += x
		sumY += y
		sumXY += x * y
		sumX2 += x * x
	}
	
	phi := 0.0
	denominator := n*sumX2 - sumX*sumX
	if denominator != 0 {
		phi = (n*sumXY - sumX*sumY) / denominator
	}
	
	// Forecast
	forecast := make([]float64, steps)
	lastValue := tse.data[len(tse.data)-1]
	lastDiff := diff[len(diff)-1]
	
	for i := 0; i < steps; i++ {
		nextDiff := phi * lastDiff
		nextValue := lastValue + nextDiff
		forecast[i] = nextValue
		lastDiff = nextDiff
		lastValue = nextValue
	}
	
	// Simple confidence intervals (based on residual variance)
	residuals := make([]float64, n-1)
	for i := 1; i < n-1; i++ {
		predicted := phi * diff[i-1]
		residuals[i-1] = diff[i] - predicted
	}
	
	residualVar := 0.0
	for _, r := range residuals {
		residualVar += r * r
	}
	residualVar /= float64(len(residuals))
	
	confidence := make([]float64, steps)
	stdError := math.Sqrt(residualVar)
	for i := 0; i < steps; i++ {
		confidence[i] = 1.96 * stdError * math.Sqrt(float64(i+1))
	}
	
	return &ForecastResult{
		Forecast:        forecast,
		Confidence:      confidence,
		Steps:           steps,
		Method:          "ARIMA",
		ConfidenceLevel: "95%",
	}, nil
}

// LinearTrendForecast performs linear trend forecasting
func (tse *TimeSeriesEngine) LinearTrendForecast(steps int) (*ForecastResult, error) {
	tse.mu.RLock()
	defer tse.mu.RUnlock()
	
	if len(tse.data) < 2 {
		return nil, fmt.Errorf("insufficient data for linear trend forecasting")
	}
	
	n := len(tse.data)
	
	// Calculate linear regression coefficients
	sumX := 0.0
	sumY := 0.0
	sumXY := 0.0
	sumX2 := 0.0
	
	for i := 0; i < n; i++ {
		x := float64(i)
		y := tse.data[i]
		sumX += x
		sumY += y
		sumXY += x * y
		sumX2 += x * x
	}
	
	denominator := n*sumX2 - sumX*sumX
	if denominator == 0 {
		return nil, fmt.Errorf("cannot calculate linear trend")
	}
	
	slope := (n*sumXY - sumX*sumY) / denominator
	intercept := (sumY - slope*sumX) / float64(n)
	
	// Forecast
	forecast := make([]float64, steps)
	for i := 0; i < steps; i++ {
		x := float64(n + i)
		forecast[i] = slope*x + intercept
	}
	
	return &ForecastResult{
		Forecast:        forecast,
		Confidence:      nil,
		Steps:           steps,
		Method:          "Linear Trend",
		ConfidenceLevel: "N/A",
	}, nil
}

// DetectAnomalies detects anomalies using z-score method
func (tse *TimeSeriesEngine) DetectAnomalies(threshold float64, window int) []int {
	tse.mu.RLock()
	defer tse.mu.RUnlock()
	
	if len(tse.data) < window {
		return nil
	}
	
	anomalies := []int{}
	
	for i := window; i < len(tse.data); i++ {
		// Calculate mean and std of window
		sum := 0.0
		for j := i - window; j < i; j++ {
			sum += tse.data[j]
		}
		mean := sum / float64(window)
		
		variance := 0.0
		for j := i - window; j < i; j++ {
			diff := tse.data[j] - mean
			variance += diff * diff
		}
		std := math.Sqrt(variance / float64(window))
		
		if std == 0 {
			continue
		}
		
		// Calculate z-score
		zScore := math.Abs((tse.data[i] - mean) / std)
		
		if zScore > threshold {
			anomalies = append(anomalies, i)
		}
	}
	
	return anomalies
}

// Percentile calculates the percentile value
func (tse *TimeSeriesEngine) Percentile(p float64) float64 {
	tse.mu.RLock()
	defer tse.mu.RUnlock()
	
	if len(tse.data) == 0 {
		return 0
	}
	
	sorted := make([]float64, len(tse.data))
	copy(sorted, tse.data)
	sort.Float64s(sorted)
	
	index := p * float64(len(sorted)-1) / 100
	lower := int(math.Floor(index))
	upper := int(math.Ceil(index))
	
	if lower == upper {
		return sorted[lower]
	}
	
	weight := index - float64(lower)
	return sorted[lower]*(1-weight) + sorted[upper]*weight
}

// helper functions
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
