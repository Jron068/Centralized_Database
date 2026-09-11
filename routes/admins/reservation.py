from flask import render_template, request, redirect, url_for, session, flash
from app import app
from config import get_connection
from models.decorators import role_required


@app.route("/reservation")
@role_required("owner")
def reservation():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        query = """
        SELECT
            r.reservation_id,
            a.fullname AS guest_name,
            res.resort_name,
            r.check_in,
            r.check_out,
            r.guests,
            r.total_amount,
            r.reservation_status,
            p.payment_status,
            r.created_at
        FROM reservations r
        JOIN customers c
            ON r.customer_id = c.customer_id
        JOIN accounts a
            ON c.account_id = a.account_id
        JOIN resorts res
            ON r.resort_id = res.resort_id
        LEFT JOIN payments p
            ON p.payment_id = (
                SELECT p2.payment_id
                FROM payments p2
                WHERE p2.reservation_id = r.reservation_id
                ORDER BY p2.payment_id DESC
                LIMIT 1
            )
        ORDER BY r.created_at DESC
        """
        cursor.execute(query)
        reservations = cursor.fetchall()
        return render_template("admin/sidebar/reservation.html", reservations=reservations)
    finally:
        cursor.close()
        connection.close()


@app.route("/admin/reservations/<int:reservation_id>")
@role_required("owner")
def reservation_detail(reservation_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT r.reservation_id, r.check_in, r.check_out, r.guests,
                   r.total_amount, r.reservation_status, r.created_at,
                   a.fullname AS guest_name, a.email AS guest_email,
                   c.phone AS guest_phone, res.resort_name,
                   p.payment_id, p.proof_of_payment, p.amount_paid,
                   p.payment_status, p.payment_date
            FROM reservations r
            JOIN customers c ON c.customer_id = r.customer_id
            JOIN accounts a ON a.account_id = c.account_id
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
        cursor.execute("""
            SELECT r.reservation_id, c.account_id, p.payment_id, p.payment_status
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

