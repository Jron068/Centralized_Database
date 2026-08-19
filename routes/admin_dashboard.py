from flask import render_template, session, redirect, url_for
from app import app
from config import get_connection
from models.decorators import role_required

@app.route("/admin_dashboard", endpoint="admin_dashboard")
@app.route("/owner-dashboard", endpoint="owner_dashboard")
@role_required("owner")
def admin_dashboard():
    owner_id = session.get("owner_id")

    if not owner_id:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Only resorts belonging to THIS owner
        cursor.execute(
            """
            SELECT resort_id, resort_name, status
            FROM resorts
            WHERE owner_id = %s
            ORDER BY resort_name ASC
            """,
            (owner_id,)
        )
        my_resorts = cursor.fetchall()

        # Only pending caretakers applying to THIS owner's resorts
        cursor.execute(
            """
            SELECT a.account_id, a.fullname, a.email, a.created_at,
                   c.resort_id, r.resort_name
            FROM accounts a
            JOIN caretakers c ON c.account_id = a.account_id
            JOIN resorts r ON r.resort_id = c.resort_id
            WHERE a.role = 'caretaker'
              AND a.approval_status = 'Pending'
              AND r.owner_id = %s
            ORDER BY a.created_at ASC
            """,
            (owner_id,)
        )
        pending_caretakers = cursor.fetchall()

        return render_template(
            "admin/admin.html",
            username=session.get("fullname"),
            resorts=my_resorts,
            pending_caretakers=pending_caretakers
        )
    finally:
        cursor.close()
        conn.close()