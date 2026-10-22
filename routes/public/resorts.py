from config import get_connection
from flask import jsonify, render_template, request, session
from app import app
from models.resort import enrich_resorts, gallery_photos
from models.resort_photos import get_resort_photos
from models.customer_favorites import ensure_customer_favorites_table

@app.route("/resorts")
def resorts():

    fullname = session.get("fullname", "Guest")
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute(f"""
            SELECT
                resort_id,
                resort_name,
                address,
                description,
                email,
                phone,
                logo,
                amenities,status
                     FROM resorts
                     WHERE status = 'Active'
                     ORDER BY resort_name
                         """)
    
    resort_rows = enrich_resorts(cursor.fetchall())
    photos_by_resort = get_resort_photos(cursor, [r["resort_id"] for r in resort_rows])
    for resort in resort_rows:
        resort["photos"] = [
            {"url": photo_url}
            for photo_url in gallery_photos(
                resort, photos_by_resort.get(resort["resort_id"], [])
            )
        ]
    favorite_resort_ids = []
    if session.get("role") == "customer" and session.get("account_id"):
        ensure_customer_favorites_table(cursor)
        cursor.execute(
            "SELECT resort_id FROM customer_favorites WHERE account_id = %s",
            (session["account_id"],),
        )
        favorite_resort_ids = [row["resort_id"] for row in cursor.fetchall()]
    cursor.close()
    connection.close()
    
    return render_template(
        "customer/resorts.html", username=fullname, resort_rows=resort_rows,
        favorite_resort_ids=favorite_resort_ids,
        search_query=request.args.get("q", "").strip()
    )


@app.route("/resort_reviews/<int:resort_id>", methods=["GET", "POST"])
def resort_reviews(resort_id):
    """List reviews and accept one review from a customer with a completed stay."""
    account_id = session.get("account_id") if session.get("role") == "customer" else None
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT resort_id FROM resorts WHERE resort_id = %s AND status = 'Active'", (resort_id,))
        if not cursor.fetchone():
            return jsonify({"ok": False, "message": "Resort not found."}), 404

        customer_id = None
        can_review = False
        already_reviewed = False
        if account_id:
            cursor.execute("SELECT customer_id FROM customers WHERE account_id = %s", (account_id,))
            customer = cursor.fetchone()
            if customer:
                customer_id = customer["customer_id"]
                cursor.execute("""
                    SELECT 1 FROM reservations
                    WHERE customer_id = %s AND resort_id = %s
                      AND reservation_status IN ('Completed', 'Confirmed')
                      AND check_out <= CURRENT_DATE
                    LIMIT 1
                """, (customer_id, resort_id))
                can_review = cursor.fetchone() is not None
                cursor.execute("SELECT 1 FROM reviews WHERE customer_id = %s AND resort_id = %s LIMIT 1", (customer_id, resort_id))
                already_reviewed = cursor.fetchone() is not None

        if request.method == "POST":
            if not account_id or not customer_id:
                return jsonify({"ok": False, "message": "Log in with a customer account to write a review."}), 401
            if not can_review:
                return jsonify({"ok": False, "message": "You can review this resort after your confirmed stay is complete."}), 403
            if already_reviewed:
                return jsonify({"ok": False, "message": "You have already reviewed this resort."}), 409

            payload = request.get_json(silent=True) or {}
            try:
                rating = int(payload.get("rating", 0))
            except (TypeError, ValueError):
                rating = 0
            raw_comment = payload.get("comment", "")
            comment = raw_comment.strip() if isinstance(raw_comment, str) else ""
            if rating < 1 or rating > 5 or not comment or len(comment) > 2000:
                return jsonify({"ok": False, "message": "Choose 1–5 stars and write a comment (up to 2,000 characters)."}), 400
            cursor.execute("""
                INSERT INTO reviews (customer_id, resort_id, rating, comment)
                VALUES (%s, %s, %s, %s)
            """, (customer_id, resort_id, rating, comment))
            connection.commit()
            already_reviewed = True

        cursor.execute("""
            SELECT rv.rating, rv.comment, rv.review_date, a.fullname AS customer_name
            FROM reviews rv
            JOIN customers c ON c.customer_id = rv.customer_id
            JOIN accounts a ON a.account_id = c.account_id
            WHERE rv.resort_id = %s
              AND EXISTS (
                  SELECT 1 FROM reservations r
                  WHERE r.customer_id = rv.customer_id AND r.resort_id = rv.resort_id
                    AND r.reservation_status IN ('Completed', 'Confirmed')
                    AND r.check_out <= CURRENT_DATE
              )
            ORDER BY rv.review_date DESC, rv.review_id DESC
        """, (resort_id,))
        reviews = cursor.fetchall()
        ratings = [int(row["rating"] or 0) for row in reviews if row["rating"] is not None]
        count = len(ratings)
        average = round(sum(ratings) / count, 1) if count else 0
        distribution = [sum(1 for value in ratings if value == star) for star in range(5, 0, -1)]
        return jsonify({
            "ok": True,
            "average": average,
            "count": count,
            "distribution": distribution,
            "can_review": can_review and not already_reviewed,
            "reviews": [{
                "name": row["customer_name"] or "Guest",
                "rating": int(row["rating"] or 0),
                "comment": row["comment"] or "",
                "date": row["review_date"].strftime("%b %d, %Y") if row["review_date"] else "",
            } for row in reviews],
        })
    except Exception:
        connection.rollback()
        app.logger.exception("Could not load or save resort reviews")
        return jsonify({"ok": False, "message": "Reviews are temporarily unavailable."}), 500
    finally:
        cursor.close()
        connection.close()

@app.route('/LuckyMielsResort')
def LuckyMielsResort():
    return render_template('resorts/LuckyMielsResort.html')

@app.route('/SunscapeResort')
def SunscapeResort():
    return render_template('resorts/SunscapeResort.html')

@app.route('/TripleZResort')
def TripleZResort():
    return render_template('resorts/TripleZ_Resort.html')

@app.route('/MagicKingdomResort')
def MagicKingdomResort():
    return render_template('resorts/MagicKingdomResort.html')

@app.route('/RenalynsResort')
def RenalynsResort():
    return render_template('resorts/RenalynResort.html')

@app.route('/GallelysResort')
def GallelysResort():
    return render_template('resorts/GallelyResort.html')
