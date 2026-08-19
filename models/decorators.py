from functools import wraps
from flask import session, redirect, url_for, flash

def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            role = session.get("role")
            if not role or role not in allowed_roles:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return wrapped
    return decorator