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

@app.route('/api/scan')
def scan():
    try:
        az = AzureCollector()
        calc = CostCalculator()
        
        orphans = az.get_orphaned_disks()
        vms = az.get_vm_inventory()
        
        formatted_orphans = []
        total_savings = 0.0
        
        for d in orphans:
            cost = calc.calculate_monthly_cost('azure', 'disk', 'premium_ssd_p6_64gb')
            total_savings += cost
            formatted_orphans.append({
                "name": d['name'],
                "size": f"{d['size_gb']} GB",
                "savings": f"${cost:.2f}"
            })
            
        return jsonify({
            "status": "success",
            "vm_count": len(vms),
            "orphans": formatted_orphans,
            "total_savings": f"${total_savings:.2f}"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
