"""
Intelligent Alert Tuning System

Machine learning system that learns from user behavior to optimize
alert thresholds, reduce fatigue, and improve alert relevance.
"""

from datetime import datetime, timedelta
from typing import Any

import numpy as np

from reaper.engine.models.resources import SessionLocal
from reaper.utils.error_handler import get_logger

logger = get_logger(__name__)


class IntelligentAlertTuner:
    """
    Machine learning system that learns from user behavior to optimize
    alert thresholds, reduce fatigue, and improve alert relevance.
    """

    def __init__(self):
        """Initialize the alert tuner with learning parameters."""
        self.learning_rate = 0.1
        self.discount_factor = 0.9
        self.alert_history = {}
        self.user_preferences = {}

    def record_alert_feedback(
        self,
        alert_id: str,
        user_id: str,
        feedback_type: str,
        feedback_value: int = None,
        response_time_seconds: int = None,
        feedback_text: str = None,
    ) -> dict[str, Any]:
        """
        Record user feedback on an alert for learning.

        Args:
            alert_id: Unique identifier for the alert
            user_id: User who provided feedback
            feedback_type: Type of feedback ('acknowledge', 'dismiss', 'snooze', 'action_taken')
            feedback_value: Optional rating (1-5)
            response_time_seconds: Time taken to respond to alert
            feedback_text: Optional text feedback

        Returns:
            Dictionary with feedback recording status
        """
        try:
            # Store feedback in database
            db = SessionLocal()

            # Create feedback record (would use proper ORM model in production)
            feedback_record = {
                "alert_id": alert_id,
                "user_id": user_id,
                "feedback_type": feedback_type,
                "feedback_value": feedback_value,
                "response_time_seconds": response_time_seconds,
                "feedback_text": feedback_text,
                "timestamp": datetime.now().isoformat(),
            }

            # Update user preferences based on feedback
            self._update_user_preferences(user_id, feedback_type, feedback_value)

            # Update alert history
            if alert_id not in self.alert_history:
                self.alert_history[alert_id] = []
            self.alert_history[alert_id].append(feedback_record)

            db.close()

            return {
                "success": True,
                "message": "Feedback recorded successfully",
                "feedback_record": feedback_record,
            }

        except Exception as e:
            logger.error(f"Alert feedback recording failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def _update_user_preferences(
        self, user_id: str, feedback_type: str, feedback_value: int
    ) -> None:
        """Update user preferences based on feedback."""
        if user_id not in self.user_preferences:
            self.user_preferences[user_id] = {
                "alert_sensitivity": 0.5,  # 0-1 scale
                "preferred_alert_types": [],
                "dismissal_rate": 0.0,
                "action_rate": 0.0,
                "total_feedback_count": 0,
            }

        preferences = self.user_preferences[user_id]
        preferences["total_feedback_count"] += 1

        # Update sensitivity based on feedback
        if feedback_type == "dismiss":
            preferences["dismissal_rate"] = (
                preferences["dismissal_rate"] * (preferences["total_feedback_count"] - 1) + 1.0
            ) / preferences["total_feedback_count"]
            # Reduce sensitivity if user dismisses alerts
            preferences["alert_sensitivity"] = max(0.1, preferences["alert_sensitivity"] - 0.05)

        elif feedback_type == "action_taken":
            preferences["action_rate"] = (
                preferences["action_rate"] * (preferences["total_feedback_count"] - 1) + 1.0
            ) / preferences["total_feedback_count"]
            # Increase sensitivity if user takes action
            preferences["alert_sensitivity"] = min(1.0, preferences["alert_sensitivity"] + 0.05)

        # Use explicit feedback value if provided
        if feedback_value is not None:
            # Normalize 1-5 to 0-1 scale
            normalized_value = (feedback_value - 1) / 4.0
            # Adjust sensitivity towards user's rating
            preferences["alert_sensitivity"] = (
                preferences["alert_sensitivity"] * 0.7 + normalized_value * 0.3
            )

    def calculate_alert_quality_score(self, alert_id: str) -> dict[str, Any]:
        """
        Calculate quality score for an alert based on user feedback.

        Args:
            alert_id: Alert identifier

        Returns:
            Dictionary with quality score and factors
        """
        if alert_id not in self.alert_history or not self.alert_history[alert_id]:
            return {
                "alert_id": alert_id,
                "quality_score": 0.5,
                "factors": {},
                "confidence": "low",
            }

        feedback_records = self.alert_history[alert_id]

        # Calculate quality factors
        total_feedback = len(feedback_records)
        dismissals = sum(1 for f in feedback_records if f["feedback_type"] == "dismiss")
        actions = sum(1 for f in feedback_records if f["feedback_type"] == "action_taken")
        acknowledgments = sum(1 for f in feedback_records if f["feedback_type"] == "acknowledge")

        # Response time analysis
        response_times = [
            f["response_time_seconds"]
            for f in feedback_records
            if f["response_time_seconds"] is not None
        ]
        avg_response_time = np.mean(response_times) if response_times else 0

        # Calculate quality score (higher is better)
        quality_score = 0.5  # Base score

        # Positive factors
        if actions > 0:
            quality_score += 0.3 * (actions / total_feedback)
        if acknowledgments > 0:
            quality_score += 0.1 * (acknowledgments / total_feedback)

        # Negative factors
        if dismissals > 0:
            quality_score -= 0.4 * (dismissals / total_feedback)

        # Response time factor (faster is better)
        if avg_response_time > 0 and avg_response_time < 3600:  # Within 1 hour
            quality_score += 0.1

        # Normalize to 0-1 range
        quality_score = max(0.0, min(1.0, quality_score))

        return {
            "alert_id": alert_id,
            "quality_score": quality_score,
            "factors": {
                "action_rate": actions / total_feedback if total_feedback > 0 else 0,
                "dismissal_rate": dismissals / total_feedback if total_feedback > 0 else 0,
                "acknowledgment_rate": acknowledgments / total_feedback
                if total_feedback > 0
                else 0,
                "avg_response_time_seconds": avg_response_time,
                "total_feedback_count": total_feedback,
            },
            "confidence": "high"
            if total_feedback >= 5
            else "medium"
            if total_feedback >= 2
            else "low",
        }

    def optimize_alert_thresholds(
        self, alert_type: str, current_threshold: float, user_id: str = None
    ) -> dict[str, Any]:
        """
        Optimize alert thresholds based on user behavior and alert quality.

        Args:
            alert_type: Type of alert (e.g., 'cost_spike', 'budget_breach', 'idle_resource')
            current_threshold: Current threshold value
            user_id: Optional user ID for personalization

        Returns:
            Dictionary with optimized threshold and rationale
        """
        try:
            # Get user-specific preferences if provided
            sensitivity = 0.5  # Default
            if user_id and user_id in self.user_preferences:
                sensitivity = self.user_preferences[user_id]["alert_sensitivity"]

            # Calculate threshold adjustment based on sensitivity
            # Higher sensitivity = lower threshold (more alerts)
            # Lower sensitivity = higher threshold (fewer alerts)

            threshold_adjustment = (0.5 - sensitivity) * 0.4  # Max 40% adjustment
            optimized_threshold = current_threshold * (1.0 + threshold_adjustment)

            # Get historical alert quality for this type
            quality_scores = []
            for alert_id, feedback_list in self.alert_history.items():
                # In production, would filter by alert_type
                quality = self.calculate_alert_quality_score(alert_id)
                quality_scores.append(quality["quality_score"])

            avg_quality = np.mean(quality_scores) if quality_scores else 0.5

            # Adjust threshold based on quality
            # Low quality = increase threshold (reduce false positives)
            # High quality = decrease threshold (catch more issues)
            if avg_quality < 0.3:
                quality_adjustment = 0.2  # Increase threshold
            elif avg_quality > 0.7:
                quality_adjustment = -0.1  # Decrease threshold
            else:
                quality_adjustment = 0.0

            optimized_threshold = optimized_threshold * (1.0 + quality_adjustment)

            return {
                "alert_type": alert_type,
                "current_threshold": current_threshold,
                "optimized_threshold": optimized_threshold,
                "adjustment_percentage": (optimized_threshold - current_threshold)
                / current_threshold
                * 100,
                "user_sensitivity": sensitivity,
                "historical_quality": avg_quality,
                "rationale": self._generate_threshold_rationale(
                    sensitivity, avg_quality, threshold_adjustment, quality_adjustment
                ),
                "confidence": "medium",
            }

        except Exception as e:
            logger.error(f"Threshold optimization failed: {e}")
            return {
                "alert_type": alert_type,
                "error": str(e),
                "optimized_threshold": current_threshold,  # Fallback to current
            }

    def _generate_threshold_rationale(
        self, sensitivity: float, quality: float, threshold_adj: float, quality_adj: float
    ) -> str:
        """Generate human-readable rationale for threshold adjustment."""
        rationale_parts = []

        # Sensitivity rationale
        if sensitivity > 0.7:
            rationale_parts.append("User prefers more alerts (high sensitivity)")
        elif sensitivity < 0.3:
            rationale_parts.append("User prefers fewer alerts (low sensitivity)")
        else:
            rationale_parts.append("User has balanced alert preferences")

        # Quality rationale
        if quality < 0.3:
            rationale_parts.append(
                "Historical alert quality is low, increasing threshold to reduce false positives"
            )
        elif quality > 0.7:
            rationale_parts.append(
                "Historical alert quality is high, decreasing threshold to catch more issues"
            )
        else:
            rationale_parts.append("Historical alert quality is average, maintaining threshold")

        return ". ".join(rationale_parts) + "."

    def get_alert_recommendations(self, user_id: str = None) -> list[dict[str, Any]]:
        """
        Get personalized alert recommendations based on user behavior.

        Args:
            user_id: Optional user ID for personalization

        Returns:
            List of alert recommendations
        """
        recommendations = []

        # Get user preferences if provided
        preferences = None
        if user_id and user_id in self.user_preferences:
            preferences = self.user_preferences[user_id]

        # Generate recommendations based on preferences
        if preferences:
            if preferences["dismissal_rate"] > 0.6:
                recommendations.append(
                    {
                        "type": "reduce_alerts",
                        "priority": "high",
                        "description": "High dismissal rate detected. Consider increasing alert thresholds.",
                        "action": "Review alert sensitivity settings",
                        "expected_impact": "Reduce alert fatigue by 30-40%",
                    }
                )

            if preferences["action_rate"] > 0.7:
                recommendations.append(
                    {
                        "type": "maintain_alerts",
                        "priority": "low",
                        "description": "High action rate indicates alerts are valuable. Maintain current settings.",
                        "action": "Continue current alert configuration",
                        "expected_impact": "Maintain operational awareness",
                    }
                )

            if preferences["alert_sensitivity"] < 0.3:
                recommendations.append(
                    {
                        "type": "increase_sensitivity",
                        "priority": "medium",
                        "description": "Alert sensitivity is very low. You may be missing important issues.",
                        "action": "Consider increasing alert sensitivity",
                        "expected_impact": "Improve issue detection rate",
                    }
                )

        else:
            # Default recommendations for new users
            recommendations.append(
                {
                    "type": "default_setup",
                    "priority": "medium",
                    "description": "No user feedback history. Start with default alert settings.",
                    "action": "Begin with standard thresholds and adjust based on experience",
                    "expected_impact": "Establish baseline for optimization",
                }
            )

        return recommendations

    def analyze_alert_performance(self, days: int = 30) -> dict[str, Any]:
        """
        Analyze overall alert performance over a time period.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary with performance metrics
        """
        cutoff_date = datetime.now() - timedelta(days=days)

        # Filter feedback records by date
        recent_feedback = []
        for alert_id, feedback_list in self.alert_history.items():
            for feedback in feedback_list:
                feedback_date = datetime.fromisoformat(feedback["timestamp"])
                if feedback_date >= cutoff_date:
                    recent_feedback.append(feedback)

        if not recent_feedback:
            return {
                "period_days": days,
                "total_alerts": 0,
                "message": "No recent alert data available",
            }

        # Calculate performance metrics
        total_alerts = len(set(f["alert_id"] for f in recent_feedback))
        total_feedback = len(recent_feedback)

        dismissals = sum(1 for f in recent_feedback if f["feedback_type"] == "dismiss")
        actions = sum(1 for f in recent_feedback if f["feedback_type"] == "action_taken")
        acknowledgments = sum(1 for f in recent_feedback if f["feedback_type"] == "acknowledge")

        # Response time metrics
        response_times = [
            f["response_time_seconds"]
            for f in recent_feedback
            if f["response_time_seconds"] is not None
        ]
        avg_response_time = np.mean(response_times) if response_times else 0
        median_response_time = np.median(response_times) if response_times else 0

        return {
            "period_days": days,
            "total_alerts": total_alerts,
            "total_feedback": total_feedback,
            "performance_metrics": {
                "dismissal_rate": dismissals / total_feedback if total_feedback > 0 else 0,
                "action_rate": actions / total_feedback if total_feedback > 0 else 0,
                "acknowledgment_rate": acknowledgments / total_feedback
                if total_feedback > 0
                else 0,
                "avg_response_time_seconds": avg_response_time,
                "median_response_time_seconds": median_response_time,
            },
            "quality_assessment": self._assess_overall_quality(dismissals, actions, total_feedback),
        }

    def _assess_overall_quality(self, dismissals: int, actions: int, total: int) -> dict[str, Any]:
        """Assess overall alert quality."""
        if total == 0:
            return {"assessment": "no_data", "message": "No data available"}

        action_rate = actions / total
        dismissal_rate = dismissals / total

        if action_rate > 0.7 and dismissal_rate < 0.2:
            return {
                "assessment": "excellent",
                "message": "Alerts are highly relevant and actionable",
            }
        if action_rate > 0.5 and dismissal_rate < 0.3:
            return {
                "assessment": "good",
                "message": "Alerts are generally relevant with some room for improvement",
            }
        if action_rate > 0.3 and dismissal_rate < 0.5:
            return {
                "assessment": "fair",
                "message": "Alerts have moderate relevance, consider threshold optimization",
            }
        return {
            "assessment": "poor",
            "message": "Alerts may be causing fatigue, review thresholds and criteria",
        }
