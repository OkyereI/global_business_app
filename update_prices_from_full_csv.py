# update_prices_from_full_csv.py - Script to update inventory prices from a full CSV export

import csv
import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Database Configuration for PostgreSQL ---
PG_DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://user:password@host:port/database' # Fallback, actual URL from .env
)

def update_inventory_prices_from_csv(csv_file_path):
    """
    Reads inventory data from a CSV file (expected to have correct prices)
    and updates purchase_price and sale_price in the PostgreSQL database,
    matching by item ID and business ID.
    """
    conn = None
    cur = None
    try:
        print("Attempting to connect to PostgreSQL database...")
        conn = psycopg2.connect(PG_DATABASE_URL)
        cur = conn.cursor()
        print("Successfully connected to PostgreSQL.")

        print(f"Reading data from {csv_file_path} to update prices...")
        with open(csv_file_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            
            updated_count = 0
            for row in reader:
                # Essential fields for matching and updating
                item_id = row.get('id')
                business_id = row.get('business_id')

                if not item_id:
                    print(f"Skipping row due to missing 'id': {row}")
                    continue
                if not business_id:
                    print(f"Skipping row due to missing 'business_id': {row}")
                    continue

                # Convert prices to float, default to 0.0 if conversion fails or not found
                try:
                    purchase_price = float(row.get('purchase_price', 0.0))
                except (ValueError, TypeError):
                    purchase_price = 0.0
                
                try:
                    sale_price = float(row.get('sale_price', 0.0))
                except (ValueError, TypeError):
                    sale_price = 0.0

                # SQL to update the specific inventory item by ID and business_id
                # Using ID for primary match, as it should be unique and consistent
                sql = """
                UPDATE inventory_items
                SET purchase_price = %s, sale_price = %s
                WHERE id = %s AND business_id = %s;
                """
                cur.execute(sql, (purchase_price, sale_price, item_id, business_id))
                
                if cur.rowcount > 0:
                    updated_count += 1
                    print(f"Updated item ID: {item_id}, Product: {row.get('product_name', 'N/A')}")
                else:
                    # This warning is useful if IDs are truly inconsistent between CSV and PG
                    print(f"Warning: Item ID {item_id} (Product: {row.get('product_name', 'N/A')}) not found in PostgreSQL or already updated.")

        conn.commit() # Commit all changes
        print(f"\nPrice update complete. Total items updated: {updated_count}")

    except psycopg2.Error as e:
        print(f"Database error: {e}")
        if conn:
            conn.rollback() # Rollback in case of error
    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_file_path}. Please ensure the file is in the correct directory.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == '__main__':
    # Adjust this path if your CSV is in a different directory (e.g., 'data/withsaleandpurchase.csv')
    csv_file_to_use = 'withsaleandpurchase.csv' 
    update_inventory_prices_from_csv(csv_file_to_use)

