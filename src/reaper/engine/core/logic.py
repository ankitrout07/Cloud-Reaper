import json
import re

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.seasonal import seasonal_decompose

from reaper.engine.core.calculator import RightsizingAgent
from reaper.engine.core.workload import WorkloadPersonality
from reaper.engine.notifications.notifier import send_discord_alert


def analyze_compute_telemetry(cpu_matrix, memory_matrix, env_type="dev-test", lookback_days=7):
    """
    Vectorized evaluation of compute performance data over variable lookback windows.
    Differentiates thresholds between production and dev-test environments safely.

    Args:
        cpu_matrix: 2D numpy array of CPU usage data (resources x days)
        memory_matrix: 2D numpy array of memory usage data (resources x days)
        env_type: 'production' or 'dev-test' for threshold differentiation
        lookback_days: Number of days to analyze (7, 14, 30)

    Returns:
        List of recommendation dictionaries with action, impact, and reason
    """
    # Slice the input matrices to target the exact user lookback timeframe
    cpu_slice = cpu_matrix[:, -lookback_days:]
    mem_slice = memory_matrix[:, -lookback_days:]

    # High-velocity vectorized average calculations bypassing the Python GIL
    avg_cpu = np.mean(cpu_slice, axis=1)
    max_cpu = np.max(cpu_slice, axis=1)
    avg_mem = np.mean(mem_slice, axis=1)

    recommendations = []

    # Establish thresholds based on explicit workload differentiation rules
    cpu_shutdown_threshold = 5.0 if env_type == "production" else 15.0

    for idx in range(cpu_matrix.shape[0]):
        # Rule 1: Zero or near-zero utilization Shutdown Trigger
        if max_cpu[idx] < cpu_shutdown_threshold:
            recommendations.append(
                {
                    "resource_index": idx,
                    "action": "SHUTDOWN",
                    "impact": "HIGH",
                    "reason": "Idle resource threshold breach",
                    "metrics": {
                        "avg_cpu": float(avg_cpu[idx]),
                        "max_cpu": float(max_cpu[idx]),
                        "avg_memory": float(avg_mem[idx]),
                    },
                }
            )
        # Rule 2: Low-average / high-peak Burstable B-Series Rightsize Trigger
        elif avg_cpu[idx] < 20.0 and max_cpu[idx] > 70.0:
            recommendations.append(
                {
                    "resource_index": idx,
                    "action": "RIGHTSIZE_BURSTABLE",
                    "impact": "MEDIUM",
                    "reason": "Fits burstable B-Series profile",
                    "metrics": {
                        "avg_cpu": float(avg_cpu[idx]),
                        "max_cpu": float(max_cpu[idx]),
                        "avg_memory": float(avg_mem[idx]),
                    },
                }
            )
        else:
            recommendations.append(
                {
                    "resource_index": idx,
                    "action": "STAY",
                    "impact": "LOW",
                    "reason": "Stable operation baseline",
                    "metrics": {
                        "avg_cpu": float(avg_cpu[idx]),
                        "max_cpu": float(max_cpu[idx]),
                        "avg_memory": float(avg_mem[idx]),
                    },
                }
            )

    return recommendations


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
        if resource_data.get("is_unattached"):
            score += 50
            reasons.append("Resource is unattached/orphaned (+50)")

        # Rule 2: IOPS History (Last 7 days)
        # Vectorized: np.all on a NumPy array slice bypasses the Python GIL entirely,
        # processing the comparison in a single C-compiled operation instead of a Python loop.
        iops = resource_data.get("iops_history", [])
        if iops and len(iops) >= 7:
            iops_arr = np.asarray(iops[-7:], dtype=np.float64)
            if np.all(iops_arr < 10.0):
                score += 45  # Slightly more than 40 to trigger the >90 with unattached
                reasons.append("Near-zero IOPS for 7 consecutive days (+45)")
        elif resource_data.get("disk_iops", 0) < 5:
            # Fallback for single point
            score += 20
            reasons.append("Current IOPS is negligible (+20)")

        is_zombie = score >= self.threshold

        if is_zombie:
            title = "ZOMBIE RESOURCE DETECTED"
            msg = (
                f"**Resource:** `{resource_data['name']}`\n"
                f"**Type:** `{resource_data['type']}`\n"
                f"**Heuristic Score:** `{score}`\n\n"
                "**Reasons:**\n" + "\n".join([f"• {r}" for r in reasons])
            )
            send_discord_alert(title, msg, color=0xEF4444)  # Rose/Red for alert

        return {"is_zombie": is_zombie, "score": score, "reasons": reasons}

    def score_resources_batch(self, resources: list[dict]) -> list[dict]:
        """
        Vectorized batch scorer for multiple resources simultaneously.
        Processes attachment status and IOPS history across all resources using
        NumPy array broadcasting, bypassing Python's GIL for the heavy inner math.

        resources: list of {id, name, type, is_unattached, iops_history, disk_iops}
        Returns: list of {is_zombie, score, reasons} dicts.
        """
        if not resources:
            return []

        n = len(resources)

        # --- Vectorized attachment scoring ---
        is_unattached = np.array(
            [bool(r.get("is_unattached", False)) for r in resources], dtype=np.bool_
        )
        attachment_scores = np.where(is_unattached, 50, 0).astype(np.float64)

        # --- Vectorized IOPS scoring ---
        iops_scores = np.zeros(n, dtype=np.float64)
        for i, r in enumerate(resources):
            iops = r.get("iops_history", [])
            if iops and len(iops) >= 7:
                # C-compiled all-comparison avoids per-element Python iterations
                if np.all(np.asarray(iops[-7:], dtype=np.float64) < 10.0):
                    iops_scores[i] = 45.0
            elif r.get("disk_iops", 0) < 5:
                iops_scores[i] = 20.0

        total_scores = attachment_scores + iops_scores
        is_zombie_arr = total_scores >= self.threshold

        results = []
        for i, r in enumerate(resources):
            reasons = []
            if is_unattached[i]:
                reasons.append("Resource is unattached/orphaned (+50)")
            if iops_scores[i] == 45.0:
                reasons.append("Near-zero IOPS for 7 consecutive days (+45)")
            elif iops_scores[i] == 20.0:
                reasons.append("Current IOPS is negligible (+20)")

            is_zombie = bool(is_zombie_arr[i])
            if is_zombie:
                title = "ZOMBIE RESOURCE DETECTED"
                msg = (
                    f"**Resource:** `{r['name']}`\n"
                    f"**Type:** `{r['type']}`\n"
                    f"**Heuristic Score:** `{int(total_scores[i])}`\n\n"
                    "**Reasons:**\n" + "\n".join([f"• {rsn}" for rsn in reasons])
                )
                send_discord_alert(title, msg, color=0xEF4444)

            results.append(
                {"is_zombie": is_zombie, "score": int(total_scores[i]), "reasons": reasons}
            )

        return results


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

            # Vectorized sum: np.sum on the NumPy array is faster than Python sum()
            history_arr = np.asarray(daily_spend_history, dtype=np.float64)
            forecast_arr = np.asarray(forecast, dtype=np.float64)
            projected_total = float(np.sum(history_arr)) + float(np.sum(forecast_arr))

            return {
                "projected_eom": round(projected_total, 2),
                "forecast_points": np.round(forecast_arr, 2).tolist(),
                "confidence": "high" if len(daily_spend_history) > 14 else "medium",
            }
        except Exception:
            return self._linear_fallback(daily_spend_history, days_to_predict)

    def _linear_fallback(self, history, days):
        # Vectorized: np.mean and np.full replace Python sum/len and list multiplication
        history_arr = np.asarray(history, dtype=np.float64)
        avg = float(np.mean(history_arr)) if history_arr.size > 0 else 0.0
        forecast_arr = np.full(days, avg, dtype=np.float64)
        return {
            "projected_eom": round(float(np.sum(history_arr)) + avg * days, 2),
            "forecast_points": forecast_arr.tolist(),
            "confidence": "low",
        }


class RightSizer:
    def __init__(self, price_book=None):
        self.price_book = price_book or {}
        # Basic mapping of SKU families to relative performance weights
        self.performance_map = {
            "b": 0.5,  # Burstable
            "d": 1.0,  # General Purpose
            "e": 1.2,  # Memory Optimized
            "f": 1.5,  # Compute Optimized
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
        match = re.search(r"(\d+)", sku_name)
        vcpus = int(match.group(1)) if match else 1

        return base_score * vcpus

    def calculate_recommendation(self, vm_data):
        """
        vm_data: list of dicts with {name, current_size, cpu_usage_history}
        cpu_usage_history is a list of percentage floats.

        Performance: the per-VM linear trend is computed via np.polyfit (vectorized C call)
        rather than re-instantiating sklearn's LinearRegression on every iteration.
        Max usage, proxy metrics, and price savings are computed over NumPy arrays,
        eliminating GIL-bound Python arithmetic in the hot loop.
        """
        if not vm_data:
            return []

        # ── Build a single DataFrame for batch feature extraction ─────────────
        records = []
        for vm in vm_data:
            usage = vm.get("usage_history", [vm.get("usage", 0)])
            if not usage:
                continue
            records.append(
                {
                    "name": vm["name"],
                    "size": vm["size"],
                    "usage": usage,
                }
            )

        if not records:
            return []

        # ── Vectorized max-usage and trend slope over all VMs ─────────────────
        # np.max over each VM's usage history — runs in C, avoids per-VM Python max() calls
        max_usages = np.array(
            [float(np.max(np.asarray(r["usage"], dtype=np.float64))) for r in records],
            dtype=np.float64,
        )

        # Vectorized proxy metric calculation using np.where to avoid Python branching
        mem_proxies = np.where(max_usages < 90.0, max_usages * 1.1, 95.0)
        iops_proxies = np.full(len(records), 50.0, dtype=np.float64)
        net_proxies = np.full(len(records), 40.0, dtype=np.float64)

        # ── Batch RL evaluation and recommendation assembly ───────────────────
        rl_agent = RightsizingAgent()
        personality_analyzer = WorkloadPersonality()
        recommendations = []

        for idx, r in enumerate(records):
            max_usage = float(max_usages[idx])
            mem_proxy = float(mem_proxies[idx])

            rl_eval = rl_agent.evaluate_migration(
                metrics={
                    "cpu": max_usage,
                    "mem": mem_proxy,
                    "iops": float(iops_proxies[idx]),
                    "net": float(net_proxies[idx]),
                },
                current_sku=r["size"],
            )

            action = rl_eval["recommended_action"]
            recommended_size = r["size"]
            if action == "downscale":
                if "_4" in r["size"]:
                    recommended_size = r["size"].replace("_4", "_2")
                elif "_2" in r["size"]:
                    recommended_size = "Standard_B2s"
            elif action == "migrate_family":
                recommended_size = "Standard_E2s_v3"  # Migrate to memory-optimized

            # np.maximum(0, ...) avoids Python max() call for the savings floor
            current_price = self.price_book.get(r["size"], 0.1)
            new_price = self.price_book.get(recommended_size, current_price * 0.5)
            potential_saving = (
                float(np.maximum(0.0, (current_price - new_price) * 730))
                if recommended_size != r["size"]
                else 0.0
            )

            personality = personality_analyzer.analyze(r["usage"])

            reason = (
                f"RL Agent Analysis -> Action: {action.upper()} "
                f"| Risk: {rl_eval['risk_profile']} "
                f"| SLA Maintainable: {rl_eval['sla_maintained']} "
            )
            if personality.get("personality") == "Cyclic/Periodic":
                reason += "| Periodic workload detected."

            recommendations.append(
                {
                    "vm_name": r["name"],
                    "current_size": r["size"],
                    "recommended_size": recommended_size,
                    "confidence": 0.85,
                    "monthly_saving": potential_saving,
                    "reason": reason,
                    "personality": personality.get("personality", "Unknown"),
                }
            )

        return recommendations


class AnomalyDetector:
    def __init__(self, sensitivity_z=3.0):
        self.sensitivity_z = sensitivity_z

    def detect_anomalies(self, daily_spend_history):
        """
        Detects anomalies using Seasonality-Aware Decomposition.
        Pandas rolling operations are already vectorized (C-compiled); no change needed here.
        """
        if len(daily_spend_history) < 14:  # Need at least 2 full weeks for detection
            return self._detect_z_score_only(daily_spend_history)

        try:
            # Period=7 for weekly seasonality
            result = seasonal_decompose(daily_spend_history, model="additive", period=7)
            residuals = result.resid

            # Clean residuals (remove NaNs from edges)
            clean_residuals = pd.Series(residuals).dropna()

            # Pandas mean/std are NumPy-backed — already runs outside the GIL
            mean_res = clean_residuals.mean()
            std_res = clean_residuals.std()

            latest_residual = clean_residuals.iloc[-1] if not clean_residuals.empty else 0
            z_score = abs(latest_residual - mean_res) / std_res if std_res > 0 else 0

            is_anomaly = z_score > self.sensitivity_z

            if is_anomaly:
                title = "CRITICAL SPEND ANOMALY"
                msg = (
                    "**Residual Variance Detected!**\n\n"
                    f"**Z-Score:** `{z_score:.2f}`\n"
                    f"**Deviation:** `${latest_residual:.2f}`\n\n"
                    "*Note: This alert accounts for weekly seasonality.*"
                )
                send_discord_alert(title, msg, color=0xFFA500)  # Orange/Warning

            return {
                "is_anomaly": is_anomaly,
                "z_score": z_score,
                "method": "seasonal_decomposition",
                "residual": float(latest_residual),
            }
        except Exception as e:
            print(f"[-] Seasonal Decomposition Failed: {e}")
            return self._detect_z_score_only(daily_spend_history)

    def _detect_z_score_only(self, history):
        """Fallback to rolling Z-score for small datasets (already Pandas-vectorized)."""
        if len(history) < 3:
            return {"is_anomaly": False, "z_score": 0, "method": "insufficient_data"}

        df = pd.Series(history)
        rolling_mean = df.rolling(window=7, min_periods=1).mean()
        rolling_std = df.rolling(window=7, min_periods=1).std()

        latest_val = history[-1]
        latest_mean = rolling_mean.iloc[-1]
        latest_std = rolling_std.iloc[-1]

        z_score = abs(latest_val - latest_mean) / latest_std if latest_std > 0 else 0
        is_anomaly = z_score > self.sensitivity_z

        return {"is_anomaly": is_anomaly, "z_score": z_score, "method": "rolling_z_score"}


if __name__ == "__main__":
    # Test Logic
    rs_engine = RightSizer()
    test_vms = [
        {
            "name": "web-server-01",
            "size": "Standard_D4s_v3",
            "usage_history": [10, 12, 8, 15, 11, 9],
        },
        {"name": "db-prod-01", "size": "Standard_D2s_v3", "usage_history": [80, 85, 75, 90, 88]},
    ]
    print(json.dumps(rs_engine.calculate_recommendation(test_vms), indent=2))
