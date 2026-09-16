from datetime import date, datetime, timedelta

from flask import render_template, request, redirect, url_for, session
from app import app
from config import get_connection
from models.decorators import role_required


@app.route('/admin/payments')
@role_required("owner")
def admin_payments():
    month_start = date.today().replace(day=1)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    start_date_text = request.args.get("start_date", month_start.isoformat())
    end_date_text = request.args.get("end_date", (next_month - timedelta(days=1)).isoformat())
    try:
        start_date = datetime.strptime(start_date_text, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date_text, "%Y-%m-%d").date()
        if end_date < start_date:
            raise ValueError
    except ValueError:
        start_date = month_start
        end_date = next_month - timedelta(days=1)
        start_date_text = start_date.isoformat()
        end_date_text = end_date.isoformat()
    end_date_exclusive = end_date + timedelta(days=1)
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                p.payment_id, p.proof_of_payment, p.reference_number, p.amount_paid,
                p.payment_status, p.payment_date,
                r.reservation_id, COALESCE(r.guest_name, a.fullname) AS guest_name,
                r.guest_phone, r.check_in, r.check_out,
                res.resort_name
            FROM payments p
            JOIN reservations r ON p.reservation_id = r.reservation_id
            JOIN customers c ON r.customer_id = c.customer_id
            JOIN accounts a ON c.account_id = a.account_id
            JOIN resorts res ON r.resort_id = res.resort_id
            WHERE p.payment_date >= %s AND p.payment_date < %s
            ORDER BY p.payment_date DESC
        """, (start_date, end_date_exclusive))
        payments = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN p.payment_status = 'Verified' THEN p.amount_paid ELSE 0 END), 0) AS collected,
                COALESCE(SUM(CASE WHEN p.payment_status = 'Pending' THEN p.amount_paid ELSE 0 END), 0) AS pending,
                COUNT(CASE WHEN p.payment_status = 'Pending' THEN 1 END) AS pending_count,
                COALESCE(SUM(CASE WHEN p.payment_status = 'Rejected' THEN p.amount_paid ELSE 0 END), 0) AS rejected,
                COUNT(CASE WHEN p.payment_status = 'Rejected' THEN 1 END) AS rejected_count,
                COUNT(CASE WHEN p.payment_status = 'Verified' THEN 1 END) AS verified_count
            FROM payments p
            JOIN reservations r ON p.reservation_id = r.reservation_id
            JOIN resorts res ON r.resort_id = res.resort_id
                        WHERE p.payment_date >= %s AND p.payment_date < %s
            """,
                        (start_date, end_date_exclusive),
        )
        summary = cursor.fetchone()
        return render_template(
            "admin/sidebar/payment.html",
            payments=payments,
            summary=summary,
            username=session.get("fullname", "Owner"),
            start_date=start_date_text,
            end_date=end_date_text,
        )
    finally:
        cursor.close()
        conn.close()


@app.route('/admin/payments/verify/<int:payment_id>', methods=['POST'])
@role_required("owner")
def verify_payment(payment_id):
    action = request.form.get('action')
    new_status = 'Verified' if action == 'verify' else 'Rejected'

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            UPDATE payments p
            JOIN reservations r ON p.reservation_id = r.reservation_id
            JOIN resorts res ON r.resort_id = res.resort_id
            SET p.payment_status = %s
            WHERE p.payment_id = %s
            """,
            (new_status, payment_id)
        )
        if action == 'verify':
            cursor.execute("""
                UPDATE reservations r
                JOIN payments p ON r.reservation_id = p.reservation_id
                JOIN resorts res ON r.resort_id = res.resort_id
                SET r.reservation_status = 'Confirmed'
                WHERE p.payment_id = %s
            """, (payment_id,))
        conn.commit()
        return redirect(url_for('admin_payments'))
    finally:
        cursor.close()
        conn.close()