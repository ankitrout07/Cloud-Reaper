"""
Go Classifier Bridge Client
Provides async interface to the Go workload classifier HTTP endpoint.

This replaces WorkloadClassifier.batch_classify() in scheduler.py with a
single async HTTP call to /api/v1/classifier/classify.  The Go side runs
classification in parallel goroutines for large batches (≥ 50 resources),
which is significantly faster than a Python for-loop under the GIL.

Usage
-----
    from reaper.integrations.go_classifier_bridge import get_classifier_bridge

    bridge = await get_classifier_bridge()

    resources = [
        {"id": "res-001", "name": "prod-vm-01", "tags": {"environment": "production"}},
        {"id": "res-002", "name": "dev-vm-99",  "tags": {}},
    ]

    result = await bridge.classify_batch(resources)
    # result = {
    #     "classifications": {"res-001": "production", "res-002": "dev-test"},
    #     "production_count": 1,
    #     "dev_test_count": 1,
    # }

    # Or use the drop-in replacement for WorkloadClassifier.batch_classify():
    mapping = result["classifications"]   # dict[str, str]
"""

import asyncio
from typing import Any

from reaper.integrations.go_bridge_base import BaseGoBridge, create_bridge_client
from reaper.utils.error_handler import get_logger

logger = get_logger("go_classifier_bridge")


class ClassifierBridge(BaseGoBridge):
    """
    Async client for the Go workload classifier.

    Drop-in replacement for WorkloadClassifier.batch_classify() in
    scheduler.py.  For batches < 50 resources the call overhead may not
    be worth it — use the Python fallback in that case.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 7070,
        timeout: float = 30.0,
        enabled: bool = True,
    ):
        """
        Args:
            host: Go bridge server host
            port: Go bridge server port (default 7070 — same bridge as /scan)
            timeout: HTTP timeout
            enabled: Whether the bridge is active
        """
        super().__init__(host, port, timeout, enabled)

    async def classify_batch(
        self, resources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Classify a batch of resources.

        Each item in ``resources`` must have:
            - id:   str (resource ID or name)
            - name: str
            - tags: dict[str, str]

        Returns:
            {
                "classifications": {
                    "<id>": "production" | "dev-test",
                    ...
                },
                "production_count": int,
                "dev_test_count":   int,
            }

        Falls back to an empty classifications dict on connection failure,
        which causes scheduler.py to treat all resources as "production"
        (safe default).
        """
        if not resources:
            return {"classifications": {}, "production_count": 0, "dev_test_count": 0}

        try:
            client = await self._get_client()
            url = f"{self.base_url}/api/v1/classifier/classify"
            resp = await client.post(url, json={"resources": resources})
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning(
                f"[go_classifier_bridge] classify_batch failed ({exc}); "
                "falling back to Python classifier."
            )
            return {"classifications": {}, "production_count": 0, "dev_test_count": 0}

    async def classify_single(
        self, resource_id: str, name: str, tags: dict[str, str]
    ) -> str:
        """
        Classify a single resource.

        Returns "production" or "dev-test".
        Defaults to "production" on any error.
        """
        result = await self.classify_batch(
            [{"id": resource_id, "name": name, "tags": tags}]
        )
        return result.get("classifications", {}).get(resource_id, "production")


# ── Factory / singleton ──────────────────────────────────────────────────────

def create_classifier_bridge(**kwargs) -> ClassifierBridge:
    """Create a classifier bridge with standard configuration."""
    return create_bridge_client(ClassifierBridge, "classifier", **kwargs)


_global_classifier_bridge: ClassifierBridge | None = None
_classifier_bridge_lock = asyncio.Lock()


async def get_classifier_bridge() -> ClassifierBridge:
    """Return (or lazily create) the global classifier bridge singleton."""
    global _global_classifier_bridge
    async with _classifier_bridge_lock:
        if _global_classifier_bridge is None:
            _global_classifier_bridge = create_classifier_bridge()
    return _global_classifier_bridge


async def close_classifier_bridge() -> None:
    """Close the global classifier bridge singleton."""
    global _global_classifier_bridge
    async with _classifier_bridge_lock:
        if _global_classifier_bridge is not None:
            await _global_classifier_bridge.close()
            _global_classifier_bridge = None
