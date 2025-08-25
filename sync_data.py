import os
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Database URLs from .env file
ONLINE_DB_URL = os.getenv('DATABASE_URL')
OFFLINE_DB_PATH = 'instance/instance_data.db'
OFFLINE_DB_URL = f'sqlite:///{OFFLINE_DB_PATH}'

# Ensure the instance directory exists for the offline database
os.makedirs(os.path.dirname(OFFLINE_DB_PATH), exist_ok=True)

def get_last_sync_timestamp():
    """
    Retrieves the last synchronization timestamp from a local file.
    """
    try:
        with open('last_sync.txt', 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return '1970-01-01 00:00:00'

def set_last_sync_timestamp(timestamp):
    """
    Saves the last synchronization timestamp to a local file.
    """
    with open('last_sync.txt', 'w') as f:
        f.write(timestamp)

def pull_online_data():
    """
    Pulls Businesses and Inventory from the online database to the offline database.
    """
    try:
        online_engine = create_engine(ONLINE_DB_URL)
        offline_engine = create_engine(OFFLINE_DB_URL)

        print("--- Pulling data from online to offline ---")
        
        # Pull Businesses
        print("Fetching businesses from online...")
        businesses_df = pd.read_sql_query("SELECT * FROM businesses", online_engine)
        businesses_df.to_sql('businesses', offline_engine, if_exists='replace', index=False)
        print(f"Pulled {len(businesses_df)} businesses.")

        # Pull Inventory Items
        print("Fetching all inventory items from online...")
        inventory_df = pd.read_sql_query("SELECT * FROM inventory_items", online_engine)
        inventory_df.to_sql('inventory_items', offline_engine, if_exists='replace', index=False)
        print(f"Pulled {len(inventory_df)} inventory items.")

    except Exception as e:
        print(f"Error during data pull: {e}")
        return False
    return True

def push_offline_sales():
    """
    Pushes all Sales Records from the offline database to the online database.
    
    NOTE: This version pushes all records every time and may create duplicates.
    It's a temporary fix for the missing 'created_at' column.
    """
    try:
        online_engine = create_engine(ONLINE_DB_URL)
        offline_engine = create_engine(OFFLINE_DB_URL)
        
        print("--- Pushing data from offline to online ---")

        # Fetch all sales records from offline DB
        print("Fetching all sales records from offline DB...")
        sales_sql = "SELECT * FROM sales_records"
        sales_df = pd.read_sql_query(sales_sql, offline_engine)

        if sales_df.empty:
            print("No new sales records to push.")
            return True

        print(f"Found {len(sales_df)} sales records. Pushing to online...")

        with online_engine.connect() as conn:
            sales_df.to_sql('sales_records', conn, if_exists='append', index=False)
            print("Sales records pushed successfully.")

    except Exception as e:
        print(f"Error during sales push: {e}")
        return False
    return True

def main():
    """
    Main function to run the synchronization process.
    """
    print("Starting synchronization process...")
    
    # 1. Pull data from online to offline
    pull_success = pull_online_data()
    if not pull_success:
        print("Synchronization aborted due to an error during data pull.")
        return

    # 2. Push sales from offline to online
    push_success = push_offline_sales()
    if not push_success:
        print("Synchronization aborted due to an error during sales push.")
        return

    # 3. Update the last sync timestamp
    set_last_sync_timestamp(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("Synchronization complete!")

if __name__ == '__main__':
    main()