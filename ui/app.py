from flask import Flask, render_template, jsonify, request, redirect, url_for
import sys
import os
from dotenv import load_dotenv

load_dotenv()

# Ensure the app can see the collectors and engine folders
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.azure_collector import AzureCollector
from engine.models import init_db
from collectors.auth_check import check_azure_status
from engine.calculator import CostCalculator
from collectors.config_manager import save_config

def is_first_run():
    sub_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    return not sub_id or len(sub_id) < 5

app = Flask(__name__)
init_db()
calc = CostCalculator()
settings_state = {
    "currency": "USD",
    "idle_strategy": "aggressive",
    "selected_subscriptions": [],
    "scheduled_sleep": {
        "enabled": False,
        "stop_time": "20:00",
        "start_time": "08:00"
    }
}

@app.before_request
def check_setup():
    # Allow access to static files and all API endpoints so they always work
    if request.path.startswith('/static') or request.path.startswith('/api/'):
        return
    
    # If it's the first run and the user isn't already going to settings
    if is_first_run() and request.endpoint != 'settings':
        return redirect(url_for('settings', mode='onboarding'))

@app.route('/')
def index():
    az = AzureCollector()
    user_name = az.get_user_name()
    sub_name = az.get_subscription_name()
    return render_template('index.html', user_name=user_name, sub_name=sub_name)

@app.route('/settings')
def settings():
    return render_template('settings.html')

@app.route('/api/settings/update', methods=['POST'])
def update_settings():
    data = request.json
    action = data.get('action')
    
    if action == 'set_currency':
        code = data.get('value')
        if calc.set_currency(code):
            settings_state['currency'] = code
            return jsonify({"status": "success", "msg": f"Currency set to {code}"})
        return jsonify({"status": "error", "msg": "Invalid currency code"}), 400
    
    if action == 'sync_pricebook':
        if calc.reload_prices():
            return jsonify({"status": "success", "msg": "Price book reloaded from YAML"})
        return jsonify({"status": "error", "msg": "File not found"}), 404
    
    if action == 'set_strategy':
        strategy = data.get('value')
        settings_state['idle_strategy'] = strategy
        return jsonify({"status": "success", "msg": f"Strategy set to {strategy}"})

    if action == 'save_subscriptions':
        subs = data.get('value', [])
        settings_state['selected_subscriptions'] = subs
        return jsonify({"status": "success", "msg": f"Target scope updated: {len(subs)} subscriptions"})

    if action == 'set_sleep_schedule':
        settings_state['scheduled_sleep'] = data.get('value')
        return jsonify({"status": "success", "msg": "Scheduled Sleep updated"})


    if action == 'initial_setup':
        # 1. Save to .env for future boots
        val = data.get('value')
        success = save_config(sub_id=val)
        
        if success:
            # 2. Trigger the Go Engine for a first-run health check
            # (Optional: You could run a dry-run scan here)
            return jsonify({"status": "success", "msg": "Environment configured"})
        else:
            return jsonify({"status": "error", "msg": "Could not write to .env"}), 500

    return jsonify({"status": "error", "msg": "Invalid action"}), 400

@app.route('/api/settings/auth')

def check_auth():
    import subprocess
    try:
        # Check if az is logged in
        subprocess.run(['az', 'account', 'show'], capture_output=True, check=True)
        return jsonify({"status": "success", "message": "Connected: Azure CLI (Active Subscription)"})
    except Exception:
        return jsonify({"status": "error", "message": "Disconnected: Please run 'az login'"})


@app.route('/api/settings/subscriptions')
def list_subscriptions():
    import subprocess
    import json
    try:
        # Path to the Go binary
        binary_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine-go', 'reaper-engine')
        
        # Check if binary exists
        if not os.path.exists(binary_path):
             subscriptions = [
                {"id": "sub-123-abc", "name": "Production-Internal (Mock)"},
                {"id": "sub-456-def", "name": "Staging-Sandbox (Mock)"},
                {"id": "sub-789-ghi", "name": "Legacy-Shared-Services (Mock)"}
            ]
             return jsonify(subscriptions)

        result = subprocess.run([binary_path, '--list-subs'], capture_output=True, text=True)
        if result.returncode == 0:
            subscriptions = json.loads(result.stdout)
            return jsonify(subscriptions)
        else:
            return jsonify({"error": result.stderr}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/pricing')
def pricing():
    return render_template('pricing.html')

@app.route('/finops')
def finops():
    return render_template('finops.html')

@app.route('/api/auth/status')
def auth_status():
    return jsonify(check_azure_status())

@app.route('/api/scan')
def scan():
    events = [
        {"msg": "Authenticating with Azure Identity...", "type": "info"},
    ]
    try:
        # Use selected subscriptions if any, otherwise fallback to default
        target_subs = settings_state.get('selected_subscriptions', [])
        if not target_subs:
            default_sub = os.getenv('AZURE_SUBSCRIPTION_ID')
            if default_sub:
                target_subs = [default_sub]
            else:
                return jsonify({"status": "error", "message": "No subscription ID configured."}), 400

        all_vms_count = 0
        all_orphans = []
        all_snapshots = []
        all_zombies = []
        all_idle_vms = []
        all_utilization_report = []
        
        az = AzureCollector()
        
        for sub_id in target_subs:
            events.append({"msg": f"Scanning subscription: {sub_id[:8]}...", "type": "info"})
            
            # Update collector for current sub
            az.subscription_id = sub_id
            az._scan_cache = None  # Force fresh scan for each subscription
            
            # Fetch inventory
            vms = az.get_vm_inventory()
            all_vms_count += len(vms)
            
            reap_data = az.get_orphaned_disks()
            all_orphans.extend(reap_data["disks"])
            all_snapshots.extend(reap_data["snapshots"])
            
            zombies = az.get_zombie_vms()
            all_zombies.extend(zombies)
            
            threshold = 2.0 if settings_state['idle_strategy'] == 'aggressive' else 10.0
            idle_vms = az.get_idle_vms(cpu_threshold=threshold)
            all_idle_vms.extend(idle_vms)
            
            try:
                utilization_report = az.get_utilization_report()
                all_utilization_report.extend(utilization_report)
            except Exception:
                pass

        total_savings = 0.0
        
        # Process Real Idle VMs
        formatted_idle = []
        for vm in all_idle_vms:
            cost = calc.calculate_monthly_cost('azure', 'compute', 'standard_d2s_v3')
            total_savings += cost
            formatted_idle.append({
                "name": vm['name'],
                "usage": vm['usage'],
                "savings": calc.format_price(cost),
                "rg": vm.get('rg', 'N/A')
            })

        # Process Real Orphaned Disks
        formatted_orphans = []
        for d in all_orphans:
            cost = calc.calculate_monthly_cost('azure', 'storage', 'premium_ssd_p6')
            total_savings += cost
            formatted_orphans.append({
                "name": d['name'],
                "size": f"{d.get('size_gb', 0)} GB",
                "savings": calc.format_price(cost),
                "rg": d.get('rg', 'N/A')
            })
            
        # Process Snapshots
        formatted_snapshots = []
        for s in all_snapshots:
            cost = calc.calculate_monthly_cost('azure', 'storage', 'premium_ssd_p6') * 0.5 # Snapshot discount
            total_savings += cost
            formatted_snapshots.append({
                "name": s['name'],
                "savings": calc.format_price(cost),
                "rg": s.get('rg', 'N/A')
            })

        # Process Zombies
        formatted_zombies = []
        for z in all_zombies:
            cost = calc.calculate_monthly_cost('azure', 'compute', 'standard_d2s_v3')
            total_savings += cost
            formatted_zombies.append({
                "name": z['name'],
                "usage": z['usage'],
                "savings": calc.format_price(cost),
                "rg": z.get('rg', 'N/A')
            })

        events.append({"msg": f"Global scan complete. {len(formatted_zombies)} zombies detected.", "type": "warning" if formatted_zombies else "success"})
            
        return jsonify({
            "status": "success",
            "vm_count": all_vms_count,
            "orphans": formatted_orphans,
            "snapshots": formatted_snapshots,
            "zombies": formatted_zombies,
            "idle_vms": formatted_idle,
            "utilization_report": all_utilization_report,
            "events": events,
            "total_savings": calc.format_price(total_savings)
        })



    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/prices')
def get_prices():
    try:
        az = AzureCollector()
        prices = az.get_live_prices()
        return jsonify({"status": "success", "prices": prices})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ─────────────────────────────────────────────────────────────────
# INFORM PHASE: Tag Health Audit
# ─────────────────────────────────────────────────────────────────
@app.route('/api/finops/tag-health')
def tag_health():
    try:
        az = AzureCollector()
        result = az.tag_health_audit()
        return jsonify({"status": "success", **result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ─────────────────────────────────────────────────────────────────
# INFORM PHASE: Anomaly Detection
# ─────────────────────────────────────────────────────────────────
@app.route('/api/finops/anomalies')
def anomalies():
    try:
        az = AzureCollector()
        data = az.get_anomaly_data()
        spike_count = sum(1 for d in data if d['is_anomaly'])
        return jsonify({"status": "success", "services": data, "spike_count": spike_count})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ─────────────────────────────────────────────────────────────────
# INFORM PHASE: Unit Economics
# ─────────────────────────────────────────────────────────────────
@app.route('/api/finops/unit-economics')
def unit_economics():
    try:
        import random
        az = AzureCollector()
        budget_data = az.get_budget_status()
        # Find the total actual spend across the mock budgets or actual budgets
        total_cloud_spend = sum([b.get('spent', 0) for b in budget_data])
        if total_cloud_spend == 0:
            total_cloud_spend = random.uniform(5000, 15000)
            
        # These would come from a real APM/telemetry source
        metrics = [
            {"metric": "Active Users",    "unit": "per 1K users",  "count": random.randint(8000, 15000)},
            {"metric": "CI/CD Builds",    "unit": "per Build",     "count": random.randint(400, 1200)},
            {"metric": "API Requests",    "unit": "per 1M req",   "count": random.randint(10, 80)},
            {"metric": "Data Processed",  "unit": "per TB",        "count": round(random.uniform(5, 50), 1)},
        ]
        
        # We split the total spend among the 4 business metrics for a realistic distribution
        for i, m in enumerate(metrics):
            m['total_spend'] = round(total_cloud_spend * [0.4, 0.2, 0.25, 0.15][i], 2)
            unit_count = m['count'] / 1000 if 'K' in m['unit'] else (m['count'] / 1_000_000 if 'M' in m['unit'] else m['count'])
            m['cost_per_unit'] = round(m['total_spend'] / max(unit_count, 1), 4)
            m['trend'] = round(random.uniform(-15, 25), 1)  # % change vs last month
            
        return jsonify({"status": "success", "metrics": metrics, "total_spend": round(total_cloud_spend, 2)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ─────────────────────────────────────────────────────────────────
# OPTIMIZE PHASE: RI/SP Advisor
# ─────────────────────────────────────────────────────────────────
@app.route('/api/finops/ri-advisor')
def ri_advisor():
    try:
        az = AzureCollector()
        candidates = az.get_ri_sp_candidates()
        total_annual_savings = sum(c['annual_savings'] for c in candidates)
        return jsonify({"status": "success", "candidates": candidates, "total_annual_savings": round(total_annual_savings, 2)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ─────────────────────────────────────────────────────────────────
# OPTIMIZE PHASE: Cold Storage Lifecycle
# ─────────────────────────────────────────────────────────────────
@app.route('/api/finops/cold-storage')
def cold_storage():
    try:
        az = AzureCollector()
        buckets = az.get_cold_storage_candidates()
        total_monthly_savings = sum(b['monthly_savings'] for b in buckets)
        return jsonify({"status": "success", "buckets": buckets, "total_monthly_savings": round(total_monthly_savings, 2)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ─────────────────────────────────────────────────────────────────
# OPTIMIZE PHASE: Modernization Advisor
# ─────────────────────────────────────────────────────────────────
@app.route('/api/finops/modernization')
def modernization():
    try:
        az = AzureCollector()
        suggestions = az.get_modernization_candidates()
        total_annual_savings = sum(s['annual_savings'] for s in suggestions)
        return jsonify({"status": "success", "suggestions": suggestions, "total_annual_savings": round(total_annual_savings, 2)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ─────────────────────────────────────────────────────────────────
# OPERATE PHASE: Policy-as-Code Guardrails
# ─────────────────────────────────────────────────────────────────
@app.route('/api/finops/policy-violations')
def policy_violations():
    try:
        az = AzureCollector()
        violations = az.get_policy_violations()
        critical = sum(1 for v in violations if v['severity'] == 'HIGH')
        return jsonify({"status": "success", "violations": violations, "critical_count": critical})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ─────────────────────────────────────────────────────────────────
# OPERATE PHASE: Budget Kill-Switch
# ─────────────────────────────────────────────────────────────────
@app.route('/api/finops/budget-status')
def budget_status():
    try:
        az = AzureCollector()
        budgets = az.get_budget_status()
        return jsonify({"status": "success", "budgets": budgets})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/finops/budget-killswitch', methods=['POST'])
def budget_killswitch():
    """Triggers automated stop of non-essential VMs in a subscription."""
    try:
        data = request.json
        sub_name = data.get('subscription', 'Unknown')
        # In production: call Azure SDK to deallocate VMs tagged non-essential
        import time
        time.sleep(0.5)  # Simulate action
        return jsonify({
            "status": "success",
            "message": f"Kill-switch activated for {sub_name}. 3 non-essential VMs scheduled for shutdown.",
            "vms_stopped": ["sandbox-test-01", "sandbox-test-02", "dev-worker-temp"],
            "estimated_savings": "$14.20/day"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
@app.route('/api/finops/burn-rate-forecast')
def burn_rate_forecast():
    try:
        az = AzureCollector()
        data = az.get_burn_rate_forecast()
        return jsonify({"status": "success", "forecast": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/finops/virtual-tags')
def virtual_tags():
    try:
        az = AzureCollector()
        data = az.get_virtual_tags()
        return jsonify({"status": "success", "virtual_tags": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/finops/greenops')
def greenops():
    try:
        az = AzureCollector()
        data = az.get_greenops_recommendations()
        return jsonify({"status": "success", "recommendations": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/finops/approve-reap', methods=['POST'])
def approve_reap():
    try:
        data = request.json
        resource_id = data.get('resource_id')
        resource_type = data.get('resource_type')
        
        if not resource_id:
            return jsonify({"status": "error", "message": "Missing resource_id"}), 400
            
        az = AzureCollector()
        result = az.execute_reap(resource_id, resource_type)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
