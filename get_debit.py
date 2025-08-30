import psycopg2
import os
from urllib.parse import urlparse

DATABASE_URL = "postgresql://bisinessdb_user:QceRMwRe2FtjhPk8iMLCIKB3j3s4KmhI@dpg-d1olvgbuibrs73cum700-a.oregon-postgres.render.com/bisinessdb"
business_id_to_find = '2e2d7a2b-84ec-4b84-bb7c-96a0d8bdd6de'

url = urlparse(DATABASE_URL)
db_params = {
    'database': url.path[1:],
    'user': url.username,
    'password': url.password,
    'host': url.hostname,
    'port': url.port
}

conn = None
try:
    conn = psycopg2.connect(**db_params)
    cursor = conn.cursor()

    # Corrected table name from 'company_transaction' to 'company_transactions'
    query = """
    SELECT SUM(amount)
    FROM company_transactions
    WHERE business_id = %s AND transaction_type = 'Debit';
    """

    cursor.execute(query, (business_id_to_find,))
    
    total_debit_amount = cursor.fetchone()[0]

    if total_debit_amount is None:
        total_debit_amount = 0.0

    print(f"Total debitor amount for business '{business_id_to_find}': GH₵{total_debit_amount:.2f}")

except (Exception, psycopg2.DatabaseError) as error:
    print(f"An error occurred: {error}")

finally:
    if conn:
        cursor.close()
        conn.close()