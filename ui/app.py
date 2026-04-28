from flask import Flask, render_template, jsonify, request, redirect, url_for
import sys
import os
from dotenv import load_dotenv

load_dotenv()

# Ensure the app can see the collectors and engine folders
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.azure_collector import AzureCollector
from collectors.auth_check import check_azure_status
from engine.calculator import CostCalculator
from collectors.config_manager import save_config

def is_configured():
    # Checks if the Subscription ID exists in environment or .env
    return os.getenv("AZURE_SUBSCRIPTION_ID") is not None

app = Flask(__name__)
calc = CostCalculator()
settings_state = {
    "currency": "USD",
    "idle_strategy": "aggressive",
    "selected_subscriptions": []
}

@app.before_request
def redirect_to_setup():
    # If not configured and not already on the settings page or static files
    if not is_configured() and request.endpoint not in ['settings', 'static', 'update_settings', 'save_initial_setup']:
        return redirect(url_for('settings', setup=True))

@app.route('/')
def index():
    return render_template('index.html')

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

    return jsonify({"status": "error", "msg": "Invalid action"}), 400

@app.route('/api/settings/initial-setup', methods=['POST'])
def save_initial_setup():
    data = request.json
    sub_id = data.get('sub_id')
    if not sub_id:
        return jsonify({"status": "error", "msg": "Subscription ID is required"}), 400
    
    if save_config(sub_id):
        return jsonify({"status": "success", "msg": "Configuration saved successfully"})
    return jsonify({"status": "error", "msg": "Failed to save configuration"}), 500

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
        all_idle_vms = []
        all_utilization_report = []
        
        az = AzureCollector()
        
        for sub_id in target_subs:
            events.append({"msg": f"Scanning subscription: {sub_id[:8]}...", "type": "info"})
            
            # Update collector for current sub
            az.subscription_id = sub_id
            az._scan_cache = None # Force fresh scan for each sub
            
            # Fetch inventory
            vms = az.get_vm_inventory()
            all_vms_count += len(vms)
            
            orphans = az.get_orphaned_disks()
            all_orphans.extend(orphans)
            
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
            cost = calc.calculate_monthly_cost('azure', 'storage', 'premium_ssd_p6_64gb')
            total_savings += cost
            formatted_orphans.append({
                "name": d['name'],
                "size": f"{d.get('size_gb', 0)} GB",
                "savings": calc.format_price(cost),
                "rg": d.get('rg', 'N/A')
            })
            
        events.append({"msg": "Global scan complete. Aggregate targets identified.", "type": "success"})
            
        return jsonify({
            "status": "success",
            "vm_count": all_vms_count,
            "orphans": formatted_orphans,
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
        # If no prices, maybe trigger a scan or return empty
        return jsonify({"status": "success", "prices": prices})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
