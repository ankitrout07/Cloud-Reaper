import threading

import requests


def send_discord_alert(title, message, color=0x3B82F6, webhook_url=None, async_mode=True):
    """
    Sends a rich notification to Discord via Webhooks.
    
    Args:
        title: Alert title
        message: Alert message content
        color: Embed color (hex integer)
        webhook_url: Discord webhook URL
        async_mode: If True, sends alert in background thread to avoid blocking
    """
    if not webhook_url:
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

    def _send_alert():
        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            return response.status_code in [200, 204]
        except Exception as e:
            print(f"[-] Discord Notify Failed: {e}")
            return False

    if async_mode:
        # Send in background thread to avoid blocking main execution
        thread = threading.Thread(target=_send_alert, daemon=True)
        thread.start()
        return True
    return _send_alert()


def send_slack_alert(message, webhook_url=None, async_mode=True):
    """
    Sends a simple text alert to Slack.
    
    Args:
        message: Alert message content
        webhook_url: Slack webhook URL
        async_mode: If True, sends alert in background thread to avoid blocking
    """
    if not webhook_url:
        webhook_url = "https://hooks.slack.com/services/YOUR_WEBHOOK_HERE"

    if "YOUR_WEBHOOK" in webhook_url:
        return False

    payload = {"text": message}
    
    def _send_alert():
        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"[-] Slack Notify Failed: {e}")
            return False

    if async_mode:
        # Send in background thread to avoid blocking main execution
        thread = threading.Thread(target=_send_alert, daemon=True)
        thread.start()
        return True
    return _send_alert()
