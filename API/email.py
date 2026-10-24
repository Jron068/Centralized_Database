import base64
import json
import os
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask_mail import Message


class EmailDeliveryError(RuntimeError):
    """Raised when the configured email provider cannot deliver a message."""


def _send_local_smtp(to_email, subject, text, html):
    from app import app, mail

    if not app.config["MAIL_USERNAME"] or not app.config["MAIL_PASSWORD"]:
        raise EmailDeliveryError(
            "Local SMTP is not configured. Set MAIL_USERNAME and MAIL_PASSWORD."
        )
    message = Message(
        subject=subject,
        sender=app.config["MAIL_DEFAULT_SENDER"],
        recipients=[to_email],
        body=text,
        html=html,
    )
    try:
        mail.send(message)
    except OSError as error:
        raise EmailDeliveryError("Could not send email through local SMTP.") from error


def _google_oauth_settings():
    settings = {
        "GOOGLE_OAUTH_CLIENT_ID": os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip(),
        "GOOGLE_OAUTH_CLIENT_SECRET": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip(),
        "GOOGLE_OAUTH_REFRESH_TOKEN": os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN", "").strip(),
        "MAIL_DEFAULT_SENDER": os.getenv("MAIL_DEFAULT_SENDER", "").strip(),
    }
    if not all(settings.values()):
        raise EmailDeliveryError(
            "Gmail API is not configured. Set GOOGLE_OAUTH_CLIENT_ID, "
            "GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REFRESH_TOKEN, and "
            "MAIL_DEFAULT_SENDER in the hosting environment."
        )
    return settings


def _google_access_token(settings):
    request = Request(
        "https://oauth2.googleapis.com/token",
        data=urlencode({
            "client_id": settings["GOOGLE_OAUTH_CLIENT_ID"],
            "client_secret": settings["GOOGLE_OAUTH_CLIENT_SECRET"],
            "refresh_token": settings["GOOGLE_OAUTH_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        }).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            token_data = json.loads(response.read(64 * 1024))
    except HTTPError as error:
        raise EmailDeliveryError(
            f"Google OAuth rejected the email authorization (HTTP {error.code})."
        ) from error
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise EmailDeliveryError(
            "Could not reach Google OAuth to authorize email delivery."
        ) from error

    access_token = token_data.get("access_token")
    if not access_token:
        raise EmailDeliveryError("Google OAuth did not return an email access token.")
    return access_token


def send_email(to_email, subject, text, html=None):
    """Send email through Gmail API over HTTPS using an OAuth refresh token."""
    oauth_keys = (
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "GOOGLE_OAUTH_REFRESH_TOKEN",
    )
    if not any((os.getenv(key) or "").strip() for key in oauth_keys):
        if os.getenv("FLASK_DEBUG") == "1":
            _send_local_smtp(to_email, subject, text, html)
            return
        _google_oauth_settings()

    settings = _google_oauth_settings()
    message = EmailMessage()
    message["To"] = to_email
    message["From"] = settings["MAIL_DEFAULT_SENDER"]
    message["Subject"] = subject
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")
    request = Request(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        data=json.dumps({"raw": raw_message}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_google_access_token(settings)}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            if response.status not in (200, 202):
                raise EmailDeliveryError(
                    f"Gmail API rejected the message (HTTP {response.status})."
                )
            response.read(64 * 1024)
    except HTTPError as error:
        raise EmailDeliveryError(
            f"Gmail API rejected the message (HTTP {error.code}); verify Gmail API access and the gmail.send OAuth scope."
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise EmailDeliveryError(
            "Could not reach Gmail API to deliver the message."
        ) from error


def send_otp_email(to_email, code, minutes=5):
    """Send an account verification code through the Gmail API."""
    text = (
        f"Your Pansol Resorts verification code is {code}. "
        f"It expires in {minutes} minutes. Do not share this code."
    )
    html = (
        "<p>Your Pansol Resorts verification code is:</p>"
        f"<p style='font-size:24px;font-weight:bold'>{code}</p>"
        f"<p>It expires in {minutes} minutes. Do not share this code.</p>"
    )
    send_email(to_email, "Your Pansol Resorts verification code", text, html)
