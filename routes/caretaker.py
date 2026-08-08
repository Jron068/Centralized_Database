# routes/caretaker_approval.py

from flask import redirect, flash, session
from app import app
from config import get_connection
from models.decorators import role_required

import secrets
import string
from werkzeug.security import generate_password_hash


def generate_random_password(length=10):
    alphabet = string.ascii_letters + string.digits
    return "".join(
        secrets.choice(alphabet)
        for _ in range(length)
    )


# ==============================
# APPROVE CARETAKER
# ==============================

@app.route("/approve-caretaker/<int:account_id>")
@role_required("owner")
def approve_caretaker(account_id):

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # Get caretaker information
        cursor.execute("""
            SELECT 
                a.account_id,
                a.fullname,
                a.email,
                a.approval_status,
                c.resort_id,
                r.resort_name

            FROM accounts a

            JOIN caretakers c 
            ON c.account_id = a.account_id

            JOIN resorts r
            ON r.resort_id = c.resort_id

            WHERE a.account_id = %s

        """, (account_id,))


        caretaker = cursor.fetchone()


        if not caretaker:

            flash("Caretaker account not found.", "danger")

            return redirect("/admin_dashboard")



        # Prevent approving twice

        if caretaker["approval_status"] == "Approved":

            flash(
                "Caretaker is already approved.",
                "warning"
            )

            return redirect("/admin_dashboard")



        # Generate temporary password

        raw_password = generate_random_password()



        # Hash password

        hashed_password = generate_password_hash(
            raw_password
        )



        # Update account

        cursor.execute("""

            UPDATE accounts

            SET

                password = %s,

                approval_status = 'Approved',

                is_verified = 1,

                approved_by = %s,

                approved_at = NOW()


            WHERE account_id = %s


        """,
        (
            hashed_password,
            session.get("user_id"),
            account_id
        ))



        connection.commit()



        # ==============================
        # TERMINAL OUTPUT ONLY
        # ==============================

        print("\n==============================")
        print(" CARETAKER ACCOUNT APPROVED ")
        print("==============================")
        print("Name:", caretaker["fullname"])
        print("Resort:", caretaker["resort_name"])
        print("Email:", caretaker["email"])
        print("Temporary Password:", raw_password)
        print("==============================\n")



        flash(
            f"{caretaker['fullname']} approved. "
            "Account credentials generated in terminal.",
            "success"
        )


    except Exception as e:

        connection.rollback()

        print("APPROVE ERROR:", e)

        flash(
            "Something went wrong while approving caretaker.",
            "danger"
        )


    finally:

        cursor.close()
        connection.close()



    return redirect("/admin_dashboard")





# ==============================
# REJECT CARETAKER
# ==============================


@app.route("/reject-caretaker/<int:account_id>")
@role_required("owner")
def reject_caretaker(account_id):

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)


    try:


        cursor.execute("""

            SELECT fullname

            FROM accounts

            WHERE account_id=%s


        """,
        (account_id,))


        caretaker = cursor.fetchone()



        if not caretaker:

            flash(
                "Caretaker account not found.",
                "danger"
            )

            return redirect("/admin_dashboard")



        cursor.execute("""

            UPDATE accounts

            SET

                approval_status='Rejected',

                approved_by=%s,

                approved_at=NOW()


            WHERE account_id=%s


        """,
        (
            session.get("user_id"),
            account_id
        ))



        connection.commit()



        print("\n==============================")
        print(" CARETAKER REJECTED ")
        print("==============================")
        print("Name:", caretaker["fullname"])
        print("==============================\n")



        flash(
            f"{caretaker['fullname']} rejected.",
            "warning"
        )



    except Exception as e:

        connection.rollback()

        print("REJECT ERROR:", e)


        flash(
            "Something went wrong while rejecting caretaker.",
            "danger"
        )



    finally:

        cursor.close()
        connection.close()



    return redirect("/admin_dashboard")