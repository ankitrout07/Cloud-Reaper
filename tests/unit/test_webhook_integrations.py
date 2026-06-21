from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from reaper.web.app_async import app, settings_state


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def test_update_integrations_settings(client):
    settings_state["discord_webhook_url"] = ""
    settings_state["slack_webhook_url"] = ""
    settings_state["webhook_url"] = ""

    payload = {
        "action": "update_integrations",
        "discord_webhook_url": "https://discord.com/api/webhooks/12345/abcde",
        "slack_webhook_url": "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX",
    }

    response = client.post("/api/settings/update", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    assert settings_state["discord_webhook_url"] == "https://discord.com/api/webhooks/12345/abcde"
    assert (
        settings_state["slack_webhook_url"]
        == "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"
    )
    assert settings_state["webhook_url"] == "https://discord.com/api/webhooks/12345/abcde"


def test_test_webhook_endpoint_discord_success(client):
    with patch("reaper.engine.notifications.notifier.requests.post") as mock_post:
        mock_post.return_value.status_code = 204

        payload = {"platform": "discord", "webhook_url": "https://discord.com/api/webhooks/test"}

        response = client.post("/api/v1/finops/test-webhook", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "Test notification sent successfully!" in data["message"]

        mock_post.assert_called_once()


def test_test_webhook_endpoint_slack_success(client):
    with patch("reaper.engine.notifications.notifier.requests.post") as mock_post:
        mock_post.return_value.status_code = 200

        payload = {"platform": "slack", "webhook_url": "https://hooks.slack.com/services/test"}

        response = client.post("/api/v1/finops/test-webhook", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

        mock_post.assert_called_once()


def test_test_webhook_endpoint_invalid_platform(client):
    payload = {"platform": "unsupported", "webhook_url": "https://unknown.com/services/test"}

    response = client.post("/api/v1/finops/test-webhook", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert data["status"] == "error"
    assert "Unrecognized" in data["message"]


def test_test_webhook_endpoint_invalid_url(client):
    payload = {"platform": "slack", "webhook_url": "ftp://hooks.slack.com/services/test"}

    response = client.post("/api/v1/finops/test-webhook", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert data["status"] == "error"
    assert "Invalid webhook URL format" in data["message"]
