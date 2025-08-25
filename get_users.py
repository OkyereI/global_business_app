# get_users.py - Script to fetch user information from the database

import os
import sqlite3
import psycopg2
import pandas as pd
from dotenv import load_dotenv
import datetime # Keep for potential date handling if needed

# Load environment variables from .env file
load_dotenv()

# Get the database URL
DB_URL = os.getenv('DATABASE_URL')

def get_all_users():
    """
    Fetches all user records from the configured database (SQLite or PostgreSQL).
    """
    conn = None
    cur = None
    try:
        if not DB_URL:
            return "Error: DATABASE_URL environment variable is not set."

        print(f"Attempting to connect to database using URL: {DB_URL}")

        if DB_URL.startswith('sqlite:///'):
            # Connect to SQLite
            db_path = DB_URL.replace('sqlite:///', '')
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row # Allows access by column name
            cur = conn.cursor()
            print("Successfully connected to SQLite.")
            # For SQLite, the table name is typically 'user' based on your model
            table_name = 'user'
        elif DB_URL.startswith('postgresql://') or DB_URL.startswith('postgresql+psycopg2://'):
            # Connect to PostgreSQL
            # psycopg2.connect expects the standard 'postgresql://' format
            pg_connect_url = DB_URL.replace("postgresql+psycopg2://", "postgresql://")
            conn = psycopg2.connect(pg_connect_url)
            cur = conn.cursor()
            print("Successfully connected to PostgreSQL.")
            # For PostgreSQL, the table name is typically 'user' based on your model
            table_name = 'user' # Explicitly use 'user' as per your models.py
        else:
            return f"Error: Unsupported database type in DATABASE_URL: {DB_URL}"

        # Selecting key user details
        # Corrected: 'type' is not a user column, but 'business_id' is.
        # Assuming you want username, role, business_id, and maybe creation date.
        sql = f"""
        SELECT 
            id, 
            username, 
            role,
            business_id,
            created_at
        FROM {table_name};
        """
        cur.execute(sql)
        
        # Fetch all rows
        rows = cur.fetchall()
        
        # Get column names from cursor description
        columns = [desc[0] for desc in cur.description]
        
        if rows:
            # Convert rows to a list of dicts for pandas if using sqlite3.Row
            if DB_URL.startswith('sqlite:///'):
                rows_as_dicts = [dict(row) for row in rows]
                df = pd.DataFrame(rows_as_dicts, columns=columns)
            else: # psycopg2 returns tuples, works directly with DataFrame
                df = pd.DataFrame(rows, columns=columns)

            # Convert timestamp/date objects to string for cleaner markdown output
            # Only apply if the column exists to avoid errors
            date_cols = ['created_at'] # Add 'last_password_update' if it exists in your User model/table
            for col in date_cols:
                if col in df.columns:
                    if pd.api.types.is_datetime64_any_dtype(df[col]):
                        df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S')
                    elif pd.api.types.is_object_dtype(df[col]): # Fallback for object type dates
                        df[col] = df[col].apply(lambda x: str(x) if isinstance(x, (datetime.date, datetime.datetime)) else x)

            return df.to_markdown(index=False)
        else:
            return "No users found in the database."

    except (psycopg2.Error, sqlite3.Error) as e:
        return f"Database error: {e}"
    except Exception as e:
        return f"An unexpected error occurred: {e}"
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

if __name__ == '__main__':
    print(get_all_users())
