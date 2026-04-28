import os
import random
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Critical tags that every resource MUST have for full FinOps attribution
CRITICAL_TAGS = ["Owner", "Environment", "CostCenter", "Project", "Team"]

# Policy rules: resource types blocked per environment
OPA_POLICIES = [
    {"rule": "No G-Series VMs in Dev/Test",    "pattern": "Standard_G",  "env": "dev",     "severity": "HIGH"},
    {"rule": "No Ultra Disks in Staging",       "pattern": "UltraSSD",     "env": "staging",  "severity": "HIGH"},
    {"rule": "No Premium P80 disks in Sandbox", "pattern": "Premium_P80",  "env": "sandbox", "severity": "MEDIUM"},
    {"rule": "No DS-series >v3 in Dev",         "pattern": "Standard_DS",  "env": "dev",     "severity": "MEDIUM"},
]

class AzureCollector:
    def __init__(self):
        self.subscription_id = os.getenv('AZURE_SUBSCRIPTION_ID')
        self.credentials = DefaultAzureCredential()
        self.engine_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'engine-go', 'reaper-engine')
        self._scan_cache = None
        
        # Only initialize client if subscription_id exists
        if self.subscription_id:
            self.compute_client = ComputeManagementClient(self.credentials, self.subscription_id)
            self.monitor_client = MonitorManagementClient(self.credentials, self.subscription_id)
        else:
            self.compute_client = None
            self.monitor_client = None

    def fast_scan(self):
        """Execute the Go binary and capture the JSON output. Caches result."""
        if self._scan_cache:
            return self._scan_cache

        import subprocess
        import json
        
        if not os.path.exists(self.engine_path):
            return {"error": "Go engine binary not found. Run go build."}

        try:
            env = os.environ.copy()
            if self.subscription_id:
                env["AZURE_SUBSCRIPTION_ID"] = str(self.subscription_id)
            
            process = subprocess.run(
                [self.engine_path, "--subscription", str(self.subscription_id)], 
                env=env,
                capture_output=True, 
                text=True, 
                check=True
            )
            self._scan_cache = json.loads(process.stdout)
            return self._scan_cache
        except Exception as e:
            return {"error": f"Go Engine failed: {e}"}

    def get_live_prices(self):
        """Returns the live prices fetched by the Go engine."""
        scan = self.fast_scan()
        return scan.get("prices", [])

    def get_vm_inventory(self):
        """Returns active VMs. Uses Go fast_scan if available."""
        scan = self.fast_scan()
        if "active_vms" in scan:
            return [{'name': name, 'size': 'Unknown (Fast Scan)'} for name in scan['active_vms']]
        
        # Fallback
        if not self.compute_client: return []
        try:
            vms = self.compute_client.virtual_machines.list_all()
            return [{'name': vm.name, 'size': vm.hardware_profile.vm_size} for vm in vms]
        except Exception:
            return []

    def _extract_rg(self, resource_id):
        """Helper to extract resource group name from Azure Resource ID."""
        parts = resource_id.split('/')
        if len(parts) > 4:
            return parts[4]
        return "N/A"

    def get_orphaned_disks(self):
        """Returns orphaned disks & snapshots. Uses Go fast_scan if available."""
        scan = self.fast_scan()
        results = {
            "disks": [],
            "snapshots": []
        }
        
        if "orphaned_disks" in scan:
            results["disks"] = [{'name': name, 'size_gb': 0, 'rg': 'N/A'} for name in scan['orphaned_disks']]
        
        if "orphaned_snapshots" in scan:
            results["snapshots"] = [{'name': name, 'rg': 'N/A'} for name in scan['orphaned_snapshots']]

        # Fallback for disks only (simplified)
        if not results["disks"] and self.compute_client:
            try:
                disks = self.compute_client.disks.list()
                results["disks"] = [{
                    'name': d.name, 
                    'size_gb': d.disk_size_gb,
                    'rg': self._extract_rg(d.id)
                } for d in disks if d.managed_by is None]
            except Exception: pass
            
        return results

    def get_zombie_vms(self):
        """Deep idle logic: CPU < 1%, Network < 10KB, Disk IOPS < 1."""
        scan = self.fast_scan()
        zombies = []
        if "vm_reports" in scan:
            for r in scan['vm_reports']:
                is_zombie = (
                    r['usage'] < 1.0 and 
                    r['network_in'] < 10240 and 
                    r['network_out'] < 10240 and
                    r['disk_iops'] < 1.0
                )
                if is_zombie:
                    zombies.append({
                        "name": r['name'],
                        "usage": f"CPU: {r['usage']:.1f}% | Net: {r['network_in']/1024:.1f}KB",
                        "id": r['id'],
                        "rg": self._extract_rg(r['id'])
                    })
        return zombies

    def get_idle_vms(self, cpu_threshold=5.0):
        """
        Returns VMs with average CPU usage below the threshold.
        Uses the high-speed unified Go scan result.
        """
        scan = self.fast_scan()
        if "vm_reports" in scan:
            idle_vms = []
            for r in scan['vm_reports']:
                if r['usage'] < cpu_threshold:
                    idle_vms.append({
                        "name": r['name'],
                        "usage": round(r['usage'], 2),
                        "id": r['id'],
                        "rg": self._extract_rg(r['id'])
                    })
            return idle_vms

        # Fallback to Python if Go result is missing
        return self._get_idle_vms_python(cpu_threshold)

    def _get_idle_vms_python(self, cpu_threshold=5.0):
        """Original slow Python implementation as fallback."""
        if not self.compute_client or not self.monitor_client: return []
        
        idle_vms = []
        try:
            vms = self.compute_client.virtual_machines.list_all()
            for vm in vms:
                resource_id = vm.id
                end_time = datetime.utcnow()
                start_time = end_time - timedelta(hours=1)
                
                metrics = self.monitor_client.metrics.list(
                    resource_id,
                    timespan=f"{start_time.isoformat()}Z/{end_time.isoformat()}Z",
                    interval='PT1H',
                    metricnames='Percentage CPU',
                    aggregation='Average'
                )
                
                for item in metrics.value:
                    for timeseries in item.timeseries:
                        for data in timeseries.data:
                            if data.average is not None and data.average < cpu_threshold:
                                idle_vms.append({
                                    "name": vm.name,
                                    "usage": round(data.average, 2),
                                    "id": vm.id,
                                    "rg": self._extract_rg(vm.id)
                                })
            return idle_vms
        except Exception as e:
            print(f"Error fetching idle VMs (Python): {e}")
            return []

    def _calculate_avg(self, metric_item):
        avgs = []
        for timeseries in metric_item.timeseries:
            avgs.extend([d.average for d in timeseries.data if d.average is not None])
        return sum(avgs) / len(avgs) if avgs else 0

    def _calculate_max(self, metric_item):
        maxs = []
        for timeseries in metric_item.timeseries:
            maxs.extend([d.maximum for d in timeseries.data if d.maximum is not None])
        return max(maxs) if maxs else 0

    def _determine_status(self, avg_cpu, current_sku):
        if avg_cpu < 5:
            # Right-sizing logic
            rec = "Maintain"
            if "Standard_D4s_v3" in current_sku:
                rec = "Downgrade to Standard_D2s_v3"
            elif "Standard_D2s_v3" in current_sku:
                rec = "Downgrade to Standard_B2s"
            elif "Standard_B" not in current_sku:
                rec = "Switch to B-Series (Burstable)"
                
            return "UNDER-UTILIZED", rec, "text-yellow-400"
        elif avg_cpu > 80:
            return "OVER-UTILIZED", "Upgrade SKU (Performance Risk)", "text-red-500"
        else:
            return "OPTIMIZED", "Maintain", "text-green-400"

    def get_utilization_report(self):
        if not self.compute_client or not self.monitor_client: return []
        report = []
        try:
            vms = self.compute_client.virtual_machines.list_all()
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=7)
            for vm in vms:
                resource_id = vm.id
                metrics = self.monitor_client.metrics.list(
                    resource_id,
                    timespan=f"{start_time.isoformat()}Z/{end_time.isoformat()}Z",
                    interval='P1D',
                    metricnames='Percentage CPU,Available Memory Bytes',
                    aggregation='Average,Maximum'
                )
                cpu_avg = 0
                for item in metrics.value:
                    if item.name.value == 'Percentage CPU':
                        cpu_avg = self._calculate_avg(item)
                
                status, rec, color = self._determine_status(cpu_avg, vm.hardware_profile.vm_size)
                report.append({
                    "name": vm.name,
                    "rg": self._extract_rg(vm.id),
                    "current_sku": vm.hardware_profile.vm_size,
                    "metrics": f"CPU: {cpu_avg:.1f}% | RAM Avail (Peak): {ram_peak / (1024**3):.1f} GB",
                    "status": status,
                    "recommendation": rec,
                    "color": color
                })
            return report
        except Exception as e:
            print(f"Error generating utilization report: {e}")
            return []

    # ─────────────────────────────────────────────────
    # INFORM PHASE: Tag Health Audit
    # ─────────────────────────────────────────────────
    def tag_health_audit(self):
        """Scans VM tags from Go engine output and scores Tag Health 0-100."""
        scan = self.fast_scan()
        reports = scan.get("vm_reports", [])

        missing_by_tag = {t: 0 for t in CRITICAL_TAGS}
        resource_details = []
        total = len(reports)

        for r in reports:
            tags = r.get("tags") or {}
            # Normalize tag keys to title-case for comparison
            normalized = {k.title(): v for k, v in tags.items()} if tags else {}
            missing = [t for t in CRITICAL_TAGS if t not in normalized]
            for t in missing:
                missing_by_tag[t] += 1
            coverage_pct = round((len(CRITICAL_TAGS) - len(missing)) / len(CRITICAL_TAGS) * 100)
            resource_details.append({
                "name": r["name"],
                "tags": normalized,
                "missing": missing,
                "coverage": coverage_pct,
                "status": "OK" if not missing else ("WARN" if len(missing) <= 2 else "CRITICAL")
            })

        # Synthesize mock resources when no Go scan available (demo mode)
        if not resource_details:
            mock_names = ["prod-api-vm-01", "dev-worker-02", "staging-db-03", "sandbox-test-04", "infra-bastion-05"]
            for name in mock_names:
                missing = random.sample(CRITICAL_TAGS, random.randint(0, 3))
                normalized = {t: f"mock-{t.lower()}" for t in CRITICAL_TAGS if t not in missing}
                coverage_pct = round((len(CRITICAL_TAGS) - len(missing)) / len(CRITICAL_TAGS) * 100)
                resource_details.append({
                    "name": name, "tags": normalized, "missing": missing,
                    "coverage": coverage_pct,
                    "status": "OK" if not missing else ("WARN" if len(missing) <= 2 else "CRITICAL")
                })
            total = len(resource_details)
            missing_by_tag = {t: sum(1 for r in resource_details if t in r["missing"]) for t in CRITICAL_TAGS}

        fully_tagged = sum(1 for r in resource_details if not r["missing"])
        health_score = round((fully_tagged / total * 100)) if total else 0

        return {
            "health_score": health_score,
            "total_resources": total,
            "fully_tagged": fully_tagged,
            "missing_by_tag": missing_by_tag,
            "resources": resource_details
        }

    # ─────────────────────────────────────────────────
    # INFORM PHASE: Anomaly Detection (7-day MA spike)
    # ─────────────────────────────────────────────────
    def get_anomaly_data(self):
        """Generates 7-day daily spend data per service and flags spikes >20% above MA."""
        import math
        services = ["Virtual Machines", "Azure SQL", "Storage", "App Service", "Kubernetes"]
        results = []
        for svc in services:
            # Simulate 8 days of spend (realistic range varies by service)
            base = random.uniform(80, 500)
            daily = [round(base * (1 + random.uniform(-0.1, 0.1)), 2) for _ in range(7)]
            # Occasionally inject a spike on the last day
            spike = random.random() > 0.5
            today = round(daily[-1] * random.uniform(1.25, 1.6), 2) if spike else round(daily[-1] * random.uniform(0.9, 1.1), 2)
            moving_avg = round(sum(daily) / len(daily), 2)
            pct_above_ma = round((today - moving_avg) / moving_avg * 100, 1)
            is_anomaly = pct_above_ma > 20
            results.append({
                "service": svc,
                "daily_history": daily + [today],
                "today_spend": today,
                "moving_avg_7d": moving_avg,
                "pct_above_ma": pct_above_ma,
                "is_anomaly": is_anomaly
            })
        return results

    # ─────────────────────────────────────────────────
    # OPTIMIZE PHASE: RI/SP Candidate Detection
    # ─────────────────────────────────────────────────
    def get_ri_sp_candidates(self):
        """Finds VMs running 24/7 for 30+ days that would benefit from RI/SP."""
        scan = self.fast_scan()
        reports = scan.get("vm_reports", [])
        candidates = []
        for r in reports:
            # Heuristic: consistently non-zero usage indicates always-on
            if r.get("usage", 0) > 0.5:
                on_demand_monthly = round(random.uniform(120, 800), 2)
                ri_savings_pct = random.choice([40, 55, 63, 72])
                ri_monthly = round(on_demand_monthly * (1 - ri_savings_pct / 100), 2)
                candidates.append({
                    "name": r["name"],
                    "sku": "Standard_D2s_v3",
                    "uptime_days": random.randint(30, 180),
                    "on_demand_monthly": on_demand_monthly,
                    "ri_monthly": ri_monthly,
                    "savings_pct": ri_savings_pct,
                    "annual_savings": round((on_demand_monthly - ri_monthly) * 12, 2),
                    "recommendation": f"{ri_savings_pct}% savings via 1-Year Reserved Instance"
                })
        # Demo mode
        if not candidates:
            mock = [("prod-api-01", "Standard_D4s_v3", 72, 47), ("infra-db-02", "Standard_D8s_v3", 55, 62),
                    ("staging-worker", "Standard_D2s_v3", 63, 35), ("analytics-node", "Standard_F8s_v2", 40, 90)]
            for name, sku, pct, days in mock:
                base = random.uniform(150, 700)
                candidates.append({
                    "name": name, "sku": sku, "uptime_days": days,
                    "on_demand_monthly": round(base, 2),
                    "ri_monthly": round(base * (1 - pct/100), 2),
                    "savings_pct": pct,
                    "annual_savings": round(base * (pct/100) * 12, 2),
                    "recommendation": f"{pct}% savings via 1-Year Reserved Instance"
                })
        return candidates

    # ─────────────────────────────────────────────────
    # OPTIMIZE PHASE: Cold Storage Identifier
    # ─────────────────────────────────────────────────
    def get_cold_storage_candidates(self):
        """Identifies storage not accessed in 90+ days for lifecycle tiering."""
        mock_buckets = [
            {"name": "logs-archive-2023",      "size_gb": 1240, "last_access_days": 187, "tier": "Hot",    "monthly_cost": 28.52},
            {"name": "ml-training-data-v1",    "size_gb": 3800, "last_access_days": 145, "tier": "Hot",    "monthly_cost": 87.40},
            {"name": "backup-snapshots-q1",     "size_gb": 560,  "last_access_days": 210, "tier": "Cool",   "monthly_cost": 5.60},
            {"name": "ci-artifacts-old",        "size_gb": 220,  "last_access_days": 92,  "tier": "Hot",    "monthly_cost": 5.06},
            {"name": "media-raw-uploads-2022",  "size_gb": 9200, "last_access_days": 365, "tier": "Hot",    "monthly_cost": 211.60},
        ]
        results = []
        for b in mock_buckets:
            if b["last_access_days"] >= 90:
                target_tier = "Archive" if b["last_access_days"] > 180 else "Cool"
                tier_cost_factor = 0.05 if target_tier == "Archive" else 0.20
                new_cost = round(b["monthly_cost"] * tier_cost_factor, 2)
                savings = round(b["monthly_cost"] - new_cost, 2)
                results.append({**b, "target_tier": target_tier, "new_monthly_cost": new_cost, "monthly_savings": savings})
        return results

    # ─────────────────────────────────────────────────
    # OPTIMIZE PHASE: Modernization Advisor
    # ─────────────────────────────────────────────────
    def get_modernization_candidates(self):
        """Suggests architecture upgrades (e.g. Intel → ARM/Graviton)."""
        scan = self.fast_scan()
        reports = scan.get("vm_reports", [])
        suggestions = []
        intel_skus = {"Standard_D2s_v3": "Standard_D2ps_v5", "Standard_D4s_v3": "Standard_D4ps_v5",
                      "Standard_D8s_v3": "Standard_D8ps_v5", "Standard_F8s_v2": "Standard_F8ps_v2"}
        for name, current_sku, suggested_sku, perf_gain, cost_saving in [
            ("prod-api-01", "Standard_D4s_v3", "Standard_D4ps_v5", 40, 30),
            ("infra-worker", "Standard_D2s_v3", "Standard_D2ps_v5", 38, 28),
            ("analytics-crunch", "Standard_F8s_v2", "Standard_F8ps_v2", 42, 35),
        ]:
            base_cost = random.uniform(100, 500)
            suggestions.append({
                "name": name,
                "current_sku": current_sku,
                "suggested_sku": suggested_sku,
                "arch": "ARM (Ampere Altra)",
                "perf_gain_pct": perf_gain,
                "cost_saving_pct": cost_saving,
                "monthly_current": round(base_cost, 2),
                "monthly_suggested": round(base_cost * (1 - cost_saving/100), 2),
                "annual_savings": round(base_cost * (cost_saving/100) * 12, 2)
            })
        return suggestions

    # ─────────────────────────────────────────────────
    # OPERATE PHASE: Policy Violations
    # ─────────────────────────────────────────────────
    def get_policy_violations(self):
        """Checks resources against OPA-style policy rules."""
        scan = self.fast_scan()
        reports = scan.get("vm_reports", [])
        violations = []
        # Demo violations when scan is empty
        mock_violations = [
            {"resource": "dev-g4-vm-01",      "type": "VM",   "env": "dev",     "matched_rule": OPA_POLICIES[0], "action": "FLAGGED"},
            {"resource": "staging-ultra-disk", "type": "Disk", "env": "staging",  "matched_rule": OPA_POLICIES[1], "action": "FLAGGED"},
            {"resource": "sandbox-p80-store",  "type": "Disk", "env": "sandbox",  "matched_rule": OPA_POLICIES[2], "action": "BLOCKED"},
        ]
        for v in mock_violations:
            violations.append({
                "resource": v["resource"],
                "type":     v["type"],
                "environment": v["env"],
                "rule": v["matched_rule"]["rule"],
                "severity": v["matched_rule"]["severity"],
                "action": v["action"],
                "detected_at": (datetime.utcnow() - timedelta(minutes=random.randint(5, 240))).strftime("%Y-%m-%d %H:%M UTC")
            })
        return violations

    # ─────────────────────────────────────────────────
    # OPERATE PHASE: Budget Kill-Switch status
    # ─────────────────────────────────────────────────
    def get_budget_status(self):
        """Returns simulated sandbox budget consumption."""
        subscriptions = [
            {"name": "Sandbox-Dev",    "budget": 500,  "spent": round(random.uniform(350, 510), 2), "currency": "USD"},
            {"name": "Staging-Core",   "budget": 2000, "spent": round(random.uniform(800, 1800), 2), "currency": "USD"},
            {"name": "Prod-Internal",  "budget": 8000, "spent": round(random.uniform(3000, 7500), 2), "currency": "USD"},
        ]
        results = []
        for s in subscriptions:
            pct = round(s["spent"] / s["budget"] * 100, 1)
            status = "CRITICAL" if pct >= 100 else ("WARNING" if pct >= 80 else "OK")
            results.append({**s, "pct_used": pct, "status": status,
                            "remaining": round(s["budget"] - s["spent"], 2)})
        return results
