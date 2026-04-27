from flask import Flask, render_template, jsonify
import sys
import os

# Ensure the app can see the collectors and engine folders
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.azure_collector import AzureCollector
from engine.calculator import CostCalculator

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/pricing')
def pricing():
    return render_template('pricing.html')

@app.route('/api/scan')
def scan():
    events = [
        {"msg": "Authenticating with Azure Identity...", "type": "info"},
    ]
    try:
        az = AzureCollector()
        calc = CostCalculator()
        
        events.append({"msg": "Fetching resource inventory from Azure...", "type": "info"})
        # Real-time fetch from your Azure Tenant
        orphans = az.get_orphaned_disks()
        
        events.append({"msg": f"Found {len(orphans)} orphaned disks.", "type": "info"})
        
        # Ensure we have some data even if the collector is being updated
        try:
            events.append({"msg": "Querying CPU/Memory metrics for rightsizing...", "type": "info"})
            idle_vms = az.get_idle_vms()
        except AttributeError:
            idle_vms = []
            
        vms = az.get_vm_inventory()
        
        total_savings = 0.0
        
        # Process Real Idle VMs (P2)
        formatted_idle = []
        for vm in idle_vms:
            # In your case, vm['name'] will now be 'app1'
            cost = calc.calculate_monthly_cost('azure', 'compute', 'standard_d2s_v3')
            total_savings += cost
            formatted_idle.append({
                "name": vm['name'],
                "usage": vm['usage'],
                "savings": f"${cost:.2f}",
                "rg": vm.get('rg', 'N/A')
            })

        # Process Real Orphaned Disks (P1)
        formatted_orphans = []
        for d in orphans:
            cost = calc.calculate_monthly_cost('azure', 'storage', 'premium_ssd_p6_64gb')
            total_savings += cost
            formatted_orphans.append({
                "name": d['name'],
                "size": f"{d['size_gb']} GB",
                "savings": f"${cost:.2f}",
                "rg": d.get('rg', 'N/A')
            })
            
        # 7-Day Utilization Report
        try:
            utilization_report = az.get_utilization_report()
            events.append({"msg": "7-day utilization report generated.", "type": "info"})
        except AttributeError:
            utilization_report = []
            
        events.append({"msg": "Scan complete. Targets identified.", "type": "success"})
            
        return jsonify({
            "status": "success",
            "vm_count": len(vms),
            "orphans": formatted_orphans,
            "idle_vms": formatted_idle,
            "utilization_report": utilization_report,
            "events": events,
            "total_savings": f"${total_savings:.2f}"
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
