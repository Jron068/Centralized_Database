import os

import mysql.connector
import psycopg
from dotenv import load_dotenv
from models.postgres_compat import connect_postgres

load_dotenv()

DatabaseError = psycopg.Error
MySQLDatabaseError = mysql.connector.Error

def get_connection():
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return connect_postgres(database_url)

    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        # An empty DB_PASSWORD in .env should still use the local default.
        password=os.getenv("DB_PASSWORD") or "root123",
        database=os.getenv("DB_NAME", "centralized_database"),
    )
    return connection
