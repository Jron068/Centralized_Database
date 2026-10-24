from flask import flash, redirect, render_template, request, session, url_for

from app import app
from config import get_connection
from models.customer_support import ensure_customer_support_messages_table
from models.decorators import role_required


MAX_SUPPORT_MESSAGE_LENGTH = 2000


def _owner_identity(cursor):
    cursor.execute(
        "SELECT owner_id FROM owners WHERE account_id = %s",
        (session.get("account_id"),),
    )
    owner = cursor.fetchone()
    return owner["owner_id"] if owner else None


@app.route("/owner/support")
@role_required("owner")
def owner_support():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        owner_id = _owner_identity(cursor)
        if not owner_id:
            return redirect(url_for("login"))

        account_id = session["account_id"]
        ensure_customer_support_messages_table(cursor)
        conn.commit()
        cursor.execute(
            """
            SELECT m.resort_id, m.sender_account, m.receiver_account, m.message,
                   m.sent_at, r.resort_name, customer.account_id AS customer_account_id,
                   customer.fullname AS customer_name,
                   (SELECT COUNT(*)
                    FROM customer_support_messages unread
                    WHERE unread.resort_id = m.resort_id
                      AND unread.sender_account = customer.account_id
                      AND unread.receiver_account = %s
                      AND unread.is_read = 0) AS unread_count
            FROM customer_support_messages m
            JOIN resorts r ON r.resort_id = m.resort_id
            JOIN accounts customer
              ON customer.account_id = CASE
                    WHEN m.sender_account = %s THEN m.receiver_account
                    ELSE m.sender_account
                 END
            WHERE r.owner_id = %s
              AND (m.sender_account = %s OR m.receiver_account = %s)
              AND m.support_message_id = (
                    SELECT MAX(latest.support_message_id)
                    FROM customer_support_messages latest
                    WHERE latest.resort_id = m.resort_id
                      AND LEAST(latest.sender_account, latest.receiver_account)
                          = LEAST(m.sender_account, m.receiver_account)
                      AND GREATEST(latest.sender_account, latest.receiver_account)
                          = GREATEST(m.sender_account, m.receiver_account)
              )
            ORDER BY m.sent_at DESC, m.support_message_id DESC
            """,
            (account_id, account_id, owner_id, account_id, account_id),
        )
        conversations = cursor.fetchall()
        return render_template(
            "admin/support.html",
            username=session.get("fullname", "Owner"),
            conversations=conversations,
            messages=[],
            selected_resort=None,
            customer=None,
            max_message_length=MAX_SUPPORT_MESSAGE_LENGTH,
        )
    finally:
        cursor.close()
        conn.close()


@app.route("/owner/support/<int:resort_id>/<int:customer_account_id>", methods=["GET", "POST"])
@role_required("owner")
def owner_support_thread(resort_id, customer_account_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        owner_id = _owner_identity(cursor)
        if not owner_id:
            return redirect(url_for("login"))

        account_id = session["account_id"]
        ensure_customer_support_messages_table(cursor)
        cursor.execute(
            """
            SELECT r.resort_id, r.resort_name
            FROM resorts r
            WHERE r.resort_id = %s AND r.owner_id = %s
            """,
            (resort_id, owner_id),
        )
        selected_resort = cursor.fetchone()
        cursor.execute(
            """
            SELECT a.account_id, a.fullname
            FROM accounts a
            JOIN customers c ON c.account_id = a.account_id
            WHERE a.account_id = %s
            """,
            (customer_account_id,),
        )
        customer = cursor.fetchone()
        if not selected_resort or not customer:
            flash("That support conversation is not available.", "warning")
            return redirect(url_for("owner_support"))

        cursor.execute(
            """
            SELECT 1
            FROM customer_support_messages
            WHERE resort_id = %s
              AND (
                (sender_account = %s AND receiver_account = %s)
                OR (sender_account = %s AND receiver_account = %s)
              )
            LIMIT 1
            """,
            (resort_id, customer_account_id, account_id, account_id, customer_account_id),
        )
        if not cursor.fetchone():
            flash("That support conversation is not available.", "warning")
            return redirect(url_for("owner_support"))

        if request.method == "POST":
            message = request.form.get("message", "").strip()
            if not message:
                flash("Enter a reply before sending.", "warning")
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
                    (resort_id, account_id, customer_account_id, message),
                )
                conn.commit()
                flash("Your reply was sent.", "success")
            return redirect(
                url_for(
                    "owner_support_thread",
                    resort_id=resort_id,
                    customer_account_id=customer_account_id,
                )
            )

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
            (resort_id, customer_account_id, account_id, account_id, customer_account_id),
        )
        messages = cursor.fetchall()
        cursor.execute(
            """
            UPDATE customer_support_messages
            SET is_read = 1
            WHERE resort_id = %s AND sender_account = %s
              AND receiver_account = %s AND is_read = 0
            """,
            (resort_id, customer_account_id, account_id),
        )
        conn.commit()
        return render_template(
            "admin/support.html",
            username=session.get("fullname", "Owner"),
            conversations=[],
            messages=messages,
            selected_resort=selected_resort,
            customer=customer,
            max_message_length=MAX_SUPPORT_MESSAGE_LENGTH,
        )
    finally:
        cursor.close()
        conn.close()
