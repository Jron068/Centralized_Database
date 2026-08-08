from flask import render_template
from app import app

@app.route("/resorts")
def resorts():
    return render_template("resorts.html")