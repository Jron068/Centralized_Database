from flask import render_template, session, redirect, url_for
from app import app
from config import get_connection
from models.decorators import role_required
from datetime import date, timedelta

@app.route("/admin_dashboard", endpoint="admin_dashboard")
@app.route("/owner-dashboard", endpoint="owner_dashboard")
@app.route("/dashboard", endpoint="dashboard")
@role_required("owner")
def admin_dashboard():
    owner_id = session.get("owner_id")

    if not owner_id:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Only resorts belonging to THIS owner
        cursor.execute(
            """
            SELECT resort_id, resort_name, status
            FROM resorts
            WHERE owner_id = %s
            ORDER BY resort_name ASC
            """,
            (owner_id,)
        )
        my_resorts = cursor.fetchall()
        resort_ids = [r["resort_id"] for r in my_resorts]

        # Only pending caretakers applying to THIS owner's resorts
        cursor.execute(
            """
            SELECT a.account_id, a.fullname, a.email, a.created_at,
                   c.resort_id, r.resort_name
            FROM accounts a
            JOIN caretakers c ON c.account_id = a.account_id
            JOIN resorts r ON r.resort_id = c.resort_id
            WHERE a.role = 'caretaker'
              AND a.approval_status = 'Pending'
              AND r.owner_id = %s
            ORDER BY a.created_at ASC
            """,
            (owner_id,)
        )
        pending_caretakers = cursor.fetchall()

        # Defaults if this owner has no resorts yet
        total_bookings = 0
        total_revenue = "0.00"
        pending_payment = 0
        revenue_labels, revenue_values = [], []
        source_labels, source_values = [], []
        occupancy_labels, occupancy_values = [], []
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

            # Occupancy Rate (last 8 days)
            cursor.execute(
                f"SELECT COUNT(*) AS total_rooms FROM rooms WHERE resort_id IN ({placeholders})",
                resort_ids
            )
            total_rooms = cursor.fetchone()["total_rooms"] or 0

            if total_rooms > 0:
                cursor.execute(
                    f"""
                    SELECT check_in, check_out FROM reservations
                    WHERE resort_id IN ({placeholders})
                      AND reservation_status IN ('Confirmed','Completed')
                      AND check_out >= (CURDATE() - INTERVAL 8 DAY)
                    """,
                    resort_ids
                )
                stays = cursor.fetchall()
                today = date.today()
                for i in range(7, -1, -1):
                    day = today - timedelta(days=i)
                    occupied = sum(1 for s in stays if s["check_in"] <= day < s["check_out"])
                    occupancy_labels.append(day.strftime("%b %d"))
                    occupancy_values.append(round((occupied / total_rooms) * 100, 1))

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
                LIMIT 5
                """,
                resort_ids
            )
            top_properties = cursor.fetchall()

        return render_template(
            "admin/admin.html",
            username=session.get("fullname"),
            resorts=my_resorts,
            pending_caretakers=pending_caretakers,
            total_bookings=total_bookings,
            total_revenue=total_revenue,
            pending_payment=pending_payment,
            revenue_labels=revenue_labels,
            revenue_values=revenue_values,
            source_labels=source_labels,
            source_values=source_values,
            occupancy_labels=occupancy_labels,
            occupancy_values=occupancy_values,
            top_properties=top_properties,
        )
    finally:
        cursor.close()
        conn.close()


#this is route for NAVBAR

@app.route("/booking")
def booking():
    return render_template("admin/navbar/booking.html")

@app.route("/properties")
def properties():
    return render_template("admin/navbar/properties.html")

@app.route("/reports")
def reports():
    return render_template("admin/navbar/reports.html")

@app.route("/reservation")
def reservation():
    return render_template("admin/sidebar/reservation.html")


#this is route for SIDEBARS

@app.route("/calendar")
def calendar():
    return render_template("admin/sidebar/calendar.html")

@app.route("/payment")
def payment():
    return render_template("admin/sidebar/payment.html")

@app.route("/guests")
def guests():
    return render_template("admin/sidebar/guestStay.html")

@app.route("/reviews")
def reviews():  
    return render_template("admin/sidebar/Reviews.html")

@app.route("/settings")
def settings(): 
    return render_template("admin/sidebar/setting.html")