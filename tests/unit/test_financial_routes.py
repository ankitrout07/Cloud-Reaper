import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from fastapi.testclient import TestClient

from reaper.web.app_async import app


class FinancialRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.patcher = patch("reaper.web.app_async.is_first_run", return_value=False)
        self.mock_first_run = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_financial_page_redirect_or_load(self):
        """Test that the /financial page loads successfully with various tabs."""
        response = self.client.get("/financial")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Financial", response.content)
        self.assertIn(b"Budget", response.content)

        for tab in [
            "alerts",
            "business-metrics",
            "commitment-reports",
            "issues",
            "commitments",
            "savings-models",
        ]:
            response = self.client.get(f"/financial?tab={tab}")
            self.assertEqual(response.status_code, 200)

    @patch("reaper.web.app_async.SessionLocal")
    def test_add_business_metric_api(self, mock_session_local):
        """Test recording a new business metric via POST API."""
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session

        payload = {"metric_name": "TEST_USERS", "value": 1500, "unit": "Users"}

        response = self.client.post("/api/finops/business-metrics", json=payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("TEST_USERS", data["message"])

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_add_business_metric_api_validation(self):
        """Test validation on the business metric creation API."""
        payload = {"metric_name": "", "value": None, "unit": "Users"}

        response = self.client.post("/api/finops/business-metrics", json=payload)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["status"], "error")
