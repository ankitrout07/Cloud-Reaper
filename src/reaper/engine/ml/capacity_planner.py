"""
Predictive Capacity Planning System

Multi-model ensemble system for predicting future resource needs
using historical patterns, business growth, and seasonal trends.
"""

from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA

from reaper.engine.models.resources import SessionLocal
from reaper.utils.error_handler import get_logger

logger = get_logger(__name__)


class PredictiveCapacityPlanner:
    """
    Multi-model ensemble system for predicting future resource needs
    using historical patterns, business growth, and seasonal trends.
    """

    def __init__(self):
        """Initialize the capacity planner with forecasting models."""
        self.models = {}
        self.forecast_horizons = {
            "short_term": 7,  # 1 week
            "medium_term": 30,  # 1 month
            "long_term": 90,  # 3 months
        }

    def predict_resource_capacity(
        self, resource_id: str, horizon: str = "medium_term"
    ) -> dict[str, Any]:
        """
        Predict future capacity needs for a specific resource.

        Args:
            resource_id: Resource identifier
            horizon: Forecast horizon ('short_term', 'medium_term', 'long_term')

        Returns:
            Dictionary with capacity predictions and recommendations
        """
        try:
            # Step 1: Gather historical data
            historical_data = self._gather_historical_data(resource_id)

            if not historical_data:
                return {
                    "resource_id": resource_id,
                    "error": "Insufficient historical data for prediction",
                    "forecast": None,
                }

            # Step 2: Prepare time series data
            time_series = self._prepare_time_series(historical_data)

            # Step 3: Generate forecasts using multiple models
            forecasts = self._generate_ensemble_forecast(time_series, horizon)

            # Step 4: Generate capacity recommendations
            recommendations = self._generate_capacity_recommendations(
                historical_data, forecasts, horizon
            )

            # Step 5: Calculate confidence intervals
            confidence_intervals = self._calculate_confidence_intervals(time_series, forecasts)

            return {
                "resource_id": resource_id,
                "forecast_horizon": horizon,
                "historical_summary": self._summarize_historical_data(historical_data),
                "forecasts": forecasts,
                "confidence_intervals": confidence_intervals,
                "recommendations": recommendations,
                "prediction_timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Capacity prediction failed for resource {resource_id}: {e}")
            return {
                "resource_id": resource_id,
                "error": str(e),
                "forecast": None,
            }

    def _gather_historical_data(self, resource_id: str) -> list[dict]:
        """Gather historical utilization and cost data for a resource."""
        try:
            db = SessionLocal()

            # Get resource info
            from reaper.engine.models.resources import Resource

            resource = db.query(Resource).filter(Resource.id == resource_id).first()
            if not resource:
                return []

            # Get cost history (last 90 days)
            from reaper.engine.models.resources import CostHistory

            start_date = datetime.now() - timedelta(days=90)
            cost_history = (
                db.query(CostHistory)
                .filter(
                    CostHistory.resource_id == resource_id,
                    CostHistory.cost_date >= start_date.date(),
                )
                .order_by(CostHistory.cost_date)
                .all()
            )

            historical_data = [
                {
                    "date": ch.cost_date.isoformat(),
                    "cost": ch.cost_amount,
                    "resource_id": ch.resource_id,
                }
                for ch in cost_history
            ]

            db.close()
            return historical_data

        except Exception as e:
            logger.error(f"Historical data gathering failed: {e}")
            return []

    def _prepare_time_series(self, historical_data: list[dict]) -> pd.Series:
        """Prepare time series data for forecasting."""
        if not historical_data:
            return pd.Series()

        df = pd.DataFrame(historical_data)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        # Create daily time series
        daily_data = df.groupby("date")["cost"].sum()

        # Fill missing dates
        date_range = pd.date_range(
            start=daily_data.index.min(), end=daily_data.index.max(), freq="D"
        )
        daily_data = daily_data.reindex(date_range, fill_value=0)

        return daily_data

    def _generate_ensemble_forecast(self, time_series: pd.Series, horizon: str) -> dict[str, Any]:
        """Generate ensemble forecast using multiple models."""
        forecast_days = self.forecast_horizons.get(horizon, 30)

        if len(time_series) < 7:
            # Not enough data for sophisticated models
            return self._simple_forecast(time_series, forecast_days)

        forecasts = {}

        # Model 1: ARIMA
        try:
            arima_forecast = self._arima_forecast(time_series, forecast_days)
            forecasts["arima"] = arima_forecast
        except Exception as e:
            logger.warning(f"ARIMA forecast failed: {e}")

        # Model 2: Moving Average
        try:
            ma_forecast = self._moving_average_forecast(time_series, forecast_days)
            forecasts["moving_average"] = ma_forecast
        except Exception as e:
            logger.warning(f"Moving average forecast failed: {e}")

        # Model 3: Linear Trend
        try:
            trend_forecast = self._linear_trend_forecast(time_series, forecast_days)
            forecasts["linear_trend"] = trend_forecast
        except Exception as e:
            logger.warning(f"Linear trend forecast failed: {e}")

        # Ensemble: Weighted average of available models
        if forecasts:
            ensemble_forecast = self._ensemble_forecasts(forecasts, forecast_days)
            forecasts["ensemble"] = ensemble_forecast
        else:
            forecasts["ensemble"] = self._simple_forecast(time_series, forecast_days)

        return forecasts

    def _arima_forecast(self, time_series: pd.Series, days: int) -> dict[str, Any]:
        """Generate ARIMA forecast."""
        try:
            # Simple ARIMA(1,1,1) model
            model = ARIMA(time_series, order=(1, 1, 1))
            model_fit = model.fit()

            forecast = model_fit.forecast(steps=days)

            # Generate forecast dates
            last_date = time_series.index[-1]
            forecast_dates = pd.date_range(
                start=last_date + timedelta(days=1), periods=days, freq="D"
            )

            return {
                "model": "ARIMA(1,1,1)",
                "values": forecast.tolist(),
                "dates": [d.isoformat() for d in forecast_dates],
                "confidence": "medium",
            }

        except Exception as e:
            logger.error(f"ARIMA forecast error: {e}")
            raise

    def _moving_average_forecast(self, time_series: pd.Series, days: int) -> dict[str, Any]:
        """Generate moving average forecast."""
        try:
            # Use 7-day moving average
            window = min(7, len(time_series))
            ma_value = time_series.rolling(window=window).mean().iloc[-1]

            forecast_values = [ma_value] * days

            last_date = time_series.index[-1]
            forecast_dates = pd.date_range(
                start=last_date + timedelta(days=1), periods=days, freq="D"
            )

            return {
                "model": f"Moving Average ({window}-day)",
                "values": forecast_values,
                "dates": [d.isoformat() for d in forecast_dates],
                "confidence": "low",
            }

        except Exception as e:
            logger.error(f"Moving average forecast error: {e}")
            raise

    def _linear_trend_forecast(self, time_series: pd.Series, days: int) -> dict[str, Any]:
        """Generate linear trend forecast."""
        try:
            # Fit linear trend
            x = np.arange(len(time_series))
            y = time_series.values

            # Simple linear regression
            coeffs = np.polyfit(x, y, 1)
            trend_func = np.poly1d(coeffs)

            # Extrapolate
            x_forecast = np.arange(len(time_series), len(time_series) + days)
            forecast_values = trend_func(x_forecast)

            # Ensure non-negative
            forecast_values = np.maximum(forecast_values, 0)

            last_date = time_series.index[-1]
            forecast_dates = pd.date_range(
                start=last_date + timedelta(days=1), periods=days, freq="D"
            )

            return {
                "model": "Linear Trend",
                "values": forecast_values.tolist(),
                "dates": [d.isoformat() for d in forecast_dates],
                "confidence": "low",
            }

        except Exception as e:
            logger.error(f"Linear trend forecast error: {e}")
            raise

    def _simple_forecast(self, time_series: pd.Series, days: int) -> dict[str, Any]:
        """Simple forecast using historical average."""
        if len(time_series) == 0:
            avg_value = 0
        else:
            avg_value = time_series.mean()

        forecast_values = [avg_value] * days

        last_date = time_series.index[-1] if len(time_series) > 0 else datetime.now()
        forecast_dates = pd.date_range(start=last_date + timedelta(days=1), periods=days, freq="D")

        return {
            "model": "Historical Average",
            "values": forecast_values,
            "dates": [d.isoformat() for d in forecast_dates],
            "confidence": "very_low",
        }

    def _ensemble_forecasts(self, forecasts: dict, days: int) -> dict[str, Any]:
        """Combine multiple forecasts using weighted average."""
        ensemble_values = []
        weights = {"arima": 0.5, "moving_average": 0.3, "linear_trend": 0.2}

        # Initialize with zeros
        for i in range(days):
            weighted_sum = 0.0
            total_weight = 0.0

            for model_name, forecast in forecasts.items():
                if model_name in weights and i < len(forecast["values"]):
                    weight = weights[model_name]
                    weighted_sum += weight * forecast["values"][i]
                    total_weight += weight

            if total_weight > 0:
                ensemble_values.append(weighted_sum / total_weight)
            else:
                ensemble_values.append(0.0)

        # Use dates from the first available forecast
        first_forecast = next(iter(forecasts.values()))
        forecast_dates = first_forecast["dates"][:days]

        return {
            "model": "Ensemble (Weighted Average)",
            "values": ensemble_values,
            "dates": forecast_dates,
            "confidence": "medium",
        }

    def _calculate_confidence_intervals(
        self, time_series: pd.Series, forecasts: dict
    ) -> dict[str, Any]:
        """Calculate confidence intervals for forecasts."""
        if "ensemble" not in forecasts:
            return {}

        ensemble_values = forecasts["ensemble"]["values"]
        std_dev = np.std(time_series.values) if len(time_series) > 0 else 0

        # Calculate 95% confidence intervals
        confidence_intervals = []
        for value in ensemble_values:
            lower = max(0, value - 1.96 * std_dev)
            upper = value + 1.96 * std_dev
            confidence_intervals.append({"lower": lower, "upper": upper})

        return {
            "confidence_level": 0.95,
            "intervals": confidence_intervals,
        }

    def _generate_capacity_recommendations(
        self, historical_data: list[dict], forecasts: dict, horizon: str
    ) -> list[dict[str, Any]]:
        """Generate capacity planning recommendations."""
        recommendations = []

        if "ensemble" not in forecasts:
            return recommendations

        ensemble_forecast = forecasts["ensemble"]
        forecast_values = ensemble_forecast["values"]

        if not forecast_values:
            return recommendations

        # Calculate forecast statistics
        avg_forecast = np.mean(forecast_values)
        max_forecast = np.max(forecast_values)
        total_forecast = np.sum(forecast_values)

        # Compare with historical average
        if historical_data:
            historical_avg = np.mean([d["cost"] for d in historical_data])
            growth_rate = (
                (avg_forecast - historical_avg) / historical_avg if historical_avg > 0 else 0
            )

            if growth_rate > 0.2:  # >20% growth
                recommendations.append(
                    {
                        "type": "scale_up",
                        "priority": "high",
                        "description": f"Forecasted {growth_rate:.1%} increase in costs. Consider scaling up capacity.",
                        "action": "Review resource allocation and consider proactive scaling",
                        "estimated_impact": f"Additional ${total_forecast - historical_avg * len(forecast_values):.2f} over {horizon}",
                    }
                )
            elif growth_rate < -0.1:  # >10% decrease
                recommendations.append(
                    {
                        "type": "scale_down",
                        "priority": "medium",
                        "description": f"Forecasted {growth_rate:.1%} decrease in costs. Consider rightsizing.",
                        "action": "Review resource utilization and consider downsizing",
                        "estimated_impact": f"Potential savings of ${abs(total_forecast - historical_avg * len(forecast_values)):.2f} over {horizon}",
                    }
                )

        # Peak capacity recommendation
        if max_forecast > avg_forecast * 1.5:
            recommendations.append(
                {
                    "type": "peak_capacity",
                    "priority": "medium",
                    "description": f"Peak forecast (${max_forecast:.2f}) is significantly above average (${avg_forecast:.2f}).",
                    "action": "Prepare for peak loads or implement auto-scaling",
                    "estimated_impact": "Prevent performance issues during peak periods",
                }
            )

        return recommendations

    def _summarize_historical_data(self, historical_data: list[dict]) -> dict[str, Any]:
        """Summarize historical data for context."""
        if not historical_data:
            return {}

        costs = [d["cost"] for d in historical_data]

        return {
            "data_points": len(historical_data),
            "total_cost": sum(costs),
            "average_cost": np.mean(costs),
            "min_cost": min(costs),
            "max_cost": max(costs),
            "std_dev": np.std(costs),
            "date_range": {
                "start": historical_data[0]["date"],
                "end": historical_data[-1]["date"],
            },
        }

    def predict_multi_resource_capacity(
        self, resource_ids: list[str], horizon: str = "medium_term"
    ) -> dict[str, Any]:
        """
        Predict capacity needs for multiple resources.

        Args:
            resource_ids: List of resource identifiers
            horizon: Forecast horizon

        Returns:
            Dictionary with aggregate predictions and individual forecasts
        """
        results = {
            "horizon": horizon,
            "resource_count": len(resource_ids),
            "forecasts": [],
            "aggregate_summary": {},
        }

        for resource_id in resource_ids:
            forecast = self.predict_resource_capacity(resource_id, horizon)
            results["forecasts"].append(forecast)

        # Calculate aggregate summary
        if results["forecasts"]:
            total_forecast_cost = 0
            successful_forecasts = [f for f in results["forecasts"] if "error" not in f]

            for forecast in successful_forecasts:
                if "forecasts" in forecast and "ensemble" in forecast["forecasts"]:
                    ensemble_values = forecast["forecasts"]["ensemble"]["values"]
                    total_forecast_cost += sum(ensemble_values)

            results["aggregate_summary"] = {
                "successful_predictions": len(successful_forecasts),
                "failed_predictions": len(results["forecasts"]) - len(successful_forecasts),
                "total_forecast_cost": total_forecast_cost,
                "average_forecast_cost": total_forecast_cost / len(successful_forecasts)
                if successful_forecasts
                else 0,
            }

        return results
