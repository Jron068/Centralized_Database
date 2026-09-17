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

    account_id = session.get("account_id")
    if not account_id:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT customer_id
            FROM customers
            WHERE account_id = %s
            LIMIT 1
            """,
            (account_id,),
        )
        customer = cursor.fetchone()

        if not customer:
            return render_template(
                "customer/customer_landingpage.html",
                username=session.get("fullname", "Guest"),
                total_bookings=0,
                upcoming_stays=0,
                completed_steps=0,
                pending_payment=0,
                upcoming_reservations=[],
                recent_reservations=[],
            )

        customer_id = customer["customer_id"]

        cursor.execute(
            """
            SELECT COUNT(*) AS total_bookings
            FROM reservations
            WHERE customer_id = %s
            """,
            (customer_id,),
        )
        total_bookings = cursor.fetchone()["total_bookings"] or 0

        cursor.execute(
            """
            SELECT COUNT(*) AS upcoming_stays
            FROM reservations
            WHERE customer_id = %s
              AND check_in >= CURDATE()
              AND reservation_status IN ('Pending', 'Confirmed', 'Approved')
            """,
            (customer_id,),
        )
        upcoming_stays = cursor.fetchone()["upcoming_stays"] or 0

        cursor.execute(
            """
            SELECT COUNT(*) AS completed_steps
            FROM reservations
            WHERE customer_id = %s
              AND reservation_status = 'Completed'
            """,
            (customer_id,),
        )
        completed_steps = cursor.fetchone()["completed_steps"] or 0

        cursor.execute(
            """
            SELECT COUNT(DISTINCT r.reservation_id) AS pending_payment
            FROM reservations r
            LEFT JOIN payments p ON p.reservation_id = r.reservation_id
            WHERE r.customer_id = %s
              AND (p.payment_status = 'Pending' OR p.payment_status IS NULL)
            """,
            (customer_id,),
        )
        pending_payment = cursor.fetchone()["pending_payment"] or 0

        cursor.execute(
            """
            SELECT r.reservation_id, res.resort_name, r.check_in, r.check_out,
                   r.guests, r.total_amount, r.reservation_status, r.created_at
            FROM reservations r
            JOIN resorts res ON res.resort_id = r.resort_id
            WHERE r.customer_id = %s
              AND r.check_in >= CURDATE()
              AND r.reservation_status IN ('Pending', 'Confirmed', 'Approved')
            ORDER BY r.check_in ASC
            LIMIT 3
            """,
            (customer_id,),
        )
        upcoming_reservations = cursor.fetchall()

        cursor.execute(
            """
            SELECT r.reservation_id, res.resort_name, r.reservation_status, r.created_at
            FROM reservations r
            JOIN resorts res ON res.resort_id = r.resort_id
            WHERE r.customer_id = %s
            ORDER BY r.created_at DESC
            LIMIT 5
            """,
            (customer_id,),
        )
        recent_reservations = cursor.fetchall()

        return render_template(
            "customer/customer_landingpage.html",
            username=session.get("fullname", "Guest"),
            total_bookings=total_bookings,
            upcoming_stays=upcoming_stays,
            completed_steps=completed_steps,
            pending_payment=pending_payment,
            upcoming_reservations=upcoming_reservations,
            recent_reservations=recent_reservations,
        )
    finally:
        cursor.close()
        conn.close()

# NOTE: /owner-dashboard is now registered inside admin.py (admin_dashboard())
# so that owners only see their own resorts/caretakers. Do not re-register
# it here — Flask will crash on startup with a duplicate-endpoint error.