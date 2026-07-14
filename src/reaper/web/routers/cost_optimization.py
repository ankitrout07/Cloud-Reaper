from __future__ import annotations

import asyncio
import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from reaper.collectors.providers.azure_collector import AzureCollector
from reaper.engine.core.cost_optimizer import (
    Priority,
    ResourceMetrics,
)
from reaper.engine.core.cost_reporter import ReportFormat, ReportPeriod
from reaper.utils.error_handler import get_logger
from reaper.web.app_async import is_first_run


def jsonify(*args, **kwargs):
    from fastapi.responses import JSONResponse
    content = args[0] if args and isinstance(args[0], dict) else kwargs
    status_code = kwargs.pop("status_code", 200)
    return JSONResponse(content=content, status_code=status_code)

logger = get_logger(__name__)

router = APIRouter(tags=["cost_optimization"])

async def analyze_cost_optimization(request: Request):
    from reaper.services.cost_optimization_service import CostOptimizationService
    service = CostOptimizationService()
    return await service.analyze_cost_optimization(request)

async def get_optimization_summary(request: Request):
    """Get a quick summary of cost optimization opportunities"""
    try:
        summary = cost_optimizer.generate_summary_report()
        return {"status": "success", "summary": summary}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

async def get_optimization_categories(request: Request):
    """Get recommendations grouped by optimization category"""
    try:
        by_category: dict[str, int] = {}
        for rec in cost_optimizer.recommendations:
            cat = rec.category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(rec.to_dict())

        # Calculate savings per category
        category_summary = {}
        for cat, recs in by_category.items():
            total_savings = sum(rec["estimated_monthly_savings"] for rec in recs)
            category_summary[cat] = {
                "recommendation_count": len(recs),
                "total_savings": total_savings,
                "recommendations": recs,
            }

        return {"status": "success", "categories": category_summary}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

async def get_optimization_by_priority(request: Request, priority):
    """Get recommendations filtered by priority level"""
    try:
        priority_enum = Priority(priority.lower())
        filtered_recs = [
            rec.to_dict() for rec in cost_optimizer.recommendations if rec.priority == priority_enum
        ]

        total_savings = sum(rec["estimated_monthly_savings"] for rec in filtered_recs)

        return jsonify(
            {
                "status": "success",
                "priority": priority,
                "count": len(filtered_recs),
                "total_savings": total_savings,
                "recommendations": filtered_recs,
            }
        )
    except ValueError:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": f"Invalid priority: {priority}"}
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

async def get_resource_optimizations(request: Request, resource_id):
    """Get all optimization recommendations for a specific resource"""
    try:
        resource_recs = [
            rec.to_dict()
            for rec in cost_optimizer.recommendations
            if rec.resource_id == resource_id
        ]

        if not resource_recs:
            return jsonify(
                {
                    "status": "error",
                    "message": f"No recommendations found for resource {resource_id}",
                },
                status_code=404,
            )

        total_savings = sum(rec["estimated_monthly_savings"] for rec in resource_recs)

        return jsonify(
            {
                "status": "success",
                "resource_id": resource_id,
                "recommendation_count": len(resource_recs),
                "total_savings": total_savings,
                "recommendations": resource_recs,
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

async def get_optimization_dashboard(request: Request):
    """Get dashboard data for cost optimization visualization"""
    try:
        summary = cost_optimizer.generate_summary_report()

        # Prepare dashboard data
        dashboard_data = {
            "total_recommendations": summary["total_recommendations"],
            "total_monthly_savings": summary["total_monthly_savings"],
            "by_priority": summary["by_priority"],
            "by_category": summary["by_category"],
            "top_recommendations": [
                rec.to_dict() for rec in cost_optimizer.prioritize_recommendations()[:10]
            ],
            "savings_potential": {
                "critical": sum(
                    rec.estimated_monthly_savings
                    for rec in cost_optimizer.recommendations
                    if rec.priority == Priority.CRITICAL
                ),
                "high": sum(
                    rec.estimated_monthly_savings
                    for rec in cost_optimizer.recommendations
                    if rec.priority == Priority.HIGH
                ),
                "medium": sum(
                    rec.estimated_monthly_savings
                    for rec in cost_optimizer.recommendations
                    if rec.priority == Priority.MEDIUM
                ),
                "low": sum(
                    rec.estimated_monthly_savings
                    for rec in cost_optimizer.recommendations
                    if rec.priority == Priority.LOW
                ),
            },
            "implementation_effort_breakdown": {
                "low": len(
                    [
                        rec
                        for rec in cost_optimizer.recommendations
                        if rec.implementation_effort == "low"
                    ]
                ),
                "medium": len(
                    [
                        rec
                        for rec in cost_optimizer.recommendations
                        if rec.implementation_effort == "medium"
                    ]
                ),
                "high": len(
                    [
                        rec
                        for rec in cost_optimizer.recommendations
                        if rec.implementation_effort == "high"
                    ]
                ),
            },
        }

        return {"status": "success", "dashboard": dashboard_data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

async def get_executive_summary(request: Request):
    """Generate executive summary of cost optimization efforts"""
    try:
        provider = request.query_params.get("provider", "azure").lower()
        period = request.query_params.get("period", "monthly").lower()

        period_enum = ReportPeriod[period.upper()]

        summary = cost_reporter.generate_executive_summary(period_enum, provider)
        return {"status": "success", "summary": summary}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

async def generate_cost_report(request: Request):
    """Generate detailed cost optimization report"""
    try:
        data = (await request.json() if await request.body() else {}) or {}
        provider = data.get("provider", "azure").lower()
        period = data.get("period", "monthly").lower()
        format_type = data.get("format", "json").lower()

        period_enum = ReportPeriod[period.upper()]
        format_enum = ReportFormat[format_type.upper()]

        # Update recommendations history from latest analysis
        recommendations = cost_optimizer.prioritize_recommendations()
        cost_reporter.update_recommendation_history([rec.to_dict() for rec in recommendations])

        report_content = cost_reporter.generate_detailed_report(period_enum, provider, format_enum)

        return jsonify(
            {
                "status": "success",
                "format": format_type,
                "report": report_content,
                "generated_at": datetime.now(datetime.UTC).isoformat(),
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

async def download_cost_report(request: Request):
    """Download cost optimization report"""
    try:
        data = (await request.json() if await request.body() else {}) or {}
        provider = data.get("provider", "azure").lower()
        period = data.get("period", "monthly").lower()
        format_type = data.get("format", "json").lower()

        period_enum = ReportPeriod[period.upper()]
        format_enum = ReportFormat[format_type.upper()]

        report_content = cost_reporter.generate_detailed_report(period_enum, provider, format_enum)

        # Create appropriate response based on format
        if format_type == "json":
            return {"status": "success", "report": report_content}
        return jsonify(
            {
                "status": "success",
                "report": report_content,
                "format": format_type,
                "filename": f"cost-optimization-report-{period}-{provider}.{format_type}",
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

async def track_recommendation_status(request: Request):
    """Track implementation status of a recommendation"""
    try:
        data = (await request.json() if await request.body() else {}) or {}
        recommendation_id = data.get("recommendation_id")
        status = data.get("status", "planned")
        notes = data.get("notes", "")

        if not recommendation_id:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "recommendation_id is required"},
            )

        success = cost_reporter.track_recommendation_status(recommendation_id, status, notes)

        if success:
            return {"status": "success", "message": "Status tracked successfully"}
        return JSONResponse(
            status_code=500, content={"status": "error", "message": "Failed to track status"}
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

async def get_implementation_progress(request: Request):
    """Get implementation progress of all recommendations"""
    try:
        progress = cost_reporter._get_implementation_progress()
        return {"status": "success", "progress": progress}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

async def get_cost_trends(request: Request):
    """Get cost optimization trends over time"""
    try:
        trends_data = {
            "trends": [trend.to_dict() for trend in cost_reporter.cost_trends],
            "analysis": cost_reporter._generate_trend_analysis(),
        }
        return {"status": "success", "trends_data": trends_data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

async def get_category_analysis(request: Request):
    """Get category-wise cost optimization analysis"""
    try:
        category_analysis = cost_reporter._generate_category_analysis()
        return {"status": "success", "category_analysis": category_analysis}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

async def get_risk_assessment(request: Request):
    """Get risk assessment for all recommendations"""
    try:
        risk_assessment = cost_reporter._generate_risk_assessment()
        return {"status": "success", "risk_assessment": risk_assessment}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

async def get_next_steps(request: Request):
    """Get recommended next steps for cost optimization"""
    try:
        next_steps = cost_reporter._generate_next_steps()
        return {"status": "success", "next_steps": next_steps}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

