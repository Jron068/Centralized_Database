from flask import render_template, request, session, redirect, url_for, flash
from werkzeug.security import check_password_hash, generate_password_hash
from app import app
from config import get_connection

def get_customer_row(cursor):
    """Fetch the customers row linked to the logged-in account, if any."""
    cursor.execute(
        "SELECT customer_id, phone, email FROM customers WHERE account_id = %s",
        (session.get("account_id"),)
    )
    return cursor.fetchone()



@app.route("/customer_landingpage")
def customer_landingpage():

    # Make sure the customer is logged in
    if "account_id" not in session:
        return redirect(url_for("login"))

    account_id = session["account_id"]

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:

        # ==========================================
        # 1. GET CUSTOMER
        # ==========================================

        cursor.execute("""
            SELECT
                c.customer_id,
                a.fullname,
                a.email
            FROM customers c
            JOIN accounts a
                ON c.account_id = a.account_id
            WHERE c.account_id = %s
        """, (account_id,))

        customer = cursor.fetchone()

        if not customer:
            return "Customer account not found", 404

        customer_id = customer["customer_id"]


        # ==========================================
        # 2. TOTAL BOOKINGS
        # ==========================================

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM reservations
            WHERE customer_id = %s
        """, (customer_id,))

        total_bookings = cursor.fetchone()["total"]


        # ==========================================
        # 3. UPCOMING STAYS
        # ==========================================

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM reservations
            WHERE customer_id = %s
              AND check_in >= CURDATE()
              AND reservation_status IN ('Pending', 'Confirmed')
        """, (customer_id,))

        upcoming_stays = cursor.fetchone()["total"]


        # ==========================================
        # 4. COMPLETED RESERVATIONS
        # ==========================================

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM reservations
            WHERE customer_id = %s
              AND reservation_status = 'Completed'
        """, (customer_id,))

        completed_steps = cursor.fetchone()["total"]


        # ==========================================
        # 5. PENDING PAYMENTS
        # ==========================================

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM payments p
            JOIN reservations r
                ON p.reservation_id = r.reservation_id
            WHERE r.customer_id = %s
              AND p.payment_status = 'Pending'
        """, (customer_id,))

        pending_payment = cursor.fetchone()["total"]


        # ==========================================
        # 6. UPCOMING RESERVATIONS
        # ==========================================

        cursor.execute("""
            SELECT
                r.reservation_id,
                rs.resort_name,
                r.check_in,
                r.check_out,
                r.guests,
                r.total_amount,
                r.reservation_status
            FROM reservations r
            JOIN resorts rs
                ON r.resort_id = rs.resort_id
            WHERE r.customer_id = %s
              AND r.check_in >= CURDATE()
              AND r.reservation_status IN ('Pending', 'Confirmed')
            ORDER BY r.check_in ASC
            LIMIT 5
        """, (customer_id,))

        upcoming_reservations = cursor.fetchall()


        # ==========================================
        # 7. RECENT RESERVATIONS
        # ==========================================

        cursor.execute("""
            SELECT
                r.reservation_id,
                rs.resort_name,
                r.check_in,
                r.check_out,
                r.reservation_status,
                r.created_at
            FROM reservations r
            JOIN resorts rs
                ON r.resort_id = rs.resort_id
            WHERE r.customer_id = %s
            ORDER BY r.created_at DESC
            LIMIT 5
        """, (customer_id,))

        recent_reservations = cursor.fetchall()


        # ==========================================
        # 8. UNREAD MESSAGES
        # ==========================================

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM messages
            WHERE receiver_account = %s
              AND is_read = 0
        """, (account_id,))

        unread_messages = cursor.fetchone()["total"]


        # ==========================================
        # 9. UNREAD NOTIFICATIONS
        # ==========================================

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM notifications
            WHERE account_id = %s
              AND is_read = 0
        """, (account_id,))

        unread_notifications = cursor.fetchone()["total"]


        # ==========================================
        # 10. SEND DATA TO HTML
        # ==========================================

        return render_template(
            "customer/customer_landingpage.html",

            username=customer["fullname"],

            total_bookings=total_bookings,
            upcoming_stays=upcoming_stays,
            completed_steps=completed_steps,
            pending_payment=pending_payment,

            upcoming_reservations=upcoming_reservations,
            recent_reservations=recent_reservations
        )

    finally:
        cursor.close()
        conn.close()


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
    fullname=session.get("fullname", "Guest")
    return render_template("customer/customer_reservation.html", username=fullname)

@app.route("/customer_paymentHistory")
def customer_paymentHistory():  
    fullname=session.get("fullname", "Guest")
    return render_template("customer/customer_paymentHistory.html", username=fullname)

        
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
        