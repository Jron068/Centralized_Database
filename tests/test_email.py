import io
import json
import os
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from flask_mail import Mail

from API import email


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return b'{"id":"message-id"}'


class EmailTests(unittest.TestCase):
    def test_otp_uses_resend_https_api_with_bounded_timeout(self):
        environment = {
            "RESEND_API_KEY": "test-api-key",
            "MAIL_DEFAULT_SENDER": "Pansol Resorts <verify@example.test>",
            "FLASK_DEBUG": "0",
        }
        with patch.dict(os.environ, environment, clear=True):
            with patch.object(email, "urlopen", return_value=_Response()) as send:
                email.send_otp_email("guest@example.test", "123456", 5)

        request = send.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "https://api.resend.com/emails")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-api-key")
        self.assertEqual(request.get_header("User-agent"), "PansolResorts/1.0")
        self.assertEqual(payload["to"], ["guest@example.test"])
        self.assertEqual(payload["from"], "Pansol Resorts <verify@example.test>")
        self.assertIn("123456", payload["text"])
        self.assertEqual(send.call_args.kwargs["timeout"], 10)

    def test_production_without_resend_configuration_fails_without_smtp(self):
        with patch.dict(os.environ, {"FLASK_DEBUG": "0"}, clear=True):
            with patch.object(Mail, "send") as smtp_send:
                with self.assertRaises(email.EmailDeliveryError):
                    email.send_otp_email("guest@example.test", "123456")

        smtp_send.assert_not_called()

    def test_resend_requires_sender_address(self):
        with patch.dict(
            os.environ,
            {"RESEND_API_KEY": "test-api-key", "FLASK_DEBUG": "0"},
            clear=True,
        ):
            with patch.object(email, "urlopen") as send:
                with self.assertRaises(email.EmailDeliveryError):
                    email.send_otp_email("guest@example.test", "123456")

        send.assert_not_called()

    def test_resend_error_includes_provider_reason_without_email_address(self):
        response = HTTPError(
            "https://api.resend.com/emails",
            403,
            "Forbidden",
            {},
            io.BytesIO(
                b'{"name":"validation_error","message":"Only send to '
                b'account@example.com"}'
            ),
        )
        environment = {
            "RESEND_API_KEY": "test-api-key",
            "MAIL_DEFAULT_SENDER": "Pansol Resorts <onboarding@resend.dev>",
            "FLASK_DEBUG": "0",
        }
        with patch.dict(os.environ, environment, clear=True):
            with patch.object(email, "urlopen", side_effect=response):
                with self.assertRaises(email.EmailDeliveryError) as raised:
                    email.send_otp_email("guest@example.test", "123456")

        self.assertIn("HTTP 403", str(raised.exception))
        self.assertIn("Only send to [redacted email]", str(raised.exception))
        self.assertNotIn("account@example.com", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
