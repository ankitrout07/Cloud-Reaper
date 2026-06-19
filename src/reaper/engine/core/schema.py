from __future__ import annotations

"""
Formalized JSON schemas for the Go-Python data handoff.

This ensures the Python intelligence layer knows exactly what structure
to expect from the Go Performance Engine's JSON output.
"""

from typing import Any, TypedDict


class VMReport(TypedDict):
    name: str
    size: str
    usage: float
    usage_history: list[float]
    network_in: float
    network_out: float
    disk_iops: float
    id: str
    tags: dict[str, str | None]
    is_unallocated: bool


class OrphanedResource(TypedDict):
    name: str
    tags: dict[str, str | None] | None


class GoEngineScanResult(TypedDict, total=False):
    """
    Schema representing the JSON structure returned by the Go engine.
    This corresponds directly to the ScanResult struct in src/engine-go/main.go.
    """

    user_name: str
    subscription_name: str
    orphaned_disks: list[OrphanedResource]
    orphaned_snapshots: list[OrphanedResource]
    active_vms: list[str]
    vm_reports: list[VMReport]
    prices: list[dict[str, Any]]  # Only present when Go runs with --mode prices


def validate_scan_result(data: dict[str, Any]) -> bool:
    """
    Basic runtime validation to ensure the Go engine's JSON matches our expected schema.
    """
    required_keys = [
        "user_name",
        "subscription_name",
        "orphaned_disks",
        "orphaned_snapshots",
        "active_vms",
        "vm_reports",
    ]

    # In prices mode, the Go engine may omit everything except prices,
    # but based on main.go, it always serializes the empty arrays
    # unless it only outputs Prices. Let's make it flexible.
    if "prices" in data and len(data.keys()) == 1:
        return True

    return all(key in data or "prices" in data for key in required_keys)
