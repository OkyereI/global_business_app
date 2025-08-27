import os
from app import create_app, db
from models import InventoryItem, Business

# Create an app context to run the query
app = create_app()

with app.app_context():
    business_id = '154779f8-c750-4777-aea0-99018da36ab8'
    
    # Query all InventoryItem records where the business_id matches
    inventory_items = InventoryItem.query.filter_by(business_id=business_id).all()
    
    if inventory_items:
        print(f"Found {len(inventory_items)} inventory items for business ID: {business_id}")
        print("--- Inventory Details ---")
        for item in inventory_items:
            # CORRECTED: Changed 'item_name' to 'item_type'
            print(f"Item ID: {item.id}, Type: {item.item_type}, Quantity: {item.current_stock}")
    else:
        print(f"No inventory items found for business ID: {business_id}")