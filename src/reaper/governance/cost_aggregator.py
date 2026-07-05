"""
Multi-Cloud Cost Aggregation System

Unified billing view across all cloud providers with currency conversion,
cost normalization, and comprehensive financial reporting.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from reaper.utils.error_handler import get_logger

logger = get_logger(__name__)


@dataclass
class CurrencyRate:
    """Currency exchange rate information"""

    from_currency: str
    to_currency: str
    rate: float
    rate_date: datetime


@dataclass
class UnifiedCostRecord:
    """Unified cost record across providers"""

    provider: str
    resource_id: str
    resource_type: str
    region: str
    service_category: str
    original_currency: str
    original_amount: float
    base_currency: str
    converted_amount: float
    billing_period_start: datetime
    billing_period_end: datetime
    cost_type: str  # 'capex', 'opex', 'reservation'
    tags: dict


class MultiCloudCostAggregator:
    """
    Unified billing view across all cloud providers with currency conversion,
    cost normalization, and comprehensive financial reporting.
    """

    def __init__(self):
        """Initialize the cost aggregator with currency conversion support."""
        self.base_currency = "USD"
        self.currency_rates = self._load_currency_rates()
        self.cost_records = []

    def _load_currency_rates(self) -> dict[str, dict[str, CurrencyRate]]:
        """Load currency exchange rates (simplified for demo)."""
        # In production, this would call a currency API
        current_date = datetime.now()

        return {
            "EUR": {"USD": CurrencyRate("EUR", "USD", 1.08, current_date)},
            "GBP": {"USD": CurrencyRate("GBP", "USD", 1.27, current_date)},
            "JPY": {"USD": CurrencyRate("JPY", "USD", 0.0067, current_date)},
            "INR": {"USD": CurrencyRate("INR", "USD", 0.012, current_date)},
            "CAD": {"USD": CurrencyRate("CAD", "USD", 0.74, current_date)},
            "AUD": {"USD": CurrencyRate("AUD", "USD", 0.65, current_date)},
        }

    def convert_currency(self, amount: float, from_currency: str, to_currency: str = None) -> float:
        """
        Convert amount from one currency to another.

        Args:
            amount: Amount to convert
            from_currency: Source currency code
            to_currency: Target currency code (defaults to base currency)

        Returns:
            Converted amount
        """
        if to_currency is None:
            to_currency = self.base_currency

        if from_currency == to_currency:
            return amount

        if from_currency == self.base_currency:
            # Converting from base to target
            # Simplified: assume we have the reverse rate
            if to_currency in self.currency_rates:
                rate = self.currency_rates[to_currency].get(self.base_currency)
                if rate:
                    return amount / rate.rate
            return amount

        if to_currency == self.base_currency:
            # Converting to base currency
            if from_currency in self.currency_rates:
                rate = self.currency_rates[from_currency].get(to_currency)
                if rate:
                    return amount * rate.rate
            return amount

        # Cross-currency conversion (via base currency)
        base_amount = self.convert_currency(amount, from_currency, self.base_currency)
        return self.convert_currency(base_amount, self.base_currency, to_currency)

    def normalize_cost(
        self,
        provider: str,
        resource_id: str,
        resource_type: str,
        region: str,
        amount: float,
        currency: str,
        billing_period_start: datetime,
        billing_period_end: datetime,
        cost_type: str = "opex",
        tags: dict = None,
    ) -> UnifiedCostRecord:
        """
        Normalize cost data to unified format.

        Args:
            provider: Cloud provider ('azure', 'aws', 'gcp')
            resource_id: Resource identifier
            resource_type: Type of resource
            region: Cloud region
            amount: Cost amount in original currency
            currency: Original currency code
            billing_period_start: Start of billing period
            billing_period_end: End of billing period
            cost_type: Type of cost ('capex', 'opex', 'reservation')
            tags: Resource tags

        Returns:
            UnifiedCostRecord with converted amount
        """
        # Determine service category
        service_category = self._determine_service_category(resource_type)

        # Convert to base currency
        converted_amount = self.convert_currency(amount, currency, self.base_currency)

        return UnifiedCostRecord(
            provider=provider,
            resource_id=resource_id,
            resource_type=resource_type,
            region=region,
            service_category=service_category,
            original_currency=currency,
            original_amount=amount,
            base_currency=self.base_currency,
            converted_amount=converted_amount,
            billing_period_start=billing_period_start,
            billing_period_end=billing_period_end,
            cost_type=cost_type,
            tags=tags or {},
        )

    def _determine_service_category(self, resource_type: str) -> str:
        """Determine service category from resource type."""
        resource_type_lower = resource_type.lower()

        if any(
            keyword in resource_type_lower for keyword in ["vm", "instance", "compute", "container"]
        ):
            return "compute"
        if any(keyword in resource_type_lower for keyword in ["storage", "disk", "blob", "bucket"]):
            return "storage"
        if any(
            keyword in resource_type_lower
            for keyword in ["network", "vnet", "subnet", "firewall", "loadbalancer"]
        ):
            return "network"
        if any(keyword in resource_type_lower for keyword in ["database", "sql", "nosql", "db"]):
            return "database"
        if any(keyword in resource_type_lower for keyword in ["function", "lambda", "serverless"]):
            return "serverless"
        return "other"

    def aggregate_costs(
        self, cost_records: list[UnifiedCostRecord], group_by: str = "provider"
    ) -> dict[str, Any]:
        """
        Aggregate costs by specified dimension.

        Args:
            cost_records: List of unified cost records
            group_by: Dimension to group by ('provider', 'service', 'region', 'resource_type')

        Returns:
            Dictionary with aggregated costs
        """
        if not cost_records:
            return {"total_cost": 0.0, "currency": self.base_currency, "groups": []}

        groups = {}
        total_cost = 0.0

        for record in cost_records:
            # Determine group key
            if group_by == "provider":
                group_key = record.provider
            elif group_by == "service":
                group_key = record.service_category
            elif group_by == "region":
                group_key = record.region
            elif group_by == "resource_type":
                group_key = record.resource_type
            else:
                group_key = "other"

            if group_key not in groups:
                groups[group_key] = {"key": group_key, "cost": 0.0, "count": 0, "resources": []}

            groups[group_key]["cost"] += record.converted_amount
            groups[group_key]["count"] += 1
            groups[group_key]["resources"].append(
                {
                    "resource_id": record.resource_id,
                    "resource_type": record.resource_type,
                    "cost": record.converted_amount,
                }
            )

            total_cost += record.converted_amount

        # Convert to list and sort by cost
        group_list = list(groups.values())
        group_list.sort(key=lambda x: x["cost"], reverse=True)

        return {
            "total_cost": total_cost,
            "currency": self.base_currency,
            "group_by": group_by,
            "groups": group_list,
        }

    def get_cost_trends(
        self, cost_records: list[UnifiedCostRecord], period: str = "monthly"
    ) -> dict[str, Any]:
        """
        Analyze cost trends over time.

        Args:
            cost_records: List of unified cost records
            period: Time period for analysis ('daily', 'weekly', 'monthly')

        Returns:
            Dictionary with trend analysis
        """
        if not cost_records:
            return {"trend": "insufficient_data", "period": period, "data_points": []}

        # Group by time period
        time_groups = {}

        for record in cost_records:
            # Determine time key based on period
            if period == "daily":
                time_key = record.billing_period_start.strftime("%Y-%m-%d")
            elif period == "weekly":
                time_key = record.billing_period_start.strftime("%Y-W%U")
            else:  # monthly
                time_key = record.billing_period_start.strftime("%Y-%m")

            if time_key not in time_groups:
                time_groups[time_key] = {"period": time_key, "cost": 0.0, "count": 0}

            time_groups[time_key]["cost"] += record.converted_amount
            time_groups[time_key]["count"] += 1

        # Convert to sorted list
        trend_data = sorted(time_groups.values(), key=lambda x: x["period"])

        # Calculate trend direction
        if len(trend_data) >= 2:
            recent_cost = trend_data[-1]["cost"]
            previous_cost = trend_data[-2]["cost"]

            if recent_cost > previous_cost * 1.05:
                trend = "increasing"
            elif recent_cost < previous_cost * 0.95:
                trend = "decreasing"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        return {
            "trend": trend,
            "period": period,
            "currency": self.base_currency,
            "data_points": trend_data,
            "average_cost": sum(d["cost"] for d in trend_data) / len(trend_data)
            if trend_data
            else 0,
        }

    def generate_multi_cloud_report(
        self,
        cost_records: list[UnifiedCostRecord],
        report_period_start: datetime,
        report_period_end: datetime,
    ) -> dict[str, Any]:
        """
        Generate comprehensive multi-cloud cost report.

        Args:
            cost_records: List of unified cost records
            report_period_start: Start of report period
            report_period_end: End of report period

        Returns:
            Dictionary with comprehensive report data
        """
        # Filter records by period
        filtered_records = [
            r
            for r in cost_records
            if r.billing_period_start >= report_period_start
            and r.billing_period_end <= report_period_end
        ]

        # Generate various aggregations
        by_provider = self.aggregate_costs(filtered_records, "provider")
        by_service = self.aggregate_costs(filtered_records, "service")
        by_region = self.aggregate_costs(filtered_records, "region")
        by_cost_type = self._aggregate_by_cost_type(filtered_records)

        # Calculate trends
        trends = self.get_cost_trends(filtered_records, "monthly")

        # Calculate cost distribution
        total_cost = by_provider["total_cost"]
        cost_distribution = {
            group["key"]: {
                "cost": group["cost"],
                "percentage": (group["cost"] / total_cost * 100) if total_cost > 0 else 0,
            }
            for group in by_provider["groups"]
        }

        return {
            "report_period": {
                "start": report_period_start.isoformat(),
                "end": report_period_end.isoformat(),
            },
            "currency": self.base_currency,
            "summary": {
                "total_cost": total_cost,
                "total_resources": len(filtered_records),
                "unique_providers": len(set(r.provider for r in filtered_records)),
                "unique_regions": len(set(r.region for r in filtered_records)),
            },
            "by_provider": by_provider,
            "by_service": by_service,
            "by_region": by_region,
            "by_cost_type": by_cost_type,
            "cost_distribution": cost_distribution,
            "trends": trends,
            "generated_at": datetime.now().isoformat(),
        }

    def _aggregate_by_cost_type(self, cost_records: list[UnifiedCostRecord]) -> dict[str, Any]:
        """Aggregate costs by cost type (capex, opex, reservation)."""
        groups = {}

        for record in cost_records:
            cost_type = record.cost_type
            if cost_type not in groups:
                groups[cost_type] = {"cost_type": cost_type, "cost": 0.0, "count": 0}

            groups[cost_type]["cost"] += record.converted_amount
            groups[cost_type]["count"] += 1

        return {
            "total_cost": sum(g["cost"] for g in groups.values()),
            "currency": self.base_currency,
            "groups": list(groups.values()),
        }

    def compare_provider_costs(
        self, cost_records: list[UnifiedCostRecord], period_days: int = 30
    ) -> dict[str, Any]:
        """
        Compare costs between providers for a specified period.

        Args:
            cost_records: List of unified cost records
            period_days: Number of days to analyze

        Returns:
            Dictionary with provider cost comparison
        """
        # Filter records by period
        cutoff_date = datetime.now() - timedelta(days=period_days)
        filtered_records = [r for r in cost_records if r.billing_period_start >= cutoff_date]

        # Aggregate by provider
        provider_costs = {}
        for record in filtered_records:
            provider = record.provider
            if provider not in provider_costs:
                provider_costs[provider] = {"cost": 0.0, "count": 0, "services": set()}

            provider_costs[provider]["cost"] += record.converted_amount
            provider_costs[provider]["count"] += 1
            provider_costs[provider]["services"].add(record.service_category)

        # Convert to comparable format
        comparison = []
        for provider, data in provider_costs.items():
            comparison.append(
                {
                    "provider": provider,
                    "cost": data["cost"],
                    "resource_count": data["count"],
                    "service_count": len(data["services"]),
                    "average_cost_per_resource": data["cost"] / data["count"]
                    if data["count"] > 0
                    else 0,
                }
            )

        # Sort by cost
        comparison.sort(key=lambda x: x["cost"], reverse=True)

        return {
            "period_days": period_days,
            "currency": self.base_currency,
            "comparison": comparison,
            "most_expensive": comparison[0] if comparison else None,
            "least_expensive": comparison[-1] if comparison else None,
        }

    def forecast_costs(
        self, cost_records: list[UnifiedCostRecord], forecast_days: int = 30
    ) -> dict[str, Any]:
        """
        Forecast future costs based on historical data.

        Args:
            cost_records: List of unified cost records
            forecast_days: Number of days to forecast

        Returns:
            Dictionary with cost forecast
        """
        if not cost_records:
            return {
                "forecast_days": forecast_days,
                "currency": self.base_currency,
                "forecast_cost": 0.0,
                "method": "insufficient_data",
            }

        # Calculate daily average from recent data
        cutoff_date = datetime.now() - timedelta(days=30)
        recent_records = [r for r in cost_records if r.billing_period_start >= cutoff_date]

        if not recent_records:
            return {
                "forecast_days": forecast_days,
                "currency": self.base_currency,
                "forecast_cost": 0.0,
                "method": "insufficient_data",
            }

        # Calculate average daily cost
        total_cost = sum(r.converted_amount for r in recent_records)
        days_covered = (
            recent_records[-1].billing_period_end - recent_records[0].billing_period_start
        ).days or 1
        daily_average = total_cost / days_covered

        # Simple forecast (linear extrapolation)
        forecast_cost = daily_average * forecast_days

        return {
            "forecast_days": forecast_days,
            "currency": self.base_currency,
            "forecast_cost": forecast_cost,
            "daily_average": daily_average,
            "method": "linear_extrapolation",
            "confidence": "low",
        }
