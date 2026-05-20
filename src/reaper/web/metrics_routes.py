# src/reaper/web/metrics_routes.py
from flask import Blueprint, jsonify, request
from reaper.engine.metrics_analyzer import FinOpsTelemetryAnalyzer
from reaper.engine.notifier import send_discord_alert, send_slack_alert

telemetry_bp = Blueprint('telemetry_api', __name__)
# Points to internal standard Prometheus routing endpoints
analyzer = FinOpsTelemetryAnalyzer(prometheus_url="http://localhost:9090")

@telemetry_bp.route('/api/v1/finops/telemetry-insights', methods=['POST'])
def get_telemetry_driven_insights():
    # Simulated mapping payload representing active PostgreSQL inventory rows
    # In practice, query your local database table 'resources' here
    mock_db_inventory = [
        {"resource_id": "aks-worker-01", "private_ip": "10.0.1.4", "sku_size": "Standard_D4_v5", "monthly_cost": 140.0},
        {"resource_id": "aks-worker-02", "private_ip": "10.0.1.5", "sku_size": "Standard_B2s", "monthly_cost": 30.0}
    ]

    try:
        actionable_insights = analyzer.analyze_compute_waste_index(mock_db_inventory)
        return jsonify({
            "status": "success",
            "telemetry_source": "Prometheus v1 Engine",
            "recommendations": actionable_insights
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": f"Telemetry parsing failure: {str(e)}"}), 500


@telemetry_bp.route('/api/v1/finops/test-webhook', methods=['POST'])
def test_alert_webhook():
    data = request.json or {}
    platform = data.get("platform", "").lower()
    webhook_url = data.get("webhook_url", "").strip()
    
    if not webhook_url:
        return jsonify({"status": "error", "message": "Webhook URL is required"}), 400
        
    # Standard security validation
    if not webhook_url.startswith("http://") and not webhook_url.startswith("https://"):
        return jsonify({"status": "error", "message": "Invalid webhook URL format"}), 400
        
    try:
        success = False
        if platform == "discord" or "discord.com" in webhook_url:
            success = send_discord_alert(
                title="🔔 Cloud-Reaper Webhook Active",
                message="Your Discord notification channel has been successfully verified!",
                color=0x00f3ff,
                webhook_url=webhook_url
            )
        elif platform == "slack" or "slack.com" in webhook_url:
            success = send_slack_alert(
                message="🔔 *Cloud-Reaper Webhook Active*\nYour Slack notification channel has been successfully verified!",
                webhook_url=webhook_url
            )
        else:
            return jsonify({"status": "error", "message": "Unrecognized or unsupported webhook platform"}), 400
            
        if success:
            return jsonify({"status": "success", "message": "Test notification sent successfully!"}), 200
        else:
            return jsonify({"status": "error", "message": "Test notification failed. Please verify the URL."}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": f"Alert dispatch failure: {str(e)}"}), 500
