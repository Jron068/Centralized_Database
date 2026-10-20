"""Shared storage helpers for account profile photos."""

import os
import uuid

from werkzeug.utils import secure_filename

from app import app

ALLOWED_PROFILE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_PROFILE_PHOTO_BYTES = 5 * 1024 * 1024


def ensure_account_profiles_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS account_profiles (
            account_id INT NOT NULL PRIMARY KEY,
            profile_photo_path VARCHAR(500) DEFAULT NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            CONSTRAINT fk_account_profiles_account
                FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def save_profile_photo(upload):
    """Validate a user-selected image, persist it, and return its static path."""
    original_name = secure_filename(upload.filename or "")
    extension = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if extension not in ALLOWED_PROFILE_EXTENSIONS:
        raise ValueError("Choose a JPG, PNG, or WEBP profile photo.")

    image_data = upload.stream.read(MAX_PROFILE_PHOTO_BYTES + 1)
    if not image_data:
        raise ValueError("The selected profile photo is empty.")
    if len(image_data) > MAX_PROFILE_PHOTO_BYTES:
        raise ValueError("Profile photos must be 5 MB or smaller.")

    directory = os.path.join(app.static_folder, "uploads", "profiles")
    os.makedirs(directory, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{extension}"
    with open(os.path.join(directory, filename), "wb") as output:
        output.write(image_data)
    return f"uploads/profiles/{filename}"
