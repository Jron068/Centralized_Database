import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from flask import render_template, request, session, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from app import app
from config import get_connection

UPLOAD_FOLDER = os.path.join('static', 'uploads', 'payments')
ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'webp'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT


# ---------- AVAILABILITY ----------
@app.route('/resort_availability/<int:resort_id>')
def resort_availability(resort_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT check_in, check_out
            FROM reservations
            WHERE resort_id = %s
              AND reservation_status IN ('Pending', 'Confirmed')
        """, (resort_id,))
        rows = cursor.fetchall()

        booked_dates = []
        for r in rows:
            d = r['check_in']
            while d < r['check_out']:
                booked_dates.append(d.strftime('%Y-%m-%d'))
                d += timedelta(days=1)

        return jsonify({"booked_dates": booked_dates})
    finally:
        cursor.close()
        conn.close()


# ---------- CREATE RESERVATION ----------
@app.route('/book_resort', methods=['POST'])
def book_resort():
    if "account_id" not in session:
        return jsonify({"success": False, "message": "Please log in to book."}), 401

    try:
        resort_id = int(request.form.get('resort_id', ''))
        guests = int(request.form.get('pax', ''))
        check_in = datetime.strptime(request.form.get('check_in', ''), '%Y-%m-%d').date()
        check_out = datetime.strptime(request.form.get('check_out', ''), '%Y-%m-%d').date()
        total_amount = Decimal(request.form.get('total_amount', ''))
    except (TypeError, ValueError, InvalidOperation):
        return jsonify({"success": False, "message": "Please provide valid booking details."}), 400

    guest_name = request.form.get('guest_name', '').strip()
    guest_phone = request.form.get('guest_phone', '').strip()
    gas_stove = request.form.get('gas_stove', 'false').lower() == 'true'
    if not guest_name or not guest_phone or guests < 1 or total_amount < 0:
        return jsonify({"success": False, "message": "Please complete all booking details."}), 400
    if check_out <= check_in:
        return jsonify({"success": False, "message": "Check-out must be after check-in."}), 400
    minimum_check_in = datetime.now().date() + timedelta(days=3)
    if check_in < minimum_check_in:
        return jsonify({
            "success": False,
            "message": f"Reservations must be made at least 3 days in advance. Earliest check-in: {minimum_check_in:%B %d, %Y}."
        }), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT customer_id FROM customers WHERE account_id = %s",
            (session['account_id'],)
        )
        customer = cursor.fetchone()
        if customer:
            customer_id = customer['customer_id']
            cursor.execute(
                "UPDATE customers SET phone = %s WHERE customer_id = %s",
                (guest_phone, customer_id)
            )
        else:
            cursor.execute(
                "INSERT INTO customers (account_id, phone) VALUES (%s, %s)",
                (session['account_id'], guest_phone)
            )
            customer_id = cursor.lastrowid

        cursor.execute(
            "SELECT resort_id FROM resorts WHERE resort_id = %s AND status = 'Active'",
            (resort_id,)
        )
        if not cursor.fetchone():
            conn.rollback()
            return jsonify({"success": False, "message": "That resort is not available."}), 404

        cursor.execute("""
            INSERT INTO reservations
                (customer_id, resort_id, check_in, check_out, guests, total_amount,
                 reservation_status, guest_name, guest_phone, pax, gas_stove)
            VALUES (%s, %s, %s, %s, %s, %s, 'Pending', %s, %s, %s, %s)
        """, (customer_id, resort_id, check_in, check_out, guests, total_amount,
              guest_name, guest_phone, guests, gas_stove))
        reservation_id = cursor.lastrowid
        conn.commit()
        return jsonify({
            "success": True,
            "message": "Reservation submitted successfully!",
            "reservation_id": reservation_id
        }), 201
    except Exception:
        conn.rollback()
        return jsonify({"success": False, "message": "Unable to save the reservation."}), 500
    finally:
        cursor.close()
        conn.close()


# ---------- PAYMENT PROOF ----------
@app.route('/submit_payment', methods=['POST'])
def submit_payment():
    if "account_id" not in session:
        return jsonify({"success": False, "message": "Please log in to submit payment."}), 401

    proof = request.files.get('proof')
    try:
        reservation_id = int(request.form.get('reservation_id', ''))
        amount_paid = Decimal(request.form.get('amount_paid', ''))
    except (TypeError, ValueError, InvalidOperation):
        return jsonify({"success": False, "message": "Invalid payment details."}), 400

    if not proof or not proof.filename or not allowed_file(proof.filename) or amount_paid < 0:
        return jsonify({"success": False, "message": "Upload a PNG, JPG, JPEG, or WEBP payment screenshot."}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT r.reservation_id
            FROM reservations AS r
            JOIN customers AS c ON c.customer_id = r.customer_id
            WHERE r.reservation_id = %s AND c.account_id = %s
        """, (reservation_id, session['account_id']))
        if not cursor.fetchone():
            return jsonify({"success": False, "message": "Reservation not found."}), 404

        extension = secure_filename(proof.filename).rsplit('.', 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{extension}"
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        proof.save(os.path.join(UPLOAD_FOLDER, filename))

        cursor.execute("""
            INSERT INTO payments (reservation_id, proof_of_payment, amount_paid, payment_status, payment_date)
            VALUES (%s, %s, %s, 'Pending', NOW())
        """, (reservation_id, f"uploads/payments/{filename}", amount_paid))
        conn.commit()
        return jsonify({"success": True, "message": "Payment proof submitted for review."}), 201
    except Exception:
        conn.rollback()
        return jsonify({"success": False, "message": "Unable to save the payment proof."}), 500
    finally:
        cursor.close()
        conn.close()
