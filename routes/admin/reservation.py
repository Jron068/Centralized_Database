import calendar as calendar_lib
from datetime import date, timedelta

from flask import render_template, request, redirect, url_for, session, flash, jsonify
from app import app
from config import get_connection
from models.decorators import role_required
from models.notifications import notify_resort_caretakers
from models.reservation_reminders import create_upcoming_reservation_reminders
from routes.caretaker import _walkin_schema


def _reservation_rows(cursor, selected_resort=None):
    schema = _walkin_schema(cursor)
    resort_filter = " AND res.resort_id = %s" if selected_resort else ""
    params = [selected_resort] if selected_resort else []
    cursor.execute(
        f"""
        SELECT r.reservation_id,
               COALESCE(NULLIF(r.guest_name, ''), a.fullname, 'Walk-in Guest') AS guest_name,
               res.resort_name, res.resort_id, r.check_in, r.check_out, r.guests,
               r.total_amount, r.reservation_status, p.payment_status, r.created_at,
               CASE WHEN {schema['walkin_expr']} THEN 'Walk-in' ELSE 'Online' END AS booking_source
        FROM reservations r
        LEFT JOIN customers c ON r.customer_id = c.customer_id
        LEFT JOIN accounts a ON c.account_id = a.account_id
        JOIN resorts res ON r.resort_id = res.resort_id
        LEFT JOIN payments p ON p.payment_id = (
            SELECT p2.payment_id FROM payments p2
            WHERE p2.reservation_id = r.reservation_id
            ORDER BY p2.payment_id DESC LIMIT 1
        )
        WHERE 1 = 1{resort_filter}
        ORDER BY r.created_at DESC, r.reservation_id DESC
        """,
        tuple(params),
    )
    return cursor.fetchall()


@app.route("/reservation")
@role_required("owner")
def reservation():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        create_upcoming_reservation_reminders(cursor)
        connection.commit()
        cursor.execute(
            "SELECT resort_id, resort_name FROM resorts ORDER BY resort_name",
        )
        resorts = cursor.fetchall()
        resort_ids = {r["resort_id"] for r in resorts}
        selected_resort = request.args.get("resort_id", type=int)
        if selected_resort not in resort_ids:
            selected_resort = None

        today = date.today()
        try:
            year = int(request.args.get("year", today.year))
            month = int(request.args.get("month", today.month))
            selected_month = date(year, month, 1)
        except (TypeError, ValueError):
            selected_month = date(today.year, today.month, 1)
        month_start = selected_month
        month_end = date(
            selected_month.year, selected_month.month,
            calendar_lib.monthrange(selected_month.year, selected_month.month)[1],
        )

        resort_filter = " AND res.resort_id = %s" if selected_resort else ""
        params = [selected_resort] if selected_resort else []
        reservations = _reservation_rows(cursor, selected_resort)

        cursor.execute(
            f"""
            SELECT r.reservation_id, r.check_in, r.check_out, r.reservation_status,
                   res.resort_id, res.resort_name,
                   COALESCE(NULLIF(r.guest_name, ''), a.fullname, 'Walk-in Guest') AS guest_name,
                   CASE WHEN {_walkin_schema(cursor)['walkin_expr']} THEN 'Walk-in' ELSE 'Online' END AS booking_source
            FROM reservations r
            LEFT JOIN customers c ON c.customer_id = r.customer_id
            LEFT JOIN accounts a ON a.account_id = c.account_id
            JOIN resorts res ON res.resort_id = r.resort_id
            LEFT JOIN payments p ON p.payment_id = (
                SELECT p2.payment_id FROM payments p2
                WHERE p2.reservation_id = r.reservation_id
                ORDER BY p2.payment_id DESC LIMIT 1
            )
            WHERE 1 = 1{resort_filter}
              AND r.check_in IS NOT NULL AND r.check_out IS NOT NULL
              AND r.check_in <= %s AND r.check_out > %s
              AND r.reservation_status IN ('Pending', 'Confirmed')
            ORDER BY r.check_in, res.resort_name
            """,
            (*params, month_end, month_start),
        )
        calendar_reservations = cursor.fetchall()
        events_by_date = {}
        for booking in calendar_reservations:
            event_day = max(booking["check_in"], month_start)
            final_day = min(booking["check_out"] - timedelta(days=1), month_end)
            while event_day <= final_day:
                events_by_date.setdefault(event_day.isoformat(), []).append(booking)
                event_day += timedelta(days=1)

        first_weekday = calendar_lib.monthrange(selected_month.year, selected_month.month)[0]
        calendar_start = month_start - timedelta(days=(first_weekday + 1) % 7)
        cell_count = ((month_end - calendar_start).days + 1 + 6) // 7 * 7
        calendar_days = [
            {"day": calendar_start + timedelta(days=i),
             "in_month": (calendar_start + timedelta(days=i)).month == selected_month.month}
            for i in range(cell_count)
        ]
        previous_month = selected_month - timedelta(days=1)
        next_month = month_end + timedelta(days=1)
        return render_template(
            "admin/sidebar/reservation.html",
            reservations=reservations,
            resorts=resorts,
            selected_resort=selected_resort,
            calendar_days=calendar_days,
            events_by_date=events_by_date,
            calendar_month=selected_month.strftime("%B %Y"),
            calendar_year=selected_month.year,
            calendar_month_number=selected_month.month,
            previous_month=previous_month,
            next_month=next_month,
            today=today,
            username=session.get("fullname", "Owner"),
        )
    finally:
        cursor.close()
        connection.close()


@app.route("/admin/reservations/data")
@role_required("owner")
def reservation_data():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT resort_id FROM resorts")
        resort_ids = {row["resort_id"] for row in cursor.fetchall()}
        selected_resort = request.args.get("resort_id", type=int)
        if selected_resort not in resort_ids:
            selected_resort = None
        rows = _reservation_rows(cursor, selected_resort)
        return jsonify({
            "reservations": [{
                "id": row["reservation_id"],
                "guest": row["guest_name"] or "Walk-in Guest",
                "resort": row["resort_name"],
                "resort_id": row["resort_id"],
                "check_in": row["check_in"].isoformat() if row["check_in"] else "",
                "check_out": row["check_out"].isoformat() if row["check_out"] else "",
                "source": row["booking_source"],
                "status": row["reservation_status"] or "Pending",
                "payment_status": row["payment_status"] or "Pending",
            } for row in rows],
        })
    finally:
        cursor.close()
        conn.close()


@app.route("/admin/reservations/<int:reservation_id>")
@role_required("owner")
def reservation_detail(reservation_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        schema = _walkin_schema(cursor)
        cursor.execute(f"""
            SELECT r.reservation_id, r.check_in, r.check_out, r.guests,
                   r.total_amount, r.reservation_status, r.created_at,
                   COALESCE(NULLIF(r.guest_name, ''), a.fullname, 'Walk-in Guest') AS guest_name,
                   a.email AS guest_email, c.phone AS guest_phone, res.resort_name, res.resort_id,
                   CASE WHEN {schema['walkin_expr']} THEN 'Walk-in' ELSE 'Online' END AS booking_source,
                   {schema['proof_expr']} AS proof_of_payment, p.payment_id, p.amount_paid,
                   p.payment_status, p.payment_date
            FROM reservations r
            LEFT JOIN customers c ON c.customer_id = r.customer_id
            LEFT JOIN accounts a ON a.account_id = c.account_id
            JOIN resorts res ON res.resort_id = r.resort_id
            LEFT JOIN payments p ON p.payment_id = (
                SELECT p2.payment_id FROM payments p2
                WHERE p2.reservation_id = r.reservation_id
                ORDER BY p2.payment_id DESC LIMIT 1
            )
            WHERE r.reservation_id = %s
        """, (reservation_id,))
        reservation = cursor.fetchone()
        if not reservation:
            flash("Reservation not found.", "warning")
            return redirect(url_for("reservation"))
        return render_template("admin/sidebar/reservation_detail.html", reservation=reservation)
    finally:
        cursor.close()
        conn.close()


@app.route("/admin/reservations/<int:reservation_id>/review", methods=["POST"])
@role_required("owner")
def review_reservation(reservation_id):
    action = request.form.get("action")
    if action not in {"approve", "reject"}:
        flash("Invalid review action.", "warning")
        return redirect(url_for("reservation_detail", reservation_id=reservation_id))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        schema = _walkin_schema(cursor)
        cursor.execute(f"""
            SELECT r.reservation_id, r.resort_id, c.account_id, p.payment_id, p.payment_status,
                   res.owner_id, CASE WHEN {schema['walkin_expr']} THEN 'Walk-in' ELSE 'Online' END AS booking_source
            FROM reservations r
            JOIN customers c ON c.customer_id = r.customer_id
            JOIN resorts res ON res.resort_id = r.resort_id
            LEFT JOIN payments p ON p.payment_id = (
                SELECT p2.payment_id FROM payments p2
                WHERE p2.reservation_id = r.reservation_id
                ORDER BY p2.payment_id DESC LIMIT 1
            )
            WHERE r.reservation_id = %s
            FOR UPDATE
        """, (reservation_id,))
        reservation = cursor.fetchone()
        if not reservation:
            flash("Reservation not found.", "warning")
            return redirect(url_for("reservation"))
        if reservation["booking_source"] == "Walk-in":
            flash("Walk-in bookings are reviewed from Walk-in Approvals.", "info")
            return redirect(url_for("admin_walkins"))
        if not reservation["payment_id"] or reservation["payment_status"] != "Pending":
            flash("Only reservations with a pending payment can be reviewed.", "warning")
            return redirect(url_for("reservation_detail", reservation_id=reservation_id))

        approved = action == "approve"
        payment_status = "Verified" if approved else "Rejected"
        reservation_status = "Confirmed" if approved else "Rejected"
        cursor.execute("UPDATE payments SET payment_status = %s WHERE payment_id = %s",
                       (payment_status, reservation["payment_id"]))
        cursor.execute("UPDATE reservations SET reservation_status = %s WHERE reservation_id = %s",
                       (reservation_status, reservation_id))
        title = "Reservation approved" if approved else "Reservation declined"
        message = (f"Your reservation #RSV-{reservation_id} has been approved."
                   if approved else
                   f"Your reservation #RSV-{reservation_id} was declined because the payment could not be verified.")
        cursor.execute("""
            INSERT INTO notifications (account_id, title, message, type)
            VALUES (%s, %s, %s, %s)
        """, (reservation["account_id"], title, message,
              "reservation_approved" if approved else "reservation_rejected"))
        notify_resort_caretakers(
            cursor,
            reservation["resort_id"],
            "Reservation approved by the owner" if approved else "Reservation declined by the owner",
            f"The owner {'approved' if approved else 'declined'} reservation #RSV-{reservation_id}.",
            "reservation_owner_approved" if approved else "reservation_owner_rejected",
        )
        conn.commit()
        flash("Reservation approved and customer notified." if approved else
              "Reservation rejected and customer notified.", "success")
    except Exception:
        conn.rollback()
        flash("The reservation review could not be saved.", "danger")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("reservation_detail", reservation_id=reservation_id))

