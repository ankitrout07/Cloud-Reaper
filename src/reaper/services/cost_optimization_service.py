import asyncio

from fastapi import Request

from reaper.collectors.providers.azure_collector import AzureCollector
from reaper.engine.core.cost import ResourceMetrics
from reaper.web.app_async import calc, is_first_run


class CostOptimizationService:
    def __init__(self):
        pass

    async def analyze_cost_optimization(self, request: Request):
        """Comprehensive cost optimization analysis for all cloud resources"""
        try:
            data = (await request.json() if await request.body() else {}) or {}
            provider = data.get("provider", "azure").lower()

            if is_first_run():
                return jsonify(
                    {"status": "unconfigured", "message": "Please configure cloud credentials first"}
                )

            # Initialize collector based on provider
            if provider == "azure":

                def _get_collector():
                    return AzureCollector()

                collector = await asyncio.to_thread(_get_collector)
            else:
                return jsonify(
                    {
                        "status": "error",
                        "message": f"Provider {provider} not yet supported in comprehensive analysis",
                    },
                    status_code=400,
                )

            cost_optimizer.recommendations.clear()

            # Get resource inventory
            resources = []

            # Get compute resources (VMs)
            try:
                vms = collector.get_vm_inventory()

                def _analyze_vm(vm):
                    vm_id = vm.get("id") or ""
                    if not vm_id and vm.get("name"):
                        vm_id = (
                            f"/subscriptions/{collector.subscription_id}/resourceGroups/"
                            f"{vm.get('rg', 'unknown')}/providers/Microsoft.Compute/virtualMachines/{vm['name']}"
                        )
                    vm_metrics = collector.get_vm_metrics(vm_id)
                    metrics = ResourceMetrics(
                        cpu_utilization=vm_metrics.get("cpu_percent", {}).get("average", 50),
                        memory_utilization=vm_metrics.get("memory_percent", {}).get("average", 50),
                        disk_utilization=vm_metrics.get("disk_percent", {}).get("average", 50),
                        network_in_mbps=vm_metrics.get("network_in_mbps", 0),
                        network_out_mbps=vm_metrics.get("network_out_mbps", 0),
                        iops=vm_metrics.get("iops", 0),
                        latency_ms=vm_metrics.get("latency_ms", 0),
                        error_rate=vm_metrics.get("error_rate", 0),
                        uptime_percentage=vm_metrics.get("uptime_percentage", 99),
                        peak_cpu_utilization=vm_metrics.get("cpu_percent", {}).get("max", 70),
                        peak_memory_utilization=vm_metrics.get("memory_percent", {}).get("max", 70),
                    )
                    current_sku = vm.get("size") or vm.get("sku") or "Standard_D2s_v3"
                    current_cost = calc.calculate_monthly_cost(provider, "compute", current_sku)
                    resource_data = {
                        "id": vm_id,
                        "name": vm.get("name", ""),
                        "type": "compute",
                        "provider": provider,
                        "sku": current_sku,
                        "region": vm.get("location", ""),
                        "tags": vm.get("tags", {}),
                    }
                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    return recommendations, {
                        "id": vm_id,
                        "name": vm.get("name", ""),
                        "type": "compute",
                        "current_cost": current_cost,
                        "metrics": vm_metrics,
                    }

                from concurrent.futures import ThreadPoolExecutor

                with ThreadPoolExecutor(max_workers=8) as pool:
                    for recs, resource in pool.map(_analyze_vm, vms):
                        cost_optimizer.recommendations.extend(recs)
                        resources.append(resource)
            except Exception as e:
                print(f"[!] Error analyzing VMs: {e}")

            # Get storage resources (disks)
            try:
                orphaned_disks = collector.get_orphaned_disks()
                for disk in orphaned_disks.get("disks", []):
                    metrics = ResourceMetrics(
                        cpu_utilization=0,
                        memory_utilization=0,
                        disk_utilization=0,  # Orphaned means not attached
                        network_in_mbps=0,
                        network_out_mbps=0,
                        iops=0,
                        latency_ms=0,
                        error_rate=0,
                        uptime_percentage=100,
                        peak_cpu_utilization=0,
                        peak_memory_utilization=0,
                    )

                    current_sku = disk.get("tier", "premium_ssd")
                    current_cost = calc.calculate_monthly_cost(provider, "storage", current_sku)

                    resource_data = {
                        "id": disk.get("id", ""),
                        "name": disk.get("name", ""),
                        "type": "storage",
                        "provider": provider,
                        "sku": current_sku,
                        "region": disk.get("location", ""),
                        "tags": disk.get("tags", {}),
                    }

                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    cost_optimizer.recommendations.extend(recommendations)

                    resources.append(
                        {
                            "id": disk.get("id", ""),
                            "name": disk.get("name", ""),
                            "type": "storage",
                            "current_cost": current_cost,
                            "metrics": {},
                        }
                    )
            except Exception as e:
                print(f"[!] Error analyzing storage: {e}")

            # Get idle resources
            try:
                idle_vms = collector.get_idle_vms(cpu_threshold=5.0)
                for vm in idle_vms:
                    metrics = ResourceMetrics(
                        cpu_utilization=vm.get("average_cpu", 5),
                        memory_utilization=20,  # Assume low memory utilization for idle VMs
                        disk_utilization=50,
                        network_in_mbps=0.1,
                        network_out_mbps=0.1,
                        iops=10,
                        latency_ms=0,
                        error_rate=0,
                        uptime_percentage=95,
                        peak_cpu_utilization=10,
                        peak_memory_utilization=30,
                    )

                    current_sku = vm.get("sku", "Standard_D2s_v3")
                    current_cost = calc.calculate_monthly_cost(provider, "compute", current_sku)

                    resource_data = {
                        "id": vm.get("id", ""),
                        "name": vm.get("name", ""),
                        "type": "compute",
                        "provider": provider,
                        "sku": current_sku,
                        "region": vm.get("location", ""),
                        "tags": vm.get("tags", {}),
                    }

                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    cost_optimizer.recommendations.extend(recommendations)
            except Exception as e:
                print(f"[!] Error analyzing idle resources: {e}")

            # ========== NEW RESOURCE TYPES ANALYSIS ==========

            # Storage Accounts
            try:
                storage_accounts = collector.get_storage_accounts()
                for account in storage_accounts:
                    metrics = ResourceMetrics(
                        cpu_utilization=0,
                        memory_utilization=0,
                        disk_utilization=50,  # Assume moderate usage
                        network_in_mbps=1.0,
                        network_out_mbps=1.0,
                        iops=100,
                        latency_ms=10,
                        error_rate=0,
                        uptime_percentage=99.9,
                        peak_cpu_utilization=0,
                        peak_memory_utilization=0,
                    )

                    current_sku = account.get("sku", "Standard_LRS")
                    current_cost = calc.calculate_monthly_cost(provider, "storage", current_sku)

                    resource_data = {
                        "id": account.get("id", ""),
                        "name": account.get("name", ""),
                        "type": "storage",
                        "provider": provider,
                        "sku": current_sku,
                        "region": account.get("location", ""),
                        "tags": account.get("tags", {}),
                    }

                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    cost_optimizer.recommendations.extend(recommendations)
                    resources.append(
                        {
                            "id": account.get("id", ""),
                            "name": account.get("name", ""),
                            "type": "storage",
                            "current_cost": current_cost,
                            "metrics": {},
                        }
                    )
            except Exception as e:
                print(f"[!] Error analyzing storage accounts: {e}")

            # AKS Clusters
            try:
                aks_clusters = collector.get_aks_clusters()
                for cluster in aks_clusters:
                    metrics = ResourceMetrics(
                        cpu_utilization=40,  # Assume moderate cluster utilization
                        memory_utilization=50,
                        disk_utilization=60,
                        network_in_mbps=5.0,
                        network_out_mbps=5.0,
                        iops=500,
                        latency_ms=5,
                        error_rate=0,
                        uptime_percentage=99.9,
                        peak_cpu_utilization=70,
                        peak_memory_utilization=80,
                    )

                    current_sku = cluster.get("sku", "Free")
                    node_count = cluster.get("node_count", 1)
                    current_cost = (
                        calc.calculate_monthly_cost(provider, "container", current_sku) * node_count
                    )

                    resource_data = {
                        "id": cluster.get("id", ""),
                        "name": cluster.get("name", ""),
                        "type": "container",
                        "provider": provider,
                        "sku": current_sku,
                        "region": cluster.get("location", ""),
                        "tags": cluster.get("tags", {}),
                    }

                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    cost_optimizer.recommendations.extend(recommendations)
                    resources.append(
                        {
                            "id": cluster.get("id", ""),
                            "name": cluster.get("name", ""),
                            "type": "container",
                            "current_cost": current_cost,
                            "metrics": {},
                        }
                    )
            except Exception as e:
                print(f"[!] Error analyzing AKS clusters: {e}")

            # Container Instances
            try:
                container_instances = collector.get_container_instances()
                for instance in container_instances:
                    metrics = ResourceMetrics(
                        cpu_utilization=30,
                        memory_utilization=40,
                        disk_utilization=20,
                        network_in_mbps=0.5,
                        network_out_mbps=0.5,
                        iops=50,
                        latency_ms=10,
                        error_rate=0,
                        uptime_percentage=95,
                        peak_cpu_utilization=50,
                        peak_memory_utilization=60,
                    )

                    current_sku = "Standard"
                    current_cost = calc.calculate_monthly_cost(provider, "container", current_sku)

                    resource_data = {
                        "id": instance.get("id", ""),
                        "name": instance.get("name", ""),
                        "type": "container",
                        "provider": provider,
                        "sku": current_sku,
                        "region": instance.get("location", ""),
                        "tags": instance.get("tags", {}),
                    }

                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    cost_optimizer.recommendations.extend(recommendations)
                    resources.append(
                        {
                            "id": instance.get("id", ""),
                            "name": instance.get("name", ""),
                            "type": "container",
                            "current_cost": current_cost,
                            "metrics": {},
                        }
                    )
            except Exception as e:
                print(f"[!] Error analyzing container instances: {e}")

            # Function Apps
            try:
                function_apps = collector.get_function_apps()
                for app in function_apps:
                    metrics = ResourceMetrics(
                        cpu_utilization=20,  # Serverless - typically lower utilization
                        memory_utilization=30,
                        disk_utilization=10,
                        network_in_mbps=0.2,
                        network_out_mbps=0.2,
                        iops=20,
                        latency_ms=50,  # Cold starts
                        error_rate=0,
                        uptime_percentage=99,  # Serverless availability
                        peak_cpu_utilization=40,
                        peak_memory_utilization=50,
                    )

                    current_sku = "Consumption"
                    current_cost = calc.calculate_monthly_cost(provider, "compute", current_sku)

                    resource_data = {
                        "id": app.get("id", ""),
                        "name": app.get("name", ""),
                        "type": "compute",
                        "provider": provider,
                        "sku": current_sku,
                        "region": app.get("location", ""),
                        "tags": app.get("tags", {}),
                    }

                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    cost_optimizer.recommendations.extend(recommendations)
                    resources.append(
                        {
                            "id": app.get("id", ""),
                            "name": app.get("name", ""),
                            "type": "compute",
                            "current_cost": current_cost,
                            "metrics": {},
                        }
                    )
            except Exception as e:
                print(f"[!] Error analyzing function apps: {e}")

            # Key Vaults
            try:
                key_vaults = collector.get_key_vaults()
                for vault in key_vaults:
                    metrics = ResourceMetrics(
                        cpu_utilization=5,  # Low utilization for vault operations
                        memory_utilization=10,
                        disk_utilization=5,
                        network_in_mbps=0.1,
                        network_out_mbps=0.1,
                        iops=10,
                        latency_ms=20,
                        error_rate=0,
                        uptime_percentage=99.9,
                        peak_cpu_utilization=10,
                        peak_memory_utilization=15,
                    )

                    current_sku = "Standard"
                    current_cost = calc.calculate_monthly_cost(provider, "database", current_sku)

                    resource_data = {
                        "id": vault.get("id", ""),
                        "name": vault.get("name", ""),
                        "type": "database",
                        "provider": provider,
                        "sku": current_sku,
                        "region": vault.get("location", ""),
                        "tags": vault.get("tags", {}),
                    }

                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    cost_optimizer.recommendations.extend(recommendations)
                    resources.append(
                        {
                            "id": vault.get("id", ""),
                            "name": vault.get("name", ""),
                            "type": "database",
                            "current_cost": current_cost,
                            "metrics": {},
                        }
                    )
            except Exception as e:
                print(f"[!] Error analyzing key vaults: {e}")

            # Redis Caches
            try:
                redis_caches = collector.get_redis_caches()
                for cache in redis_caches:
                    metrics = ResourceMetrics(
                        cpu_utilization=45,  # Caching typically has moderate utilization
                        memory_utilization=60,  # Memory-intensive
                        disk_utilization=20,
                        network_in_mbps=2.0,
                        network_out_mbps=2.0,
                        iops=200,
                        latency_ms=1,  # Low latency for cache
                        error_rate=0,
                        uptime_percentage=99.9,
                        peak_cpu_utilization=70,
                        peak_memory_utilization=85,
                    )

                    current_sku = cache.get("sku_name", "Basic")
                    current_cost = calc.calculate_monthly_cost(provider, "database", current_sku)

                    resource_data = {
                        "id": cache.get("id", ""),
                        "name": cache.get("name", ""),
                        "type": "database",
                        "provider": provider,
                        "sku": current_sku,
                        "region": cache.get("location", ""),
                        "tags": cache.get("tags", {}),
                    }

                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    cost_optimizer.recommendations.extend(recommendations)
                    resources.append(
                        {
                            "id": cache.get("id", ""),
                            "name": cache.get("name", ""),
                            "type": "database",
                            "current_cost": current_cost,
                            "metrics": {},
                        }
                    )
            except Exception as e:
                print(f"[!] Error analyzing Redis caches: {e}")

            # Cosmos DB Accounts
            try:
                cosmos_accounts = collector.get_cosmos_db_accounts()
                for account in cosmos_accounts:
                    metrics = ResourceMetrics(
                        cpu_utilization=50,
                        memory_utilization=55,
                        disk_utilization=70,
                        network_in_mbps=3.0,
                        network_out_mbps=3.0,
                        iops=1000,
                        latency_ms=10,
                        error_rate=0,
                        uptime_percentage=99.99,
                        peak_cpu_utilization=80,
                        peak_memory_utilization=90,
                    )

                    current_sku = "Standard"
                    current_cost = calc.calculate_monthly_cost(provider, "database", current_sku)

                    resource_data = {
                        "id": account.get("id", ""),
                        "name": account.get("name", ""),
                        "type": "database",
                        "provider": provider,
                        "sku": current_sku,
                        "region": account.get("location", ""),
                        "tags": account.get("tags", {}),
                    }

                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    cost_optimizer.recommendations.extend(recommendations)
                    resources.append(
                        {
                            "id": account.get("id", ""),
                            "name": account.get("name", ""),
                            "type": "database",
                            "current_cost": current_cost,
                            "metrics": {},
                        }
                    )
            except Exception as e:
                print(f"[!] Error analyzing Cosmos DB accounts: {e}")

            # Data Factories
            try:
                data_factories = collector.get_data_factories()
                for factory in data_factories:
                    metrics = ResourceMetrics(
                        cpu_utilization=30,
                        memory_utilization=40,
                        disk_utilization=30,
                        network_in_mbps=1.5,
                        network_out_mbps=1.5,
                        iops=100,
                        latency_ms=100,  # Batch processing
                        error_rate=0,
                        uptime_percentage=99,
                        peak_cpu_utilization=60,
                        peak_memory_utilization=70,
                    )

                    current_sku = "Standard"
                    current_cost = calc.calculate_monthly_cost(provider, "compute", current_sku)

                    resource_data = {
                        "id": factory.get("id", ""),
                        "name": factory.get("name", ""),
                        "type": "compute",
                        "provider": provider,
                        "sku": current_sku,
                        "region": factory.get("location", ""),
                        "tags": factory.get("tags", {}),
                    }

                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    cost_optimizer.recommendations.extend(recommendations)
                    resources.append(
                        {
                            "id": factory.get("id", ""),
                            "name": factory.get("name", ""),
                            "type": "compute",
                            "current_cost": current_cost,
                            "metrics": {},
                        }
                    )
            except Exception as e:
                print(f"[!] Error analyzing data factories: {e}")

            # Logic Apps
            try:
                logic_apps = collector.get_logic_apps()
                for app in logic_apps:
                    metrics = ResourceMetrics(
                        cpu_utilization=15,  # Serverless workflow
                        memory_utilization=20,
                        disk_utilization=10,
                        network_in_mbps=0.3,
                        network_out_mbps=0.3,
                        iops=30,
                        latency_ms=200,  # Workflow processing
                        error_rate=0,
                        uptime_percentage=99,
                        peak_cpu_utilization=30,
                        peak_memory_utilization=40,
                    )

                    current_sku = app.get("sku", "Consumption")
                    current_cost = calc.calculate_monthly_cost(provider, "compute", current_sku)

                    resource_data = {
                        "id": app.get("id", ""),
                        "name": app.get("name", ""),
                        "type": "compute",
                        "provider": provider,
                        "sku": current_sku,
                        "region": app.get("location", ""),
                        "tags": app.get("tags", {}),
                    }

                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    cost_optimizer.recommendations.extend(recommendations)
                    resources.append(
                        {
                            "id": app.get("id", ""),
                            "name": app.get("name", ""),
                            "type": "compute",
                            "current_cost": current_cost,
                            "metrics": {},
                        }
                    )
            except Exception as e:
                print(f"[!] Error analyzing logic apps: {e}")

            # Event Hubs
            try:
                event_hubs = collector.get_event_hubs()
                for hub in event_hubs:
                    metrics = ResourceMetrics(
                        cpu_utilization=35,
                        memory_utilization=45,
                        disk_utilization=40,
                        network_in_mbps=2.5,
                        network_out_mbps=2.5,
                        iops=300,
                        latency_ms=20,
                        error_rate=0,
                        uptime_percentage=99.9,
                        peak_cpu_utilization=65,
                        peak_memory_utilization=75,
                    )

                    current_sku = hub.get("sku_name", "Basic")
                    current_cost = calc.calculate_monthly_cost(provider, "network", current_sku)

                    resource_data = {
                        "id": hub.get("id", ""),
                        "name": hub.get("name", ""),
                        "type": "network",
                        "provider": provider,
                        "sku": current_sku,
                        "region": hub.get("location", ""),
                        "tags": hub.get("tags", {}),
                    }

                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    cost_optimizer.recommendations.extend(recommendations)
                    resources.append(
                        {
                            "id": hub.get("id", ""),
                            "name": hub.get("name", ""),
                            "type": "network",
                            "current_cost": current_cost,
                            "metrics": {},
                        }
                    )
            except Exception as e:
                print(f"[!] Error analyzing event hubs: {e}")

            # Service Bus Namespaces
            try:
                service_bus = collector.get_service_bus_namespaces()
                for namespace in service_bus:
                    metrics = ResourceMetrics(
                        cpu_utilization=25,
                        memory_utilization=35,
                        disk_utilization=30,
                        network_in_mbps=1.0,
                        network_out_mbps=1.0,
                        iops=150,
                        latency_ms=15,
                        error_rate=0,
                        uptime_percentage=99.9,
                        peak_cpu_utilization=50,
                        peak_memory_utilization=60,
                    )

                    current_sku = namespace.get("sku_name", "Basic")
                    current_cost = calc.calculate_monthly_cost(provider, "network", current_sku)

                    resource_data = {
                        "id": namespace.get("id", ""),
                        "name": namespace.get("name", ""),
                        "type": "network",
                        "provider": provider,
                        "sku": current_sku,
                        "region": namespace.get("location", ""),
                        "tags": namespace.get("tags", {}),
                    }

                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    cost_optimizer.recommendations.extend(recommendations)
                    resources.append(
                        {
                            "id": namespace.get("id", ""),
                            "name": namespace.get("name", ""),
                            "type": "network",
                            "current_cost": current_cost,
                            "metrics": {},
                        }
                    )
            except Exception as e:
                print(f"[!] Error analyzing service bus namespaces: {e}")

            # IoT Hubs
            try:
                iot_hubs = collector.get_iot_hubs()
                for hub in iot_hubs:
                    metrics = ResourceMetrics(
                        cpu_utilization=30,
                        memory_utilization=40,
                        disk_utilization=35,
                        network_in_mbps=1.2,
                        network_out_mbps=1.2,
                        iops=200,
                        latency_ms=25,
                        error_rate=0,
                        uptime_percentage=99.9,
                        peak_cpu_utilization=55,
                        peak_memory_utilization=65,
                    )

                    current_sku = hub.get("sku_name", "F1")
                    current_cost = calc.calculate_monthly_cost(provider, "network", current_sku)

                    resource_data = {
                        "id": hub.get("id", ""),
                        "name": hub.get("name", ""),
                        "type": "network",
                        "provider": provider,
                        "sku": current_sku,
                        "region": hub.get("location", ""),
                        "tags": hub.get("tags", {}),
                    }

                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    cost_optimizer.recommendations.extend(recommendations)
                    resources.append(
                        {
                            "id": hub.get("id", ""),
                            "name": hub.get("name", ""),
                            "type": "network",
                            "current_cost": current_cost,
                            "metrics": {},
                        }
                    )
            except Exception as e:
                print(f"[!] Error analyzing IoT hubs: {e}")

            # Cognitive Services
            try:
                cognitive_services = collector.get_cognitive_services()
                for service in cognitive_services:
                    metrics = ResourceMetrics(
                        cpu_utilization=40,
                        memory_utilization=50,
                        disk_utilization=25,
                        network_in_mbps=2.0,
                        network_out_mbps=2.0,
                        iops=250,
                        latency_ms=50,  # AI processing latency
                        error_rate=0,
                        uptime_percentage=99.5,
                        peak_cpu_utilization=70,
                        peak_memory_utilization=80,
                    )

                    current_sku = service.get("sku_name", "S0")
                    current_cost = calc.calculate_monthly_cost(provider, "compute", current_sku)

                    resource_data = {
                        "id": service.get("id", ""),
                        "name": service.get("name", ""),
                        "type": "compute",
                        "provider": provider,
                        "sku": current_sku,
                        "region": service.get("location", ""),
                        "tags": service.get("tags", {}),
                    }

                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    cost_optimizer.recommendations.extend(recommendations)
                    resources.append(
                        {
                            "id": service.get("id", ""),
                            "name": service.get("name", ""),
                            "type": "compute",
                            "current_cost": current_cost,
                            "metrics": {},
                        }
                    )
            except Exception as e:
                print(f"[!] Error analyzing cognitive services: {e}")

            # Application Insights
            try:
                app_insights = collector.get_application_insights()
                for insights in app_insights:
                    metrics = ResourceMetrics(
                        cpu_utilization=10,  # Monitoring service
                        memory_utilization=15,
                        disk_utilization=20,
                        network_in_mbps=0.5,
                        network_out_mbps=0.5,
                        iops=50,
                        latency_ms=30,
                        error_rate=0,
                        uptime_percentage=99.9,
                        peak_cpu_utilization=20,
                        peak_memory_utilization=25,
                    )

                    current_sku = "Standard"
                    current_cost = calc.calculate_monthly_cost(provider, "network", current_sku)

                    resource_data = {
                        "id": insights.get("id", ""),
                        "name": insights.get("name", ""),
                        "type": "network",
                        "provider": provider,
                        "sku": current_sku,
                        "region": insights.get("location", ""),
                        "tags": insights.get("tags", {}),
                    }

                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    cost_optimizer.recommendations.extend(recommendations)
                    resources.append(
                        {
                            "id": insights.get("id", ""),
                            "name": insights.get("name", ""),
                            "type": "network",
                            "current_cost": current_cost,
                            "metrics": {},
                        }
                    )
            except Exception as e:
                print(f"[!] Error analyzing application insights: {e}")

            # CDN Profiles
            try:
                cdn_profiles = collector.get_cdn_profiles()
                for profile in cdn_profiles:
                    metrics = ResourceMetrics(
                        cpu_utilization=20,
                        memory_utilization=25,
                        disk_utilization=15,
                        network_in_mbps=5.0,  # High bandwidth for CDN
                        network_out_mbps=5.0,
                        iops=100,
                        latency_ms=5,  # Low latency for CDN
                        error_rate=0,
                        uptime_percentage=99.9,
                        peak_cpu_utilization=40,
                        peak_memory_utilization=50,
                    )

                    current_sku = profile.get("sku_name", "Standard_Microsoft")
                    current_cost = calc.calculate_monthly_cost(provider, "network", current_sku)

                    resource_data = {
                        "id": profile.get("id", ""),
                        "name": profile.get("name", ""),
                        "type": "network",
                        "provider": provider,
                        "sku": current_sku,
                        "region": profile.get("location", ""),
                        "tags": profile.get("tags", {}),
                    }

                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    cost_optimizer.recommendations.extend(recommendations)
                    resources.append(
                        {
                            "id": profile.get("id", ""),
                            "name": profile.get("name", ""),
                            "type": "network",
                            "current_cost": current_cost,
                            "metrics": {},
                        }
                    )
            except Exception as e:
                print(f"[!] Error analyzing CDN profiles: {e}")

            # API Management Instances
            try:
                apim_instances = collector.get_api_management_instances()
                for instance in apim_instances:
                    metrics = ResourceMetrics(
                        cpu_utilization=35,
                        memory_utilization=45,
                        disk_utilization=30,
                        network_in_mbps=3.0,
                        network_out_mbps=3.0,
                        iops=200,
                        latency_ms=10,
                        error_rate=0,
                        uptime_percentage=99.9,
                        peak_cpu_utilization=60,
                        peak_memory_utilization=70,
                    )

                    current_sku = instance.get("sku_name", "Developer")
                    current_cost = calc.calculate_monthly_cost(provider, "network", current_sku)

                    resource_data = {
                        "id": instance.get("id", ""),
                        "name": instance.get("name", ""),
                        "type": "network",
                        "provider": provider,
                        "sku": current_sku,
                        "region": instance.get("location", ""),
                        "tags": instance.get("tags", {}),
                    }

                    recommendations = cost_optimizer.analyze_resource(
                        resource_data, metrics, current_cost
                    )
                    cost_optimizer.recommendations.extend(recommendations)
                    resources.append(
                        {
                            "id": instance.get("id", ""),
                            "name": instance.get("name", ""),
                            "type": "network",
                            "current_cost": current_cost,
                            "metrics": {},
                        }
                    )
            except Exception as e:
                print(f"[!] Error analyzing API management instances: {e}")

            # Prioritize and generate summary
            prioritized_recommendations = cost_optimizer.prioritize_recommendations()
            summary = cost_optimizer.generate_summary_report()

            return jsonify(
                {
                    "status": "success",
                    "summary": summary,
                    "recommendations": [rec.to_dict() for rec in prioritized_recommendations],
                    "analyzed_resources": len(resources),
                }
            )

        except Exception as e:
            print(f"[!] Error in cost optimization analysis: {e}")
            return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

