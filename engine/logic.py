import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from statsmodels.tsa.arima.model import ARIMA
import os
import json
import requests
import datetime

def notify_discord(message):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return
    try:
        requests.post(webhook_url, json={"content": message})
    except Exception as e:
        print(f"[-] Discord Notification Failed: {e}")

class ZombieScorer:
    def __init__(self):
        self.threshold = 90

    def score_resource(self, resource_data):
        """
        resource_data: {id, name, type, is_unattached, iops_history}
        """
        score = 0
        reasons = []

        # Rule 1: Attachment Status
        if resource_data.get('is_unattached'):
            score += 50
            reasons.append("Resource is unattached/orphaned (+50)")

        # Rule 2: IOPS History (Last 7 days)
        iops = resource_data.get('iops_history', [])
        if iops and len(iops) >= 7:
            if all(v < 10 for v in iops[-7:]):
                score += 45 # Slightly more than 40 to trigger the >90 with unattached
                reasons.append("Near-zero IOPS for 7 consecutive days (+45)")
        elif resource_data.get('disk_iops', 0) < 5:
            # Fallback for single point
            score += 20
            reasons.append("Current IOPS is negligible (+20)")

        is_zombie = score >= self.threshold
        
        if is_zombie:
            msg = f"🚨 **ZOMBIE DETECTED** 🚨\nResource: `{resource_data['name']}`\nType: `{resource_data['type']}`\nScore: `{score}`\nReasons: {', '.join(reasons)}"
            notify_discord(msg)

        return {
            'is_zombie': is_zombie,
            'score': score,
            'reasons': reasons
        }

class BudgetForecaster:
    def __init__(self):
        pass

    def forecast_eom(self, daily_spend_history, days_to_predict=30):
        """
        daily_spend_history: list of floats (daily costs)
        """
        if len(daily_spend_history) < 5:
            # Not enough data for ARIMA, use linear trend
            return self._linear_fallback(daily_spend_history, days_to_predict)

        try:
            # ARIMA(1,1,1) is a good starting point for cost trends
            model = ARIMA(daily_spend_history, order=(1, 1, 1))
            model_fit = model.fit()
            forecast = model_fit.forecast(steps=days_to_predict)
            
            projected_total = sum(daily_spend_history) + sum(forecast)
            return {
                'projected_eom': round(projected_total, 2),
                'forecast_points': [round(float(x), 2) for x in forecast],
                'confidence': 'high' if len(daily_spend_history) > 14 else 'medium'
            }
        except Exception:
            return self._linear_fallback(daily_spend_history, days_to_predict)

    def _linear_fallback(self, history, days):
        avg = sum(history) / len(history) if history else 0
        forecast = [avg] * days
        return {
            'projected_eom': round(sum(history) + (avg * days), 2),
            'forecast_points': forecast,
            'confidence': 'low'
        }

class RightSizer:
    def __init__(self, price_book=None):
        self.price_book = price_book or {}
        # Basic mapping of SKU families to relative performance weights
        self.performance_map = {
            'b': 0.5,  # Burstable
            'd': 1.0,  # General Purpose
            'e': 1.2,  # Memory Optimized
            'f': 1.5,  # Compute Optimized
        }

    def _get_perf_score(self, sku_name):
        """Estimate performance score based on SKU name."""
        sku_lower = sku_name.lower()
        base_score = 1.0
        for family, weight in self.performance_map.items():
            if sku_lower.startswith(f"standard_{family}"):
                base_score = weight
                break
        
        # Extract vCPU-ish number from SKU (e.g., D2s_v3 -> 2)
        import re
        match = re.search(r'(\d+)', sku_name)
        vcpus = int(match.group(1)) if match else 1
        
        return base_score * vcpus

    def calculate_recommendation(self, vm_data):
        """
        vm_data: list of dicts with {name, current_size, cpu_usage_history}
        cpu_usage_history is a list of percentage floats.
        """
        recommendations = []
        
        for vm in vm_data:
            usage = vm.get('usage_history', [vm.get('usage', 0)])
            if not usage:
                continue
                
            # Create a simple regression to see the trend/stability
            X = np.array(range(len(usage))).reshape(-1, 1)
            y = np.array(usage)
            
            model = LinearRegression()
            model.fit(X, y)
            
            # Predict "Safe Peak" (Mean + 2*Std or similar heuristic from regression)
            predicted_mean = model.predict([[len(usage)]])[0]
            max_usage = max(usage)
            safe_target = max(predicted_mean, max_usage) * 1.2 # 20% buffer
            
            current_perf = self._get_perf_score(vm['size'])
            required_perf = (safe_target / 100.0) * current_perf
            
            # Find better SKU
            # For simplicity, we suggest a smaller version of the same family if usage is low
            recommended_size = vm['size']
            potential_saving = 0
            
            if safe_target < 30: # Heavily underutilized
                # Try to find a smaller SKU (e.g., D4 -> D2 -> B2)
                if "_4" in vm['size']:
                    recommended_size = vm['size'].replace("_4", "_2")
                elif "_2" in vm['size']:
                    recommended_size = "Standard_B2s" # Extreme downsize
                
            # Calculate Savings (Mock calculation if price book is empty)
            # In a real app, we'd lookup prices for both sizes
            if recommended_size != vm['size']:
                potential_saving = 25.0 # Mock $25/mo saving
                
            recommendations.append({
                'vm_name': vm['name'],
                'current_size': vm['size'],
                'recommended_size': recommended_size,
                'confidence': 0.85,
                'monthly_saving': potential_saving,
                'reason': f"Peak CPU at {max_usage:.1f}% indicates over-provisioning."
            })
            
        return recommendations

if __name__ == "__main__":
    # Test Logic
    rs = RightSizer()
    test_vms = [
        {'name': 'web-server-01', 'size': 'Standard_D4s_v3', 'usage_history': [10, 12, 8, 15, 11, 9]},
        {'name': 'db-prod-01', 'size': 'Standard_D2s_v3', 'usage_history': [80, 85, 75, 90, 88]}
    ]
    print(json.dumps(rs.calculate_recommendation(test_vms), indent=2))
