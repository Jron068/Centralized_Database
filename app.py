from flask import Flask
from flask_mail import Mail


app = Flask(__name__)

app.secret_key = "pansol_secret_key"


# ============================
# FLASK MAIL CONFIGURATION
# ============================

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True

app.config['MAIL_USERNAME'] = 'your-email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your-app-password'


mail = Mail(app)



# ============================
# ROUTES
# ============================

from routes.home import *
from routes.registration import *
from routes.otp import *
from routes.login import *
from routes.customer_landingpage import *
from routes.admin import *
from routes.caretaker import *



if __name__ == "__main__":
    app.run(debug=True)