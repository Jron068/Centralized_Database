"""Idempotent database upgrades for customer payment and booking decisions."""


_BOOKING_COLUMNS = {
    "reservations": {
        "customer_decision": "VARCHAR(20) NOT NULL DEFAULT 'Pending'",
    },
    "payments": {
        "payer_name": "VARCHAR(150) NULL",
        "payer_phone": "VARCHAR(30) NULL",
        "reference_number": "VARCHAR(100) NULL",
        "payment_method": "VARCHAR(30) NULL",
    },
}


def ensure_booking_workflow_schema(connection):
    cursor = connection.cursor(dictionary=True)
    try:
        for table, columns in _BOOKING_COLUMNS.items():
            cursor.execute(
                "SELECT COLUMN_NAME AS name FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
                (table,),
            )
            existing = {row["name"] for row in cursor.fetchall()}
            for name, definition in columns.items():
                if name not in existing:
                    cursor.execute(
                        f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                    )
        connection.commit()
    finally:
        cursor.close()
