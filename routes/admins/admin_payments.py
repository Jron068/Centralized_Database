from flask import render_template, request, redirect, url_for
from app import app
from config import get_connection


@app.route('/admin/payments')
def admin_payments():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                p.payment_id, p.proof_of_payment, p.reference_number, p.amount_paid,
                p.payment_status, p.payment_date,
                r.reservation_id, r.guest_name, r.guest_phone, r.check_in, r.check_out,
                res.resort_name
            FROM payments p
            JOIN reservations r ON p.reservation_id = r.reservation_id
            JOIN resorts res ON r.resort_id = res.resort_id
            ORDER BY p.payment_date DESC
        """)
        payments = cursor.fetchall()
        return render_template("admin/sidebar/payments.html", payments=payments)
    finally:
        cursor.close()
        conn.close()


@app.route('/admin/payments/verify/<int:payment_id>', methods=['POST'])
def verify_payment(payment_id):
    action = request.form.get('action')
    new_status = 'Verified' if action == 'verify' else 'Rejected'

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "UPDATE payments SET payment_status = %s WHERE payment_id = %s",
            (new_status, payment_id)
        )
        if action == 'verify':
            cursor.execute("""
                UPDATE reservations r
                JOIN payments p ON r.reservation_id = p.reservation_id
                SET r.reservation_status = 'Confirmed'
                WHERE p.payment_id = %s
            """, (payment_id,))
        conn.commit()
        return redirect(url_for('admin_payments'))
    finally:
        cursor.close()
        conn.close()