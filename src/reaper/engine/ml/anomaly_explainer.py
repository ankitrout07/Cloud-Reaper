"""
Anomaly Root Cause Analysis

AI-powered system that explains cost anomalies by correlating
multiple data dimensions and generating human-readable explanations.
"""

import json
from datetime import datetime, timedelta
from typing import Any

from google import genai
from google.genai import types

from reaper.engine.models.resources import SessionLocal
from reaper.utils.error_handler import get_logger

logger = get_logger(__name__)


class AnomalyRootCauseAnalyzer:
    """
    AI-powered system that explains cost anomalies by correlating
    multiple data dimensions and generating human-readable explanations.
    """

    def __init__(self):
        """Initialize the anomaly analyzer with Gemini client."""
        import os

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")

        self.client = genai.Client(api_key=api_key)
        self.model_identity = "gemini-2.5-flash"

    def analyze_anomaly(self, anomaly_id: str, anomaly_data: dict[str, Any]) -> dict[str, Any]:
        """
        Analyze an anomaly to determine its root cause and generate explanation.

        Args:
            anomaly_id: Unique identifier for the anomaly
            anomaly_data: Dictionary containing anomaly details (cost spike info, etc.)

        Returns:
            Dictionary with root cause analysis and explanation
        """
        try:
            # Step 1: Gather contextual data
            context_data = self._gather_contextual_data(anomaly_data)

            # Step 2: Correlate potential causes
            correlations = self._correlate_causes(anomaly_data, context_data)

            # Step 3: Generate AI-powered explanation
            explanation = self._generate_explanation(anomaly_data, context_data, correlations)

            # Step 4: Generate actionable recommendations
            recommendations = self._generate_recommendations(anomaly_data, correlations)

            return {
                "anomaly_id": anomaly_id,
                "root_cause": explanation.get("root_cause", "Unknown"),
                "confidence_score": explanation.get("confidence", 0.5),
                "causal_factors": correlations,
                "explanation_text": explanation.get("explanation", ""),
                "recommendations": recommendations,
                "analysis_timestamp": datetime.now().isoformat(),
            }

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
            return result

        except Exception as e:
            logger.error(f"AI explanation generation failed: {e}")
            return self._fallback_explanation(anomaly_data, correlations)

    def _fallback_explanation(self, anomaly_data: dict, correlations: list[dict]) -> dict[str, Any]:
        """Fallback explanation without AI."""
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
        }

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
        Analyze multiple anomalies in batch.

        Args:
            anomalies: List of anomaly dictionaries

        Returns:
            List of analysis results
        """
        results = []
        for anomaly in anomalies:
            anomaly_id = anomaly.get("id", "unknown")
            result = self.analyze_anomaly(anomaly_id, anomaly)
            results.append(result)

        return results
