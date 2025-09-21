from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from models import Business, InventoryItem, SalesRecord, db

# Create a Blueprint for the synchronization API
sync_api = Blueprint('sync_api', __name__, url_prefix='/api/sync')

@sync_api.route('/pull_data/<string:business_id>', methods=['GET'])
@login_required
def pull_data(business_id):
    """
    API endpoint to pull all business, inventory, and sales data for offline use.
    The client will call this when it regains an internet connection.
    """
    try:
        # Check if the current user has access to this business_id
        if current_user.business_id != business_id:
            return jsonify({"status": "error", "message": "Unauthorized access"}), 403

        # Fetch all business and related inventory and sales data.
        # joinedload ensures the related data is loaded in one query, improving performance.
        business = Business.query.options(
            joinedload(Business.inventory_items),
            joinedload(Business.sales_records)
        ).filter_by(id=business_id).first()

        if not business:
            return jsonify({"status": "error", "message": "Business not found"}), 404

        # Convert the ORM objects to a serializable dictionary format.
        # This assumes your models have a to_dict() method.
        # If not, you'll need to create one for each model (e.g., Business, InventoryItem, SalesRecord).
        business_data = business.to_dict()
        inventory_data = [item.to_dict() for item in business.inventory_items]
        sales_data = [sale.to_dict() for sale in business.sales_records]

        # Respond with all the data
        return jsonify({
            "status": "success",
            "message": "Data pulled successfully.",
            "data": {
                "business": business_data,
                "inventory": inventory_data,
                "sales": sales_data
            }
        })

    except Exception as e:
        print(f"Error pulling data: {e}")
        return jsonify({"status": "error", "message": "An error occurred during data retrieval."}), 500

@sync_api.route('/push_data', methods=['POST'])
@login_required
def push_data():
    """
    API endpoint to push local sales and inventory changes to the central server.
    The client will call this when it goes back online.
    """
    try:
        data = request.json
        business_id = data.get('business_id')

        # Check for user authorization
        if current_user.business_id != business_id:
            return jsonify({"status": "error", "message": "Unauthorized access"}), 403

        # Process new sales records
        for sale_data in data.get('sales_records', []):
            existing_sale = SalesRecord.query.get(sale_data.get('id'))
            if existing_sale:
                # Update existing sales record if it already exists
                existing_sale.quantity = sale_data.get('quantity')
                # You might need to update other fields as well.
            else:
                # Create a new sales record
                new_sale = SalesRecord(**sale_data)
                db.session.add(new_sale)
        
        # Process inventory updates
        for item_data in data.get('inventory_updates', []):
            inventory_item = InventoryItem.query.get(item_data.get('id'))
            if inventory_item:
                # Update inventory quantity
                inventory_item.quantity = item_data.get('quantity')
            else:
                # This case might indicate an issue, but you can create a new record if needed
                new_inventory_item = InventoryItem(**item_data)
                db.session.add(new_inventory_item)

        db.session.commit()
        return jsonify({"status": "success", "message": "Changes synced successfully."})

    except Exception as e:
        db.session.rollback()
        print(f"Error pushing data: {e}")
        return jsonify({"status": "error", "message": "An error occurred during synchronization."}), 500
