# export_companies.py
import os
import csv
from app import create_app
from extensions import db
from models import Company
from datetime import datetime

# The business_id to filter the companies
BUSINESS_ID = '661ded04-6f2f-4cf0-b7e9-e6900a60a2b0'

def export_companies_to_csv(business_id):
    """
    Fetches all companies for a given business_id and exports them to a CSV file.
    """
    app = create_app()
    with app.app_context():
        print(f"Connecting to the database and fetching companies for business_id: {business_id}...")

        try:
            companies = Company.query.filter_by(business_id=business_id).all()
            
            if not companies:
                print(f"No companies found for business ID '{business_id}'. No CSV file will be created.")
                return

            # Define the CSV file name and path
            filename = f"companies_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            # Define the CSV headers based on the Company model
            headers = [
                'id', 'name', 'contact_person', 'phone', 'email', 'address', 
                'balance', 'is_active', 'date_added', 'business_id'
            ]

            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=headers)
                writer.writeheader()

                for company in companies:
                    writer.writerow({
                        'id': getattr(company, 'id', ''),
                        'name': getattr(company, 'name', ''),
                        'contact_person': getattr(company, 'contact_person', ''),
                        'phone': getattr(company, 'phone', ''),
                        'email': getattr(company, 'email', ''),
                        'address': getattr(company, 'address', ''),
                        'balance': float(getattr(company, 'balance', 0.0)) if getattr(company, 'balance', None) is not None else 0.0,
                        'is_active': getattr(company, 'is_active', False),
                        'date_added': getattr(company, 'date_added', datetime.min).strftime('%Y-%m-%d %H:%M:%S') if getattr(company, 'date_added', None) else '',
                        'business_id': getattr(company, 'business_id', '')
                    })
            
            print(f"Successfully exported {len(companies)} companies to '{filename}'.")

        except Exception as e:
            print(f"An error occurred during export: {e}")
            db.session.rollback() # Rollback in case of error

if __name__ == '__main__':
    export_companies_to_csv(BUSINESS_ID)