from flask import render_template, request, redirect, session
from datetime import datetime

from app import app
from config import get_connection


@app.route("/otp")
def otp():
    return render_template("otp.html")


@app.route("/verify-otp", methods=["POST"])
def verify_otp():

    email = session.get("otp_email")

    otp = (
        request.form.get("otp1","") +
        request.form.get("otp2","") +
        request.form.get("otp3","") +
        request.form.get("otp4","") +
        request.form.get("otp5","") +
        request.form.get("otp6","")
    ).strip()

    if not email:
        return redirect("/registration")

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM accounts
        WHERE email=%s
    """, (email,))

    account = cursor.fetchone()

    if account is None:
        cursor.close()
        connection.close()
        return "Account not found."

    if account["verification_code"] != otp:
        cursor.close()
        connection.close()
        return "Invalid OTP."

    if datetime.now() > account["verification_expiration"]:
        cursor.close()
        connection.close()
        return "OTP expired."

    cursor.execute("""
        UPDATE accounts
        SET
            is_verified=1,
            verification_code=NULL,
            verification_expiration=NULL
        WHERE account_id=%s
    """, (account["account_id"],))

    connection.commit()

    cursor.close()
    connection.close()

    session.pop("otp_email", None)

    return redirect("/verification-done")


@app.route("/verification-done")
def verification_done():
    return render_template("verified_done.html")