# routes/admin_dashboard.py
from flask import render_template, session
from app import app
from config import get_connection
from utils.decorators import role_required


@app.route("/admin_dashboard")
@role_required("owner")
def admin_dashboard():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT a.account_id, a.fullname, a.email, a.created_at,
               c.resort_id, r.resort_name
        FROM accounts a
        JOIN caretakers c ON c.account_id = a.account_id
        JOIN resorts r ON r.resort_id = c.resort_id
        WHERE a.role = 'caretaker'
          AND a.approval_status = 'Pending'
        ORDER BY a.created_at ASC
    """)
    pending_caretakers = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "admin_dashboard.html",
        username=session.get("username"),
        pending_caretakers=pending_caretakers
    )