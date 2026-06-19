from __future__ import annotations
"""
Comprehensive Cost Optimization Recommendation Engine

This module provides intelligent cost optimization recommendations covering:
- Compute rightsizing and migration opportunities
- Storage optimization and tier recommendations
- Network and bandwidth optimization
- Reserved instance/commitment analysis
- Spot instance opportunities
- Idle resource identification
- Multi-cloud cost comparison
- Regional arbitrage opportunities
- Architecture-level optimization suggestions
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class OptimizationCategory(Enum):
    """Categories of cost optimizations"""

    COMPUTE = "compute"
    STORAGE = "storage"
    NETWORK = "network"
    DATABASE = "database"
    CONTAINER = "container"
    LICENSE = "license"
    ARCHITECTURE = "architecture"


class Priority(Enum):
    """Priority levels for recommendations"""

    CRITICAL = "critical"  # Immediate action required, high savings
    HIGH = "high"  # Significant savings, implement soon
    MEDIUM = "medium"  # Moderate savings, consider implementing
    LOW = "low"  # Minor savings, nice to have


class RiskLevel(Enum):
    """Risk levels for implementing recommendations"""

    SAFE = "safe"  # No service impact
    LOW = "low"  # Minimal service impact
    MEDIUM = "medium"  # Some service impact, requires testing
    HIGH = "high"  # Significant service impact, careful planning required


@dataclass
class CostRecommendation:
    """Individual cost optimization recommendation"""

    id: str
    title: str
    description: str
    category: OptimizationCategory
    priority: Priority
    risk_level: RiskLevel
    estimated_monthly_savings: float
    estimated_savings_percentage: float
    implementation_effort: str  # "low", "medium", "high"
    resource_id: str
    resource_name: str
    resource_type: str
    current_cost: float
    recommended_action: str
    recommended_config: dict[str, Any] = field(default_factory=dict)
    implementation_steps: list[str] = field(default_factory=list)
    potential_issues: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "priority": self.priority.value,
            "risk_level": self.risk_level.value,
            "estimated_monthly_savings": self.estimated_monthly_savings,
            "estimated_savings_percentage": self.estimated_savings_percentage,
            "implementation_effort": self.implementation_effort,
            "resource_id": self.resource_id,
            "resource_name": self.resource_name,
            "resource_type": self.resource_type,
            "current_cost": self.current_cost,
            "recommended_action": self.recommended_action,
            "recommended_config": self.recommended_config,
            "implementation_steps": self.implementation_steps,
            "potential_issues": self.potential_issues,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class ResourceMetrics:
    """Current resource metrics for analysis"""

    cpu_utilization: float  # percentage
    memory_utilization: float  # percentage
    disk_utilization: float  # percentage
    network_in_mbps: float
    network_out_mbps: float
    iops: float
    latency_ms: float
    error_rate: float  # percentage
    uptime_percentage: float
    peak_cpu_utilization: float
    peak_memory_utilization: float


class ComprehensiveCostOptimizer:
    """
    Main cost optimization engine that analyzes resources and generates
    comprehensive cost optimization recommendations.
    """

    def __init__(self):
        self.recommendations: list[CostRecommendation] = []
        self.sku_mapping = self._load_sku_mappings()
        self.regional_pricing = self._load_regional_pricing()

    def _load_sku_mappings(self) -> dict[str, dict]:
        """Load SKU mappings for rightsizing recommendations"""
        return {
            # AWS EC2
            "aws": {
                "compute": {
                    "t3.micro": {
                        "cpu": 2,
                        "memory": 1,
                        "family": "burstable",
                        "performance_tier": 1,
                    },
                    "t3.small": {
                        "cpu": 2,
                        "memory": 2,
                        "family": "burstable",
                        "performance_tier": 2,
                    },
                    "t3.medium": {
                        "cpu": 2,
                        "memory": 4,
                        "family": "burstable",
                        "performance_tier": 3,
                    },
                    "m5.large": {"cpu": 2, "memory": 8, "family": "general", "performance_tier": 4},
                    "m5.xlarge": {
                        "cpu": 4,
                        "memory": 16,
                        "family": "general",
                        "performance_tier": 5,
                    },
                    "c5.large": {"cpu": 2, "memory": 4, "family": "compute", "performance_tier": 6},
                    "c5.xlarge": {
                        "cpu": 4,
                        "memory": 8,
                        "family": "compute",
                        "performance_tier": 7,
                    },
                }
            },
            # Azure VMs
            "azure": {
                "compute": {
                    "Standard_B1s": {
                        "cpu": 1,
                        "memory": 1,
                        "family": "burstable",
                        "performance_tier": 1,
                    },
                    "Standard_B2s": {
                        "cpu": 2,
                        "memory": 4,
                        "family": "burstable",
                        "performance_tier": 2,
                    },
                    "Standard_D2s_v3": {
                        "cpu": 2,
                        "memory": 8,
                        "family": "general",
                        "performance_tier": 3,
                    },
                    "Standard_D4s_v3": {
                        "cpu": 4,
                        "memory": 16,
                        "family": "general",
                        "performance_tier": 4,
                    },
                    "Standard_E4s_v3": {
                        "cpu": 4,
                        "memory": 32,
                        "family": "memory",
                        "performance_tier": 5,
                    },
                    "Standard_F4s_v2": {
                        "cpu": 4,
                        "memory": 8,
                        "family": "compute",
                        "performance_tier": 6,
                    },
                }
            },
            # GCP Compute Engine
            "gcp": {
                "compute": {
                    "e2-small": {"cpu": 2, "memory": 2, "family": "e2", "performance_tier": 1},
                    "e2-medium": {"cpu": 2, "memory": 4, "family": "e2", "performance_tier": 2},
                    "n2-standard-2": {"cpu": 2, "memory": 8, "family": "n2", "performance_tier": 3},
                    "n2-standard-4": {
                        "cpu": 4,
                        "memory": 16,
                        "family": "n2",
                        "performance_tier": 4,
                    },
                    "n2-highmem-4": {"cpu": 4, "memory": 32, "family": "n2", "performance_tier": 5},
                    "c2-standard-4": {
                        "cpu": 4,
                        "memory": 16,
                        "family": "c2",
                        "performance_tier": 6,
                    },
                }
            },
        }

    def _load_regional_pricing(self) -> dict[str, dict]:
        """Load regional pricing data for arbitrage analysis"""
        return {
            "aws": {
                "us-east-1": 1.0,  # baseline
                "us-east-2": 0.95,
                "us-west-1": 1.05,
                "us-west-2": 0.92,
                "eu-west-1": 1.08,
                "eu-west-2": 1.02,
                "ap-southeast-1": 0.98,
            },
            "azure": {
                "eastus": 1.0,  # baseline
                "eastus2": 0.97,
                "westus": 1.03,
                "westus2": 0.95,
                "westeurope": 1.06,
                "northeurope": 1.04,
                "southeastasia": 0.99,
            },
            "gcp": {
                "us-central1": 1.0,  # baseline
                "us-east1": 1.02,
                "us-west1": 1.04,
                "europe-west1": 1.08,
                "europe-west4": 1.05,
                "asia-southeast1": 0.97,
            },
        }

    def analyze_resource(
        self, resource_data: dict[str, Any], metrics: ResourceMetrics, current_cost: float
    ) -> list[CostRecommendation]:
        """
        Analyze a single resource and generate cost optimization recommendations.

        Args:
            resource_data: Resource metadata (provider, type, region, current_sku, etc.)
            metrics: Current resource metrics (cpu, memory, network, etc.)
            current_cost: Current monthly cost of the resource

        Returns:
            List of cost optimization recommendations for this resource
        """
        recommendations = []

        provider = resource_data.get("provider", "").lower()
        resource_type = resource_data.get("type", "").lower()
        current_sku = resource_data.get("sku", "")
        region = resource_data.get("region", "")

        # Generate recommendations based on resource type
        if "compute" in resource_type or "vm" in resource_type or "instance" in resource_type:
            recommendations.extend(
                self._analyze_compute_resource(provider, resource_data, metrics, current_cost)
            )
        elif "storage" in resource_type or "disk" in resource_type or "volume" in resource_type:
            recommendations.extend(
                self._analyze_storage_resource(provider, resource_data, metrics, current_cost)
            )
        elif "database" in resource_type or "db" in resource_type:
            recommendations.extend(
                self._analyze_database_resource(provider, resource_data, metrics, current_cost)
            )
        elif "network" in resource_type or "loadbalancer" in resource_type:
            recommendations.extend(
                self._analyze_network_resource(provider, resource_data, metrics, current_cost)
            )

        # Add regional arbitrage recommendations
        recommendations.extend(
            self._analyze_regional_arbitrage(provider, resource_data, metrics, current_cost, region)
        )

        return recommendations

    def _analyze_compute_resource(
        self,
        provider: str,
        resource_data: dict[str, Any],
        metrics: ResourceMetrics,
        current_cost: float,
    ) -> list[CostRecommendation]:
        """Analyze compute resources for optimization opportunities"""
        recommendations = []
        resource_id = resource_data.get("id", "")
        resource_name = resource_data.get("name", "")
        current_sku = resource_data.get("sku", "")

        # 1. Right-sizing recommendations
        right_size_rec = self._generate_right_sizing_recommendation(
            provider, resource_data, metrics, current_cost
        )
        if right_size_rec:
            recommendations.append(right_size_rec)

        # 2. Idle resource identification
        idle_rec = self._identify_idle_compute_resource(
            provider, resource_data, metrics, current_cost
        )
        if idle_rec:
            recommendations.append(idle_rec)

        # 3. Reserved instance analysis
        reserved_rec = self._analyze_reserved_instance_opportunity(
            provider, resource_data, metrics, current_cost
        )
        if reserved_rec:
            recommendations.append(reserved_rec)

        # 4. Spot instance opportunity
        spot_rec = self._analyze_spot_instance_opportunity(
            provider, resource_data, metrics, current_cost
        )
        if spot_rec:
            recommendations.append(spot_rec)

        # 5. Architecture optimization (e.g., serverless migration)
        arch_rec = self._analyze_architecture_optimization(
            provider, resource_data, metrics, current_cost
        )
        if arch_rec:
            recommendations.append(arch_rec)

        return recommendations

    def _generate_right_sizing_recommendation(
        self,
        provider: str,
        resource_data: dict[str, Any],
        metrics: ResourceMetrics,
        current_cost: float,
    ) -> CostRecommendation | None:
        """Generate right-sizing recommendation based on resource utilization"""
        current_sku = resource_data.get("sku", "")

        # Get SKU specifications
        sku_info = self.sku_mapping.get(provider, {}).get("compute", {}).get(current_sku)
        if not sku_info:
            return None

        # Analyze utilization patterns
        cpu_avg = metrics.cpu_utilization
        mem_avg = metrics.memory_utilization
        cpu_peak = metrics.peak_cpu_utilization
        mem_peak = metrics.peak_memory_utilization

        # Determine if resource is over-provisioned
        if cpu_avg < 30 and mem_avg < 50:
            # Significantly over-provisioned - recommend downsizing
            return self._create_downsize_recommendation(
                provider, resource_data, metrics, current_cost, sku_info
            )
        if cpu_avg < 50 and mem_avg < 70:
            # Moderately over-provisioned
            return self._create_moderate_downsize_recommendation(
                provider, resource_data, metrics, current_cost, sku_info
            )
        if cpu_peak < 40 and mem_peak < 60:
            # Consistently underutilized even at peak
            return self._create_conservative_downsize_recommendation(
                provider, resource_data, metrics, current_cost, sku_info
            )

        return None

    def _create_downsize_recommendation(
        self,
        provider: str,
        resource_data: dict[str, Any],
        metrics: ResourceMetrics,
        current_cost: float,
        sku_info: dict,
    ) -> CostRecommendation:
        """Create aggressive downsize recommendation"""
        resource_id = resource_data.get("id", "")
        resource_name = resource_data.get("name", "")
        current_sku = resource_data.get("sku", "")

        # Find appropriate smaller SKU
        recommended_sku = self._find_smaller_sku(provider, current_sku, sku_info)
        savings_percentage = 0.6  # Estimated 60% savings
        estimated_savings = current_cost * savings_percentage

        return CostRecommendation(
            id=f"rightsize_{resource_id}",
            title=f"Right-size {resource_name} - Significant Cost Reduction",
            description=f"Resource is significantly over-provisioned ({metrics.cpu_utilization:.1f}% CPU, {metrics.memory_utilization:.1f}% Memory). Moving from {current_sku} to {recommended_sku} can save approximately {savings_percentage * 100:.0f}% of costs.",
            category=OptimizationCategory.COMPUTE,
            priority=Priority.HIGH,
            risk_level=RiskLevel.LOW,
            estimated_monthly_savings=estimated_savings,
            estimated_savings_percentage=savings_percentage,
            implementation_effort="low",
            resource_id=resource_id,
            resource_name=resource_name,
            resource_type="compute",
            current_cost=current_cost,
            recommended_action=f"Downsize from {current_sku} to {recommended_sku}",
            recommended_config={
                "target_sku": recommended_sku,
                "current_sku": current_sku,
                "reason": "low_utilization",
            },
            implementation_steps=[
                "Analyze usage patterns for the past 30 days",
                f"Test workload on {recommended_sku} in staging",
                "Schedule migration during low-traffic period",
                "Monitor performance for 7 days post-migration",
                "Rollback if performance issues occur",
            ],
            potential_issues=[
                "Performance degradation during peak periods",
                "Application may require minimum resource thresholds",
                "Migration may require brief downtime",
            ],
        )

    def _find_smaller_sku(self, provider: str, current_sku: str, current_sku_info: dict) -> str:
        """Find a smaller SKU that can still handle the workload"""
        current_tier = current_sku_info.get("performance_tier", 5)
        family = current_sku_info.get("family", "general")

        # Look for SKU 1-2 tiers lower
        skus = self.sku_mapping.get(provider, {}).get("compute", {})

        candidates = []
        for sku, info in skus.items():
            tier = info.get("performance_tier", 10)
            sku_family = info.get("family", "general")

            # Prefer same family, 1-2 tiers lower
            if sku_family == family and current_tier - tier >= 1 and current_tier - tier <= 2:
                candidates.append((sku, tier))

        if candidates:
            # Return the largest candidate that's still smaller
            candidates.sort(key=lambda x: x[1], reverse=True)
            return candidates[0][0]

        # Fallback to burstable if available
        for sku, info in skus.items():
            if info.get("family") == "burstable":
                return sku

        return current_sku  # No suitable smaller SKU found

    def _identify_idle_compute_resource(
        self,
        provider: str,
        resource_data: dict[str, Any],
        metrics: ResourceMetrics,
        current_cost: float,
    ) -> CostRecommendation | None:
        """Identify idle compute resources that can be terminated or scaled down"""
        # Resource is considered idle if very low utilization for extended period
        is_idle = (
            metrics.cpu_utilization < 5
            and metrics.memory_utilization < 10
            and metrics.network_in_mbps < 1
            and metrics.network_out_mbps < 1
        )

        if not is_idle:
            return None

        resource_id = resource_data.get("id", "")
        resource_name = resource_data.get("name", "")

        return CostRecommendation(
            id=f"idle_{resource_id}",
            title=f"Terminate or Scale Idle Resource: {resource_name}",
            description=f"Resource appears to be idle ({metrics.cpu_utilization:.1f}% CPU, {metrics.memory_utilization:.1f}% Memory) with minimal network activity. Consider terminating or using auto-scaling to save costs.",
            category=OptimizationCategory.COMPUTE,
            priority=Priority.CRITICAL,
            risk_level=RiskLevel.LOW,
            estimated_monthly_savings=current_cost,
            estimated_savings_percentage=100.0,
            implementation_effort="low",
            resource_id=resource_id,
            resource_name=resource_name,
            resource_type="compute",
            current_cost=current_cost,
            recommended_action="Terminate resource or implement auto-scaling",
            recommended_config={
                "action": "terminate_or_autoscale",
                "auto_scale": {"min_instances": 0, "max_instances": 1, "target_cpu": 50},
            },
            implementation_steps=[
                "Verify resource is not required for backup/standby",
                "Check for any scheduled tasks or dependencies",
                "Implement auto-scaling with minimum 0 instances if applicable",
                "Set up monitoring to catch unexpected usage patterns",
                "Document resource purpose and termination decision",
            ],
            potential_issues=[
                "Resource may be used for periodic batch jobs",
                "May have dependencies that aren't immediately visible",
                "Termination may affect dependent services",
            ],
        )

    def _analyze_reserved_instance_opportunity(
        self,
        provider: str,
        resource_data: dict[str, Any],
        metrics: ResourceMetrics,
        current_cost: float,
    ) -> CostRecommendation | None:
        """Analyze opportunity for reserved instances/commitments"""
        # Stable workloads with consistent high utilization are good candidates
        is_stable_workload = (
            metrics.cpu_utilization > 50
            and metrics.uptime_percentage > 95
            and metrics.error_rate < 1
        )

        if not is_stable_workload:
            return None

        resource_id = resource_data.get("id", "")
        resource_name = resource_data.get("name", "")

        # Estimated savings with reserved instances (typically 30-70%)
        savings_percentage = 0.5  # Conservative 50% estimate
        estimated_savings = current_cost * savings_percentage

        return CostRecommendation(
            id=f"reserved_{resource_id}",
            title=f"Purchase Reserved Instance for {resource_name}",
            description=f"Resource shows stable, consistent utilization patterns suitable for reserved instances. Purchasing reserved instances can save approximately {savings_percentage * 100:.0f}% compared to on-demand pricing.",
            category=OptimizationCategory.COMPUTE,
            priority=Priority.HIGH,
            risk_level=RiskLevel.SAFE,
            estimated_monthly_savings=estimated_savings,
            estimated_savings_percentage=savings_percentage,
            implementation_effort="low",
            resource_id=resource_id,
            resource_name=resource_name,
            resource_type="compute",
            current_cost=current_cost,
            recommended_action="Purchase reserved instance commitment",
            recommended_config={
                "commitment_type": "1_year",  # Can be 1_year or 3_year
                "payment_option": "partial_upfront",  # or all_upfront, no_upfront
            },
            implementation_steps=[
                "Analyze workload patterns to ensure stability",
                "Choose appropriate commitment term (1 or 3 years)",
                "Select payment option based on budget constraints",
                "Purchase reserved instances",
                "Update cost tracking to account for commitment",
            ],
            potential_issues=[
                "Commitment reduces flexibility for scaling down",
                "Requires upfront payment or commitment",
                "Workload changes could reduce savings",
            ],
        )

    def _analyze_spot_instance_opportunity(
        self,
        provider: str,
        resource_data: dict[str, Any],
        metrics: ResourceMetrics,
        current_cost: float,
    ) -> CostRecommendation | None:
        """Analyze opportunity for spot instances"""
        # Fault-tolerant, interruptible workloads are good candidates
        is_fault_tolerant = (
            metrics.uptime_percentage < 95  # Can tolerate interruptions
            or resource_data.get("tags", {}).get("workload_type") == "batch"
            or resource_data.get("tags", {}).get("environment") == "testing"
        )

        if not is_fault_tolerant:
            return None

        resource_id = resource_data.get("id", "")
        resource_name = resource_data.get("name", "")

        # Spot instances can save 70-90% compared to on-demand
        savings_percentage = 0.8  # Conservative 80% estimate
        estimated_savings = current_cost * savings_percentage

        return CostRecommendation(
            id=f"spot_{resource_id}",
            title=f"Migrate {resource_name} to Spot Instances",
            description=f"Resource appears suitable for spot instances due to fault-tolerant nature. Spot instances can save approximately {savings_percentage * 100:.0f}% compared to on-demand pricing.",
            category=OptimizationCategory.COMPUTE,
            priority=Priority.MEDIUM,
            risk_level=RiskLevel.MEDIUM,
            estimated_monthly_savings=estimated_savings,
            estimated_savings_percentage=savings_percentage,
            implementation_effort="medium",
            resource_id=resource_id,
            resource_name=resource_name,
            resource_type="compute",
            current_cost=current_cost,
            recommended_action="Migrate to spot instances with fallback strategy",
            recommended_config={
                "instance_type": "spot",
                "fallback_strategy": "on_demand",
                "interruption_handling": "graceful_shutdown",
            },
            implementation_steps=[
                "Implement graceful shutdown handling",
                "Set up on-demand fallback capacity",
                "Configure instance type flexibility",
                "Test interruption handling",
                "Monitor spot instance availability and pricing",
            ],
            potential_issues=[
                "Spot instances can be interrupted with short notice",
                "May require fallback to on-demand capacity",
                "Pricing can be volatile",
                "Not suitable for stateful applications without migration",
            ],
        )

    def _analyze_architecture_optimization(
        self,
        provider: str,
        resource_data: dict[str, Any],
        metrics: ResourceMetrics,
        current_cost: float,
    ) -> CostRecommendation | None:
        """Analyze architecture-level optimizations (e.g., serverless migration)"""
        # Intermittent usage patterns are good for serverless
        is_intermittent = metrics.cpu_utilization < 20 and metrics.uptime_percentage < 50

        if not is_intermittent:
            return None

        resource_id = resource_data.get("id", "")
        resource_name = resource_data.get("name", "")

        # Serverless can save 70-90% for intermittent workloads
        savings_percentage = 0.7
        estimated_savings = current_cost * savings_percentage

        return CostRecommendation(
            id=f"serverless_{resource_id}",
            title=f"Migrate {resource_name} to Serverless Architecture",
            description=f"Resource shows intermittent usage patterns suitable for serverless architecture. Serverless can save approximately {savings_percentage * 100:.0f}% by eliminating idle costs.",
            category=OptimizationCategory.ARCHITECTURE,
            priority=Priority.MEDIUM,
            risk_level=RiskLevel.HIGH,
            estimated_monthly_savings=estimated_savings,
            estimated_savings_percentage=savings_percentage,
            implementation_effort="high",
            resource_id=resource_id,
            resource_name=resource_name,
            resource_type="compute",
            current_cost=current_cost,
            recommended_action="Migrate to serverless architecture (AWS Lambda, Azure Functions, GCP Cloud Functions)",
            recommended_config={
                "architecture_type": "serverless",
                "function_type": "event_driven",
            },
            implementation_steps=[
                "Refactor application for serverless architecture",
                "Implement event-driven patterns",
                "Set up proper monitoring and observability",
                "Test performance and cold start times",
                "Implement gradual migration strategy",
            ],
            potential_issues=[
                "Requires significant architectural changes",
                "Cold start latency may impact performance",
                "Vendor lock-in concerns",
                "Different cost model requires careful monitoring",
            ],
        )

    def _analyze_storage_resource(
        self,
        provider: str,
        resource_data: dict[str, Any],
        metrics: ResourceMetrics,
        current_cost: float,
    ) -> list[CostRecommendation]:
        """Analyze storage resources for optimization opportunities"""
        recommendations = []

        # 1. Storage tier optimization
        tier_rec = self._optimize_storage_tier(provider, resource_data, metrics, current_cost)
        if tier_rec:
            recommendations.append(tier_rec)

        # 2. Unused storage cleanup
        unused_rec = self._identify_unused_storage(provider, resource_data, metrics, current_cost)
        if unused_rec:
            recommendations.append(unused_rec)

        # 3. Storage lifecycle policies
        lifecycle_rec = self._implement_storage_lifecycle(
            provider, resource_data, metrics, current_cost
        )
        if lifecycle_rec:
            recommendations.append(lifecycle_rec)

        return recommendations

    def _optimize_storage_tier(
        self,
        provider: str,
        resource_data: dict[str, Any],
        metrics: ResourceMetrics,
        current_cost: float,
    ) -> CostRecommendation | None:
        """Optimize storage tier based on access patterns"""
        resource_id = resource_data.get("id", "")
        resource_name = resource_data.get("name", "")
        current_tier = resource_data.get("tier", "standard")

        # Analyze IOPS patterns to determine optimal tier
        iops = metrics.iops
        disk_utilization = metrics.disk_utilization

        # Low IOPS and low utilization can move to cheaper tier
        if iops < 100 and disk_utilization < 30:
            savings_percentage = 0.6  # 60% savings for tier downgrade
            estimated_savings = current_cost * savings_percentage

            recommended_tier = "archive" if disk_utilization < 10 else "cold"

            return CostRecommendation(
                id=f"storage_tier_{resource_id}",
                title=f"Move {resource_name} to {recommended_tier.upper()} Storage Tier",
                description=f"Storage shows low IOPS ({iops}) and low utilization ({disk_utilization:.1f}%). Moving to {recommended_tier} tier can save approximately {savings_percentage * 100:.0f}% of storage costs.",
                category=OptimizationCategory.STORAGE,
                priority=Priority.MEDIUM,
                risk_level=RiskLevel.LOW,
                estimated_monthly_savings=estimated_savings,
                estimated_savings_percentage=savings_percentage,
                implementation_effort="low",
                resource_id=resource_id,
                resource_name=resource_name,
                resource_type="storage",
                current_cost=current_cost,
                recommended_action=f"Move storage from {current_tier} to {recommended_tier}",
                recommended_config={
                    "current_tier": current_tier,
                    "recommended_tier": recommended_tier,
                    "reason": "low_access_frequency",
                },
                implementation_steps=[
                    "Analyze access patterns to ensure compatibility",
                    "Create snapshot before tier change",
                    "Initiate storage tier migration",
                    "Monitor for performance impact",
                    "Verify application compatibility",
                ],
                potential_issues=[
                    f"{recommended_tier} tier may have higher retrieval costs",
                    "Migration may take time for large volumes",
                    "Performance impact on access frequency",
                ],
            )

        return None

    def _identify_unused_storage(
        self,
        provider: str,
        resource_data: dict[str, Any],
        metrics: ResourceMetrics,
        current_cost: float,
    ) -> CostRecommendation | None:
        """Identify completely unused storage that can be deleted"""
        # Storage is unused if zero IOPS and very low utilization
        if metrics.iops == 0 and metrics.disk_utilization < 5:
            resource_id = resource_data.get("id", "")
            resource_name = resource_data.get("name", "")

            return CostRecommendation(
                id=f"unused_storage_{resource_id}",
                title=f"Delete Unused Storage: {resource_name}",
                description=f"Storage appears to be completely unused (0 IOPS, {metrics.disk_utilization:.1f}% utilization). Consider deleting to save full storage costs.",
                category=OptimizationCategory.STORAGE,
                priority=Priority.HIGH,
                risk_level=RiskLevel.LOW,
                estimated_monthly_savings=current_cost,
                estimated_savings_percentage=100.0,
                implementation_effort="low",
                resource_id=resource_id,
                resource_name=resource_name,
                resource_type="storage",
                current_cost=current_cost,
                recommended_action="Delete unused storage",
                recommended_config={
                    "action": "delete",
                    "create_snapshot": True,
                },
                implementation_steps=[
                    "Verify no data dependencies",
                    "Create final snapshot as backup",
                    "Delete storage resource",
                    "Remove from any configuration/automation",
                    "Update documentation",
                ],
                potential_issues=[
                    "Data loss if not properly backed up",
                    "May have hidden dependencies",
                    "Snapshot costs may apply",
                ],
            )

        return None

    def _implement_storage_lifecycle(
        self,
        provider: str,
        resource_data: dict[str, Any],
        metrics: ResourceMetrics,
        current_cost: float,
    ) -> CostRecommendation | None:
        """Implement storage lifecycle policies for automatic optimization"""
        resource_id = resource_data.get("id", "")
        resource_name = resource_data.get("name", "")

        savings_percentage = 0.3  # Estimated 30% savings from lifecycle policies
        estimated_savings = current_cost * savings_percentage

        return CostRecommendation(
            id=f"lifecycle_{resource_id}",
            title=f"Implement Storage Lifecycle Policy for {resource_name}",
            description="Implement storage lifecycle policies to automatically move infrequently accessed data to cheaper storage tiers and delete old data.",
            category=OptimizationCategory.STORAGE,
            priority=Priority.MEDIUM,
            risk_level=RiskLevel.LOW,
            estimated_monthly_savings=estimated_savings,
            estimated_savings_percentage=savings_percentage,
            implementation_effort="medium",
            resource_id=resource_id,
            resource_name=resource_name,
            resource_type="storage",
            current_cost=current_cost,
            recommended_action="Implement storage lifecycle management policy",
            recommended_config={
                "policy_rules": [
                    {
                        "transition_to_ia_after_days": 30,
                        "transition_to_archive_after_days": 90,
                        "delete_after_days": 365,
                    }
                ]
            },
            implementation_steps=[
                "Analyze data access patterns",
                "Design lifecycle policy rules",
                "Implement lifecycle policy",
                "Test with sample data",
                "Monitor policy effectiveness",
            ],
            potential_issues=[
                "Incorrect policy rules could delete important data",
                "Retrieval costs for archived data",
                "Policy complexity may increase management overhead",
            ],
        )

    def _analyze_database_resource(
        self,
        provider: str,
        resource_data: dict[str, Any],
        metrics: ResourceMetrics,
        current_cost: float,
    ) -> list[CostRecommendation]:
        """Analyze database resources for optimization opportunities"""
        recommendations = []

        # 1. Database rightsizing
        db_size_rec = self._rightsize_database(provider, resource_data, metrics, current_cost)
        if db_size_rec:
            recommendations.append(db_size_rec)

        # 2. Serverless database option
        serverless_rec = self._analyze_serverless_database(
            provider, resource_data, metrics, current_cost
        )
        if serverless_rec:
            recommendations.append(serverless_rec)

        return recommendations

    def _rightsize_database(
        self,
        provider: str,
        resource_data: dict[str, Any],
        metrics: ResourceMetrics,
        current_cost: float,
    ) -> CostRecommendation | None:
        """Rightsize database based on utilization"""
        if metrics.cpu_utilization < 30 and metrics.memory_utilization < 40:
            resource_id = resource_data.get("id", "")
            resource_name = resource_data.get("name", "")

            savings_percentage = 0.4
            estimated_savings = current_cost * savings_percentage

            return CostRecommendation(
                id=f"db_rightsize_{resource_id}",
                title=f"Right-size Database: {resource_name}",
                description=f"Database shows low utilization ({metrics.cpu_utilization:.1f}% CPU, {metrics.memory_utilization:.1f}% Memory). Consider downsizing to reduce costs.",
                category=OptimizationCategory.DATABASE,
                priority=Priority.HIGH,
                risk_level=RiskLevel.MEDIUM,
                estimated_monthly_savings=estimated_savings,
                estimated_savings_percentage=savings_percentage,
                implementation_effort="medium",
                resource_id=resource_id,
                resource_name=resource_name,
                resource_type="database",
                current_cost=current_cost,
                recommended_action="Downsize database instance",
                recommended_config={
                    "action": "downsize",
                    "target_size": "2_sizes_smaller",
                },
                implementation_steps=[
                    "Analyze database performance metrics",
                    "Test performance on smaller instance",
                    "Schedule maintenance window for resize",
                    "Monitor post-resize performance",
                    "Update connection strings if needed",
                ],
                potential_issues=[
                    "Performance degradation under load",
                    "Resize may require downtime",
                    "Connection limits may be affected",
                ],
            )

        return None

    def _analyze_serverless_database(
        self,
        provider: str,
        resource_data: dict[str, Any],
        metrics: ResourceMetrics,
        current_cost: float,
    ) -> CostRecommendation | None:
        """Analyze serverless database option"""
        if metrics.cpu_utilization < 20 and metrics.uptime_percentage < 50:
            resource_id = resource_data.get("id", "")
            resource_name = resource_data.get("name", "")

            savings_percentage = 0.5
            estimated_savings = current_cost * savings_percentage

            return CostRecommendation(
                id=f"db_serverless_{resource_id}",
                title=f"Migrate to Serverless Database: {resource_name}",
                description="Database shows intermittent usage patterns suitable for serverless database option.",
                category=OptimizationCategory.DATABASE,
                priority=Priority.MEDIUM,
                risk_level=RiskLevel.HIGH,
                estimated_monthly_savings=estimated_savings,
                estimated_savings_percentage=savings_percentage,
                implementation_effort="high",
                resource_id=resource_id,
                resource_name=resource_name,
                resource_type="database",
                current_cost=current_cost,
                recommended_action="Migrate to serverless database (Azure SQL Database serverless, AWS Aurora Serverless)",
                recommended_config={
                    "architecture_type": "serverless_database",
                    "auto_pause": True,
                    "min_capacity": "1 ACU",
                    "max_capacity": "4 ACU",
                },
                implementation_steps=[
                    "Evaluate serverless database compatibility",
                    "Test application compatibility",
                    "Plan migration strategy",
                    "Implement gradual migration",
                    "Set up monitoring and alerting",
                ],
                potential_issues=[
                    "Cold start latency",
                    "Different performance characteristics",
                    "May require application changes",
                    "Higher cost under constant load",
                ],
            )

        return None

    def _analyze_network_resource(
        self,
        provider: str,
        resource_data: dict[str, Any],
        metrics: ResourceMetrics,
        current_cost: float,
    ) -> list[CostRecommendation]:
        """Analyze network resources for optimization opportunities"""
        recommendations = []

        # 1. Load balancer optimization
        lb_rec = self._optimize_load_balancer(provider, resource_data, metrics, current_cost)
        if lb_rec:
            recommendations.append(lb_rec)

        # 2. Network transfer optimization
        transfer_rec = self._optimize_network_transfer(
            provider, resource_data, metrics, current_cost
        )
        if transfer_rec:
            recommendations.append(transfer_rec)

        return recommendations

    def _optimize_load_balancer(
        self,
        provider: str,
        resource_data: dict[str, Any],
        metrics: ResourceMetrics,
        current_cost: float,
    ) -> CostRecommendation | None:
        """Optimize load balancer configuration"""
        resource_id = resource_data.get("id", "")
        resource_name = resource_data.get("name", "")

        savings_percentage = 0.2
        estimated_savings = current_cost * savings_percentage

        return CostRecommendation(
            id=f"lb_optimize_{resource_id}",
            title=f"Optimize Load Balancer: {resource_name}",
            description="Load balancer configuration can be optimized to reduce costs while maintaining performance.",
            category=OptimizationCategory.NETWORK,
            priority=Priority.LOW,
            risk_level=RiskLevel.LOW,
            estimated_monthly_savings=estimated_savings,
            estimated_savings_percentage=savings_percentage,
            implementation_effort="low",
            resource_id=resource_id,
            resource_name=resource_name,
            resource_type="network",
            current_cost=current_cost,
            recommended_action="Optimize load balancer configuration",
            recommended_config={
                "enable_cross_zone_load_balancing": True,
                "connection_draining_timeout": 300,
                "health_check_interval": 30,
            },
            implementation_steps=[
                "Analyze current load balancer configuration",
                "Review traffic patterns and distribution",
                "Implement optimization recommendations",
                "Monitor performance post-optimization",
                "Adjust based on results",
            ],
            potential_issues=[
                "May require brief configuration changes",
                "Performance impact during optimization",
                "May need application-specific tuning",
            ],
        )

    def _optimize_network_transfer(
        self,
        provider: str,
        resource_data: dict[str, Any],
        metrics: ResourceMetrics,
        current_cost: float,
    ) -> CostRecommendation | None:
        """Optimize network transfer costs"""
        if metrics.network_out_mbps > 100:  # High outbound traffic
            resource_id = resource_data.get("id", "")
            resource_name = resource_data.get("name", "")

            savings_percentage = 0.3
            estimated_savings = current_cost * savings_percentage

            return CostRecommendation(
                id=f"network_transfer_{resource_id}",
                title=f"Optimize Network Transfer Costs for {resource_name}",
                description="High network transfer costs detected. Implement CDN, caching, or data transfer optimization to reduce costs.",
                category=OptimizationCategory.NETWORK,
                priority=Priority.MEDIUM,
                risk_level=RiskLevel.LOW,
                estimated_monthly_savings=estimated_savings,
                estimated_savings_percentage=savings_percentage,
                implementation_effort="medium",
                resource_id=resource_id,
                resource_name=resource_name,
                resource_type="network",
                current_cost=current_cost,
                recommended_action="Implement network transfer optimization",
                recommended_config={
                    "enable_cdn": True,
                    "enable_compression": True,
                    "optimize_data_transfer": True,
                },
                implementation_steps=[
                    "Analyze network transfer patterns",
                    "Implement CDN for static content",
                    "Enable compression for text-based content",
                    "Consider data transfer optimization services",
                    "Monitor cost savings",
                ],
                potential_issues=[
                    "CDN costs may offset some savings",
                    "Caching may affect data freshness",
                    "Implementation may require application changes",
                ],
            )

        return None

    def _analyze_regional_arbitrage(
        self,
        provider: str,
        resource_data: dict[str, Any],
        metrics: ResourceMetrics,
        current_cost: float,
        region: str,
    ) -> list[CostRecommendation]:
        """Analyze regional arbitrage opportunities"""
        recommendations = []

        regional_pricing = self.regional_pricing.get(provider, {})
        if not regional_pricing:
            return recommendations

        current_region_price = regional_pricing.get(region, 1.0)

        # Find cheaper regions
        cheaper_regions = []
        for r, price_multiplier in regional_pricing.items():
            if price_multiplier < current_region_price * 0.95:  # At least 5% cheaper
                savings_percentage = 1.0 - price_multiplier
                cheaper_regions.append((r, savings_percentage))

        if cheaper_regions:
            # Sort by savings
            cheaper_regions.sort(key=lambda x: x[1], reverse=True)
            best_region, best_savings = cheaper_regions[0]

            estimated_savings = current_cost * best_savings
            resource_id = resource_data.get("id", "")
            resource_name = resource_data.get("name", "")

            rec = CostRecommendation(
                id=f"regional_arbitrage_{resource_id}",
                title=f"Regional Arbitrage: Move {resource_name} to {best_region}",
                description=f"Moving resource from {region} to {best_region} can save approximately {best_savings * 100:.0f}% due to regional pricing differences.",
                category=OptimizationCategory.ARCHITECTURE,
                priority=Priority.MEDIUM,
                risk_level=RiskLevel.HIGH,
                estimated_monthly_savings=estimated_savings,
                estimated_savings_percentage=best_savings,
                implementation_effort="high",
                resource_id=resource_id,
                resource_name=resource_name,
                resource_type="compute",
                current_cost=current_cost,
                recommended_action=f"Migrate resource to {best_region} for cost savings",
                recommended_config={
                    "current_region": region,
                    "recommended_region": best_region,
                    "savings_percentage": best_savings,
                },
                implementation_steps=[
                    f"Analyze regulatory and compliance requirements for {best_region}",
                    "Evaluate latency impact on users",
                    "Plan data migration strategy",
                    "Implement gradual migration",
                    "Update DNS and routing",
                    "Monitor performance and costs",
                ],
                potential_issues=[
                    "Increased latency for users in current region",
                    "Data transfer costs during migration",
                    "Regulatory/compliance requirements",
                    "Service availability differences by region",
                ],
            )
            recommendations.append(rec)

        return recommendations

    def generate_summary_report(self) -> dict[str, Any]:
        """Generate a comprehensive summary of all recommendations"""
        total_savings = sum(rec.estimated_monthly_savings for rec in self.recommendations)

        # Group by category
        by_category = {}
        by_priority = {}

        for rec in self.recommendations:
            cat = rec.category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(rec)

            pri = rec.priority.value
            if pri not in by_priority:
                by_priority[pri] = []
            by_priority[pri].append(rec)

        return {
            "total_recommendations": len(self.recommendations),
            "total_monthly_savings": total_savings,
            "by_category": {cat: len(recs) for cat, recs in by_category.items()},
            "by_priority": {pri: len(recs) for pri, recs in by_priority.items()},
            "recommendations": [rec.to_dict() for rec in self.recommendations],
        }

    def prioritize_recommendations(self) -> list[CostRecommendation]:
        """Sort recommendations by priority and savings"""
        priority_order = {
            Priority.CRITICAL: 0,
            Priority.HIGH: 1,
            Priority.MEDIUM: 2,
            Priority.LOW: 3,
        }

        return sorted(
            self.recommendations,
            key=lambda rec: (
                priority_order.get(rec.priority, 99),
                -rec.estimated_monthly_savings,
                rec.estimated_savings_percentage,
            ),
        )
