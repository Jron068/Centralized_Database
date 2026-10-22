"""Shared helpers for account notifications."""


def notify_resort_caretakers(cursor, resort_id, title, message, notification_type):
    """Queue a notification for every active caretaker assigned to this resort."""
    cursor.execute(
        """
        INSERT INTO notifications (account_id, title, message, type)
        SELECT c.account_id, %s, %s, %s
        FROM caretakers c
        WHERE c.resort_id = %s AND c.status = 'Active'
        """,
        (title, message, notification_type, resort_id),
    )
