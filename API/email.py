import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask_mail import Message


def _provider_error_detail(error):
    """Return a bounded provider message without exposing recipient addresses."""
    try:
        body = error.read(4096).decode("utf-8", errors="replace")
        parsed = json.loads(body)
        detail = parsed.get("message") or parsed.get("name") or body
    except (json.JSONDecodeError, AttributeError):
        detail = body if "body" in locals() else ""
    detail = re.sub(
        r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        "[redacted email]",
        str(detail),
    )
    return detail[:500]


class EmailDeliveryError(RuntimeError):
    """Raised when the configured email provider cannot deliver a message."""


def send_otp_email(to_email, code, minutes=5):
    """Send an account verification code through the configured mail server."""
    subject = "Your Pansol Resorts verification code"
    text = (
        f"Your Pansol Resorts verification code is {code}. "
        f"It expires in {minutes} minutes. Do not share this code."
    )
    html = (
        "<p>Your Pansol Resorts verification code is:</p>"
        f"<p style='font-size:24px;font-weight:bold'>{code}</p>"
        f"<p>It expires in {minutes} minutes. Do not share this code.</p>"
    )
    api_key = (os.getenv("RESEND_API_KEY") or "").strip()
    if api_key:
        sender = (os.getenv("MAIL_DEFAULT_SENDER") or "").strip()
        if not sender:
            raise EmailDeliveryError(
                "Set MAIL_DEFAULT_SENDER to an address verified with the email provider."
            )
        payload = json.dumps({
            "from": sender,
            "to": [to_email],
            "subject": subject,
            "text": text,
            "html": html,
        }).encode("utf-8")
        request = Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "PansolResorts/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:
                if response.status not in (200, 201):
                    raise EmailDeliveryError(
                        f"Email provider rejected the message (HTTP {response.status})."
                    )
                response.read(64 * 1024)
        except HTTPError as error:
            detail = _provider_error_detail(error)
            suffix = f": {detail}" if detail else ""
            raise EmailDeliveryError(
                f"Email provider rejected the message (HTTP {error.code}){suffix}"
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise EmailDeliveryError("Could not reach the email provider. Please try again.") from error
        return

    if os.getenv("FLASK_DEBUG") != "1":
        raise EmailDeliveryError(
            "Email delivery is not configured. Add RESEND_API_KEY and "
            "MAIL_DEFAULT_SENDER to the hosting environment."
        )

    message = Message(
        subject=subject,
        recipients=[to_email],
        body=text,
        html=html,
    )
    from app import mail

    mail.send(message)
