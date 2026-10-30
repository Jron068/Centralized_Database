import os
from threading import Lock

import mysql.connector
import psycopg
from dotenv import load_dotenv
from models.booking_schema import ensure_booking_workflow_schema
from models.postgres_compat import connect_postgres

load_dotenv()

DatabaseError = psycopg.Error
MySQLDatabaseError = mysql.connector.Error
_booking_schema_ready = False
_booking_schema_lock = Lock()

def get_connection():
    global _booking_schema_ready
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        connection = connect_postgres(database_url)
    else:
        connection = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            # An empty DB_PASSWORD in .env should still use the local default.
            password=os.getenv("DB_PASSWORD") or "root123",
            database=os.getenv("DB_NAME", "centralized_database"),
        )

    if not _booking_schema_ready:
        with _booking_schema_lock:
            if not _booking_schema_ready:
                try:
                    ensure_booking_workflow_schema(connection)
                except (DatabaseError, MySQLDatabaseError):
                    connection.close()
                    raise
                _booking_schema_ready = True
    return connection
