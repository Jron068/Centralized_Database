from flask import render_template, request, redirect, session, flash, url_for
from werkzeug.security import check_password_hash
from app import app
from config import get_connection

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("auth/login.html")

    email = (request.form.get("email") or "").strip()
    password = request.form.get("password")

    if not email or not password:
        flash("Please complete all fields.", "warning")
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Only account-level fields here — no "role" column needed anymore.
        cursor.execute(
            """
            SELECT account_id, fullname, email, password,
                   account_status, is_verified, approval_status
            FROM accounts
            WHERE email = %s
            """,
            (email,)
        )
        account = cursor.fetchone()

        if not account:
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))

        if not check_password_hash(account["password"], password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))

        if account["account_status"] != "Active":
            flash("Your account is not active.", "error")
            return redirect(url_for("login"))

        account_id = account["account_id"]

        # ------------------------------------------------------------
        # Determine the role by checking which table this account_id
        # actually belongs to, instead of trusting a stored role string.
        # Check owners (admin) first, then caretakers, then customers.
        # ------------------------------------------------------------
        cursor.execute(
            "SELECT owner_id FROM owners WHERE account_id = %s",
            (account_id,)
        )
        owner_row = cursor.fetchone()

        cursor.execute(
            "SELECT resort_id, status FROM caretakers WHERE account_id = %s",
            (account_id,)
        )
        caretaker_row = cursor.fetchone()

        cursor.execute(
            "SELECT customer_id FROM customers WHERE account_id = %s",
            (account_id,)
        )
        customer_row = cursor.fetchone()

        role = None

        if owner_row:
            role = "owner"
        elif caretaker_row:
            role = "caretaker"
        elif customer_row:
            role = "customer"

        if role is None:
            flash("No role found for this account.", "error")
            return redirect(url_for("login"))

        # ------------------------------------------------------------
        # Role-specific validation (same checks you had before)
        # ------------------------------------------------------------
        if role == "caretaker":
            if account["approval_status"] != "Approved":
                flash("Your account is still pending owner approval.", "warning")
                return redirect(url_for("login"))

            if caretaker_row["status"] != "Active":
                flash("Your caretaker assignment is not active.", "warning")
                return redirect(url_for("login"))

            session["resort_id"] = caretaker_row["resort_id"]

        elif role == "customer":
            if not account["is_verified"]:
                flash("Please verify your account first.", "warning")
                return redirect(url_for("login"))

            session["customer_id"] = customer_row["customer_id"]

        elif role == "owner":
            session["owner_id"] = owner_row["owner_id"]

        # ------------------------------------------------------------
        # Common session data
        # ------------------------------------------------------------
        session["user_id"] = account_id
        session["account_id"] = account_id
        session["fullname"] = account["fullname"]
        session["role"] = role

        if role == "customer":
            return redirect(url_for("customer_aboutpage"))
        elif role == "caretaker":
            return redirect(url_for("caretaker_dashboard"))
        elif role == "owner":
            return redirect(url_for("admin_dashboard"))

    finally:
        cursor.close()
        conn.close()