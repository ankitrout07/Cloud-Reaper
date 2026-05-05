import datetime

from reaper.engine.models import CostHistory, Resource

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
        is_protected=False
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
        date=datetime.datetime.now(UTC)
    )
    
    assert cost.cost == 100.50
    assert cost.currency == "USD"
    assert cost.cost_type == "ACTUAL"
