from functools import wraps
from flask import session, redirect, flash


def role_required(required_role):

    def decorator(func):

        @wraps(func)
        def wrapper(*args, **kwargs):

            if "role" not in session:

                flash("Please login first.")

                return redirect("/login")


            if session["role"] != required_role:

                flash("Access denied.")

                return redirect("/")


            return func(*args, **kwargs)

        return wrapper

    return decorator