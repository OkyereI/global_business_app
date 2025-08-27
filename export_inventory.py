import os
import csv
from app import create_app, db
from models import InventoryItem

# Initialize the Flask app and database
app = create_app()

with app.app_context():
    business_id = '154779f8-c750-4777-aea0-99018da36ab8'
    
    # Query all InventoryItem records where the business_id matches
    inventory_items = InventoryItem.query.filter_by(business_id=business_id).all()
    
    if inventory_items:
        # Define the path for the output CSV file
        csv_file_path = "inventory_export.csv"
        
        # Open the file in write mode
        with open(csv_file_path, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            
            # Write the header row
            csv_writer.writerow([
                'ID', 'Item Name', 'Item Type', 'Current Stock', 'Is Fixed Price', 
                'Barcode', 'Unit Price Per Tab', 'Expiry Date', 'Batch Number', 
                'Purchase Price', 'Sale Price', 'Fixed Sale Price', 'Markup Percentage'
            ])
            
            # Write the data rows
            for item in inventory_items:
                csv_writer.writerow([
                    item.id,
                    item.item_name if hasattr(item, 'item_name') else 'N/A', # Add a fallback for item_name
                    item.item_type,
                    item.current_stock,
                    item.is_fixed_price,
                    item.barcode,
                    item.unit_price_per_tab,
                    item.expiry_date.strftime('%Y-%m-%d') if item.expiry_date else '',
                    item.batch_number,
                    item.purchase_price,
                    item.sale_price,
                    item.fixed_sale_price,
                    item.markup_percentage_pharmacy
                ])
        
        print(f"Successfully exported {len(inventory_items)} items to {csv_file_path}")
    else:
        print(f"No inventory items found for business ID: {business_id}")