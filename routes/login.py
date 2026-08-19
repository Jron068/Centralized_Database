from flask import render_template, request, redirect, session, flash, url_for
from werkzeug.security import check_password_hash
from app import app
from config import get_connection

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("auth/login.html")

    email = request.form.get("email")
    password = request.form.get("password")
    selected_role = request.form.get("role")

    if not email or not password:
        flash("Please complete all fields.", "warning")
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT account_id, fullname, email, password, role,
                   account_status, is_verified, approval_status
            FROM accounts
            WHERE email = %s
            """,
            (email,)
        )
        account = cursor.fetchone()

        if not account or not check_password_hash(account["password"], password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))

        if selected_role and account["role"] != selected_role:
            flash("Role mismatched. Please input your correct account type.", "warning")
            return redirect(url_for("login"))

        if account["account_status"] != "Active":
            flash("Your account is not active.", "error")
            return redirect(url_for("login"))

        if account["role"] == "caretaker":
            if account["approval_status"] != "Approved":
                flash("Your account is still pending owner approval.", "warning")
                return redirect(url_for("login"))

            cursor.execute(
                "SELECT resort_id FROM caretakers WHERE account_id = %s",
                (account["account_id"],)
            )
            caretaker_row = cursor.fetchone()
            session["resort_id"] = caretaker_row["resort_id"] if caretaker_row else None

        elif account["role"] == "customer":
            if not account["is_verified"]:
                flash("Please verify your account first.", "warning")
                return redirect(url_for("login"))

        elif account["role"] == "owner":
            # Look up this owner's owner_id so the dashboard can filter
            # resorts/caretakers to only what this owner manages.
            cursor.execute(
                "SELECT owner_id FROM owners WHERE account_id = %s",
                (account["account_id"],)
            )
            owner_row = cursor.fetchone()

            if not owner_row:
                flash("No owner profile linked to this account.", "error")
                return redirect(url_for("login"))

            session["owner_id"] = owner_row["owner_id"]

        session["user_id"] = account["account_id"]
        session["account_id"] = account["account_id"]
        session["fullname"] = account["fullname"]
        session["role"] = account["role"]

        if account["role"] == "customer":
            return redirect(url_for("customer_landingpage"))
        elif account["role"] == "caretaker":
            return redirect(url_for("caretaker_dashboard"))
        elif account["role"] == "owner":
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Unknown account role.", "error")
            return redirect(url_for("login"))

    finally:
        cursor.close()
        conn.close()