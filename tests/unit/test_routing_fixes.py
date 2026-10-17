import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from fastapi.testclient import TestClient

from reaper.web.app_async import app


class RoutingFixesTestCase(unittest.TestCase):
    """Test cases for URL path routing bug fixes."""

    def setUp(self):
        self.client = TestClient(app)

    def test_vault_config_alias_works(self):
        """Test that /api/vault/config alias routes correctly to vault_setup."""
        # This should not raise an ImportError
        payload = {"passcode": "test12345678", "confirm": "test12345678", "passcode_type": "password"}
        response = self.client.post("/api/vault/config", json=payload)

        # We expect either success (if vault not configured) or error (if already configured)
        # but NOT an ImportError or 500 due to the broken import
        self.assertNotEqual(response.status_code, 500)
        data = response.json()
        # The error should be about vault state, not about missing import
        if response.status_code != 200:
            self.assertIn("error", data.get("status", ""))
            self.assertNotIn("ImportError", str(data.get("message", "")))

    def test_vault_entry_id_with_invalid_string(self):
        """Test that invalid entry_id strings return 404 instead of 422."""
        # Mock vault as unlocked
        with patch("reaper.web.routers.vault._is_vault_unlocked", return_value=True):
            with patch("reaper.web.routers.vault._session_fernet", return_value=MagicMock()):
                # Test with non-numeric string
                response = self.client.get("/api/vault/entries/invalid")
                self.assertEqual(response.status_code, 404)
                data = response.json()
                self.assertEqual(data["status"], "error")
                self.assertIn("not found", data["message"].lower())

    def test_vault_entry_id_with_valid_string(self):
        """Test that valid entry_id strings work correctly."""
        with patch("reaper.web.routers.vault._is_vault_unlocked", return_value=True):
            with patch("reaper.web.routers.vault._session_fernet", return_value=MagicMock()):
                with patch("reaper.web.routers.vault.SessionLocal") as mock_session:
                    # Mock database returning no entry
                    mock_session.return_value.__enter__ = MagicMock()
                    mock_session.return_value.__exit__ = MagicMock()
                    mock_session.return_value.query.return_value.filter_by.return_value.first.return_value = None

                    response = self.client.get("/api/vault/entries/123")
                    self.assertEqual(response.status_code, 404)
                    data = response.json()
                    self.assertEqual(data["status"], "error")
                    self.assertIn("not found", data["message"].lower())

    def test_vault_delete_entry_id_with_invalid_string(self):
        """Test that invalid entry_id strings return 404 instead of 422 for DELETE."""
        with patch("reaper.web.routers.vault._is_vault_unlocked", return_value=True):
            # Test with non-numeric string
            response = self.client.delete("/api/vault/entries/invalid")
            self.assertEqual(response.status_code, 404)
            data = response.json()
            self.assertEqual(data["status"], "error")
            self.assertIn("not found", data["message"].lower())

    def test_finops_commitment_aliases_exist(self):
        """Test that commitment alias routes exist and delegate correctly."""
        # These should not return 404 (they may return other errors based on state)
        response = self.client.post("/api/finops/commitment/simulate", json={"hourly_spend": 10.0})
        self.assertNotEqual(response.status_code, 404)

        response = self.client.post("/api/finops/commitment/purchase", json={"simulation": {}})
        self.assertNotEqual(response.status_code, 404)

    def test_finops_budget_status_aliases_exist(self):
        """Test that budget status alias routes exist."""
        response = self.client.get("/api/finops/budget-status")
        self.assertNotEqual(response.status_code, 404)

        response = self.client.get("/api/finops/tag-health")
        self.assertNotEqual(response.status_code, 404)

    def test_resources_dismiss_with_slashes_workaround(self):
        """Test that /api/resources/dismiss accepts resource_id in body (for IDs with slashes)."""
        # This should work even with slashes in the ID
        resource_id_with_slashes = "/subscriptions/abc/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm1"
        payload = {"resource_id": resource_id_with_slashes, "reason": "Test"}
        response = self.client.post("/api/resources/dismiss", json=payload)

        # Should return success (mocked function)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")


if __name__ == "__main__":
    unittest.main()
