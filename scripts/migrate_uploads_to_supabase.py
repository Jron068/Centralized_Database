"""Copy existing local upload files to Supabase Storage and update their DB references."""

import mimetypes
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from dotenv import load_dotenv
from psycopg import sql

from models.file_storage import delete_uploaded_file, upload_file


STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"
FILE_COLUMNS = (
    ("resorts", "resort_id", "logo"),
    ("resort_photos", "photo_id", "photo_path"),
    ("resort_updates", "update_id", "image_path"),
    ("account_profiles", "account_id", "profile_photo_path"),
    ("payments", "payment_id", "proof_of_payment"),
    ("reservations", "reservation_id", "proof_of_payment"),
)


def _local_file(reference):
    if not reference or urlsplit(reference).scheme:
        return None
    relative = reference.replace("\\", "/").lstrip("/")
    if relative.startswith("static/"):
        relative = relative[len("static/"):]
    if not relative.startswith("uploads/"):
        return None
    path = (STATIC_ROOT / relative).resolve()
    if os.path.commonpath((str(STATIC_ROOT.resolve()), str(path))) != str(STATIC_ROOT.resolve()):
        raise RuntimeError("A stored file reference points outside the static directory.")
    return path


def _file_content_type(path):
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def main():
    load_dotenv(".env")
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeError("Set DATABASE_URL in .env to your Supabase PostgreSQL connection string.")

    connection = psycopg.connect(
        database_url,
        connect_timeout=10,
        sslmode="require",
        prepare_threshold=None,
    )
    uploaded = []
    try:
        cursor = connection.cursor()
        try:
            pending = []
            for table, primary_key, column in FILE_COLUMNS:
                cursor.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s AND column_name = %s",
                    (table, column),
                )
                if not cursor.fetchone():
                    continue
                query = sql.SQL("SELECT {}, {} FROM {} WHERE {} IS NOT NULL").format(
                    sql.Identifier(primary_key),
                    sql.Identifier(column),
                    sql.Identifier(table),
                    sql.Identifier(column),
                )
                cursor.execute(query)
                for row_id, reference in cursor.fetchall():
                    local_path = _local_file(reference)
                    if local_path is None:
                        continue
                    if not local_path.is_file():
                        raise RuntimeError(
                            "At least one database upload reference has no matching local file. "
                            "No files were uploaded; restore the missing files and retry."
                        )
                    pending.append((table, primary_key, column, row_id, reference, local_path))

            for table, primary_key, column, row_id, old_reference, local_path in pending:
                private = any(part in {"payments", "walkin_proofs"} for part in local_path.parts)
                filename = local_path.name
                object_path = f"legacy/{table}/{row_id}/{filename}"
                new_reference = upload_file(
                    local_path.read_bytes(),
                    object_path,
                    private=private,
                    content_type=_file_content_type(local_path),
                )
                uploaded.append(new_reference)
                cursor.execute(
                    sql.SQL("UPDATE {} SET {} = %s WHERE {} = %s AND {} = %s").format(
                        sql.Identifier(table),
                        sql.Identifier(column),
                        sql.Identifier(primary_key),
                        sql.Identifier(column),
                    ),
                    (new_reference, row_id, old_reference),
                )
            connection.commit()
            print(f"Migrated {len(uploaded)} existing upload(s) to Supabase Storage.")
            print("Payment and walk-in proof files were stored in the private bucket.")
        except Exception:
            connection.rollback()
            for reference in uploaded:
                delete_uploaded_file(reference)
            raise
        finally:
            cursor.close()
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Upload migration stopped: {exc}", file=sys.stderr)
        sys.exit(1)
