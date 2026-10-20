"""Persistence helpers for customer-saved resorts."""


def ensure_customer_favorites_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customer_favorites (
            account_id INT NOT NULL,
            resort_id INT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (account_id, resort_id),
            CONSTRAINT fk_customer_favorites_account
                FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE,
            CONSTRAINT fk_customer_favorites_resort
                FOREIGN KEY (resort_id) REFERENCES resorts(resort_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
