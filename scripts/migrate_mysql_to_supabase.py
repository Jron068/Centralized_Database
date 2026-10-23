"""Copy the existing MySQL application data into an empty Supabase schema.

This script does not delete or modify the source database. It refuses to write
if the destination contains rows or if the source and destination schemas do not
match safely. Set DATABASE_URL in .env before running it.
"""

import os
import sys

import mysql.connector
import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.rows import dict_row


TABLES = (
    "accounts",
    "owners",
    "resorts",
    "caretakers",
    "customers",
    "messages",
    "notifications",
    "reservations",
    "payments",
    "resort_owners",
    "resort_photos",
    "reviews",
    "account_profiles",
    "customer_favorites",
    "resort_updates",
)
OPTIONAL_TABLES = {"account_profiles", "customer_favorites", "resort_updates"}
IDENTITY_COLUMNS = {
    "accounts": "account_id",
    "caretakers": "caretaker_id",
    "customers": "customer_id",
    "messages": "message_id",
    "notifications": "notification_id",
    "owners": "owner_id",
    "payments": "payment_id",
    "reservations": "reservation_id",
    "resort_photos": "photo_id",
    "resorts": "resort_id",
    "reviews": "review_id",
    "resort_updates": "update_id",
}
BATCH_SIZE = 500


def _connect_mysql():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD") or "root123",
        database=os.getenv("DB_NAME", "centralized_database"),
    )


def _source_columns(cursor, table):
    cursor.execute(f"SELECT * FROM `{table}` LIMIT 0")
    columns = [column[0] for column in cursor.description]
    # mysql-connector-python can leave the cursor's result pending even for
    # LIMIT 0 metadata queries. Drain it before the same cursor is reused.
    cursor.fetchall()
    return columns


def _destination_columns(cursor, table):
    cursor.execute(
        "SELECT column_name, is_nullable, column_default, is_identity "
        "FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s "
        "ORDER BY ordinal_position",
        (table,),
    )
    return cursor.fetchall()


def _validate_schemas(source, target):
    source_cursor = source.cursor(dictionary=True)
    target_cursor = target.cursor(row_factory=dict_row)
    try:
        source_cursor.execute(
            "SELECT TABLE_NAME AS table_name FROM information_schema.tables "
            "WHERE TABLE_SCHEMA = %s",
            (os.getenv("DB_NAME", "centralized_database"),),
        )
        source_tables = {row["table_name"] for row in source_cursor.fetchall()}
        target_cursor.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'"
        )
        target_tables = {row["table_name"] for row in target_cursor.fetchall()}

        missing_source = [name for name in TABLES if name not in source_tables and name not in OPTIONAL_TABLES]
        missing_target = [name for name in TABLES if name not in target_tables]
        if missing_source or missing_target:
            raise RuntimeError(
                "Schema check failed. Missing source tables: "
                f"{', '.join(missing_source) or 'none'}; missing Supabase tables: "
                f"{', '.join(missing_target) or 'none'}."
            )

        available = [name for name in TABLES if name in source_tables]
        columns_by_table = {}
        for table in available:
            source_columns = _source_columns(source_cursor, table)
            target_columns = _destination_columns(target_cursor, table)
            target_names = {column["column_name"] for column in target_columns}
            absent = [column for column in source_columns if column not in target_names]
            if absent:
                raise RuntimeError(
                    f"Schema check failed for {table}; update schema/supabase.sql to include "
                    f"source columns: {', '.join(absent)}."
                )
            unfilled = [
                column["column_name"] for column in target_columns
                if column["column_name"] not in source_columns
                and column["is_nullable"] == "NO"
                and column["column_default"] is None
                and column["is_identity"] != "YES"
            ]
            if unfilled:
                raise RuntimeError(
                    f"Schema check failed for {table}; these required Supabase columns "
                    f"are absent from MySQL: {', '.join(unfilled)}."
                )
            columns_by_table[table] = source_columns
        return available, columns_by_table
    finally:
        source_cursor.close()
        target_cursor.close()


def _assert_empty_destination(target, tables):
    with target.cursor() as cursor:
        for table in tables:
            cursor.execute(
                sql.SQL("SELECT EXISTS (SELECT 1 FROM {} LIMIT 1)").format(
                    sql.Identifier(table)
                )
            )
            if cursor.fetchone()[0]:
                raise RuntimeError(
                    f"Supabase table {table} already has rows. No data was copied; "
                    "use a fresh empty project for this one-time migration."
                )


def _copy_table(source, target, table, columns, defer_column=None):
    source_cursor = source.cursor(dictionary=True)
    target_cursor = target.cursor()
    copied = 0
    deferred = []
    names = sql.SQL(", ").join(sql.Identifier(name) for name in columns)
    placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in columns)
    insert = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(table), names, placeholders
    )
    try:
        source_cursor.execute(f"SELECT * FROM `{table}`")
        while rows := source_cursor.fetchmany(BATCH_SIZE):
            values = []
            for row in rows:
                row_values = dict(row)
                if defer_column and row_values.get(defer_column) is not None:
                    deferred.append((row_values[columns[0]], row_values[defer_column]))
                    row_values[defer_column] = None
                values.append(tuple(row_values[column] for column in columns))
            target_cursor.executemany(insert, values)
            copied += len(values)
        return copied, deferred
    finally:
        source_cursor.close()
        target_cursor.close()


def _restore_deferred_values(target, table, id_column, value_column, values):
    if not values:
        return
    with target.cursor() as cursor:
        cursor.executemany(
            sql.SQL("UPDATE {} SET {} = %s WHERE {} = %s").format(
                sql.Identifier(table), sql.Identifier(value_column), sql.Identifier(id_column)
            ),
            [(value, row_id) for row_id, value in values],
        )


def _reset_identity_sequences(target, tables):
    with target.cursor() as cursor:
        for table in tables:
            identity = IDENTITY_COLUMNS.get(table)
            if not identity:
                continue
            cursor.execute(
                sql.SQL(
                    "SELECT setval(pg_get_serial_sequence(%s, %s), "
                    "COALESCE(MAX({}), 1), MAX({}) IS NOT NULL) FROM {}"
                ).format(sql.Identifier(identity), sql.Identifier(identity), sql.Identifier(table)),
                (f"public.{table}", identity),
            )


def main():
    load_dotenv()
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeError("Set DATABASE_URL in .env to your Supabase Session pooler connection string.")

    source = _connect_mysql()
    target = psycopg.connect(
        database_url,
        connect_timeout=10,
        sslmode="require",
        prepare_threshold=None,
    )
    try:
        tables, columns_by_table = _validate_schemas(source, target)
        _assert_empty_destination(target, tables)
        counts = {}
        deferred_accounts = []
        deferred_caretakers = []
        for table in TABLES:
            if table not in tables:
                continue
            defer_column = (
                "requested_resort_id" if table == "accounts"
                else "caretaker_id" if table == "resorts"
                else None
            )
            count, deferred = _copy_table(
                source, target, table, columns_by_table[table], defer_column
            )
            counts[table] = count
            if table == "accounts":
                deferred_accounts = deferred
            elif table == "resorts":
                deferred_caretakers = deferred

        _restore_deferred_values(
            target, "accounts", "account_id", "requested_resort_id", deferred_accounts
        )
        _restore_deferred_values(
            target, "resorts", "resort_id", "caretaker_id", deferred_caretakers
        )
        _reset_identity_sequences(target, tables)
        target.commit()
        for table, count in counts.items():
            print(f"Copied {count} rows from {table}.")
        print("Migration committed. The MySQL source was left unchanged.")
    except Exception:
        target.rollback()
        raise
    finally:
        source.close()
        target.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Migration stopped: {exc}", file=sys.stderr)
        sys.exit(1)
