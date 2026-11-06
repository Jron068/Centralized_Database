def ensure_password_resets_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            account_id INT NOT NULL PRIMARY KEY,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            expires_at DATETIME NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_password_resets_account
                FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
        )
    """)
