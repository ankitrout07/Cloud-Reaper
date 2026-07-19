from __future__ import annotations

import asyncio
import datetime
import json as json_module

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from reaper.collectors.providers.azure_collector import AzureCollector
from reaper.utils.error_handler import get_logger


def jsonify(*args, **kwargs):
    from fastapi.responses import JSONResponse
    content = args[0] if args and isinstance(args[0], dict) else kwargs
    status_code = kwargs.pop("status_code", 200)
    return JSONResponse(content=content, status_code=status_code)

logger = get_logger(__name__)

router = APIRouter(tags=["resources"])

@router.get("/api/resources/inventory")
async def get_resource_inventory(request: Request):
    """Get comprehensive inventory of all Azure resources for cost optimization with streaming response.

    Query params:
        page      (int, default 1)  - page number for server-side pagination
        page_size (int, default 50) - items per page (max 200)
        category  (str, optional)   - filter by resource category
        status    (str, optional)   - filter by status (Idle, Orphaned, Active, …)
        q         (str, optional)   - text search against name / type
        stream    (bool, default False) - enable streaming response for large datasets
    """
    try:
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = min(200, max(1, int(request.query_params.get("page_size", 50))))
        category_filter = request.query_params.get("category", "").strip().lower()
        status_filter = request.query_params.get("status", "").strip()
        search_q = request.query_params.get("q", "").strip().lower()
        stream_response = request.query_params.get("stream", "false").lower() == "true"

        def _get_collector():
            return AzureCollector()

        az = await asyncio.to_thread(_get_collector)

        inventory: dict[str, list | dict] = {
            "virtual_machines": [],
            "disks": [],
            "storage_accounts": [],
            "network_resources": [],
            "databases": [],
            "app_services": [],
            "functions": [],
            "kubernetes": [],
            "key_vaults": [],
            "cognitive_services": [],
            "monitoring": [],
            "messaging": [],
            "other_resources": [],
            "summary": {
                "total_resources": 0,
                "idle_resources": 0,
                "orphaned_resources": 0,
                "estimated_monthly_cost": 0.0,
                "by_category": {},
            },
        }

        collected_ids = set()
        _cat_map = {
            "virtual_machines": "virtual_machines",
            "disks": "disks",
            "storage_accounts": "storage_accounts",
            "network_resources": "network_resources",
            "databases": "databases",
            "cosmos_db": "databases",
            "app_services": "app_services",
            "functions": "functions",
            "kubernetes": "kubernetes",
            "container_instances": "other_resources",
            "key_vaults": "key_vaults",
            "redis_caches": "messaging",
            "data_factories": "other_resources",
            "logic_apps": "other_resources",
            "event_hubs": "messaging",
            "service_bus": "messaging",
            "iot_hubs": "messaging",
            "cognitive_services": "cognitive_services",
            "monitoring": "monitoring",
            "cdn_profiles": "other_resources",
            "api_management": "other_resources",
            "recovery_vaults": "other_resources",
            "other_resources": "other_resources",
        }

        def _add(category: str, resource: dict) -> None:
            """Append resource to category list and update summary counts."""
            r_id = resource.get("id")
            if r_id:
                collected_ids.add(r_id.lower())

            target_cat = _cat_map.get(category, "other_resources")
            resource["category"] = target_cat
            inventory[target_cat].append(resource)  # type: ignore[union-attr]

            summary = inventory["summary"]
            summary["total_resources"] += 1  # type: ignore[index]
            summary["by_category"][target_cat] = summary["by_category"].get(target_cat, 0) + 1  # type: ignore[index]
            summary["estimated_monthly_cost"] += resource.get("estimated_cost", 0.0)  # type: ignore[index]
            if resource.get("status") in ("Idle",):
                summary["idle_resources"] += 1  # type: ignore[index]
            elif resource.get("status") in ("Orphaned", "Unassociated", "Empty"):
                summary["orphaned_resources"] += 1  # type: ignore[index]

        # ---- Virtual Machines ----
        try:
            # Parallel execution: fetch VM inventory and idle VMs concurrently
            vms_result = await asyncio.to_thread(az.get_vm_inventory)
            idle_vms_result = await asyncio.to_thread(az.get_idle_vms, cpu_threshold=5.0)

            vms = vms_result
            idle_vms = idle_vms_result
            idle_vm_names = {vm["name"] for vm in idle_vms}

            # Batch cost estimation for all VMs
            vm_cost_tasks = []
            for vm in vms:
                vm_cost_tasks.append(
                    asyncio.to_thread(
                        az.estimate_resource_cost,
                        "microsoft.compute/virtualmachines",
                        vm.get("size", ""),
                        vm.get("location", ""),
                    )
                )

            vm_costs = await asyncio.gather(*vm_cost_tasks)

            for vm, cost in zip(vms, vm_costs, strict=False):
                is_idle = vm["name"] in idle_vm_names
                _add(
                    "virtual_machines",
                    {
                        "id": vm["id"],
                        "name": vm["name"],
                        "type": "Microsoft.Compute/virtualMachines",
                        "location": vm["location"],
                        "size": vm["size"],
                        "status": "Idle" if is_idle else "Active",
                        "tags": vm["tags"],
                        "category": "compute",
                        "can_dismiss": is_idle,
                        "dismiss_reason": "Idle VM with low CPU utilization" if is_idle else None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching VMs: {e}")

        # ---- Disks ----
        try:
            # Parallel execution: fetch orphaned disks and all disks concurrently
            orphaned_disks_result = await asyncio.to_thread(az.get_orphaned_disks)
            all_disks_result = await asyncio.to_thread(lambda: list(az.compute.disks.list()))

            orphaned_disks_data = orphaned_disks_result
            orphaned_disk_names = {d["name"] for d in orphaned_disks_data.get("disks", [])}
            all_disks = all_disks_result

            # Batch cost estimation for all disks
            disk_cost_tasks = []
            for disk in all_disks:
                disk_cost_tasks.append(
                    asyncio.to_thread(
                        az.estimate_resource_cost,
                        "microsoft.compute/disks",
                        disk.sku.name if disk.sku else "",
                        disk.location,
                    )
                )

            disk_costs = await asyncio.gather(*disk_cost_tasks)

            for disk, cost in zip(all_disks, disk_costs, strict=False):
                is_orphaned = disk.name in orphaned_disk_names
                _add(
                    "disks",
                    {
                        "id": disk.id,
                        "name": disk.name,
                        "type": "Microsoft.Compute/disks",
                        "location": disk.location,
                        "size_gb": disk.disk_size_gb,
                        "sku": disk.sku.name if disk.sku else "Unknown",
                        "status": "Orphaned" if is_orphaned else "Attached",
                        "category": "storage",
                        "can_dismiss": is_orphaned,
                        "dismiss_reason": "Unattached disk with no associated VM"
                        if is_orphaned
                        else None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching disks: {e}")

        # ---- Storage Accounts ----
        try:
            storage_accounts = await asyncio.to_thread(az.get_storage_accounts)

            # Batch cost estimation for all storage accounts
            storage_cost_tasks = []
            for acc in storage_accounts:
                storage_cost_tasks.append(
                    asyncio.to_thread(
                        az.estimate_resource_cost,
                        "microsoft.storage/storageaccounts",
                        acc.get("sku", ""),
                        acc.get("location", ""),
                    )
                )

            storage_costs = await asyncio.gather(*storage_cost_tasks)

            for acc, cost in zip(storage_accounts, storage_costs, strict=False):
                tier = acc.get("access_tier", "Hot")
                _add(
                    "storage_accounts",
                    {
                        "id": acc["id"],
                        "name": acc["name"],
                        "type": "Microsoft.Storage/storageAccounts",
                        "location": acc["location"],
                        "sku": acc.get("sku", "Unknown"),
                        "kind": acc.get("kind", ""),
                        "access_tier": tier,
                        "status": "Cold" if tier in ("Cool", "Archive") else "Active",
                        "category": "storage",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching storage accounts: {e}")

        # ---- Network Resources ----
        try:
            # Parallel execution: fetch network resources concurrently
            ips_result = await asyncio.to_thread(az.get_unassociated_public_ips)
            lbs_result = await asyncio.to_thread(az.get_idle_load_balancers)

            # Batch cost estimation for network resources
            network_cost_tasks = []
            for ip in ips_result:
                network_cost_tasks.append(
                    asyncio.to_thread(
                        az.estimate_resource_cost,
                        "microsoft.network/publicipaddresses",
                        ip.get("sku", ""),
                        ip.get("location", ""),
                    )
                )
            for lb in lbs_result:
                network_cost_tasks.append(
                    asyncio.to_thread(
                        az.estimate_resource_cost,
                        "microsoft.network/loadbalancers",
                        lb.get("sku", ""),
                        lb.get("location", ""),
                    )
                )

            network_costs = await asyncio.gather(*network_cost_tasks)

            # Process IPs (first half of costs)
            ip_count = len(ips_result)
            ip_costs = network_costs[:ip_count]
            for ip, cost in zip(ips_result, ip_costs, strict=False):
                _add(
                    "network_resources",
                    {
                        "id": f"/subscriptions/{az.subscription_id}/providers/Microsoft.Network/publicIPAddresses/{ip['name']}",
                        "name": ip["name"],
                        "type": "Microsoft.Network/publicIPAddresses",
                        "location": ip["location"],
                        "sku": ip["sku"],
                        "status": "Unassociated",
                        "category": "network",
                        "can_dismiss": True,
                        "dismiss_reason": "Public IP with no associated resources",
                        "estimated_cost": cost,
                    },
                )

            # Process load balancers (second half of costs)
            lb_costs = network_costs[ip_count:]
            for lb, cost in zip(lbs_result, lb_costs, strict=False):
                _add(
                    "network_resources",
                    {
                        "id": f"/subscriptions/{az.subscription_id}/providers/Microsoft.Network/loadBalancers/{lb['name']}",
                        "name": lb["name"],
                        "type": "Microsoft.Network/loadBalancers",
                        "location": lb["location"],
                        "sku": lb["sku"],
                        "status": "Idle",
                        "category": "network",
                        "can_dismiss": True,
                        "dismiss_reason": "Load balancer with no backend pool members",
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching network resources: {e}")

        # ---- SQL Databases ----
        try:
            for db in az.get_sql_databases():
                cost = az.estimate_resource_cost(
                    "microsoft.sql/servers/databases", db.get("sku", ""), db.get("location", "")
                )
                _add(
                    "databases",
                    {
                        "id": db.get("id", ""),
                        "name": db.get("name", ""),
                        "type": "Microsoft.Sql/servers/databases",
                        "location": db.get("location", ""),
                        "sku": db.get("sku", "Unknown"),
                        "status": "Idle" if db.get("is_idle") else "Active",
                        "average_cpu": db.get("average_cpu", 0.0),
                        "category": "database",
                        "can_dismiss": db.get("is_idle", False),
                        "dismiss_reason": "Idle database with low utilization"
                        if db.get("is_idle")
                        else None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching SQL databases: {e}")

        # ---- App Services ----
        try:
            for plan in az.get_empty_app_service_plans():
                cost = az.estimate_resource_cost(
                    "microsoft.web/serverfarms", plan.get("sku", ""), plan.get("location", "")
                )
                _add(
                    "app_services",
                    {
                        "id": f"/subscriptions/{az.subscription_id}/providers/Microsoft.Web/serverfarms/{plan['name']}",
                        "name": plan["name"],
                        "type": "Microsoft.Web/serverfarms",
                        "location": plan["location"],
                        "sku": plan["sku"],
                        "tier": plan.get("tier", ""),
                        "status": "Empty",
                        "category": "app_services",
                        "can_dismiss": True,
                        "dismiss_reason": "App Service Plan with no assigned apps",
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching app services: {e}")

        # ---- Azure Functions ----
        try:
            for fn in az.get_function_apps():
                cost = az.estimate_resource_cost("microsoft.web/sites", "", fn.get("location", ""))
                is_stopped = fn.get("state", "Running") not in ("Running",)
                _add(
                    "functions",
                    {
                        "id": fn["id"],
                        "name": fn["name"],
                        "type": "Microsoft.Web/sites (Function)",
                        "location": fn["location"],
                        "state": fn.get("state", "Running"),
                        "runtime": fn.get("runtime", ""),
                        "status": "Stopped" if is_stopped else "Active",
                        "category": "functions",
                        "can_dismiss": is_stopped,
                        "dismiss_reason": "Function app is stopped" if is_stopped else None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching function apps: {e}")

        # ---- AKS Clusters ----
        try:
            for cluster in az.get_aks_clusters():
                cost = az.estimate_resource_cost(
                    "microsoft.containerservice/managedclusters",
                    cluster.get("sku", ""),
                    cluster.get("location", ""),
                )
                power = cluster.get("power_state", "Running")
                _add(
                    "kubernetes",
                    {
                        "id": cluster["id"],
                        "name": cluster["name"],
                        "type": "Microsoft.ContainerService/managedClusters",
                        "location": cluster["location"],
                        "kubernetes_version": cluster.get("kubernetes_version", ""),
                        "node_count": cluster.get("node_count", 0),
                        "status": "Stopped" if power == "Stopped" else "Active",
                        "category": "kubernetes",
                        "can_dismiss": power == "Stopped",
                        "dismiss_reason": "AKS cluster is stopped" if power == "Stopped" else None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching AKS clusters: {e}")

        # ---- Container Instances ----
        try:
            for cg in az.get_container_instances():
                cost = az.estimate_resource_cost(
                    "microsoft.containerinstance/containergroups", "", cg.get("location", "")
                )
                _add(
                    "container_instances",
                    {
                        "id": cg["id"],
                        "name": cg["name"],
                        "type": "Microsoft.ContainerInstance/containerGroups",
                        "location": cg["location"],
                        "os_type": cg.get("os_type", "Linux"),
                        "container_count": cg.get("container_count", 0),
                        "status": cg.get("provisioning_state", "Succeeded"),
                        "category": "container_instances",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching container instances: {e}")

        # ---- Key Vaults ----
        try:
            for kv in az.get_key_vaults():
                cost = az.estimate_resource_cost(
                    "microsoft.keyvault/vaults", "Standard", kv.get("location", "")
                )
                _add(
                    "key_vaults",
                    {
                        "id": kv["id"],
                        "name": kv["name"],
                        "type": "Microsoft.KeyVault/vaults",
                        "location": kv["location"],
                        "status": "Active",
                        "category": "key_vaults",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching key vaults: {e}")

        # ---- Redis Caches ----
        try:
            for cache in az.get_redis_caches():
                cost = az.estimate_resource_cost(
                    "microsoft.cache/redis", cache.get("sku_name", ""), cache.get("location", "")
                )
                _add(
                    "redis_caches",
                    {
                        "id": cache["id"],
                        "name": cache["name"],
                        "type": "Microsoft.Cache/Redis",
                        "location": cache["location"],
                        "sku": f"{cache.get('sku_name', '')} C{cache.get('sku_capacity', '')}",
                        "status": cache.get("provisioning_state", "Succeeded"),
                        "category": "redis_caches",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching Redis caches: {e}")

        # ---- Cosmos DB ----
        try:
            for acc in az.get_cosmos_db_accounts():
                cost = az.estimate_resource_cost(
                    "microsoft.documentdb/databaseaccounts", "", acc.get("location", "")
                )
                _add(
                    "cosmos_db",
                    {
                        "id": acc["id"],
                        "name": acc["name"],
                        "type": "Microsoft.DocumentDB/databaseAccounts",
                        "location": acc["location"],
                        "kind": acc.get("kind", "GlobalDocumentDB"),
                        "consistency": acc.get("consistency_level", "Session"),
                        "status": "Active",
                        "category": "cosmos_db",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching Cosmos DB: {e}")

        # ---- Data Factories ----
        try:
            for factory in az.get_data_factories():
                cost = az.estimate_resource_cost(
                    "microsoft.datafactory/factories", "", factory.get("location", "")
                )
                _add(
                    "data_factories",
                    {
                        "id": factory["id"],
                        "name": factory["name"],
                        "type": "Microsoft.DataFactory/factories",
                        "location": factory["location"],
                        "status": factory.get("provisioning_state", "Succeeded"),
                        "category": "data_factories",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching Data Factories: {e}")

        # ---- Logic Apps ----
        try:
            for wf in az.get_logic_apps():
                cost = az.estimate_resource_cost(
                    "microsoft.logic/workflows", wf.get("sku", ""), wf.get("location", "")
                )
                state = wf.get("state", "Enabled")
                _add(
                    "logic_apps",
                    {
                        "id": wf["id"],
                        "name": wf["name"],
                        "type": "Microsoft.Logic/workflows",
                        "location": wf["location"],
                        "state": state,
                        "status": "Disabled" if state == "Disabled" else "Active",
                        "category": "logic_apps",
                        "can_dismiss": state == "Disabled",
                        "dismiss_reason": "Logic App is disabled" if state == "Disabled" else None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching Logic Apps: {e}")

        # ---- Event Hubs ----
        try:
            for ns in az.get_event_hubs():
                cost = az.estimate_resource_cost(
                    "microsoft.eventhub/namespaces", ns.get("sku_name", ""), ns.get("location", "")
                )
                _add(
                    "event_hubs",
                    {
                        "id": ns["id"],
                        "name": ns["name"],
                        "type": "Microsoft.EventHub/namespaces",
                        "location": ns["location"],
                        "sku": ns.get("sku_name", "Basic"),
                        "status": ns.get("provisioning_state", "Succeeded"),
                        "category": "event_hubs",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching Event Hubs: {e}")

        # ---- Service Bus ----
        try:
            for ns in az.get_service_bus_namespaces():
                cost = az.estimate_resource_cost(
                    "microsoft.servicebus/namespaces",
                    ns.get("sku_name", ""),
                    ns.get("location", ""),
                )
                _add(
                    "service_bus",
                    {
                        "id": ns["id"],
                        "name": ns["name"],
                        "type": "Microsoft.ServiceBus/namespaces",
                        "location": ns["location"],
                        "sku": ns.get("sku_name", "Basic"),
                        "status": ns.get("provisioning_state", "Succeeded"),
                        "category": "service_bus",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching Service Bus: {e}")

        # ---- IoT Hubs ----
        try:
            for hub in az.get_iot_hubs():
                cost = az.estimate_resource_cost(
                    "microsoft.devices/iothubs", hub.get("sku_name", ""), hub.get("location", "")
                )
                _add(
                    "iot_hubs",
                    {
                        "id": hub["id"],
                        "name": hub["name"],
                        "type": "Microsoft.Devices/IotHubs",
                        "location": hub["location"],
                        "sku": hub.get("sku_name", "F1"),
                        "status": hub.get("state", "Active"),
                        "category": "iot_hubs",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching IoT Hubs: {e}")

        # ---- Cognitive Services ----
        try:
            for acc in az.get_cognitive_services():
                cost = az.estimate_resource_cost(
                    "microsoft.cognitiveservices/accounts",
                    acc.get("sku_name", ""),
                    acc.get("location", ""),
                )
                _add(
                    "cognitive_services",
                    {
                        "id": acc["id"],
                        "name": acc["name"],
                        "type": f"Microsoft.CognitiveServices/accounts ({acc.get('kind', 'Unknown')})",
                        "location": acc["location"],
                        "sku": acc.get("sku_name", "S0"),
                        "kind": acc.get("kind", "Unknown"),
                        "status": acc.get("provisioning_state", "Succeeded"),
                        "category": "cognitive_services",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching Cognitive Services: {e}")

        # ---- Application Insights ----
        try:
            for comp in az.get_application_insights():
                cost = az.estimate_resource_cost(
                    "microsoft.insights/components", "", comp.get("location", "")
                )
                _add(
                    "monitoring",
                    {
                        "id": comp["id"],
                        "name": comp["name"],
                        "type": "Microsoft.Insights/components",
                        "location": comp["location"],
                        "application_type": comp.get("application_type", "web"),
                        "retention_days": comp.get("retention_in_days", 90),
                        "status": "Active",
                        "category": "monitoring",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching Application Insights: {e}")

        # ---- CDN Profiles ----
        try:
            for profile in az.get_cdn_profiles():
                cost = az.estimate_resource_cost(
                    "microsoft.cdn/profiles",
                    profile.get("sku_name", ""),
                    profile.get("location", ""),
                )
                _add(
                    "cdn_profiles",
                    {
                        "id": profile["id"],
                        "name": profile["name"],
                        "type": "Microsoft.Cdn/profiles",
                        "location": profile["location"],
                        "sku": profile.get("sku_name", "Standard_Microsoft"),
                        "status": profile.get("resource_state", "Active"),
                        "category": "cdn_profiles",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching CDN profiles: {e}")

        # ---- API Management ----
        try:
            for svc in az.get_api_management_instances():
                cost = az.estimate_resource_cost(
                    "microsoft.apimanagement/service",
                    svc.get("sku_name", ""),
                    svc.get("location", ""),
                )
                _add(
                    "api_management",
                    {
                        "id": svc["id"],
                        "name": svc["name"],
                        "type": "Microsoft.ApiManagement/service",
                        "location": svc["location"],
                        "sku": svc.get("sku_name", "Developer"),
                        "status": svc.get("provisioning_state", "Succeeded"),
                        "category": "api_management",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching API Management: {e}")

        # ---- Recovery Vaults ----
        try:
            for vault in az.get_recovery_vaults():
                cost = az.estimate_resource_cost(
                    "microsoft.recoveryservices/vaults",
                    vault.get("sku", ""),
                    vault.get("location", ""),
                )
                _add(
                    "recovery_vaults",
                    {
                        "id": f"/subscriptions/{az.subscription_id}/providers/Microsoft.RecoveryServices/vaults/{vault['name']}",
                        "name": vault["name"],
                        "type": "Microsoft.RecoveryServices/vaults",
                        "location": vault["location"],
                        "sku": vault["sku"],
                        "status": "Active",
                        "category": "backup",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching recovery vaults: {e}")

        # ---- Resource Graph Fallback for Uncollected Resources ----
        try:
            all_resources = az.get_all_resources_by_resource_graph()
            if all_resources:
                _type_to_cat = {
                    "microsoft.compute/virtualmachines": "virtual_machines",
                    "microsoft.compute/disks": "disks",
                    "microsoft.storage/storageaccounts": "storage_accounts",
                    "microsoft.network/publicipaddresses": "network_resources",
                    "microsoft.network/loadbalancers": "network_resources",
                    "microsoft.containerservice/managedclusters": "kubernetes",
                    "microsoft.containerinstance/containergroups": "other_resources",
                    "microsoft.web/sites": "app_services",
                    "microsoft.web/serverfarms": "app_services",
                    "microsoft.sql/servers/databases": "databases",
                    "microsoft.keyvault/vaults": "key_vaults",
                    "microsoft.cache/redis": "messaging",
                    "microsoft.documentdb/databaseaccounts": "databases",
                    "microsoft.datafactory/factories": "other_resources",
                    "microsoft.logic/workflows": "other_resources",
                    "microsoft.eventhub/namespaces": "messaging",
                    "microsoft.servicebus/namespaces": "messaging",
                    "microsoft.devices/iothubs": "messaging",
                    "microsoft.cognitiveservices/accounts": "cognitive_services",
                    "microsoft.insights/components": "monitoring",
                    "microsoft.cdn/profiles": "other_resources",
                    "microsoft.apimanagement/service": "other_resources",
                    "microsoft.recoveryservices/vaults": "other_resources",
                }

                for r in all_resources:
                    r_id = r.get("id", "")
                    if not r_id or r_id.lower() in collected_ids:
                        continue

                    r_type = r.get("type", "").lower()

                    category = "other_resources"
                    if (
                        r_type == "microsoft.web/sites"
                        and "functionapp" in str(r.get("kind", "")).lower()
                    ):
                        category = "functions"
                    else:
                        category = _type_to_cat.get(r_type, "other_resources")

                    # Estimate cost
                    sku_name = (
                        r.get("sku", {}).get("name", "")
                        if isinstance(r.get("sku"), dict)
                        else (r.get("sku") or "")
                    )
                    cost = az.estimate_resource_cost(r_type, sku_name, r.get("location", ""))

                    _add(
                        category,
                        {
                            "id": r_id,
                            "name": r.get("name", "Unnamed"),
                            "type": r.get("type", "Unknown"),
                            "location": r.get("location", "global"),
                            "status": "Active",
                            "category": category,
                            "can_dismiss": False,
                            "dismiss_reason": None,
                            "estimated_cost": cost,
                            "sku": sku_name,
                            "kind": r.get("kind", ""),
                            "tags": r.get("tags") or {},
                        },
                    )
        except Exception as e:
            print(f"[!] Error in Resource Graph fallback: {e}")

        # ---- Flatten all resources for pagination + filtering ----
        all_categories = [k for k in inventory if k not in ("summary", "other_resources")]
        all_flat: list[dict] = []
        for cat in all_categories:
            all_flat.extend(inventory[cat])  # type: ignore[union-attr]

        # Apply server-side filters
        if category_filter:
            all_flat = [r for r in all_flat if r.get("category", "") == category_filter]
        if status_filter:
            all_flat = [r for r in all_flat if r.get("status", "") == status_filter]
        if search_q:
            all_flat = [
                r
                for r in all_flat
                if search_q in r.get("name", "").lower() or search_q in r.get("type", "").lower()
            ]

        total = len(all_flat)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_flat = all_flat[start:end]

        # Round estimated cost
        inventory["summary"]["estimated_monthly_cost"] = round(  # type: ignore[index]
            inventory["summary"]["estimated_monthly_cost"],
            2,  # type: ignore[index]
        )

        # Return streaming response if requested
        if stream_response:

            async def generate_stream():
                """Generator function for streaming JSON response."""
                # Send initial metadata
                yield (
                    json_module.dumps(
                        {
                            "status": "success",
                            "page": page,
                            "page_size": page_size,
                            "total": total,
                            "total_pages": max(1, (total + page_size - 1) // page_size),
                            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        }
                    )
                    + "\n"
                )

                # Stream resources in chunks
                chunk_size = 50
                for i in range(0, len(paginated_flat), chunk_size):
                    chunk = paginated_flat[i : i + chunk_size]
                    yield (
                        json_module.dumps(
                            {
                                "type": "resources_chunk",
                                "chunk_index": i // chunk_size,
                                "total_chunks": (len(paginated_flat) + chunk_size - 1)
                                // chunk_size,
                                "resources": chunk,
                            }
                        )
                        + "\n"
                    )
                    await asyncio.sleep(0.01)  # Small delay to prevent overwhelming the client

                # Send summary at the end
                yield json_module.dumps({"type": "summary", "data": inventory}) + "\n"

            return StreamingResponse(
                generate_stream(),
                media_type="application/json",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",  # Disable nginx buffering
                },
            )

        return jsonify(
            {
                "status": "success",
                "data": inventory,
                "resources": paginated_flat,
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": max(1, (total + page_size - 1) // page_size),
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@router.get("/api/resources/inventory/summary")
async def get_resource_inventory_summary(request: Request):
    """Lightweight endpoint returning only counts + cost — no resource lists.
    Suitable for dashboard widgets that don't need full resource data.
    """
    try:

        def _fetch_resources():
            c = AzureCollector()
            return c.get_all_resources_via_resource_graph()

        all_resources = await asyncio.to_thread(_fetch_resources)
        type_counts: dict[str, int] = {}
        for r in all_resources:
            rt = str(r.get("type", "other")).lower()
            type_counts[rt] = type_counts.get(rt, 0) + 1

        # Map to friendly categories
        _type_to_cat = {
            "microsoft.compute/virtualmachines": "compute",
            "microsoft.compute/disks": "storage",
            "microsoft.storage/storageaccounts": "storage",
            "microsoft.network/publicipaddresses": "network",
            "microsoft.network/loadbalancers": "network",
            "microsoft.containerservice/managedclusters": "kubernetes",
            "microsoft.containerinstance/containergroups": "container_instances",
            "microsoft.web/sites": "app_services",
            "microsoft.web/serverfarms": "app_services",
            "microsoft.sql/servers/databases": "database",
            "microsoft.keyvault/vaults": "key_vaults",
            "microsoft.cache/redis": "redis_caches",
            "microsoft.documentdb/databaseaccounts": "cosmos_db",
            "microsoft.datafactory/factories": "data_factories",
            "microsoft.logic/workflows": "logic_apps",
            "microsoft.eventhub/namespaces": "event_hubs",
            "microsoft.servicebus/namespaces": "service_bus",
            "microsoft.devices/iothubs": "iot_hubs",
            "microsoft.cognitiveservices/accounts": "cognitive_services",
            "microsoft.insights/components": "monitoring",
            "microsoft.cdn/profiles": "cdn_profiles",
            "microsoft.apimanagement/service": "api_management",
            "microsoft.recoveryservices/vaults": "backup",
        }
        by_category: dict[str, int] = {}
        for rt, count in type_counts.items():
            cat = _type_to_cat.get(rt, "other")
            by_category[cat] = by_category.get(cat, 0) + count

        return jsonify(
            {
                "status": "success",
                "total_resources": len(all_resources),
                "by_category": by_category,
                "by_type": type_counts,
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@router.get("/api/resources/search")
async def search_resources(request: Request):
    """Full-text search across all Azure resources by name or type.

    Query params:
        q         (str, required)   - search term
        category  (str, optional)   - filter by category
        status    (str, optional)   - filter by status
        page      (int, default 1)
        page_size (int, default 25)
    """
    q = request.query_params.get("q", "").strip().lower()
    if not q:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Query param 'q' is required."},
        )

    try:
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = min(100, max(1, int(request.query_params.get("page_size", 25))))
        category_filter = request.query_params.get("category", "").strip().lower()
        status_filter = request.query_params.get("status", "").strip()

        def _fetch_resources():
            c = AzureCollector()
            return c.get_all_resources_via_resource_graph()

        all_resources = await asyncio.to_thread(_fetch_resources)

        results = [
            {
                "id": r.get("id", ""),
                "name": r.get("name", ""),
                "type": r.get("type", ""),
                "location": r.get("location", ""),
                "resource_group": r.get("resourceGroup", ""),
                "tags": r.get("tags") or {},
                "kind": r.get("kind", ""),
            }
            for r in all_resources
            if q in str(r.get("name", "")).lower() or q in str(r.get("type", "")).lower()
        ]

        if category_filter:
            from reaper.collectors.providers.azure_collector import AzureCollector as _AC

            _type_to_cat = _AC._COST_FALLBACK  # borrow the type map keys for category matching
            results = [r for r in results if category_filter in r.get("type", "").lower()]
        if status_filter:
            results = [r for r in results if r.get("status", "") == status_filter]

        total = len(results)
        start = (page - 1) * page_size
        paginated = results[start : start + page_size]

        return jsonify(
            {
                "status": "success",
                "query": q,
                "results": paginated,
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": max(1, (total + page_size - 1) // page_size),
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@router.post("/api/resources/{resource_id}/dismiss")
async def dismiss_resource(request: Request, resource_id: str):
    """Mark a resource for dismissal/cleanup."""
    try:
        data = await request.json() if request.body() else {}
        reason = data.get("reason", "Manual dismissal")

        # In a real implementation, this would:
        # 1. Log the dismissal action
        # 2. Create a cleanup ticket
        # 3. Optionally trigger actual resource deletion

        return jsonify(
            {
                "status": "success",
                "message": f"Resource {resource_id} marked for dismissal",
                "resource_id": resource_id,
                "reason": reason,
                "action_taken": "marked_for_cleanup",
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

