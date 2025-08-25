# export_sqlite_to_csv.py - Script to export inventory data from local SQLite to CSV

import sqlite3
import csv
import os

# Define the path to your SQLite database file
# Assuming instance_data.db is in the 'instance' subdirectory
SQLITE_DB_PATH = 'instance/instance_data.db'
CSV_OUTPUT_PATH = 'inventory_full_data_for_restore.csv' # Output to project root

def export_inventory_data(db_path, output_csv_path):
    conn = None
    try:
        print(f"Attempting to connect to SQLite database: {db_path}...")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        print("Successfully connected to SQLite.")

        # SELECT only the columns that are likely to exist and are essential for restoration.
        # This avoids "no such column" errors if your local SQLite schema is older/different.
        sql_query = """
        SELECT 
            id, 
            product_name, 
            category, 
            current_stock, 
            purchase_price, 
            sale_price, 
            business_id, 
            last_updated
        FROM inventory_items;
        """
        cur.execute(sql_query)
        
        # Get column names from the cursor description
        column_names = [description[0] for description in cur.description]
        
        print(f"Exporting data to CSV: {output_csv_path}...")
        with open(output_csv_path, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(column_names) # Write header row
            csv_writer.writerows(cur)        # Write data rows
        
        print("Export successful!")

    except sqlite3.Error as e:
        print(f"SQLite database error: {e}")
    except FileNotFoundError:
        print(f"Error: SQLite database file not found at {db_path}. Please check the path.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if conn:
            conn.close()
            print("SQLite connection closed.")

if __name__ == '__main__':
    # Ensure you are running this script from your project's root directory (e.g., ~/pharmapp1/)
    export_inventory_data(SQLITE_DB_PATH, CSV_OUTPUT_PATH)

