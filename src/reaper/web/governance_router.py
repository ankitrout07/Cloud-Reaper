# src/reaper/web/governance_router.py
from __future__ import annotations

import os
from typing import Any
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from reaper.governance.policy_engine import CrossCloudPolicyEngine, PolicyCategory, PolicySeverity, PolicyStatus
from reaper.governance.migration_advisor import CloudMigrationAdvisor
from reaper.governance.cost_aggregator import MultiCloudCostAggregator
from reaper.governance.best_practices import ProviderBestPracticesEngine, PracticeCategory

governance_router = APIRouter()

# Check if governance features are enabled
GOVERNANCE_ENABLED = os.getenv("GOVERNANCE_ENABLED", "true").lower() == "true"

# Initialize governance engines
if GOVERNANCE_ENABLED:
    policy_engine = CrossCloudPolicyEngine()
    migration_advisor = CloudMigrationAdvisor()
    cost_aggregator = MultiCloudCostAggregator()
    best_practices_engine = ProviderBestPracticesEngine()
else:
    # Create dummy engines for graceful degradation
    policy_engine = None
    migration_advisor = None
    cost_aggregator = None
    best_practices_engine = None


# ============ Policy Engine Endpoints ============

class PolicyTemplateCreate(BaseModel):
    policy_id: str
    name: str
    category: str
    severity: str
    description: str
    universal_rules: list[dict]
    provider_translations: dict[str, list[dict]]


class PolicyTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    universal_rules: list[dict] | None = None
    provider_translations: dict[str, list[dict]] | None = None


class PolicyComplianceRequest(BaseModel):
    policy_id: str
    resources: list[dict]
    provider: str


@governance_router.get("/api/v1/governance/policies")
async def list_policies(category: str = None, status: str = None):
    """List all policy templates with optional filtering."""
    if not GOVERNANCE_ENABLED or policy_engine is None:
        raise HTTPException(status_code=503, detail="Governance features are disabled")
    
    try:
        policy_category = PolicyCategory(category) if category else None
        policy_status = PolicyStatus(status) if status else None
        
        templates = policy_engine.list_templates(
            category=policy_category, 
            status=policy_status
        )
        
        return {
            "status": "success",
            "count": len(templates),
            "policies": [policy_engine._template_to_dict(t) for t in templates]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid filter parameter: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list policies: {e}")


@governance_router.get("/api/v1/governance/policies/{policy_id}")
async def get_policy(policy_id: str):
    """Get a specific policy template by ID."""
    try:
        template = policy_engine.get_template(policy_id)
        if not template:
            raise HTTPException(status_code=404, detail=f"Policy '{policy_id}' not found")
        
        return {
            "status": "success",
            "policy": policy_engine._template_to_dict(template)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get policy: {e}")


@governance_router.post("/api/v1/governance/policies")
async def create_policy(request: PolicyTemplateCreate):
    """Create a new policy template."""
    try:
        from reaper.governance.policy_engine import PolicyTemplate
        
        template = PolicyTemplate(
            policy_id=request.policy_id,
            name=request.name,
            category=PolicyCategory(request.category),
            severity=PolicySeverity(request.severity),
            description=request.description,
            universal_rules=request.universal_rules,
            provider_translations=request.provider_translations,
            status=PolicyStatus.DRAFT
        )
        
        result = policy_engine.create_template(template)
        
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=400, detail=result["error"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid parameter: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create policy: {e}")


@governance_router.put("/api/v1/governance/policies/{policy_id}")
async def update_policy(policy_id: str, request: PolicyTemplateUpdate):
    """Update an existing policy template."""
    try:
        updates = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.description is not None:
            updates["description"] = request.description
        if request.status is not None:
            updates["status"] = PolicyStatus(request.status)
        if request.universal_rules is not None:
            updates["universal_rules"] = request.universal_rules
        if request.provider_translations is not None:
            updates["provider_translations"] = request.provider_translations
        
        result = policy_engine.update_template(policy_id, updates)
        
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=404, detail=result["error"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid parameter: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update policy: {e}")


@governance_router.delete("/api/v1/governance/policies/{policy_id}")
async def delete_policy(policy_id: str):
    """Delete a policy template."""
    try:
        result = policy_engine.delete_template(policy_id)
        
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=404, detail=result["error"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete policy: {e}")


@governance_router.post("/api/v1/governance/policies/evaluate")
async def evaluate_policy_compliance(request: PolicyComplianceRequest):
    """Evaluate compliance of resources against a policy template."""
    try:
        result = policy_engine.evaluate_policy_compliance(
            request.policy_id,
            request.resources,
            request.provider
        )
        
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=404, detail=result["error"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to evaluate policy compliance: {e}")


@governance_router.get("/api/v1/governance/policies/report")
async def get_policy_report(provider: str = None):
    """Generate a comprehensive policy report."""
    try:
        report = policy_engine.generate_policy_report(provider=provider)
        return {
            "status": "success",
            "report": report
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate policy report: {e}")


# ============ Migration Advisor Endpoints ============

class MigrationAssessmentRequest(BaseModel):
    source_provider: str
    target_provider: str
    resource_inventory: list[dict]
    assessment_name: str | None = None


class ProviderComparisonRequest(BaseModel):
    resource_inventory: list[dict]
    current_provider: str


@governance_router.post("/api/v1/governance/migration/assess")
async def assess_migration(request: MigrationAssessmentRequest):
    """Perform comprehensive migration assessment."""
    try:
        result = migration_advisor.assess_migration(
            request.source_provider,
            request.target_provider,
            request.resource_inventory,
            request.assessment_name
        )
        
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=400, detail=result["error"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to assess migration: {e}")


@governance_router.post("/api/v1/governance/migration/compare")
async def compare_providers(request: ProviderComparisonRequest):
    """Compare all migration options from current provider."""
    try:
        result = migration_advisor.compare_providers(
            request.resource_inventory,
            request.current_provider
        )
        return {
            "status": "success",
            "comparison": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compare providers: {e}")


# ============ Cost Aggregation Endpoints ============

class CostNormalizationRequest(BaseModel):
    provider: str
    resource_id: str
    resource_type: str
    region: str
    amount: float
    currency: str
    billing_period_start: str  # ISO format datetime
    billing_period_end: str    # ISO format datetime
    cost_type: str = "opex"
    tags: dict | None = None


class CostAggregationRequest(BaseModel):
    cost_records: list[dict]
    group_by: str = "provider"


class CostTrendsRequest(BaseModel):
    cost_records: list[dict]
    period: str = "monthly"


class MultiCloudReportRequest(BaseModel):
    cost_records: list[dict]
    report_period_start: str  # ISO format datetime
    report_period_end: str    # ISO format datetime


class ProviderCostComparisonRequest(BaseModel):
    cost_records: list[dict]
    period_days: int = 30


class CostForecastRequest(BaseModel):
    cost_records: list[dict]
    forecast_days: int = 30


@governance_router.post("/api/v1/governance/cost/normalize")
async def normalize_cost(request: CostNormalizationRequest):
    """Normalize cost data to unified format."""
    try:
        period_start = datetime.fromisoformat(request.billing_period_start)
        period_end = datetime.fromisoformat(request.billing_period_end)
        
        record = cost_aggregator.normalize_cost(
            request.provider,
            request.resource_id,
            request.resource_type,
            request.region,
            request.amount,
            request.currency,
            period_start,
            period_end,
            request.cost_type,
            request.tags
        )
        
        return {
            "status": "success",
            "record": {
                "provider": record.provider,
                "resource_id": record.resource_id,
                "resource_type": record.resource_type,
                "region": record.region,
                "service_category": record.service_category,
                "original_currency": record.original_currency,
                "original_amount": record.original_amount,
                "base_currency": record.base_currency,
                "converted_amount": record.converted_amount,
                "cost_type": record.cost_type,
                "tags": record.tags
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to normalize cost: {e}")


@governance_router.post("/api/v1/governance/cost/aggregate")
async def aggregate_costs(request: CostAggregationRequest):
    """Aggregate costs by specified dimension."""
    try:
        from reaper.governance.cost_aggregator import UnifiedCostRecord
        
        # Convert dict records to UnifiedCostRecord objects
        cost_records = []
        for record_dict in request.cost_records:
            record = UnifiedCostRecord(**record_dict)
            cost_records.append(record)
        
        result = cost_aggregator.aggregate_costs(cost_records, request.group_by)
        return {
            "status": "success",
            "aggregation": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to aggregate costs: {e}")


@governance_router.post("/api/v1/governance/cost/trends")
async def get_cost_trends(request: CostTrendsRequest):
    """Analyze cost trends over time."""
    try:
        from reaper.governance.cost_aggregator import UnifiedCostRecord
        
        # Convert dict records to UnifiedCostRecord objects
        cost_records = []
        for record_dict in request.cost_records:
            record = UnifiedCostRecord(**record_dict)
            cost_records.append(record)
        
        result = cost_aggregator.get_cost_trends(cost_records, request.period)
        return {
            "status": "success",
            "trends": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get cost trends: {e}")


@governance_router.post("/api/v1/governance/cost/multi-cloud-report")
async def generate_multi_cloud_report(request: MultiCloudReportRequest):
    """Generate comprehensive multi-cloud cost report."""
    try:
        from reaper.governance.cost_aggregator import UnifiedCostRecord
        
        # Convert dict records to UnifiedCostRecord objects
        cost_records = []
        for record_dict in request.cost_records:
            record = UnifiedCostRecord(**record_dict)
            cost_records.append(record)
        
        period_start = datetime.fromisoformat(request.report_period_start)
        period_end = datetime.fromisoformat(request.report_period_end)
        
        result = cost_aggregator.generate_multi_cloud_report(
            cost_records,
            period_start,
            period_end
        )
        return {
            "status": "success",
            "report": result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate multi-cloud report: {e}")


@governance_router.post("/api/v1/governance/cost/compare-providers")
async def compare_provider_costs(request: ProviderCostComparisonRequest):
    """Compare costs between providers for a specified period."""
    try:
        from reaper.governance.cost_aggregator import UnifiedCostRecord
        
        # Convert dict records to UnifiedCostRecord objects
        cost_records = []
        for record_dict in request.cost_records:
            record = UnifiedCostRecord(**record_dict)
            cost_records.append(record)
        
        result = cost_aggregator.compare_provider_costs(
            cost_records,
            request.period_days
        )
        return {
            "status": "success",
            "comparison": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compare provider costs: {e}")


@governance_router.post("/api/v1/governance/cost/forecast")
async def forecast_costs(request: CostForecastRequest):
    """Forecast future costs based on historical data."""
    try:
        from reaper.governance.cost_aggregator import UnifiedCostRecord
        
        # Convert dict records to UnifiedCostRecord objects
        cost_records = []
        for record_dict in request.cost_records:
            record = UnifiedCostRecord(**record_dict)
            cost_records.append(record)
        
        result = cost_aggregator.forecast_costs(
            cost_records,
            request.forecast_days
        )
        return {
            "status": "success",
            "forecast": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to forecast costs: {e}")


# ============ Best Practices Endpoints ============

class PracticeEvaluationRequest(BaseModel):
    practice_id: str
    resources: list[dict]


class ProviderComplianceRequest(BaseModel):
    provider: str
    resources: list[dict]


class RecommendationsRequest(BaseModel):
    provider: str
    resources: list[dict]
    max_recommendations: int = 10


@governance_router.get("/api/v1/governance/best-practices")
async def list_best_practices(provider: str = None, category: str = None):
    """List best practices with optional filtering."""
    try:
        practice_category = PracticeCategory(category) if category else None
        
        practices = best_practices_engine.list_practices(
            provider=provider,
            category=practice_category
        )
        
        return {
            "status": "success",
            "count": len(practices),
            "practices": [best_practices_engine._practice_to_dict(p) for p in practices]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid filter parameter: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list best practices: {e}")


@governance_router.get("/api/v1/governance/best-practices/{practice_id}")
async def get_best_practice(practice_id: str):
    """Get a specific best practice by ID."""
    try:
        practice = best_practices_engine.get_practice(practice_id)
        if not practice:
            raise HTTPException(status_code=404, detail=f"Best practice '{practice_id}' not found")
        
        return {
            "status": "success",
            "practice": best_practices_engine._practice_to_dict(practice)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get best practice: {e}")


@governance_router.post("/api/v1/governance/best-practices/evaluate")
async def evaluate_practice(request: PracticeEvaluationRequest):
    """Evaluate a best practice against resources."""
    try:
        result = best_practices_engine.evaluate_practice(
            request.practice_id,
            request.resources
        )
        
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=404, detail=result["error"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to evaluate best practice: {e}")


@governance_router.post("/api/v1/governance/best-practices/provider-compliance")
async def evaluate_provider_compliance(request: ProviderComplianceRequest):
    """Evaluate all practices for a specific provider."""
    try:
        result = best_practices_engine.evaluate_provider_compliance(
            request.provider,
            request.resources
        )
        return {
            "status": "success",
            "compliance": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to evaluate provider compliance: {e}")


@governance_router.post("/api/v1/governance/best-practices/recommendations")
async def generate_recommendations(request: RecommendationsRequest):
    """Generate prioritized recommendations for improvement."""
    try:
        result = best_practices_engine.generate_recommendations(
            request.provider,
            request.resources,
            request.max_recommendations
        )
        return {
            "status": "success",
            "recommendations": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate recommendations: {e}")


# ============ Health Check Endpoint ============

@governance_router.get("/api/v1/governance/health")
async def health_check():
    """Health check endpoint for governance services."""
    return {
        "status": "healthy" if GOVERNANCE_ENABLED else "disabled",
        "enabled": GOVERNANCE_ENABLED,
        "services": {
            "policy_engine": "operational" if GOVERNANCE_ENABLED and policy_engine else "disabled",
            "migration_advisor": "operational" if GOVERNANCE_ENABLED and migration_advisor else "disabled",
            "cost_aggregator": "operational" if GOVERNANCE_ENABLED and cost_aggregator else "disabled",
            "best_practices_engine": "operational" if GOVERNANCE_ENABLED and best_practices_engine else "disabled"
        },
        "timestamp": datetime.now().isoformat()
    }
