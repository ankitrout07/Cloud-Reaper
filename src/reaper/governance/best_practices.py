"""
Provider-Specific Best Practices Engine

Cloud provider-specific best practices recommendations and
compliance checking for Azure, AWS, and GCP.
"""

import json
import logging
from typing import Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from reaper.utils.error_handler import get_logger

logger = get_logger(__name__)


class PracticeCategory(Enum):
    """Categories of best practices"""
    COST_OPTIMIZATION = "cost_optimization"
    SECURITY = "security"
    RELIABILITY = "reliability"
    OPERATIONAL_EXCELLENCE = "operational_excellence"
    PERFORMANCE = "performance"
    SUSTAINABILITY = "sustainability"


class PracticeSeverity(Enum):
    """Severity levels for practice violations"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class PracticeStatus(Enum):
    """Status of practice implementation"""
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


@dataclass
class BestPractice:
    """Best practice definition"""
    practice_id: str
    name: str
    category: PracticeCategory
    severity: PracticeSeverity
    provider: str
    description: str
    rationale: str
    implementation_guide: str
    resource_types: list[str]
    check_logic: dict[str, Any]
    remediation_steps: list[str]
    references: list[str]


@dataclass
class PracticeEvaluation:
    """Result of evaluating a best practice against resources"""
    practice_id: str
    resource_id: str
    resource_type: str
    status: PracticeStatus
    severity: PracticeSeverity
    findings: str
    recommendations: list[str]
    estimated_effort: str  # "low", "medium", "high"
    estimated_cost_impact: str  # "none", "low", "medium", "high"


class ProviderBestPracticesEngine:
    """
    Cloud provider-specific best practices recommendations and
    compliance checking for Azure, AWS, and GCP.
    """

    def __init__(self):
        """Initialize the best practices engine with provider-specific practices."""
        self.practices: dict[str, BestPractice] = {}
        self._load_azure_practices()
        self._load_aws_practices()
        self._load_gcp_practices()

    def _load_azure_practices(self):
        """Load Azure-specific best practices."""
        
        # Cost Optimization Practices
        self.practices["azure-reserved-instances"] = BestPractice(
            practice_id="azure-reserved-instances",
            name="Use Azure Reserved Instances for Long-Term Workloads",
            category=PracticeCategory.COST_OPTIMIZATION,
            severity=PracticeSeverity.HIGH,
            provider="azure",
            description="Purchase Reserved Instances for workloads running 24/7 to save up to 72% compared to pay-as-you-go rates.",
            rationale="Reserved Instances provide significant cost savings for predictable, long-term workloads.",
            implementation_guide="Identify VMs with consistent utilization over 12 months and purchase appropriate RI terms.",
            resource_types=["Microsoft.Compute/virtualMachines"],
            check_logic={
                "condition": "billing_model == 'pay_as_you_go' and avg_monthly_uptime > 90%",
                "threshold": 0.9
            },
            remediation_steps=[
                "Analyze VM utilization patterns over the past 90 days",
                "Identify candidates for Reserved Instances",
                "Purchase appropriate RI term (1-year or 3-year)",
                "Apply RIs to eligible VMs"
            ],
            references=[
                "https://docs.microsoft.com/azure/cost-management-billing/reservations-save-compute-costs"
            ]
        )

        self.practices["azure-right-sizing"] = BestPractice(
            practice_id="azure-right-sizing",
            name="Right-Size Azure Virtual Machines",
            category=PracticeCategory.COST_OPTIMIZATION,
            severity=PracticeSeverity.MEDIUM,
            provider="azure",
            description="Ensure VMs are appropriately sized based on actual utilization to avoid over-provisioning.",
            rationale="Over-provisioned VMs waste money on unused resources.",
            implementation_guide="Monitor CPU, memory, and disk utilization patterns and resize to appropriate SKUs.",
            resource_types=["Microsoft.Compute/virtualMachines"],
            check_logic={
                "condition": "avg_cpu_utilization < 20% or avg_memory_utilization < 20%",
                "threshold": 0.2
            },
            remediation_steps=[
                "Review VM utilization metrics",
                "Identify underutilized VMs",
                "Select appropriate smaller SKU",
                "Resize VM during maintenance window"
            ],
            references=[
                "https://docs.microsoft.com/azure/cost-management-billing/manage-costs"
            ]
        )

        # Security Practices
        self.practices["azure-nsg-flow-logs"] = BestPractice(
            practice_id="azure-nsg-flow-logs",
            name="Enable Network Security Group Flow Logs",
            category=PracticeCategory.SECURITY,
            severity=PracticeSeverity.HIGH,
            provider="azure",
            description="Enable NSG flow logs to monitor network traffic and detect security issues.",
            rationale="Flow logs provide visibility into network traffic for security monitoring and compliance.",
            implementation_guide="Enable NSG flow logs for all Network Security Groups and send to Azure Monitor.",
            resource_types=["Microsoft.Network/networkSecurityGroups"],
            check_logic={
                "condition": "flow_logs_enabled == false",
                "threshold": None
            },
            remediation_steps=[
                "Identify NSGs without flow logs",
                "Enable NSG flow logs in Azure Monitor",
                "Configure retention policy",
                "Set up alerts for suspicious traffic"
            ],
            references=[
                "https://docs.microsoft.com/azure/network-watcher/network-watcher-nsg-flow-logs-overview"
            ]
        )

        self.practices["azure-disk-encryption"] = BestPractice(
            practice_id="azure-disk-encryption",
            name="Enable Azure Disk Encryption for VMs",
            category=PracticeCategory.SECURITY,
            severity=PracticeSeverity.CRITICAL,
            provider="azure",
            description="Enable Azure Disk Encryption for all virtual machines to protect data at rest.",
            rationale="Disk encryption protects sensitive data and meets compliance requirements.",
            implementation_guide="Enable ADE for all VMs using Azure Key Vault.",
            resource_types=["Microsoft.Compute/virtualMachines"],
            check_logic={
                "condition": "disk_encryption_enabled == false",
                "threshold": None
            },
            remediation_steps=[
                "Create or use existing Azure Key Vault",
                "Enable Disk Encryption extension on VMs",
                "Verify encryption status",
                "Set up key rotation policies"
            ],
            references=[
                "https://docs.microsoft.com/azure/security/fundamentals/azure-disk-encryption-vms"
            ]
        )

        # Reliability Practices
        self.practices["azure-availability-sets"] = BestPractice(
            practice_id="azure-availability-sets",
            name="Use Availability Sets for High Availability",
            category=PracticeCategory.RELIABILITY,
            severity=PracticeSeverity.HIGH,
            provider="azure",
            description="Deploy VMs in Availability Sets to ensure SLA compliance and high availability.",
            rationale="Availability Sets provide 99.95% SLA for VMs with fault and update domains.",
            implementation_guide="Group VMs in Availability Sets for multi-tier applications.",
            resource_types=["Microsoft.Compute/virtualMachines"],
            check_logic={
                "condition": "availability_set == null and tier != 'standalone'",
                "threshold": None
            },
            remediation_steps=[
                "Identify VMs requiring high availability",
                "Create Availability Sets",
                "Migrate VMs to Availability Sets",
                "Update deployment templates"
            ],
            references=[
                "https://docs.microsoft.com/azure/virtual-machines/availability"
            ]
        )

        # Operational Excellence Practices
        self.practices["azure-tags"] = BestPractice(
            practice_id="azure-tags",
            name="Implement Azure Resource Tagging Strategy",
            category=PracticeCategory.OPERATIONAL_EXCELLENCE,
            severity=PracticeSeverity.MEDIUM,
            provider="azure",
            description="Implement consistent tagging across all Azure resources for cost management and governance.",
            rationale="Tags enable cost allocation, resource organization, and compliance tracking.",
            implementation_guide="Define tagging strategy and enforce through Azure Policy.",
            resource_types=["*"],
            check_logic={
                "condition": "required_tags_missing == true",
                "threshold": None
            },
            remediation_steps=[
                "Define required tags (Environment, Owner, CostCenter)",
                "Create Azure Policy for tag enforcement",
                "Tag existing resources",
                "Implement tagging process for new resources"
            ],
            references=[
                "https://docs.microsoft.com/azure/azure-resource-manager/management/tag-resources"
            ]
        )

    def _load_aws_practices(self):
        """Load AWS-specific best practices."""
        
        # Cost Optimization Practices
        self.practices["aws-reserved-instances"] = BestPractice(
            practice_id="aws-reserved-instances",
            name="Use AWS Reserved Instances for Long-Term Workloads",
            category=PracticeCategory.COST_OPTIMIZATION,
            severity=PracticeSeverity.HIGH,
            provider="aws",
            description="Purchase Reserved Instances for workloads running 24/7 to save up to 75% compared to on-demand rates.",
            rationale="Reserved Instances provide significant cost savings for predictable, long-term workloads.",
            implementation_guide="Identify EC2 instances with consistent utilization and purchase appropriate RI terms.",
            resource_types=["AWS::EC2::Instance"],
            check_logic={
                "condition": "instance_lifecycle == 'on-demand' and avg_monthly_uptime > 90%",
                "threshold": 0.9
            },
            remediation_steps=[
                "Analyze EC2 utilization patterns",
                "Identify RI candidates",
                "Purchase appropriate RI term",
                "Apply RIs to eligible instances"
            ],
            references=[
                "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ri-purchasing.html"
            ]
        )

        self.practices["aws-right-sizing"] = BestPractice(
            practice_id="aws-right-sizing",
            name="Right-Size AWS EC2 Instances",
            category=PracticeCategory.COST_OPTIMIZATION,
            severity=PracticeSeverity.MEDIUM,
            provider="aws",
            description="Ensure EC2 instances are appropriately sized based on actual utilization.",
            rationale="Over-provisioned instances waste money on unused resources.",
            implementation_guide="Monitor CloudWatch metrics and resize to appropriate instance types.",
            resource_types=["AWS::EC2::Instance"],
            check_logic={
                "condition": "avg_cpu_utilization < 20% or avg_memory_utilization < 20%",
                "threshold": 0.2
            },
            remediation_steps=[
                "Review CloudWatch metrics",
                "Identify underutilized instances",
                "Select appropriate instance type",
                "Resize during maintenance window"
            ],
            references=[
                "https://docs.aws.amazon.com/cost-management/latest/userguide/right-sizing.html"
            ]
        )

        # Security Practices
        self.practices["aws-vpc-flow-logs"] = BestPractice(
            practice_id="aws-vpc-flow-logs",
            name="Enable VPC Flow Logs",
            category=PracticeCategory.SECURITY,
            severity=PracticeSeverity.HIGH,
            provider="aws",
            description="Enable VPC flow logs to monitor network traffic and detect security issues.",
            rationale="Flow logs provide visibility into network traffic for security monitoring and compliance.",
            implementation_guide="Enable VPC flow logs for all VPCs and send to CloudWatch Logs or S3.",
            resource_types=["AWS::EC2::VPC"],
            check_logic={
                "condition": "flow_logs_enabled == false",
                "threshold": None
            },
            remediation_steps=[
                "Identify VPCs without flow logs",
                "Enable VPC flow logs",
                "Configure destination (CloudWatch Logs or S3)",
                "Set up log retention and analysis"
            ],
            references=[
                "https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html"
            ]
        )

        self.practices["aws-ebs-encryption"] = BestPractice(
            practice_id="aws-ebs-encryption",
            name="Enable EBS Encryption by Default",
            category=PracticeCategory.SECURITY,
            severity=PracticeSeverity.CRITICAL,
            provider="aws",
            description="Enable EBS encryption by default to protect data at rest.",
            rationale="EBS encryption protects sensitive data and meets compliance requirements.",
            implementation_guide="Enable EBS encryption by default in each AWS Region.",
            resource_types=["AWS::EC2::Volume"],
            check_logic={
                "condition": "encrypted == false",
                "threshold": None
            },
            remediation_steps=[
                "Enable EBS encryption by default",
                "Encrypt existing unencrypted volumes",
                "Verify encryption status",
                "Update AMIs to use encrypted volumes"
            ],
            references=[
                "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EBSEncryption.html"
            ]
        )

        # Reliability Practices
        self.practices["aws-multi-az"] = BestPractice(
            practice_id="aws-multi-az",
            name="Deploy Resources Across Multiple Availability Zones",
            category=PracticeCategory.RELIABILITY,
            severity=PracticeSeverity.HIGH,
            provider="aws",
            description="Deploy resources across multiple AZs to ensure high availability and meet SLA requirements.",
            rationale="Multi-AZ deployments provide 99.99% SLA for many AWS services.",
            implementation_guide="Use Auto Scaling Groups and RDS Multi-AZ deployments.",
            resource_types=["AWS::EC2::Instance", "AWS::RDS::DBInstance"],
            check_logic={
                "condition": "availability_zones_count < 2 and tier != 'standalone'",
                "threshold": 2
            },
            remediation_steps=[
                "Identify single-AZ resources",
                "Configure multi-AZ deployment",
                "Update DNS and load balancers",
                "Test failover procedures"
            ],
            references=[
                "https://docs.aws.amazon.com/whitepapers/high-availability-multi-region.html"
            ]
        )

        # Operational Excellence Practices
        self.practices["aws-tags"] = BestPractice(
            practice_id="aws-tags",
            name="Implement AWS Resource Tagging Strategy",
            category=PracticeCategory.OPERATIONAL_EXCELLENCE,
            severity=PracticeSeverity.MEDIUM,
            provider="aws",
            description="Implement consistent tagging across all AWS resources for cost management and governance.",
            rationale="Tags enable cost allocation, resource organization, and compliance tracking.",
            implementation_guide="Define tagging strategy and enforce through AWS Config rules.",
            resource_types=["*"],
            check_logic={
                "condition": "required_tags_missing == true",
                "threshold": None
            },
            remediation_steps=[
                "Define required tags (Environment, Owner, CostCenter)",
                "Create AWS Config rules for tag enforcement",
                "Tag existing resources",
                "Implement tagging process for new resources"
            ],
            references=[
                "https://docs.aws.amazon.com/whitepapers/resource-tagging.html"
            ]
        )

    def _load_gcp_practices(self):
        """Load GCP-specific best practices."""
        
        # Cost Optimization Practices
        self.practices["gcp-cud"] = BestPractice(
            practice_id="gcp-cud",
            name="Use Committed Use Discounts for Long-Term Workloads",
            category=PracticeCategory.COST_OPTIMIZATION,
            severity=PracticeSeverity.HIGH,
            provider="gcp",
            description="Purchase Committed Use Discounts for workloads running 24/7 to save up to 70% compared to on-demand rates.",
            rationale="CUDs provide significant cost savings for predictable, long-term workloads.",
            implementation_guide="Identify instances with consistent utilization and purchase appropriate CUDs.",
            resource_types=["compute.googleapis.com/Instance"],
            check_logic={
                "condition": "scheduling_type == 'on-demand' and avg_monthly_uptime > 90%",
                "threshold": 0.9
            },
            remediation_steps=[
                "Analyze instance utilization patterns",
                "Identify CUD candidates",
                "Purchase appropriate CUD term",
                "Apply CUDs to eligible instances"
            ],
            references=[
                "https://cloud.google.com/compute/docs/instances/signing-up-committed-use-discounts"
            ]
        )

        self.practices["gcp-right-sizing"] = BestPractice(
            practice_id="gcp-right-sizing",
            name="Right-Size GCP Compute Instances",
            category=PracticeCategory.COST_OPTIMIZATION,
            severity=PracticeSeverity.MEDIUM,
            provider="gcp",
            description="Ensure compute instances are appropriately sized based on actual utilization.",
            rationale="Over-provisioned instances waste money on unused resources.",
            implementation_guide="Monitor Cloud Monitoring metrics and resize to appropriate machine types.",
            resource_types=["compute.googleapis.com/Instance"],
            check_logic={
                "condition": "avg_cpu_utilization < 20% or avg_memory_utilization < 20%",
                "threshold": 0.2
            },
            remediation_steps=[
                "Review Cloud Monitoring metrics",
                "Identify underutilized instances",
                "Select appropriate machine type",
                "Resize instances"
            ],
            references=[
                "https://cloud.google.com/compute/docs/instances/right-sizing"
            ]
        )

        # Security Practices
        self.practices["gcp-vpc-flow-logs"] = BestPractice(
            practice_id="gcp-vpc-flow-logs",
            name="Enable VPC Flow Logs",
            category=PracticeCategory.SECURITY,
            severity=PracticeSeverity.HIGH,
            provider="gcp",
            description="Enable VPC flow logs to monitor network traffic and detect security issues.",
            rationale="Flow logs provide visibility into network traffic for security monitoring and compliance.",
            implementation_guide="Enable VPC flow logs for all VPCs and send to Cloud Logging.",
            resource_types=["compute.googleapis.com/Network"],
            check_logic={
                "condition": "flow_logs_enabled == false",
                "threshold": None
            },
            remediation_steps=[
                "Identify VPCs without flow logs",
                "Enable VPC flow logs",
                "Configure destination (Cloud Logging)",
                "Set up log retention and analysis"
            ],
            references=[
                "https://cloud.google.com/vpc/docs/using-flow-logs"
            ]
        )

        self.practices["gcp-disk-encryption"] = BestPractice(
            practice_id="gcp-disk-encryption",
            name="Enable Disk Encryption for GCE Instances",
            category=PracticeCategory.SECURITY,
            severity=PracticeSeverity.CRITICAL,
            provider="gcp",
            description="Enable disk encryption for all compute instances to protect data at rest.",
            rationale="Disk encryption protects sensitive data and meets compliance requirements.",
            implementation_guide="Enable disk encryption using Customer-Managed Encryption Keys (CMEK).",
            resource_types=["compute.googleapis.com/Instance"],
            check_logic={
                "condition": "disk_encryption_enabled == false",
                "threshold": None
            },
            remediation_steps=[
                "Create or use existing Cloud KMS key",
                "Enable disk encryption on instances",
                "Verify encryption status",
                "Set up key rotation policies"
            ],
            references=[
                "https://cloud.google.com/compute/docs/disks/customer-managed-encryption"
            ]
        )

        # Reliability Practices
        self.practices["gcp-regional-resources"] = BestPractice(
            practice_id="gcp-regional-resources",
            name="Deploy Resources Across Multiple Zones",
            category=PracticeCategory.RELIABILITY,
            severity=PracticeSeverity.HIGH,
            provider="gcp",
            description="Deploy resources across multiple zones within a region for high availability.",
            rationale="Multi-zone deployments provide 99.99% SLA for many GCP services.",
            implementation_guide="Use regional Managed Instance Groups and regional Cloud SQL instances.",
            resource_types=["compute.googleapis.com/Instance", "sqladmin.googleapis.com/Instance"],
            check_logic={
                "condition": "zones_count < 2 and tier != 'standalone'",
                "threshold": 2
            },
            remediation_steps=[
                "Identify single-zone resources",
                "Configure multi-zone deployment",
                "Update load balancers",
                "Test failover procedures"
            ],
            references=[
                "https://cloud.google.com/architecture/high-availability"
            ]
        )

        # Operational Excellence Practices
        self.practices["gcp-labels"] = BestPractice(
            practice_id="gcp-labels",
            name="Implement GCP Resource Labeling Strategy",
            category=PracticeCategory.OPERATIONAL_EXCELLENCE,
            severity=PracticeSeverity.MEDIUM,
            provider="gcp",
            description="Implement consistent labeling across all GCP resources for cost management and governance.",
            rationale="Labels enable cost allocation, resource organization, and compliance tracking.",
            implementation_guide="Define labeling strategy and enforce through organization policies.",
            resource_types=["*"],
            check_logic={
                "condition": "required_labels_missing == true",
                "threshold": None
            },
            remediation_steps=[
                "Define required labels (Environment, Owner, CostCenter)",
                "Create organization policies for label enforcement",
                "Label existing resources",
                "Implement labeling process for new resources"
            ],
            references=[
                "https://cloud.google.com/resource-manager/docs/creating-managing-labels"
            ]
        )

    def get_practice(self, practice_id: str) -> BestPractice | None:
        """Get a best practice by ID."""
        return self.practices.get(practice_id)

    def list_practices(
        self, provider: str = None, category: PracticeCategory = None
    ) -> list[BestPractice]:
        """List best practices with optional filtering."""
        practices = list(self.practices.values())

        if provider:
            practices = [p for p in practices if p.provider == provider]

        if category:
            practices = [p for p in practices if p.category == category]

        return practices

    def evaluate_practice(
        self, practice_id: str, resources: list[dict]
    ) -> dict[str, Any]:
        """
        Evaluate a best practice against resources.

        Args:
            practice_id: Best practice ID
            resources: List of resource dictionaries to evaluate

        Returns:
            Dictionary with evaluation results
        """
        practice = self.practices.get(practice_id)
        if not practice:
            return {
                "success": False,
                "error": f"Best practice '{practice_id}' not found"
            }

        # Evaluate each resource
        results = []
        for resource in resources:
            evaluation = self._evaluate_resource_practice(resource, practice)
            results.append(evaluation)

        # Calculate summary
        compliant_count = sum(1 for r in results if r["status"] == PracticeStatus.COMPLIANT.value)
        non_compliant_count = sum(1 for r in results if r["status"] == PracticeStatus.NON_COMPLIANT.value)

        return {
            "success": True,
            "practice_id": practice_id,
            "practice_name": practice.name,
            "provider": practice.provider,
            "category": practice.category.value,
            "total_resources": len(results),
            "compliant_count": compliant_count,
            "non_compliant_count": non_compliant_count,
            "compliance_percentage": (compliant_count / len(results) * 100) if results else 0,
            "results": results
        }

    def _evaluate_resource_practice(
        self, resource: dict, practice: BestPractice
    ) -> dict[str, Any]:
        """Evaluate a single resource against a best practice."""
        resource_id = resource.get("id", "unknown")
        resource_type = resource.get("type", "unknown")

        # Check if resource type matches
        if practice.resource_types != ["*"]:
            if not any(pattern.lower() in resource_type.lower() for pattern in practice.resource_types):
                return {
                    "resource_id": resource_id,
                    "resource_type": resource_type,
                    "status": PracticeStatus.NOT_APPLICABLE.value,
                    "severity": PracticeSeverity.INFO.value,
                    "findings": "Resource type not applicable to this practice",
                    "recommendations": [],
                    "estimated_effort": "none",
                    "estimated_cost_impact": "none"
                }

        # Evaluate condition (simplified)
        check_logic = practice.check_logic
        condition = check_logic.get("condition", "")
        threshold = check_logic.get("threshold")

        # Simple condition evaluation
        is_compliant = self._evaluate_condition(resource, condition, threshold)

        if is_compliant:
            status = PracticeStatus.COMPLIANT
            findings = "Resource meets best practice requirements"
            recommendations = []
        else:
            status = PracticeStatus.NON_COMPLIANT
            findings = f"Resource violates best practice: {practice.description}"
            recommendations = practice.remediation_steps

        return {
            "resource_id": resource_id,
            "resource_type": resource_type,
            "status": status.value,
            "severity": practice.severity.value,
            "findings": findings,
            "recommendations": recommendations,
            "estimated_effort": self._estimate_effort(practice),
            "estimated_cost_impact": self._estimate_cost_impact(practice)
        }

    def _evaluate_condition(self, resource: dict, condition: str, threshold: Any) -> bool:
        """Evaluate a condition against resource data (simplified)."""
        # This is a simplified implementation
        # In production, you'd use a proper expression evaluator

        try:
            if "==" in condition:
                key, value = condition.split("==")
                key = key.strip()
                value = value.strip().strip("'\"")
                return str(resource.get(key, "")) == value
            elif ">" in condition:
                key, value = condition.split(">")
                key = key.strip()
                value = float(value.strip())
                return float(resource.get(key, 0)) > value
            elif "<" in condition:
                key, value = condition.split("<")
                key = key.strip()
                value = float(value.strip())
                return float(resource.get(key, 0)) < value
            elif "&&" in condition:
                # Handle AND conditions
                parts = condition.split("&&")
                return all(self._evaluate_condition(resource, part.strip(), threshold) for part in parts)
            else:
                return True  # Default to compliant if condition can't be evaluated
        except Exception:
            return True  # Default to compliant on error

    def _estimate_effort(self, practice: BestPractice) -> str:
        """Estimate implementation effort for a practice."""
        # Simple estimation based on category and severity
        if practice.severity in [PracticeSeverity.CRITICAL, PracticeSeverity.HIGH]:
            return "high"
        elif practice.severity == PracticeSeverity.MEDIUM:
            return "medium"
        else:
            return "low"

    def _estimate_cost_impact(self, practice: BestPractice) -> str:
        """Estimate cost impact of implementing a practice."""
        if practice.category == PracticeCategory.COST_OPTIMIZATION:
            return "high"  # Cost optimization practices have high positive impact
        elif practice.category == PracticeCategory.SECURITY:
            return "medium"  # Security practices have moderate cost impact
        else:
            return "low"

    def evaluate_provider_compliance(
        self, provider: str, resources: list[dict]
    ) -> dict[str, Any]:
        """
        Evaluate all practices for a specific provider.

        Args:
            provider: Cloud provider ('azure', 'aws', 'gcp')
            resources: List of resource dictionaries to evaluate

        Returns:
            Dictionary with comprehensive compliance results
        """
        provider_practices = self.list_practices(provider=provider)

        all_results = {}
        for practice in provider_practices:
            evaluation = self.evaluate_practice(practice.practice_id, resources)
            if evaluation.get("success"):
                all_results[practice.practice_id] = evaluation

        # Calculate overall compliance
        total_evaluations = sum(len(r["results"]) for r in all_results.values())
        total_compliant = sum(
            sum(1 for r in e["results"] if r["status"] == PracticeStatus.COMPLIANT.value)
            for e in all_results.values()
        )

        # Group by category
        by_category = {}
        for practice in provider_practices:
            category = practice.category.value
            if category not in by_category:
                by_category[category] = {
                    "total_practices": 0,
                    "compliant_practices": 0,
                    "practices": []
                }
            by_category[category]["total_practices"] += 1
            by_category[category]["practices"].append(practice.practice_id)

        return {
            "provider": provider,
            "total_practices": len(provider_practices),
            "total_evaluations": total_evaluations,
            "total_compliant": total_compliant,
            "overall_compliance_percentage": (total_compliant / total_evaluations * 100) if total_evaluations > 0 else 0,
            "by_category": by_category,
            "practice_results": all_results,
            "generated_at": datetime.now().isoformat()
        }

    def generate_recommendations(
        self, provider: str, resources: list[dict], max_recommendations: int = 10
    ) -> dict[str, Any]:
        """
        Generate prioritized recommendations for improvement.

        Args:
            provider: Cloud provider ('azure', 'aws', 'gcp')
            resources: List of resource dictionaries to evaluate
            max_recommendations: Maximum number of recommendations to return

        Returns:
            Dictionary with prioritized recommendations
        """
        compliance = self.evaluate_provider_compliance(provider, resources)

        # Prioritize by severity and compliance impact
        recommendations = []
        for practice_id, evaluation in compliance["practice_results"].items():
            practice = self.get_practice(practice_id)
            if practice and evaluation["non_compliant_count"] > 0:
                recommendations.append({
                    "practice_id": practice_id,
                    "practice_name": practice.name,
                    "category": practice.category.value,
                    "severity": practice.severity.value,
                    "non_compliant_count": evaluation["non_compliant_count"],
                    "compliance_percentage": evaluation["compliance_percentage"],
                    "estimated_effort": self._estimate_effort(practice),
                    "estimated_cost_impact": self._estimate_cost_impact(practice),
                    "priority_score": self._calculate_priority_score(practice, evaluation)
                })

        # Sort by priority score
        recommendations.sort(key=lambda x: x["priority_score"], reverse=True)

        return {
            "provider": provider,
            "total_recommendations": len(recommendations),
            "top_recommendations": recommendations[:max_recommendations],
            "generated_at": datetime.now().isoformat()
        }

    def _calculate_priority_score(self, practice: BestPractice, evaluation: dict) -> float:
        """Calculate priority score for a recommendation."""
        # Higher score = higher priority
        severity_weights = {
            PracticeSeverity.CRITICAL: 4.0,
            PracticeSeverity.HIGH: 3.0,
            PracticeSeverity.MEDIUM: 2.0,
            PracticeSeverity.LOW: 1.0,
            PracticeSeverity.INFO: 0.5
        }

        category_weights = {
            PracticeCategory.SECURITY: 1.5,
            PracticeCategory.COST_OPTIMIZATION: 1.3,
            PracticeCategory.RELIABILITY: 1.2,
            PracticeCategory.OPERATIONAL_EXCELLENCE: 1.0,
            PracticeCategory.PERFORMANCE: 0.8,
            PracticeCategory.SUSTAINABILITY: 0.6
        }

        severity_weight = severity_weights.get(practice.severity, 1.0)
        category_weight = category_weights.get(practice.category, 1.0)
        impact_weight = (100 - evaluation["compliance_percentage"]) / 100

        return severity_weight * category_weight * impact_weight * 10

    def _practice_to_dict(self, practice: BestPractice) -> dict[str, Any]:
        """Convert best practice to dictionary."""
        return {
            "practice_id": practice.practice_id,
            "name": practice.name,
            "category": practice.category.value,
            "severity": practice.severity.value,
            "provider": practice.provider,
            "description": practice.description,
            "rationale": practice.rationale,
            "implementation_guide": practice.implementation_guide,
            "resource_types": practice.resource_types,
            "check_logic": practice.check_logic,
            "remediation_steps": practice.remediation_steps,
            "references": practice.references
        }
