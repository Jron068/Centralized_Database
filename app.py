import os
import secrets
import sys
from flask import Flask, render_template, session
from flask_mail import Mail
from dotenv import load_dotenv
from config import DatabaseError, MySQLDatabaseError

load_dotenv()


app = Flask(__name__)

# Set FLASK_SECRET_KEY in .env to keep sessions valid after restarts.
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024


# ============================
# FLASK MAIL CONFIGURATION (Gmail only: used to send the verification code)
# ============================

app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "1") == "1"
app.config["MAIL_USERNAME"] = (os.getenv("MAIL_USERNAME") or "").strip()
# Google displays App Passwords in groups; remove spaces before SMTP login.
app.config["MAIL_PASSWORD"] = (os.getenv("MAIL_PASSWORD") or "").replace(" ", "").strip()
app.config["MAIL_DEFAULT_SENDER"] = (
    os.getenv("MAIL_DEFAULT_SENDER") or app.config["MAIL_USERNAME"]
).strip()


mail = Mail(app)


@app.before_request
def clear_messages_from_old_sessions():
    """Clear one-time flash messages saved before the email OTP change."""
    if session.get("_flash_messages_version") != 2:
        session.pop("_flashes", None)
        session["_flash_messages_version"] = 2


@app.errorhandler(DatabaseError)
@app.errorhandler(MySQLDatabaseError)
def database_error(error):
    app.logger.error("Database request failed: %s", error)
    return render_template("errors/database_error.html"), 503

# Route modules import `app` by name. When started with `python app.py`,
# reuse this module so they register routes on the same Flask instance.
if __name__ == "__main__":
    sys.modules["app"] = sys.modules[__name__]



# ============================
# ROUTES
# ============================

import routes.public.home
import routes.public.resorts
import routes.auth.registration
import routes.auth.otp
import routes.auth.login
import routes.customer.dashboard
import routes.customer.booking_routes
import routes.admin.admin_dashboard
import routes.admin.admin_payments
import routes.caretaker
import routes.admin.reservation
import routes.admin.property_manager



if __name__ == "__main__":
    if not any(rule.rule == "/" for rule in app.url_map.iter_rules()):
        raise RuntimeError("The home route was not registered.")
    app.run(
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
        port=int(os.getenv("PORT", "5001")),
    )
