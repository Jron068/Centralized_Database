from flask import render_template, request, redirect, session, flash
from werkzeug.security import check_password_hash
from app import app
from config import get_connection

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role")

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Check if the email exists
        cursor.execute(
            "SELECT * FROM accounts WHERE email=%s",
            (email,)
        )

        account = cursor.fetchone()

        if account is None:
            cursor.close()
            conn.close()
            flash("No Account Registered.", "error")
            return redirect("/login")

        # Check if the selected role matches the account role
        if account["role"] != role:
            cursor.close()
            conn.close()
            flash("Please input your correct account.", "warning")
            return redirect("/login")

        # Check the password
        if not check_password_hash(account["password"], password):
            cursor.close()
            conn.close()
            flash("Please input your correct account.", "warning")
            return redirect("/login")

        cursor.close()
        conn.close()

        # Save session
        session["user_id"] = account["account_id"]
        session["fullname"] = account["fullname"]
        session["role"] = account["role"]

        # Redirect based on role
        if account["role"] == "customer":
            return redirect("/customer_landingpage")

        elif account["role"] == "caretaker":
            return redirect("/caretaker_dashboard")

        elif account["role"] == "owner":
            return redirect("/owner_dashboard")

        else:
            flash("Unknown account role.")
            return redirect("/login")

    return render_template("login.html")