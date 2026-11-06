import hashlib
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from flask import render_template, request, redirect, session, flash, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from app import app
from config import get_connection
from API.email import send_email
from models.account_profile import ensure_account_profiles_table
from models.file_storage import file_url
from models.password_reset import ensure_password_resets_table


def _safe_next_url(value):
    """Accept only same-site relative paths for post-login redirects."""
    if not isinstance(value, str) or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return None
    return value


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = _safe_next_url(request.values.get("next"))
    if request.method == "GET":
        return render_template("auth/login.html", next_url=next_url or "")

    email = (request.form.get("email") or "").strip()
    password = request.form.get("password")

    if not email or not password:
        flash("Please complete all fields.", "warning")
        return redirect(url_for("login", next=next_url) if next_url else url_for("login"))

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
            return redirect(url_for("login", next=next_url) if next_url else url_for("login"))

        if not check_password_hash(account["password"], password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("login", next=next_url) if next_url else url_for("login"))

        if account["account_status"] != "Active":
            flash("Your account is not active.", "error")
            return redirect(url_for("login", next=next_url) if next_url else url_for("login"))

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
            return redirect(url_for("login", next=next_url) if next_url else url_for("login"))

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
        ensure_account_profiles_table(cursor)
        cursor.execute(
            "SELECT profile_photo_path FROM account_profiles WHERE account_id = %s",
            (account_id,),
        )
        profile = cursor.fetchone()
        if profile and profile.get("profile_photo_path"):
            session["profile_photo"] = file_url(profile["profile_photo_path"])
        else:
            session.pop("profile_photo", None)

        if role == "customer":
            if next_url and next_url.startswith("/resorts"):
                return redirect(next_url)
            return redirect(url_for("customer_aboutpage"))
        elif role == "caretaker":
            return redirect(url_for("caretaker_dashboard"))
        elif role == "owner":
            return redirect(url_for("admin_dashboard"))

    finally:
        cursor.close()
        conn.close()


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("auth/forgot_password.html")

    email = (request.form.get("email") or "").strip().lower()
    if not email:
        flash("Enter the email address associated with your account.", "warning")
        return redirect(url_for("forgot_password"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        ensure_password_resets_table(cursor)
        cursor.execute(
            "SELECT account_id FROM accounts WHERE LOWER(email) = %s AND account_status = 'Active'",
            (email,),
        )
        account = cursor.fetchone()
        if account:
            cursor.execute(
                "SELECT created_at FROM password_resets WHERE account_id = %s",
                (account["account_id"],),
            )
            previous_reset = cursor.fetchone()
            can_send = not previous_reset or (
                datetime.now() - previous_reset["created_at"]
            ).total_seconds() >= 60
            if can_send:
                token = secrets.token_urlsafe(32)
                reset_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
                expires_at = datetime.now() + timedelta(minutes=30)
                cursor.execute("DELETE FROM password_resets WHERE account_id = %s", (account["account_id"],))
                cursor.execute(
                    "INSERT INTO password_resets (account_id, token_hash, expires_at) VALUES (%s, %s, %s)",
                    (account["account_id"], reset_hash, expires_at),
                )
                conn.commit()
                reset_url = url_for("reset_password", token=token, _external=True)
                try:
                    send_email(
                        email,
                        "Reset your Pansol Resorts password",
                        f"Use this link within 30 minutes to reset your password: {reset_url}",
                        f"<p>Use the link below within 30 minutes to reset your password.</p>"
                        f"<p><a href=\"{reset_url}\">Reset my password</a></p>"
                        "<p>If you did not request this, you can ignore this email.</p>",
                    )
                except Exception:
                    cursor.execute("DELETE FROM password_resets WHERE account_id = %s", (account["account_id"],))
                    conn.commit()
                    app.logger.exception("Password reset email could not be delivered")

        flash(
            "If an active account uses that email, a password reset link will be sent shortly.",
            "success",
        )
        return redirect(url_for("login"))
    except Exception:
        conn.rollback()
        app.logger.exception("Password reset request could not be processed")
        flash("We couldn't process your request right now. Please try again.", "error")
        return redirect(url_for("forgot_password"))
    finally:
        cursor.close()
        conn.close()


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        ensure_password_resets_table(cursor)
        cursor.execute(
            "SELECT account_id FROM password_resets WHERE token_hash = %s AND expires_at > %s",
            (token_hash, datetime.now()),
        )
        reset = cursor.fetchone()
        if not reset:
            flash("This password reset link is invalid or has expired. Request a new one.", "warning")
            return redirect(url_for("forgot_password"))

        if request.method == "GET":
            return render_template("auth/reset_password.html", token=token)

        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "warning")
            return render_template("auth/reset_password.html", token=token)
        if password != confirm_password:
            flash("Passwords do not match.", "warning")
            return render_template("auth/reset_password.html", token=token)

        cursor.execute(
            "UPDATE accounts SET password = %s WHERE account_id = %s",
            (generate_password_hash(password), reset["account_id"]),
        )
        cursor.execute("DELETE FROM password_resets WHERE account_id = %s", (reset["account_id"],))
        conn.commit()
        flash("Your password has been updated. You can now sign in.", "success")
        return redirect(url_for("login"))
    except Exception:
        conn.rollback()
        app.logger.exception("Password reset could not be completed")
        flash("We couldn't reset your password right now. Please request a new link.", "error")
        return redirect(url_for("forgot_password"))
    finally:
        cursor.close()
        conn.close()
