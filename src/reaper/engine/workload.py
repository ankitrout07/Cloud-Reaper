import datetime
import json
import random

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.seasonal import seasonal_decompose


class WorkloadPersonality:
    """
    Analyzes the 'personality' of a workload by detecting periodic patterns.
    Moves beyond simple thresholding to understand cyclic behavior.
    """

    def __init__(self, period=24):
        self.period = period  # Default to 24 for daily cycle if data is hourly

    def analyze(self, metric_history):
        """
        metric_history: list of floats (e.g., CPU or Memory usage)
        """
        if len(metric_history) < self.period * 2:
            return {
                "personality": "Indeterminate",
                "reason": "Insufficient data for seasonal analysis",
            }

        try:
            # Perform seasonal decomposition
            result = seasonal_decompose(metric_history, model="additive", period=self.period)
            seasonal = result.seasonal
            trend = result.trend

            # Check for seasonality strength
            # Strength = Var(seasonal) / (Var(seasonal) + Var(residual))
            clean_seasonal = pd.Series(seasonal).dropna()
            clean_residual = pd.Series(result.resid).dropna()

            var_s = clean_seasonal.var()
            var_r = clean_residual.var()
            strength = var_s / (var_s + var_r) if (var_s + var_r) > 0 else 0

            personality = "Stable"
            if strength > 0.6:
                personality = "Cyclic/Periodic"
            elif var_r > var_s:
                personality = "Erratic/Bursty"

            # Detect "Monday Morning" type peaks
            # In a real app, we'd map timestamps to indices. 
            # Here we just look for high-magnitude seasonal components.
            peak_indices = np.where(seasonal == np.max(seasonal))[0]
            
            recommendation = "Maintain current tier."
            if personality == "Cyclic/Periodic":
                recommendation = "Recommend Burstable (B-Series) for cost-efficient burst handling."
            elif personality == "Erratic/Bursty":
                recommendation = "Recommend Compute-Optimized (F-Series) to handle unpredictable spikes."

            return {
                "personality": personality,
                "seasonality_strength": round(float(strength), 2),
                "trend_slope": "Increasing" if trend[-5] < trend[-1] else "Stable/Decreasing",
                "recommendation": recommendation,
                "peak_offset": int(peak_indices[0]) if len(peak_indices) > 0 else 0,
            }
        except Exception as e:
            return {"personality": "Unknown", "error": str(e)}


class PredictiveScalingEngine:
    """
    Forecasts future demand to allow for pre-emptive scaling (pre-warming).
    """

    def __init__(self, forecast_steps=15):
        self.forecast_steps = forecast_steps

    def predict_load(self, metric_history):
        """
        Predicts future load and recommends actions.
        """
        if len(metric_history) < 10:
            return {"action": "NONE", "reason": "Insufficient history"}

        try:
            # Use ARIMA for short-term forecasting
            model = ARIMA(metric_history, order=(1, 1, 0))
            model_fit = model.fit()
            forecast = model_fit.forecast(steps=self.forecast_steps)
            
            latest_val = metric_history[-1]
            peak_forecast = max(forecast)
            
            action = "STAY"
            if peak_forecast > 85:
                action = "PRE_WARM"
            elif peak_forecast < 20 and latest_val < 30:
                action = "SCALE_DOWN"

            return {
                "current_load": round(float(latest_val), 1),
                "predicted_peak": round(float(peak_forecast), 1),
                "forecast_window_min": self.forecast_steps,
                "action": action,
                "reason": f"Forecasted peak of {peak_forecast:.1f}% exceeds threshold." if action == "PRE_WARM" else "Load within safe bounds."
            }
        except Exception:
            return {"action": "ERROR", "reason": "Forecasting failed"}


class SpotAdvisor:
    """
    Predicts Spot Instance interruption probability and recommends safer regions.
    """

    def __init__(self):
        # Mock volatility data by region and SKU family
        self.volatility_map = {
            "eastus": {"D": 0.1, "E": 0.2, "F": 0.15},
            "westus2": {"D": 0.15, "E": 0.25, "F": 0.2},
            "southindia": {"D": 0.3, "E": 0.4, "F": 0.35},
            "brazilsouth": {"D": 0.4, "E": 0.5, "F": 0.45},
        }

    def get_interruption_risk(self, sku_id, region):
        """
        Calculates interruption risk percentage.
        """
        region = region.lower().replace(" ", "")
        sku_family = sku_id.split("_")[1][0].upper() if "_" in sku_id else "D"
        
        base_risk = self.volatility_map.get(region, {}).get(sku_family, 0.2)
        
        # Add random "market noise"
        noise = random.uniform(-0.05, 0.05)
        final_risk = min(max(base_risk + noise, 0.05), 0.95)
        
        status = "LOW"
        if final_risk > 0.4:
            status = "CRITICAL"
        elif final_risk > 0.2:
            status = "MEDIUM"

        return {
            "sku": sku_id,
            "region": region,
            "interruption_probability": f"{round(final_risk * 100)}%",
            "risk_status": status,
            "recommendation": "Safe for Dev/Test" if status == "LOW" else "Move to Pay-As-You-Go or more stable region (e.g., eastus)"
        }


if __name__ == "__main__":
    # Demo/Verification
    print("--- 🧠 CLOUD-REAPER INTELLIGENT WORKLOAD ANALYSIS ---")
    
    # 1. Pattern-Aware Scaling Demo
    print("\n[1] Testing Workload Personality...")
    # Synthetic daily pattern with a spike
    base = [10] * 24
    base[8:11] = [80, 85, 75]  # Morning burst
    history = base * 7  # 1 week of data
    
    analyzer = WorkloadPersonality(period=24)
    personality = analyzer.analyze(history)
    print(json.dumps(personality, indent=2))
    
    # 2. Predictive Scaling Demo
    print("\n[2] Testing Predictive Scaling...")
    linear_trend = [20, 22, 25, 30, 38, 45, 55, 68, 75, 82] # Rapidly increasing load
    scaler = PredictiveScalingEngine(forecast_steps=10)
    prediction = scaler.predict_load(linear_trend)
    print(json.dumps(prediction, indent=2))
    
    # 3. Spot Advisor Demo
    print("\n[3] Testing Spot Advisor...")
    advisor = SpotAdvisor()
    risk = advisor.get_interruption_risk("Standard_F4s_v2", "southindia")
    print(json.dumps(risk, indent=2))
