from flask import render_template
from app import app
from config import get_connection




@app.route("/")
def index():
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT resort_name, address, description, email, phone, logo,
                       amenities, price, max_pax
                FROM resorts
                WHERE status = 'Active'
                ORDER BY resort_name
            """)
            resorts = cursor.fetchall()
        finally:
            cursor.close()
    finally:
        connection.close()

    return render_template("index.html", resorts=resorts)

@app.route('/statics_page/about')
def about():
    return render_template('statics_page/about.html')

@app.route('/howitworks')
def howitworks():
    return render_template('statics_page/howitworks.html')

@app.route('/contact')
def contact():  
    return render_template('statics_page/contact.html')

@app.route('/landing_resortpage')
def landing_resortpage():
    return render_template('LandingPage/landing_resortpage.html')