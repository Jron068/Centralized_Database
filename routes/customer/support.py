from flask import flash, redirect, render_template, request, session, url_for

from app import app
from config import get_connection
from models.customer_support import ensure_customer_support_messages_table


SUPPORT_EMAIL = "aronjohncastillo098@gmail.com"
SUPPORT_PHONES = ("09196281147", "09554036106")
MAX_SUPPORT_MESSAGE_LENGTH = 2000


@app.route("/customer_support", methods=["GET", "POST"])
def customer_support():
    if session.get("role") != "customer" or not session.get("account_id"):
        return redirect(url_for("login"))

    account_id = session["account_id"]
    selected_resort_id = request.values.get("resort_id", "").strip()
    try:
        selected_resort_id = int(selected_resort_id) if selected_resort_id else None
    except ValueError:
        selected_resort_id = None

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        ensure_customer_support_messages_table(cursor)
        conn.commit()
        cursor.execute(
            """
            SELECT r.resort_id, r.resort_name, r.status, a.account_id AS owner_account_id,
                   a.fullname AS owner_name
            FROM resorts r
            JOIN owners o ON o.owner_id = r.owner_id
            JOIN accounts a ON a.account_id = o.account_id
            WHERE a.account_status = 'Active'
              AND (r.status = 'Active' OR EXISTS (
                  SELECT 1 FROM customer_support_messages sm
                  WHERE sm.resort_id = r.resort_id
                    AND (sm.sender_account = %s OR sm.receiver_account = %s)
              ))
            ORDER BY r.resort_name
            """,
            (account_id, account_id),
        )
        resorts = cursor.fetchall()
        selected_resort = next(
            (resort for resort in resorts if resort["resort_id"] == selected_resort_id),
            None,
        )

        if request.method == "POST":
            message = request.form.get("message", "").strip()
            if not selected_resort:
                flash("Choose a resort before contacting its support team.", "warning")
            elif not message:
                flash("Enter a message before sending.", "warning")
            elif len(message) > MAX_SUPPORT_MESSAGE_LENGTH:
                flash(
                    f"Messages must be {MAX_SUPPORT_MESSAGE_LENGTH} characters or fewer.",
                    "warning",
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO customer_support_messages
                        (resort_id, sender_account, receiver_account, message)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        selected_resort["resort_id"],
                        account_id,
                        selected_resort["owner_account_id"],
                        message,
                    ),
                )
                conn.commit()
                flash("Your message was sent to the resort owner.", "success")
            return redirect(
                url_for("customer_support", resort_id=selected_resort_id)
                if selected_resort_id
                else url_for("customer_support")
            )

        conversation = []
        if selected_resort:
            cursor.execute(
                """
                SELECT support_message_id, sender_account, message, sent_at
                FROM customer_support_messages
                WHERE resort_id = %s
                  AND (
                    (sender_account = %s AND receiver_account = %s)
                    OR (sender_account = %s AND receiver_account = %s)
                  )
                ORDER BY sent_at ASC, support_message_id ASC
                """,
                (
                    selected_resort["resort_id"],
                    account_id,
                    selected_resort["owner_account_id"],
                    selected_resort["owner_account_id"],
                    account_id,
                ),
            )
            conversation = cursor.fetchall()
            cursor.execute(
                """
                UPDATE customer_support_messages
                SET is_read = 1
                WHERE resort_id = %s AND sender_account = %s
                  AND receiver_account = %s AND is_read = 0
                """,
                (selected_resort["resort_id"], selected_resort["owner_account_id"], account_id),
            )
            conn.commit()

        return render_template(
            "customer/customer_support.html",
            username=session.get("fullname", "Guest"),
            resorts=resorts,
            selected_resort=selected_resort,
            conversation=conversation,
            support_email=SUPPORT_EMAIL,
            support_phones=SUPPORT_PHONES,
            max_message_length=MAX_SUPPORT_MESSAGE_LENGTH,
        )
    finally:
        cursor.close()
        conn.close()
