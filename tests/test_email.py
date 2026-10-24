import smtplib
import unittest
from unittest.mock import patch

from flask_mail import Mail

from API import email
from app import app


class EmailTests(unittest.TestCase):
    def test_otp_uses_configured_smtp_credentials_and_sender(self):
        settings = {
            "MAIL_USERNAME": "verify@example.test",
            "MAIL_PASSWORD": "test-app-password",
            "MAIL_DEFAULT_SENDER": "Pansol Resorts <verify@example.test>",
        }
        with patch.dict(app.config, settings):
            with app.app_context():
                with patch.object(Mail, "send") as smtp_send:
                    email.send_otp_email("guest@example.test", "123456", 5)

        message = smtp_send.call_args.args[0]
        self.assertEqual(message.sender, settings["MAIL_DEFAULT_SENDER"])
        self.assertEqual(message.recipients, ["guest@example.test"])
        self.assertIn("123456", message.body)
        self.assertIn("5 minutes", message.body)
        self.assertIn("123456", message.html)

    def test_missing_smtp_credentials_fails_without_sending(self):
        settings = {
            "MAIL_USERNAME": "",
            "MAIL_PASSWORD": "",
            "MAIL_DEFAULT_SENDER": "",
        }
        with patch.dict(app.config, settings):
            with app.app_context():
                with patch.object(Mail, "send") as smtp_send:
                    with self.assertRaises(email.EmailDeliveryError):
                        email.send_otp_email("guest@example.test", "123456")

        smtp_send.assert_not_called()

    def test_smtp_failure_is_reported_as_email_delivery_error(self):
        settings = {
            "MAIL_USERNAME": "verify@example.test",
            "MAIL_PASSWORD": "test-app-password",
            "MAIL_DEFAULT_SENDER": "verify@example.test",
        }
        with patch.dict(app.config, settings):
            with app.app_context():
                with patch.object(Mail, "send", side_effect=smtplib.SMTPException("failed")):
                    with self.assertRaises(email.EmailDeliveryError):
                        email.send_otp_email("guest@example.test", "123456")


if __name__ == "__main__":
    unittest.main()
