import random
import secrets
import string
from datetime import datetime, timedelta

from flask import render_template, request, redirect, session, url_for, flash
from flask_mail import Message
from werkzeug.security import generate_password_hash

from app import app, mail
from config import get_connection

def generate_random_password(length=10):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

def send_email(to_email, subject, body_html):
    try:
        msg = Message(subject=subject, recipients=[to_email], html=body_html)
        mail.send(msg)
        return True
    except Exception as e:
        print("EMAIL ERROR:", e)
        return False

def get_owner_email_for_resort(resort_id, cursor):
    cursor.execute(
        """
        SELECT a.email, a.fullname, a.account_id
        FROM resorts r
        JOIN accounts a ON r.owner_id = a.account_id
        WHERE r.resort_id = %s
        """,
        (resort_id,)
    )
    return cursor.fetchone()

@app.route("/registration")
def registration():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT r.resort_id, r.resort_name
            FROM resorts r
            WHERE r.status = 'Active'
              AND r.resort_id NOT IN (
                  SELECT c.resort_id
                  FROM caretakers c
                  WHERE c.status IN ('Active', 'Pending')
              )
            """
        )
        resorts = cursor.fetchall()
        return render_template("auth/registration.html", resorts=resorts)
    finally:
        cursor.close()
        conn.close()

@app.route("/verification", methods=["POST"])
def verification():
    role = request.form.get("role")
    fullname = request.form.get("fullname")
    email = request.form.get("email")
    phone = request.form.get("phone")
    password = request.form.get("password")
    confirm_password = request.form.get("confirm_password")
    resort_id = request.form.get("resort_id")

    if not fullname or not email or not phone:
        flash("Please complete all required fields.", "warning")
        return redirect(url_for("registration"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT account_id FROM accounts WHERE email=%s", (email,))
        if cursor.fetchone():
            flash("Email already registered.", "warning")
            return redirect(url_for("registration"))

        if role == "customer":
            if not password or password != confirm_password:
                flash("Passwords do not match or are missing.", "warning")
                return redirect(url_for("registration"))

            hashed_password = generate_password_hash(password)
            otp = str(random.randint(100000, 999999))
            expiration = datetime.now() + timedelta(minutes=5)

            cursor.execute(
                """
                INSERT INTO accounts
                (fullname, email, password, role, account_status, is_verified, verification_code, verification_expiration)
                VALUES (%s, %s, %s, 'customer', 'Active', 0, %s, %s)
                """,
                (fullname, email, hashed_password, otp, expiration)
            )
            account_id = cursor.lastrowid

            cursor.execute(
                "INSERT INTO customers (account_id, phone, email) VALUES (%s, %s, %s)",
                (account_id, phone, email)
            )
            conn.commit()

            session["otp_email"] = email
            return redirect(url_for("otp"))

        elif role == "caretaker":
            if not resort_id:
                flash("Please select a resort.", "warning")
                return redirect(url_for("registration"))

            # Make sure the resort still exists and is still available
            cursor.execute(
                "SELECT resort_id FROM resorts WHERE resort_id = %s AND status = 'Active'",
                (resort_id,)
            )
            if not cursor.fetchone():
                flash("Selected resort is no longer available.", "warning")
                return redirect(url_for("registration"))

            cursor.execute(
                """
                SELECT caretaker_id FROM caretakers
                WHERE resort_id = %s AND status IN ('Active', 'Pending')
                """,
                (resort_id,)
            )
            if cursor.fetchone():
                flash("This resort already has an active or pending caretaker.", "warning")
                return redirect(url_for("registration"))

            placeholder_password = generate_password_hash(secrets.token_hex(16))
            cursor.execute(
                """
                INSERT INTO accounts
                (fullname, email, password, role, account_status, is_verified, approval_status)
                VALUES (%s, %s, %s, 'caretaker', 'Active', 0, 'Pending')
                """,
                (fullname, email, placeholder_password)
            )
            account_id = cursor.lastrowid

            # Status is 'Pending' until the owner/admin approves it
            cursor.execute(
                """
                INSERT INTO caretakers (account_id, resort_id, assigned_date, status)
                VALUES (%s, %s, %s, 'Pending')
                """,
                (account_id, resort_id, datetime.now())
            )
            conn.commit()

            owner = get_owner_email_for_resort(resort_id, cursor)
            cursor.execute("SELECT resort_name FROM resorts WHERE resort_id=%s", (resort_id,))
            resort_row = cursor.fetchone()
            resort_name = resort_row["resort_name"] if resort_row else "your resort"

            if owner:
                approve_link = url_for("approve_caretaker", account_id=account_id, _external=True)
                send_email(
                    to_email=owner["email"],
                    subject=f"New Caretaker Application — {resort_name}",
                    body_html=f"""
                        <p>Hi {owner['fullname']},</p>
                        <p><strong>{fullname}</strong> ({email}) applied as caretaker for <strong>{resort_name}</strong>.</p>
                        <p><a href="{approve_link}">Approve Caretaker Application</a></p>
                    """
                )

            flash("Caretaker application submitted. Awaiting owner approval.", "info")
            return redirect(url_for("login"))

        flash("Invalid role selected.", "error")
        return redirect(url_for("registration"))

    finally:
        cursor.close()
        conn.close()

@app.route("/caretaker-dashboard")
def caretaker_dashboard():
    if session.get("role") != "caretaker":
        return redirect(url_for("login"))
    return render_template("caretaker/caretaker_dashboard.html", fullname=session.get("fullname"))

@app.route("/customer-dashboard")
def customer_dashboard():
    if session.get("role") != "customer":
        return redirect(url_for("login"))
    return render_template("customer_dashboard.html", fullname=session.get("fullname"))

# NOTE: /owner-dashboard is now registered inside admin.py (admin_dashboard())
# so that owners only see their own resorts/caretakers. Do not re-register
# it here — Flask will crash on startup with a duplicate-endpoint error.