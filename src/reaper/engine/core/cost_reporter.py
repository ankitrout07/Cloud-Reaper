"""
Automated Cost Saving Report Generator

This module provides comprehensive reporting capabilities for cost optimization:
- Daily/weekly/monthly automated reports
- Trend analysis and cost savings tracking
- Implementation progress tracking
- Executive summary generation
- Multi-cloud cost comparison reports
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ReportPeriod(Enum):
    """Reporting time periods"""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class ReportFormat(Enum):
    """Report output formats"""

    JSON = "json"
    PDF = "pdf"
    HTML = "html"
    MARKDOWN = "markdown"
    CSV = "csv"


@dataclass
class CostSavingImpact:
    """Track the impact of implemented cost saving measures"""

    recommendation_id: str
    implemented_date: datetime
    original_monthly_cost: float
    new_monthly_cost: float
    monthly_savings: float
    implementation_status: str  # "planned", "in_progress", "completed", "failed"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "implemented_date": self.implemented_date.isoformat(),
            "original_monthly_cost": self.original_monthly_cost,
            "new_monthly_cost": self.new_monthly_cost,
            "monthly_savings": self.monthly_savings,
            "savings_percentage": (self.monthly_savings / self.original_monthly_cost * 100)
            if self.original_monthly_cost > 0
            else 0,
            "implementation_status": self.implementation_status,
            "notes": self.notes,
        }


@dataclass
class CostTrend:
    """Cost trend data for analysis"""

    period: str
    total_cost: float
    optimized_cost: float
    savings: float
    resource_count: int
    recommendations_count: int
    implemented_recommendations: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "total_cost": self.total_cost,
            "optimized_cost": self.optimized_cost,
            "savings": self.savings,
            "savings_percentage": (self.savings / self.total_cost * 100)
            if self.total_cost > 0
            else 0,
            "resource_count": self.resource_count,
            "recommendations_count": self.recommendations_count,
            "implemented_recommendations": self.implemented_recommendations,
        }


class AutomatedCostReporter:
    """
    Generate automated cost saving reports and track optimization progress.
    """

    def __init__(self):
        self.saving_impacts: list[CostSavingImpact] = []
        self.cost_trends: list[CostTrend] = []
        self.recommendations_history: list[dict[str, Any]] = []

    def generate_executive_summary(
        self, period: ReportPeriod = ReportPeriod.MONTHLY, provider: str = "azure"
    ) -> dict[str, Any]:
        """Generate executive summary for cost optimization efforts"""

        total_potential_savings = sum(
            rec.get("estimated_monthly_savings", 0) for rec in self.recommendations_history
        )

        total_implemented_savings = sum(
            impact.monthly_savings
            for impact in self.saving_impacts
            if impact.implementation_status == "completed"
        )

        implementation_rate = (
            (
                len([i for i in self.saving_impacts if i.implementation_status == "completed"])
                / len(self.saving_impacts)
                if self.saving_impacts
                else 0
            )
            if self.saving_impacts
            else 0
        )

        # Category breakdown
        category_savings = {}
        for rec in self.recommendations_history:
            cat = rec.get("category", "unknown")
            if cat not in category_savings:
                category_savings[cat] = 0
            category_savings[cat] += rec.get("estimated_monthly_savings", 0)

        # Priority breakdown
        priority_breakdown = {
            "critical": len(
                [r for r in self.recommendations_history if r.get("priority") == "critical"]
            ),
            "high": len([r for r in self.recommendations_history if r.get("priority") == "high"]),
            "medium": len(
                [r for r in self.recommendations_history if r.get("priority") == "medium"]
            ),
            "low": len([r for r in self.recommendations_history if r.get("priority") == "low"]),
        }

        return {
            "report_period": period.value,
            "provider": provider,
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "total_potential_savings": total_potential_savings,
                "total_implemented_savings": total_implemented_savings,
                "savings_realization_rate": implementation_rate * 100 if implementation_rate else 0,
                "total_recommendations": len(self.recommendations_history),
                "category_savings": category_savings,
                "priority_breakdown": priority_breakdown,
            },
            "trends": self._generate_trend_analysis(),
            "top_opportunities": self._get_top_opportunities(limit=5),
            "implementation_progress": self._get_implementation_progress(),
        }

    def _generate_trend_analysis(self) -> dict[str, Any]:
        """Generate cost trend analysis"""
        if len(self.cost_trends) < 2:
            return {"message": "Insufficient data for trend analysis"}

        recent_trends = self.cost_trends[-6:]  # Last 6 periods

        # Calculate trend direction
        if len(recent_trends) >= 2:
            latest = recent_trends[-1]
            previous = recent_trends[0]

            cost_change = latest.total_cost - previous.total_cost
            savings_change = latest.savings - previous.savings

            trend_direction = "stable"
            if cost_change < -100:  # Significant cost reduction
                trend_direction = "decreasing"
            elif cost_change > 100:
                trend_direction = "increasing"

        return {
            "trend_direction": trend_direction,
            "cost_change": cost_change if "cost_change" in locals() else 0,
            "savings_change": savings_change if "savings_change" in locals() else 0,
            "periods_analyzed": len(recent_trends),
            "trends": [trend.to_dict() for trend in recent_trends],
        }

    def _get_top_opportunities(self, limit: int = 5) -> list[dict[str, Any]]:
        """Get top cost saving opportunities by potential savings"""
        sorted_recs = sorted(
            self.recommendations_history,
            key=lambda x: x.get("estimated_monthly_savings", 0),
            reverse=True,
        )
        return sorted_recs[:limit]

    def _get_implementation_progress(self) -> dict[str, Any]:
        """Get implementation progress across all recommendations"""
        total = len(self.recommendations_history)
        if total == 0:
            return {"message": "No recommendations available"}

        status_counts = {
            "planned": len(
                [r for r in self.recommendations_history if r.get("status") == "planned"]
            ),
            "in_progress": len(
                [r for r in self.recommendations_history if r.get("status") == "in_progress"]
            ),
            "completed": len(
                [r for r in self.recommendations_history if r.get("status") == "completed"]
            ),
            "failed": len([r for r in self.recommendations_history if r.get("status") == "failed"]),
        }

        return {
            "total_recommendations": total,
            "status_breakdown": status_counts,
            "completion_percentage": (status_counts["completed"] / total * 100) if total > 0 else 0,
        }

    def generate_detailed_report(
        self,
        period: ReportPeriod = ReportPeriod.MONTHLY,
        provider: str = "azure",
        format: ReportFormat = ReportFormat.JSON,
    ) -> str:
        """Generate detailed cost optimization report"""
        executive_summary = self.generate_executive_summary(period, provider)

        detailed_report = {
            "executive_summary": executive_summary,
            "detailed_recommendations": self.recommendations_history,
            "implementation_tracking": [impact.to_dict() for impact in self.saving_impacts],
            "cost_trends": [trend.to_dict() for trend in self.cost_trends],
            "resource_optimization_details": self._generate_resource_details(),
            "category_analysis": self._generate_category_analysis(),
            "risk_assessment": self._generate_risk_assessment(),
            "next_steps": self._generate_next_steps(),
        }

        if format == ReportFormat.JSON:
            return json.dumps(detailed_report, indent=2)
        if format == ReportFormat.MARKDOWN:
            return self._convert_to_markdown(detailed_report)
        if format == ReportFormat.HTML:
            return self._convert_to_html(detailed_report)
        if format == ReportFormat.CSV:
            return self._convert_to_csv(detailed_report)
        return json.dumps(detailed_report, indent=2)

    def _generate_resource_details(self) -> dict[str, Any]:
        """Generate detailed resource-level optimization details"""
        resource_summary = {}

        for rec in self.recommendations_history:
            resource_id = rec.get("resource_id")
            resource_name = rec.get("resource_name")
            resource_type = rec.get("resource_type")

            if resource_id not in resource_summary:
                resource_summary[resource_id] = {
                    "resource_id": resource_id,
                    "resource_name": resource_name,
                    "resource_type": resource_type,
                    "recommendations": [],
                    "total_potential_savings": 0,
                }

            resource_summary[resource_id]["recommendations"].append(rec)
            resource_summary[resource_id]["total_potential_savings"] += rec.get(
                "estimated_monthly_savings", 0
            )

        return resource_summary

    def _generate_category_analysis(self) -> dict[str, Any]:
        """Generate category-wise cost optimization analysis"""
        category_analysis = {}

        for rec in self.recommendations_history:
            category = rec.get("category", "unknown")

            if category not in category_analysis:
                category_analysis[category] = {
                    "recommendation_count": 0,
                    "total_potential_savings": 0,
                    "average_savings_per_recommendation": 0,
                    "priority_distribution": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                    "risk_distribution": {"safe": 0, "low": 0, "medium": 0, "high": 0},
                    "implementation_effort_distribution": {"low": 0, "medium": 0, "high": 0},
                }

            cat_analysis = category_analysis[category]
            cat_analysis["recommendation_count"] += 1
            cat_analysis["total_potential_savings"] += rec.get("estimated_monthly_savings", 0)
            cat_analysis["priority_distribution"][rec.get("priority", "low")] += 1
            cat_analysis["risk_distribution"][rec.get("risk_level", "low")] += 1
            cat_analysis["implementation_effort_distribution"][
                rec.get("implementation_effort", "low")
            ] += 1

        # Calculate averages
        for _cat, analysis in category_analysis.items():
            if analysis["recommendation_count"] > 0:
                analysis["average_savings_per_recommendation"] = (
                    analysis["total_potential_savings"] / analysis["recommendation_count"]
                )

        return category_analysis

    def _generate_risk_assessment(self) -> dict[str, Any]:
        """Generate risk assessment for implementation"""
        risk_summary = {
            "total_recommendations": len(self.recommendations_history),
            "by_risk_level": {
                "safe": [],
                "low": [],
                "medium": [],
                "high": [],
            },
            "recommended_implementation_order": [],
            "quick_wins": [],
            "high_value_high_effort": [],
        }

        for rec in self.recommendations_history:
            risk_level = rec.get("risk_level", "low")
            savings = rec.get("estimated_monthly_savings", 0)
            effort = rec.get("implementation_effort", "medium")

            risk_summary["by_risk_level"][risk_level].append(rec)

            # Quick wins: high savings, low risk, low effort
            if risk_level in ["safe", "low"] and effort == "low" and savings > 100:
                risk_summary["quick_wins"].append(rec)

            # High value, high effort
            if savings > 1000 and effort == "high":
                risk_summary["high_value_high_effort"].append(rec)

        # Sort recommendations by risk level (safest first)
        risk_order = {"safe": 0, "low": 1, "medium": 2, "high": 3}
        sorted_recs = sorted(
            self.recommendations_history,
            key=lambda x: (
                risk_order.get(x.get("risk_level", "low"), 2),
                -x.get("estimated_monthly_savings", 0),
            ),
        )
        risk_summary["recommended_implementation_order"] = sorted_recs

        return risk_summary

    def _generate_next_steps(self) -> list[str]:
        """Generate actionable next steps"""
        next_steps = []

        if not self.recommendations_history:
            return ["Run cost optimization analysis to generate recommendations"]

        # Check for critical priority items
        critical_count = len(
            [r for r in self.recommendations_history if r.get("priority") == "critical"]
        )
        if critical_count > 0:
            next_steps.append(
                f"Address {critical_count} critical priority recommendations immediately"
            )

        # Check implementation progress
        completed_count = len(
            [i for i in self.saving_impacts if i.implementation_status == "completed"]
        )
        total_count = len(self.saving_impacts)

        if total_count > 0 and completed_count < total_count:
            next_steps.append(
                f"Complete {total_count - completed_count} in-progress implementations"
            )

        # Check for safe, high-value opportunities
        quick_wins = len(
            [
                r
                for r in self.recommendations_history
                if r.get("risk_level") in ["safe", "low"]
                and r.get("estimated_monthly_savings") > 500
                and r.get("implementation_effort") == "low"
            ]
        )
        if quick_wins > 0:
            next_steps.append(
                f"Implement {quick_wins} quick-win opportunities for immediate savings"
            )

        # Monitor trends
        if len(self.cost_trends) >= 2:
            latest_trend = self.cost_trends[-1]
            if latest_trend.savings > latest_trend.total_cost * 0.3:
                next_steps.append("Excellent progress - continue monitoring and optimization")
            else:
                next_steps.append("Review optimization strategy and identify new opportunities")

        return next_steps

    def _convert_to_markdown(self, report: dict[str, Any]) -> str:
        """Convert report to Markdown format"""
        md = []

        executive = report["executive_summary"]
        md.append("# Cost Optimization Report")
        md.append(f"**Period:** {executive['report_period'].upper()}")
        md.append(f"**Provider:** {executive['provider'].upper()}")
        md.append(f"**Generated:** {executive['generated_at']}")
        md.append("")

        md.append("## Executive Summary")
        summary = executive["summary"]
        md.append(
            f"- **Total Potential Monthly Savings:** ${summary['total_potential_savings']:,.2f}"
        )
        md.append(f"- **Total Implemented Savings:** ${summary['total_implemented_savings']:,.2f}")
        md.append(f"- **Savings Realization Rate:** {summary['savings_realization_rate']:.1f}%")
        md.append(f"- **Total Recommendations:** {summary['total_recommendations']}")
        md.append("")

        md.append("## Category Breakdown")
        for category, savings in summary["category_savings"].items():
            md.append(f"- **{category.title()}:** ${savings:,.2f}")
        md.append("")

        md.append("## Priority Distribution")
        priority = summary["priority_breakdown"]
        md.append(f"- **Critical:** {priority['critical']}")
        md.append(f"- **High:** {priority['high']}")
        md.append(f"- **Medium:** {priority['medium']}")
        md.append(f"- **Low:** {priority['low']}")
        md.append("")

        md.append("## Top Opportunities")
        for i, rec in enumerate(executive["top_opportunities"], 1):
            md.append(f"{i}. **{rec.get('title', 'Unknown')}**")
            md.append(f"   - Savings: ${rec.get('estimated_monthly_savings', 0):,.2f}/month")
            md.append(f"   - Priority: {rec.get('priority', 'unknown').upper()}")
            md.append(f"   - Risk: {rec.get('risk_level', 'unknown').title()}")
            md.append("")

        md.append("## Implementation Progress")
        progress = executive["implementation_progress"]
        md.append(f"- **Completion Rate:** {progress['completion_percentage']:.1f}%")
        md.append(f"- **Completed:** {progress['status_breakdown']['completed']}")
        md.append(f"- **In Progress:** {progress['status_breakdown']['in_progress']}")
        md.append(f"- **Planned:** {progress['status_breakdown']['planned']}")
        md.append("")

        md.append("## Recommended Next Steps")
        for step in executive["next_steps"]:
            md.append(f"- {step}")
        md.append("")

        return "\n".join(md)

    def _convert_to_html(self, report: dict[str, Any]) -> str:
        """Convert report to HTML format"""
        html = []

        executive = report["executive_summary"]
        html.append("<html><head><title>Cost Optimization Report</title>")
        html.append("<style>")
        html.append(
            "body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }"
        )
        html.append(
            ".summary-card { background: #f0f9ff; padding: 20px; border-radius: 8px; margin: 20px 0; }"
        )
        html.append(
            ".recommendation { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }"
        )
        html.append(".critical { border-left: 4px solid #dc2626; }")
        html.append(".high { border-left: 4px solid #f59e0b; }")
        html.append(".medium { border-left: 4px solid #3b82f6; }")
        html.append(".low { border-left: 4px solid #10b981; }")
        html.append("</style></head><body>")

        html.append("<h1>Cost Optimization Report</h1>")
        html.append(
            f"<p><strong>Period:</strong> {executive['report_period'].upper()} | <strong>Provider:</strong> {executive['provider'].upper()}</p>"
        )
        html.append(f"<p><strong>Generated:</strong> {executive['generated_at']}</p>")

        summary = executive["summary"]
        html.append("<div class='summary-card'>")
        html.append("<h2>Executive Summary</h2>")
        html.append(
            f"<p><strong>Total Potential Monthly Savings:</strong> ${summary['total_potential_savings']:,.2f}</p>"
        )
        html.append(
            f"<p><strong>Total Implemented Savings:</strong> ${summary['total_implemented_savings']:,.2f}</p>"
        )
        html.append(
            f"<p><strong>Savings Realization Rate:</strong> {summary['savings_realization_rate']:.1f}%</p>"
        )
        html.append(
            f"<p><strong>Total Recommendations:</strong> {summary['total_recommendations']}</p>"
        )
        html.append("</div>")

        html.append("<h2>Top Opportunities</h2>")
        for i, rec in enumerate(executive["top_opportunities"], 1):
            priority_class = rec.get("priority", "low")
            html.append(f"<div class='recommendation {priority_class}'>")
            html.append(f"<h3>{i}. {rec.get('title', 'Unknown')}</h3>")
            html.append(
                f"<p><strong>Savings:</strong> ${rec.get('estimated_monthly_savings', 0):,.2f}/month"
            )
            html.append(
                f"<p><strong>Priority:</strong> {rec.get('priority', 'unknown').upper()}</p>"
            )
            html.append(f"<p><strong>Risk:</strong> {rec.get('risk_level', 'unknown').title()}</p>")
            html.append(
                f"<p><strong>Description:</strong> {rec.get('description', 'No description')}</p>"
            )
            html.append("</div>")

        html.append("</body></html>")

        return "\n".join(html)

    def _convert_to_csv(self, report: dict[str, Any]) -> str:
        """Convert report to CSV format"""
        csv_lines = []

        csv_lines.append(
            "Recommendation Title,Category,Priority,Risk Level,Monthly Savings,Savings %,Resource Name,Implementation Effort"
        )

        for rec in report["detailed_recommendations"]:
            line = f'"{rec.get("title", "Unknown")}","{rec.get("category", "unknown")}","{rec.get("priority", "unknown")}","{rec.get("risk_level", "unknown")}",{rec.get("estimated_monthly_savings", 0)},{rec.get("estimated_savings_percentage", 0) * 100:.1f},"{rec.get("resource_name", "unknown")}","{rec.get("implementation_effort", "unknown")}'
            csv_lines.append(line)

        return "\n".join(csv_lines)

    def track_recommendation_status(self, recommendation_id: str, status: str, notes: str = ""):
        """Track implementation status of a recommendation"""
        for impact in self.saving_impacts:
            if impact.recommendation_id == recommendation_id:
                impact.implementation_status = status
                impact.notes = notes
                return True

        # Create new tracking entry
        impact = CostSavingImpact(
            recommendation_id=recommendation_id,
            implemented_date=datetime.utcnow(),
            original_monthly_cost=0,
            new_monthly_cost=0,
            monthly_savings=0,
            implementation_status=status,
            notes=notes,
        )
        self.saving_impacts.append(impact)
        return True

    def update_recommendation_history(self, recommendations: list[dict[str, Any]]):
        """Update the recommendations history with new analysis results"""
        # Add timestamp to each recommendation
        for rec in recommendations:
            rec["analysis_date"] = datetime.utcnow().isoformat()
            rec["status"] = "planned"  # Default status

        # Merge with existing history, avoiding duplicates
        existing_ids = {r.get("id") for r in self.recommendations_history}
        for rec in recommendations:
            if rec.get("id") not in existing_ids:
                self.recommendations_history.append(rec)

    def add_cost_trend(
        self,
        period: str,
        total_cost: float,
        optimized_cost: float,
        resource_count: int,
        recommendations_count: int,
        implemented_count: int,
    ):
        """Add a cost trend data point"""
        trend = CostTrend(
            period=period,
            total_cost=total_cost,
            optimized_cost=optimized_cost,
            savings=total_cost - optimized_cost,
            resource_count=resource_count,
            recommendations_count=recommendations_count,
            implemented_recommendations=implemented_count,
        )
        self.cost_trends.append(trend)
