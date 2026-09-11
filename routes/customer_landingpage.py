from flask import render_template, request, session, redirect, url_for, flash
from werkzeug.security import check_password_hash, generate_password_hash
from app import app
from config import get_connection
from flask import jsonify

def get_customer_row(cursor):
    """Fetch the customers row linked to the logged-in account, if any."""
    cursor.execute(
        "SELECT customer_id, phone, email FROM customers WHERE account_id = %s",
        (session.get("account_id"),)
    )
    return cursor.fetchone()


@app.route("/customer_aboutpage")
def customer_aboutpage():
    fullname = session.get("fullname", "Guest")
    return render_template("customer/customer_aboutpage.html", username=fullname)

@app.route("/customer_howitworks")
def customer_howitworks():
    fullname=session.get("fullname", "Guest")
    return render_template("customer/customer_howitworks.html", username=fullname)


@app.route("/customer_reservation")
def customer_reservation():
    if "account_id" not in session:
        return redirect(url_for("login"))

    fullname = session.get("fullname", "Guest")
    account_id = session["account_id"]

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                r.reservation_id,
                res.resort_name,
                r.check_in,
                r.check_out,
                r.guests,
                r.total_amount,
                r.reservation_status,
                r.created_at
            FROM reservations r
            JOIN customers c ON r.customer_id = c.customer_id
            JOIN resorts res ON r.resort_id = res.resort_id
            WHERE c.account_id = %s
            ORDER BY r.created_at DESC
        """, (account_id,))
        reservations = cursor.fetchall()

        cursor.execute("""
            SELECT notification_id, title, message, created_at
            FROM notifications
            WHERE account_id = %s AND is_read = 0
            ORDER BY created_at DESC
            LIMIT 5
        """, (account_id,))
        notifications = cursor.fetchall()
        if notifications:
            notification_ids = [item["notification_id"] for item in notifications]
            placeholders = ",".join(["%s"] * len(notification_ids))
            cursor.execute(
                f"UPDATE notifications SET is_read = 1 WHERE notification_id IN ({placeholders})",
                notification_ids
            )
            conn.commit()

        return render_template(
            "customer/customer_reservation.html",
            username=fullname,
            reservations=reservations,
            notifications=notifications
        )
    finally:
        cursor.close()
        conn.close()

@app.route("/customer_paymentHistory")
def customer_paymentHistory():
    if "account_id" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT p.payment_id, p.proof_of_payment, p.reference_number,
                   p.amount_paid, p.payment_status, p.payment_date,
                   r.reservation_id, res.resort_name
            FROM payments p
            JOIN reservations r ON r.reservation_id = p.reservation_id
            JOIN customers c ON c.customer_id = r.customer_id
            JOIN resorts res ON res.resort_id = r.resort_id
            WHERE c.account_id = %s
            ORDER BY p.payment_date DESC, p.payment_id DESC
        """, (session["account_id"],))
        payments = cursor.fetchall()
        return render_template(
            "customer/customer_paymentHistory.html",
            username=session.get("fullname", "Guest"),
            payments=payments
        )
    finally:
        cursor.close()
        conn.close()

        
@app.route("/customer_deal")
def customer_deal():
    fullname = session.get("fullname", "Guest")
    return render_template("customer/customer_deal.html", username=fullname)

@app.route("/customer_favorites")
def customer_favorites():
    fullname = session.get("fullname", "Guest")
    return render_template("customer/customer_favorites.html", username=fullname)


# ================= PROFILE SETTING =================
@app.route("/customer_profileSetting", methods=["GET", "POST"])
def customer_profileSetting():
    fullname = session.get("fullname", "Guest")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if request.method == "POST":
            new_fullname = request.form.get("fullname", "").strip()
            email = request.form.get("email", "").strip()
            contact_email = request.form.get("contact_email", "").strip()
            phone = request.form.get("phone", "").strip()

            if not new_fullname or not email:
                flash("Full name and email are required.", "warning")
                return redirect(url_for("customer_profileSetting"))

            cursor.execute(
                "SELECT account_id FROM accounts WHERE email = %s AND account_id != %s",
                (email, session.get("account_id"))
            )
            if cursor.fetchone():
                flash("That email is already in use by another account.", "warning")
                return redirect(url_for("customer_profileSetting"))

            cursor.execute(
                "UPDATE accounts SET fullname = %s, email = %s WHERE account_id = %s",
                (new_fullname, email, session.get("account_id"))
            )

            existing = get_customer_row(cursor)
            if existing:
                cursor.execute(
                    "UPDATE customers SET phone = %s, email = %s WHERE account_id = %s",
                    (phone, contact_email, session.get("account_id"))
                )
            else:
                cursor.execute(
                    "INSERT INTO customers (account_id, phone, email) VALUES (%s, %s, %s)",
                    (session.get("account_id"), phone, contact_email)
                )

            conn.commit()

            # Keep session fullname in sync since the navbar reads it directly
            session["fullname"] = new_fullname

            flash("Profile updated successfully.", "success")
            return redirect(url_for("customer_profileSetting"))

        # GET
        cursor.execute(
            "SELECT account_id, fullname, email FROM accounts WHERE account_id = %s",
            (session.get("account_id"),)
        )
        account = cursor.fetchone()
        customer = get_customer_row(cursor) or {}

        return render_template(
            "customer/customer_profileSetting.html",
            username=fullname,
            account=account,
            customer=customer
        )
    finally:
        cursor.close()
        conn.close()


# ================= CHANGE PASSWORD =================
@app.route("/customer_changePassword", methods=["GET", "POST"])
def customer_changePassword():
    fullname = session.get("fullname", "Guest")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if request.method == "POST":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")

            if new_password != confirm_password:
                flash("New password and confirmation do not match.", "warning")
                return redirect(url_for("customer_changePassword"))

            if len(new_password) < 8:
                flash("New password must be at least 8 characters.", "warning")
                return redirect(url_for("customer_changePassword"))

            cursor.execute(
                "SELECT password FROM accounts WHERE account_id = %s",
                (session.get("account_id"),)
            )
            row = cursor.fetchone()

            if not row or not check_password_hash(row["password"], current_password):
                flash("Your current password is incorrect.", "error")
                return redirect(url_for("customer_changePassword"))

            new_hash = generate_password_hash(new_password)
            cursor.execute(
                "UPDATE accounts SET password = %s WHERE account_id = %s",
                (new_hash, session.get("account_id"))
            )
            conn.commit()

            flash("Password updated successfully. Please log in again.", "success")
            session.clear()
            return redirect(url_for("login"))

        return render_template(
            "customer/customer_changePassword.html",
            username=fullname
        )
    finally:
        cursor.close()
        conn.close()
        
