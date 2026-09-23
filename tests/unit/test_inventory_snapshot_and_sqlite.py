import os
import pytest
from sqlalchemy import text
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from reaper.engine.models.resources import (
    CloudResource,
    SessionLocal,
    engine,
    _apply_sqlite_pragmas,
)
from reaper.web.app_async import app
from reaper.web.routers.resources import _read_inventory_from_db, _RESOURCE_TYPE_TO_CATEGORY


def test_sqlite_wal_and_busy_timeout():
    """Verify that SQLite connection applies WAL journal mode and busy_timeout=5000."""
    with engine.connect() as conn:
        journal_mode = conn.execute(text("PRAGMA journal_mode")).scalar()
        busy_timeout = conn.execute(text("PRAGMA busy_timeout")).scalar()
        synchronous = conn.execute(text("PRAGMA synchronous")).scalar()

        # In SQLite, in-memory or WAL mode returns 'wal'
        assert str(journal_mode).lower() in ("wal", "memory")
        assert busy_timeout == 5000
        # synchronous=NORMAL is 1
        assert synchronous in (1, 2)


def test_read_inventory_from_db_snapshot():
    """Verify reading inventory from SQLite snapshot populates categories and summary."""
    import asyncio

    with SessionLocal() as db_session:
        # Seed test resource
        test_vm = CloudResource(
            id="/subscriptions/sub-123/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-test-1",
            provider="azure",
            resource_type="virtual_machines",
            region="eastus",
            cost_attributes={
                "name": "vm-test-1",
                "type": "Microsoft.Compute/virtualMachines",
                "status": "Idle",
                "estimated_cost": 45.50,
            },
        )
        test_disk = CloudResource(
            id="/subscriptions/sub-123/resourceGroups/rg-1/providers/Microsoft.Compute/disks/disk-test-1",
            provider="azure",
            resource_type="disks",
            region="eastus",
            cost_attributes={
                "name": "disk-test-1",
                "type": "Microsoft.Compute/disks",
                "status": "Orphaned",
                "estimated_cost": 12.00,
            },
        )
        db_session.merge(test_vm)
        db_session.merge(test_disk)
        db_session.commit()

    async def _run():
        return await _read_inventory_from_db(
            category_filter="",
            status_filter="",
            search_q="",
        )

    inventory, flat, last_scanned = asyncio.run(_run())

    assert inventory["summary"]["total_resources"] >= 2
    assert inventory["summary"]["idle_resources"] >= 1
    assert inventory["summary"]["orphaned_resources"] >= 1
    assert inventory["summary"]["estimated_monthly_cost"] > 0
    assert len(inventory["virtual_machines"]) >= 1
    assert len(inventory["disks"]) >= 1


def test_get_resource_inventory_endpoint():
    """Verify GET /api/resources/inventory returns snapshot metadata instantly without live SDK calls."""
    import asyncio

    async def _run():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/resources/inventory?page=1&page_size=10")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["snapshot"] is True
            assert "data" in data
            assert "summary" in data["data"]
            assert "timestamp" in data

    asyncio.run(_run())


def test_get_resource_inventory_summary_endpoint():
    """Verify GET /api/resources/inventory/summary returns aggregate counts directly from DB."""
    import asyncio

    async def _run():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/resources/inventory/summary")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["snapshot"] is True
            assert "total_resources" in data
            assert "by_category" in data

    asyncio.run(_run())


def test_post_trigger_scan_endpoint():
    """Verify POST /api/resources/scan triggers background scan via Go bridge."""
    import asyncio

    async def _run():
        transport = ASGITransport(app=app)
        with patch("reaper.integrations.go_bridge.scan", new_callable=AsyncMock) as mock_scan:
            mock_scan.return_value = {"db_stats": {"ResourceCount": 10}}
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/resources/scan",
                    json={"subscription_id": "sub-12345", "provider": "azure"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "accepted"
                assert data["subscription_id"] == "sub-12345"

    asyncio.run(_run())


def test_go_bridge_persistent_client():
    """Verify go_bridge reuses a single persistent httpx.AsyncClient."""
    import asyncio
    from reaper.integrations.go_bridge import _get_bridge_client

    async def _run():
        client1 = await _get_bridge_client()
        client2 = await _get_bridge_client()
        assert client1 is client2
        assert not client1.is_closed

    asyncio.run(_run())
