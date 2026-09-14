from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from reaper.collectors.providers.azure_collector import AzureCollector
from reaper.utils.error_handler import get_logger
from reaper.web.app_async import is_first_run as app_is_first_run, settings_state

def is_first_run():
    return app_is_first_run()


def jsonify(*args, **kwargs):
    from fastapi.responses import JSONResponse
    content = args[0] if args and isinstance(args[0], dict) else kwargs
    status_code = kwargs.pop("status_code", 200)
    return JSONResponse(content=content, status_code=status_code)

logger = get_logger(__name__)

router = APIRouter(tags=["financial"])

@router.post("/api/financial/target-margin/calculate")
async def calculate_target_margin(request: Request):
    """Calculate optimal resource modifications to close the gap between current and target spend using actual Azure resource costs."""
    try:
        data = await request.json()
    except Exception:
        data = {}

    try:
        current_spend = data.get("current_spend", 0.0)
        target_spend = data.get("target_spend", 0.0)

        # Get current resource inventory for analysis
        if is_first_run():
            return jsonify(
                {"status": "unconfigured", "message": "Please configure cloud credentials first"}
            )

        def _fetch_tmf_data():
            c = AzureCollector()
            return (
                c.get_resource_cost_summary(),
                c.get_vm_inventory(),
                c.get_idle_vms(),
                c.get_orphaned_disks(),
            )

        resource_summary, vms, idle_vms, orphaned_disks = await asyncio.to_thread(_fetch_tmf_data)

        # Use actual current spend from resource summary if available
        if resource_summary and resource_summary.get("total_monthly_cost", 0) > 0:
            current_spend = resource_summary["total_monthly_cost"]
            print(f"[TMF] Using current spend from resource summary: ${current_spend:.2f}")
        elif current_spend == 0.0:
            # If no current spend provided and no resource summary, return error
            print("[TMF] No current spend available - cannot calculate target margin")
            return jsonify(
                {
                    "status": "error",
                    "message": "Unable to determine current spend. Please ensure Azure credentials are configured and resources are available.",
                }
            )

        # Enhanced savings calculation with risk-weighted optimization
        optimization_opportunities = []

        # VM Rightsizing Analysis (High Impact, Low Risk)
        if vms:
            for vm in vms:
                vm_cost = vm.get("cost", 0)  # Use actual cost from inventory
                if vm_cost == 0:
                    continue

                cpu_utilization = vm.get("cpu_utilization", 50)
                memory_utilization = vm.get("memory_utilization", 50)

                # Calculate rightsizing potential based on utilization
                if cpu_utilization < 30 or memory_utilization < 30:
                    # More precise savings calculation based on actual utilization
                    utilization_factor = min(cpu_utilization, memory_utilization) / 100
                    potential_savings = (
                        vm_cost * (1 - utilization_factor) * 0.8
                    )  # 80% of unused capacity
                    risk_score = 0.2  # Low risk

                    # Suggest specific size downgrade based on utilization
                    suggested_action = "Downsize to smaller VM size"
                    if cpu_utilization < 10:
                        suggested_action = "Downsize to 1/4 size or consider serverless"
                    elif cpu_utilization < 20:
                        suggested_action = "Downsize to 1/2 size"

                    optimization_opportunities.append(
                        {
                            "type": "rightsizing",
                            "resource_id": vm.get("id"),
                            "resource_name": vm.get("name"),
                            "potential_savings": round(potential_savings, 2),
                            "risk_score": risk_score,
                            "implementation_complexity": "low",
                            "description": f"{vm.get('name')} ({vm.get('size')}) - CPU: {cpu_utilization}%, {suggested_action}",
                            "current_cost": round(vm_cost, 2),
                        }
                    )

        # Idle Resource Elimination (High Impact, Very Low Risk)
        if idle_vms:
            for vm in idle_vms:
                vm_cost = vm.get("cost", 0)  # Use actual cost from enhanced idle VM data
                if vm_cost == 0:
                    continue

                potential_savings = vm_cost  # 100% savings by eliminating
                risk_score = 0.1  # Very low risk
                optimization_opportunities.append(
                    {
                        "type": "idle_elimination",
                        "resource_id": vm.get("id"),
                        "resource_name": vm.get("name"),
                        "potential_savings": round(potential_savings, 2),
                        "risk_score": risk_score,
                        "implementation_complexity": "very_low",
                        "description": f"Delete or deallocate idle VM {vm.get('name')} ({vm.get('size')}, {vm.get('location')})",
                        "current_cost": round(vm_cost, 2),
                    }
                )

        # Storage Tier Optimization (Medium Impact, Low Risk)
        if orphaned_disks and orphaned_disks.get("disks"):
            for disk in orphaned_disks["disks"]:
                disk_cost = disk.get("cost", 0)  # Use actual cost from enhanced orphaned disk data
                if disk_cost == 0:
                    continue

                current_tier = disk.get("tier", "premium")

                # Calculate savings based on tier downgrades
                tier_savings_map = {
                    "Premium_LRS": 0.6,  # 60% savings by moving to standard
                    "Premium_ZRS": 0.6,
                    "Standard_LRS": 0.4,  # 40% savings by moving to cool
                    "Standard_GRS": 0.4,
                    "Standard_ZRS": 0.4,
                }

                potential_savings = disk_cost * tier_savings_map.get(current_tier, 0.3)
                risk_score = 0.15  # Low risk

                # Suggest specific tier based on current tier
                suggested_tier = "Standard HDD"
                if "Premium" in current_tier:
                    suggested_tier = "Standard SSD"
                elif "Standard" in current_tier:
                    suggested_tier = "Cool tier (if infrequently accessed)"

                optimization_opportunities.append(
                    {
                        "type": "storage_optimization",
                        "resource_id": disk.get("id"),
                        "resource_name": disk.get("name"),
                        "potential_savings": round(potential_savings, 2),
                        "risk_score": risk_score,
                        "implementation_complexity": "low",
                        "description": f"Move {disk.get('name')} ({disk.get('size_gb', 0)}GB) from {current_tier} to {suggested_tier}",
                        "current_cost": round(disk_cost, 2),
                    }
                )

        # Network Resource Cleanup (Medium Impact, Low Risk)
        if resource_summary:
            networking_resources = resource_summary.get("networking", {}).get("resources", [])
            for resource in networking_resources:
                if resource.get("is_waste", False):
                    resource_cost = resource.get("cost", 0)
                    if resource_cost > 0:
                        potential_savings = resource_cost
                        risk_score = 0.1  # Very low risk for orphaned resources
                        optimization_opportunities.append(
                            {
                                "type": "network_cleanup",
                                "resource_id": resource.get("name"),
                                "resource_name": resource.get("name"),
                                "potential_savings": round(potential_savings, 2),
                                "risk_score": risk_score,
                                "implementation_complexity": "very_low",
                                "description": f"Delete orphaned {resource.get('type')} {resource.get('name')}",
                                "current_cost": round(resource_cost, 2),
                            }
                        )

        # Commitment Adoption (High Impact, Medium Risk)
        # Calculate based on actual VM compute costs from resource summary
        compute_costs = (
            resource_summary.get("virtual_machines", {}).get("total_cost", 0)
            if resource_summary
            else 0
        )
        if compute_costs > 50:  # Only recommend if compute spend is significant
            commitment_potential = (
                compute_costs * 0.30
            )  # Up to 30% savings with reservations on compute
            optimization_opportunities.append(
                {
                    "type": "commitment_adoption",
                    "resource_id": "commitment_pool",
                    "resource_name": "Azure Reserved Instances",
                    "potential_savings": round(commitment_potential, 2),
                    "risk_score": 0.4,  # Medium risk (commitment period)
                    "implementation_complexity": "medium",
                    "description": f"Purchase Azure Reserved Instances for ${compute_costs:.2f}/month compute spend (save ~30%)",
                    "current_cost": round(compute_costs, 2),
                }
            )

        # Sort opportunities by ROI (savings/risk ratio) - prioritize high savings, low risk
        optimization_opportunities.sort(
            key=lambda x: x["potential_savings"] / (x["risk_score"] + 0.1), reverse=True
        )

        # Calculate gap
        gap = current_spend - target_spend

        # Calculate total potential
        total_potential = sum(opt["potential_savings"] for opt in optimization_opportunities)

        if total_potential < gap:
            return jsonify(
                {
                    "status": "warning",
                    "message": "Unable to close gap with available optimizations",
                    "gap": gap,
                    "total_potential": total_potential,
                    "remaining_gap": gap - total_potential,
                    "available_opportunities": len(optimization_opportunities),
                }
            )

        # Smart gap-closing algorithm: prioritize high-ROI opportunities
        selected_optimizations = []
        remaining_gap = gap
        total_projected_savings = 0

        for opt in optimization_opportunities:
            if remaining_gap <= 0:
                break

            # Take full optimization if it doesn't over-close the gap significantly
            if opt["potential_savings"] <= remaining_gap * 1.1:  # Allow 10% overage
                selected_optimizations.append(opt)
                total_projected_savings += opt["potential_savings"]
                remaining_gap -= opt["potential_savings"]
            else:
                # Partial optimization - take only what's needed
                partial_ratio = remaining_gap / opt["potential_savings"]
                partial_opt = opt.copy()
                partial_opt["potential_savings"] = remaining_gap
                partial_opt["description"] = (
                    f"Partial: {opt['description']} ({partial_ratio:.1%} implementation)"
                )
                selected_optimizations.append(partial_opt)
                total_projected_savings += remaining_gap
                remaining_gap = 0

        # Aggregate by optimization type for UI display
        type_aggregates = {}
        for opt in selected_optimizations:
            opt_type = opt["type"]
            if opt_type not in type_aggregates:
                type_aggregates[opt_type] = {
                    "total_savings": 0,
                    "count": 0,
                    "avg_risk": 0,
                    "resources": [],
                }
            type_aggregates[opt_type]["total_savings"] += opt["potential_savings"]
            type_aggregates[opt_type]["count"] += 1
            type_aggregates[opt_type]["avg_risk"] += opt["risk_score"]
            type_aggregates[opt_type]["resources"].append(opt["resource_name"])

        # Calculate averages and percentages
        max_savings_by_type = {
            "rightsizing": sum(
                opt["potential_savings"]
                for opt in optimization_opportunities
                if opt["type"] == "rightsizing"
            ),
            "idle_elimination": sum(
                opt["potential_savings"]
                for opt in optimization_opportunities
                if opt["type"] == "idle_elimination"
            ),
            "storage_optimization": sum(
                opt["potential_savings"]
                for opt in optimization_opportunities
                if opt["type"] == "storage_optimization"
            ),
            "network_cleanup": sum(
                opt["potential_savings"]
                for opt in optimization_opportunities
                if opt["type"] == "network_cleanup"
            ),
            "commitment_adoption": sum(
                opt["potential_savings"]
                for opt in optimization_opportunities
                if opt["type"] == "commitment_adoption"
            ),
        }

        optimal_levers = {}
        for opt_type, aggregates in type_aggregates.items():
            aggregates["avg_risk"] /= aggregates["count"]
            max_possible = max_savings_by_type.get(opt_type, 1)
            optimal_levers[opt_type] = (
                min(100, (aggregates["total_savings"] / max_possible) * 100)
                if max_possible > 0
                else 0
            )

        # Ensure all lever types are present
        for lever_type in [
            "rightsizing",
            "idle_elimination",
            "storage_optimization",
            "commitment_adoption",
        ]:
            if lever_type not in optimal_levers:
                optimal_levers[lever_type] = 0

        projected_rightsizing_savings = type_aggregates.get("rightsizing", {}).get(
            "total_savings", 0
        )
        projected_idle_savings = type_aggregates.get("idle_elimination", {}).get("total_savings", 0)
        projected_storage_savings = type_aggregates.get("storage_optimization", {}).get(
            "total_savings", 0
        )
        projected_commitment_savings = type_aggregates.get("commitment_adoption", {}).get(
            "total_savings", 0
        )

        new_spend = current_spend - total_projected_savings

        return jsonify(
            {
                "status": "success",
                "current_spend": current_spend,
                "target_spend": target_spend,
                "gap": gap,
                "optimal_levers": optimal_levers,
                "projected_savings": {
                    "rightsizing": projected_rightsizing_savings,
                    "idle_elimination": projected_idle_savings,
                    "storage_optimization": projected_storage_savings,
                    "commitment_adoption": projected_commitment_savings,
                    "total": total_projected_savings,
                },
                "new_spend": new_spend,
                "gap_status": "closed" if new_spend <= target_spend else "open",
                "optimization_details": {
                    "total_opportunities_analyzed": len(optimization_opportunities),
                    "selected_optimizations": len(selected_optimizations),
                    "avg_risk_score": sum(opt["risk_score"] for opt in selected_optimizations)
                    / len(selected_optimizations)
                    if selected_optimizations
                    else 0,
                },
                "recommended_actions": [
                    {
                        "type": "VM Rightsizing",
                        "impact": projected_rightsizing_savings,
                        "description": f"Optimize {type_aggregates.get('rightsizing', {}).get('count', 0)} VMs for ${projected_rightsizing_savings:.2f} savings",
                        "risk_level": "low"
                        if type_aggregates.get("rightsizing", {}).get("avg_risk", 0) < 0.3
                        else "medium",
                    },
                    {
                        "type": "Idle Resource Elimination",
                        "impact": projected_idle_savings,
                        "description": f"Remove {type_aggregates.get('idle_elimination', {}).get('count', 0)} idle resources for ${projected_idle_savings:.2f} savings",
                        "risk_level": "very_low",
                    },
                    {
                        "type": "Storage Tier Optimization",
                        "impact": projected_storage_savings,
                        "description": f"Optimize {type_aggregates.get('storage_optimization', {}).get('count', 0)} storage resources for ${projected_storage_savings:.2f} savings",
                        "risk_level": "low",
                    },
                    {
                        "type": "Commitment Adoption",
                        "impact": projected_commitment_savings,
                        "description": f"Implement commitment strategy for ${projected_commitment_savings:.2f} savings",
                        "risk_level": "medium",
                    },
                ],
                "detailed_recommendations": selected_optimizations,
            }
        )

    except Exception as e:
        print(f"[!] Error in target margin calculation: {e}")
        import traceback

        traceback.print_exc()
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@router.post("/api/financial/target-margin/apply")
async def apply_target_margin_optimizations(request: Request):
    """Apply the calculated optimization recommendations physically to Azure."""
    try:
        try:
            data = await request.json()
        except Exception:
            data = {}

        optimizations = data.get("optimizations", {})
        detailed_recommendations = data.get("detailed_recommendations", [])

        if not detailed_recommendations:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "No detailed recommendations provided to apply.",
                },
            )

        from reaper.remediators.azure_remediator import AzureRemediator

        remediator = AzureRemediator()

        results = []
        applied_count = 0

        for rec in detailed_recommendations:
            rec_type = rec.get("type")
            res_id = rec.get("resource_id")
            res_name = rec.get("resource_name", "unknown")

            if not res_id or res_id == "commitment_pool":
                # Skip commitments or invalid resources for automated physical remediation
                continue

            op_result = {
                "resource": res_name,
                "type": rec_type,
                "status": "skipped",
                "message": "Unsupported type",
            }

            if rec_type == "rightsizing":
                op_result = remediator.downsize_vm(res_id)
                op_result["resource"] = res_name
            elif rec_type == "idle_elimination":
                op_result = remediator.delete_vm(res_id)
                op_result["resource"] = res_name
            elif rec_type == "storage_optimization":
                op_result = remediator.downgrade_disk(res_id, target_tier="Standard_LRS")
                op_result["resource"] = res_name

            results.append(op_result)
            if op_result.get("status") in ["processing", "dry_run"]:
                applied_count += 1

        return jsonify(
            {
                "status": "success",
                "message": "Optimization operations initiated",
                "applied_count": applied_count,
                "is_dry_run": remediator.is_dry_run,
                "results": results,
                "details": {
                    "rightsizing_applied": optimizations.get("rightsizing", 0),
                    "idle_elimination_applied": optimizations.get("idle_elimination", 0),
                    "storage_optimization_applied": optimizations.get("storage_optimization", 0),
                    "commitment_adoption_applied": optimizations.get("commitment_adoption", 0),
                },
            }
        )

    except Exception as e:
        print(f"[!] Error applying optimizations: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@router.get("/api/financial/current-spend")
async def get_current_spend(request: Request):
    """Fetch current monthly spend from Azure resources and return persisted target spend.

    Returns:
        current_spend  – live cumulative spend from Azure resources (or cached override)
        target_spend   – last persisted target spend (default: 80% of budget_threshold)
        budget_cap     – the budget threshold configured in Settings
        burn_rate      – daily burn rate
        forecast       – 30-day forecast
        source         – 'azure' | 'override' | 'fallback'
        resource_breakdown – detailed cost breakdown by resource type
    """
    try:
        budget_threshold = float(settings_state.get("budget_threshold", 1000.0))
        # Persisted target_spend – default 80 % of budget_threshold if not set
        target_spend = float(settings_state.get("target_spend", round(budget_threshold * 0.80, 2)))
        # Persisted current_spend override (manual entry takes precedence)
        current_override = settings_state.get("current_spend_override")

        source = "fallback"
        current_spend = 0.0
        burn_rate = 0.0
        forecast = 0.0
        resource_breakdown = None

        if current_override is not None:
            # Use manual override if provided
            current_spend = float(current_override)
            burn_rate = current_spend / 30
            forecast = burn_rate * 30
            source = "override"
        else:
            # Try to pull live data from Azure resources
            try:

                def _fetch_cost_data():
                    c = AzureCollector()
                    return c.get_resource_cost_summary(), c.get_cost_vs_budget()

                resource_cost_summary, cost_data = await asyncio.to_thread(_fetch_cost_data)
                current_spend = float(resource_cost_summary.get("total_monthly_cost", 0.0))
                resource_breakdown = resource_cost_summary

                burn_rate = float(
                    cost_data.get("burn_rate", current_spend / 30 if current_spend > 0 else 0)
                )
                forecast = float(cost_data.get("forecast", burn_rate * 30 if burn_rate > 0 else 0))

                if current_spend > 0:
                    source = "azure"
                else:
                    # If Azure returns 0 costs, return error to user
                    return jsonify(
                        {
                            "status": "error",
                            "message": "Unable to fetch current spend from Azure. Please ensure Azure credentials are configured and Cost Management API is accessible.",
                            "current_spend": 0.0,
                            "target_spend": round(target_spend, 2),
                            "budget_cap": round(budget_threshold, 2),
                            "burn_rate": 0.0,
                            "forecast": 0.0,
                            "source": "error",
                            "resource_breakdown": None,
                        }
                    )
            except Exception as e:
                print(f"[!] Error fetching Azure resource costs: {e}")
                # Azure not configured – return error to user
                return jsonify(
                    {
                        "status": "error",
                        "message": f"Error fetching Azure resource costs: {e!s}. Please ensure Azure credentials are configured.",
                        "current_spend": 0.0,
                        "target_spend": round(target_spend, 2),
                        "budget_cap": round(budget_threshold, 2),
                        "burn_rate": 0.0,
                        "forecast": 0.0,
                        "source": "error",
                        "resource_breakdown": None,
                    }
                )

        return jsonify(
            {
                "status": "success",
                "current_spend": round(current_spend, 2),
                "target_spend": round(target_spend, 2),
                "budget_cap": round(budget_threshold, 2),
                "burn_rate": round(burn_rate, 4),
                "forecast": round(forecast, 2),
                "source": source,
                "resource_breakdown": resource_breakdown,
            }
        )
    except Exception as e:
        print(f"[!] Error fetching current spend: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@router.post("/api/financial/spend-config")
async def update_spend_config(request: Request):
    """Persist current spend override and / or target spend.

    Body (all fields optional):
        current_spend  (float) – manual override for current monthly spend
        target_spend   (float) – desired target monthly spend
    """
    try:
        try:
            data = await request.json()
        except Exception:
            data = {}

        updated: dict = {}

        raw_current = data.get("current_spend")
        if raw_current is not None:
            val = float(raw_current)
            if val < 0:
                return JSONResponse(
                    status_code=400,
                    content={"status": "error", "message": "current_spend cannot be negative"},
                )
            settings_state["current_spend_override"] = val
            updated["current_spend"] = val

        raw_target = data.get("target_spend")
        if raw_target is not None:
            val = float(raw_target)
            if val < 0:
                return JSONResponse(
                    status_code=400,
                    content={"status": "error", "message": "target_spend cannot be negative"},
                )
            settings_state["target_spend"] = val
            updated["target_spend"] = val

        if not updated:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Provide current_spend and/or target_spend"},
            )

        return jsonify(
            {
                "status": "success",
                "message": "Spend configuration updated",
                "updated": updated,
            }
        )
    except ValueError as e:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": f"Invalid value: {e}"}
        )
    except Exception as e:
        print(f"[!] Error updating spend config: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ─── Frontend Alias Routes ─────────────────────────────────────────────────────
# The financial.html template uses legacy endpoint paths that differ from the
# canonical routes refactored into this router.  These aliases keep backwards
# compatibility without modifying the template.

@router.get("/api/financial/spend/current")
async def spend_current_alias(request: Request):
    """Alias: 'spend/current' → canonical 'current-spend'."""
    return await get_current_spend(request)


@router.post("/api/financial/spend/update")
async def spend_update_alias(request: Request):
    """Alias: 'spend/update' → canonical 'spend-config'.
    Frontend sends { current_spend } or { target_spend } which both match
    the spend-config handler body schema.
    """
    return await update_spend_config(request)
