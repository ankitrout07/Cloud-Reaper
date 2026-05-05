import numpy as np
import pandas as pd


class BusinessCorrelation:
    def __init__(self, db_connection=None):
        self.db = db_connection

    def get_unit_economics(self, cost_history, user_history):
        """
        Calculates Marginal Revenue vs Marginal Cost (MR=MC).
        cost_history: list of daily infrastructure costs
        user_history: list of daily active users
        """
        if len(cost_history) < 7 or len(user_history) < 7:
            return {"error": "Insufficient data for correlation"}

        df = pd.DataFrame({"cost": cost_history, "users": user_history})

        # Calculate Cost per User
        df["cpu"] = df["cost"] / df["users"]

        # Simple Linear Regression to find the cost function C(u)
        # C = m*u + b
        z = np.polyfit(df["users"], df["cost"], 1)
        np.poly1d(z)

        marginal_cost = z[0]  # The derivative dC/du is constant 'm' in linear fit

        user_history[-1]
        cost_history[-1]

        # Identify if we are in "Efficiency Zone"
        # If marginal cost < revenue per user (let's assume $0.50 ARPU for now)
        arpu = 0.50
        is_efficient = marginal_cost < arpu

        return {
            "marginal_cost": round(float(marginal_cost), 4),
            "cost_per_user": round(float(df["cpu"].iloc[-1]), 4),
            "is_efficient": is_efficient,
            "break_even_users": round(float(-z[1] / z[0])) if z[0] != 0 else 0,
            "slope": "increasing" if z[0] > 0 else "decreasing",
        }


class ProportionalAllocator:
    def __init__(self):
        pass

    def attribute_shared_costs(self, shared_cost, usage_map):
        """
        Formula: Cost_Team = (Usage_Team / Usage_Total) * Cost_Shared
        usage_map: { 'team_a': 500, 'team_b': 300, ... } (Network Out in GB)
        """
        total_usage = sum(usage_map.values())
        if total_usage == 0:
            return dict.fromkeys(usage_map, 0)

        allocations = {}
        for team, usage in usage_map.items():
            percentage = usage / total_usage
            allocations[team] = {
                "allocated_cost": round(percentage * shared_cost, 2),
                "usage_percentage": round(percentage * 100, 2),
            }

        return allocations
