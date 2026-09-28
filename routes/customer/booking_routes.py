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

# Common add-on rates. Keep these the same as the constants in the page
# (EXTRA_PAX_PRICE, LPG_PRICE, WATER_PRICE).
EXTRA_PAX_RATE = Decimal('200.00')     # per head beyond the resort's included pax
MINERAL_WATER_RATE = Decimal('50.00')  # per bottle/unit
GAS_STOVE_RATE = Decimal('150.00')     # LPG, flat
MAX_GUESTS = 100                       # sanity limit only

# Fixed price and included pax for each resort, keyed by resort_id.
# VERIFY these ids match your resorts table. Better long term: store
# `price` and `max_pax` columns on the resorts table and read them from there.
RESORT_RATES = {
    1: {'price': Decimal('1100.00'), 'max_pax': 12},  # Triple Z
    2: {'price': Decimal('1300.00'), 'max_pax': 18},  # Sunscape
    3: {'price': Decimal('1200.00'), 'max_pax': 15},  # Lucky Miels
    4: {'price': Decimal('1500.00'), 'max_pax': 20},  # Magic Kingdom
    5: {'price': Decimal('1500.00'), 'max_pax': 15},  # Gallely
    6: {'price': Decimal('1200.00'), 'max_pax': 15},
}

# Tour packages do not change the fixed price.
TOUR_TYPES = {'day', 'night', '22_hour'}


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
        # The mineral water field is now a quantity, not true/false.
        water_qty = int(request.form.get('mineral_water', '0') or 0)
    except (TypeError, ValueError, InvalidOperation):
        return jsonify({"success": False, "message": "Please provide valid booking details."}), 400

    guest_name = request.form.get('guest_name', '').strip()
    guest_phone = request.form.get('guest_phone', '').strip()
    gas_stove = request.form.get('gas_stove', 'false').lower() == 'true'
    # The page sends this field as "package"; "tour_type" is also accepted.
    tour_type = (request.form.get('tour_type') or request.form.get('package') or '').strip()

    if not guest_name or not guest_phone or not (1 <= guests <= MAX_GUESTS):
        return jsonify({"success": False, "message": "Please complete all booking details."}), 400
    if water_qty < 0 or water_qty > 500:
        return jsonify({"success": False, "message": "Invalid mineral water quantity."}), 400
    if tour_type not in TOUR_TYPES:
        return jsonify({"success": False, "message": "Select a valid tour package."}), 400
    if resort_id not in RESORT_RATES:
        return jsonify({"success": False, "message": "This resort does not have a price set yet."}), 400
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

        cursor.execute(
            "SELECT role, is_verified, account_status FROM accounts WHERE account_id = %s",
            (session['account_id'],),
        )
        account = cursor.fetchone()
        if not account or account['role'] != 'customer' or not account['is_verified'] or account['account_status'] != 'Active':
            conn.rollback()
            return jsonify({"success": False, "message": "Please log in with an active, verified customer account to book."}), 403

        # Total = fixed resort price + extra pax + LPG + mineral water.
        # Always computed on the server; the browser total is never trusted.
        rate = RESORT_RATES[resort_id]
        extra_pax = max(0, guests - rate['max_pax'])
        total_amount = (rate['price']
                        + EXTRA_PAX_RATE * extra_pax
                        + (GAS_STOVE_RATE if gas_stove else Decimal('0.00'))
                        + MINERAL_WATER_RATE * water_qty)

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
            "reservation_id": reservation_id,
            "total_amount": str(total_amount)
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