"""Persistence helpers for customer-to-resort-owner support conversations."""


def ensure_customer_support_messages_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customer_support_messages (
            support_message_id INT AUTO_INCREMENT PRIMARY KEY,
            resort_id INT NOT NULL,
            sender_account INT NOT NULL,
            receiver_account INT NOT NULL,
            message TEXT NOT NULL,
            is_read SMALLINT NOT NULL DEFAULT 0,
            sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_support_thread (resort_id, sender_account, receiver_account, sent_at),
            INDEX idx_support_recipient (receiver_account, is_read, sent_at),
            CONSTRAINT fk_support_resort
                FOREIGN KEY (resort_id) REFERENCES resorts(resort_id),
            CONSTRAINT fk_support_sender
                FOREIGN KEY (sender_account) REFERENCES accounts(account_id),
            CONSTRAINT fk_support_receiver
                FOREIGN KEY (receiver_account) REFERENCES accounts(account_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
