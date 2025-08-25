# connect_db.py - Script to test connection to the PostgreSQL database

import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables from .env file
# This assumes your DATABASE_URL is stored in your .env file
load_dotenv()

# Retrieve the DATABASE_URL from environment variables
# Ensure it includes the sslmode=require if connecting to Render
PG_DATABASE_URL = os.getenv('DATABASE_URL')

def test_db_connection():
    """
    Tests the connection to the PostgreSQL database using the DATABASE_URL
    and fetches the current database version.
    """
    conn = None
    cur = None
    try:
        print("Attempting to connect to PostgreSQL database...")
        # Add sslmode=require directly in the connection string if not in .env
        # or if it's explicitly needed by your provider (like Render)
        conn = psycopg2.connect(PG_DATABASE_URL)
        cur = conn.cursor()
        print("Successfully connected to PostgreSQL! 🎉")

        # Execute a simple query to get the database version
        cur.execute("SELECT version();")
        db_version = cur.fetchone()[0]
        print(f"PostgreSQL Database Version: {db_version}")

        # You can add more queries here to check specific tables, e.g.:
        # cur.execute("SELECT COUNT(*) FROM users;")
        # user_count = cur.fetchone()[0]
        # print(f"Number of users: {user_count}")

    except psycopg2.Error as e:
        print(f"Database connection failed! 😟 Error: {e}")
        print("Please check your DATABASE_URL in the .env file and ensure network connectivity.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == '__main__':
    test_db_connection()
