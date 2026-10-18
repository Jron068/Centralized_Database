"""Database helpers for resort gallery photos."""


def ensure_resort_photos_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resort_photos (
            photo_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            resort_id INT NOT NULL,
            photo_path VARCHAR(500) NOT NULL,
            caption VARCHAR(255) DEFAULT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_resort_photos_resort (resort_id),
            CONSTRAINT fk_resort_photos_resort
                FOREIGN KEY (resort_id) REFERENCES resorts(resort_id)
                ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def get_resort_photos(cursor, resort_ids):
    resort_ids = list(resort_ids)
    if not resort_ids:
        return {}
    ensure_resort_photos_table(cursor)
    placeholders = ",".join(["%s"] * len(resort_ids))
    cursor.execute(
        f"SELECT photo_id, resort_id, photo_path, caption FROM resort_photos "
        f"WHERE resort_id IN ({placeholders}) ORDER BY created_at, photo_id",
        tuple(resort_ids),
    )
    photos = {}
    for photo in cursor.fetchall():
        photos.setdefault(photo["resort_id"], []).append(photo)
    return photos
