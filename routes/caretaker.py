from flask import redirect, flash, session, url_for, render_template
from flask import request
from werkzeug.security import generate_password_hash

from app import app, mail
from config import get_connection
from flask_mail import Message
from models.decorators import role_required

def caretaker_page(template_name):
    if session.get("role") != "caretaker":
        return redirect(url_for("login"))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT r.resort_id, r.resort_name, r.address, r.status
            FROM resorts r
            JOIN caretakers c ON c.resort_id = r.resort_id
            WHERE c.account_id = %s AND c.status = 'Active'
            """,
            (session.get("account_id"),),
        )
        resort = cursor.fetchone()
        if not resort:
            return redirect(url_for("login"))
        return render_template(
            template_name,
            fullname=session.get("fullname", "Caretaker"),
            resort=resort,
        )
    finally:
        cursor.close()
        conn.close()

@app.route("/caretaker/updates")
@role_required("caretaker")
def caretaker_updates():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT r.resort_name
            FROM resorts r
            JOIN caretakers c ON c.resort_id = r.resort_id
            WHERE c.account_id = %s AND c.status = 'Active'
            """,
            (session.get("account_id"),),
        )
        resort = cursor.fetchone()
        if not resort:
            return redirect(url_for("login"))

        cursor.execute(
            """
            SELECT title, message, type, created_at
            FROM notifications
            WHERE account_id = %s
            ORDER BY created_at DESC
            """,
            (session.get("account_id"),),
        )
        updates = cursor.fetchall()
        return render_template(
            "caretaker/caretaker_updates.html",
            fullname=session.get("fullname", "Caretaker"),
            resort=resort,
            updates=updates,
        )
    finally:
        cursor.close()
        conn.close()

@app.route("/caretaker/guests")
@role_required("caretaker")
def caretaker_guests():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT r.reservation_id, r.guest_name, r.check_in, r.check_out,
                   r.guests, r.reservation_status
            FROM reservations r
            JOIN caretakers c ON c.resort_id = r.resort_id
            WHERE c.account_id = %s AND c.status = 'Active'
            ORDER BY r.check_in DESC
            """,
            (session.get("account_id"),),
        )
        guests = cursor.fetchall()
        return render_template(
            "caretaker/caretaker_guests.html",
            fullname=session.get("fullname", "Caretaker"),
            guests=guests,
        )
    finally:
        cursor.close()
        conn.close()

@app.route("/caretaker/inventory")
@role_required("caretaker")
def caretaker_inventory():
    return caretaker_page("caretaker/caretaker_inventory.html")

@app.route("/caretaker/maintenance")
@role_required("caretaker")
def caretaker_maintenance():
    return caretaker_page("caretaker/caretaker_maintenance.html")

@app.route("/caretaker/messages")
@role_required("caretaker")
def caretaker_messages():
    return caretaker_page("caretaker/caretaker_messages.html")

@app.route("/caretaker/notifications")
@role_required("caretaker")
def caretaker_notifications():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT title, message, type, is_read, created_at
            FROM notifications
            WHERE account_id = %s
            ORDER BY created_at DESC
            LIMIT 30
            """,
            (session.get("account_id"),),
        )
        notifications = cursor.fetchall()
        return render_template(
            "caretaker/caretaker_notifications.html",
            fullname=session.get("fullname", "Caretaker"),
            notifications=notifications,
        )
    finally:
        cursor.close()
        conn.close()

@app.route("/caretaker/reports")
@role_required("caretaker")
def caretaker_reports():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT r.resort_id, r.resort_name, r.address, r.status
            FROM resorts r
            JOIN caretakers c ON c.resort_id = r.resort_id
            WHERE c.account_id = %s AND c.status = 'Active'
            """,
            (session.get("account_id"),),
        )
        resort = cursor.fetchone()
        if not resort:
            return redirect(url_for("login"))
        cursor.execute(
            """
            SELECT COUNT(*) AS bookings
            FROM reservations
            WHERE resort_id = %s
              AND created_at >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
            """,
            (resort["resort_id"],),
        )
        bookings = cursor.fetchone()["bookings"] or 0
        cursor.execute(
            """
            SELECT COALESCE(SUM(p.amount_paid), 0) AS revenue
            FROM payments p
            JOIN reservations r ON r.reservation_id = p.reservation_id
            WHERE r.resort_id = %s
              AND p.payment_status = 'Verified'
              AND p.payment_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
            """,
            (resort["resort_id"],),
        )
        revenue = cursor.fetchone()["revenue"] or 0
        return render_template(
            "caretaker/caretaker_reports.html",
            fullname=session.get("fullname", "Caretaker"),
            resort=resort,
            bookings=bookings,
            revenue=revenue,
        )
    finally:
        cursor.close()
        conn.close()

@app.route("/caretaker/reservations/<int:reservation_id>/review", methods=["POST"])
@role_required("caretaker")
def caretaker_review_reservation(reservation_id):
    action = request.form.get("action")
    if action not in {"approve", "reject"}:
        flash("Invalid reservation action.", "warning")
        return redirect(url_for("caretaker_dashboard"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
                 SELECT r.reservation_id, cu.account_id AS customer_account_id,
                     r.reservation_status,
                   p.payment_id, p.payment_status
            FROM reservations r
            JOIN caretakers c ON c.resort_id = r.resort_id
                 JOIN customers cu ON cu.customer_id = r.customer_id
            LEFT JOIN payments p ON p.payment_id = (
                SELECT p2.payment_id
                FROM payments p2
                WHERE p2.reservation_id = r.reservation_id
                ORDER BY p2.payment_id DESC
                LIMIT 1
            )
            WHERE r.reservation_id = %s
              AND c.account_id = %s
              AND c.status = 'Active'
            FOR UPDATE
            """,
            (reservation_id, session.get("account_id")),
        )
        reservation = cursor.fetchone()
        if not reservation:
            flash("Reservation not found for your assigned resort.", "danger")
            return redirect(url_for("caretaker_dashboard"))
        if reservation["reservation_status"] in {"Cancelled", "Rejected", "Completed"}:
            flash("This reservation can no longer be reviewed.", "warning")
            return redirect(url_for("caretaker_dashboard"))
        if not reservation["payment_id"]:
            flash("The customer has not submitted payment proof yet.", "warning")
            return redirect(url_for("caretaker_dashboard"))

        approved = action == "approve"
        payment_status = "Verified" if approved else "Rejected"
        reservation_status = "Confirmed" if approved else "Rejected"
        cursor.execute(
            "UPDATE payments SET payment_status = %s WHERE payment_id = %s",
            (payment_status, reservation["payment_id"]),
        )
        cursor.execute(
            "UPDATE reservations SET reservation_status = %s WHERE reservation_id = %s",
            (reservation_status, reservation_id),
        )
        cursor.execute(
            """
            INSERT INTO notifications (account_id, title, message, type)
            VALUES (%s, %s, %s, %s)
            """,
            (
                reservation["customer_account_id"],
                "Reservation approved" if approved else "Reservation rejected",
                f"Your reservation #RSV-{reservation_id} was {'approved' if approved else 'rejected'} by the caretaker.",
                "reservation_approved" if approved else "reservation_rejected",
            ),
        )
        conn.commit()
        flash(
            "Reservation approved and payment verified." if approved else "Reservation rejected.",
            "success" if approved else "warning",
        )
    except Exception:
        conn.rollback()
        flash("The reservation review could not be saved.", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("caretaker_dashboard"))

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

        if caretaker["approval_status"] == "Approved":
            flash("Caretaker is already approved.", "warning")
            return redirect(url_for("admin_dashboard"))

        cursor.execute(
            """
            UPDATE accounts
            SET account_status = 'Active', approval_status = 'Approved', is_verified = 1,
                approved_by = %s, approved_at = NOW()
            WHERE account_id = %s
            """,
            (session.get("user_id"), account_id)
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
                <p>You can now log in using your registered email and password.</p>
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

        cursor.execute(
            """
            UPDATE accounts
            SET account_status='Inactive', approval_status='Rejected', approved_by=%s, approved_at=NOW()
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

@app.route("/admin/caretakers/<int:account_id>/reset-password", methods=["POST"])
@role_required("owner")
def reset_caretaker_password(account_id):
    new_password = request.form.get("new_password", "")
    if len(new_password) < 8:
        flash("Caretaker password must be at least 8 characters.", "warning")
        return redirect(url_for("admin_dashboard"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT a.account_id
            FROM accounts a
            JOIN caretakers c ON c.account_id = a.account_id
            WHERE a.account_id = %s AND a.role = 'caretaker'
            """,
            (account_id,),
        )
        if not cursor.fetchone():
            flash("Caretaker account not found.", "danger")
            return redirect(url_for("admin_dashboard"))

        cursor.execute(
            "UPDATE accounts SET password = %s WHERE account_id = %s AND role = 'caretaker'",
            (generate_password_hash(new_password), account_id),
        )
        conn.commit()
        flash("Caretaker password reset successfully.", "success")
    except Exception:
        conn.rollback()
        flash("Caretaker password could not be reset.", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("admin_dashboard"))