import requests


def send_discord_alert(title, message, color=0x3B82F6):
    """
    Sends a rich notification to Discord via Webhooks.
    """
    webhook_url = "https://discord.com/api/webhooks/YOUR_WEBHOOK_HERE"
    if "YOUR_WEBHOOK" in webhook_url:
        return False

    payload = {
        "embeds": [
            {
                "title": title,
                "description": message,
                "color": color,
            }
        ]
    }

    try:
        # Added timeout to fix S113
        response = requests.post(webhook_url, json=payload, timeout=10)
        return response.status_code == 204
    except Exception as e:
        print(f"[-] Discord Notify Failed: {e}")
        return False


def send_slack_alert(message):
    """
    Sends a simple text alert to Slack.
    """
    webhook_url = "https://hooks.slack.com/services/YOUR_WEBHOOK_HERE"
    if "YOUR_WEBHOOK" in webhook_url:
        return False

    payload = {"text": message}
    try:
        # Added timeout to fix S113
        response = requests.post(webhook_url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"[-] Slack Notify Failed: {e}")
        return False
