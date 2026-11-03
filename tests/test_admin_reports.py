import unittest
from unittest.mock import Mock, patch

from app import app
from routes.admin import admin_dashboard


class _ReportsCursor:
    def __init__(self):
        self.calls = []
        self.resorts = [
            {"resort_id": resort_id, "resort_name": f"Resort {resort_id}", "status": "Active"}
            for resort_id in range(1, 7)
        ]
        self.revenue_rows = [
            {"resort_id": resort_id, "resort_name": f"Resort {resort_id}", "bookings": 0, "revenue": 0}
            for resort_id in range(1, 7)
        ]
        self.one_rows = [
            {"total": 0},
            {"total": 0},
            {"occupied_nights": 0},
            {"average_rating": 0, "total_reviews": 0},
        ]

    def execute(self, statement, params=None):
        self.calls.append((statement, params))

    def fetchall(self):
        if not hasattr(self, "_resorts_returned"):
            self._resorts_returned = True
            return self.resorts
        return self.revenue_rows

    def fetchone(self):
        return self.one_rows.pop(0)

    def close(self):
        pass


class AdminReportsTests(unittest.TestCase):
    def test_reports_lists_the_same_six_resorts_as_properties(self):
        cursor = _ReportsCursor()
        connection = Mock()
        connection.cursor.return_value = cursor
        app.config["TESTING"] = True
        client = app.test_client()
        with client.session_transaction() as session:
            session["role"] = "owner"
            session["owner_id"] = 1

        with patch.object(admin_dashboard, "get_connection", return_value=connection):
            response = client.get("/reports")

        self.assertEqual(response.status_code, 200)
        for resort_id in range(1, 7):
            self.assertIn(f"Resort {resort_id}".encode(), response.data)
        resort_list_sql = cursor.calls[0][0]
        self.assertIn("FROM resorts ORDER BY resort_name", resort_list_sql)
        self.assertNotIn("owner_id", resort_list_sql)

        summary_sql, summary_params = cursor.calls[-1]
        self.assertIn("res.resort_id IN (%s,%s,%s,%s,%s,%s)", summary_sql)
        self.assertEqual(summary_params[-6:], (1, 2, 3, 4, 5, 6))


if __name__ == "__main__":
    unittest.main()
