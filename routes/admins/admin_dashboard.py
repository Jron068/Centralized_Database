import calendar as calendar_lib
from datetime import date, datetime, timedelta

from flask import render_template, request, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash
from app import app
from config import get_connection
from models.decorators import role_required

@app.route("/admin_dashboard", endpoint="admin_dashboard")
@app.route("/owner-dashboard", endpoint="owner_dashboard")
@app.route("/dashboard", endpoint="dashboard")
@role_required("owner")
def admin_dashboard():
    if not session.get("owner_id"):
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    selected_resort = request.args.get("resort_id", "").strip()
    try:
        selected_resort = int(selected_resort) if selected_resort else None
    except ValueError:
        selected_resort = None

    try:
        cursor.execute(
            """
            SELECT resort_id, resort_name, status
            FROM resorts
            ORDER BY resort_name ASC
            """
        )
        my_resorts = cursor.fetchall()
        resort_ids = [r["resort_id"] for r in my_resorts]

        cursor.execute(
            """
            SELECT resort_id, resort_name, status
            FROM resorts
            WHERE owner_id = %s
            ORDER BY resort_name ASC
            """,
            (session.get("owner_id"),),
        )
        owner_resorts = cursor.fetchall()

        cursor.execute(
            """
            SELECT a.account_id, a.fullname, a.email, c.status, c.assigned_date,
                   r.resort_id, r.resort_name
            FROM caretakers c
            JOIN accounts a ON a.account_id = c.account_id
            JOIN resorts r ON r.resort_id = c.resort_id
            ORDER BY r.resort_name ASC, a.fullname ASC
            """
        )
        assigned_caretakers = cursor.fetchall()
        taken_resort_ids = {row["resort_id"] for row in assigned_caretakers}

        cursor.execute(
            """
            SELECT r.resort_id,
                   r.resort_name,
                   COUNT(DISTINCT res.reservation_id) AS total_bookings,
                   COALESCE(SUM(CASE WHEN p.payment_status = 'Verified' THEN p.amount_paid ELSE 0 END), 0) AS total_revenue,
                   COALESCE(SUM(CASE WHEN p.payment_status = 'Pending' THEN 1 ELSE 0 END), 0) AS pending_payments,
                   COALESCE(MAX(a.fullname), 'Unassigned') AS caretaker_name
            FROM resorts r
            LEFT JOIN reservations res ON res.resort_id = r.resort_id
            LEFT JOIN payments p ON p.reservation_id = res.reservation_id
            LEFT JOIN caretakers c ON c.resort_id = r.resort_id AND c.status = 'Active'
            LEFT JOIN accounts a ON a.account_id = c.account_id
            WHERE r.owner_id = %s
            GROUP BY r.resort_id, r.resort_name
            ORDER BY r.resort_name ASC
            """,
            (session.get("owner_id"),),
        )
        resort_stats = cursor.fetchall()

        owner_resort_ids = {row["resort_id"] for row in owner_resorts}
        if selected_resort not in owner_resort_ids:
            selected_resort = None

        if selected_resort:
            selected_resort_name = next((row["resort_name"] for row in resort_stats if row["resort_id"] == selected_resort), None)
        else:
            selected_resort_name = None

        # Defaults if this owner has no resorts yet
        total_bookings = 0
        total_revenue = "0.00"
        pending_payment = 0
        revenue_labels, revenue_values = [], []
        source_labels, source_values = [], []
        top_properties = []

        if resort_ids:
            placeholders = ",".join(["%s"] * len(resort_ids))

            # Total Bookings
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM reservations WHERE resort_id IN ({placeholders})",
                resort_ids
            )
            total_bookings = cursor.fetchone()["total"] or 0

            # Total Revenue (Verified payments only)
            cursor.execute(
                f"""
                SELECT COALESCE(SUM(p.amount_paid), 0) AS total_revenue
                FROM payments p
                JOIN reservations r ON p.reservation_id = r.reservation_id
                WHERE r.resort_id IN ({placeholders}) AND p.payment_status = 'Verified'
                """,
                resort_ids
            )
            total_revenue = f"{cursor.fetchone()['total_revenue']:,.2f}"

            # Pending Payments count
            cursor.execute(
                f"""
                SELECT COUNT(*) AS pending FROM payments p
                JOIN reservations r ON p.reservation_id = r.reservation_id
                WHERE r.resort_id IN ({placeholders}) AND p.payment_status = 'Pending'
                """,
                resort_ids
            )
            pending_payment = cursor.fetchone()["pending"] or 0

            # Revenue Trend (last 30 days)
            cursor.execute(
                f"""
                SELECT DATE(p.payment_date) AS pay_date, SUM(p.amount_paid) AS daily_total
                FROM payments p
                JOIN reservations r ON p.reservation_id = r.reservation_id
                WHERE r.resort_id IN ({placeholders})
                  AND p.payment_status = 'Verified'
                  AND p.payment_date >= (CURDATE() - INTERVAL 30 DAY)
                GROUP BY DATE(p.payment_date)
                ORDER BY pay_date ASC
                """,
                resort_ids
            )
            revenue_rows = cursor.fetchall()
            revenue_labels = [row["pay_date"].strftime("%b %d") for row in revenue_rows]
            revenue_values = [float(row["daily_total"]) for row in revenue_rows]

            # Bookings by Status (no "source" column exists in your schema)
            cursor.execute(
                f"""
                SELECT reservation_status, COUNT(*) AS cnt
                FROM reservations
                WHERE resort_id IN ({placeholders})
                GROUP BY reservation_status
                """,
                resort_ids
            )
            source_rows = cursor.fetchall()
            source_labels = [row["reservation_status"] for row in source_rows]
            source_values = [row["cnt"] for row in source_rows]

            # Top Performing Properties
            cursor.execute(
                f"""
                SELECT res.resort_name AS name,
                       COUNT(r.reservation_id) AS bookings,
                       COALESCE(SUM(p.amount_paid), 0) AS revenue
                FROM resorts res
                LEFT JOIN reservations r ON r.resort_id = res.resort_id
                LEFT JOIN payments p ON p.reservation_id = r.reservation_id AND p.payment_status = 'Verified'
                WHERE res.resort_id IN ({placeholders})
                GROUP BY res.resort_id, res.resort_name
                ORDER BY revenue DESC
                """,
                resort_ids
            )
            top_properties = cursor.fetchall()

        return render_template(
            "admin/admin.html",
            username=session.get("fullname"),
            resorts=my_resorts,
            owner_resorts=owner_resorts,
            assigned_caretakers=assigned_caretakers,
            taken_resort_ids=taken_resort_ids,
            selected_resort=selected_resort,
            selected_resort_name=selected_resort_name,
            resort_stats=resort_stats,
            total_bookings=total_bookings,
            total_revenue=total_revenue,
            pending_payment=pending_payment,
            revenue_labels=revenue_labels,
            revenue_values=revenue_values,
            source_labels=source_labels,
            source_values=source_values,
            top_properties=top_properties,
        )
    finally:
        cursor.close()
        conn.close()

@app.route("/admin/caretakers/create", methods=["POST"])
@role_required("owner")
def create_caretaker_account():
    fullname = request.form.get("fullname", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()
    resort_id = request.form.get("resort_id")

    if not fullname or not email or not password or not resort_id:
        flash("Please fill in all caretaker fields.", "warning")
        return redirect(url_for("admin_dashboard"))

    if len(password) < 8:
        flash("Caretaker password must be at least 8 characters.", "warning")
        return redirect(url_for("admin_dashboard"))

    owner_id = session.get("owner_id")
    if not owner_id:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT resort_id
            FROM resorts
            WHERE resort_id = %s AND owner_id = %s
            """,
            (resort_id, owner_id),
        )
        if not cursor.fetchone():
            flash("Selected resort is not valid for your account.", "warning")
            return redirect(url_for("admin_dashboard"))

        cursor.execute(
            "SELECT account_id FROM accounts WHERE email = %s",
            (email,),
        )
        if cursor.fetchone():
            flash("A caretaker account with this email already exists.", "warning")
            return redirect(url_for("admin_dashboard"))

        cursor.execute(
            """
            SELECT 1
            FROM caretakers
            WHERE resort_id = %s AND status IN ('Active', 'Pending')
            LIMIT 1
            """,
            (resort_id,),
        )
        if cursor.fetchone():
            flash("This resort already has an active or pending caretaker assigned.", "warning")
            return redirect(url_for("admin_dashboard"))

        hashed_password = generate_password_hash(password)
        cursor.execute(
            """
            INSERT INTO accounts
            (fullname, email, password, role, account_status, is_verified, approval_status, approved_by, approved_at)
            VALUES (%s, %s, %s, 'caretaker', 'Active', 1, 'Approved', %s, NOW())
            """,
            (fullname, email, hashed_password, session.get("user_id")),
        )
        account_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO caretakers (account_id, resort_id, assigned_date, status)
            VALUES (%s, %s, NOW(), 'Active')
            """,
            (account_id, resort_id),
        )
        conn.commit()
        flash(f"Caretaker account for {fullname} was created successfully.", "success")
    except Exception as exc:
        conn.rollback()
        print("CREATE CARETAKER ERROR:", exc)
        flash("Unable to create caretaker account right now.", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("admin_dashboard"))


#this is route for NAVBAR

@app.route("/booking")
def booking():
    return render_template("admin/navbar/booking.html")

@app.route("/properties", methods=["GET", "POST"])
@role_required("owner")
def properties():
    owner_id = session.get("owner_id")
    if not owner_id:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        if request.method == "POST":
            resort_name = request.form.get("resort_name", "").strip()

            if not resort_name:
                flash("Property name is required.", "warning")
                return redirect(url_for("properties"))

            cursor.execute(
                """
                INSERT INTO resorts
                    (owner_id, resort_name, address, description, email, phone, amenities, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    owner_id,
                    resort_name,
                    request.form.get("address", "").strip() or None,
                    request.form.get("description", "").strip() or None,
                    request.form.get("email", "").strip() or None,
                    request.form.get("phone", "").strip() or None,
                    request.form.get("amenities", "").strip() or None,
                    request.form.get("status", "Active"),
                ),
            )
            conn.commit()
            flash("Property added successfully.", "success")
            return redirect(url_for("properties"))

        cursor.execute(
            """
            SELECT resort_id, resort_name, address, description, email, phone,
                   amenities, status, logo
            FROM resorts
            WHERE owner_id = %s
            ORDER BY created_at DESC, resort_name ASC
            """,
            (owner_id,),
        )
        properties = cursor.fetchall()
        return render_template(
            "admin/navbar/properties.html",
            properties=properties,
            username=session.get("fullname", "Owner"),
        )
    finally:
        cursor.close()
        conn.close()

@app.route("/properties/<int:resort_id>/edit", methods=["POST"])
@role_required("owner")
def edit_property(resort_id):
    owner_id = session.get("owner_id")
    resort_name = request.form.get("resort_name", "").strip()
    status = request.form.get("status", "Active")

    if not owner_id:
        return redirect(url_for("login"))
    if not resort_name:
        flash("Property name is required.", "warning")
        return redirect(url_for("properties"))
    if status not in {"Active", "Inactive"}:
        flash("Invalid property status.", "warning")
        return redirect(url_for("properties"))

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE resorts
            SET resort_name = %s, address = %s, description = %s,
                email = %s, phone = %s, amenities = %s, status = %s
            WHERE resort_id = %s AND owner_id = %s
            """,
            (
                resort_name,
                request.form.get("address", "").strip() or None,
                request.form.get("description", "").strip() or None,
                request.form.get("email", "").strip() or None,
                request.form.get("phone", "").strip() or None,
                request.form.get("amenities", "").strip() or None,
                status,
                resort_id,
                owner_id,
            ),
        )
        updated = cursor.rowcount
        conn.commit()
        flash(
            "Property updated successfully." if updated else "Property was not found or is not yours.",
            "success" if updated else "warning",
        )
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("properties"))

@app.route("/properties/<int:resort_id>/delete", methods=["POST"])
@role_required("owner")
def delete_property(resort_id):
    owner_id = session.get("owner_id")
    if not owner_id:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM resorts WHERE resort_id = %s AND owner_id = %s",
            (resort_id, owner_id),
        )
        conn.commit()
        flash(
            "Property deleted successfully." if cursor.rowcount else "Property was not found or is not yours.",
            "success" if cursor.rowcount else "warning",
        )
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("properties"))

@app.route("/reports")
@role_required("owner")
def reports():
    current_month = date.today().strftime("%Y-%m")
    selected_month = request.args.get("month", current_month)
    try:
        month_start = datetime.strptime(selected_month, "%Y-%m").date().replace(day=1)
        if month_start.strftime("%Y-%m") != selected_month:
            raise ValueError
    except (TypeError, ValueError):
        selected_month = current_month
        month_start = date.today().replace(day=1)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_end = next_month - timedelta(days=1)
    selected_resort = request.args.get("resort_id", "")
    try:
        selected_resort = int(selected_resort) if selected_resort else None
    except ValueError:
        selected_resort = None

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT resort_id, resort_name FROM resorts WHERE owner_id = %s ORDER BY resort_name",
            (session.get("owner_id"),),
        )
        report_resorts = cursor.fetchall()
        resort_filter = " AND r.resort_id = %s" if selected_resort else ""
        resort_params = [selected_resort] if selected_resort else []

        cursor.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM reservations r
            WHERE r.created_at >= %s AND r.created_at < %s{resort_filter}
            """,
            (month_start, next_month, *resort_params),
        )
        total_bookings = cursor.fetchone()["total"] or 0

        cursor.execute(
                        f"""
            SELECT COALESCE(SUM(p.amount_paid), 0) AS total
                        FROM payments p
                        JOIN reservations r ON r.reservation_id = p.reservation_id
            WHERE p.payment_status = 'Verified'
                            AND p.payment_date >= %s AND p.payment_date < %s{resort_filter}
            """,
                        (month_start, next_month, *resort_params),
        )
        revenue = float(cursor.fetchone()["total"] or 0)

        if selected_resort:
            cursor.execute(
                "SELECT COUNT(*) AS total FROM resorts WHERE status = 'Active' AND resort_id = %s",
                (selected_resort,),
            )
        else:
            cursor.execute("SELECT COUNT(*) AS total FROM resorts WHERE status = 'Active'")
        total_resorts = cursor.fetchone()["total"] or 0

        cursor.execute(
            f"""
            SELECT COALESCE(SUM(
                DATEDIFF(
                    LEAST(r.check_out, %s),
                    GREATEST(r.check_in, %s)
                )
            ), 0) AS occupied_nights
            FROM reservations r
                        WHERE r.reservation_status = 'Confirmed'
              AND r.check_in < %s AND r.check_out > %s
                            {resort_filter}
            """,
                        (next_month, month_start, next_month, month_start, *resort_params),
        )
        occupied_nights = float(cursor.fetchone()["occupied_nights"] or 0)
        days_in_month = (month_end - month_start).days + 1
        occupancy_rate = round(
            occupied_nights / (total_resorts * days_in_month) * 100
        ) if total_resorts else 0

        review_filter = " AND rv.resort_id = %s" if selected_resort else ""
        cursor.execute(
            f"""
            SELECT COALESCE(AVG(rating), 0) AS average_rating,
                   COUNT(*) AS total_reviews
            FROM reviews rv
            WHERE rv.review_date >= %s AND rv.review_date < %s{review_filter}
            """,
            (month_start, next_month, selected_resort)
            if selected_resort else (month_start, next_month),
        )
        rating_summary = cursor.fetchone()

        resort_summary_filter = " AND res.resort_id = %s" if selected_resort else ""
        cursor.execute(
            f"""
            SELECT res.resort_name,
                   COUNT(DISTINCT r.reservation_id) AS bookings,
                   COALESCE(SUM(
                       CASE WHEN p.payment_status = 'Verified' THEN p.amount_paid ELSE 0 END
                   ), 0) AS revenue
            FROM resorts res
            LEFT JOIN reservations r
                ON r.resort_id = res.resort_id
               AND r.created_at >= %s AND r.created_at < %s
                        LEFT JOIN payments p
                ON p.reservation_id = r.reservation_id
               AND p.payment_date >= %s AND p.payment_date < %s
            WHERE 1 = 1{resort_summary_filter}
            GROUP BY res.resort_id, res.resort_name
            ORDER BY revenue DESC, bookings DESC, res.resort_name ASC
            """,
            (month_start, next_month, month_start, next_month, selected_resort)
            if selected_resort else
            (month_start, next_month, month_start, next_month),
        )
        revenue_by_resort = cursor.fetchall()

        return render_template(
            "admin/navbar/reports.html",
            username=session.get("fullname", "Owner"),
            total_bookings=total_bookings,
            occupancy_rate=occupancy_rate,
            total_resorts=total_resorts,
            revenue=revenue,
            average_rating=float(rating_summary["average_rating"] or 0),
            total_reviews=rating_summary["total_reviews"] or 0,
            revenue_by_resort=revenue_by_resort,
            report_resorts=report_resorts,
            selected_month=selected_month,
            selected_resort=selected_resort,
        )
    finally:
        cursor.close()
        conn.close()



#this is route for SIDEBARS

@app.route("/calendar")
@role_required("owner")
def calendar():
    owner_id = session.get("owner_id")
    if not owner_id:
        return redirect(url_for("login"))

    today = date.today()
    try:
        selected_year = int(request.args.get("year", today.year))
        selected_month = int(request.args.get("month", today.month))
        selected_date = date(selected_year, selected_month, 1)
    except (TypeError, ValueError):
        selected_date = date(today.year, today.month, 1)

    month_start = selected_date
    month_end = date(
        selected_date.year,
        selected_date.month,
        calendar_lib.monthrange(selected_date.year, selected_date.month)[1],
    )

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
                 SELECT r.reservation_id, r.check_in, r.check_out,
                     r.reservation_status, res.resort_name,
                     COALESCE(r.guest_name, a.fullname) AS guest_name
            FROM reservations r
            JOIN resorts res ON res.resort_id = r.resort_id
            JOIN customers c ON c.customer_id = r.customer_id
            JOIN accounts a ON a.account_id = c.account_id
                        WHERE r.check_in IS NOT NULL
              AND r.check_out IS NOT NULL
                            AND r.check_in <= %s
                            AND r.check_out >= %s
                            AND r.reservation_status IN ('Pending', 'Confirmed')
            ORDER BY r.check_in, res.resort_name
            """,
                        (month_end, month_start),
        )
        reservations = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    events_by_date = {}
    for reservation in reservations:
        event_start = max(reservation["check_in"], month_start)
        event_end = min(reservation["check_out"], month_end)
        event_day = event_start
        while event_day <= event_end:
            events_by_date.setdefault(event_day.isoformat(), []).append(reservation)
            event_day += timedelta(days=1)

    first_weekday, days_in_month = calendar_lib.monthrange(selected_date.year, selected_date.month)
    calendar_start = month_start - timedelta(days=(first_weekday + 1) % 7)
    total_cells = ((calendar_start - month_start).days * -1 + days_in_month)
    total_cells = ((total_cells + 6) // 7) * 7
    calendar_days = [
        {
            "day": calendar_start + timedelta(days=index),
            "in_month": (calendar_start + timedelta(days=index)).month == selected_month,
        }
        for index in range(total_cells)
    ]

    previous_month = selected_date - timedelta(days=1)
    next_month = month_end + timedelta(days=1)
    return render_template(
        "admin/sidebar/calendar.html",
        calendar_days=calendar_days,
        events_by_date=events_by_date,
        calendar_month=selected_date.strftime("%B %Y"),
        previous_month=previous_month,
        next_month=next_month,
        today=today,
        username=session.get("fullname", "Owner"),
    )

@app.route("/payment")
def payment():
    return redirect(url_for("admin_payments"))

@app.route("/guests")
@role_required("owner")
def guests():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT c.customer_id, a.fullname AS guest_name, a.email,
                   COUNT(r.reservation_id) AS total_stays,
                   MAX(r.check_out) AS last_visit
            FROM customers c
            JOIN accounts a ON a.account_id = c.account_id
            JOIN reservations r ON r.customer_id = c.customer_id
            GROUP BY c.customer_id, a.fullname, a.email
            ORDER BY last_visit DESC, guest_name ASC
            """
        )
        guests = cursor.fetchall()
        return render_template(
            "admin/sidebar/guestStay.html",
            guests=guests,
            username=session.get("fullname", "Owner"),
        )
    finally:
        cursor.close()
        conn.close()

@app.route("/reviews")
@role_required("owner")
def reviews():  
    current_month = date.today().strftime("%Y-%m")
    selected_month = request.args.get("month", current_month)
    try:
        month_start = datetime.strptime(selected_month, "%Y-%m").date().replace(day=1)
        if month_start.strftime("%Y-%m") != selected_month:
            raise ValueError
    except (TypeError, ValueError):
        selected_month = current_month
        month_start = date.today().replace(day=1)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    selected_resort = request.args.get("resort_id", "")
    try:
        selected_resort = int(selected_resort) if selected_resort else None
    except ValueError:
        selected_resort = None

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT resort_id, resort_name FROM resorts WHERE owner_id = %s ORDER BY resort_name",
            (session.get("owner_id"),),
        )
        review_resorts = cursor.fetchall()
        resort_filter = " AND rv.resort_id = %s" if selected_resort else ""
        cursor.execute(
            f"""
            SELECT rv.review_id, rv.rating, rv.comment, rv.review_date,
                   a.fullname AS guest_name, res.resort_name
            FROM reviews rv
            JOIN customers c ON c.customer_id = rv.customer_id
            JOIN accounts a ON a.account_id = c.account_id
            JOIN resorts res ON res.resort_id = rv.resort_id
            WHERE rv.review_date >= %s AND rv.review_date < %s{resort_filter}
            ORDER BY rv.review_date DESC
            """,
            (month_start, next_month, selected_resort) if selected_resort else (month_start, next_month),
        )
        reviews = cursor.fetchall()
        return render_template(
            "admin/sidebar/Reviews.html",
            reviews=reviews,
            review_resorts=review_resorts,
            selected_month=selected_month,
            selected_resort=selected_resort,
            username=session.get("fullname", "Owner"),
        )
    finally:
        cursor.close()
        conn.close()

@app.route("/settings", methods=["GET", "POST"])
@role_required("owner")
def settings():
    account_id = session.get("account_id")
    if not account_id:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if request.method == "POST":
            fullname = request.form.get("fullname", "").strip()
            email = request.form.get("email", "").strip()
            if not fullname or not email:
                flash("Full name and email are required.", "warning")
                return redirect(url_for("settings"))

            cursor.execute(
                "SELECT account_id FROM accounts WHERE email = %s AND account_id <> %s",
                (email, account_id),
            )
            if cursor.fetchone():
                flash("That email is already in use.", "warning")
                return redirect(url_for("settings"))

            cursor.execute(
                "UPDATE accounts SET fullname = %s, email = %s WHERE account_id = %s AND role = 'owner'",
                (fullname, email, account_id),
            )
            conn.commit()
            session["fullname"] = fullname
            flash("Account settings updated successfully.", "success")
            return redirect(url_for("settings"))

        cursor.execute(
            "SELECT fullname, email FROM accounts WHERE account_id = %s AND role = 'owner'",
            (account_id,),
        )
        account = cursor.fetchone()
        if not account:
            return redirect(url_for("login"))

        cursor.execute(
            """
            SELECT resort_id, resort_name, address, status
            FROM resorts
            WHERE owner_id = %s
            ORDER BY resort_name
            """,
            (session.get("owner_id"),),
        )
        owner_resorts = cursor.fetchall()

        cursor.execute(
            """
            SELECT title, message, type, is_read, created_at
            FROM notifications
            WHERE account_id = %s
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (account_id,),
        )
        notifications = cursor.fetchall()

        cursor.execute(
            """
            SELECT a.fullname, a.email, c.status, r.resort_name
            FROM caretakers c
            JOIN accounts a ON a.account_id = c.account_id
            JOIN resorts r ON r.resort_id = c.resort_id
            WHERE r.owner_id = %s
            ORDER BY a.fullname
            """,
            (session.get("owner_id"),),
        )
        team_members = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN p.payment_status = 'Verified' THEN p.amount_paid ELSE 0 END), 0) AS collected,
                COALESCE(SUM(CASE WHEN p.payment_status = 'Pending' THEN p.amount_paid ELSE 0 END), 0) AS pending,
                COUNT(*) AS payment_count
            FROM payments p
            JOIN reservations rv ON rv.reservation_id = p.reservation_id
            JOIN resorts r ON r.resort_id = rv.resort_id
            WHERE r.owner_id = %s
            """,
            (session.get("owner_id"),),
        )
        billing = cursor.fetchone()

        return render_template(
            "admin/sidebar/setting.html",
            account=account,
            owner_resorts=owner_resorts,
            notifications=notifications,
            team_members=team_members,
            billing=billing,
            username=account["fullname"],
        )
    finally:
        cursor.close()
        conn.close()
