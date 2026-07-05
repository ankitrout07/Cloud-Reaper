"""
Cloud Provider Migration Advisor

Advanced cost-benefit analysis system for evaluating workload
migration between cloud providers with risk assessment and planning.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from reaper.utils.error_handler import get_logger

logger = get_logger(__name__)


class MigrationDirection(Enum):
    """Direction of migration"""

    AZURE_TO_AWS = "azure_to_aws"
    AZURE_TO_GCP = "azure_to_gcp"
    AWS_TO_AZURE = "aws_to_azure"
    AWS_TO_GCP = "aws_to_gcp"
    GCP_TO_AZURE = "gcp_to_azure"
    GCP_TO_AWS = "gcp_to_aws"


class RiskLevel(Enum):
    """Risk levels for migration"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ResourceMapping:
    """Mapping between cloud provider resources"""

    source_type: str
    target_type: str
    size_mapping: dict[str, str]
    feature_parity_score: float
    effort_level: str  # "low", "medium", "high"


@dataclass
class MigrationAssessment:
    """Complete migration assessment for a workload"""

    assessment_id: str
    source_provider: str
    target_provider: str
    resource_inventory: list[dict]
    cost_analysis: dict[str, Any]
    risk_assessment: dict[str, Any]
    roi_analysis: dict[str, Any]
    migration_plan: dict[str, Any]
    created_at: datetime


class CloudMigrationAdvisor:
    """
    Advanced cost-benefit analysis system for evaluating workload
    migration between cloud providers with risk assessment and planning.
    """

    def __init__(self):
        """Initialize the migration advisor with resource mappings."""
        self.resource_mappings = self._load_resource_mappings()
        self.pricing_data = self._load_pricing_data()

    def _load_resource_mappings(self) -> dict[str, dict[str, ResourceMapping]]:
        """Load resource mappings between cloud providers."""
        return {
            "azure_to_aws": {
                "compute": ResourceMapping(
                    source_type="Microsoft.Compute/virtualMachines",
                    target_type="AWS::EC2::Instance",
                    size_mapping={
                        "Standard_B2s": "t3.medium",
                        "Standard_D2s_v3": "t3.large",
                        "Standard_D4s_v3": "m5.large",
                        "Standard_E4s_v3": "r5.large",
                        "Standard_F4s_v2": "c5.large",
                        "Standard_D8s_v3": "m5.xlarge",
                        "Standard_E8s_v3": "r5.xlarge",
                    },
                    feature_parity_score=0.92,
                    effort_level="medium",
                ),
                "storage": ResourceMapping(
                    source_type="Microsoft.Storage/storageAccounts",
                    target_type="AWS::S3::Bucket",
                    size_mapping={
                        "Standard_LRS": "STANDARD",
                        "Standard_GRS": "STANDARD_IA",
                        "Standard_RAGRS": "REDUCED_REDUNDANCY",
                        "Premium_LRS": "INTELLIGENT_TIERING",
                    },
                    feature_parity_score=0.95,
                    effort_level="low",
                ),
                "database": ResourceMapping(
                    source_type="Microsoft.Sql/servers/databases",
                    target_type="AWS::RDS::DBInstance",
                    size_mapping={
                        "Basic": "db.t3.micro",
                        "Standard_S0": "db.t3.small",
                        "Standard_S1": "db.t3.medium",
                        "Standard_S2": "db.t3.large",
                        "Premium_P1": "db.m5.large",
                    },
                    feature_parity_score=0.88,
                    effort_level="high",
                ),
            },
            "aws_to_azure": {
                "compute": ResourceMapping(
                    source_type="AWS::EC2::Instance",
                    target_type="Microsoft.Compute/virtualMachines",
                    size_mapping={
                        "t3.micro": "Standard_B1s",
                        "t3.small": "Standard_B2s",
                        "t3.medium": "Standard_D2s_v3",
                        "m5.large": "Standard_D4s_v3",
                        "r5.large": "Standard_E4s_v3",
                        "c5.large": "Standard_F4s_v2",
                        "m5.xlarge": "Standard_D8s_v3",
                    },
                    feature_parity_score=0.90,
                    effort_level="medium",
                ),
                "storage": ResourceMapping(
                    source_type="AWS::S3::Bucket",
                    target_type="Microsoft.Storage/storageAccounts",
                    size_mapping={
                        "STANDARD": "Standard_LRS",
                        "STANDARD_IA": "Standard_GRS",
                        "REDUCED_REDUNDANCY": "Standard_RAGRS",
                        "INTELLIGENT_TIERING": "Premium_LRS",
                    },
                    feature_parity_score=0.93,
                    effort_level="low",
                ),
                "database": ResourceMapping(
                    source_type="AWS::RDS::DBInstance",
                    target_type="Microsoft.Sql/servers/databases",
                    size_mapping={
                        "db.t3.micro": "Basic",
                        "db.t3.small": "Standard_S0",
                        "db.t3.medium": "Standard_S1",
                        "db.t3.large": "Standard_S2",
                        "db.m5.large": "Premium_P1",
                    },
                    feature_parity_score=0.85,
                    effort_level="high",
                ),
            },
            "azure_to_gcp": {
                "compute": ResourceMapping(
                    source_type="Microsoft.Compute/virtualMachines",
                    target_type="compute.googleapis.com/Instance",
                    size_mapping={
                        "Standard_B2s": "e2-medium",
                        "Standard_D2s_v3": "e2-standard-2",
                        "Standard_D4s_v3": "n2-standard-2",
                        "Standard_E4s_v3": "n2-highmem-2",
                        "Standard_F4s_v2": "n2-highcpu-2",
                        "Standard_D8s_v3": "n2-standard-4",
                    },
                    feature_parity_score=0.89,
                    effort_level="medium",
                ),
                "storage": ResourceMapping(
                    source_type="Microsoft.Storage/storageAccounts",
                    target_type="storage.googleapis.com/Bucket",
                    size_mapping={
                        "Standard_LRS": "STANDARD",
                        "Standard_GRS": "NEARLINE",
                        "Standard_RAGRS": "COLDLINE",
                        "Premium_LRS": "ARCHIVE",
                    },
                    feature_parity_score=0.91,
                    effort_level="low",
                ),
            },
            "gcp_to_azure": {
                "compute": ResourceMapping(
                    source_type="compute.googleapis.com/Instance",
                    target_type="Microsoft.Compute/virtualMachines",
                    size_mapping={
                        "e2-medium": "Standard_B2s",
                        "e2-standard-2": "Standard_D2s_v3",
                        "n2-standard-2": "Standard_D4s_v3",
                        "n2-highmem-2": "Standard_E4s_v3",
                        "n2-highcpu-2": "Standard_F4s_v2",
                        "n2-standard-4": "Standard_D8s_v3",
                    },
                    feature_parity_score=0.87,
                    effort_level="medium",
                ),
                "storage": ResourceMapping(
                    source_type="storage.googleapis.com/Bucket",
                    target_type="Microsoft.Storage/storageAccounts",
                    size_mapping={
                        "STANDARD": "Standard_LRS",
                        "NEARLINE": "Standard_GRS",
                        "COLDLINE": "Standard_RAGRS",
                        "ARCHIVE": "Premium_LRS",
                    },
                    feature_parity_score=0.90,
                    effort_level="low",
                ),
            },
        }

    def _load_pricing_data(self) -> dict[str, dict[str, float]]:
        """Load approximate pricing data for cost comparison."""
        return {
            "azure": {
                "compute": {
                    "Standard_B2s": 0.052,
                    "Standard_D2s_v3": 0.096,
                    "Standard_D4s_v3": 0.192,
                    "Standard_E4s_v3": 0.256,
                    "Standard_F4s_v2": 0.208,
                },
                "storage": {
                    "Standard_LRS": 0.018,
                    "Standard_GRS": 0.036,
                    "Premium_LRS": 0.135,
                },
                "database": {
                    "Basic": 0.006,
                    "Standard_S0": 0.015,
                    "Standard_S1": 0.030,
                    "Premium_P1": 0.465,
                },
            },
            "aws": {
                "compute": {
                    "t3.medium": 0.0416,
                    "m5.large": 0.096,
                    "r5.large": 0.126,
                    "c5.large": 0.085,
                },
                "storage": {
                    "STANDARD": 0.023,
                    "STANDARD_IA": 0.0125,
                    "INTELLIGENT_TIERING": 0.023,
                },
                "database": {
                    "db.t3.micro": 0.017,
                    "db.t3.small": 0.034,
                    "db.t3.medium": 0.068,
                    "db.m5.large": 0.173,
                },
            },
            "gcp": {
                "compute": {
                    "e2-medium": 0.035,
                    "e2-standard-2": 0.070,
                    "n2-standard-2": 0.095,
                    "n2-highmem-2": 0.130,
                    "n2-highcpu-2": 0.080,
                },
                "storage": {
                    "STANDARD": 0.020,
                    "NEARLINE": 0.010,
                    "COLDLINE": 0.004,
                    "ARCHIVE": 0.002,
                },
            },
        }

    def assess_migration(
        self,
        source_provider: str,
        target_provider: str,
        resource_inventory: list[dict],
        assessment_name: str = None,
    ) -> dict[str, Any]:
        """
        Perform comprehensive migration assessment.

        Args:
            source_provider: Current cloud provider ('azure', 'aws', 'gcp')
            target_provider: Target cloud provider ('azure', 'aws', 'gcp')
            resource_inventory: List of current resources with costs
            assessment_name: Optional name for the assessment

        Returns:
            Dictionary with complete migration assessment
        """
        try:
            # Generate assessment ID
            assessment_id = f"migration-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

            # Cost analysis
            cost_analysis = self._analyze_costs(
                source_provider, target_provider, resource_inventory
            )

            # Risk assessment
            risk_assessment = self._assess_risks(
                source_provider, target_provider, resource_inventory
            )

            # ROI analysis
            roi_analysis = self._calculate_roi(
                source_provider, target_provider, cost_analysis, risk_assessment
            )

            # Migration plan
            migration_plan = self._generate_migration_plan(
                source_provider, target_provider, resource_inventory, risk_assessment
            )

            assessment = MigrationAssessment(
                assessment_id=assessment_id,
                source_provider=source_provider,
                target_provider=target_provider,
                resource_inventory=resource_inventory,
                cost_analysis=cost_analysis,
                risk_assessment=risk_assessment,
                roi_analysis=roi_analysis,
                migration_plan=migration_plan,
                created_at=datetime.now(),
            )

            return {"success": True, "assessment": self._assessment_to_dict(assessment)}

        except Exception as e:
            logger.error(f"Migration assessment failed: {e}")
            return {"success": False, "error": str(e)}

    def _analyze_costs(
        self, source_provider: str, target_provider: str, resources: list[dict]
    ) -> dict[str, Any]:
        """Analyze cost implications of migration."""
        source_total = 0.0
        target_total = 0.0
        cost_differences = []

        mapping_key = f"{source_provider}_to_{target_provider}"
        mappings = self.resource_mappings.get(mapping_key, {})

        for resource in resources:
            resource_type = resource.get("type", "unknown")
            sku = resource.get("sku", "unknown")
            current_cost = resource.get("hourly_rate", 0.0)

            # Find mapping for this resource type
            mapping = None
            for category, resource_mapping in mappings.items():
                if category in resource_type.lower():
                    mapping = resource_mapping
                    break

            if mapping:
                # Map to target SKU
                target_sku = mapping.size_mapping.get(sku, sku)

                # Get target pricing
                target_pricing = self.pricing_data.get(target_provider, {})
                category_pricing = target_pricing.get(
                    mapping.source_type.split("/")[-1].lower(), {}
                )
                target_cost = category_pricing.get(target_sku, current_cost)

                cost_diff = target_cost - current_cost
                cost_differences.append(
                    {
                        "resource_id": resource.get("id"),
                        "source_sku": sku,
                        "target_sku": target_sku,
                        "source_cost": current_cost,
                        "target_cost": target_cost,
                        "cost_difference": cost_diff,
                        "savings_percentage": (cost_diff / current_cost * 100)
                        if current_cost > 0
                        else 0,
                    }
                )

                source_total += current_cost
                target_total += target_cost

        total_savings = source_total - target_total
        savings_percentage = (total_savings / source_total * 100) if source_total > 0 else 0

        return {
            "source_monthly_cost": source_total * 730,  # Hourly to monthly
            "target_monthly_cost": target_total * 730,
            "monthly_savings": total_savings * 730,
            "savings_percentage": savings_percentage,
            "annual_savings": total_savings * 730 * 12,
            "cost_differences": cost_differences,
            "break_even_months": self._calculate_break_even(cost_differences),
        }

    def _assess_risks(
        self, source_provider: str, target_provider: str, resources: list[dict]
    ) -> dict[str, Any]:
        """Assess migration risks."""
        technical_risks = []
        operational_risks = []
        business_risks = []

        # Technical risks
        mapping_key = f"{source_provider}_to_{target_provider}"
        mappings = self.resource_mappings.get(mapping_key, {})

        for resource in resources:
            resource_type = resource.get("type", "unknown")

            for category, mapping in mappings.items():
                if category in resource_type.lower():
                    if mapping.feature_parity_score < 0.9:
                        technical_risks.append(
                            {
                                "resource_id": resource.get("id"),
                                "risk_type": "feature_parity",
                                "description": f"Feature parity score: {mapping.feature_parity_score}",
                                "mitigation": "Review feature requirements and consider workarounds",
                            }
                        )

                    if mapping.effort_level == "high":
                        operational_risks.append(
                            {
                                "resource_id": resource.get("id"),
                                "risk_type": "migration_complexity",
                                "description": "High migration complexity",
                                "mitigation": "Allocate additional time and resources",
                            }
                        )

        # Operational risks
        operational_risks.extend(
            [
                {
                    "risk_type": "downtime",
                    "description": "Potential downtime during migration",
                    "mitigation": "Plan migration during maintenance windows",
                },
                {
                    "risk_type": "data_loss",
                    "description": "Data loss during transfer",
                    "mitigation": "Implement backup and validation procedures",
                },
            ]
        )

        # Business risks
        business_risks.extend(
            [
                {
                    "risk_type": "contractual_obligations",
                    "description": "Existing contractual commitments with source provider",
                    "mitigation": "Review contracts and plan exit strategy",
                },
                {
                    "risk_type": "team_expertise",
                    "description": "Team may lack expertise with target provider",
                    "mitigation": "Provide training and certification",
                },
            ]
        )

        # Calculate overall risk level
        total_risks = len(technical_risks) + len(operational_risks) + len(business_risks)
        if total_risks > 10:
            overall_risk = RiskLevel.HIGH
        elif total_risks > 5:
            overall_risk = RiskLevel.MEDIUM
        else:
            overall_risk = RiskLevel.LOW

        return {
            "overall_risk_level": overall_risk.value,
            "technical_risks": technical_risks,
            "operational_risks": operational_risks,
            "business_risks": business_risks,
            "total_risks": total_risks,
            "risk_score": self._calculate_risk_score(
                technical_risks, operational_risks, business_risks
            ),
        }

    def _calculate_roi(
        self, source_provider: str, target_provider: str, cost_analysis: dict, risk_assessment: dict
    ) -> dict[str, Any]:
        """Calculate return on investment for migration."""
        annual_savings = cost_analysis.get("annual_savings", 0)
        risk_score = risk_assessment.get("risk_score", 0.5)

        # Estimate migration costs (simplified)
        migration_costs = {
            "planning": 5000,  # $5,000 for planning
            "implementation": 20000,  # $20,000 for implementation
            "testing": 10000,  # $10,000 for testing
            "training": 5000,  # $5,000 for training
            "contingency": 10000,  # $10,000 contingency
        }
        total_migration_cost = sum(migration_costs.values())

        # Calculate ROI timeline
        if annual_savings > 0:
            payback_months = total_migration_cost / (annual_savings / 12)
            roi_percentage = (annual_savings / total_migration_cost) * 100
        else:
            payback_months = float("inf")
            roi_percentage = -100

        return {
            "annual_savings": annual_savings,
            "migration_costs": migration_costs,
            "total_migration_cost": total_migration_cost,
            "payback_period_months": payback_months,
            "payback_period_years": payback_months / 12
            if payback_months != float("inf")
            else float("inf"),
            "roi_percentage": roi_percentage,
            "net_present_value": self._calculate_npv(annual_savings, total_migration_cost),
            "risk_adjusted_roi": roi_percentage * (1 - risk_score),
        }

    def _generate_migration_plan(
        self,
        source_provider: str,
        target_provider: str,
        resources: list[dict],
        risk_assessment: dict,
    ) -> dict[str, Any]:
        """Generate detailed migration plan."""
        phases = [
            {
                "phase": 1,
                "name": "Planning and Assessment",
                "duration_weeks": 4,
                "tasks": [
                    "Detailed resource inventory",
                    "Dependency mapping",
                    "Cost optimization review",
                    "Risk assessment and mitigation planning",
                ],
            },
            {
                "phase": 2,
                "name": "Environment Setup",
                "duration_weeks": 3,
                "tasks": [
                    "Target provider account setup",
                    "Network configuration",
                    "Security configuration",
                    "Initial resource provisioning",
                ],
            },
            {
                "phase": 3,
                "name": "Data Migration",
                "duration_weeks": 6,
                "tasks": [
                    "Data backup and validation",
                    "Data transfer",
                    "Data verification",
                    "Cutover planning",
                ],
            },
            {
                "phase": 4,
                "name": "Application Migration",
                "duration_weeks": 8,
                "tasks": [
                    "Application reconfiguration",
                    "Testing and validation",
                    "Performance optimization",
                    "User acceptance testing",
                ],
            },
            {
                "phase": 5,
                "name": "Cutover and Optimization",
                "duration_weeks": 2,
                "tasks": [
                    "Final cutover",
                    "Monitoring and optimization",
                    "Documentation and handover",
                    "Source resource cleanup",
                ],
            },
        ]

        total_duration = sum(phase["duration_weeks"] for phase in phases)

        return {
            "total_duration_weeks": total_duration,
            "total_duration_months": total_duration / 4,
            "phases": phases,
            "critical_path": self._identify_critical_path(resources),
            "rollback_plan": self._generate_rollback_plan(),
        }

    def _calculate_break_even(self, cost_differences: list[dict]) -> int:
        """Calculate break-even period in months."""
        total_monthly_savings = sum(diff["cost_difference"] * 730 for diff in cost_differences)

        # Estimate migration costs
        migration_cost = 50000  # $50,000 estimated migration cost

        if total_monthly_savings > 0:
            return migration_cost / total_monthly_savings
        return float("inf")

    def _calculate_risk_score(self, technical: list, operational: list, business: list) -> float:
        """Calculate overall risk score (0-1)."""
        # Weight different risk types
        weights = {"technical": 0.4, "operational": 0.3, "business": 0.3}

        max_risks = 10  # Assume 10 is maximum expected risks per category

        technical_score = min(len(technical) / max_risks, 1.0)
        operational_score = min(len(operational) / max_risks, 1.0)
        business_score = min(len(business) / max_risks, 1.0)

        total_score = (
            technical_score * weights["technical"]
            + operational_score * weights["operational"]
            + business_score * weights["business"]
        )

        return total_score

    def _calculate_npv(self, annual_savings: float, initial_cost: float, years: int = 3) -> float:
        """Calculate net present value over specified years."""
        discount_rate = 0.10  # 10% discount rate
        npv = -initial_cost  # Initial investment is negative

        for year in range(1, years + 1):
            present_value = annual_savings / ((1 + discount_rate) ** year)
            npv += present_value

        return npv

    def _identify_critical_path(self, resources: list[dict]) -> list[str]:
        """Identify critical path items in migration."""
        # Simplified critical path identification
        critical_items = []

        for resource in resources:
            resource_type = resource.get("type", "").lower()
            if "database" in resource_type or "storage" in resource_type:
                critical_items.append(resource.get("id"))

        return critical_items

    def _generate_rollback_plan(self) -> dict[str, Any]:
        """Generate rollback plan."""
        return {
            "strategy": "gradual_rollback",
            "triggers": [
                "critical_failures",
                "performance_degradation_gt_50_percent",
                "data_corruption",
            ],
            "procedures": [
                "Switch DNS back to source provider",
                "Re-enable source resources",
                "Data synchronization from target to source",
                "User notification and communication",
            ],
            "max_rollback_time_hours": 24,
        }

    def _assessment_to_dict(self, assessment: MigrationAssessment) -> dict[str, Any]:
        """Convert assessment to dictionary."""
        return {
            "assessment_id": assessment.assessment_id,
            "source_provider": assessment.source_provider,
            "target_provider": assessment.target_provider,
            "resource_inventory": assessment.resource_inventory,
            "cost_analysis": assessment.cost_analysis,
            "risk_assessment": assessment.risk_assessment,
            "roi_analysis": assessment.roi_analysis,
            "migration_plan": assessment.migration_plan,
            "created_at": assessment.created_at.isoformat(),
        }

    def compare_providers(
        self, resource_inventory: list[dict], current_provider: str
    ) -> dict[str, Any]:
        """Compare all migration options from current provider."""
        providers = ["azure", "aws", "gcp"]
        providers.remove(current_provider)

        comparisons = []
        for target_provider in providers:
            assessment = self.assess_migration(
                current_provider, target_provider, resource_inventory
            )
            if assessment.get("success"):
                comparisons.append(assessment["assessment"])

        # Sort by annual savings
        comparisons.sort(key=lambda x: x["roi_analysis"]["annual_savings"], reverse=True)

        return {
            "current_provider": current_provider,
            "comparisons": comparisons,
            "recommended_option": comparisons[0] if comparisons else None,
        }
