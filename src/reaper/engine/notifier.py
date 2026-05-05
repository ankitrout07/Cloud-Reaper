import requests
import json
import os

def send_discord_alert(title, message, color=0x00ffff):
    """
    Sends a rich glassmorphism-style embed alert to Discord.
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("[-] Discord Webhook URL not configured. Skipping alert.")
        return False
        
    payload = {
        "embeds": [{
            "title": f"🛡️ {title}",
            "description": message,
            "color": color, # Cyan for Cloud-Reaper branding
            "footer": {"text": "Cloud-Reaper FinOps Engine v1.0"},
            "timestamp": None # Could add ISO timestamp here
        }]
    }
    
    try:
        response = requests.post(webhook_url, json=payload)
        return response.status_code == 204
    except Exception as e:
        print(f"[-] Discord Notification Failed: {e}")
        return False

def send_slack_alert(message):
    """
    Placeholder for Slack integration.
    """
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return False
        
    payload = {"text": message}
    try:
        response = requests.post(webhook_url, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"[-] Slack Notification Failed: {e}")
        return False
