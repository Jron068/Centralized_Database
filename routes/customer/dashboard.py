from flask import render_template, request, session, redirect, url_for, flash
from werkzeug.security import check_password_hash, generate_password_hash
from app import app
from config import get_connection
from flask import jsonify
from models.resort_updates import ensure_resort_updates_table, update_image_url
from models.customer_favorites import ensure_customer_favorites_table
from models.account_profile import ensure_account_profiles_table, save_profile_photo
from models.file_storage import file_url
from models.resort import enrich_resorts

def get_customer_row(cursor):
    """Fetch the customers row linked to the logged-in account, if any."""
    cursor.execute(
        "SELECT customer_id, phone, email FROM customers WHERE account_id = %s",
        (session.get("account_id"),)
    )
    return cursor.fetchone()

@app.route("/customer_landingpage")
def customer_landingpage():
    # Keep the legacy URL used by the customer top navigation connected to
    # the authenticated dashboard and its live reservation data.
    return redirect(url_for("customer_dashboard"))

@app.route("/customer_messages")
def customer_messages():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        ensure_resort_updates_table(cursor)
        cursor.execute(
            "SELECT u.update_id, u.title, u.category, u.message, u.image_path, u.created_at, "
            "r.resort_name FROM resort_updates u LEFT JOIN resorts r ON r.resort_id = u.resort_id "
            "WHERE u.resort_id IS NULL OR r.status = 'Active' "
            "ORDER BY u.created_at DESC, u.update_id DESC LIMIT 100"
        )
        updates = cursor.fetchall()
        for update in updates:
            update["image_url"] = update_image_url(update.pop("image_path", None))
        return render_template("customer/customer_message.html", username=session.get("fullname", "Guest"), updates=updates)
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
    if session.get("role") != "customer" or "account_id" not in session:
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
    if session.get("role") != "customer" or "account_id" not in session:
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
        for payment in payments:
            payment["proof_url"] = file_url(payment["proof_of_payment"]) if payment["proof_of_payment"] else None
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
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT resort_id, resort_name, address, description, logo, price, max_pax
            FROM resorts WHERE status = 'Active' ORDER BY resort_name
        """)
        resorts = enrich_resorts(cursor.fetchall())
        return render_template(
            "customer/customer_deal.html",
            username=session.get("fullname", "Guest"),
            resorts=resorts,
        )
    finally:
        cursor.close()
        conn.close()

@app.route("/customer_favorites")
def customer_favorites():
    if session.get("role") != "customer" or "account_id" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        ensure_customer_favorites_table(cursor)
        cursor.execute("""
            SELECT r.resort_id, r.resort_name, r.address, r.description,
                   r.logo, r.price, r.max_pax, f.created_at
            FROM customer_favorites f
            JOIN resorts r ON r.resort_id = f.resort_id
            WHERE f.account_id = %s AND r.status = 'Active'
            ORDER BY f.created_at DESC, r.resort_name
        """, (session["account_id"],))
        favorites = enrich_resorts(cursor.fetchall())
        return render_template(
            "customer/customer_favorite.html",
            username=session.get("fullname", "Guest"),
            favorites=favorites,
        )
    finally:
        cursor.close()
        conn.close()


@app.route("/customer_favorites/<int:resort_id>/toggle", methods=["POST"])
def toggle_customer_favorite(resort_id):
    wants_json = "application/json" in request.headers.get("Accept", "")
    if session.get("role") != "customer" or "account_id" not in session:
        if wants_json:
            return jsonify({"ok": False, "login_required": True}), 401
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        ensure_customer_favorites_table(cursor)
        cursor.execute(
            "SELECT resort_id FROM resorts WHERE resort_id = %s AND status = 'Active'",
            (resort_id,),
        )
        if not cursor.fetchone():
            if wants_json:
                return jsonify({"ok": False, "message": "That resort is no longer available."}), 404
            flash("That resort is no longer available.", "warning")
            return redirect(url_for("customer_favorites"))

        cursor.execute(
            "SELECT resort_id FROM customer_favorites WHERE account_id = %s AND resort_id = %s",
            (session["account_id"], resort_id),
        )
        if cursor.fetchone():
            cursor.execute(
                "DELETE FROM customer_favorites WHERE account_id = %s AND resort_id = %s",
                (session["account_id"], resort_id),
            )
            saved = False
            flash("Resort removed from your saved list.", "success")
        else:
            cursor.execute(
                "INSERT INTO customer_favorites (account_id, resort_id) VALUES (%s, %s)",
                (session["account_id"], resort_id),
            )
            saved = True
            flash("Resort saved to your favorites.", "success")
        conn.commit()
        if wants_json:
            return jsonify({"ok": True, "saved": saved})
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("customer_favorites"))


# ================= PROFILE SETTING =================
@app.route("/customer_profileSetting", methods=["GET", "POST"])
def customer_profileSetting():
    if session.get("role") != "customer" or "account_id" not in session:
        return redirect(url_for("login"))
    fullname = session.get("fullname", "Guest")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if request.method == "POST":
            new_fullname = request.form.get("fullname", "").strip()
            email = request.form.get("email", "").strip()
            contact_email = request.form.get("contact_email", "").strip()
            phone = request.form.get("phone", "").strip()
            profile_upload = request.files.get("profile_picture")

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

            profile_path = None
            if profile_upload and profile_upload.filename:
                try:
                    profile_path = save_profile_photo(profile_upload)
                except ValueError as exc:
                    conn.rollback()
                    flash(str(exc), "warning")
                    return redirect(url_for("customer_profileSetting"))
                ensure_account_profiles_table(cursor)
                cursor.execute(
                    "INSERT INTO account_profiles (account_id, profile_photo_path) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE profile_photo_path = VALUES(profile_photo_path)",
                    (session.get("account_id"), profile_path),
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
            if profile_path:
                session["profile_photo"] = file_url(profile_path)

            flash("Profile updated successfully.", "success")
            return redirect(url_for("customer_profileSetting"))

        # GET
        cursor.execute(
            "SELECT account_id, fullname, email FROM accounts WHERE account_id = %s",
            (session.get("account_id"),)
        )
        account = cursor.fetchone()
        ensure_account_profiles_table(cursor)
        cursor.execute(
            "SELECT profile_photo_path FROM account_profiles WHERE account_id = %s",
            (session.get("account_id"),),
        )
        photo = cursor.fetchone()
        profile_photo = file_url(photo["profile_photo_path"]) if photo and photo.get("profile_photo_path") else None
        if profile_photo:
            session["profile_photo"] = profile_photo
        customer = get_customer_row(cursor) or {}

        return render_template(
            "customer/customer_profileSetting.html",
            username=fullname,
            account=account,
            customer=customer,
            profile_photo=profile_photo,
        )
    finally:
        cursor.close()
        conn.close()


# ================= CHANGE PASSWORD =================
@app.route("/customer_changePassword", methods=["GET", "POST"])
def customer_changePassword():
    if session.get("role") != "customer" or "account_id" not in session:
        return redirect(url_for("login"))
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
        
