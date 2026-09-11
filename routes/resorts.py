from config import get_connection
from flask import jsonify, render_template, session
from app import app

@app.route("/resorts")
def resorts():

    fullname = session.get("fullname", "Guest")
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    
    cursor.execute("""
            SELECT
                resort_id,
                resort_name,
                address,
                description,
                email,
                phone,
                logo,
                amenities,status
                FROM resorts WHERE status = 'Active' ORDER BY resort_name
                   """)
    
    resort_rows = cursor.fetchall()
    cursor.close()
    connection.close()
    
    return render_template(
        "customer/resorts.html", username=fullname, resort_rows=resort_rows
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
    return render_template('resorts/RenalynsResort.html')

@app.route('/GallelysResort')
def GallelysResort():
    return render_template('resorts/GallelysResort.html')