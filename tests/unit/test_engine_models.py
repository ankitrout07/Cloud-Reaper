import datetime

from reaper.collectors.config_manager import normalize_resource
from reaper.engine.models import (
    Budget,
    BudgetAlert,
    CloudCommitment,
    CloudConnection,
    CostHistory,
    Resource,
)

try:
    from datetime import UTC
except ImportError:
    # Shim for local verification on older Python versions
    UTC = getattr(datetime, "UTC", datetime.timezone.utc)  # noqa: UP017


def test_resource_model_instantiation():
    resource = Resource(
        id="/subscriptions/123/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        name="vm1",
        type="Microsoft.Compute/virtualMachines",
        region="eastus",
        tags={"env": "prod"},
        active=True,
        is_protected=False,
    )

    assert resource.name == "vm1"
    assert resource.region == "eastus"
    assert resource.tags["env"] == "prod"
    assert resource.active is True
    assert resource.is_protected is False


def test_cost_history_model_instantiation():
    cost = CostHistory(
        resource_id="/subscriptions/123/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        cost=100.50,
        currency="USD",
        cost_type="ACTUAL",
        date=datetime.datetime.now(UTC),
    )

    assert cost.cost == 100.50
    assert cost.currency == "USD"
    assert cost.cost_type == "ACTUAL"


def test_cloud_connection_model_instantiation():
    conn = CloudConnection(
        provider_type="aws",
        connection_name="prod-aws",
        credentials={
            "access_key_id": "AKIAEXAMPLE",
            "secret_access_key": "secret",
            "region": "us-east-1",
        },
        is_active=True,
    )

    assert conn.provider_type == "aws"
    assert conn.connection_name == "prod-aws"
    assert conn.credentials["region"] == "us-east-1"
    assert conn.is_active is True


def test_budget_model_instantiation():
    budget = Budget(
        name="prod-monthly",
        scope_type="TAG",
        scope_value="Owner=ankit",
        monthly_limit=5000.00,
    )

    assert budget.name == "prod-monthly"
    assert budget.scope_type == "TAG"
    assert budget.scope_value == "Owner=ankit"
    assert float(budget.monthly_limit) == 5000.00


def test_budget_alert_model_instantiation():
    alert = BudgetAlert(
        budget_id=1,
        threshold_percentage=85.00,
        notification_channel="DISCORD",
        is_triggered=False,
    )

    assert alert.budget_id == 1
    assert float(alert.threshold_percentage) == 85.00
    assert alert.notification_channel == "DISCORD"
    assert alert.is_triggered is False


def test_cloud_commitment_model_instantiation():
    commitment = CloudCommitment(
        id="arn:aws:savingsplans::123:sp/sp-abc",
        provider_type="aws",
        commitment_type="SAVINGS_PLAN",
        hourly_commitment=1.25,
        status="ACTIVE",
        expiration_date=datetime.datetime(2027, 6, 1, tzinfo=UTC),
    )

    assert commitment.id == "arn:aws:savingsplans::123:sp/sp-abc"
    assert commitment.provider_type == "aws"
    assert commitment.commitment_type == "SAVINGS_PLAN"
    assert float(commitment.hourly_commitment) == 1.25
    assert commitment.status == "ACTIVE"


def test_normalize_aws_resource():
    resource = {
        "InstanceId": "i-12345",
        "InstanceType": "t3.micro",
        "tags": [{"Key": "Name", "Value": "web-server"}],
        "region": "us-east-1",
        "hourly_cost": 0.0116,
    }
    normalized = normalize_resource("aws", resource)

    assert normalized["id"] == "i-12345"
    assert normalized["name"] == "web-server"
    assert normalized["type"] == "ComputeResource"
    assert normalized["region"] == "us-east-1"
    assert normalized["hourly_cost"] == 0.0116
    assert normalized["provider"] == "aws"
