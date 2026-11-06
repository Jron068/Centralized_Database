import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from flask import render_template, request, session, redirect, url_for, jsonify, flash
from werkzeug.utils import secure_filename
from app import app
from config import get_connection
from models.notifications import notify_resort_caretakers
from models.file_storage import upload_file, file_url, delete_uploaded_file

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
TOUR_WINDOWS = {
    'day': (time(8), time(17)),
    'night': (time(19), time(6)),
    '22_hour': (time(14), time(12)),
}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT


# ---------- AVAILABILITY ----------
@app.route('/resort_availability/<int:resort_id>')
def resort_availability(resort_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT resort_id FROM resorts WHERE resort_id = %s AND status = 'Active'",
            (resort_id,),
        )
        if not cursor.fetchone():
            return jsonify({"message": "Resort not found or unavailable."}), 404

        cursor.execute("""
            SELECT check_in, check_out, tour_type, start_at, end_at
            FROM reservations
            WHERE resort_id = %s
              AND check_in IS NOT NULL AND check_out IS NOT NULL
              AND check_out > check_in
              AND reservation_status IN ('Pending', 'Confirmed')
        """, (resort_id,))
        rows = cursor.fetchall()

        booked_dates = []
        bookings = []
        for r in rows:
            start_at, end_at = r.get('start_at'), r.get('end_at')
            if start_at and end_at:
                booked_day = start_at.date()
                while booked_day <= end_at.date():
                    booked_dates.append(booked_day.strftime('%Y-%m-%d'))
                    booked_day += timedelta(days=1)
            else:
                # Legacy date-only bookings reserve the whole date range.
                d = r['check_in']
                while d < r['check_out']:
                    booked_dates.append(d.strftime('%Y-%m-%d'))
                    d += timedelta(days=1)
            bookings.append({
                "start_at": start_at.strftime('%Y-%m-%dT%H:%M:%S') if start_at else None,
                "end_at": end_at.strftime('%Y-%m-%dT%H:%M:%S') if end_at else None,
                "tour_type": r.get('tour_type'),
                "check_in": r['check_in'].strftime('%Y-%m-%d'),
                "check_out": r['check_out'].strftime('%Y-%m-%d'),
            })

        response = jsonify({"booked_dates": booked_dates, "bookings": bookings})
        response.headers["Cache-Control"] = "no-store"
        return response
    finally:
        cursor.close()
        conn.close()


# ---------- CREATE RESERVATION ----------
@app.route('/book_resort', methods=['POST'])
def book_resort():
    if session.get("role") != "customer" or "account_id" not in session:
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

    if not guest_name or not guest_phone or guests < 1:
        return jsonify({"success": False, "message": "Please complete all booking details."}), 400
    if water_qty < 0 or water_qty > 500:
        return jsonify({"success": False, "message": "Invalid mineral water quantity."}), 400
    if tour_type not in TOUR_TYPES:
        return jsonify({"success": False, "message": "Select a valid tour package."}), 400
    if check_out <= check_in:
        return jsonify({"success": False, "message": "Check-out must be after check-in."}), 400
    minimum_check_in = datetime.now().date() + timedelta(days=3)
    if check_in < minimum_check_in:
        return jsonify({
            "success": False,
            "message": f"Reservations must be made at least 3 days in advance. Earliest check-in: {minimum_check_in:%B %d, %Y}."
        }), 400
    start_time, end_time = TOUR_WINDOWS[tour_type]
    start_at = datetime.combine(check_in, start_time)
    expected_check_out = check_in + timedelta(days=1)
    if check_out != expected_check_out:
        return jsonify({"success": False, "message": "Check-out must match the selected tour schedule."}), 400
    end_date = check_in if tour_type == 'day' else check_out
    end_at = datetime.combine(end_date, end_time)
    if end_at <= start_at:
        return jsonify({"success": False, "message": "The selected tour schedule is invalid."}), 400

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
            "SELECT resort_id, price, max_pax FROM resorts WHERE resort_id = %s AND status = 'Active' FOR UPDATE",
            (resort_id,)
        )
        resort = cursor.fetchone()
        if not resort:
            conn.rollback()
            return jsonify({"success": False, "message": "That resort is not available."}), 404

        # Use the same saved price and included guest count shown on the customer listing.
        # Legacy defaults support older rows whose database fields are still empty.
        fallback_rate = RESORT_RATES.get(resort_id)
        saved_price = resort.get("price")
        saved_max_pax = resort.get("max_pax")
        if saved_price is None and not fallback_rate:
            conn.rollback()
            return jsonify({"success": False, "message": "This resort does not have a price set yet."}), 400
        rate = {
            "price": Decimal(str(saved_price if saved_price is not None else fallback_rate["price"])),
            "max_pax": int(saved_max_pax if saved_max_pax is not None else (fallback_rate["max_pax"] if fallback_rate else 15)),
        }
        max_guests = max(MAX_GUESTS, rate["max_pax"])
        if guests > max_guests:
            conn.rollback()
            return jsonify({
                "success": False,
                "message": f"This resort accepts up to {max_guests} guests per reservation."
            }), 400

        cursor.execute(
            "SELECT role, is_verified, account_status FROM accounts WHERE account_id = %s",
            (session['account_id'],),
        )
        account = cursor.fetchone()
        if not account or account['role'] != 'customer' or not account['is_verified'] or account['account_status'] != 'Active':
            conn.rollback()
            return jsonify({"success": False, "message": "Please log in with an active, verified customer account to book."}), 403

        cursor.execute("""
            SELECT reservation_id
            FROM reservations
            WHERE resort_id = %s
              AND reservation_status IN ('Pending', 'Confirmed')
              AND check_in IS NOT NULL AND check_out IS NOT NULL
              AND (
                    (start_at IS NOT NULL AND end_at IS NOT NULL
                     AND start_at < %s AND end_at > %s)
                    OR
                    ((start_at IS NULL OR end_at IS NULL)
                     AND check_in < %s AND check_out > %s)
              )
            LIMIT 1
            FOR UPDATE
        """, (resort_id, end_at, start_at, check_out, check_in))
        if cursor.fetchone():
            conn.rollback()
            return jsonify({"success": False, "message": "Those dates are no longer available. Please choose another stay."}), 409

        # Total = fixed resort price + extra pax + LPG + mineral water.
        # Always computed on the server; the browser total is never trusted.
        extra_pax = max(0, guests - rate['max_pax'])
        total_amount = (rate['price']
                        + EXTRA_PAX_RATE * extra_pax
                        + (GAS_STOVE_RATE if gas_stove else Decimal('0.00'))
                        + MINERAL_WATER_RATE * water_qty)

        cursor.execute("""
            INSERT INTO reservations
                (customer_id, resort_id, check_in, check_out, start_at, end_at, tour_type, guests, total_amount,
                 reservation_status, guest_name, guest_phone, pax, gas_stove, customer_decision)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pending', %s, %s, %s, %s, 'Pending')
        """, (customer_id, resort_id, check_in, check_out, start_at, end_at, tour_type, guests, total_amount,
              guest_name, guest_phone, guests, int(gas_stove)))
        reservation_id = cursor.lastrowid
        notify_resort_caretakers(
            cursor,
            resort_id,
            "New reservation request",
            f"A customer requested {check_in:%b %d, %Y} to {check_out:%b %d, %Y} for reservation #RSV-{reservation_id}. Review it in Guests & Reservations.",
            "reservation_new",
        )
        conn.commit()
        return jsonify({
            "success": True,
            "message": "Reservation submitted successfully!",
            "reservation_id": reservation_id,
            "total_amount": str(total_amount),
            "downpayment_amount": str((total_amount * Decimal('0.10')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
        }), 201
    except Exception:
        conn.rollback()
        app.logger.exception("Reservation could not be created")
        return jsonify({"success": False, "message": "Unable to save the reservation."}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/customer/reservations/<int:reservation_id>/decision", methods=["POST"])
def customer_reservation_decision(reservation_id):
    if session.get("role") != "customer" or "account_id" not in session:
        return redirect(url_for("login"))

    decision = request.form.get("decision")
    if decision not in {"continue", "cancel"}:
        flash("Choose whether you want to continue or cancel this reservation.", "warning")
        return redirect(url_for("customer_reservation"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT r.reservation_id, r.resort_id, r.reservation_status
            FROM reservations r
            JOIN customers c ON c.customer_id = r.customer_id
            WHERE r.reservation_id = %s AND c.account_id = %s
            FOR UPDATE
            """,
            (reservation_id, session["account_id"]),
        )
        reservation = cursor.fetchone()
        if not reservation:
            flash("Reservation not found.", "warning")
            return redirect(url_for("customer_reservation"))
        if reservation["reservation_status"] != "Pending":
            flash("Only pending reservations can be changed here.", "warning")
            return redirect(url_for("customer_reservation"))

        if decision == "cancel":
            cursor.execute(
                """
                UPDATE reservations
                SET customer_decision = 'Cancelled', reservation_status = 'Cancelled'
                WHERE reservation_id = %s
                """,
                (reservation_id,),
            )
            notice_title = "Customer cancelled a reservation"
            notice_message = f"Reservation #RSV-{reservation_id} was cancelled by the customer."
            flash("Your reservation was cancelled. Its dates remain available to other customers.", "success")
        else:
            cursor.execute(
                "UPDATE reservations SET customer_decision = 'Continue' WHERE reservation_id = %s",
                (reservation_id,),
            )
            notice_title = "Customer confirmed a reservation"
            notice_message = f"The customer confirmed they want to continue with reservation #RSV-{reservation_id}."
            flash("Thanks for confirming. The resort can now review your reservation.", "success")

        notify_resort_caretakers(
            cursor, reservation["resort_id"], notice_title, notice_message, "reservation_customer_decision"
        )
        cursor.execute(
            """
            INSERT INTO notifications (account_id, title, message, type)
            SELECT o.account_id, %s, %s, 'reservation_customer_decision'
            FROM resorts res
            JOIN owners o ON o.owner_id = res.owner_id
            WHERE res.resort_id = %s AND o.account_id IS NOT NULL
            """,
            (notice_title, notice_message, reservation["resort_id"]),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        app.logger.exception("Customer reservation decision could not be saved")
        flash("We couldn't save your reservation decision. Please try again.", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("customer_reservation"))


# ---------- PAYMENT PROOF ----------
@app.route('/submit_payment', methods=['POST'])
def submit_payment():
    if session.get("role") != "customer" or "account_id" not in session:
        return jsonify({"success": False, "message": "Please log in to submit payment."}), 401

    proof = request.files.get('proof')
    payer_name = request.form.get('payer_name', '').strip()
    payer_phone = request.form.get('payer_phone', '').strip()
    reference_number = request.form.get('reference_number', '').strip()
    payment_method = request.form.get('payment_method', '').strip()
    try:
        reservation_id = int(request.form.get('reservation_id', ''))
        amount_paid = Decimal(request.form.get('amount_paid', ''))
    except (TypeError, ValueError, InvalidOperation):
        return jsonify({"success": False, "message": "Invalid payment details."}), 400

    if (not payer_name or len(payer_name) > 150
            or not payer_phone or len(payer_phone) > 30
            or not reference_number or len(reference_number) > 100
            or payment_method not in {'GCash', 'Maya', 'MariBank'}
            or not proof or not proof.filename or not allowed_file(proof.filename)
            or not amount_paid.is_finite() or amount_paid <= 0):
        return jsonify({
            "success": False,
            "message": "Enter the sender name, phone number, transaction reference, payment method, and upload a PNG, JPG, JPEG, or WEBP receipt.",
        }), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    proof_path = None
    try:
        cursor.execute("""
            SELECT r.reservation_id, r.reservation_status, r.total_amount
            FROM reservations AS r
            JOIN customers AS c ON c.customer_id = r.customer_id
            WHERE r.reservation_id = %s AND c.account_id = %s
            FOR UPDATE
        """, (reservation_id, session['account_id']))
        reservation = cursor.fetchone()
        if not reservation:
            return jsonify({"success": False, "message": "Reservation not found."}), 404
        if reservation["reservation_status"] != "Pending":
            return jsonify({"success": False, "message": "This reservation is no longer accepting payment proofs."}), 409

        cursor.execute("""
            SELECT COALESCE(SUM(CASE WHEN payment_status = 'Verified' THEN amount_paid ELSE 0 END), 0) AS verified_total,
                   SUM(CASE WHEN payment_status = 'Pending' THEN 1 ELSE 0 END) AS pending_count
            FROM payments
            WHERE reservation_id = %s
        """, (reservation_id,))
        payment_summary = cursor.fetchone()
        if payment_summary["pending_count"]:
            return jsonify({"success": False, "message": "A payment for this reservation is already awaiting review."}), 409

        total_amount = Decimal(str(reservation["total_amount"] or 0)).quantize(Decimal("0.01"))
        verified_total = Decimal(str(payment_summary["verified_total"] or 0)).quantize(Decimal("0.01"))
        downpayment = (total_amount * Decimal("0.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        balance_due = total_amount - verified_total
        allowed_amounts = {balance_due}
        if verified_total == 0:
            allowed_amounts.add(downpayment)
        if amount_paid != amount_paid.quantize(Decimal("0.01")) or amount_paid.quantize(Decimal("0.01")) not in allowed_amounts:
            return jsonify({
                "success": False,
                "message": "Payment must be the 10% downpayment or the remaining balance."
            }), 400

        image_data = proof.stream.read(5 * 1024 * 1024 + 1)
        if len(image_data) > 5 * 1024 * 1024:
            return jsonify({"success": False, "message": "Payment proofs must be 5 MB or smaller."}), 400
        extension = secure_filename(proof.filename).rsplit('.', 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{extension}"
        content_type = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
        }[extension]
        proof_path = upload_file(
            image_data, f"payments/{filename}", private=True, content_type=content_type
        )

        cursor.execute("""
            INSERT INTO payments
                (reservation_id, proof_of_payment, amount_paid, payment_status, payment_date,
                 payer_name, payer_phone, reference_number, payment_method)
            VALUES (%s, %s, %s, 'Pending', NOW(), %s, %s, %s, %s)
        """, (
            reservation_id, proof_path, amount_paid, payer_name,
            payer_phone, reference_number, payment_method,
        ))
        conn.commit()
        return jsonify({"success": True, "message": "Payment proof submitted for review."}), 201
    except Exception:
        conn.rollback()
        app.logger.exception("Payment proof upload failed")
        if proof_path:
            try:
                delete_uploaded_file(proof_path)
            except Exception:
                app.logger.exception("Could not clean up the uploaded payment proof")
        return jsonify({"success": False, "message": "Unable to save the payment proof."}), 500
    finally:
        cursor.close()
        conn.close()
