import unittest
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from unittest.mock import Mock, patch

from app import app
from routes.customer import booking_routes
from routes.auth import login as auth_login


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


class _SequenceCursor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.calls = []
        self.lastrowid = 321

    def execute(self, statement, params=None):
        self.calls.append((statement, params))

    def fetchone(self):
        return self.rows.pop(0)

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class CustomerBookingTests(unittest.TestCase):
    def test_booking_accepts_resort_configured_capacity_above_default_limit(self):
        cursor = _Cursor()
        cursor.rows[1]["max_pax"] = 200
        connection = Mock()
        connection.cursor.return_value = cursor
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
            "pax": "200",
            "mineral_water": "0",
        }

        with patch.object(booking_routes, "get_connection", return_value=connection):
            with patch.object(booking_routes, "notify_resort_caretakers"):
                response = client.post("/book_resort", data=booking_data)

        self.assertEqual(response.status_code, 201)
        insert_params = next(
            params for statement, params in cursor.calls
            if "INSERT INTO reservations" in statement
        )
        self.assertEqual(insert_params[7], 200)

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

    def test_pending_or_confirmed_reservations_mark_availability_as_booked(self):
        cursor = _SequenceCursor([
            {"resort_id": 1},
            {
                "check_in": date(2099, 12, 1),
                "check_out": date(2099, 12, 2),
            },
        ])
        connection = Mock()
        connection.cursor.return_value = cursor

        with patch.object(booking_routes, "get_connection", return_value=connection):
            response = app.test_client().get("/resort_availability/1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["booked_dates"], ["2099-12-01"])
        self.assertIn("status = 'Active'", cursor.calls[0][0])
        self.assertIn("reservation_status IN ('Pending', 'Confirmed')", cursor.calls[1][0])
        self.assertEqual(response.json["bookings"][0]["tour_type"], None)

    def test_inactive_resort_has_no_searchable_availability(self):
        cursor = _SequenceCursor([None])
        connection = Mock()
        connection.cursor.return_value = cursor

        with patch.object(booking_routes, "get_connection", return_value=connection):
            response = app.test_client().get("/resort_availability/99")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json["message"], "Resort not found or unavailable.")
        self.assertEqual(len(cursor.calls), 1)

    def test_availability_returns_exact_tour_time_window_for_filtering(self):
        cursor = _SequenceCursor([
            {"resort_id": 1},
            {
                "check_in": date(2099, 12, 1),
                "check_out": date(2099, 12, 2),
                "tour_type": "day",
                "start_at": datetime(2099, 12, 1, 8),
                "end_at": datetime(2099, 12, 1, 17),
            },
        ])
        connection = Mock()
        connection.cursor.return_value = cursor

        with patch.object(booking_routes, "get_connection", return_value=connection):
            response = app.test_client().get("/resort_availability/1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["bookings"][0]["tour_type"], "day")
        self.assertEqual(response.json["bookings"][0]["start_at"], "2099-12-01T08:00:00")
        self.assertEqual(response.json["bookings"][0]["end_at"], "2099-12-01T17:00:00")

    def test_booking_persists_package_specific_time_window_and_ten_percent_downpayment(self):
        for tour_type, expected_start, expected_end in (
            ("day", datetime(2099, 12, 1, 8), datetime(2099, 12, 1, 17)),
            ("night", datetime(2099, 12, 1, 19), datetime(2099, 12, 2, 6)),
        ):
            with self.subTest(tour_type=tour_type):
                cursor = _Cursor()
                connection = Mock()
                connection.cursor.return_value = cursor
                client = app.test_client()
                with client.session_transaction() as session:
                    session["role"] = "customer"
                    session["account_id"] = 44

                booking_data = {
                    "resort_id": "1",
                    "check_in": "2099-12-01",
                    "check_out": "2099-12-02",
                    "tour_type": tour_type,
                    "guest_name": "Test Guest",
                    "guest_phone": "09123456789",
                    "pax": "2",
                    "gas_stove": "false",
                    "mineral_water": "0",
                }
                with patch.object(booking_routes, "get_connection", return_value=connection):
                    with patch.object(booking_routes, "notify_resort_caretakers"):
                        response = client.post("/book_resort", data=booking_data)

                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.json["downpayment_amount"], "110.00")
                insert_sql, insert_params = next(
                    (statement, params)
                    for statement, params in cursor.calls
                    if "INSERT INTO reservations" in statement
                )
                self.assertIn("start_at, end_at, tour_type", insert_sql)
                self.assertEqual(insert_params[4], expected_start)
                self.assertEqual(insert_params[5], expected_end)

    def test_payment_submission_saves_sender_and_reference_details(self):
        cursor = _SequenceCursor([
            {"reservation_id": 321, "reservation_status": "Pending", "total_amount": Decimal("1500.00")},
            {"verified_total": Decimal("0.00"), "pending_count": 0},
        ])
        connection = Mock()
        connection.cursor.return_value = cursor
        client = app.test_client()
        with client.session_transaction() as session:
            session["role"] = "customer"
            session["account_id"] = 44

        payment_data = {
            "reservation_id": "321",
            "amount_paid": "150.00",
            "payment_method": "GCash",
            "payer_name": "Test Sender",
            "payer_phone": "09123456789",
            "reference_number": "TXN-12345",
            "proof": (BytesIO(b"receipt"), "receipt.png", "image/png"),
        }
        with patch.object(booking_routes, "get_connection", return_value=connection):
            with patch.object(booking_routes, "upload_file", return_value="payments/receipt.png"):
                response = client.post("/submit_payment", data=payment_data)

        self.assertEqual(response.status_code, 201)
        insert_sql, insert_params = next(
            (statement, params)
            for statement, params in cursor.calls
            if "INSERT INTO payments" in statement
        )
        self.assertIn("payer_name", insert_sql)
        self.assertIn("reference_number", insert_sql)
        self.assertEqual(insert_params[3:6], ("Test Sender", "09123456789", "TXN-12345"))
        connection.commit.assert_called_once()

    def test_payment_rejects_amounts_other_than_downpayment_or_full_balance(self):
        cursor = _SequenceCursor([
            {"reservation_id": 321, "reservation_status": "Pending", "total_amount": Decimal("1500.00")},
            {"verified_total": Decimal("0.00"), "pending_count": 0},
        ])
        connection = Mock()
        connection.cursor.return_value = cursor
        client = app.test_client()
        with client.session_transaction() as session:
            session["role"] = "customer"
            session["account_id"] = 44
        payment_data = {
            "reservation_id": "321",
            "amount_paid": "750.00",
            "payment_method": "GCash",
            "payer_name": "Test Sender",
            "payer_phone": "09123456789",
            "reference_number": "TXN-12345",
            "proof": (BytesIO(b"receipt"), "receipt.png", "image/png"),
        }
        with patch.object(booking_routes, "get_connection", return_value=connection):
            with patch.object(booking_routes, "upload_file") as upload_file:
                response = client.post("/submit_payment", data=payment_data)

        self.assertEqual(response.status_code, 400)
        upload_file.assert_not_called()
        connection.commit.assert_not_called()

    def test_forgot_password_sends_a_reset_link(self):
        cursor = _SequenceCursor([{"account_id": 44}, None])
        connection = Mock()
        connection.cursor.return_value = cursor
        with patch.object(auth_login, "get_connection", return_value=connection):
            with patch.object(auth_login, "send_email") as send_email:
                response = app.test_client().post(
                    "/forgot-password",
                    data={"email": "guest@example.com"},
                )

        self.assertEqual(response.status_code, 302)
        send_email.assert_called_once()
        self.assertIn("/reset-password/", send_email.call_args.args[2])
        self.assertTrue(any("INSERT INTO password_resets" in statement for statement, _ in cursor.calls))
        connection.commit.assert_called_once()

    def test_password_reset_updates_password_and_invalidates_token(self):
        cursor = _SequenceCursor([{"account_id": 44}])
        connection = Mock()
        connection.cursor.return_value = cursor
        with patch.object(auth_login, "get_connection", return_value=connection):
            response = app.test_client().post(
                "/reset-password/one-time-token",
                data={"password": "new-strong-password", "confirm_password": "new-strong-password"},
            )

        self.assertEqual(response.status_code, 302)
        updates = [statement for statement, _ in cursor.calls]
        self.assertTrue(any("UPDATE accounts SET password" in statement for statement in updates))
        self.assertTrue(any("DELETE FROM password_resets" in statement for statement in updates))
        connection.commit.assert_called_once()

    def test_customer_can_cancel_a_pending_reservation(self):
        cursor = _SequenceCursor([{
            "reservation_id": 123,
            "resort_id": 5,
            "reservation_status": "Pending",
        }])
        connection = Mock()
        connection.cursor.return_value = cursor
        client = app.test_client()
        with client.session_transaction() as session:
            session["role"] = "customer"
            session["account_id"] = 44

        with patch.object(booking_routes, "get_connection", return_value=connection):
            with patch.object(booking_routes, "notify_resort_caretakers"):
                response = client.post(
                    "/customer/reservations/123/decision",
                    data={"decision": "cancel"},
                )

        self.assertEqual(response.status_code, 302)
        updates = [statement for statement, _ in cursor.calls if "UPDATE reservations" in statement]
        self.assertTrue(any("customer_decision = 'Cancelled'" in statement for statement in updates))
        self.assertTrue(any("reservation_status = 'Cancelled'" in statement for statement in updates))
        connection.commit.assert_called_once()

    def test_customer_can_confirm_they_want_to_continue(self):
        cursor = _SequenceCursor([{
            "reservation_id": 123,
            "resort_id": 5,
            "reservation_status": "Pending",
        }])
        connection = Mock()
        connection.cursor.return_value = cursor
        client = app.test_client()
        with client.session_transaction() as session:
            session["role"] = "customer"
            session["account_id"] = 44

        with patch.object(booking_routes, "get_connection", return_value=connection):
            with patch.object(booking_routes, "notify_resort_caretakers"):
                response = client.post(
                    "/customer/reservations/123/decision",
                    data={"decision": "continue"},
                )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(any(
            "SET customer_decision = 'Continue'" in statement
            for statement, _ in cursor.calls
        ))
        connection.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
