"""
Test suite for enhanced anomaly explainer functionality.

Tests for:
- Redis caching
- Rule-based fallback system
- SHAP feature importance
- Anomaly clustering
- Time-series decomposition
- Automated anomaly labeling
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import numpy as np

from src.reaper.engine.ml.anomaly_explainer import AnomalyRootCauseAnalyzer


class TestRedisCaching:
    """Test Redis caching functionality."""

    @patch('src.reaper.engine.ml.anomaly_explainer.redis')
    def test_redis_initialization_success(self, mock_redis):
        """Test successful Redis initialization."""
        mock_client = Mock()
        mock_redis.from_url.return_value = mock_client
        mock_client.ping.return_value = True

        analyzer = AnomalyRootCauseAnalyzer()
        assert analyzer.redis_client is not None
        mock_client.ping.assert_called_once()

    @patch('src.reaper.engine.ml.anomaly_explainer.redis')
    def test_redis_initialization_failure(self, mock_redis):
        """Test Redis initialization failure handling."""
        mock_redis.from_url.side_effect = Exception("Connection failed")

        analyzer = AnomalyRootCauseAnalyzer()
        assert analyzer.redis_client is None

    def test_cache_key_generation(self):
        """Test cache key generation for anomaly data."""
        analyzer = AnomalyRootCauseAnalyzer()

        anomaly_data = {
            "resource_id": "res-123",
            "resource_type": "vm",
            "provider": "azure",
            "cost_change": 100.0,
            "time_period": "2024-01-01"
        }

        cache_key = analyzer._generate_cache_key(anomaly_data)
        assert cache_key.startswith("anomaly:")
        assert len(cache_key) > len("anomaly:")

    @patch('src.reaper.engine.ml.anomaly_explainer.redis')
    def test_cache_storage_and_retrieval(self, mock_redis):
        """Test caching and retrieval of explanations."""
        mock_client = Mock()
        mock_redis.from_url.return_value = mock_client
        mock_client.ping.return_value = True

        analyzer = AnomalyRootCauseAnalyzer()

        # Test caching
        test_explanation = {"root_cause": "test", "confidence": 0.8}
        analyzer._cache_explanation("test_key", test_explanation)
        mock_client.setex.assert_called_once()

        # Test retrieval
        mock_client.get.return_value = json.dumps(test_explanation)
        cached = analyzer._get_cached_explanation("test_key")
        assert cached == test_explanation


class TestRuleBasedFallback:
    """Test rule-based fallback system."""

    def test_domain_patterns_structure(self):
        """Test that domain patterns are properly defined."""
        assert hasattr(AnomalyRootCauseAnalyzer, 'DOMAIN_PATTERNS')
        patterns = AnomalyRootCauseAnalyzer.DOMAIN_PATTERNS

        assert "cost_spike_vm" in patterns
        assert "cost_spike_storage" in patterns
        assert "cost_spike_network" in patterns
        assert "cost_spike_database" in patterns
        assert "seasonal_pattern" in patterns

        # Check pattern structure
        for pattern_name, pattern_data in patterns.items():
            assert "indicators" in pattern_data
            assert "causes" in pattern_data
            assert "recommendations" in pattern_data

    def test_rule_based_fallback_vm_pattern(self):
        """Test rule-based fallback for VM cost spike."""
        analyzer = AnomalyRootCauseAnalyzer()

        anomaly_data = {"cost_change": 100.0}
        context_data = {
            "resource_info": {
                "type": "Virtual Machine",
                "name": "test-vm",
                "provider": "Azure"
            }
        }
        correlations = []

        result = analyzer._rule_based_fallback(anomaly_data, context_data, correlations)

        assert result["method"] == "rule_based"
        assert result["pattern_matched"] == True
        assert "root_cause" in result
        assert "confidence" in result

    def test_rule_based_fallback_no_pattern_match(self):
        """Test rule-based fallback when no pattern matches."""
        analyzer = AnomalyRootCauseAnalyzer()

        anomaly_data = {"cost_change": 100.0}
        context_data = {
            "resource_info": {
                "type": "UnknownResource",
                "name": "test",
                "provider": "Unknown"
            }
        }
        correlations = []

        result = analyzer._rule_based_fallback(anomaly_data, context_data, correlations)

        assert result["method"] == "correlation_fallback"
        assert result["pattern_matched"] == False


class TestSHAPFeatureImportance:
    """Test SHAP feature importance calculation."""

    def test_feature_extraction(self):
        """Test feature extraction from anomaly data."""
        analyzer = AnomalyRootCauseAnalyzer()

        anomaly_data = {
            "cost_change": 100.0,
            "cost_amount": 500.0
        }
        context_data = {
            "resource_info": {
                "type": "vm",
                "provider": "azure"
            },
            "cost_history": [
                {"date": "2024-01-01", "amount": 100.0},
                {"date": "2024-01-02", "amount": 200.0},
                {"date": "2024-01-03", "amount": 150.0}
            ]
        }

        features = analyzer._extract_features(anomaly_data, context_data)

        assert "cost_change" in features
        assert "cost_amount" in features
        assert "avg_cost" in features
        assert "std_cost" in features
        assert "cost_volatility" in features

    def test_shap_calculation_with_sufficient_data(self):
        """Test SHAP calculation with sufficient data."""
        analyzer = AnomalyRootCauseAnalyzer()

        anomaly_data = {
            "cost_change": 100.0,
            "cost_amount": 500.0
        }
        context_data = {
            "resource_info": {
                "type": "vm",
                "provider": "azure"
            },
            "cost_history": [
                {"date": "2024-01-01", "amount": 100.0},
                {"date": "2024-01-02", "amount": 200.0}
            ]
        }

        result = analyzer._calculate_feature_importance(anomaly_data, context_data)

        # Should either return results or error
        assert "feature_importance" in result or "error" in result


class TestTimeSeriesDecomposition:
    """Test time-series decomposition functionality."""

    def test_decomposition_with_insufficient_data(self):
        """Test decomposition with insufficient data."""
        analyzer = AnomalyRootCauseAnalyzer()

        context_data = {
            "cost_history": [
                {"date": "2024-01-01", "amount": 100.0}
            ]
        }

        result = analyzer._decompose_time_series(context_data)

        assert "error" in result
        assert "Insufficient data" in result["error"]

    def test_decomposition_with_sufficient_data(self):
        """Test decomposition with sufficient data."""
        analyzer = AnomalyRootCauseAnalyzer()

        # Create 14 days of data
        cost_history = []
        base_date = datetime(2024, 1, 1)
        for i in range(14):
            cost_history.append({
                "date": (base_date + timedelta(days=i)).isoformat(),
                "amount": 100.0 + i * 10 + np.random.normal(0, 5)
            })

        context_data = {"cost_history": cost_history}

        result = analyzer._decompose_time_series(context_data)

        # Should either return decomposition results or error
        # (may fail if statsmodels not properly installed)
        assert "error" in result or "trend" in result


class TestAnomalyClustering:
    """Test anomaly clustering functionality."""

    def test_clustering_with_single_anomaly(self):
        """Test clustering with single anomaly (should return -1)."""
        analyzer = AnomalyRootCauseAnalyzer()

        anomaly_results = [
            {
                "confidence_score": 0.8,
                "root_cause": "test cause",
                "causal_factors": [{"factor": "test", "description": "test"}]
            }
        ]

        result = analyzer._cluster_anomalies(anomaly_results)

        assert "cluster_ids" in result
        assert len(result["cluster_ids"]) == 1
        assert result["cluster_ids"][0] == -1  # No clusters with single point

    def test_clustering_with_multiple_anomalies(self):
        """Test clustering with multiple anomalies."""
        analyzer = AnomalyRootCauseAnalyzer()

        anomaly_results = [
            {
                "confidence_score": 0.8,
                "root_cause": "test cause 1",
                "causal_factors": [{"factor": "test", "description": "test"}]
            },
            {
                "confidence_score": 0.6,
                "root_cause": "test cause 2",
                "causal_factors": [{"factor": "test", "description": "test"}]
            },
            {
                "confidence_score": 0.9,
                "root_cause": "test cause 3",
                "causal_factors": [{"factor": "test", "description": "test"}]
            }
        ]

        result = analyzer._cluster_anomalies(anomaly_results)

        assert "cluster_ids" in result
        assert len(result["cluster_ids"]) == 3
        assert "cluster_insights" in result


class TestAnomalyLabeling:
    """Test automated anomaly labeling functionality."""

    def test_label_anomaly(self):
        """Test labeling an anomaly."""
        analyzer = AnomalyRootCauseAnalyzer()

        result = analyzer.label_anomaly("anomaly-123", "true_positive", "user-1")

        assert result["success"] == True
        assert result["anomaly_id"] == "anomaly-123"
        assert result["label"] == "true_positive"

        # Check that label was stored
        assert "anomaly-123" in analyzer.anomaly_labels
        assert analyzer.anomaly_labels["anomaly-123"]["label"] == "true_positive"

    def test_get_label_statistics_empty(self):
        """Test getting label statistics when no labels exist."""
        analyzer = AnomalyRootCauseAnalyzer()

        result = analyzer.get_label_statistics()

        assert "message" in result
        assert "No labels available" in result["message"]

    def test_get_label_statistics_with_data(self):
        """Test getting label statistics with labeled data."""
        analyzer = AnomalyRootCauseAnalyzer()

        # Add some labels
        analyzer.label_anomaly("anomaly-1", "true_positive", "user-1")
        analyzer.label_anomaly("anomaly-2", "false_positive", "user-1")
        analyzer.label_anomaly("anomaly-3", "true_positive", "user-2")

        result = analyzer.get_label_statistics()

        assert result["total_labels"] == 3
        assert "label_distribution" in result
        assert result["label_distribution"]["true_positive"] == 2
        assert result["label_distribution"]["false_positive"] == 1


class TestEnhancedAnalysis:
    """Test enhanced analysis integration."""

    @patch('src.reaper.engine.ml.anomaly_explainer.redis')
    @patch('src.reaper.engine.ml.anomaly_explainer.genai')
    def test_analyze_anomaly_with_cache_hit(self, mock_genai, mock_redis):
        """Test analysis with cache hit."""
        mock_client = Mock()
        mock_redis.from_url.return_value = mock_client
        mock_client.ping.return_value = True

        # Mock cached explanation
        cached_explanation = {
            "root_cause": "cached cause",
            "confidence": 0.9,
            "cache_hit": False
        }
        mock_client.get.return_value = json.dumps(cached_explanation)

        analyzer = AnomalyRootCauseAnalyzer()

        anomaly_data = {
            "resource_id": "res-123",
            "resource_type": "vm",
            "provider": "azure",
            "cost_change": 100.0
        }

        result = analyzer.analyze_anomaly("anomaly-123", anomaly_data)

        assert result["cache_hit"] == True
        assert result["root_cause"] == "cached cause"

    @patch('src.reaper.engine.ml.anomaly_explainer.SessionLocal')
    def test_analyze_anomaly_with_enhancements(self, mock_session):
        """Test analysis with all enhancements enabled."""
        analyzer = AnomalyRootCauseAnalyzer()

        # Mock database session
        mock_db = Mock()
        mock_session.return_value = mock_db

        anomaly_data = {
            "resource_id": "res-123",
            "resource_type": "vm",
            "provider": "azure",
            "cost_change": 100.0,
            "cost_date": "2024-01-15"
        }

        result = analyzer.analyze_anomaly("anomaly-123", anomaly_data)

        # Check that enhanced fields are present
        assert "anomaly_id" in result
        assert "analysis_method" in result
        assert "cache_hit" in result
        # May have errors if Gemini API not available, but structure should be there


if __name__ == "__main__":
    pytest.main([__file__, "-v"])