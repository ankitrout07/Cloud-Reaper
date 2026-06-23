from __future__ import annotations

import logging
import os
from typing import Any

from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient

logger = logging.getLogger(__name__)


class AzureRemediator:
    """
    Executes physical resource modifications in Azure.
    Protected by the ENABLE_REMEDIATION environment variable.
    """

    def __init__(self, subscription_id: str | None = None):
        self.subscription_id = subscription_id or os.getenv("AZURE_SUBSCRIPTION_ID")
        self.is_dry_run = os.getenv("ENABLE_REMEDIATION", "false").lower() != "true"

        if not self.subscription_id:
            logger.warning("[AzureRemediator] No Azure Subscription ID configured.")
            self.compute = None
            return

        try:
            self.credentials = DefaultAzureCredential()
            # pyrefly: ignore [bad-argument-type]
            self.compute = ComputeManagementClient(self.credentials, self.subscription_id)
        except Exception as e:
            logger.error(f"[AzureRemediator] Failed to initialize Azure SDK clients: {e}")
            self.compute = None

        # Pre-defined aggressive downsizing matrix mapping expensive SKUs to cheaper alternatives
        self.DOWNSIZE_MATRIX = {
            # Compute Optimized
            "standard_f4s_v2": "Standard_B4ms",
            "standard_f2s_v2": "Standard_B2ms",
            # General Purpose
            "standard_d4s_v3": "Standard_B4ms",
            "standard_d2s_v3": "Standard_B2ms",
            "standard_d4s_v4": "Standard_B4ms",
            "standard_d2s_v4": "Standard_B2ms",
            "standard_d4s_v5": "Standard_B4ms",
            "standard_d2s_v5": "Standard_B2ms",
            # Memory Optimized
            "standard_e4s_v3": "Standard_B4ms",
            "standard_e2s_v3": "Standard_B2ms",
        }

    def _parse_resource_id(self, resource_id: str) -> tuple[str, str]:
        """Extracts resource group and resource name from an Azure resource ID."""
        parts = resource_id.strip("/").split("/")
        # /subscriptions/{sub}/resourceGroups/{rg}/providers/{provider}/{type}/{name}
        try:
            rg_index = parts.index("resourceGroups")
            rg_name = parts[rg_index + 1]
            resource_name = parts[-1]
            return rg_name, resource_name
        except (ValueError, IndexError):
            return "", ""

    def downsize_vm(self, resource_id: str, target_size: str | None = None) -> dict[str, Any]:
        """
        Downscales a VM to a cheaper SKU.
        If target_size is None, determines the best SKU via the downsizing matrix.
        """
        if not self.compute:
            return {"status": "error", "message": "Azure credentials not configured."}

        rg_name, vm_name = self._parse_resource_id(resource_id)
        if not rg_name or not vm_name:
            return {"status": "error", "message": f"Invalid resource ID: {resource_id}"}

        try:
            vm = self.compute.virtual_machines.get(rg_name, vm_name)
            current_size = str(vm.hardware_profile.vm_size).lower()

            # Determine target size if not provided
            if not target_size:
                target_size = self.DOWNSIZE_MATRIX.get(current_size, "Standard_B2ms")

            if self.is_dry_run:
                return {
                    "status": "dry_run",
                    "message": f"[DRY-RUN] Would downsize {vm_name} from {vm.hardware_profile.vm_size} to {target_size}",
                }

            # Apply the new hardware profile
            vm.hardware_profile.vm_size = target_size

            # Initiate async update operation
            poller = self.compute.virtual_machines.begin_create_or_update(rg_name, vm_name, vm)

            return {
                "status": "processing",
                "message": f"Initiated downsizing of {vm_name} to {target_size}",
                "operation": "begin_create_or_update",
            }
        except ResourceNotFoundError:
            return {"status": "error", "message": f"VM {vm_name} not found in {rg_name}."}
        except Exception as e:
            logger.error(f"[AzureRemediator] Error downsizing VM {resource_id}: {e}")
            return {"status": "error", "message": str(e)}

    def delete_vm(self, resource_id: str) -> dict[str, Any]:
        """Safely stops and deletes an idle virtual machine."""
        if not self.compute:
            return {"status": "error", "message": "Azure credentials not configured."}

        rg_name, vm_name = self._parse_resource_id(resource_id)
        if not rg_name or not vm_name:
            return {"status": "error", "message": f"Invalid resource ID: {resource_id}"}

        try:
            if self.is_dry_run:
                return {
                    "status": "dry_run",
                    "message": f"[DRY-RUN] Would power off and delete VM {vm_name}",
                }

            # 1. Power off the VM gracefully
            self.compute.virtual_machines.begin_power_off(rg_name, vm_name)

            # 2. Issue the delete command
            # Optionally we could clean up disks and NICs, but standard delete takes care of it
            # if the resources were created with `delete_option = Delete`
            poller = self.compute.virtual_machines.begin_delete(rg_name, vm_name)

            return {
                "status": "processing",
                "message": f"Initiated deletion of idle VM {vm_name}",
                "operation": "begin_delete",
            }
        except Exception as e:
            logger.error(f"[AzureRemediator] Error deleting VM {resource_id}: {e}")
            return {"status": "error", "message": str(e)}

    def downgrade_disk(self, resource_id: str, target_tier: str = "Standard_LRS") -> dict[str, Any]:
        """Downgrades a managed disk to a cheaper storage tier."""
        if not self.compute:
            return {"status": "error", "message": "Azure credentials not configured."}

        rg_name, disk_name = self._parse_resource_id(resource_id)
        if not rg_name or not disk_name:
            return {"status": "error", "message": f"Invalid resource ID: {resource_id}"}

        try:
            if self.is_dry_run:
                return {
                    "status": "dry_run",
                    "message": f"[DRY-RUN] Would downgrade disk {disk_name} to tier {target_tier}",
                }

            from azure.mgmt.compute.models import DiskSku, DiskUpdate

            disk_update = DiskUpdate(sku=DiskSku(name=target_tier))
            poller = self.compute.disks.begin_update(rg_name, disk_name, disk_update)

            return {
                "status": "processing",
                "message": f"Initiated tier downgrade for disk {disk_name}",
                "operation": "begin_update",
            }
        except Exception as e:
            logger.error(f"[AzureRemediator] Error downgrading disk {resource_id}: {e}")
            return {"status": "error", "message": str(e)}
