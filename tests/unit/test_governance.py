"""
Unit tests for Governance Features

Tests for the cross-cloud governance modules including policy engine,
migration advisor, cost aggregator, and best practices engine.
"""

import unittest
from datetime import datetime

from reaper.governance.policy_engine import CrossCloudPolicyEngine, PolicyCategory, PolicySeverity, PolicyStatus
from reaper.governance.migration_advisor import CloudMigrationAdvisor
from reaper.governance.cost_aggregator import MultiCloudCostAggregator
from reaper.governance.best_practices import ProviderBestPracticesEngine, PracticeCategory


class TestPolicyEngine(unittest.TestCase):
    """Test cases for Cross-Cloud Policy Engine"""

    def setUp(self):
        """Set up test fixtures"""
        self.policy_engine = CrossCloudPolicyEngine()

    def test_list_templates(self):
        """Test listing policy templates"""
        templates = self.policy_engine.list_templates()
        self.assertIsInstance(templates, list)
        self.assertGreater(len(templates), 0)

    def test_list_templates_by_category(self):
        """Test listing policy templates filtered by category"""
        templates = self.policy_engine.list_templates(category=PolicyCategory.COST_OPTIMIZATION)
        self.assertIsInstance(templates, list)
        for template in templates:
            self.assertEqual(template.category, PolicyCategory.COST_OPTIMIZATION)

    def test_get_template(self):
        """Test getting a specific policy template"""
        template = self.policy_engine.get_template("vm-size-limits")
        self.assertIsNotNone(template)
        self.assertEqual(template.policy_id, "vm-size-limits")

    def test_create_template(self):
        """Test creating a new policy template"""
        from reaper.governance.policy_engine import PolicyTemplate

        new_template = PolicyTemplate(
            policy_id="test-policy",
            name="Test Policy",
            category=PolicyCategory.COST_OPTIMIZATION,
            severity=PolicySeverity.MEDIUM,
            description="Test policy for unit testing",
            universal_rules=[],
            provider_translations={}
        )

        result = self.policy_engine.create_template(new_template)
        self.assertTrue(result["success"])

        # Clean up
        self.policy_engine.delete_template("test-policy")

    def test_delete_template(self):
        """Test deleting a policy template"""
        from reaper.governance.policy_engine import PolicyTemplate

        # First create a template
        new_template = PolicyTemplate(
            policy_id="test-delete-policy",
            name="Test Delete Policy",
            category=PolicyCategory.COST_OPTIMIZATION,
            severity=PolicySeverity.MEDIUM,
            description="Test policy for deletion",
            universal_rules=[],
            provider_translations={}
        )
        self.policy_engine.create_template(new_template)

        # Then delete it
        result = self.policy_engine.delete_template("test-delete-policy")
        self.assertTrue(result["success"])

        # Verify it's gone
        template = self.policy_engine.get_template("test-delete-policy")
        self.assertIsNone(template)

    def test_evaluate_policy_compliance(self):
        """Test evaluating policy compliance"""
        # Use a simple test resource
        resources = [
            {
                "id": "test-resource-1",
                "type": "Microsoft.Compute/virtualMachines",
                "sku": "Standard_D64s_v3",
                "hourly_cost": 1.5
            }
        ]

        result = self.policy_engine.evaluate_policy_compliance(
            "vm-size-limits",
            resources,
            "azure"
        )

        self.assertTrue(result["success"])
        self.assertIn("compliance_percentage", result)


class TestMigrationAdvisor(unittest.TestCase):
    """Test cases for Cloud Migration Advisor"""

    def setUp(self):
        """Set up test fixtures"""
        self.migration_advisor = CloudMigrationAdvisor()

    def test_assess_migration(self):
        """Test migration assessment"""
        resource_inventory = [
            {
                "id": "vm-1",
                "type": "Microsoft.Compute/virtualMachines",
                "sku": "Standard_D2s_v3",
                "hourly_rate": 0.096
            },
            {
                "id": "storage-1",
                "type": "Microsoft.Storage/storageAccounts",
                "sku": "Standard_LRS",
                "hourly_rate": 0.018
            }
        ]

        result = self.migration_advisor.assess_migration(
            "azure",
            "aws",
            resource_inventory
        )

        self.assertTrue(result["success"])
        self.assertIn("assessment", result)
        self.assertIn("cost_analysis", result["assessment"])
        self.assertIn("risk_assessment", result["assessment"])
        self.assertIn("roi_analysis", result["assessment"])

    def test_compare_providers(self):
        """Test comparing migration options across providers"""
        resource_inventory = [
            {
                "id": "vm-1",
                "type": "Microsoft.Compute/virtualMachines",
                "sku": "Standard_D2s_v3",
                "hourly_rate": 0.096
            }
        ]

        result = self.migration_advisor.compare_providers(
            resource_inventory,
            "azure"
        )

        self.assertIn("current_provider", result)
        self.assertIn("comparisons", result)
        self.assertIn("recommended_option", result)


class TestCostAggregator(unittest.TestCase):
    """Test cases for Multi-Cloud Cost Aggregator"""

    def setUp(self):
        """Set up test fixtures"""
        self.cost_aggregator = MultiCloudCostAggregator()

    def test_convert_currency(self):
        """Test currency conversion"""
        # Test conversion from EUR to USD
        amount = 100.0
        converted = self.cost_aggregator.convert_currency(amount, "EUR", "USD")
        self.assertIsInstance(converted, float)
        self.assertGreater(converted, 0)

    def test_normalize_cost(self):
        """Test cost normalization"""
        record = self.cost_aggregator.normalize_cost(
            provider="azure",
            resource_id="resource-1",
            resource_type="Microsoft.Compute/virtualMachines",
            region="eastus",
            amount=100.0,
            currency="EUR",
            billing_period_start=datetime.now(),
            billing_period_end=datetime.now(),
            cost_type="opex"
        )

        self.assertEqual(record.provider, "azure")
        self.assertEqual(record.base_currency, "USD")
        self.assertGreater(record.converted_amount, 0)

    def test_aggregate_costs(self):
        """Test cost aggregation by provider"""
        from reaper.governance.cost_aggregator import UnifiedCostRecord

        cost_records = [
            UnifiedCostRecord(
                provider="azure",
                resource_id="resource-1",
                resource_type="Microsoft.Compute/virtualMachines",
                region="eastus",
                service_category="compute",
                original_currency="USD",
                original_amount=100.0,
                base_currency="USD",
                converted_amount=100.0,
                billing_period_start=datetime.now(),
                billing_period_end=datetime.now(),
                cost_type="opex",
                tags={}
            ),
            UnifiedCostRecord(
                provider="aws",
                resource_id="resource-2",
                resource_type="AWS::EC2::Instance",
                region="us-east-1",
                service_category="compute",
                original_currency="USD",
                original_amount=150.0,
                base_currency="USD",
                converted_amount=150.0,
                billing_period_start=datetime.now(),
                billing_period_end=datetime.now(),
                cost_type="opex",
                tags={}
            )
        ]

        result = self.cost_aggregator.aggregate_costs(cost_records, "provider")

        self.assertEqual(result["total_cost"], 250.0)
        self.assertEqual(len(result["groups"]), 2)


class TestBestPracticesEngine(unittest.TestCase):
    """Test cases for Provider Best Practices Engine"""

    def setUp(self):
        """Set up test fixtures"""
        self.best_practices_engine = ProviderBestPracticesEngine()

    def test_list_practices(self):
        """Test listing best practices"""
        practices = self.best_practices_engine.list_practices()
        self.assertIsInstance(practices, list)
        self.assertGreater(len(practices), 0)

    def test_list_practices_by_provider(self):
        """Test listing best practices filtered by provider"""
        practices = self.best_practices_engine.list_practices(provider="azure")
        self.assertIsInstance(practices, list)
        for practice in practices:
            self.assertEqual(practice.provider, "azure")

    def test_get_practice(self):
        """Test getting a specific best practice"""
        practice = self.best_practices_engine.get_practice("azure-reserved-instances")
        self.assertIsNotNone(practice)
        self.assertEqual(practice.practice_id, "azure-reserved-instances")

    def test_evaluate_practice(self):
        """Test evaluating a best practice"""
        resources = [
            {
                "id": "vm-1",
                "type": "Microsoft.Compute/virtualMachines",
                "billing_model": "pay_as_you_go",
                "avg_monthly_uptime": 95
            }
        ]

        result = self.best_practices_engine.evaluate_practice(
            "azure-reserved-instances",
            resources
        )

        self.assertTrue(result["success"])
        self.assertIn("compliance_percentage", result)

    def test_evaluate_provider_compliance(self):
        """Test evaluating all practices for a provider"""
        resources = [
            {
                "id": "vm-1",
                "type": "Microsoft.Compute/virtualMachines",
                "billing_model": "pay_as_you_go",
                "avg_monthly_uptime": 95
            }
        ]

        result = self.best_practices_engine.evaluate_provider_compliance(
            "azure",
            resources
        )

        self.assertIn("provider", result)
        self.assertIn("overall_compliance_percentage", result)
        self.assertIn("practice_results", result)


if __name__ == "__main__":
    unittest.main()
