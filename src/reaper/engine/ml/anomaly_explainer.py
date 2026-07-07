"""
Anomaly Root Cause Analysis

AI-powered system that explains cost anomalies by correlating
multiple data dimensions and generating human-readable explanations.

Enhanced with:
- Redis caching for similar anomaly patterns
- Rule-based fallback system with domain-specific patterns
- SHAP values for feature importance attribution
- Anomaly clustering for batch analysis
- Time-series decomposition for root cause analysis
- Automated anomaly labeling for continuous learning
"""

import hashlib
import json
import os
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import redis
import shap
from google import genai
from google.genai import types
from scipy import signal
from scipy.cluster.hierarchy import dendrogram, linkage
from scipy.spatial.distance import pdist, squareform
from sklearn.cluster import DBSCAN, KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from statsmodels.tsa.seasonal import seasonal_decompose

from reaper.engine.models.resources import SessionLocal
from reaper.utils.error_handler import get_logger

logger = get_logger(__name__)


class AnomalyRootCauseAnalyzer:
    """
    AI-powered system that explains cost anomalies by correlating
    multiple data dimensions and generating human-readable explanations.

    Enhanced with caching, rule-based fallback, SHAP explanations,
    clustering, time-series decomposition, and automated labeling.
    """

    # Domain-specific anomaly patterns for rule-based fallback
    DOMAIN_PATTERNS = {
        "cost_spike_vm": {
            "indicators": ["vm", "virtual machine", "compute", "cpu", "memory"],
            "causes": [
                "Unexpected VM scaling",
                "Increased compute workload",
                "VM size upgrade",
                "Long-running instances"
            ],
            "recommendations": [
                "Review VM utilization metrics",
                "Check for auto-scaling events",
                "Analyze workload patterns",
                "Consider rightsizing opportunities"
            ]
        },
        "cost_spike_storage": {
            "indicators": ["storage", "disk", "blob", "file", "data transfer"],
            "causes": [
                "Increased storage usage",
                "Data egress spikes",
                "Storage tier changes",
                "Backup operations"
            ],
            "recommendations": [
                "Review storage usage trends",
                "Analyze data transfer patterns",
                "Check backup schedules",
                "Optimize storage tier selection"
            ]
        },
        "cost_spike_network": {
            "indicators": ["network", "bandwidth", "data transfer", "egress", "ingress"],
            "causes": [
                "Increased data transfer",
                "Cross-region data movement",
                "Public endpoint usage",
                "CDN usage changes"
            ],
            "recommendations": [
                "Optimize data transfer routes",
                "Review CDN configuration",
                "Implement data compression",
                "Use private endpoints where possible"
            ]
        },
        "cost_spike_database": {
            "indicators": ["database", "sql", "nosql", "db", "data store"],
            "causes": [
                "Increased database operations",
                "Database scaling",
                "Storage growth",
                "Query performance issues"
            ],
            "recommendations": [
                "Review query performance",
                "Analyze database throughput",
                "Check indexing strategy",
                "Consider read replicas"
            ]
        },
        "seasonal_pattern": {
            "indicators": ["weekly", "monthly", "quarterly", "seasonal", "periodic"],
            "causes": [
                "Business cycle patterns",
                "Scheduled workloads",
                "End-of-month processing",
                "Seasonal demand changes"
            ],
            "recommendations": [
                "Implement reserved instances",
                "Schedule auto-scaling",
                "Optimize for predictable patterns",
                "Use spot instances for flexible workloads"
            ]
        }
    }

    def __init__(self):
        """Initialize the anomaly analyzer with Gemini client and enhancements."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")

        self.client = genai.Client(api_key=api_key)
        self.model_identity = "gemini-2.5-flash"

        # Initialize Redis caching
        self.redis_client = self._init_redis_cache()

        # Initialize feature scaler for SHAP
        self.feature_scaler = StandardScaler()

        # Initialize clustering models
        self.dbscan = DBSCAN(eps=0.5, min_samples=5)
        self.kmeans = KMeans(n_clusters=5, random_state=42)
        self.pca = PCA(n_components=0.95)  # Keep 95% variance

        # Anomaly label storage for continuous learning
        self.anomaly_labels = {}  # anomaly_id -> label
        self.label_history = []   # List of labeled anomalies

    def _init_redis_cache(self):
        """Initialize Redis client for caching anomaly patterns."""
        try:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            redis_client = redis.from_url(redis_url, decode_responses=True)
            # Test connection
            redis_client.ping()
            logger.info("Redis cache initialized successfully")
            return redis_client
        except Exception as e:
            logger.warning(f"Redis initialization failed, caching disabled: {e}")
            return None

    def _generate_cache_key(self, anomaly_data: dict[str, Any]) -> str:
        """Generate a unique cache key for anomaly data."""
        # Create a deterministic hash from relevant anomaly features
        features = {
            "resource_id": anomaly_data.get("resource_id"),
            "resource_type": anomaly_data.get("resource_type"),
            "provider": anomaly_data.get("provider"),
            "cost_change": anomaly_data.get("cost_change"),
            "time_period": anomaly_data.get("time_period")
        }
        feature_str = json.dumps(features, sort_keys=True)
        return f"anomaly:{hashlib.md5(feature_str.encode()).hexdigest()}"

    def _get_cached_explanation(self, cache_key: str) -> dict[str, Any] | None:
        """Retrieve cached explanation if available."""
        if not self.redis_client:
            return None
        try:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Cache retrieval failed: {e}")
        return None

    def _cache_explanation(self, cache_key: str, explanation: dict[str, Any], ttl: int = 86400):
        """Cache explanation with TTL (default 24 hours)."""
        if not self.redis_client:
            return
        try:
            self.redis_client.setex(cache_key, ttl, json.dumps(explanation))
            logger.debug(f"Cached explanation for key: {cache_key}")
        except Exception as e:
            logger.warning(f"Cache storage failed: {e}")

    def analyze_anomaly(self, anomaly_id: str, anomaly_data: dict[str, Any]) -> dict[str, Any]:
        """
        Analyze an anomaly to determine its root cause and generate explanation.

        Enhanced with caching, rule-based fallback, and advanced analysis features.

        Args:
            anomaly_id: Unique identifier for the anomaly
            anomaly_data: Dictionary containing anomaly details (cost spike info, etc.)

        Returns:
            Dictionary with root cause analysis and explanation
        """
        try:
            # Step 0: Check cache for similar anomalies
            cache_key = self._generate_cache_key(anomaly_data)
            cached_explanation = self._get_cached_explanation(cache_key)
            if cached_explanation:
                logger.info(f"Retrieved cached explanation for anomaly {anomaly_id}")
                cached_explanation["cache_hit"] = True
                cached_explanation["anomaly_id"] = anomaly_id
                return cached_explanation

            # Step 1: Gather contextual data
            context_data = self._gather_contextual_data(anomaly_data)

            # Step 2: Correlate potential causes
            correlations = self._correlate_causes(anomaly_data, context_data)

            # Step 3: Perform time-series decomposition if cost history available
            decomposition = self._decompose_time_series(context_data) if "cost_history" in context_data else None

            # Step 4: Generate AI-powered explanation with fallback
            explanation = self._generate_explanation_with_fallback(anomaly_data, context_data, correlations, decomposition)

            # Step 5: Generate SHAP feature importance if possible
            feature_importance = self._calculate_feature_importance(anomaly_data, context_data)

            # Step 6: Generate actionable recommendations
            recommendations = self._generate_recommendations(anomaly_data, correlations)

            result = {
                "anomaly_id": anomaly_id,
                "root_cause": explanation.get("root_cause", "Unknown"),
                "confidence_score": explanation.get("confidence", 0.5),
                "causal_factors": correlations,
                "explanation_text": explanation.get("explanation", ""),
                "recommendations": recommendations,
                "feature_importance": feature_importance,
                "time_series_decomposition": decomposition,
                "analysis_method": explanation.get("method", "ai"),
                "cache_hit": False,
                "analysis_timestamp": datetime.now().isoformat(),
            }

            # Cache the result
            self._cache_explanation(cache_key, result)

            return result

        except Exception as e:
            logger.error(f"Anomaly analysis failed: {e}")
            return {
                "anomaly_id": anomaly_id,
                "error": str(e),
                "analysis_timestamp": datetime.now().isoformat(),
            }

    def _gather_contextual_data(self, anomaly_data: dict[str, Any]) -> dict[str, Any]:
        """Gather contextual data around the anomaly period."""
        context = {}

        try:
            db = SessionLocal()

            # Get resource type information
            resource_id = anomaly_data.get("resource_id")
            if resource_id:
                from reaper.engine.models.resources import Resource

                resource = db.query(Resource).filter(Resource.id == resource_id).first()
                if resource:
                    context["resource_info"] = {
                        "name": resource.name,
                        "type": resource.type,
                        "provider": resource.provider,
                        "region": resource.region,
                        "sku": resource.sku,
                        "tags": resource.tags,
                    }

            # Get cost history around anomaly period
            if "cost_date" in anomaly_data:
                cost_date = anomaly_data["cost_date"]
                start_date = datetime.fromisoformat(cost_date) - timedelta(days=7)
                end_date = datetime.fromisoformat(cost_date) + timedelta(days=1)

                from reaper.engine.models.resources import CostHistory

                cost_history = (
                    db.query(CostHistory)
                    .filter(
                        CostHistory.cost_date >= start_date.date(),
                        CostHistory.cost_date <= end_date.date(),
                    )
                    .order_by(CostHistory.cost_date)
                    .all()
                )

                context["cost_history"] = [
                    {
                        "date": ch.cost_date.isoformat(),
                        "amount": ch.cost_amount,
                        "resource_id": ch.resource_id,
                    }
                    for ch in cost_history
                ]

            db.close()

        except Exception as e:
            logger.error(f"Contextual data gathering failed: {e}")

        return context

    def _correlate_causes(
        self, anomaly_data: dict[str, Any], context_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Correlate potential causes for the anomaly."""
        correlations = []

        # Analyze cost patterns
        if "cost_history" in context_data:
            cost_history = context_data["cost_history"]
            if len(cost_history) > 1:
                # Calculate trend
                amounts = [ch["amount"] for ch in cost_history]
                if len(amounts) >= 2:
                    recent_change = (
                        (amounts[-1] - amounts[-2]) / amounts[-2] if amounts[-2] > 0 else 0
                    )
                    correlations.append(
                        {
                            "factor": "cost_trend",
                            "description": f"Recent cost change: {recent_change:.1%}",
                            "impact": "high" if abs(recent_change) > 0.5 else "medium",
                        }
                    )

        # Analyze resource characteristics
        if "resource_info" in context_data:
            resource_info = context_data["resource_info"]
            correlations.append(
                {
                    "factor": "resource_type",
                    "description": f"Resource type: {resource_info.get('type')}",
                    "impact": "medium",
                }
            )
            correlations.append(
                {
                    "factor": "provider",
                    "description": f"Cloud provider: {resource_info.get('provider')}",
                    "impact": "low",
                }
            )

        # Analyze tags for business context
        if "resource_info" in context_data:
            tags = context_data["resource_info"].get("tags", {})
            if tags:
                correlations.append(
                    {
                        "factor": "business_context",
                        "description": f"Resource tags: {json.dumps(tags)}",
                        "impact": "medium",
                    }
                )

        return correlations

    def _generate_explanation(
        self, anomaly_data: dict, context_data: dict, correlations: list[dict]
    ) -> dict[str, Any]:
        """Generate AI-powered explanation using Gemini."""
        prompt = f"""
        You are a cloud cost analysis expert. Explain the root cause of this cost anomaly.

        Anomaly Details:
        {json.dumps(anomaly_data, indent=2, default=str)}

        Contextual Data:
        {json.dumps(context_data, indent=2, default=str)}

        Correlated Factors:
        {json.dumps(correlations, indent=2, default=str)}

        Provide a JSON response with:
        - root_cause: Primary cause of the anomaly (1-2 sentences)
        - confidence: Confidence score (0-1)
        - explanation: Detailed explanation (3-5 sentences)
        - key_factors: List of most important contributing factors
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_identity,
                contents=prompt,
                generation_config=types.GenerationConfig(
                    temperature=0.3, response_mime_type="application/json"
                ),
            )

            result = json.loads(response.text)
            logger.info(f"Generated explanation for anomaly: {result.get('root_cause')}")
            result["method"] = "ai"
            return result

        except Exception as e:
            logger.error(f"AI explanation generation failed: {e}")
            return self._rule_based_fallback(anomaly_data, context_data, correlations)

    def _rule_based_fallback(self, anomaly_data: dict, context_data: dict, correlations: list[dict]) -> dict[str, Any]:
        """Rule-based fallback system with domain-specific anomaly patterns."""
        try:
            # Extract relevant features for pattern matching
            resource_info = context_data.get("resource_info", {})
            resource_type = resource_info.get("type", "").lower()
            resource_name = resource_info.get("name", "").lower()
            provider = resource_info.get("provider", "").lower()

            # Combine all text for pattern matching
            search_text = f"{resource_type} {resource_name} {provider}"

            # Find matching domain pattern
            matched_pattern = None
            max_matches = 0

            for pattern_name, pattern_data in self.DOMAIN_PATTERNS.items():
                matches = 0
                for indicator in pattern_data["indicators"]:
                    if indicator.lower() in search_text:
                        matches += 1

                if matches > max_matches:
                    max_matches = matches
                    matched_pattern = pattern_data

            if matched_pattern and max_matches > 0:
                # Use matched pattern for explanation
                root_cause = matched_pattern["causes"][0] if matched_pattern["causes"] else "Unknown pattern match"
                key_factors = [f"Pattern: {pattern}" for pattern in matched_pattern["indicators"][:3]]

                return {
                    "root_cause": root_cause,
                    "confidence": min(0.7, 0.3 + (max_matches * 0.1)),  # Confidence based on match strength
                    "explanation": f"Cost anomaly matches known pattern for {matched_pattern['indicators'][0]}. "
                    f"Likely causes include: {', '.join(matched_pattern['causes'][:2])}. "
                    f"Recommendations: {', '.join(matched_pattern['recommendations'][:2])}.",
                    "key_factors": key_factors,
                    "method": "rule_based",
                    "pattern_matched": True
                }

            # Fallback to correlation-based explanation
            return self._correlation_based_fallback(anomaly_data, correlations)

        except Exception as e:
            logger.error(f"Rule-based fallback failed: {e}")
            return self._correlation_based_fallback(anomaly_data, correlations)

    def _correlation_based_fallback(self, anomaly_data: dict, correlations: list[dict]) -> dict[str, Any]:
        """Fallback explanation based on correlations when no pattern matches."""
        # Determine most likely cause based on correlations
        high_impact_factors = [c for c in correlations if c.get("impact") == "high"]

        if high_impact_factors:
            root_cause = f"Anomaly likely caused by: {high_impact_factors[0].get('description')}"
        else:
            root_cause = "Anomaly detected, but specific cause requires further investigation"

        return {
            "root_cause": root_cause,
            "confidence": 0.4,
            "explanation": f"Cost anomaly detected with {len(correlations)} correlated factors. "
            f"Primary factor appears to be related to {correlations[0].get('factor') if correlations else 'unknown causes'}.",
            "key_factors": [c.get("factor") for c in correlations[:3]],
            "method": "correlation_fallback",
            "pattern_matched": False
        }

    def _generate_explanation_with_fallback(
        self, anomaly_data: dict, context_data: dict, correlations: list[dict], decomposition: dict = None
    ) -> dict[str, Any]:
        """Generate explanation with fallback to rule-based system."""
        try:
            # Try AI first
            explanation = self._generate_explanation(anomaly_data, context_data, correlations)

            # If AI failed or low confidence, try rule-based
            if explanation.get("confidence", 0) < 0.5 or explanation.get("method") == "correlation_fallback":
                logger.info("AI confidence low, using rule-based fallback")
                rule_explanation = self._rule_based_fallback(anomaly_data, context_data, correlations)
                # Use rule-based if it has higher confidence
                if rule_explanation.get("confidence", 0) > explanation.get("confidence", 0):
                    explanation = rule_explanation

            # Enhance with time-series decomposition insights if available
            if decomposition:
                explanation["decomposition_insights"] = self._extract_decomposition_insights(decomposition)

            return explanation

        except Exception as e:
            logger.error(f"Explanation generation with fallback failed: {e}")
            return self._correlation_based_fallback(anomaly_data, correlations)

    def _generate_recommendations(
        self, anomaly_data: dict, correlations: list[dict]
    ) -> list[dict[str, Any]]:
        """Generate actionable recommendations based on anomaly analysis."""
        recommendations = []

        # Generic recommendations based on correlation factors
        for correlation in correlations:
            factor = correlation.get("factor")

            if factor == "cost_trend":
                recommendations.append(
                    {
                        "action": "monitor_trend",
                        "description": "Continue monitoring cost trends for the next 7 days",
                        "priority": "medium",
                        "estimated_impact": "Prevent future cost spikes",
                    }
                )

            elif factor == "resource_type":
                recommendations.append(
                    {
                        "action": "review_resource",
                        "description": "Review resource configuration and utilization",
                        "priority": "high",
                        "estimated_impact": "Optimize resource allocation",
                    }
                )

            elif factor == "business_context":
                recommendations.append(
                    {
                        "action": "validate_tags",
                        "description": "Validate resource tags and business context",
                        "priority": "low",
                        "estimated_impact": "Improve cost attribution",
                    }
                )

        return recommendations

    def batch_analyze_anomalies(self, anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Analyze multiple anomalies in batch with clustering for group analysis.

        Args:
            anomalies: List of anomaly dictionaries

        Returns:
            List of analysis results with cluster assignments
        """
        results = []
        for anomaly in anomalies:
            anomaly_id = anomaly.get("id", "unknown")
            result = self.analyze_anomaly(anomaly_id, anomaly)
            results.append(result)

        # Perform clustering on batch results
        if len(results) > 1:
            cluster_results = self._cluster_anomalies(results)
            for i, result in enumerate(results):
                result["cluster_id"] = cluster_results.get("cluster_ids", [])[i] if i < len(cluster_results.get("cluster_ids", [])) else -1
                result["cluster_insights"] = cluster_results.get("cluster_insights", {}).get(result.get("cluster_id", -1))

        return results

    def _decompose_time_series(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """Perform time-series decomposition to identify trend, seasonal, and residual components."""
        try:
            cost_history = context_data.get("cost_history", [])
            if not cost_history or len(cost_history) < 14:  # Need at least 2 weeks
                return {"error": "Insufficient data for decomposition"}

            # Extract time series data
            dates = [datetime.fromisoformat(ch["date"]) for ch in cost_history]
            values = [ch["amount"] for ch in cost_history]

            # Create pandas Series
            import pandas as pd
            ts = pd.Series(values, index=dates)

            # Perform decomposition
            # Use additive model for cost data (costs are always positive)
            decomposition = seasonal_decompose(ts, model='additive', period=7)  # Weekly seasonality

            # Extract components
            trend = decomposition.trend.dropna()
            seasonal = decomposition.seasonal.dropna()
            residual = decomposition.resid.dropna()

            # Analyze components
            trend_strength = self._calculate_trend_strength(trend)
            seasonal_strength = self._calculate_seasonal_strength(seasonal)
            residual_volatility = residual.std() if len(residual) > 0 else 0

            # Identify dominant component
            components = {
                "trend": trend_strength,
                "seasonal": seasonal_strength,
                "residual": residual_volatility
            }
            dominant_component = max(components, key=components.get)

            return {
                "trend": {
                    "values": trend.tolist(),
                    "strength": trend_strength,
                    "direction": "increasing" if trend.iloc[-1] > trend.iloc[0] else "decreasing"
                },
                "seasonal": {
                    "values": seasonal.tolist(),
                    "strength": seasonal_strength,
                    "pattern": "weekly"  # Assuming weekly pattern
                },
                "residual": {
                    "values": residual.tolist(),
                    "volatility": residual_volatility
                },
                "dominant_component": dominant_component,
                "interpretation": self._interpret_decomposition(dominant_component, components)
            }

        except Exception as e:
            logger.error(f"Time-series decomposition failed: {e}")
            return {"error": str(e)}

    def _calculate_trend_strength(self, trend_series) -> float:
        """Calculate the strength of the trend component."""
        if len(trend_series) < 2:
            return 0.0
        # Use linear regression slope as trend strength
        x = np.arange(len(trend_series))
        y = trend_series.values
        slope = np.polyfit(x, y, 1)[0]
        return abs(slope) / (np.mean(y) + 1e-6)  # Normalized by mean

    def _calculate_seasonal_strength(self, seasonal_series) -> float:
        """Calculate the strength of the seasonal component."""
        if len(seasonal_series) < 2:
            return 0.0
        # Use range relative to mean as seasonal strength
        return (seasonal_series.max() - seasonal_series.min()) / (np.mean(np.abs(seasonal_series)) + 1e-6)

    def _interpret_decomposition(self, dominant_component: str, components: dict) -> str:
        """Generate interpretation of decomposition results."""
        interpretations = {
            "trend": "Strong trend pattern detected - anomaly likely related to gradual cost changes",
            "seasonal": "Strong seasonal pattern detected - anomaly likely part of regular business cycle",
            "residual": "High residual volatility - anomaly likely due to irregular or unexpected factors"
        }
        return interpretations.get(dominant_component, "Mixed patterns detected")

    def _extract_decomposition_insights(self, decomposition: dict) -> list[str]:
        """Extract key insights from time-series decomposition."""
        insights = []

        if "error" in decomposition:
            return ["Decomposition analysis unavailable"]

        dominant = decomposition.get("dominant_component", "")
        if dominant == "trend":
            trend_dir = decomposition["trend"]["direction"]
            insights.append(f"Cost trend is {trend_dir}, suggesting gradual changes")
        elif dominant == "seasonal":
            insights.append("Strong seasonal patterns detected, likely part of regular business cycle")
        elif dominant == "residual":
            insights.append("High irregular volatility detected, suggesting unexpected factors")

        return insights

    def _calculate_feature_importance(self, anomaly_data: dict, context_data: dict) -> dict[str, Any]:
        """Calculate SHAP feature importance for anomaly explanation."""
        try:
            # Extract features from anomaly data and context
            features = self._extract_features(anomaly_data, context_data)
            if not features:
                return {"error": "Insufficient features for SHAP analysis"}

            # Create feature matrix
            feature_names = list(features.keys())
            feature_values = np.array([list(features.values())])

            # Scale features
            scaled_features = self.feature_scaler.fit_transform(feature_values)

            # Use a simple model for SHAP (in production, use a trained model)
            from sklearn.ensemble import RandomForestRegressor
            model = RandomForestRegressor(n_estimators=100, random_state=42)

            # For SHAP, we need more data points - create synthetic variations
            synthetic_data = self._create_synthetic_features(features, n_samples=50)
            synthetic_scaled = self.feature_scaler.transform(synthetic_data)

            # Train model on synthetic data
            # Create synthetic target (cost change as target)
            synthetic_target = synthetic_scaled[:, 0]  # Use first feature as target
            model.fit(synthetic_scaled, synthetic_target)

            # Calculate SHAP values
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(scaled_features)

            # Format results
            importance_dict = {}
            for i, name in enumerate(feature_names):
                importance_dict[name] = {
                    "value": float(shap_values[0][i]),
                    "importance": abs(float(shap_values[0][i]))
                }

            # Sort by importance
            sorted_importance = sorted(importance_dict.items(), key=lambda x: x[1]["importance"], reverse=True)

            return {
                "feature_importance": dict(sorted_importance),
                "top_features": [name for name, _ in sorted_importance[:5]],
                "interpretation": self._interpret_shap_values(sorted_importance[:3])
            }

        except Exception as e:
            logger.error(f"SHAP feature importance calculation failed: {e}")
            return {"error": str(e)}

    def _extract_features(self, anomaly_data: dict, context_data: dict) -> dict[str, float]:
        """Extract numerical features from anomaly data for SHAP analysis."""
        features = {}

        try:
            # Basic anomaly features
            features["cost_change"] = float(anomaly_data.get("cost_change", 0))
            features["cost_amount"] = float(anomaly_data.get("cost_amount", 0))

            # Resource features
            resource_info = context_data.get("resource_info", {})
            features["resource_type_encoded"] = hash(resource_info.get("type", "")) % 100
            features["provider_encoded"] = hash(resource_info.get("provider", "")) % 100

            # Cost history features
            cost_history = context_data.get("cost_history", [])
            if cost_history:
                costs = [ch["amount"] for ch in cost_history]
                features["avg_cost"] = np.mean(costs)
                features["std_cost"] = np.std(costs)
                features["max_cost"] = np.max(costs)
                features["min_cost"] = np.min(costs)
                features["cost_volatility"] = features["std_cost"] / (features["avg_cost"] + 1e-6)
            else:
                features["avg_cost"] = 0.0
                features["std_cost"] = 0.0
                features["max_cost"] = 0.0
                features["min_cost"] = 0.0
                features["cost_volatility"] = 0.0

            # Time-based features
            features["day_of_week"] = datetime.now().weekday()
            features["day_of_month"] = datetime.now().day

            return features

        except Exception as e:
            logger.error(f"Feature extraction failed: {e}")
            return {}

    def _create_synthetic_features(self, base_features: dict, n_samples: int = 50) -> np.ndarray:
        """Create synthetic feature variations for SHAP analysis."""
        feature_names = list(base_features.keys())
        base_values = np.array([list(base_features.values())])

        # Add noise to create variations
        noise_level = 0.1
        synthetic_data = []

        for _ in range(n_samples):
            noise = np.random.normal(0, noise_level, len(base_values[0]))
            synthetic_sample = base_values[0] * (1 + noise)
            synthetic_data.append(synthetic_sample)

        return np.array(synthetic_data)

    def _interpret_shap_values(self, top_features: list) -> str:
        """Generate interpretation of SHAP values."""
        if not top_features:
            return "No significant features identified"

        feature_names = [name for name, _ in top_features]
        return f"Most influential factors: {', '.join(feature_names[:3])}"

    def _cluster_anomalies(self, anomaly_results: list[dict]) -> dict[str, Any]:
        """Cluster similar anomalies for batch analysis."""
        try:
            # Extract features for clustering
            features = []
            valid_indices = []

            for i, result in enumerate(anomaly_results):
                feature_vector = self._extract_anomaly_features(result)
                if feature_vector:
                    features.append(feature_vector)
                    valid_indices.append(i)

            if len(features) < 2:
                return {"cluster_ids": [-1] * len(anomaly_results), "cluster_insights": {}}

            features_array = np.array(features)

            # Normalize features
            normalized_features = StandardScaler().fit_transform(features_array)

            # Apply PCA for dimensionality reduction
            reduced_features = self.pca.fit_transform(normalized_features)

            # Perform clustering
            n_clusters = min(5, len(features) // 2)  # Adaptive number of clusters
            if n_clusters < 2:
                n_clusters = 2

            cluster_labels = self.kmeans.fit_predict(reduced_features)

            # Map cluster labels back to original results
            cluster_ids = [-1] * len(anomaly_results)
            for idx, cluster_id in zip(valid_indices, cluster_labels):
                cluster_ids[idx] = int(cluster_id)

            # Generate cluster insights
            cluster_insights = self._generate_cluster_insights(anomaly_results, cluster_ids)

            return {
                "cluster_ids": cluster_ids,
                "cluster_insights": cluster_insights,
                "n_clusters": n_clusters,
                "cluster_centers": self.kmeans.cluster_centers_.tolist()
            }

        except Exception as e:
            logger.error(f"Anomaly clustering failed: {e}")
            return {"cluster_ids": [-1] * len(anomaly_results), "cluster_insights": {}}

    def _extract_anomaly_features(self, anomaly_result: dict) -> list[float] | None:
        """Extract feature vector from anomaly result for clustering."""
        try:
            features = []

            # Numerical features
            features.append(anomaly_result.get("confidence_score", 0.5))

            # Root cause encoding
            root_cause = anomaly_result.get("root_cause", "")
            features.append(hash(root_cause) % 100)

            # Causal factors count
            causal_factors = anomaly_result.get("causal_factors", [])
            features.append(len(causal_factors))

            # Feature importance (if available)
            feature_importance = anomaly_result.get("feature_importance", {})
            if isinstance(feature_importance, dict) and "feature_importance" in feature_importance:
                top_importance = list(feature_importance["feature_importance"].values())[:3]
                for imp in top_importance:
                    if isinstance(imp, dict):
                        features.append(imp.get("importance", 0.0))

            return features if features else None

        except Exception as e:
            logger.error(f"Feature extraction for clustering failed: {e}")
            return None

    def _generate_cluster_insights(self, anomaly_results: list[dict], cluster_ids: list[int]) -> dict[int, dict]:
        """Generate insights for each cluster."""
        cluster_insights = {}

        # Group anomalies by cluster
        clusters = {}
        for idx, cluster_id in enumerate(cluster_ids):
            if cluster_id not in clusters:
                clusters[cluster_id] = []
            clusters[cluster_id].append(anomaly_results[idx])

        # Generate insights for each cluster
        for cluster_id, cluster_anomalies in clusters.items():
            if cluster_id == -1:  # Noise cluster
                continue

            insights = {
                "size": len(cluster_anomalies),
                "common_patterns": self._find_common_patterns(cluster_anomalies),
                "avg_confidence": np.mean([a.get("confidence_score", 0.5) for a in cluster_anomalies]),
                "top_root_causes": self._get_top_root_causes(cluster_anomalies)
            }

            cluster_insights[cluster_id] = insights

        return cluster_insights

    def _find_common_patterns(self, cluster_anomalies: list[dict]) -> list[str]:
        """Find common patterns among anomalies in a cluster."""
        patterns = []

        # Common resource types
        resource_types = []
        for anomaly in cluster_anomalies:
            causal_factors = anomaly.get("causal_factors", [])
            for factor in causal_factors:
                if factor.get("factor") == "resource_type":
                    resource_types.append(factor.get("description", ""))

        if resource_types:
            from collections import Counter
            common_types = [rt for rt, _ in Counter(resource_types).most_common(3)]
            patterns.extend([f"Common resource type: {rt}" for rt in common_types])

        return patterns

    def _get_top_root_causes(self, cluster_anomalies: list[dict]) -> list[str]:
        """Get most common root causes in cluster."""
        root_causes = [a.get("root_cause", "") for a in cluster_anomalies]

        from collections import Counter
        top_causes = [rc for rc, _ in Counter(root_causes).most_common(3)]

        return top_causes

    def label_anomaly(self, anomaly_id: str, label: str, user_id: str = None) -> dict[str, Any]:
        """
        Label an anomaly for continuous learning.

        Args:
            anomaly_id: Unique identifier for the anomaly
            label: User-provided label (e.g., "true_positive", "false_positive", "actionable")
            user_id: Optional user ID who provided the label

        Returns:
            Dictionary with labeling status
        """
        try:
            # Store label
            self.anomaly_labels[anomaly_id] = {
                "label": label,
                "user_id": user_id,
                "timestamp": datetime.now().isoformat()
            }

            # Add to history
            self.label_history.append({
                "anomaly_id": anomaly_id,
                "label": label,
                "user_id": user_id,
                "timestamp": datetime.now().isoformat()
            })

            # TODO: In production, this would trigger model retraining
            logger.info(f"Anomaly {anomaly_id} labeled as '{label}' by user {user_id}")

            return {
                "success": True,
                "anomaly_id": anomaly_id,
                "label": label,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Anomaly labeling failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_label_statistics(self) -> dict[str, Any]:
        """Get statistics about anomaly labels for continuous learning insights."""
        if not self.label_history:
            return {"message": "No labels available yet"}

        from collections import Counter
        label_counts = Counter([l["label"] for l in self.label_history])

        return {
            "total_labels": len(self.label_history),
            "label_distribution": dict(label_counts),
            "most_common_label": label_counts.most_common(1)[0] if label_counts else None,
            "labeling_trend": self._calculate_labeling_trend()
        }

    def _calculate_labeling_trend(self) -> list[dict]:
        """Calculate labeling trend over time."""
        # Group labels by day
        from collections import defaultdict
        daily_labels = defaultdict(list)

        for label_entry in self.label_history:
            date = label_entry["timestamp"][:10]  # Extract date part
            daily_labels[date].append(label_entry["label"])

        # Calculate trend
        trend = []
        for date, labels in sorted(daily_labels.items()):
            from collections import Counter
            label_counts = Counter(labels)
            trend.append({
                "date": date,
                "total_labels": len(labels),
                "label_breakdown": dict(label_counts)
            })

        return trend
