import os
import csv
from datetime import datetime
import uuid

# Import necessary SQLAlchemy components
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, Boolean, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker

# --- Configuration Section ---
# Use the database URL provided by the user
DATABASE_URL = "postgresql://bisinessdb_user:QceRMwRe2FtjhPk8iMLCIKB3j3s4KmhI@dpg-d1olvgbuibrs73cum700-a.oregon-postgres.render.com/bisinessdb"

# The specific business ID to query for transactions
TARGET_BUSINESS_ID = "2e2d7a2b-84ec-4b84-bb7c-96a0d8bdd6de"

# Define the output CSV file name
OUTPUT_FILENAME = f"transactions_{TARGET_BUSINESS_ID}.csv"

# --- Database Setup ---

# Create a base class for declarative models
Base = declarative_base()

# Define the database model based on the user's provided class
class CompanyTransaction(Base):
    """
    SQLAlchemy model for the 'company_transactions' table,
    exactly as provided by the user.
    """
    __tablename__ = 'company_transactions'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = Column(String(36), ForeignKey('businesses.id'), nullable=False)
    transaction_type = Column(String(50), nullable=False)  # 'income' or 'expense'
    amount = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    transaction_date = Column(Date, nullable=False)
    synced_to_remote = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f'<CompanyTransaction {self.transaction_type} - {self.amount}>'

# Create a database engine
engine = create_engine(DATABASE_URL)

# Create a session to interact with the database
Session = sessionmaker(bind=engine)
session = Session()

try:
    print("Attempting to connect to the database...")
    print(f"Fetching transactions for business ID: {TARGET_BUSINESS_ID}")

    # --- Query Execution ---
    # Construct a query to find all transactions where the business_id matches the target ID.
    transactions_query = session.query(CompanyTransaction).filter_by(business_id=TARGET_BUSINESS_ID)

    # Execute the query and get all results
    all_transactions = transactions_query.all()

    # --- Write to CSV File ---
    if all_transactions:
        print(f"Found {len(all_transactions)} transactions. Writing to '{OUTPUT_FILENAME}'...")
        
        # Open the CSV file in write mode ('w')
        # The `newline=''` argument is crucial to prevent empty rows from being written
        with open(OUTPUT_FILENAME, 'w', newline='', encoding='utf-8') as csvfile:
            # Create a CSV writer object
            csv_writer = csv.writer(csvfile)

            # Write the header row
            csv_writer.writerow([
                'id',
                'business_id',
                'transaction_type',
                'amount',
                'description',
                'transaction_date',
                'synced_to_remote'
            ])

            # Loop through the fetched transactions and write each one as a row
            for transaction in all_transactions:
                csv_writer.writerow([
                    transaction.id,
                    transaction.business_id,
                    transaction.transaction_type,
                    transaction.amount,
                    transaction.description,
                    transaction.transaction_date,
                    transaction.synced_to_remote
                ])
        
        print(f"\nSuccessfully wrote all transactions to {OUTPUT_FILENAME}")
    else:
        print("No transactions found for this business ID.")

except Exception as e:
    print(f"An error occurred: {e}")
    print("Please check your database connection URL and ensure the 'company_transactions' table and its columns exist as defined in the model.")

finally:
    # Always close the session to release the connection back to the pool
    session.close()
    print("Database session closed.")
