# Enhanced Anomaly Explainer - Implementation Guide

## Overview

The Anomaly Explainer module has been significantly enhanced with advanced ML capabilities to improve root cause analysis, explanation quality, and operational efficiency. This document describes the new features and how to use them.

## New Features

### 1. Redis Caching for Similar Anomaly Patterns

**Purpose**: Reduce API costs and improve response times by caching explanations for similar anomalies.

**Implementation**:
- Automatic cache key generation based on anomaly features
- Configurable TTL (default: 24 hours)
- Graceful fallback when Redis is unavailable
- Cache hit tracking for analytics

**Usage**:
```python
from src.reaper.engine.ml.anomaly_explainer import AnomalyRootCauseAnalyzer

# Initialize (Redis connection optional)
analyzer = AnomalyRootCauseAnalyzer()

# Analyze anomaly (will check cache first)
result = analyzer.analyze_anomaly("anomaly-123", anomaly_data)

# Check if result came from cache
if result.get("cache_hit"):
    print("Retrieved from cache")
```

**Configuration**:
```bash
# In .env file
REDIS_URL=redis://localhost:6379/0
ANOMALY_CACHE_TTL=86400  # 24 hours
```

### 2. Rule-Based Fallback System

**Purpose**: Provide high-quality explanations even when AI services are unavailable or return low-confidence results.

**Implementation**:
- Domain-specific anomaly patterns (VM, storage, network, database, seasonal)
- Pattern matching against resource types and characteristics
- Confidence scoring based on match strength
- Automatic fallback when AI confidence is low

**Domain Patterns**:
- `cost_spike_vm`: VM-related cost anomalies
- `cost_spike_storage`: Storage-related cost anomalies
- `cost_spike_network`: Network/bandwidth-related anomalies
- `cost_spike_database`: Database-related anomalies
- `seasonal_pattern`: Seasonal/business cycle patterns

**Usage**:
```python
# Automatic fallback - no code changes needed
result = analyzer.analyze_anomaly("anomaly-123", anomaly_data)

# Check which method was used
method = result.get("analysis_method")  # "ai", "rule_based", or "correlation_fallback"
if result.get("pattern_matched"):
    print("Domain pattern matched")
```

### 3. SHAP Feature Importance Attribution

**Purpose**: Explain which features contributed most to the anomaly detection, improving transparency and trust.

**Implementation**:
- SHAP (SHapley Additive exPlanations) values calculation
- Feature extraction from anomaly data and context
- Synthetic data generation for model training
- Top feature identification and interpretation

**Usage**:
```python
result = analyzer.analyze_anomaly("anomaly-123", anomaly_data)

# Access feature importance
feature_importance = result.get("feature_importance")
if feature_importance and "feature_importance" in feature_importance:
    top_features = feature_importance["top_features"]
    print(f"Top contributing features: {top_features}")

    # Get detailed importance values
    for feature, importance in feature_importance["feature_importance"].items():
        print(f"{feature}: {importance['importance']:.3f}")
```

**Configuration**:
```bash
ENABLE_SHAP_ANALYSIS=true
SHAP_SYNTHETIC_SAMPLES=50
SHAP_TOP_FEATURES=5
```

### 4. Anomaly Clustering for Batch Analysis

**Purpose**: Group similar anomalies together to identify patterns and enable batch remediation.

**Implementation**:
- K-means clustering with PCA dimensionality reduction
- Feature extraction from anomaly results
- Cluster insight generation (common patterns, root causes)
- Adaptive cluster count based on data size

**Usage**:
```python
# Batch analyze multiple anomalies
anomalies = [
    {"id": "anomaly-1", "cost_change": 100.0, ...},
    {"id": "anomaly-2", "cost_change": 150.0, ...},
    {"id": "anomaly-3", "cost_change": 200.0, ...}
]

results = analyzer.batch_analyze_anomalies(anomalies)

# Access cluster information
for result in results:
    cluster_id = result.get("cluster_id")
    cluster_insights = result.get("cluster_insights")
    print(f"Anomaly {result['anomaly_id']} in cluster {cluster_id}")
    if cluster_insights:
        print(f"Cluster size: {cluster_insights['size']}")
        print(f"Common patterns: {cluster_insights['common_patterns']}")
```

**Configuration**:
```bash
ENABLE_ANOMALY_CLUSTERING=true
CLUSTERING_MIN_SAMPLES=5
CLUSTERING_EPS=0.5
CLUSTERING_N_CLUSTERS=5
```

### 5. Time-Series Decomposition

**Purpose**: Separate cost patterns into trend, seasonal, and residual components to better understand anomaly root causes.

**Implementation**:
- Seasonal decomposition using statsmodels
- Trend strength calculation
- Seasonal pattern detection
- Component interpretation and insights

**Usage**:
```python
result = analyzer.analyze_anomaly("anomaly-123", anomaly_data)

# Access decomposition results
decomposition = result.get("time_series_decomposition")
if decomposition and "error" not in decomposition:
    dominant = decomposition["dominant_component"]
    print(f"Dominant component: {dominant}")

    # Access individual components
    trend = decomposition["trend"]
    seasonal = decomposition["seasonal"]
    residual = decomposition["residual"]

    print(f"Trend direction: {trend['direction']}")
    print(f"Seasonal strength: {seasonal['strength']}")
    print(f"Residual volatility: {residual['volatility']}")
```

**Configuration**:
```bash
ENABLE_TIME_SERIES_DECOMPOSITION=true
DECOMPOSITION_PERIOD=7  # Weekly seasonality
DECOMPOSITION_MODEL=additive  # or 'multiplicative'
```

### 6. Automated Anomaly Labeling

**Purpose**: Enable continuous learning by collecting user feedback on anomaly classifications.

**Implementation**:
- Label storage with user attribution
- Label history tracking
- Label statistics and trend analysis
- Foundation for future model retraining

**Usage**:
```python
# Label an anomaly
result = analyzer.label_anomaly(
    anomaly_id="anomaly-123",
    label="true_positive",  # or "false_positive", "actionable", etc.
    user_id="user-1"
)

# Get labeling statistics
stats = analyzer.get_label_statistics()
print(f"Total labels: {stats['total_labels']}")
print(f"Label distribution: {stats['label_distribution']}")
print(f"Labeling trend: {stats['labeling_trend']}")
```

**Supported Labels**:
- `true_positive`: Valid anomaly requiring action
- `false_positive`: Anomaly that doesn't require action
- `actionable`: Anomaly with clear remediation path
- `informational`: Anomaly for awareness only
- `investigate`: Anomaly requiring further investigation

## Installation

### Requirements

Add the following dependencies to your `requirements.txt`:

```txt
scipy>=1.11.0
redis>=5.0.0
shap>=0.42.0
joblib>=1.3.0
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### Redis Setup (Optional but Recommended)

For production use, set up Redis for caching:

```bash
# Using Docker
docker run -d -p 6379:6379 redis:7-alpine

# Or install locally
# Ubuntu/Debian
sudo apt-get install redis-server

# macOS
brew install redis
brew services start redis
```

## Configuration

Create or update your `.env` file with the following variables:

```bash
# Required
GEMINI_API_KEY=your_gemini_api_key_here

# Optional - Redis Caching
REDIS_URL=redis://localhost:6379/0
ANOMALY_CACHE_TTL=86400

# Optional - Feature Flags
ENABLE_SHAP_ANALYSIS=true
ENABLE_TIME_SERIES_DECOMPOSITION=true
ENABLE_ANOMALY_CLUSTERING=true
ENABLE_RULE_BASED_FALLBACK=true

# Optional - Algorithm Parameters
CLUSTERING_MIN_SAMPLES=5
CLUSTERING_EPS=0.5
CLUSTERING_N_CLUSTERS=5
DECOMPOSITION_PERIOD=7
DECOMPOSITION_MODEL=additive
SHAP_SYNTHETIC_SAMPLES=50
SHAP_TOP_FEATURES=5
```

## API Integration

### REST API Endpoints

The enhanced anomaly explainer can be integrated into your existing API:

```python
from fastapi import FastAPI, HTTPException
from src.reaper.engine.ml.anomaly_explainer import AnomalyRootCauseAnalyzer

app = FastAPI()
analyzer = AnomalyRootCauseAnalyzer()

@app.post("/api/anomaly/analyze")
async def analyze_anomaly(anomaly_data: dict):
    """Analyze a single anomaly with enhanced features."""
    try:
        anomaly_id = anomaly_data.get("id", "unknown")
        result = analyzer.analyze_anomaly(anomaly_id, anomaly_data)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/anomaly/batch-analyze")
async def batch_analyze_anomalies(anomalies: list[dict]):
    """Analyze multiple anomalies with clustering."""
    try:
        results = analyzer.batch_analyze_anomalies(anomalies)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/anomaly/label")
async def label_anomaly(anomaly_id: str, label: str, user_id: str = None):
    """Label an anomaly for continuous learning."""
    try:
        result = analyzer.label_anomaly(anomaly_id, label, user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/anomaly/label-statistics")
async def get_label_statistics():
    """Get anomaly labeling statistics."""
    try:
        stats = analyzer.get_label_statistics()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

## Performance Considerations

### Caching Impact

- **Cache Hit Rate**: Monitor cache hit rate to optimize TTL settings
- **Memory Usage**: Redis memory usage depends on anomaly volume and cache size
- **Latency**: Cache hits typically reduce response time by 80-90%

### SHAP Analysis Impact

- **Computation Time**: SHAP analysis adds 100-500ms per analysis
- **Memory Usage**: Synthetic data generation requires additional memory
- **Recommendation**: Disable for real-time requirements, enable for batch analysis

### Clustering Impact

- **Scalability**: Clustering complexity is O(n²) for small datasets, O(n log n) for large datasets
- **Batch Size**: Optimal batch size is 50-100 anomalies
- **Memory**: PCA and clustering require O(n) memory where n is the number of features

### Time-Series Decomposition Impact

- **Minimum Data**: Requires at least 14 days of hourly/daily data
- **Computation Time**: Adds 50-200ms per analysis
- **Accuracy**: Improves with longer time series (30+ days recommended)

## Monitoring and Analytics

### Key Metrics to Track

1. **Cache Performance**
   - Cache hit rate
   - Average cache latency
   - Cache size growth

2. **Analysis Method Distribution**
   - AI vs. rule-based vs. correlation fallback
   - Pattern match rate
   - Average confidence by method

3. **Feature Importance**
   - Top contributing features
   - Feature importance distribution
   - Feature importance trends over time

4. **Clustering Quality**
   - Average cluster size
   - Cluster distribution
   - Common patterns by cluster

5. **Labeling Analytics**
   - Label distribution
   - Labeling trend over time
   - User participation rate

### Logging

The enhanced system includes detailed logging:

```python
import logging

# Set log level
logging.getLogger("src.reaper.engine.ml.anomaly_explainer").setLevel(logging.DEBUG)

# Key log messages:
# - "Redis cache initialized successfully"
# - "Retrieved cached explanation for anomaly {anomaly_id}"
# - "AI confidence low, using rule-based fallback"
# - "Anomaly {anomaly_id} labeled as '{label}' by user {user_id}"
```

## Troubleshooting

### Redis Connection Issues

**Problem**: Redis initialization fails, caching disabled

**Solution**:
```bash
# Check Redis is running
redis-cli ping

# Check connection string
echo $REDIS_URL

# Test connection
redis-cli -u $REDIS_URL ping
```

### SHAP Analysis Errors

**Problem**: SHAP analysis fails with "Insufficient features" error

**Solution**:
- Ensure anomaly data includes cost history
- Verify resource information is available
- Check that numerical features can be extracted

### Time-Series Decomposition Errors

**Problem**: Decomposition fails with "Insufficient data" error

**Solution**:
- Ensure at least 14 data points are available
- Check that cost history dates are properly formatted
- Verify time series has sufficient variance

### Clustering Issues

**Problem**: All anomalies assigned to cluster -1 (noise)

**Solution**:
- Increase `CLUSTERING_EPS` parameter
- Decrease `CLUSTERING_MIN_SAMPLES`
- Ensure anomalies have sufficient feature diversity

## Future Enhancements

Planned improvements for future versions:

1. **Model Retraining**: Automated model retraining based on labeled data
2. **Advanced Clustering**: Hierarchical clustering and anomaly-specific algorithms
3. **Real-time Decomposition**: Streaming time-series decomposition
4. **Explainable AI**: Integration with LIME and other XAI techniques
5. **Transfer Learning**: Pre-trained models for specific cloud providers
6. **Multi-variate Analysis**: Cross-resource anomaly detection
7. **Causal Inference**: True causal relationship discovery
8. **Alert Integration**: Automatic alert generation based on clustering

## Contributing

When contributing to the enhanced anomaly explainer:

1. Add tests for new features in `tests/unit/test_anomaly_explainer_enhanced.py`
2. Update this documentation with new features
3. Ensure backward compatibility with existing API
4. Add configuration options for new parameters
5. Include performance impact analysis

## License

This enhancement maintains the same license as the parent Cloud-Reaper project.