import numpy as np
import pandas as pd

from reaper.collectors.providers import azure_collector as _ac_module


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
        z = np.polyfit(df["users"].to_numpy(dtype=float), df["cost"].to_numpy(dtype=float), 1)

        marginal_cost = z[0]  # The derivative dC/du is constant 'm' in linear fit

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


class RegionalArbitrage:
    def __init__(self):
        # Top regions to compare against
        self.target_regions = [
            "eastus",
            "westeurope",
            "southindia",
            "brazilsouth",
            "westus2",
            "northeurope",
        ]

    def analyze_arbitrage(self, sku_id, current_region, current_price_hourly):
        """
        Scans other regions to find a cheaper deployment option using the high-performance Go engine.
        """
        collector = _ac_module.AzureCollector()

        # Use the Go engine for parallel fetching across all target regions
        arbitrage_data = collector.get_arbitrage_data(sku_id, self.target_regions)

        if "error" in arbitrage_data:
            return {
                "found_cheaper": False,
                "message": f"Arbitrage scan failed: {arbitrage_data['error']}",
            }

        cheapest_region = current_region
        cheapest_price = current_price_hourly

        for res in arbitrage_data.get("results", []):
            region = res.get("region")
            price = res.get("price", 0)
            if price > 0 and price < cheapest_price:
                cheapest_price = price
                cheapest_region = region

        if cheapest_region != current_region and cheapest_price < current_price_hourly:
            monthly_current = current_price_hourly * 730
            monthly_cheapest = cheapest_price * 730
            savings = monthly_current - monthly_cheapest
            pct_reduction = (savings / monthly_current) * 100

            return {
                "found_cheaper": True,
                "current_region": current_region,
                "cheaper_region": cheapest_region,
                "savings_monthly": round(savings, 2),
                "pct_reduction": round(pct_reduction, 1),
                "message": (
                    f"Deploying this {sku_id} in {cheapest_region} instead of "
                    f"{current_region} would save you "
                    f"${round(savings, 2)}/month ({round(pct_reduction, 1)}% reduction)."
                ),
            }

        return {
            "found_cheaper": False,
            "message": (
                f"Your current region {current_region} is already"
                " the most cost-effective among targets."
            ),
        }
