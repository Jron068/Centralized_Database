import hmac
import time
from datetime import datetime, timedelta

from flask import render_template, request, redirect, session, flash, url_for
from app import app
from config import get_connection
from API.email import EmailDeliveryError, send_otp_email
import secrets

OTP_MINUTES = 5
RESEND_COOLDOWN_SECONDS = 60
MAX_ATTEMPTS = 5


@app.route("/otp")
def otp():
    email = session.get("otp_email")
    if not email:
        return redirect(url_for("registration"))

    return render_template("auth/otp.html", email=mask_email(email))


def mask_email(email):
    name, separator, domain = email.partition("@")
    if not separator or not name:
        return email
    return f"{name[:2]}***@{domain}"


@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    email = session.get("otp_email")
    otp_code = "".join(request.form.get(f"otp{i}", "") for i in range(1, 7)).strip()

    if not email:
        return redirect(url_for("registration"))

    # Stops people from guessing the code again and again
    attempts = session.get("otp_attempts", 0)
    if attempts >= MAX_ATTEMPTS:
        flash("Too many wrong attempts. Please request a new code.", "error")
        return redirect(url_for("otp"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM accounts WHERE email=%s", (email,))
        account = cursor.fetchone()

        if not account:
            flash("Account not found.", "error")
            return redirect(url_for("registration"))

        stored_code = account["verification_code"]
        expiration = account["verification_expiration"]

        if not stored_code or not expiration:
            flash("No active code. Please request a new one.", "error")
            return redirect(url_for("otp"))

        if datetime.now() > expiration:
            flash("OTP has expired. Please request a new code.", "error")
            return redirect(url_for("otp"))

        if not hmac.compare_digest(str(stored_code), otp_code):
            session["otp_attempts"] = attempts + 1
            flash("Invalid OTP.", "error")
            return redirect(url_for("otp"))

        # Correct code: mark the account as verified
        cursor.execute(
            """
            UPDATE accounts
            SET is_verified=1, verification_code=NULL, verification_expiration=NULL
            WHERE account_id=%s
            """,
            (account["account_id"],),
        )
        conn.commit()
        session.pop("otp_email", None)
        session.pop("otp_attempts", None)
        session.pop("otp_last_sent", None)

        return redirect(url_for("verification_done"))

    finally:
        cursor.close()
        conn.close()


@app.route("/resend-otp", methods=["POST"])
def resend_otp():
    email = session.get("otp_email")
    if not email:
        return redirect(url_for("registration"))

    # Make the user wait a bit between requests
    elapsed = time.time() - session.get("otp_last_sent", 0)
    if elapsed < RESEND_COOLDOWN_SECONDS:
        wait = int(RESEND_COOLDOWN_SECONDS - elapsed)
        flash(f"Please wait {wait}s before requesting a new code.", "warning")
        return redirect(url_for("otp"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT a.account_id
            FROM accounts a
            WHERE a.email = %s AND a.is_verified = 0
            """,
            (email,),
        )
        row = cursor.fetchone()
        if not row:
            flash("Account not found or already verified.", "error")
            return redirect(url_for("registration"))

        # Send the new code to the email address used during registration.
        code = f"{secrets.randbelow(1_000_000):06d}"
        try:
            send_otp_email(email, code, OTP_MINUTES)
        except Exception as error:
            app.logger.exception("Could not resend registration email OTP")
            if isinstance(error, EmailDeliveryError):
                message = "We couldn't resend the verification email. Check the email provider configuration and try again."
            else:
                message = "We couldn't resend the verification email. Please try again or contact support."
            flash(message, "error")
            return redirect(url_for("otp"))

        # 2. Save the code and when it expires
        expiration = datetime.now() + timedelta(minutes=OTP_MINUTES)
        cursor.execute(
            "UPDATE accounts SET verification_code=%s, verification_expiration=%s WHERE account_id=%s",
            (code, expiration, row["account_id"]),
        )
        conn.commit()

        session["otp_last_sent"] = time.time()
        session["otp_attempts"] = 0
        flash("A new verification code has been sent.", "success")
        return redirect(url_for("otp"))

    finally:
        cursor.close()
        conn.close()


@app.route("/send-otp", methods=["POST"])
def send_otp():
    """Keep the older verification page working with the current resend flow."""
    return resend_otp()


@app.route("/verification-done")
def verification_done():
    return render_template("auth/verified_done.html")
