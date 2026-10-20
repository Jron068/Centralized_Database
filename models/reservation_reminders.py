"""Create one-time owner and caretaker reminders for near-term arrivals."""


def create_upcoming_reservation_reminders(cursor):
    """Queue reminders for active bookings arriving in two or three days.

    This is called when an owner or caretaker opens an operational page. The
    notification row itself is the idempotency record, so refreshing a page
    will not create another reminder for the same recipient and lead time.
    The caller owns the transaction and should commit after this function.
    """
    cursor.execute(
        """
        SELECT r.reservation_id, r.check_in,
               COALESCE(NULLIF(r.guest_name, ''), 'Guest') AS guest_name,
               rs.resort_name, o.account_id AS owner_account_id,
               c.account_id AS caretaker_account_id,
               DATEDIFF(r.check_in, CURDATE()) AS days_before
        FROM reservations r
        JOIN resorts rs ON rs.resort_id = r.resort_id
        JOIN owners o ON o.owner_id = rs.owner_id
        LEFT JOIN caretakers c ON c.resort_id = rs.resort_id AND c.status = 'Active'
        WHERE r.reservation_status IN ('Pending', 'Confirmed')
          AND DATEDIFF(r.check_in, CURDATE()) IN (2, 3)
        ORDER BY r.check_in, r.reservation_id
        """
    )
    arrivals = cursor.fetchall()
    created = 0

    for arrival in arrivals:
        days_before = int(arrival["days_before"])
        title = f"Reservation arrival in {days_before} days"
        check_in = arrival["check_in"]
        arrival_date = check_in.strftime("%b %d, %Y") if hasattr(check_in, "strftime") else str(check_in)
        message = (
            f"Reservation #RSV-{arrival['reservation_id']} for {arrival['guest_name']} "
            f"at {arrival['resort_name']} arrives in {days_before} days "
            f"({arrival_date}). Please review the schedule and prepare for arrival."
        )

        recipients = {
            arrival.get("owner_account_id"),
            arrival.get("caretaker_account_id"),
        }
        for account_id in recipients - {None}:
            cursor.execute(
                """
                SELECT notification_id
                FROM notifications
                WHERE account_id = %s AND type = 'reservation_reminder'
                  AND title = %s AND message = %s
                LIMIT 1
                """,
                (account_id, title, message),
            )
            if cursor.fetchone():
                continue

            cursor.execute(
                """
                INSERT INTO notifications (account_id, title, message, type)
                VALUES (%s, %s, %s, 'reservation_reminder')
                """,
                (account_id, title, message),
            )
            created += 1

    return created
