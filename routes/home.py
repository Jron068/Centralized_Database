from flask import render_template
from app import app

@app.route("/")
def index():
    return render_template("index.html")

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