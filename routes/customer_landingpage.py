from flask import render_template
from app import app

@app.route("/customer_landingpage")
def customer_landingpage():
    return render_template("customer_landingpage.html")