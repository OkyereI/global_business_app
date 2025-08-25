import os
import psycopg2
from dotenv import load_dotenv
import pandas as pd
import datetime

# Load environment variables from .env file
load_dotenv()
PG_DATABASE_URL = os.getenv('DATABASE_URL')

def get_inventory_for_businesses(business_ids):
    """
    Fetches inventory items for a list of given business_ids from the PostgreSQL database.
    
    Args:
        business_ids (list): A list of business UUIDs as strings.
        
    Returns:
        str: A markdown-formatted string of the inventory data or an error message.
    """
    conn = None
    if not business_ids:
        return "No business IDs provided. Please provide a list of IDs to query."

    try:
        print(f"Attempting to connect to PostgreSQL database to fetch inventory for business_ids: {business_ids}...")
        conn = psycopg2.connect(PG_DATABASE_URL)
        cur = conn.cursor()
        print("Successfully connected to PostgreSQL.")

        # Construct the SQL query with a placeholder for multiple IDs
        # The `IN` clause is used to match any ID in the provided list
        sql = """
        SELECT 
            id, 
            product_name, 
            category, 
            current_stock, 
            purchase_price, 
            sale_price, 
            item_type, 
            is_fixed_price, 
            fixed_sale_price, 
            number_of_tabs, 
            business_id, 
            last_updated
        FROM inventory_items
        WHERE business_id IN %s;
        """
        
        # Use a psycopg2 adapter to correctly format the list as a tuple for the IN clause
        from psycopg2.extensions import adapt
        adapted_ids = tuple(business_ids)

        cur.execute(sql, (adapted_ids,))
        
        # Fetch all rows
        rows = cur.fetchall()
        
        # Get column names from cursor description
        columns = [desc[0] for desc in cur.description]
        
        cur.close()
        conn.close()

        if rows:
            df = pd.DataFrame(rows, columns=columns)
            # Convert timestamp/date objects to string for cleaner markdown output
            for col in ['last_updated']:
                if col in df.columns and pd.api.types.is_datetime64_any_dtype(df[col]):
                    df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S')
                elif col in df.columns and pd.api.types.is_object_dtype(df[col]):
                     df[col] = df[col].apply(lambda x: str(x) if isinstance(x, (datetime.date, datetime.datetime)) else x)

            return df.to_markdown(index=False)
        else:
            return f"No inventory items found for the provided business IDs."

    except psycopg2.Error as e:
        return f"Database error: {e}"
    except Exception as e:
        return f"An unexpected error occurred: {e}"
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    # Example usage with a list of business IDs
    business_ids_to_query = [
        'cc8583bd-cc9d-4be1-be4c-b0fb1a335637',
        '0099b4f6-e11f-4f83-aad1-d7522fd8e893', # Replace with a real business ID
        '3893b602-6fed-4216-95b1-df1bb22fed9f'  # Replace with another real business ID
    ]
    print(get_inventory_for_businesses(business_ids_to_query))