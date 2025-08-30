# merge_businesses.py
import os
from app import create_app
from extensions import db
from models import Company, CompanyTransaction
from sqlalchemy import text

# Define the source and destination business IDs
SOURCE_BUSINESS_ID = '2e2d7a2b-84ec-4b84-bb7c-96a0d8bdd6de'
DESTINATION_BUSINESS_ID = '661ded04-6f2f-4cf0-b7e9-e6900a60a2b0'

def merge_business_data(source_id, destination_id):
    """
    Merges all companies and their transactions from a source business ID
    to a destination business ID.
    """
    app = create_app()
    with app.app_context():
        print(f"Connecting to the database to merge data from '{source_id}' to '{destination_id}'...")
        
        try:
            # Step 1: Update the business_id for all companies
            company_count = Company.query.filter_by(business_id=source_id).update(
                {'business_id': destination_id},
                synchronize_session='fetch'
            )
            print(f"Updated {company_count} company records.")

            # Step 2: Update the business_id for all company transactions
            transaction_count = CompanyTransaction.query.filter_by(business_id=source_id).update(
                {'business_id': destination_id},
                synchronize_session='fetch'
            )
            print(f"Updated {transaction_count} company transaction records.")
            
            # Commit the changes to the database
            db.session.commit()
            print("\n✅ Merge successful! All records have been updated.")

        except Exception as e:
            db.session.rollback() # Rollback changes in case of an error
            print(f"\n❌ An error occurred during the merge process: {e}")
            print("Database changes have been rolled back.")

if __name__ == '__main__':
    merge_business_data(SOURCE_BUSINESS_ID, DESTINATION_BUSINESS_ID)