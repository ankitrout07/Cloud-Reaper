"""
Formalized JSON schemas for the Go-Python data handoff.

This ensures the Python intelligence layer knows exactly what structure 
to expect from the Go Performance Engine's JSON output.
"""

from typing import Any, Dict, List, Optional, TypedDict


class VMReport(TypedDict):
    name: str
    size: str
    usage: float
    usage_history: List[float]
    network_in: float
    network_out: float
    disk_iops: float
    id: str
    tags: Dict[str, Optional[str]]
    is_unallocated: bool


class OrphanedResource(TypedDict):
    name: str
    tags: Optional[Dict[str, Optional[str]]]


class GoEngineScanResult(TypedDict, total=False):
    """
    Schema representing the JSON structure returned by the Go engine.
    This corresponds directly to the ScanResult struct in src/engine-go/main.go.
    """
    user_name: str
    subscription_name: str
    orphaned_disks: List[OrphanedResource]
    orphaned_snapshots: List[OrphanedResource]
    active_vms: List[str]
    vm_reports: List[VMReport]
    prices: List[Dict[str, Any]]  # Only present when Go runs with --mode prices


def validate_scan_result(data: Dict[str, Any]) -> bool:
    """
    Basic runtime validation to ensure the Go engine's JSON matches our expected schema.
    """
    required_keys = [
        "user_name",
        "subscription_name",
        "orphaned_disks",
        "orphaned_snapshots",
        "active_vms",
        "vm_reports"
    ]
    
    # In prices mode, the Go engine may omit everything except prices,
    # but based on main.go, it always serializes the empty arrays 
    # unless it only outputs Prices. Let's make it flexible.
    if "prices" in data and len(data.keys()) == 1:
        return True
        
    for key in required_keys:
        if key not in data and "prices" not in data:
            return False
            
    return True
