import secrets
import string
from flask import redirect, flash, session, url_for
from werkzeug.security import generate_password_hash

from app import app, mail
from config import get_connection
from flask_mail import Message
from models.decorators import role_required

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

@app.route("/approve-caretaker/<int:account_id>")
@role_required("owner")
def approve_caretaker(account_id):
    owner_id = session.get("owner_id")
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT a.account_id, a.fullname, a.email, a.approval_status,
                   c.resort_id, r.resort_name, r.owner_id
            FROM accounts a
            JOIN caretakers c ON c.account_id = a.account_id
            JOIN resorts r ON r.resort_id = c.resort_id
            WHERE a.account_id = %s AND a.role = 'caretaker'
            """,
            (account_id,)
        )
        caretaker = cursor.fetchone()

        if not caretaker:
            flash("Caretaker account not found.", "danger")
            return redirect(url_for("admin_dashboard"))

        # Prevent one owner from approving a caretaker for another owner's resort
        if caretaker["owner_id"] != owner_id:
            flash("You are not authorized to approve this application.", "danger")
            return redirect(url_for("admin_dashboard"))

        if caretaker["approval_status"] == "Approved":
            flash("Caretaker is already approved.", "warning")
            return redirect(url_for("admin_dashboard"))

        raw_password = generate_random_password()
        hashed_password = generate_password_hash(raw_password)

        cursor.execute(
            """
            UPDATE accounts
            SET password = %s, approval_status = 'Approved', is_verified = 1,
                approved_by = %s, approved_at = NOW()
            WHERE account_id = %s
            """,
            (hashed_password, session.get("user_id"), account_id)
        )

        cursor.execute(
            "UPDATE caretakers SET status = 'Active' WHERE account_id = %s",
            (account_id,)
        )
        conn.commit()

        login_link = url_for("login", _external=True)
        send_email(
            to_email=caretaker["email"],
            subject=f"You're Approved — {caretaker['resort_name']}",
            body_html=f"""
                <p>Hi {caretaker['fullname']},</p>
                <p>Your caretaker account for <strong>{caretaker['resort_name']}</strong> has been approved.</p>
                <ul>
                    <li>Email: {caretaker['email']}</li>
                    <li>Temporary Password: <strong>{raw_password}</strong></li>
                </ul>
                <p><a href="{login_link}">Log In Here</a></p>
            """
        )

        flash(f"{caretaker['fullname']} approved. Login credentials sent via email.", "success")

    except Exception as e:
        conn.rollback()
        print("APPROVE ERROR:", e)
        flash("Error approving caretaker.", "danger")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("admin_dashboard"))

@app.route("/reject-caretaker/<int:account_id>")
@role_required("owner")
def reject_caretaker(account_id):
    owner_id = session.get("owner_id")
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT a.fullname, r.owner_id
            FROM accounts a
            JOIN caretakers c ON c.account_id = a.account_id
            JOIN resorts r ON r.resort_id = c.resort_id
            WHERE a.account_id = %s
            """,
            (account_id,)
        )
        caretaker = cursor.fetchone()

        if not caretaker:
            flash("Caretaker account not found.", "danger")
            return redirect(url_for("admin_dashboard"))

        if caretaker["owner_id"] != owner_id:
            flash("You are not authorized to reject this application.", "danger")
            return redirect(url_for("admin_dashboard"))

        cursor.execute(
            """
            UPDATE accounts
            SET approval_status='Rejected', approved_by=%s, approved_at=NOW()
            WHERE account_id=%s
            """,
            (session.get("user_id"), account_id)
        )

        # Free up the resort so it reappears in the registration dropdown
        cursor.execute(
            "UPDATE caretakers SET status='Inactive' WHERE account_id=%s",
            (account_id,)
        )
        conn.commit()

        flash(f"{caretaker['fullname']} application rejected.", "warning")

    except Exception as e:
        conn.rollback()
        print("REJECT ERROR:", e)
        flash("Error rejecting caretaker.", "danger")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("admin_dashboard"))