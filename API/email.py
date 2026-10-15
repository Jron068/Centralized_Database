from flask_mail import Message

from app import mail


def send_otp_email(to_email, code, minutes=5):
    """Send an account verification code through the configured mail server."""
    message = Message(
        subject="Your Pansol Resorts verification code",
        recipients=[to_email],
        body=(
            f"Your Pansol Resorts verification code is {code}. "
            f"It expires in {minutes} minutes. Do not share this code."
        ),
        html=(
            "<p>Your Pansol Resorts verification code is:</p>"
            f"<p style='font-size:24px;font-weight:bold'>{code}</p>"
            f"<p>It expires in {minutes} minutes. Do not share this code.</p>"
        ),
    )
    mail.send(message)
