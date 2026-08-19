from flask import render_template
from app import app

@app.route("/resorts")
def resorts():
    return render_template("customer/resorts.html")

@app.route('/LuckyMielsResort')
def LuckyMielsResort():
    return render_template('resorts/LuckyMielsResort.html')

@app.route('/SunscapeResort')
def SunscapeResort():
    return render_template('resorts/SunscapeResort.html')

@app.route('/TripleZResort')
def TripleZResort():
    return render_template('resorts/TripleZResort.html')
    return render_template('resorts/LuckyMielsResort.html')

@app.route('/MagicKingdomResort')
def MagicKingdomResort():
    return render_template('resorts/MagicKingdomResort.html')

@app.route('/RenalynsResort')
def RenalynsResort():
    return render_template('resorts/RenalynsResort.html')

@app.route('/GallelysResort')
def GallelysResort():
    return render_template('resorts/GallelysResort.html')