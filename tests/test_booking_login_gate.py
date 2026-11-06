import unittest

from app import app
from routes.auth.login import _safe_next_url


class BookingLoginGateTests(unittest.TestCase):
    def test_guest_is_sent_to_login_before_opening_selected_resort(self):
        response = app.test_client().get("/book/resort/42")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            "/login?next=/resorts?resort_id%3D42",
        )

    def test_customer_is_sent_to_selected_resort(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session["role"] = "customer"
            session["account_id"] = 15

        response = client.get("/book/resort/42")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/resorts?resort_id=42")

    def test_login_page_preserves_the_resort_return_destination(self):
        response = app.test_client().get(
            "/login?next=%2Fresorts%3Fresort_id%3D42"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'name="next" value="/resorts?resort_id=42"', response.data)

    def test_external_and_protocol_relative_redirects_are_rejected(self):
        self.assertIsNone(_safe_next_url("https://example.com"))
        self.assertIsNone(_safe_next_url("//example.com"))
        self.assertIsNone(_safe_next_url("/\\example.com"))
        self.assertEqual(_safe_next_url("/resorts?resort_id=42"), "/resorts?resort_id=42")


if __name__ == "__main__":
    unittest.main()
