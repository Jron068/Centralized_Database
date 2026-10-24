import smtplib

from flask_mail import Message


class EmailDeliveryError(RuntimeError):
    """Raised when the configured email provider cannot deliver a message."""


def send_otp_email(to_email, code, minutes=5):
    """Send an account verification code using the configured SMTP server."""
    from app import app, mail

    required_settings = ("MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_DEFAULT_SENDER")
    missing_settings = [
        setting for setting in required_settings
        if not (app.config.get(setting) or "").strip()
    ]
    if missing_settings:
        raise EmailDeliveryError(
            "Email delivery is not configured. Set MAIL_USERNAME, MAIL_PASSWORD, "
            "and MAIL_DEFAULT_SENDER in the hosting environment."
        )

    text = (
        f"Your Pansol Resorts verification code is {code}. "
        f"It expires in {minutes} minutes. Do not share this code."
    )
    html = (
        "<p>Your Pansol Resorts verification code is:</p>"
        f"<p style='font-size:24px;font-weight:bold'>{code}</p>"
        f"<p>It expires in {minutes} minutes. Do not share this code.</p>"
    )
    message = Message(
        subject="Your Pansol Resorts verification code",
        sender=app.config["MAIL_DEFAULT_SENDER"],
        recipients=[to_email],
        body=text,
        html=html,
    )
    try:
        mail.send(message)
    except (smtplib.SMTPException, OSError) as error:
        raise EmailDeliveryError(
            "Could not send the verification email through the configured SMTP server."
        ) from error
