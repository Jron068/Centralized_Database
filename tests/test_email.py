import base64
import json
import os
import unittest
from email import message_from_bytes
from unittest.mock import patch

from flask_mail import Mail

from API import email
from app import app


class _Response:
    def __init__(self, payload, status=200):
        self.payload = json.dumps(payload).encode()
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.payload[:size]


class EmailTests(unittest.TestCase):
    def setUp(self):
        self.google_environment = {
            "GOOGLE_OAUTH_CLIENT_ID": "client-id",
            "GOOGLE_OAUTH_CLIENT_SECRET": "client-secret",
            "GOOGLE_OAUTH_REFRESH_TOKEN": "refresh-token",
            "MAIL_DEFAULT_SENDER": "Pansol Resorts <verify@example.test>",
            "FLASK_DEBUG": "0",
        }

    def test_otp_uses_gmail_api_over_https(self):
        responses = [
            _Response({"access_token": "access-token"}),
            _Response({"id": "message-id"}),
        ]
        with patch.dict(os.environ, self.google_environment, clear=True):
            with patch.object(email, "urlopen", side_effect=responses) as send:
                email.send_otp_email("guest@example.test", "123456", 5)

        token_request, message_request = [call.args[0] for call in send.call_args_list]
        self.assertEqual(token_request.full_url, "https://oauth2.googleapis.com/token")
        self.assertEqual(
            message_request.full_url,
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        )
        self.assertEqual(message_request.get_header("Authorization"), "Bearer access-token")
        self.assertEqual(send.call_args_list[0].kwargs["timeout"], 10)
        self.assertEqual(send.call_args_list[1].kwargs["timeout"], 10)

        raw = json.loads(message_request.data)["raw"]
        raw += "=" * (-len(raw) % 4)
        parsed_message = message_from_bytes(base64.urlsafe_b64decode(raw))
        self.assertEqual(parsed_message["To"], "guest@example.test")
        self.assertEqual(parsed_message["From"], self.google_environment["MAIL_DEFAULT_SENDER"])
        self.assertIn("123456", parsed_message.get_payload()[0].get_payload(decode=True).decode())

    def test_production_without_oauth_credentials_fails_before_network_request(self):
        with patch.dict(os.environ, {"FLASK_DEBUG": "0"}, clear=True):
            with patch.object(email, "urlopen") as send:
                with self.assertRaises(email.EmailDeliveryError):
                    email.send_otp_email("guest@example.test", "123456")
        send.assert_not_called()

    def test_local_debug_can_continue_using_smtp(self):
        with patch.dict(os.environ, {"FLASK_DEBUG": "1"}, clear=True):
            with patch.dict(app.config, {
                "MAIL_USERNAME": "verify@example.test",
                "MAIL_PASSWORD": "local-test-password",
                "MAIL_DEFAULT_SENDER": "verify@example.test",
            }):
                with app.app_context():
                    with patch.object(Mail, "send") as smtp_send:
                        email.send_otp_email("guest@example.test", "123456", 5)
        message = smtp_send.call_args.args[0]
        self.assertEqual(message.recipients, ["guest@example.test"])
        self.assertIn("123456", message.body)

    def test_partial_oauth_configuration_does_not_fall_back_to_smtp(self):
        environment = {
            "FLASK_DEBUG": "1",
            "GOOGLE_OAUTH_CLIENT_ID": "client-id",
        }
        with patch.dict(os.environ, environment, clear=True):
            with patch.object(Mail, "send") as smtp_send:
                with self.assertRaises(email.EmailDeliveryError):
                    email.send_otp_email("guest@example.test", "123456")
        smtp_send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
