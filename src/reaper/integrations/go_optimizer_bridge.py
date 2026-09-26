"""
Go Optimizer Bridge Client
Provides async interface to the Go cost optimizer HTTP server.

This replaces the 6 _analyze_*_resource serial Python loops in
cost_optimizer.py with a single async HTTP call to the Go engine,
which runs all analysis stages in parallel goroutines.

Usage
-----
    from reaper.integrations.go_optimizer_bridge import get_optimizer_bridge

    bridge = await get_optimizer_bridge()

    # Build the batch request
    resources = [
        {
            "resource": {
                "id": "/subscriptions/.../vm1",
                "name": "vm1",
                "type": "VirtualMachine",
                "provider": "azure",
                "sku": "Standard_D2s_v3",
                "region": "eastus",
                "tags": {}
            },
            "metrics": {
                "cpu_utilization": 12.5,
                "memory_utilization": 38.0,
                "disk_utilization": 20.0,
                "network_in_mbps": 0.5,
                "network_out_mbps": 0.2,
                "iops": 100.0,
                "latency_ms": 5.0,
                "error_rate": 0.0,
                "uptime_percentage": 99.9,
                "peak_cpu_utilization": 25.0,
                "peak_memory_utilization": 45.0,
            },
            "current_cost": 120.50,
        }
    ]

    result = await bridge.analyze_resources(resources)
    # result = {"recommendations": [...], "total_potential_savings": 72.30, ...}
"""

import asyncio
from typing import Any

from reaper.integrations.go_bridge_base import (
    BaseGoBridge,
    GoBridgeConnectionError,
    create_bridge_client,
)
from reaper.utils.error_handler import get_logger

logger = get_logger("go_optimizer_bridge")


class OptimizerBridge(BaseGoBridge):
    """
    Async client for the Go cost optimizer engine.

    Replaces the serial Python loops in cost_optimizer.py with a single
    async HTTP POST to /api/v1/optimizer/analyze, which runs all analysis
    stages (compute, storage, database, network, regional arbitrage) in
    parallel goroutines on the Go side.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 7070,
        timeout: float = 60.0,
        enabled: bool = True,
    ):
        """
        Args:
            host: Go bridge server host (default: localhost)
            port: Go bridge server port (default: 7070 — same bridge as /scan)
            timeout: HTTP timeout in seconds (60 s for large batches)
            enabled: Whether the bridge is active
        """
        super().__init__(host, port, timeout, enabled)

    async def analyze_resources(
        self, resources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Analyze a batch of resources using the Go optimizer.

        Each item in ``resources`` must have:
            - resource: dict with id, name, type, provider, sku, region, tags
            - metrics:  dict with cpu_utilization, memory_utilization, etc.
            - current_cost: float (monthly USD)

        Returns the raw Go AnalyzeResponse:
            {
                "recommendations": [...],
                "total_potential_savings": 123.45,
                "resource_count": 10,
                "analyzed_at": "2026-09-26T..."
            }

        Falls back to an empty result on connection failure so the Python
        pipeline can continue with the ML stages.
        """
        try:
            import httpx

            client = await self._get_client()
            url = f"{self.base_url}/api/v1/optimizer/analyze"
            resp = await client.post(url, json={"resources": resources})
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning(
                f"[go_optimizer_bridge] analyze_resources failed ({exc}); "
                "returning empty recommendations."
            )
            return {"recommendations": [], "total_potential_savings": 0.0, "resource_count": 0}

    async def analyze_single(
        self,
        resource: dict[str, Any],
        metrics: dict[str, Any],
        current_cost: float,
    ) -> list[dict[str, Any]]:
        """
        Convenience wrapper to analyze a single resource.

        Returns the list of recommendation dicts for this resource.
        """
        result = await self.analyze_resources(
            [{"resource": resource, "metrics": metrics, "current_cost": current_cost}]
        )
        return result.get("recommendations", [])


# ── Factory / singleton ──────────────────────────────────────────────────────

def create_optimizer_bridge(**kwargs) -> OptimizerBridge:
    """Create an optimizer bridge with standard configuration."""
    return create_bridge_client(OptimizerBridge, "optimizer", **kwargs)


_global_optimizer_bridge: OptimizerBridge | None = None
_optimizer_bridge_lock = asyncio.Lock()


async def get_optimizer_bridge() -> OptimizerBridge:
    """Return (or lazily create) the global optimizer bridge singleton."""
    global _global_optimizer_bridge
    async with _optimizer_bridge_lock:
        if _global_optimizer_bridge is None:
            _global_optimizer_bridge = create_optimizer_bridge()
    return _global_optimizer_bridge


async def close_optimizer_bridge() -> None:
    """Close the global optimizer bridge singleton."""
    global _global_optimizer_bridge
    async with _optimizer_bridge_lock:
        if _global_optimizer_bridge is not None:
            await _global_optimizer_bridge.close()
            _global_optimizer_bridge = None
