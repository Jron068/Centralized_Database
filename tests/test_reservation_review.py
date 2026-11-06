import unittest
from unittest.mock import Mock, patch

from app import app
import routes.admin.reservation as admin_reservations
import routes.caretaker as caretaker_routes


class ReservationReviewTests(unittest.TestCase):
    def test_owner_can_approve_online_booking_with_pending_payment(self):
        cursor = Mock()
        cursor.fetchone.return_value = {
            "reservation_id": 37,
            "resort_id": 4,
            "check_in": None,
            "check_out": None,
            "start_at": None,
            "end_at": None,
            "reservation_status": "Pending",
            "customer_decision": "Continue",
            "account_id": 12,
            "payment_id": 81,
            "payment_status": "Pending",
            "owner_id": 3,
            "booking_source": "Online",
        }
        connection = Mock()
        connection.cursor.return_value = cursor
        client = app.test_client()
        with client.session_transaction() as session:
            session["role"] = "owner"
            session["account_id"] = 3

        with patch.object(admin_reservations, "get_connection", return_value=connection):
            with patch.object(admin_reservations, "_walkin_schema", return_value={"walkin_expr": "FALSE"}):
                with patch.object(admin_reservations, "_dates_conflict", return_value=None):
                    with patch.object(admin_reservations, "notify_resort_caretakers"):
                        response = client.post(
                            "/admin/reservations/37/review",
                            data={"action": "approve"},
                        )

        self.assertEqual(response.status_code, 302)
        review_query = cursor.execute.call_args_list[0].args[0]
        self.assertIn("FOR UPDATE OF r", review_query)
        self.assertTrue(any(
            "UPDATE reservations SET reservation_status" in call.args[0]
            for call in cursor.execute.call_args_list
        ))
        connection.commit.assert_called_once()

    def test_caretaker_can_reject_pending_request_before_payment(self):
        cursor = Mock()
        cursor.fetchone.return_value = {
            "reservation_id": 38,
            "resort_id": 4,
            "check_in": None,
            "check_out": None,
            "start_at": None,
            "end_at": None,
            "customer_account_id": 13,
            "reservation_status": "Pending",
            "customer_decision": "Pending",
            "payment_id": None,
            "payment_status": None,
        }
        connection = Mock()
        connection.cursor.return_value = cursor
        client = app.test_client()
        with client.session_transaction() as session:
            session["role"] = "caretaker"
            session["account_id"] = 20

        with patch.object(caretaker_routes, "get_connection", return_value=connection):
            with patch.object(caretaker_routes, "_walkin_schema", return_value={"walkin_expr": "FALSE"}):
                with patch.object(caretaker_routes, "_customer_visible_clause", return_value="TRUE"):
                    response = client.post(
                        "/caretaker/reservations/38/review",
                        data={"action": "reject"},
                    )

        self.assertEqual(response.status_code, 302)
        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertIn("FOR UPDATE OF r", statements[0])
        self.assertTrue(any("UPDATE reservations SET reservation_status" in sql for sql in statements))
        self.assertFalse(any("UPDATE payments SET payment_status" in sql for sql in statements))
        connection.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
