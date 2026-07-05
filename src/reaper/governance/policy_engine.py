"""
Cross-Cloud Policy Templates System

Unified policy definition and enforcement system that works across
Azure, AWS, and GCP with provider-specific translations.
"""

import json
import logging
from typing import Any
from dataclasses import dataclass
from enum import Enum

from reaper.utils.error_handler import get_logger

logger = get_logger(__name__)


class PolicyCategory(Enum):
    """Categories of governance policies"""
    COST_OPTIMIZATION = "cost_optimization"
    SECURITY_GOVERNANCE = "security_governance"
    OPERATIONAL_EXCELLENCE = "operational_excellence"
    SUSTAINABILITY = "sustainability"
    COMPLIANCE = "compliance"


class PolicySeverity(Enum):
    """Severity levels for policy violations"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PolicyStatus(Enum):
    """Status of policy definitions"""
    ACTIVE = "active"
    DRAFT = "draft"
    DISABLED = "disabled"
    ARCHIVED = "archived"


@dataclass
class PolicyTemplate:
    """Universal policy template that can be translated to provider-specific implementations"""
    policy_id: str
    name: str
    category: PolicyCategory
    severity: PolicySeverity
    description: str
    universal_rules: list[dict]
    provider_translations: dict[str, list[dict]]
    version: int = 1
    status: PolicyStatus = PolicyStatus.DRAFT


class CrossCloudPolicyEngine:
    """
    Unified policy definition and enforcement system that works across
    Azure, AWS, and GCP with provider-specific translations.
    """

    def __init__(self):
        """Initialize the policy engine with default templates."""
        self.templates: dict[str, PolicyTemplate] = {}
        self._load_default_templates()

    def _load_default_templates(self):
        """Load default policy templates for common governance scenarios."""
        
        # Cost Optimization Policies
        self.templates["vm-size-limits"] = PolicyTemplate(
            policy_id="vm-size-limits",
            name="VM Size Cost Guardrail",
            category=PolicyCategory.COST_OPTIMIZATION,
            severity=PolicySeverity.HIGH,
            description="Prevents oversized VM instances and recommends cost-effective alternatives",
            universal_rules=[
                {
                    "resource_type": "compute",
                    "condition": "hourly_cost > 1.0",
                    "action": "alert",
                    "exceptions": ["environment:production"]
                }
            ],
            provider_translations={
                "azure": [
                    {
                        "resource_type": "Microsoft.Compute/virtualMachines",
                        "condition": "sku in ['Standard_D64s_v3', 'Standard_E64s_v3', 'Standard_M64s_v2']",
                        "enforcement": "azure_policy",
                        "parameters": {
                            "policyDefinitionId": "/providers/Microsoft.Authorization/policyDefinitions/da66fb3e-0c98-4f6b-9c75-919bc3ffdb13",
                            "displayName": "VM Size Cost Guardrail"
                        }
                    }
                ],
                "aws": [
                    {
                        "resource_type": "AWS::EC2::Instance",
                        "condition": "InstanceType in ['x1.32xlarge', 'x2iezn.12xlarge', 'p4d.24xlarge']",
                        "enforcement": "config_rule",
                        "parameters": {
                            "ConfigRuleName": "vm-size-cost-guardrail",
                            "SourceIdentifier": "AWS_CONFIG_RULE"
                        }
                    }
                ],
                "gcp": [
                    {
                        "resource_type": "compute.googleapis.com/Instance",
                        "condition": "machineType in ['n1-highmem-96', 'n1-highcpu-96', 'm1-ultramem-160']",
                        "enforcement": "organization_policy",
                        "parameters": {
                            "constraint": "compute.vmCanIpmi",
                            "policyType": "boolean"
                        }
                    }
                ]
            }
        )

        # Security Governance Policies
        self.templates["encryption-requirements"] = PolicyTemplate(
            policy_id="encryption-requirements",
            name="Data Encryption at Rest",
            category=PolicyCategory.SECURITY_GOVERNANCE,
            severity=PolicySeverity.CRITICAL,
            description="Ensures all storage resources have encryption enabled",
            universal_rules=[
                {
                    "resource_type": "storage",
                    "condition": "encryption_enabled == false",
                    "action": "block",
                    "exceptions": []
                }
            ],
            provider_translations={
                "azure": [
                    {
                        "resource_type": "Microsoft.Storage/storageAccounts",
                        "condition": "encryption.enabled == false",
                        "enforcement": "azure_policy",
                        "parameters": {
                            "policyDefinitionId": "/providers/Microsoft.Authorization/policyDefinitions/7ff53491-492d-4b75-970f-c24bd926d53a",
                            "displayName": "Storage accounts should have encryption at rest enabled"
                        }
                    }
                ],
                "aws": [
                    {
                        "resource_type": "AWS::S3::Bucket",
                        "condition": "BucketEncryption == null",
                        "enforcement": "config_rule",
                        "parameters": {
                            "ConfigRuleName": "s3-bucket-encryption-enabled",
                            "SourceIdentifier": "S3_BUCKET_ENCRYPTION_ENABLED"
                        }
                    }
                ],
                "gcp": [
                    {
                        "resource_type": "storage.googleapis.com/Bucket",
                        "condition": "encryption.defaultKmsKeyName == null",
                        "enforcement": "organization_policy",
                        "parameters": {
                            "constraint": "storage.uniformBucketLevelAccess",
                            "policyType": "boolean"
                        }
                    }
                ]
            }
        )

        # Operational Excellence Policies
        self.templates["tagging-compliance"] = PolicyTemplate(
            policy_id="tagging-compliance",
            name="Resource Tagging Compliance",
            category=PolicyCategory.OPERATIONAL_EXCELLENCE,
            severity=PolicySeverity.MEDIUM,
            description="Ensures all resources have required tags for cost attribution",
            universal_rules=[
                {
                    "resource_type": "*",
                    "condition": "tags.required_missing == true",
                    "action": "alert",
                    "exceptions": []
                }
            ],
            provider_translations={
                "azure": [
                    {
                        "resource_type": "*",
                        "condition": "tags['owner'] == null || tags['project'] == null",
                        "enforcement": "azure_policy",
                        "parameters": {
                            "policyDefinitionId": "/providers/Microsoft.Authorization/policyDefinitions/93607586-8e29-4d8f-b83b-44904759b561",
                            "displayName": "Require tags on resources"
                        }
                    }
                ],
                "aws": [
                    {
                        "resource_type": "*",
                        "condition": "Tags['Owner'] == null || Tags['Project'] == null",
                        "enforcement": "config_rule",
                        "parameters": {
                            "ConfigRuleName": "required-tags-compliance",
                            "SourceIdentifier": "REQUIRED_TAGS"
                        }
                    }
                ],
                "gcp": [
                    {
                        "resource_type": "*",
                        "condition": "labels['owner'] == null || labels['project'] == null",
                        "enforcement": "organization_policy",
                        "parameters": {
                            "constraint": "compute.requireShieldedVm",
                            "policyType": "boolean"
                        }
                    }
                ]
            }
        )

        # Sustainability Policies
        self.templates["carbon-intensity-limits"] = PolicyTemplate(
            policy_id="carbon-intensity-limits",
            name="Regional Carbon Intensity Limits",
            category=PolicyCategory.SUSTAINABILITY,
            severity=PolicySeverity.MEDIUM,
            description="Limits resource deployment in high-carbon intensity regions",
            universal_rules=[
                {
                    "resource_type": "compute",
                    "condition": "region_carbon_intensity > 500",
                    "action": "recommend",
                    "exceptions": ["region:eu-central-1", "region:us-west-2"]
                }
            ],
            provider_translations={
                "azure": [
                    {
                        "resource_type": "Microsoft.Compute/virtualMachines",
                        "condition": "location in ['eastasia', 'southeastasia', 'australiaeast']",
                        "enforcement": "azure_policy",
                        "parameters": {
                            "policyDefinitionId": "/providers/Microsoft.Authorization/policyDefinitions/custom-carbon-intensity",
                            "displayName": "Regional Carbon Intensity Limits"
                        }
                    }
                ],
                "aws": [
                    {
                        "resource_type": "AWS::EC2::Instance",
                        "condition": "Region in ['ap-southeast-1', 'ap-south-1', 'sa-east-1']",
                        "enforcement": "config_rule",
                        "parameters": {
                            "ConfigRuleName": "carbon-intensity-limits",
                            "SourceIdentifier": "CUSTOM_LAMBDA"
                        }
                    }
                ],
                "gcp": [
                    {
                        "resource_type": "compute.googleapis.com/Instance",
                        "condition": "zone in ['asia-southeast1-*', 'asia-south1-*', 'southamerica-east1-*']",
                        "enforcement": "organization_policy",
                        "parameters": {
                            "constraint": "compute.restrictSharedVpcPeering",
                            "policyType": "list"
                        }
                    }
                ]
            }
        )

    def get_template(self, policy_id: str) -> PolicyTemplate | None:
        """Get a policy template by ID."""
        return self.templates.get(policy_id)

    def list_templates(
        self, category: PolicyCategory = None, status: PolicyStatus = None
    ) -> list[PolicyTemplate]:
        """List policy templates with optional filtering."""
        templates = list(self.templates.values())

        if category:
            templates = [t for t in templates if t.category == category]

        if status:
            templates = [t for t in templates if t.status == status]

        return templates

    def create_template(self, template: PolicyTemplate) -> dict[str, Any]:
        """Create a new policy template."""
        if template.policy_id in self.templates:
            return {
                "success": False,
                "error": f"Policy template with ID '{template.policy_id}' already exists"
            }

        self.templates[template.policy_id] = template
        return {
            "success": True,
            "message": f"Policy template '{template.policy_id}' created successfully",
            "template": self._template_to_dict(template)
        }

    def update_template(self, policy_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Update an existing policy template."""
        template = self.templates.get(policy_id)
        if not template:
            return {
                "success": False,
                "error": f"Policy template '{policy_id}' not found"
            }

        # Update version
        template.version += 1

        # Apply updates
        for key, value in updates.items():
            if hasattr(template, key):
                setattr(template, key, value)

        return {
            "success": True,
            "message": f"Policy template '{policy_id}' updated to version {template.version}",
            "template": self._template_to_dict(template)
        }

    def delete_template(self, policy_id: str) -> dict[str, Any]:
        """Delete a policy template."""
        if policy_id not in self.templates:
            return {
                "success": False,
                "error": f"Policy template '{policy_id}' not found"
            }

        del self.templates[policy_id]
        return {
            "success": True,
            "message": f"Policy template '{policy_id}' deleted successfully"
        }

    def evaluate_policy_compliance(
        self, policy_id: str, resources: list[dict], provider: str
    ) -> dict[str, Any]:
        """
        Evaluate compliance of resources against a policy template.

        Args:
            policy_id: Policy template ID
            resources: List of resource dictionaries to evaluate
            provider: Cloud provider ('azure', 'aws', 'gcp')

        Returns:
            Dictionary with compliance results
        """
        template = self.templates.get(policy_id)
        if not template:
            return {
                "success": False,
                "error": f"Policy template '{policy_id}' not found"
            }

        # Get provider-specific rules
        provider_rules = template.provider_translations.get(provider, [])
        if not provider_rules:
            return {
                "success": False,
                "error": f"No rules defined for provider '{provider}'"
            }

        # Evaluate each resource
        results = []
        for resource in resources:
            compliance_result = self._evaluate_resource_compliance(
                resource, provider_rules, template.universal_rules
            )
            results.append(compliance_result)

        # Calculate summary
        compliant_count = sum(1 for r in results if r["compliant"])
        non_compliant_count = len(results) - compliant_count

        return {
            "success": True,
            "policy_id": policy_id,
            "provider": provider,
            "total_resources": len(results),
            "compliant_count": compliant_count,
            "non_compliant_count": non_compliant_count,
            "compliance_percentage": (compliant_count / len(results) * 100) if results else 0,
            "results": results
        }

    def _evaluate_resource_compliance(
        self, resource: dict, provider_rules: list[dict], universal_rules: list[dict]
    ) -> dict[str, Any]:
        """Evaluate a single resource against policy rules."""
        resource_id = resource.get("id", "unknown")
        resource_type = resource.get("type", "unknown")
        
        violations = []
        compliant = True

        # Evaluate provider-specific rules
        for rule in provider_rules:
            if self._matches_resource_type(resource, rule.get("resource_type")):
                if self._evaluate_condition(resource, rule.get("condition")):
                    violations.append({
                        "rule": rule.get("resource_type"),
                        "condition": rule.get("condition"),
                        "action": rule.get("action"),
                        "enforcement": rule.get("enforcement")
                    })
                    compliant = False

        # Evaluate universal rules
        for rule in universal_rules:
            if self._matches_resource_type(resource, rule.get("resource_type")):
                if self._evaluate_condition(resource, rule.get("condition")):
                    violations.append({
                        "rule": rule.get("resource_type"),
                        "condition": rule.get("condition"),
                        "action": rule.get("action"),
                        "enforcement": "universal"
                    })
                    compliant = False

        return {
            "resource_id": resource_id,
            "resource_type": resource_type,
            "compliant": compliant,
            "violations": violations
        }

    def _matches_resource_type(self, resource: dict, pattern: str) -> bool:
        """Check if resource matches the pattern."""
        if pattern == "*":
            return True
        
        resource_type = resource.get("type", "")
        return pattern.lower() in resource_type.lower()

    def _evaluate_condition(self, resource: dict, condition: str) -> bool:
        """Evaluate a condition against resource data (simplified)."""
        # This is a simplified implementation
        # In production, you'd use a proper expression evaluator
        
        try:
            # Simple evaluation for common conditions
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
            elif " in " in condition:
                # Evaluate "in" operator - check if value is in a list or substring
                # Format: "key in [value1, value2, value3]" or "substring in string"
                parts = condition.split(" in ")
                if len(parts) != 2:
                    return False
                
                key = parts[0].strip()
                target = parts[1].strip()
                
                # Get the resource value
                resource_value = resource.get(key, "")
                
                # Check if target is a list (starts with '[')
                if target.startswith("[") and target.endswith("]"):
                    # Parse list: [value1, value2, value3]
                    try:
                        # Remove brackets and split by comma
                        list_content = target[1:-1].strip()
                        if not list_content:
                            return False
                        
                        # Parse list items
                        list_items = [item.strip().strip("'\"") for item in list_content.split(",")]
                        return str(resource_value) in list_items
                    except Exception:
                        return False
                else:
                    # Check if resource_value contains target as substring
                    target_clean = target.strip("'\"")
                    return target_clean in str(resource_value)
            else:
                return False
        except Exception:
            return False

    def _template_to_dict(self, template: PolicyTemplate) -> dict[str, Any]:
        """Convert policy template to dictionary."""
        return {
            "policy_id": template.policy_id,
            "name": template.name,
            "category": template.category.value,
            "severity": template.severity.value,
            "description": template.description,
            "universal_rules": template.universal_rules,
            "provider_translations": template.provider_translations,
            "version": template.version,
            "status": template.status.value
        }

    def generate_policy_report(self, provider: str = None) -> dict[str, Any]:
        """Generate a comprehensive policy report."""
        templates = self.list_templates(status=PolicyStatus.ACTIVE)
        
        if provider:
            templates = [t for t in templates if provider in t.provider_translations]

        return {
            "total_policies": len(templates),
            "by_category": {
                category.value: len([t for t in templates if t.category == category])
                for category in PolicyCategory
            },
            "by_severity": {
                severity.value: len([t for t in templates if t.severity == severity])
                for severity in PolicySeverity
            },
            "by_provider": {
                provider: len([t for t in templates if provider in t.provider_translations])
                for provider in ["azure", "aws", "gcp"]
            },
            "templates": [self._template_to_dict(t) for t in templates]
        }