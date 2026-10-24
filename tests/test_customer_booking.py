import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

from app import app
from routes.customer import booking_routes


class _Cursor:
    def __init__(self):
        self.rows = [
            {"customer_id": 7},
            {"resort_id": 1, "price": Decimal("1100.00"), "max_pax": 12},
            {"role": "customer", "is_verified": True, "account_status": "Active"},
            None,
        ]
        self.calls = []
        self.lastrowid = 123

    def execute(self, statement, params=None):
        self.calls.append((statement, params))

    def fetchone(self):
        return self.rows.pop(0)

    def close(self):
        pass


class CustomerBookingTests(unittest.TestCase):
    def test_booking_saves_gas_stove_as_smallint_compatible_value(self):
        cursor = _Cursor()
        connection = Mock()
        connection.cursor.return_value = cursor

        app.config["TESTING"] = True
        client = app.test_client()
        with client.session_transaction() as session:
            session["role"] = "customer"
            session["account_id"] = 44

        booking_data = {
            "resort_id": "1",
            "check_in": "2099-12-01",
            "check_out": "2099-12-02",
            "tour_type": "day",
            "guest_name": "Test Guest",
            "guest_phone": "09123456789",
            "pax": "2",
            "gas_stove": "true",
            "mineral_water": "0",
        }

        with patch.object(booking_routes, "get_connection", return_value=connection):
            with patch.object(booking_routes, "notify_resort_caretakers"):
                response = client.post("/book_resort", data=booking_data)

        self.assertEqual(response.status_code, 201)
        insert_sql, insert_params = next(
            (statement, params)
            for statement, params in cursor.calls
            if "INSERT INTO reservations" in statement
        )
        self.assertIn("gas_stove", insert_sql)
        self.assertEqual(insert_params[-1], 1)
        self.assertIs(type(insert_params[-1]), int)
        connection.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
