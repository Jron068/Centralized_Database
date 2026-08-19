import mysql.connector

def get_connection():
    connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password="root123",
        database="centralized_database"
    )
    return connection