from datetime import datetime
from flask import render_template, request, redirect, session, flash, url_for
from app import app
from config import get_connection

@app.route("/otp")
def otp():
    return render_template("auth/otp.html")

@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    email = session.get("otp_email")
    otp_code = "".join(request.form.get(f"otp{i}", "") for i in range(1, 7)).strip()

    if not email:
        return redirect(url_for("registration"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM accounts WHERE email=%s", (email,))
        account = cursor.fetchone()

        if not account:
            flash("Account not found.", "error")
            return redirect(url_for("registration"))

        if account["verification_code"] != otp_code:
            flash("Invalid OTP.", "error")
            return redirect(url_for("otp"))

        if datetime.now() > account["verification_expiration"]:
            flash("OTP has expired.", "error")
            return redirect(url_for("otp"))

        cursor.execute(
            """
            UPDATE accounts
            SET is_verified=1, verification_code=NULL, verification_expiration=NULL
            WHERE account_id=%s
            """,
            (account["account_id"],)
        )
        conn.commit()
        session.pop("otp_email", None)

        return redirect(url_for("verification_done"))

    finally:
        cursor.close()
        conn.close()

@app.route("/verification-done")
def verification_done():
    return render_template("auth/verified_done.html")