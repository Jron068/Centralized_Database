from flask import render_template, request, redirect, session, url_for, flash
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import random
import string
import secrets

from app import app, mail
from flask_mail import Message
from config import get_connection


# ----------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------

def generate_random_password(length=10):
    """Generate a secure random password for approved caretakers."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def send_email(to_email, subject, body_html):
    """Generic email sender using Flask-Mail."""
    try:
        msg = Message(
            subject=subject,
            recipients=[to_email],
            html=body_html
        )
        mail.send(msg)
        return True
    except Exception as e:
        print("EMAIL ERROR:", e)
        return False


def get_owner_email_for_resort(resort_id, cursor):
    """
    Fetch the owner account email tied to a resort.
    Assumes resorts table has an owner_id column referencing accounts.
    """
    cursor.execute("""
        SELECT a.email, a.fullname, a.account_id
        FROM resorts r
        JOIN accounts a ON r.owner_id = a.account_id
        WHERE r.resort_id = %s
    """, (resort_id,))
    return cursor.fetchone()


# ----------------------------------------------------------------------
# REGISTRATION PAGE
# ----------------------------------------------------------------------

@app.route("/registration")
def registration():

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    # Only show resorts that are Active AND don't already have an
    # approved/active caretaker assigned (one resort = one caretaker)
    cursor.execute("""
        SELECT r.resort_id, r.resort_name
        FROM resorts r
        WHERE r.status = 'Active'
          AND r.resort_id NOT IN (
              SELECT c.resort_id
              FROM caretakers c
              WHERE c.status IN ('Active', 'Pending')
          )
    """)

    resorts = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "registration.html",
        resorts=resorts
    )


# ----------------------------------------------------------------------
# REGISTRATION SUBMISSION
# ----------------------------------------------------------------------

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
        return "Please complete all fields."

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT account_id
        FROM accounts
        WHERE email=%s
    """, (email,))

    existing = cursor.fetchone()

    if existing:
        cursor.close()
        connection.close()
        return "Email already registered."

    # ------------------------------------------------------------
    # CUSTOMER REGISTRATION (unchanged flow)
    # ------------------------------------------------------------
    if role == "customer":

        if password != confirm_password:
            cursor.close()
            connection.close()
            return "Password does not match."

        if not password:
            cursor.close()
            connection.close()
            return "Please complete all fields."

        hashed_password = generate_password_hash(password)

        otp = str(random.randint(100000, 999999))
        expiration = datetime.now() + timedelta(minutes=5)

        cursor.execute("""
            INSERT INTO accounts
            (
                fullname,
                email,
                password,
                role,
                account_status,
                is_verified,
                verification_code,
                verification_expiration
            )

            VALUES
            (
                %s,%s,%s,
                'customer',
                'Active',
                0,
                %s,
                %s
            )
        """,
        (
            fullname,
            email,
            hashed_password,
            otp,
            expiration
        ))

        account_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO customers
            (
                account_id,
                phone,
                email
            )

            VALUES
            (
                %s,%s,%s
            )
        """,
        (
            account_id,
            phone,
            email
        ))

        connection.commit()

        session["otp_email"] = email

        print("================")
        print("OTP:", otp)
        print("================")

        cursor.close()
        connection.close()

        return redirect("/otp")

    # ------------------------------------------------------------
    # CARETAKER REGISTRATION
    # No password is set by the caretaker. Account is created in a
    # Pending state, and the resort owner is notified to approve it.
    # ------------------------------------------------------------
    elif role == "caretaker":

        if not resort_id:
            cursor.close()
            connection.close()
            return "Please select a resort."

        # Enforce one resort = one caretaker (Pending or Active blocks it)
        cursor.execute("""
            SELECT caretaker_id
            FROM caretakers
            WHERE resort_id = %s
              AND status IN ('Active', 'Pending')
        """, (resort_id,))

        if cursor.fetchone():
            cursor.close()
            connection.close()
            return "This resort already has a caretaker assigned or pending approval."

        # No usable password yet — placeholder hash until owner approves.
        # A caretaker can never log in with this since the real password
        # is generated and overwritten upon approval.
        placeholder_password = generate_password_hash(secrets.token_hex(16))

        cursor.execute("""
            INSERT INTO accounts
            (
                fullname,
                email,
                password,
                role,
                account_status,
                is_verified,
                approval_status
            )

            VALUES
            (
                %s,%s,%s,
                'caretaker',
                'Active',
                0,
                'Pending'
            )
        """,
        (
            fullname,
            email,
            placeholder_password
        ))

        account_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO caretakers
            (
                account_id,
                resort_id,
                assigned_date,
                status
            )

            VALUES
            (
                %s,%s,%s,%s
            )
        """,
        (
            account_id,
            resort_id,
            datetime.now(),
            'Pending'
        ))

        connection.commit()

        # ---- Notify the resort owner that a caretaker is awaiting approval ----
        owner = get_owner_email_for_resort(resort_id, cursor)

        cursor.execute("SELECT resort_name FROM resorts WHERE resort_id=%s", (resort_id,))
        resort_row = cursor.fetchone()
        resort_name = resort_row["resort_name"] if resort_row else "your resort"

        if owner:
            approve_link = url_for(
                "approve_caretaker",
                account_id=account_id,
                _external=True
            )

            send_email(
                to_email=owner["email"],
                subject=f"New Caretaker Application — {resort_name}",
                body_html=f"""
                    <p>Hi {owner['fullname']},</p>
                    <p><strong>{fullname}</strong> ({email}) has applied to be the
                    caretaker for <strong>{resort_name}</strong>.</p>
                    <p>Please review and approve this application:</p>
                    <p><a href="{approve_link}">Approve Caretaker</a></p>
                """
            )

        cursor.close()
        connection.close()

        return "Your caretaker application has been submitted. Please wait for the owner's approval."

    cursor.close()
    connection.close()

    return "Invalid registration role."


# ----------------------------------------------------------------------
# OWNER APPROVES A CARETAKER
# Generates the random password, saves it (hashed), and emails the
# caretaker their login credentials.
# ----------------------------------------------------------------------

@app.route("/approve-caretaker/<int:account_id>", methods=["GET"])
def approve_caretaker(account_id):

    # In production, wrap this route with an owner-auth check
    # (e.g. @login_required + verify session["role"] == "owner"
    # and that the resort belongs to this owner).
    if session.get("role") != "owner":
        return "Unauthorized. Please log in as the resort owner."

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT a.account_id, a.email, a.fullname, a.approval_status,
               c.resort_id, c.status AS caretaker_status
        FROM accounts a
        JOIN caretakers c ON a.account_id = c.account_id
        WHERE a.account_id = %s AND a.role = 'caretaker'
    """, (account_id,))

    caretaker = cursor.fetchone()

    if not caretaker:
        cursor.close()
        connection.close()
        return "Caretaker not found."

    if caretaker["approval_status"] == "Approved":
        cursor.close()
        connection.close()
        return "This caretaker has already been approved."

    cursor.execute("SELECT resort_name FROM resorts WHERE resort_id=%s",
                    (caretaker["resort_id"],))
    resort_row = cursor.fetchone()
    resort_name = resort_row["resort_name"] if resort_row else "your assigned resort"

    # ---- Generate the caretaker's login password ----
    generated_password = generate_random_password(10)
    hashed_password = generate_password_hash(generated_password)

    cursor.execute("""
        UPDATE accounts
        SET password = %s,
            is_verified = 1,
            approval_status = 'Approved'
        WHERE account_id = %s
    """, (hashed_password, account_id))

    cursor.execute("""
        UPDATE caretakers
        SET status = 'Active'
        WHERE account_id = %s
    """, (account_id,))

    connection.commit()

    # ---- Notify caretaker with their login credentials ----
    login_link = url_for("login", _external=True)

    send_email(
        to_email=caretaker["email"],
        subject=f"You're Approved — {resort_name}",
        body_html=f"""
            <p>Hi {caretaker['fullname']},</p>
            <p>Your application to be the caretaker of
            <strong>{resort_name}</strong> has been approved.</p>
            <p>Here are your login credentials:</p>
            <ul>
                <li>Email: {caretaker['email']}</li>
                <li>Temporary Password: <strong>{generated_password}</strong></li>
            </ul>
            <p>Please log in and change your password as soon as possible:</p>
            <p><a href="{login_link}">Log In</a></p>
        """
    )

    cursor.close()
    connection.close()

    return f"Caretaker {caretaker['fullname']} has been approved and notified."


# ----------------------------------------------------------------------
# LOGIN
# Works for all roles. Caretakers can only log in once approval_status
# is 'Approved' — otherwise they're told to wait.
# ----------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email")
    password = request.form.get("password")

    if not email or not password:
        return "Please complete all fields."

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT account_id, fullname, email, password, role,
               account_status, is_verified, approval_status
        FROM accounts
        WHERE email = %s
    """, (email,))

    account = cursor.fetchone()

    if not account or not check_password_hash(account["password"], password):
        cursor.close()
        connection.close()
        return "Invalid email or password."

    if account["account_status"] != "Active":
        cursor.close()
        connection.close()
        return "Your account is not active."

    if account["role"] == "caretaker":
        if account["approval_status"] != "Approved":
            cursor.close()
            connection.close()
            return "Your account is still pending owner approval."

        cursor.execute("""
            SELECT resort_id FROM caretakers WHERE account_id = %s
        """, (account["account_id"],))
        caretaker_row = cursor.fetchone()

        session["account_id"] = account["account_id"]
        session["role"] = "caretaker"
        session["fullname"] = account["fullname"]
        session["resort_id"] = caretaker_row["resort_id"] if caretaker_row else None

        cursor.close()
        connection.close()

        return redirect(url_for("caretaker"))

    elif account["role"] == "customer":
        if not account["is_verified"]:
            cursor.close()
            connection.close()
            return "Please verify your account first."

        session["account_id"] = account["account_id"]
        session["role"] = "customer"
        session["fullname"] = account["fullname"]

        cursor.close()
        connection.close()

        return redirect(url_for("customer_landingpage"))

    elif account["role"] == "owner":
        session["account_id"] = account["account_id"]
        session["role"] = "owner"
        session["fullname"] = account["fullname"]

        cursor.close()
        connection.close()

        return redirect(url_for("owner_dashboard"))

    cursor.close()
    connection.close()

    return "Unrecognized role."


# ----------------------------------------------------------------------
# DASHBOARD ROUTES (stubs — wire to your actual templates)
# ----------------------------------------------------------------------

@app.route("/caretaker-dashboard")
def caretaker_dashboard():
    if session.get("role") != "caretaker":
        return redirect(url_for("login"))
    return render_template("caretaker_dashboard.html", fullname=session.get("fullname"))


@app.route("/customer-dashboard")
def customer_dashboard():
    if session.get("role") != "customer":
        return redirect(url_for("login"))
    return render_template("customer_dashboard.html", fullname=session.get("fullname"))


@app.route("/owner-dashboard")
def owner_dashboard():
    if session.get("role") != "owner":
        return redirect(url_for("login"))
    return render_template("owner_dashboard.html", fullname=session.get("fullname"))