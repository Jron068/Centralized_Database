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
