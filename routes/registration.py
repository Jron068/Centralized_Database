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
        JOIN owners o ON r.owner_id = o.owner_id
        JOIN accounts a ON o.account_id = a.account_id
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
            SELECT o.owner_id
            FROM owners o
            JOIN accounts a ON a.account_id = o.account_id
            WHERE a.role = 'owner' AND a.account_status = 'Active'
            ORDER BY o.owner_id
            LIMIT 1
            """
        )
        admin_owner = cursor.fetchone()
        registration_owner_id = session.get("owner_id") or (
            admin_owner["owner_id"] if admin_owner else None
        )

        owner_filter = " AND r.owner_id = %s" if registration_owner_id else ""
        query_params = (registration_owner_id,) if registration_owner_id else ()
        cursor.execute(
            f"""
                             SELECT r.resort_id, r.resort_name,
                                 EXISTS (
                                  SELECT 1
                                  FROM caretakers c
                                  WHERE c.resort_id = r.resort_id
                                    AND c.status IN ('Active', 'Pending')
                                 ) AS has_caretaker
            FROM resorts r
                        JOIN owners o ON o.owner_id = r.owner_id
                        JOIN accounts owner_account ON owner_account.account_id = o.account_id
                        WHERE r.status = 'Active'
                            AND owner_account.role = 'owner'
                            AND owner_account.account_status = 'Active'
              {owner_filter}
                        ORDER BY r.resort_name
                        """,
                        query_params,
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
            if not password or password != confirm_password:
                flash("Passwords do not match or are missing.", "warning")
                return redirect(url_for("registration"))

            if not resort_id:
                flash("Please select a resort.", "warning")
                return redirect(url_for("registration"))

            # Make sure the resort still exists and is still available
            registration_owner_id = session.get("owner_id")
            if not registration_owner_id:
                cursor.execute(
                    """
                    SELECT o.owner_id
                    FROM owners o
                    JOIN accounts a ON a.account_id = o.account_id
                    WHERE a.role = 'owner' AND a.account_status = 'Active'
                    ORDER BY o.owner_id
                    LIMIT 1
                    """
                )
                admin_owner = cursor.fetchone()
                registration_owner_id = admin_owner["owner_id"] if admin_owner else None

            cursor.execute(
                                """
                                SELECT r.resort_id
                                FROM resorts r
                                JOIN owners o ON o.owner_id = r.owner_id
                                JOIN accounts owner_account ON owner_account.account_id = o.account_id
                                WHERE r.resort_id = %s
                                    AND r.status = 'Active'
                                    AND owner_account.role = 'owner'
                                    AND owner_account.account_status = 'Active'
                                    AND r.owner_id = %s
                                """,
                                (resort_id, registration_owner_id)
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

            hashed_password = generate_password_hash(password)
            cursor.execute(
                """
                INSERT INTO accounts
                (fullname, email, password, role, account_status, is_verified, approval_status)
                VALUES (%s, %s, %s, 'caretaker', 'Active', 0, 'Pending')
                """,
                (fullname, email, hashed_password)
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

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT r.resort_id, r.resort_name, r.address, r.description,
                   r.logo, r.status
            FROM resorts r
            JOIN caretakers c ON c.resort_id = r.resort_id
            WHERE c.account_id = %s AND c.status = 'Active'
            """,
            (session.get("account_id"),),
        )
        resort = cursor.fetchone()
        if not resort:
            session.clear()
            flash("Your caretaker assignment is no longer active.", "warning")
            return redirect(url_for("login"))

        cursor.execute(
            """
                 SELECT r.reservation_id, r.guest_name, r.check_in, r.check_out,
                     r.guests, r.total_amount, r.reservation_status,
                     COALESCE(p.payment_status, 'No payment') AS payment_status,
                     p.proof_of_payment, p.amount_paid, p.payment_date
            FROM reservations r
                 LEFT JOIN payments p ON p.payment_id = (
                  SELECT p2.payment_id
                  FROM payments p2
                  WHERE p2.reservation_id = r.reservation_id
                  ORDER BY p2.payment_id DESC
                  LIMIT 1
                 )
            WHERE r.resort_id = %s
              AND r.check_out >= CURDATE()
              AND r.reservation_status IN ('Pending', 'Confirmed')
            ORDER BY r.check_in ASC
            LIMIT 10
            """,
            (resort["resort_id"],),
        )
        reservations = cursor.fetchall()

        cursor.execute(
            """
            SELECT title, message, created_at, is_read
            FROM notifications
            WHERE account_id = %s
            ORDER BY created_at DESC
            LIMIT 5
            """,
            (session.get("account_id"),),
        )
        notifications = cursor.fetchall()

        return render_template(
            "caretaker/caretaker_dashboard.html",
            fullname=session.get("fullname"),
            resort=resort,
            reservations=reservations,
            notifications=notifications,
        )
    finally:
        cursor.close()
        conn.close()

@app.route("/customer-dashboard")
def customer_dashboard():
    if session.get("role") != "customer":
        return redirect(url_for("login"))
    return render_template(
        "customer/customer_landingpage.html",
        username=session.get("fullname", "Guest"),
    )

# NOTE: /owner-dashboard is now registered inside admin.py (admin_dashboard())
# so that owners only see their own resorts/caretakers. Do not re-register
# it here — Flask will crash on startup with a duplicate-endpoint error.