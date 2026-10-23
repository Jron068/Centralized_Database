"""Shared resort announcements posted by admins and caretakers."""


def ensure_resort_updates_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resort_updates (
            update_id INT AUTO_INCREMENT PRIMARY KEY,
            author_account_id INT NOT NULL,
            author_role VARCHAR(20) NOT NULL,
            resort_id INT NULL,
            title VARCHAR(100) NOT NULL,
            category VARCHAR(30) NOT NULL DEFAULT 'notice',
            message VARCHAR(2000) NOT NULL,
            image_path VARCHAR(500) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_resort_updates_scope_created (resort_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def update_image_url(image_path):
    if not image_path:
        return None
    from models.file_storage import file_url
    return file_url(image_path)
