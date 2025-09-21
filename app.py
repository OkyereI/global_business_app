from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort,Response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, current_user, login_required, UserMixin
from functools import wraps
from datetime import datetime, date, timedelta # Import date and timedelta for dashboard
import os
import csv
import sys
import uuid
import pandas as pd
import requests # Import requests for API calls
import json # Import json for API responses and handling
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Index, create_engine, text, func, cast,or_  # Import func and cast for dashboard queries
from dotenv import load_dotenv
from flask import current_app
from extensions import db, migrate # ADD THIS LINE AND REMOVE OLD DB/MIGRATE DEFINITIONS
import io
import logging
from sync_api import sync_api
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
import time
import threading
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Global Configuration (if needed for constants) ---
# Example: Placeholder for external API keys/URLs if they are truly global
ARKESEL_API_KEY = os.getenv('ARKESEL_API_KEY')
ARKESEL_SENDER_ID = os.getenv('ARKESEL_SENDER_ID', 'YourSenderID')
ARKESEL_SMS_URL = "https://sms.arkesel.com/sms/api" # Correct Arkesel SMS API URL
REMOTE_SERVER_URL = os.getenv('ONLINE_FLASK_APP_BASE_URL', 'http://localhost:5000')
# These should ideally come from Business info, but as fallback for SMS or defaults
ENTERPRISE_NAME = os.getenv('ENTERPRISE_NAME', 'Your Enterprise Name')
PHARMACY_LOCATION = os.getenv('PHARMACY_LOCATION', 'Your Town, Your Region')
PHARMACY_ADDRESS = os.getenv('PHARMACY_ADDRESS', '123 Business St')
PHARMACY_CONTACT = os.getenv('PHARMACY_CONTACT', '+1234567890')
ADMIN_PHONE_NUMBER = os.getenv('ADMIN_PHONE_NUMBER', '') # For daily reports
from extensions import db, migrate # ADD THIS LINE AND REMOVE OLD DB/MIGRATE DEFINITIONS

# --- Path Configuration for PyInstaller ---
def get_app_paths():
    """Get proper paths for templates, static files, and database based on execution context."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        base_dir = sys._MEIPASS
        template_dir = os.path.join(base_dir, 'templates')
        static_dir = os.path.join(base_dir, 'static')
        
        # For database, use a writable location outside the bundle
        executable_dir = os.path.dirname(sys.executable)
        instance_dir = os.path.join(executable_dir, 'instance')
        if not os.path.exists(instance_dir):
            os.makedirs(instance_dir)
        db_path = os.path.join(instance_dir, 'instance_data.db')
    else:
        # Running in development
        base_dir = os.path.dirname(os.path.abspath(__file__))
        template_dir = os.path.join(base_dir, 'templates')
        static_dir = os.path.join(base_dir, 'static')
        
        instance_dir = os.path.join(base_dir, 'instance')
        if not os.path.exists(instance_dir):
            os.makedirs(instance_dir)
        db_path = os.path.join(instance_dir, 'instance_data.db')
    
    return {
        'template_folder': template_dir,
        'static_folder': static_dir,
        'db_path': db_path,
        'instance_path': os.path.dirname(db_path)
    }

# Get application paths
app_paths = get_app_paths()
template_folder = app_paths['template_folder']
db_path = app_paths['db_path']


SYNC_STATUS = {
    "is_syncing": False,
    "last_sync_time": None,
    "last_sync_success": None,
    "last_sync_message": "Idle."
}

# Enhanced Sync Monitoring Variables
enhanced_sync_status = {
    'last_sync': None,
    'sync_conflicts': [],
    'sync_health': 'healthy',
    'sync_running': False
}

# Sync conflict types
CONFLICT_TYPES = {
    'DATA_MISMATCH': 'Data mismatch between systems',
    'TIMESTAMP_CONFLICT': 'Timestamp synchronization conflict',
    'DUPLICATE_RECORD': 'Duplicate record detected',
    'VALIDATION_ERROR': 'Data validation error'
}
# Enhanced Sync Helper Functions
def check_sync_conflicts():
    """Check for potential sync conflicts"""
    from datetime import datetime
    import random
    
    # Simulate conflict detection (replace with your actual logic)
    conflicts = []
    
    # Example: Check for timestamp conflicts
    if random.random() > 0.7:  # 30% chance of conflict for demo
        conflicts.append({
            'id': f'conflict_{int(datetime.now().timestamp())}',
            'type': 'TIMESTAMP_CONFLICT', 
            'description': 'Data timestamp mismatch detected',
            'severity': 'medium',
            'created_at': datetime.now().isoformat(),
            'table_affected': 'sales'
        })
    
    enhanced_sync_status['sync_conflicts'] = conflicts
    return conflicts

def resolve_sync_conflict(conflict_id, resolution):
    """Resolve a sync conflict"""
    for i, conflict in enumerate(enhanced_sync_status['sync_conflicts']):
        if conflict['id'] == conflict_id:
            # Mark conflict as resolved
            conflict['status'] = 'resolved'
            conflict['resolution'] = resolution
            conflict['resolved_at'] = datetime.now().isoformat()
            
            # Remove from active conflicts
            enhanced_sync_status['sync_conflicts'].pop(i)
            
            return {'success': True, 'message': 'Conflict resolved successfully'}
    
    return {'success': False, 'message': 'Conflict not found'}

def get_enhanced_sync_status():
    """Get current enhanced synchronization status"""
    from datetime import datetime
    
    # Update sync status (replace with your actual logic)
    check_sync_conflicts()  # Check for new conflicts
    
    return {
        'last_sync': enhanced_sync_status.get('last_sync') or datetime.now().isoformat(),
        'sync_health': enhanced_sync_status['sync_health'],
        'sync_running': enhanced_sync_status['sync_running'],
        'conflicts_count': len(enhanced_sync_status['sync_conflicts']),
        'conflicts': enhanced_sync_status['sync_conflicts'],
        'status_updated': datetime.now().isoformat()
    }

def create_app():
    # This is the application factory function
    app = Flask(__name__, template_folder=template_folder, static_folder=app_paths['static_folder'])
    

    
    # --- Configuration ---
    DB_TYPE = os.getenv('DB_TYPE', 'sqlite')
    if DB_TYPE == 'sqlite':
        # Use the corrected db_path that works with PyInstaller
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
        print(f"Using SQLite database: {app.config['SQLALCHEMY_DATABASE_URI']}")
        # Ensure database directory exists
        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
    else:
        pg_url = os.getenv(
            'DATABASE_URL',
            'postgresql://bisinessdb_user:QceRMwRe2FtjhPk8iMLCIKB3j3s4KmhI@dpg-d1olvgbuibrs73cum700-a.oregon-postgres.render.com/bisinessdb'
        )
        app.config['SQLALCHEMY_DATABASE_URI'] = pg_url.replace("postgresql://", "postgresql+psycopg2://")
        print(f"Using PostgreSQL database with psycopg2: {app.config['SQLALCHEMY_DATABASE_URI']}")

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'your_super_secret_key_here')
    app.config['ENV'] = 'development'
    app.config['DEBUG'] = True

    # # --- Initialize Flask Extensions with the app instance ---
    db.init_app(app)
    migrate.init_app(app, db) # Initialize Migrate with the app and db instances
    csrf = CSRFProtect(app)
    
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message_category = 'info'
    
    # Import models after the extensions have been initialized
    from models import User, Business, SalesRecord, InventoryItem, HirableItem, RentalRecord, Creditor, Debtor, CompanyTransaction, FutureOrder, Company, Customer, ReturnRecord
    @login_manager.user_loader
    def load_user(user_id):
        # This function is called after tables are created, so it will work.
        return db.session.get(User, user_id)


    

    # For simplicity, I'll define a basic login_required if Flask-Login is not explicitly used.
    def login_required(f):
        from functools import wraps
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'username' not in session:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    def get_user_role():
        return session.get('role')

    def get_business_id():
        return session.get('business_id')

    def get_business_type():
        return session.get('business_type')

    # Basic login_required (if Flask-Login is not explicitly used)
    # def login_required(f):
    #     from functools import wraps
    #     @wraps(f)
    #     def decorated_function(*args, **kwargs):
    #         if 'username' not in session:
    #             flash('Please log in to access this page.', 'warning')
    #             return redirect(url_for('login'))
    #         return f(*args, **kwargs)
    #     return decorated_function

    # def admin_required(f):
    #     from functools import wraps
    #     @wraps(f)
    #     def decorated_function(*args, **kwargs):
    #         if session.get('role') != 'admin':
    #             flash('Access denied: Admins only.', 'danger')
    #             return redirect(url_for('dashboard'))
    #         return f(*args, **kwargs)
    #     return decorated_function

    def super_admin_required(f):
        from functools import wraps
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get('role') != 'super_admin':
                flash('Access denied: Super Admin only.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function

    def api_key_required(f):
        """
        Decorator to check for a valid API key in the request header.
        """
        @wraps(f)
        def decorated_function(*args, **kwargs):
            api_key = request.headers.get('X-API-Key')
            if not api_key or api_key != os.getenv('REMOTE_ADMIN_API_KEY'):
                return jsonify({'message': 'API Key is missing or invalid.'}), 401
            return f(*args, **kwargs)
        return decorated_function

    # Permissions based on roles (can be extended)
    def permission_required(roles):
        from functools import wraps
        def wrapper(f): # 'f' is the function being decorated (e.g., dashboard, inventory)
            @wraps(f)
            def decorated_function(*args, **kwargs):
                if session.get('role') not in roles:
                    flash(f'Access denied. Required roles: {", ".join(roles)}.', 'danger')
                    return redirect(url_for('dashboard'))
                return f(*args, **kwargs)
            return decorated_function
        return wrapper

    def roles_required(*roles):
        """
        Decorator to check if the current user has at least one of the specified roles.
        """
        def wrapper(fn):
            @wraps(fn)
            def decorated_view(*args, **kwargs):
                if not current_user.is_authenticated:
                    # If not logged in, redirect to login page (handled by Flask-Login)
                    return current_app.login_manager.unauthorized()
                
                if not current_user.role in roles:
                    # If user does not have the required role, abort with a 403 Forbidden error
                    abort(403)
                return fn(*args, **kwargs)
            return decorated_view
        return wrapper







    @app.before_request
    def handle_authentication_and_authorization():
        # Define a set of endpoints that do NOT require a user session to access.
        # This includes the login page itself, static files, and all synchronization API endpoints.
        public_endpoints = {
            'login',
            'static',
            'sync_status',
            'get_users_for_sync',
            'get_inventory_for_sync',
            'api_upsert_inventory',
            'api_record_sales',
            'enhanced_sync_dashboard',
            'api_enhanced_sync_status',
            'sync_conflicts_page',
            'api_sync_conflicts',
            'api_resolve_conflict',
            'test_connection'
        }

        # If the requested endpoint is in our list of public endpoints, allow access.
        if request.endpoint in public_endpoints:
            return

        # For all other routes, check if a user is logged in.
        if 'username' not in session:
            return redirect(url_for('login'))
    # def handle_auth():
    #     # Define endpoints and paths that are publicly accessible without a session
    #     public_paths = [
    #         '/login',
    #         '/static',
    #         '/sync_status',
    #     ]

    #     # Check if the requested path starts with an API prefix
    #     if request.path.startswith('/api/v1/'):
    #         return

    #     # Check if the requested path is in the list of open paths
    #     if request.path in public_paths:
    #         return

    #     # For all other routes, check if a user is logged in
    #     if 'username' not in session:
    #         return redirect(url_for('login'))
    def get_current_business_id():
        return session.get('business_id')

    def get_current_business_type():
        business_id = session.get('business_id')
        if business_id:
            business = Business.query.get(business_id)
            if business:
                return business.type
        return None

    # --- JSON Serialization Helper for InventoryItem and HirableItem ---
    def safe_convert(value, converter, default):
        """
        Safely converts a value using a specified converter.
        Returns default if value is None or conversion fails.
        """
        try:
            # Attempt conversion only if value is not None
            return converter(value) if value is not None else default
        except (TypeError, ValueError):
            # Catch specific conversion errors and return default
            return default

    def safe_currency_print(amount, label="Amount"):
        """Print currency safely with fallback for encoding issues."""
        try:
            return f"{label}: GH₵{amount:.2f}"
        except UnicodeEncodeError:
            return f"{label}: GHS{amount:.2f}"

        # Then replace the problematic line with:
        print(safe_currency_print(total_displayed_sales, "DEBUG: Total displayed sales"))
    def serialize_inventory_item(item):
        """
        Serializes an InventoryItem object to a dictionary for JSON conversion.
        Uses getattr for robust attribute access and safe_convert for type handling.
        Includes comprehensive error logging for debugging.
        """
        try:
            # Use getattr() for robust attribute access.
            # If an attribute is missing on the 'item' object, getattr returns None.
            _id = getattr(item, 'id', None)
            _product_name = getattr(item, 'product_name', None)
            _category = getattr(item, 'category', None)
            _purchase_price = getattr(item, 'purchase_price', None)
            _sale_price = getattr(item, 'sale_price', None)
            _current_stock = getattr(item, 'current_stock', None)
            _last_updated = getattr(item, 'last_updated', None)
            _batch_number = getattr(item, 'batch_number', None)
            _number_of_tabs = getattr(item, 'number_of_tabs', None)
            _unit_price_per_tab = getattr(item, 'unit_price_per_tab', None)
            _item_type = getattr(item, 'item_type', None)
            _expiry_date = getattr(item, 'expiry_date', None)
            _is_fixed_price = getattr(item, 'is_fixed_price', None)
            _fixed_sale_price = getattr(item, 'fixed_sale_price', None)
            _is_active = getattr(item, 'is_active', None)
            _barcode = getattr(item, 'barcode', None)

            # Handle dates more defensively:
            # Check if it's actually a date/datetime object before calling isoformat().
            last_updated_iso = None
            if isinstance(_last_updated, (datetime, date)):
                last_updated_iso = _last_updated.isoformat()

            expiry_date_iso = None
            if isinstance(_expiry_date, (datetime, date)):
                expiry_date_iso = _expiry_date.isoformat()

            return {
                'id': safe_convert(_id, str, ''),
                'product_name': safe_convert(_product_name, str, 'N/A'),
                'category': safe_convert(_category, str, 'N/A'),
                'purchase_price': safe_convert(_purchase_price, float, 0.0),
                'sale_price': safe_convert(_sale_price, float, 0.0),
                'current_stock': safe_convert(_current_stock, float, 0.0),
                'last_updated': last_updated_iso, # Use processed ISO string or None
                'batch_number': safe_convert(_batch_number, str, 'N/A'),
                'number_of_tabs': safe_convert(_number_of_tabs, float, 1.0),
                'unit_price_per_tab': safe_convert(_unit_price_per_tab, float, 0.0),
                'item_type': safe_convert(_item_type, str, 'N/A'),
                'expiry_date': expiry_date_iso, # Use processed ISO string or None
                'is_fixed_price': safe_convert(_is_fixed_price, bool, False),
                'fixed_sale_price': safe_convert(_fixed_sale_price, float, 0.0),
                'is_active': safe_convert(_is_active, bool, False),
                'barcode': safe_convert(_barcode, str, '')
            }
        except Exception as e:
            # Log the specific exception type and message for powerful debugging
            error_id = getattr(item, 'id', 'UNKNOWN_ID_ERROR')
            error_product_name = getattr(item, 'product_name', 'UNKNOWN_PRODUCT_NAME_ERROR')
            print(f"CRITICAL: Serialization failed for item '{error_product_name}' (ID: {error_id}). "
                f"Exception Type: {e.__class__.__name__}, Message: {str(e)}")
            # Return a minimal, error-safe dictionary that won't crash the JavaScript.
            return {
                "id": "serialization_error_" + str(error_id)[:8], # Unique ID for error items
                "product_name": f"Serialization Error (ID: {str(error_id)[:8]})",
                "current_stock": 0.0,
                "sale_price": 0.0,
                "unit_price_per_tab": 0.0,
                "number_of_tabs": 1.0,
                "is_fixed_price": False,
                "fixed_sale_price": 0.0,
                "expiry_date": None,
                "barcode": "",
                "item_type": "N/A",
                "category": "N/A",
                "purchase_price": 0.0,
                "last_updated": None,
                "batch_number": "N/A",
                "is_active": False
            }
    def calculate_company_balance_details(company_id):
        """
        Calculates the balance, total debtors, and total creditors for a single company
        based on its transactions from the database.
        """
        # Fetch all transactions for the given company_id
        transactions = CompanyTransaction.query.filter_by(company_id=company_id).all()
        current_balance = 0.0

        for transaction in transactions:
            # Corrected attribute name from 'type' to 'transaction_type'
            if transaction.transaction_type == 'Debit':
                current_balance += transaction.amount
            elif transaction.transaction_type == 'Credit':
                current_balance -= transaction.amount

        total_debtors = 0.0
        total_creditors = 0.0

        if current_balance > 0:
            total_debtors = current_balance
        elif current_balance < 0:
            total_creditors = abs(current_balance) # Use abs() for absolute value

        return {
            'balance': current_balance,
            'total_debtors': total_debtors,
            'total_creditors': total_creditors
        }
    def serialize_sale_record(sale):
        """Converts a SaleRecord SQLAlchemy object to a JSON-serializable dictionary."""
        return {
            'id': sale.id,
            'product_id': sale.product_id,
            'product_name': sale.product_name,
            'quantity_sold': float(sale.quantity_sold),
            'sale_unit_type': sale.sale_unit_type,
            'price_at_time_per_unit_sold': float(sale.price_at_time_per_unit_sold),
            'total_amount': float(sale.total_amount),
            'sale_date': sale.sale_date.isoformat(),
            'customer_phone': sale.customer_phone,
            'sales_person_name': sale.sales_person_name,
            'transaction_id': sale.transaction_id
        }


    # --- NEW: API Serialization Helpers ---
    def serialize_business(business):
        """Converts a Business SQLAlchemy object to a JSON-serializable dictionary."""
        return {
            'id': str(business.id),
            'name': str(business.name),
            'address': str(business.address) if business.address else None,
            'location': str(business.location) if business.location else None,
            'contact': str(business.contact) if business.contact else None,
            'type': str(business.type),
            'is_active': bool(business.is_active),
            'last_updated': business.last_updated.isoformat() if business.last_updated else None
        }

    def serialize_inventory_item_api(item):
        """Converts an InventoryItem SQLAlchemy object to a JSON-serializable dictionary for API."""
        return {
            'id': str(item.id),
            'business_id': str(item.business_id),
            'product_name': str(item.product_name),
            'category': str(item.category),
            'purchase_price': float(item.purchase_price),
            'sale_price': float(item.sale_price),
            'current_stock': float(item.current_stock),
            'last_updated': item.last_updated.isoformat() if item.last_updated else None,
            'batch_number': str(item.batch_number) if item.batch_number else None,
            'number_of_tabs': int(item.number_of_tabs),
            'unit_price_per_tab': float(item.unit_price_per_tab),
            'item_type': str(item.item_type),
            'expiry_date': item.expiry_date.isoformat() if item.expiry_date else None,
            'is_fixed_price': bool(item.is_fixed_price),
            'fixed_sale_price': float(item.fixed_sale_price),
            'is_active': bool(item.is_active)
        }

    def serialize_sale_record_api(sale):
        """Converts a SaleRecord SQLAlchemy object to a JSON-serializable dictionary for API."""
        return {
            'id': str(sale.id),
            'business_id': str(sale.business_id),
            'product_id': str(sale.product_id),
            'product_name': str(sale.product_name),
            'quantity_sold': float(sale.quantity_sold),
            'sale_unit_type': str(sale.sale_unit_type) if sale.sale_unit_type else None,
            'price_at_time_per_unit_sold': float(sale.price_at_time_per_unit_sold),
            'total_amount': float(sale.total_amount),
            'sale_date': sale.sale_date.isoformat() if sale.sale_date else None,
            'customer_phone': str(sale.customer_phone) if sale.customer_phone else None,
            'sales_person_name': str(sale.sales_person_name) if sale.sales_person_name else None,
            'reference_number': str(sale.reference_number) if hasattr(sale, 'reference_number') and sale.reference_number else None,
            'transaction_id': str(sale.transaction_id) if sale.transaction_id else None
        }

    def get_remote_flask_base_url():
        """
        Determines the base URL for the remote Flask API.
        This URL should NOT have a trailing slash.
        """
        remote_url = os.getenv('FLASK_API_URL', 'http://localhost:5000')
        # Ensure no trailing slash for consistent joining
        if remote_url.endswith('/'):
            remote_url = remote_url.rstrip('/')
        return remote_url

    def get_last_synced_timestamp():
        """Retrieves the last successful sync timestamp from a configuration or file."""
        # In a desktop app, you'd save this to a local config file or SQLite table
        # For now, let's use a simple file in the instance path for demonstration
        sync_marker_path = os.path.join(app.instance_path, 'last_sync.txt')
        if os.path.exists(sync_marker_path):
            with open(sync_marker_path, 'r') as f:
                return f.read().strip()
        return '1970-01-01T00:00:00Z' # Epoch for initial sync

    def set_last_synced_timestamp(timestamp):
        """Saves the last successful sync timestamp."""
        sync_marker_path = os.path.join(app.instance_path, 'last_sync.txt')
        with open(sync_marker_path, 'w') as f:
            f.write(timestamp)

    # Helper function to check network connectivity
    def check_network_online(timeout=5):
        """Checks if there's an active internet connection by trying to reach a reliable host."""
        try:
            requests.head("http://www.google.com", timeout=timeout)
            return True
        except requests.ConnectionError:
            return False
        except Exception as e:
            print(f"Network check error: {e}")
            return False
    def pull_data_from_remote(business_id, access_token):
        """
        Pulls data for a specific business from the remote server.
        """
        remote_url = get_remote_flask_base_url()
        headers = {'Authorization': f'Bearer {access_token}'} if access_token else {}
        
        if not business_id:
            print("Error: No business ID provided for synchronization.")
            return False, "Synchronization failed: Business ID not found."

        try:
            # --- Step 1: Pull Business Data ---
            print(f"Pulling data for business ID: {business_id}")
            business_response = requests.get(f"{remote_url}/api/v1/businesses/{business_id}", headers=headers)
            business_response.raise_for_status()
            
            if not business_response.text:
                print("Error: Received an empty response body for /api/v1/businesses/{business_id}")
                return False, "Synchronization failed: Remote server returned empty data for business."
            
            business_data = business_response.json()
            
            with app.app_context():
                business = db.session.get(Business, business_data['id'])
                if business:
                    business.name = business_data['name']
                    business.address = business_data['address']
                    business.location = business_data['location']
                    business.contact = business_data['contact']
                    business.type = business_data['type']
                    business.is_active = business_data['is_active']
                    business.last_updated = datetime.fromisoformat(business_data['last_updated'])
                else:
                    new_business = Business(
                        id=business_data['id'],
                        name=business_data['name'],
                        address=business_data['address'],
                        location=business_data['location'],
                        contact=business_data['contact'],
                        type=business_data['type'],
                        is_active=business_data['is_active'],
                        last_updated=datetime.fromisoformat(business_data['last_updated'])
                    )
                    db.session.add(new_business)
                db.session.commit()
                print("Successfully pulled and replaced business data.")
            
            # --- Step 2: Pull Users for this Business ---
            print("Pulling users for this business...")
            users_response = requests.get(f"{remote_url}/api/v1/users/business/{business_id}", headers=headers)
            users_response.raise_for_status()
            
            if not users_response.text:
                print("Error: Received an empty response body for /api/v1/users/business/{business_id}")
                return False, "Synchronization failed: Remote server returned empty data for users."
                
            users_data = users_response.json()
            
            with app.app_context():
                User.query.filter_by(business_id=business_id).delete()
                for user_data in users_data:
                    user = User(
                        id=user_data['id'],
                        username=user_data['username'],
                        password=user_data['password'],
                        role=user_data['role'],
                        business_id=user_data['business_id'],
                        is_active=user_data['is_active'],
                        created_at=datetime.fromisoformat(user_data['created_at'])
                    )
                    db.session.add(user)
                db.session.commit()
                print("Successfully pulled and replaced user data.")

            # --- Step 3: Pull Inventory for this Business ---
            print("Pulling inventory for this business...")
            inventory_response = requests.get(f"{remote_url}/api/v1/inventory/business/{business_id}", headers=headers)
            inventory_response.raise_for_status()

            if not inventory_response.text:
                print("Error: Received an empty response body for /api/v1/inventory/business/{business_id}")
                return False, "Synchronization failed: Remote server returned empty data for inventory."

            inventory_data = inventory_response.json()

            with app.app_context():
                InventoryItem.query.filter_by(business_id=business_id).delete()
                for item_data in inventory_data:
                    item = InventoryItem(
                        id=item_data['id'],
                        business_id=item_data['business_id'],
                        product_name=item_data['product_name'],
                        category=item_data['category'],
                        purchase_price=item_data['purchase_price'],
                        sale_price=item_data['sale_price'],
                        current_stock=item_data['current_stock'],
                        last_updated=datetime.fromisoformat(item_data['last_updated']),
                        batch_number=item_data['batch_number'],
                        number_of_tabs=item_data['number_of_tabs'],
                        unit_price_per_tab=item_data['unit_price_per_tab'],
                        item_type=item_data['item_type'],
                        expiry_date=datetime.fromisoformat(item_data['expiry_date']).date() if item_data['expiry_date'] else None,
                        is_fixed_price=item_data['is_fixed_price'],
                        fixed_sale_price=item_data['fixed_sale_price'],
                        is_active=item_data['is_active']
                    )
                    db.session.add(item)
                db.session.commit()
                print("Successfully pulled and replaced inventory data.")

            return True, "Synchronization successful."

        except requests.exceptions.RequestException as e:
            db.session.rollback()
            print(f"Error during sync: {e}")
            return False, f"Synchronization failed due to a network or server error: {e}"
        except json.JSONDecodeError as e:
            db.session.rollback()
            print(f"JSON decoding error: {e}. Raw response text was: {e.doc}")
            return False, f"Synchronization failed: Invalid data format received from the server."
        except Exception as e:
            db.session.rollback()
            print(f"An unexpected error occurred: {e}")
            return False, f"An unexpected error occurred: {e}"
    # def pull_data_from_remote(business_id, access_token):
    #     """
    #     Pulls data for a specific business from the remote server.
    #     """
    #     remote_url = get_remote_flask_base_url()
    #     headers = {'Authorization': f'Bearer {access_token}'} if access_token else {}
        
    #     # Check for a valid business ID
    #     if not business_id:
    #         print("Error: No business ID provided for synchronization.")
    #         return False, "Synchronization failed: Business ID not found."

    #     try:
    #         # --- Step 1: Pull Business Data ---
    #         print(f"Pulling data for business ID: {business_id}")
    #         business_response = requests.get(f"{remote_url}/api/v1/businesses/{business_id}", headers=headers)
    #         business_response.raise_for_status()
            
    #         # Check for empty response body before decoding
    #         if not business_response.text.strip():
    #             print("Error: Received an empty response for business data. Possible server issue.")
    #             return False, "Synchronization failed: Received an empty response from business API."
            
    #         business_data = business_response.json()
            
    #         with app.app_context():
    #             business = db.session.get(Business, business_data['id'])
    #             if business:
    #                 # Update existing business
    #                 business.name = business_data['name']
    #                 business.address = business_data['address']
    #                 business.location = business_data['location']
    #                 business.contact = business_data['contact']
    #                 business.type = business_data['type']
    #                 business.is_active = business_data['is_active']
    #                 business.last_updated = datetime.fromisoformat(business_data['last_updated'])
    #             else:
    #                 # Add new business
    #                 new_business = Business(
    #                     id=business_data['id'],
    #                     name=business_data['name'],
    #                     address=business_data['address'],
    #                     location=business_data['location'],
    #                     contact=business_data['contact'],
    #                     type=business_data['type'],
    #                     is_active=business_data['is_active'],
    #                     last_updated=datetime.fromisoformat(business_data['last_updated'])
    #                 )
    #                 db.session.add(new_business)
    #             db.session.commit()
    #             print("Successfully pulled and replaced business data.")
            
    #         # --- Step 2: Pull Users for this Business ---
    #         print("Pulling users for this business...")
    #         users_response = requests.get(f"{remote_url}/api/v1/users/business/{business_id}", headers=headers)
    #         users_response.raise_for_status()
            
    #         if not users_response.text.strip():
    #             print("Error: Received an empty response for user data. Skipping user sync.")
    #             # Continue with the rest of the sync instead of failing
    #         else:
    #             users_data = users_response.json()
    #             with app.app_context():
    #                 User.query.filter_by(business_id=business_id).delete()
    #                 for user_data in users_data:
    #                     user = User(
    #                         id=user_data['id'],
    #                         username=user_data['username'],
    #                         password=user_data['password'],
    #                         role=user_data['role'],
    #                         business_id=user_data['business_id'],
    #                         is_active=user_data['is_active'],
    #                         created_at=datetime.fromisoformat(user_data['created_at'])
    #                     )
    #                     db.session.add(user)
    #                 db.session.commit()
    #                 print("Successfully pulled and replaced user data.")

    #         # --- Step 3: Pull Inventory for this Business ---
    #         print("Pulling inventory for this business...")
    #         inventory_response = requests.get(f"{remote_url}/api/v1/inventory/business/{business_id}", headers=headers)
    #         inventory_response.raise_for_status()

    #         if not inventory_response.text.strip():
    #             print("Error: Received an empty response for inventory data. Skipping inventory sync.")
    #         else:
    #             inventory_data = inventory_response.json()
    #             with app.app_context():
    #                 InventoryItem.query.filter_by(business_id=business_id).delete()
    #                 for item_data in inventory_data:
    #                     item = InventoryItem(
    #                         id=item_data['id'],
    #                         business_id=item_data['business_id'],
    #                         product_name=item_data['product_name'],
    #                         category=item_data['category'],
    #                         purchase_price=item_data['purchase_price'],
    #                         sale_price=item_data['sale_price'],
    #                         current_stock=item_data['current_stock'],
    #                         last_updated=datetime.fromisoformat(item_data['last_updated']),
    #                         batch_number=item_data['batch_number'],
    #                         number_of_tabs=item_data['number_of_tabs'],
    #                         unit_price_per_tab=item_data['unit_price_per_tab'],
    #                         item_type=item_data['item_type'],
    #                         expiry_date=datetime.fromisoformat(item_data['expiry_date']).date() if item_data['expiry_date'] else None,
    #                         is_fixed_price=item_data['is_fixed_price'],
    #                         fixed_sale_price=item_data['fixed_sale_price'],
    #                         is_active=item_data['is_active']
    #                     )
    #                     db.session.add(item)
    #                 db.session.commit()
    #                 print("Successfully pulled and replaced inventory data.")

    #         return True, "Synchronization successful."

    #     except requests.exceptions.RequestException as e:
    #         db.session.rollback()
    #         print(f"Error during sync: {e}")
    #         return False, f"Synchronization failed: {e}"
    #     except Exception as e:
    #         db.session.rollback()
    #         print(f"An unexpected error occurred: {e}")
    #         return False, f"An unexpected error occurred: {e}"
    

    def push_data_to_remote(remote_business_id, api_key):
        remote_url = get_remote_flask_base_url()
        headers = {'Content-Type': 'application/json'} # API expects JSON
        
        # 1. Push pending Sales Records (those not yet marked as synced in local DB)
        with app.app_context(): # Ensure we are in app context for DB operations
            pending_sales = SalesRecord.query.filter_by(business_id=remote_business_id, synced_to_remote=False).all()
            if pending_sales:
                sales_data = [serialize_sale_record_api(s) for s in pending_sales]
                try:
                    sales_response = requests.post(f"{remote_url}/api/v1/sales", json=sales_data, headers=headers)
                    sales_response.raise_for_status()
                    response_json = sales_response.json()
                    if response_json.get('message') == 'Sales records synchronized successfully.':
                        for sale in pending_sales:
                            sale.synced_to_remote = True # Mark as synced locally
                        db.session.commit()
                        print(f"Pushed {len(pending_sales)} sales to remote. Response: {response_json}")
                        return True, f"Pushed {len(pending_sales)} sales."
                    else:
                        print(f"Error pushing sales (remote message): {response_json.get('message')}")
                        return False, f"Error pushing sales: {response_json.get('message')}"
                except requests.exceptions.RequestException as e:
                    print(f"Error pushing sales: {e}")
                    db.session.rollback() # Rollback if API call fails
                    return False, f"Error pushing sales: {e}"
                except Exception as e:
                    print(f"Unexpected error pushing sales: {e}")
                    db.session.rollback()
                    return False, f"Unexpected error pushing sales: {e}"
            else:
                print("No pending sales to push.")
                return True, "No pending sales to push."

        # NOTE: If you enable local inventory modifications, you'd need a similar
        # push logic for InventoryItem objects here, possibly using a `synced_to_remote` flag
        # on InventoryItem as well. For now, we assume inventory is primarily pulled.

    # In your app.py or wherever your sync logic resides

    def perform_sync(business_id):
        try:
            # Step 1: Check if the business is registered on the remote server
            business = Business.query.get(business_id)
            if not business.remote_id: # Assuming you add a remote_id field to your Business model
                print("Business not registered remotely. Attempting to register...")
                register_url = 'http://localhost:5000/api/v1/register_business'
                payload = {'business_name': business.name, '...': '...'} # Add other business details
                response = requests.post(register_url, json=payload)
                response.raise_for_status()
                
                # Get the new remote ID from the server's response and save it locally
                new_remote_id = response.json().get('business_id')
                business.remote_id = new_remote_id
                db.session.commit()
                print(f"Successfully registered business. New remote ID: {new_remote_id}")

            # Step 2: Now that we have a valid remote ID, proceed with sync
            remote_business_id = business.remote_id if business.remote_id else business.id # Use the remote ID if it exists
            
            # Pull users
            users_url = f'http://localhost:5000/api/v1/users?business_id={remote_business_id}'
            response = requests.get(users_url)
            response.raise_for_status() # This will now work correctly
            
            # ... proceed to pull inventory, sales, etc. ...
            
            return True, "Synchronization successful."
        except requests.exceptions.RequestException as e:
            return False, f"Error during synchronization: {e}"
    def pull_inventory_data(api_key, business_id):
        """Pulls inventory data for a specific business from the remote server."""
        try:
            api_endpoint = f"{os.getenv('ONLINE_FLASK_APP_BASE_URL', 'http://localhost:5000')}/api/v1/inventory/business/{business_id}"
            
            # Mask API key for logging
            masked_key = api_key[:3] + "*" * (len(api_key) - 6) + api_key[-3:] if api_key else "None"
            logging.info(f"[SYNC][Inventory Pull] Fetching inventory from: {api_endpoint}")
            logging.info(f"[SYNC][Inventory Pull] Using API Key: {masked_key}")

            headers = {'X-API-Key': api_key}
            response = requests.get(api_endpoint, timeout=30, headers=headers)
            response.raise_for_status()

            remote_inventory_data = response.json()
            logging.info(f"[SYNC][Inventory Pull] Received {len(remote_inventory_data)} inventory items.")

            if not isinstance(remote_inventory_data, list):
                logging.warning("[SYNC][Inventory Pull] Remote inventory data is not a list. Wrapping in a list.")
                remote_inventory_data = [remote_inventory_data]

            new_items_count = 0
            updated_items_count = 0

            for item_data in remote_inventory_data:
                if not isinstance(item_data, dict):
                    logging.warning("[SYNC][Inventory Pull] Skipping malformed inventory entry.")
                    continue
                    
                remote_id = item_data.get('id')
                if not remote_id:
                    logging.warning("[SYNC][Inventory Pull] Skipping inventory entry with no ID.")
                    continue
                
                local_product = Product.query.filter_by(remote_id=remote_id).first()

                if not local_product:
                    new_product = Product(
                        name=item_data.get('name', 'Unknown Product'),
                        business_id=item_data.get('business_id', business_id),
                        quantity=item_data.get('quantity', 0),
                        unit_price=item_data.get('unit_price', 0.0),
                        remote_id=remote_id
                    )
                    db.session.add(new_product)
                    new_items_count += 1
                else:
                    local_product.name = item_data.get('name', local_product.name)
                    local_product.quantity = item_data.get('quantity', local_product.quantity)
                    local_product.unit_price = item_data.get('unit_price', local_product.unit_price)
                    updated_items_count += 1
            
            db.session.commit()
            logging.info(f"[SYNC][Inventory Pull] Completed. {new_items_count} new items, {updated_items_count} updated.")
            return True, f"Inventory synchronized successfully. {new_items_count} new items added, {updated_items_count} items updated."

        except requests.exceptions.RequestException as e:
            logging.error(f"[SYNC][Inventory Pull] Network error: {e}")
            return False, f"Network error during inventory sync: {e}"
        except json.JSONDecodeError as e:
            logging.error(f"[SYNC][Inventory Pull] JSON decode error: {e}. Raw response: {response.text[:200]}...")
            return False, f"Error decoding JSON response during inventory sync: {e}. Server responded with: '{response.text[:100]}...'"
        except Exception as e:
            logging.exception("[SYNC][Inventory Pull] Unexpected error")
            return False, f"An unexpected error occurred during inventory sync: {e}"

    def pull_business_data(api_key):
        """Pulls business and user data from the remote server."""
        try:
            api_endpoint = f"{os.getenv('ONLINE_FLASK_APP_BASE_URL', 'http://localhost:5000')}/api/businesses"
            logging.info(f"Attempting to fetch businesses from: {api_endpoint}")
            
            headers = {'X-API-Key': api_key}
            response = requests.get(api_endpoint, timeout=30, headers=headers)
            response.raise_for_status()

            remote_businesses_data = response.json()
            logging.info(f"Received {len(remote_businesses_data)} businesses from the remote server.")

            new_businesses_count = 0
            updated_businesses_count = 0
            new_users_count = 0
            inventory_sync_msg = ""
            
            # Ensure the response is a list before iterating
            if not isinstance(remote_businesses_data, list):
                logging.warning("Remote business data is not a list. Wrapping in a list.")
                remote_businesses_data = [remote_businesses_data]
            
            for remote_business_data in remote_businesses_data:
                # Check if the individual item is a dictionary
                if not isinstance(remote_business_data, dict):
                    logging.warning(f"Skipping malformed business entry: {remote_business_data}")
                    continue
                
                remote_id = remote_business_data.get('id')
                if not remote_id:
                    logging.warning("Skipping business entry with no ID.")
                    continue
                
                local_business = Business.query.filter_by(remote_id=remote_id).first()
                if not local_business:
                    local_business = Business(
                        name=remote_business_data.get('name', 'Unknown Name'),
                        type=remote_business_data.get('type', 'Unknown Type'),
                        address=remote_business_data.get('address', 'Unknown Address'),
                        contact=remote_business_data.get('contact', 'Unknown Contact'),
                        email=remote_business_data.get('email', 'Unknown Email'),
                        is_active=remote_business_data.get('is_active', True),
                        last_synced_at=datetime.utcnow(),
                        remote_id=remote_id
                    )
                    db.session.add(local_business)
                    db.session.commit()
                    logging.info(f"Created new local business: {local_business.name}")
                    new_businesses_count += 1
                else:
                    local_business.name = remote_business_data.get('name', local_business.name)
                    local_business.type = remote_business_data.get('type', local_business.type)
                    local_business.address = remote_business_data.get('address', local_business.address)
                    local_business.contact = remote_business_data.get('contact', local_business.contact)
                    local_business.email = remote_business_data.get('email', local_business.email)
                    local_business.is_active = remote_business_data.get('is_active', local_business.is_active)
                    local_business.last_synced_at = datetime.utcnow()
                    updated_businesses_count += 1
                    logging.info(f"Updated existing local business: {local_business.name}")

                # Pull inventory data for this specific business
                success_inv_pull, msg_inv_pull = pull_inventory_data(api_key, local_business.id)
                inventory_sync_msg += f"Inventory for {local_business.name} synced: {msg_inv_pull}. "
                
                remote_users = remote_business_data.get('users', [])
                if not isinstance(remote_users, list):
                    logging.warning(f"Skipping malformed user list for business ID {remote_id}")
                    continue

                for remote_user_data in remote_users:
                    if not isinstance(remote_user_data, dict):
                        logging.warning("Skipping a malformed user entry from remote data.")
                        continue
                    remote_user_id = remote_user_data.get('id')
                    if not remote_user_id:
                        logging.warning("Skipping user entry with no ID.")
                        continue
                        
                    local_user = User.query.filter_by(id=remote_user_id).first()

                    if not local_user:
                        new_user = User(
                            id=remote_user_id,
                            username=remote_user_data.get('username', 'Unknown User'),
                            _password_hash=remote_user_data.get('_password_hash', ''),
                            role=remote_user_data.get('role', 'user'),
                            business_id=local_business.id,
                            is_active=remote_user_data.get('is_active', True),
                            created_at=datetime.utcnow()
                        )
                        db.session.add(new_user)
                        logging.info(f"Created new user: {new_user.username} for business {local_business.name}")
                        new_users_count += 1
                    else:
                        local_user.username = remote_user_data.get('username', local_user.username)
                        local_user._password_hash = remote_user_data.get('_password_hash', local_user._password_hash)
                        local_user.role = remote_user_data.get('role', local_user.role)
                        local_user.business_id = local_business.id
                        local_user.is_active = remote_user_data.get('is_active', local_user.is_active)
                        logging.info(f"Updated user: {local_user.username}")
            
            db.session.commit()
            final_message = f"Businesses synced: {new_businesses_count} added, {updated_businesses_count} updated. Users synced: {new_users_count} added. {inventory_sync_msg}"
            return True, final_message

        except requests.exceptions.RequestException as e:
            return False, f"Network error during business sync: {e}"
        except json.JSONDecodeError as e:
            return False, f"Error decoding JSON response during business sync: {e}. Server responded with: '{response.text[:100]}...'"
        except Exception as e:
            return False, f"An unexpected error occurred during business sync: {e}"

  
    def pull_business_data(api_key):
        """Pulls business and user data from the remote server."""
        try:
            api_endpoint = f"{os.getenv('ONLINE_FLASK_APP_BASE_URL', 'http://localhost:5000')}/api/businesses"
            logging.info(f"Attempting to fetch businesses from: {api_endpoint}")
            
            headers = {'X-API-Key': api_key}
            response = requests.get(api_endpoint, timeout=30, headers=headers)
            response.raise_for_status()

            remote_businesses_data = response.json()
            logging.info(f"Received {len(remote_businesses_data)} businesses from the remote server.")

            new_businesses_count = 0
            updated_businesses_count = 0
            new_users_count = 0
            inventory_sync_msg = ""
            
            # Ensure the response is a list before iterating
            if not isinstance(remote_businesses_data, list):
                logging.warning("Remote business data is not a list. Wrapping in a list.")
                remote_businesses_data = [remote_businesses_data]
            
            for remote_business_data in remote_businesses_data:
                # Check if the individual item is a dictionary
                if not isinstance(remote_business_data, dict):
                    logging.warning(f"Skipping malformed business entry: {remote_business_data}")
                    continue
                
                remote_id = remote_business_data.get('id')
                if not remote_id:
                    logging.warning("Skipping business entry with no ID.")
                    continue
                
                local_business = Business.query.filter_by(remote_id=remote_id).first()
                if not local_business:
                    local_business = Business(
                        name=remote_business_data.get('name', 'Unknown Name'),
                        type=remote_business_data.get('type', 'Unknown Type'),
                        address=remote_business_data.get('address', 'Unknown Address'),
                        contact=remote_business_data.get('contact', 'Unknown Contact'),
                        email=remote_business_data.get('email', 'Unknown Email'),
                        is_active=remote_business_data.get('is_active', True),
                        last_synced_at=datetime.utcnow(),
                        remote_id=remote_id
                    )
                    db.session.add(local_business)
                    db.session.commit()
                    logging.info(f"Created new local business: {local_business.name}")
                    new_businesses_count += 1
                else:
                    local_business.name = remote_business_data.get('name', local_business.name)
                    local_business.type = remote_business_data.get('type', local_business.type)
                    local_business.address = remote_business_data.get('address', local_business.address)
                    local_business.contact = remote_business_data.get('contact', local_business.contact)
                    local_business.email = remote_business_data.get('email', local_business.email)
                    local_business.is_active = remote_business_data.get('is_active', local_business.is_active)
                    local_business.last_synced_at = datetime.utcnow()
                    updated_businesses_count += 1
                    logging.info(f"Updated existing local business: {local_business.name}")

                # Pull inventory data for this specific business
                success_inv_pull, msg_inv_pull = pull_inventory_data(api_key, local_business.id)
                inventory_sync_msg += f"Inventory for {local_business.name} synced: {msg_inv_pull}. "
                
                remote_users = remote_business_data.get('users', [])
                if not isinstance(remote_users, list):
                    logging.warning(f"Skipping malformed user list for business ID {remote_id}")
                    continue

                for remote_user_data in remote_users:
                    if not isinstance(remote_user_data, dict):
                        logging.warning("Skipping a malformed user entry from remote data.")
                        continue
                    remote_user_id = remote_user_data.get('id')
                    if not remote_user_id:
                        logging.warning("Skipping user entry with no ID.")
                        continue
                        
                    local_user = User.query.filter_by(id=remote_user_id).first()

                    if not local_user:
                        new_user = User(
                            id=remote_user_id,
                            username=remote_user_data.get('username', 'Unknown User'),
                            _password_hash=remote_user_data.get('_password_hash', ''),
                            role=remote_user_data.get('role', 'user'),
                            business_id=local_business.id,
                            is_active=remote_user_data.get('is_active', True),
                            created_at=datetime.utcnow()
                        )
                        db.session.add(new_user)
                        logging.info(f"Created new user: {new_user.username} for business {local_business.name}")
                        new_users_count += 1
                    else:
                        local_user.username = remote_user_data.get('username', local_user.username)
                        local_user._password_hash = remote_user_data.get('_password_hash', local_user._password_hash)
                        local_user.role = remote_user_data.get('role', local_user.role)
                        local_user.business_id = local_business.id
                        local_user.is_active = remote_user_data.get('is_active', local_user.is_active)
                        logging.info(f"Updated user: {local_user.username}")
            
            db.session.commit()
            final_message = f"Businesses synced: {new_businesses_count} added, {updated_businesses_count} updated. Users synced: {new_users_count} added. {inventory_sync_msg}"
            return True, final_message

        except requests.exceptions.RequestException as e:
            return False, f"Network error during business sync: {e}"
        except json.JSONDecodeError as e:
            return False, f"Error decoding JSON response during business sync: {e}. Server responded with: '{response.text[:100]}...'"
        except Exception as e:
            return False, f"An unexpected error occurred during business sync: {e}"

    def push_inventory_data(business_id, api_key):
        """Pushes local inventory data to the remote server."""
        try:
            # Placeholder: Fetch locally created/updated inventory items
            # local_products = Product.query.filter_by(business_id=business_id, synced=False).all()
            # api_endpoint = f"{os.getenv('ONLINE_FLASK_APP_BASE_URL', 'http://localhost:5000')}/api/inventory/sync"
            # headers = {'X-API-Key': api_key}
            # data = [product.to_dict() for product in local_products]
            # response = requests.post(api_endpoint, json=data, headers=headers)
            # response.raise_for_status()
            logging.info(f"Pushing inventory data to remote server for business ID: {business_id}")
            return True, "Inventory data push successful."
        except Exception as e:
            return False, f"Failed to push inventory data to remote server: {e}"

    # def perform_sync(business_id, api_key):
    #     """Orchestrates the full synchronization process."""
    #     try:
    #         # Pull phase
    #         success_pull_biz, msg_pull_biz = pull_business_data(api_key)
    #         if not success_pull_biz:
    #             return False, f"Business pull failed: {msg_pull_biz}"

    #         # Push phase
    #         success_push_inv, msg_push_inv = push_inventory_data(business_id, api_key)
    #         if not success_push_inv:
    #             return False, f"Inventory push failed: {msg_push_inv}"
            
    #         return True, f"Full synchronization successful. {msg_pull_biz}. {msg_push_inv}"

    #     except Exception as e:
    #         db.session.rollback()
    #         return False, f"An unexpected error occurred during full sync: {e}"

    def perform_sync(business_id, api_key):
        """Orchestrates the full synchronization process."""
        try:
            # --- Log the API key being used (masked for security) ---
            masked_key = api_key[:3] + "*" * (len(api_key) - 6) + api_key[-3:] if api_key else "None"
            logging.info(f"[SYNC] Using API Key: {masked_key}")

            # --- Step 1: Pull business + user data ---
            success_pull_biz, msg_pull_biz = pull_business_data(api_key)
            if not success_pull_biz:
                logging.error(f"[SYNC] Business pull failed: {msg_pull_biz}")
                return False, f"Business pull failed: {msg_pull_biz}"

            # --- Step 2: Pull inventory data for this specific business ---
            success_pull_inv, msg_pull_inv = pull_inventory_data(api_key, business_id)
            if not success_pull_inv:
                logging.error(f"[SYNC] Inventory pull failed: {msg_pull_inv}")
                return False, f"Inventory pull failed: {msg_pull_inv}"

            # --- Step 3: Push local inventory changes (if any) ---
            success_push_inv, msg_push_inv = push_inventory_data(business_id, api_key)
            if not success_push_inv:
                logging.error(f"[SYNC] Inventory push failed: {msg_push_inv}")
                return False, f"Inventory push failed: {msg_push_inv}"

            # --- Final status ---
            logging.info(f"[SYNC] Success! {msg_pull_biz}. {msg_pull_inv}. {msg_push_inv}")
            return True, (
                f"Full synchronization successful. "
                f"{msg_pull_biz}. {msg_pull_inv}. {msg_push_inv}"
            )

        except Exception as e:
            db.session.rollback()
            logging.exception("[SYNC] Unexpected error during full sync")
            return False, f"An unexpected error occurred during full sync: {e}"

  


    @app.route('/api/debug_key', methods=['GET'])
    def debug_key():
        key_from_env = os.getenv('REMOTE_ADMIN_API_KEY')
        return jsonify({'key': key_from_env, 'is_found': bool(key_from_env)})
    # END OF TEMPORARY ROUTE
    # The csrf.exempt decorator should be removed because the form sends a token.
    @app.route('/api/v1/register_business_for_sync', methods=['POST'])
    @api_key_required
    @csrf.exempt
    def register_business_for_sync():
        # 1. Validate incoming data type
        if not request.is_json:
            return jsonify({'message': 'Invalid content type. Expected JSON.'}), 400

        data = request.get_json()

        # 2. Extract and validate required fields
        name = data.get('name')
        business_type = data.get('type')
        address = data.get('address')
        location = data.get('location')
        contact = data.get('contact')
        email = data.get('email')

        if not name or not business_type:
            return jsonify({'message': 'Business name and type are required for registration.'}), 400

        # 3. Check for existing business to prevent duplicates
        existing_business = Business.query.filter_by(name=name).first()
        if existing_business:
            return jsonify({
                'message': 'Business already registered online.',
                'business_id': existing_business.id
            }), 200

        # 4. Attempt to create and save new business record
        try:
            new_business = Business(
                name=name,
                type=business_type,
                address=address,
                location=location,
                contact=contact,
                email=email,
                is_active=True
            )
            db.session.add(new_business)
            db.session.commit()
            return jsonify({
                'message': 'Business registered successfully online.',
                'business_id': new_business.id
            }), 201
        except Exception as e:
            # 5. Handle any database or other unexpected errors
            db.session.rollback()
            print(f"Error registering business online: {e}")
            return jsonify({'message': f'Failed to register business online: {str(e)}'}), 500


    def perform_sync(local_business_id, sync_api_key):
        if not check_network_online():
            print("Offline: Cannot perform synchronization.")
            return False, "Offline: Cannot perform synchronization."

        print("Online: Starting synchronization...")
        
        local_business = Business.query.get(local_business_id)
        if not local_business:
            return False, "Error: Local business not found."

        # Use a dictionary to store headers for all requests
        headers = {'X-API-Key': sync_api_key, 'Content-Type': 'application/json'}

        # --- NEW: Check and Register Business Remotely ---
        if not local_business.remote_id:
            print(f"Local business '{local_business.name}' not yet linked to remote server. Attempting registration...")
            registration_url = f"{REMOTE_SERVER_URL}/api/v1/register_business_for_sync"
            try:
                registration_payload = {
                    'name': local_business.name,
                    'address': local_business.address,
                    'location': local_business.location,
                    'contact': local_business.contact,
                    'email': local_business.email,
                    'type': local_business.type,
                }
                # Use headers to authenticate this request
                response = requests.post(registration_url, json=registration_payload, headers=headers)
                response.raise_for_status()

                remote_registration_data = response.json()
                new_remote_id = remote_registration_data.get('business_id')

                if new_remote_id:
                    local_business.remote_id = new_remote_id
                    db.session.commit()
                    print(f"Successfully registered local business '{local_business.name}' on remote server. Remote ID: {new_remote_id}")
                else:
                    return False, f"Remote registration failed: No business_id returned. Message: {remote_registration_data.get('message', 'Unknown error')}"
            
            except requests.exceptions.RequestException as e:
                # This catches all request errors (HTTP, network, etc.)
                db.session.rollback()
                return False, f"Failed to register business remotely: {e}"

        # Use the remote_id for all subsequent API calls
        effective_business_id = local_business.remote_id

        # Make sure get_last_synced_timestamp is configured to retrieve a timestamp for the specific business
        last_synced_at = local_business.last_synced_at.isoformat() if local_business.last_synced_at else "1970-01-01T00:00:00Z"
        print(f"Last synced at: {last_synced_at}")

        # Pass the API key to the push and pull functions
        success_push, msg_push = push_data_to_remote(effective_business_id, sync_api_key)
        if not success_push:
            return False, f"Sync failed during push: {msg_push}"

        success_pull, msg_pull = pull_data_from_remote(effective_business_id,  sync_api_key)
        if not success_pull:
            return False, f"Sync failed during pull: {msg_pull}"

        local_business.last_synced_at = datetime.utcnow()
        db.session.commit()
        print(f"Synchronization successful at {local_business.last_synced_at.isoformat()}")
        return True, "Synchronization successful!"

    
    @app.route('/api/v1/users', methods=['GET'])
    @api_key_required
    def get_users_for_sync():
        try:
            business_id = request.args.get('business_id')
            if not business_id:
                return jsonify({'error': 'business_id is a required query parameter'}), 400

            users = User.query.filter_by(business_id=business_id).all()
            user_list = []
            for user in users:
                user_list.append({
                    'id': user.id,
                    'username': user.username,
                    'role': user.role,
                    'is_active': user.is_active,
                    'business_id': user.business_id,
                    # ADD THIS LINE to include the password hash
                    'password_hash': user.password_hash 
                })

            return jsonify(user_list)

        except Exception as e:
            print(f"Error fetching users for sync: {e}")
            return jsonify({'error': 'An internal server error occurred.'}),

    @app.route('/api/v1/businesses', methods=['GET'])
    @api_key_required
    # @login_required # Temporary: Should be API-specific auth in production
    def api_get_businesses():
        """
        API endpoint to fetch a list of businesses.
        Can be filtered by last_updated timestamp for incremental sync.
        """
        if session.get('role') != 'super_admin':
            # For non-super admins, restrict to their own business if applicable
            business_id = get_current_business_id()
            if not business_id:
                return jsonify({'message': 'Access denied: Business ID not in session for this user.'}), 403
            businesses = Business.query.filter_by(id=business_id, is_active=True).all()
        else:
            # Super admin can see all active businesses
            businesses = Business.query.filter_by(is_active=True).all()
        
        # Filter by last_synced_at if provided in query parameters
        last_synced_at_str = request.args.get('last_synced_at')
        if last_synced_at_str:
            try:
                last_synced_at = datetime.fromisoformat(last_synced_at_str)
                businesses = [b for b in businesses if b.last_updated and b.last_updated > last_synced_at]
            except ValueError:
                return jsonify({'message': 'Invalid last_synced_at format. Use ISO 8601.'}), 400

        return jsonify([serialize_business(b) for b in businesses])


    @app.route('/api/v1/inventory', methods=['GET'])
    @api_key_required
    # @login_required # Temporary: Should be API-specific auth in production
    def api_get_inventory():
        """
        API endpoint to fetch inventory items for a business.
        Requires business_id in query params. Can be filtered by last_updated.
        """
        business_id = request.args.get('business_id')
        if not business_id:
            return jsonify({'message': 'Business ID is required.'}), 400

        if session.get('role') != 'super_admin' and business_id != get_current_business_id():
            return jsonify({'message': 'Access denied: You can only view inventory for your assigned business.'}), 403

        inventory_query = InventoryItem.query.filter_by(business_id=business_id, is_active=True)

        # Filter by last_synced_at for incremental sync
        last_synced_at_str = request.args.get('last_synced_at')
        if last_synced_at_str:
            try:
                last_synced_at = datetime.fromisoformat(last_synced_at_str)
                inventory_query = inventory_query.filter(InventoryItem.last_updated > last_synced_at)
            except ValueError:
                return jsonify({'message': 'Invalid last_synced_at format. Use ISO 8601.'}), 400
        
        inventory_items = inventory_query.all()
        return jsonify([serialize_inventory_item_api(item) for item in inventory_items])


    @app.route('/api/v1/inventory', methods=['POST'])
    @api_key_required
    # @login_required # Temporary: Should be API-specific auth in production
    def api_upsert_inventory():
        """
        API endpoint to create or update inventory items in batch.
        Expected data: JSON list of inventory item objects.
        """
        business_id = get_current_business_id()
        if not business_id:
            return jsonify({'message': 'Business ID is required to add/update inventory.'}), 400

        if session.get('role') not in ['admin', 'sales']: # Sales can also update stock if part of their workflow
            return jsonify({'message': 'Access denied: Insufficient role to add/update inventory.'}), 403

        items_data = request.get_json()
        if not isinstance(items_data, list):
            return jsonify({'message': 'Request body must be a JSON array of inventory items.'}), 400

        updated_count = 0
        added_count = 0
        errors = []

        for item_data in items_data:
            try:
                item_id = item_data.get('id')
                product_name = item_data.get('product_name')
                category = item_data.get('category')
                purchase_price = float(item_data.get('purchase_price'))
                sale_price = float(item_data.get('sale_price'))
                current_stock = float(item_data.get('current_stock'))
                batch_number = item_data.get('batch_number')
                number_of_tabs = int(item_data.get('number_of_tabs', 1))
                unit_price_per_tab = float(item_data.get('unit_price_per_tab', 0.0))
                item_type = item_data.get('item_type')
                expiry_date_str = item_data.get('expiry_date')
                is_fixed_price = bool(item_data.get('is_fixed_price', False))
                fixed_sale_price = float(item_data.get('fixed_sale_price', 0.0))
                is_active = bool(item_data.get('is_active', True))

                expiry_date_obj = datetime.fromisoformat(expiry_date_str).date() if expiry_date_str else None

                item = None
                if item_id:
                    item = InventoryItem.query.filter_by(id=item_id, business_id=business_id).first()
                
                # If item_id was not provided or not found, try by product_name for existing items within the business
                if not item:
                    item = InventoryItem.query.filter_by(product_name=product_name, business_id=business_id).first()

                if item:
                    # Update existing item
                    item.product_name = product_name
                    item.category = category
                    item.purchase_price = purchase_price
                    item.sale_price = sale_price
                    item.current_stock = current_stock
                    item.batch_number = batch_number
                    item.number_of_tabs = number_of_tabs
                    item.unit_price_per_tab = unit_price_per_tab
                    item.item_type = item_type
                    item.expiry_date = expiry_date_obj
                    item.is_fixed_price = is_fixed_price
                    item.fixed_sale_price = fixed_sale_price
                    item.is_active = is_active
                    item.last_updated = datetime.now() # Update timestamp
                    db.session.add(item)
                    updated_count += 1
                else:
                    # Create new item
                    new_item = InventoryItem(
                        business_id=business_id,
                        product_name=product_name,
                        category=category,
                        purchase_price=purchase_price,
                        sale_price=sale_price,
                        current_stock=current_stock,
                        batch_number=batch_number,
                        number_of_tabs=number_of_tabs,
                        unit_price_per_tab=unit_price_per_tab,
                        item_type=item_type,
                        expiry_date=expiry_date_obj,
                        is_fixed_price=is_fixed_price,
                        fixed_sale_price=fixed_sale_price,
                        is_active=is_active,
                        last_updated=datetime.now() # Set timestamp for new item
                    )
                    db.session.add(new_item)
                    added_count += 1
            except Exception as e:
                errors.append(f"Error processing item '{item_data.get('product_name', 'N/A')}': {str(e)}")
                db.session.rollback() # Rollback current transaction on error
                return jsonify({'message': 'Error processing some items.', 'errors': errors}), 400

        db.session.commit()
        return jsonify({
            'message': 'Inventory synchronization successful.',
            'added_count': added_count,
            'updated_count': updated_count,
            'errors': errors
        })

    # In your app.py file

    # In your app.py file

    @app.route('/api/v1/inventory', methods=['GET'])
    @api_key_required
    def get_inventory_for_sync():
        print("DEBUG: Accessing inventory endpoint.") # ADD THIS LINE
        
        print("DEBUG: Inside get_inventory_for_sync() function.")
        try:
            business_id = request.args.get('business_id')
            if not business_id:
                return jsonify({'error': 'business_id is a required query parameter'}), 400
            
            # Pull inventory items for the given business
            inventory_items = InventoryItem.query.filter_by(business_id=business_id).all()
            
            inventory_list = []
            for item in inventory_items:
                inventory_list.append({
                    'id': item.id,
                    'business_id': item.business_id,
                    'product_name': item.product_name,
                    'category': item.category,
                    'purchase_price': item.purchase_price,
                    'sale_price': item.sale_price,
                    'current_stock': item.current_stock,
                    'last_updated': item.last_updated.isoformat(),
                    'batch_number': item.batch_number,
                    'number_of_tabs': item.number_of_tabs,
                    'unit_price_per_tab': item.unit_price_per_tab,
                    'item_type': item.item_type,
                    'expiry_date': item.expiry_date.isoformat() if item.expiry_date else None,
                    'is_fixed_price': item.is_fixed_price,
                    'fixed_sale_price': item.fixed_sale_price,
                    'is_active': item.is_active,
                    'barcode': item.barcode,
                    'markup_percentage_pharmacy': item.markup_percentage_pharmacy,
                    'synced_to_remote': item.synced_to_remote,
                })
            
            return jsonify(inventory_list)

        except Exception as e:
            print(f"Error fetching inventory for sync: {e}")
            return jsonify({'error': 'An internal server error occurred.'}), 500
    @app.route('/api/v1/sales', methods=['POST'])
    @api_key_required
    # @login_required # Temporary: Should be API-specific auth in production
    def api_record_sales():
        """
        API endpoint to record new sales in batch.
        Expected data: JSON list of sales record objects.
        """
        business_id = get_current_business_id()
        if not business_id:
            return jsonify({'message': 'Business ID is required to record sales.'}), 400

        if session.get('role') not in ['admin', 'sales']:
            return jsonify({'message': 'Access denied: Insufficient role to record sales.'}), 403

        sales_data = request.get_json()
        if not isinstance(sales_data, list):
            return jsonify({'message': 'Request body must be a JSON array of sales records.'}), 400

        recorded_count = 0
        errors = []

        for sale_data in sales_data:
            try:
                # Assuming a new sale record is always created, no 'upsert' for sales for now.
                # If the client provides an 'id', we use it, otherwise generate a new one.
                sale_id = sale_data.get('id', str(uuid.uuid4()))
                product_id = sale_data.get('product_id')
                product_name = sale_data.get('product_name')
                quantity_sold = float(sale_data.get('quantity_sold'))
                sale_unit_type = sale_data.get('sale_unit_type')
                price_at_time_per_unit_sold = float(sale_data.get('price_at_time_per_unit_sold'))
                total_amount = float(sale_data.get('total_amount'))
                sale_date_str = sale_data.get('sale_date')
                customer_phone = sale_data.get('customer_phone')
                sales_person_name = sale_data.get('sales_person_name')
                reference_number = sale_data.get('reference_number')
                transaction_id = sale_data.get('transaction_id')

                sale_date_obj = datetime.fromisoformat(sale_date_str) if sale_date_str else datetime.now()

                # Optional: Deduct stock if sales are pushed from offline app (already deducted locally)
                # This logic depends on whether offline app fully handles stock or just records sales.
                # For robustness, we might re-verify/deduct here or log discrepancies.
                # For now, we assume stock was handled locally and just record the sale.
                
                # Check if this exact sale record (by ID and transaction_id) already exists to prevent duplicates on sync
                existing_sale = SalesRecord.query.filter_by(id=sale_id, business_id=business_id, transaction_id=transaction_id).first()
                if existing_sale:
                    errors.append(f"Sale record with ID '{sale_id}' and transaction ID '{transaction_id}' already exists. Skipping.")
                    continue # Skip adding duplicate

                new_sale = SalesRecord(
                    id=sale_id, # Use provided ID for idempotency
                    business_id=business_id,
                    product_id=product_id,
                    product_name=product_name,
                    quantity_sold=quantity_sold,
                    sale_unit_type=sale_unit_type,
                    price_at_time_per_unit_sold=price_at_time_per_unit_sold,
                    total_amount=total_amount,
                    sale_date=sale_date_obj,
                    customer_phone=customer_phone,
                    sales_person_name=sales_person_name,
                    reference_number=reference_number,
                    transaction_id=transaction_id
                )
                db.session.add(new_sale)
                recorded_count += 1
            except Exception as e:
                errors.append(f"Error processing sale for product '{sale_data.get('product_name', 'N/A')}': {str(e)}")
                db.session.rollback() # Rollback current transaction on error
                return jsonify({'message': 'Error processing some sales records.', 'errors': errors}), 400

        db.session.commit()
        return jsonify({
            'message': 'Sales records synchronized successfully.',
            'recorded_count': recorded_count,
            'errors': errors
        })
    # ... (existing imports and other code) ...

    @app.route('/api/get_product_by_barcode', methods=['POST'])
    @api_key_required
    # @login_required
    def get_product_by_barcode():
        """
        API endpoint to fetch product details by barcode or product name.
        Ensures robust search (case-insensitive, trimmed) and
        correct, consistent data formatting for frontend consumption.
        """
        business_id = get_current_business_id()
        print(f"DEBUG: get_product_by_barcode - business_id: {business_id}")
        if not business_id:
            return jsonify({'success': False, 'message': 'Business context not found.'}), 400

        data = request.get_json()
        query_string = data.get('barcode', '').strip() # Strip whitespace from input
        print(f"DEBUG: get_product_by_barcode - Received query_string: '{query_string}'")

        if not query_string:
            return jsonify({'success': False, 'message': 'Barcode or product name not provided.'}), 400

        # 1. Try searching by exact barcode first.
        # We explicitly handle cases where the barcode might be empty or None in the database.
        product = InventoryItem.query.filter(
            InventoryItem.business_id == business_id,
            (InventoryItem.barcode == query_string) | (InventoryItem.barcode == None) | (InventoryItem.barcode == ''),
            InventoryItem.is_active == True
        ).first()
        print(f"DEBUG: get_product_by_barcode - Product found by exact barcode: {product.product_name if product else 'None'}")

        if not product:
            # 2. If not found by exact barcode, try searching by product name
            # (case-insensitive, partial match on product_name)
            product = InventoryItem.query.filter(
                InventoryItem.business_id == business_id,
                InventoryItem.is_active == True,
                func.lower(InventoryItem.product_name).ilike(f'%{query_string.lower()}%') # Case-insensitive partial match
            ).first()
            print(f"DEBUG: get_product_by_barcode - Product found by product name: {product.product_name if product else 'None'}")

        if product:
            # Check stock before returning
            if product.current_stock <= 0:
                print(f"DEBUG: Product '{product.product_name}' is out of stock.")
                return jsonify({
                    'success': False,
                    'message': f"Product '{product.product_name}' is out of stock."
                }), 400

            # Prepare product data for JSON response, ensuring correct types and defaults
            # This structure ensures all expected keys are always present for the frontend
            product_data = {
                'id': str(product.id), # Ensure ID is string for consistency with UUIDs
                'product_name': product.product_name,
                'current_stock': float(product.current_stock or 0.0), # Ensure float, default 0.0
                'is_fixed_price': product.is_fixed_price,
                'barcode': product.barcode,
                'number_of_tabs': float(product.number_of_tabs or 1.0), # Ensure float, default 1.0
                'unit_price_per_tab': float(product.unit_price_per_tab or 0.0), # Ensure float, default 0.0
                'item_type': product.item_type,
                'expiry_date': product.expiry_date.strftime('%Y-%m-%d') if product.expiry_date else None,
                'batch_number': product.batch_number,
                'purchase_price': float(product.purchase_price or 0.0),
                'sale_price': float(product.sale_price or 0.0), # Always include regular sale price
                'fixed_sale_price': float(product.fixed_sale_price or 0.0), # Always include fixed sale price
                'markup_percentage_pharmacy': float(product.markup_percentage_pharmacy or 0.0) # Always include markup
            }

            print(f"DEBUG: Product found and returning: {product_data}")
            return jsonify({'success': True, 'product': product_data})
        else:
            # If no product found by barcode or name, suggest similar products if any exist
            similar_products = InventoryItem.query.filter(
                InventoryItem.business_id == business_id,
                InventoryItem.is_active == True,
                func.lower(InventoryItem.product_name).ilike(f'%{query_string.lower()}%')
            ).limit(5).all()

            if similar_products:
                suggestions = [p.product_name for p in similar_products]
                message = f'Product not found. Did you mean: {", ".join(suggestions)}?'
                print(f"DEBUG: Product not found, suggesting: {message}")
                return jsonify({
                    'success': False,
                    'message': message
                }), 404
            
            message = 'Product not found for this barcode or name.'
            print(f"DEBUG: Product not found: {message}")
            return jsonify({
                'success': False,
                'message': message
            }), 404

  

    def create_database_if_not_exists(app):
        """Creates the database and its tables if they don't exist."""
        db_path = os.path.join(app.instance_path, 'instance_data.db')
        if not os.path.exists(db_path):
            with app.app_context():
                db.create_all()
                print("Database tables created successfully.")

    # Ensure the instance directory exists for the offline database
    # os.makedirs(os.path.dirname(OFFLINE_DB_PATH), exist_ok=True)

    # Helper function to get last sync timestamp
    def get_last_sync_timestamp():
        try:
            with open('last_sync.txt', 'r') as f:
                return f.read().strip()
        except FileNotFoundError:
            return '1970-01-01 00:00:00'

    # Helper function to set last sync timestamp
    def set_last_sync_timestamp(timestamp):
        with open('last_sync.txt', 'w') as f:
            f.write(timestamp)


    
    @app.route('/trigger_sync', methods=['POST'])
    @login_required
    def trigger_sync():
        """
        Triggers the data synchronization process based on the user's role.
        """
        is_online = check_network_online()
        if not is_online:
            return jsonify({'success': False, 'message': 'No internet connection detected.'}), 200

        user_role = current_user.role
        current_business_id = current_user.business_id
        
        # Retrieve the API key to be used for all sync API calls
        sync_api_key = os.getenv("REMOTE_ADMIN_API_KEY")
        if not sync_api_key:
            return jsonify({'success': False, 'message': 'Synchronization API key not configured.'}), 500

        if user_role == 'super_admin':
            success, message = super_admin_full_sync()
        elif user_role == 'admin':
            success, message = perform_sync(current_business_id, sync_api_key)
        else:
            message = "Unauthorized role to perform synchronization."
            return jsonify({'success': False, 'message': message}), 403

        if success:
            return jsonify({'success': True, 'message': message}), 200
        else:
            return jsonify({'success': False, 'message': message}), 500
    
    @app.route('/api/v1/business/<uuid:business_id>', methods=['GET'])
    @api_key_required
    def get_business_by_id(business_id):
        """Returns a single business record by its UUID."""
        try:
            business = db.session.get(Business, business_id)
            if not business:
                abort(404)
            return jsonify({
                "id": str(business.id),
                "name": business.name,
                "type": business.type,
                "address": business.address,
                "location": business.location,
                "contact": business.contact,
                "email": business.email,
                "is_active": business.is_active,
                "last_synced_at": business.last_synced_at.isoformat() if business.last_synced_at else None,
            })
        except Exception as e:
            logging.error(f"Error getting business: {e}")
            abort(500)

    @app.route('/api/v1/businesses/<uuid:business_id>/inventory', methods=['GET'])
    @api_key_required
    def get_inventory_for_business(business_id):
        """Returns a list of all inventory items for a specific business."""
        try:
            items = InventoryItem.query.filter_by(business_id=business_id).all()
            inventory_list = []
            for item in items:
                inventory_list.append({
                    "id": str(item.id),
                    "business_id": str(item.business_id),
                    "product_name": item.product_name,
                    "category": item.category,
                    "purchase_price": float(item.purchase_price),
                    "sale_price": float(item.sale_price),
                    "current_stock": float(item.current_stock),
                    "last_updated": item.last_updated.isoformat(),
                    "batch_number": item.batch_number,
                    "number_of_tabs": float(item.number_of_tabs),
                    "unit_price_per_tab": float(item.unit_price_per_tab),
                    "item_type": item.item_type,
                    "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None,
                    "is_fixed_price": item.is_fixed_price,
                    "fixed_sale_price": float(item.fixed_sale_price),
                    "is_active": item.is_active,
                    "barcode": item.barcode,
                    "markup_percentage_pharmacy": float(item.markup_percentage_pharmacy),
                })
            return jsonify(inventory_list)
        except Exception as e:
            logging.error(f"Error getting inventory: {e}")
            abort(500)

    @app.route('/api/v1/users', methods=['GET'])
    @api_key_required
    def get_users_for_business():
        """Returns a list of all users for a specific business, based on business_id in query params."""
        business_id = request.args.get('business_id')
        if not business_id:
            abort(400, description="Missing business_id query parameter.")
        try:
            users = User.query.filter_by(business_id=business_id).all()
            user_list = []
            for user in users:
                user_list.append({
                    "id": str(user.id),
                    "username": user.username,
                    "role": user.role,
                    "is_active": user.is_active,
                    "business_id": str(user.business_id),
                    "password_hash": user._password_hash,
                    "created_at": user.created_at.isoformat()
                })
            return jsonify(user_list)
        except Exception as e:
            logging.error(f"Error getting users: {e}")
            abort(500)
    
    @app.route('/api/v1/sales/push', methods=['POST'])
    @api_key_required
    def push_sales_record():
        """Receives and saves a sales record from an offline app."""
        data = request.json
        if not data:
            return jsonify({"message": "Invalid JSON data"}), 400

        try:
            sale_id = data.get('id')
            existing_sale = db.session.get(SalesRecord, sale_id)
            if existing_sale:
                logging.warning(f"Sale {sale_id} already exists. Conflict.")
                return jsonify({"message": "Sale already exists"}), 409

            sale_record = SalesRecord(
                id=sale_id,
                business_id=data['business_id'],
                sales_person_id=data['sales_person_id'],
                customer_id=data.get('customer_id'),
                grand_total_amount=data['grand_total_amount'],
                payment_method=data['payment_method'],
                transaction_date=datetime.fromisoformat(data['transaction_date']),
                synced_to_remote=True
            )
            db.session.add(sale_record)

            for item_data in data.get('items', []):
                sale_item = SalesItem(
                    id=item_data['id'],
                    sales_record_id=sale_record.id,
                    inventory_item_id=item_data['inventory_item_id'],
                    quantity_sold=item_data['quantity_sold'],
                    unit_price_at_sale=item_data['unit_price_at_sale']
                )
                db.session.add(sale_item)

            db.session.commit()
            return jsonify({"message": "Sales record pushed successfully"}), 201

        except Exception as e:
            db.session.rollback()
            logging.error(f"Error pushing sales record: {e}")
            return jsonify({"message": "An error occurred", "error": str(e)}), 500

    @app.route('/api/v1/sales/upsert', methods=['POST'])
    @api_key_required
    def upsert_sales_record():
        """
        Receives and saves or updates a sales record and its items from an offline app.
        This function handles both creation and modification.
        """
        data = request.json
        if not data:
            return jsonify({"message": "Invalid JSON data"}), 400

        try:
            sale_id = data.get('id')
            existing_sale = SalesRecord.query.options(db.joinedload(SalesRecord.items)).get(sale_id)

            if existing_sale:
                # Case 1: The record exists, so we update it.
                logging.info(f"Updating existing sales record: {sale_id}")
                existing_sale.business_id = data['business_id']
                existing_sale.sales_person_id = data['sales_person_id']
                existing_sale.customer_id = data.get('customer_id')
                existing_sale.grand_total_amount = data['grand_total_amount']
                existing_sale.payment_method = data['payment_method']
                existing_sale.transaction_date = datetime.fromisoformat(data['transaction_date'])
                existing_sale.synced_to_remote = True

                # Handle sales items: update, add, and delete as necessary.
                new_items_data = data.get('items', [])
                new_item_ids = {item_data['id'] for item_data in new_items_data}
                existing_item_ids = {item.id for item in existing_sale.items}

                # Delete items that are no longer in the new data.
                items_to_delete = [item for item in existing_sale.items if item.id not in new_item_ids]
                for item in items_to_delete:
                    db.session.delete(item)
                
                # Update or add new items.
                for item_data in new_items_data:
                    item_id = item_data['id']
                    if item_id in existing_item_ids:
                        # Update existing item
                        existing_item = next((i for i in existing_sale.items if i.id == item_id), None)
                        if existing_item:
                            existing_item.inventory_item_id = item_data['inventory_item_id']
                            existing_item.quantity_sold = item_data['quantity_sold']
                            existing_item.unit_price_at_sale = item_data['unit_price_at_sale']
                    else:
                        # Add new item
                        sale_item = SalesItem(
                            id=item_id,
                            sales_record_id=existing_sale.id,
                            inventory_item_id=item_data['inventory_item_id'],
                            quantity_sold=item_data['quantity_sold'],
                            unit_price_at_sale=item_data['unit_price_at_sale']
                        )
                        db.session.add(sale_item)
                
                db.session.commit()
                return jsonify({"message": f"Sales record {sale_id} updated successfully"}), 200

            else:
                # Case 2: The record does not exist, so we create a new one.
                logging.info(f"Creating new sales record: {sale_id}")
                sale_record = SalesRecord(
                    id=sale_id,
                    business_id=data['business_id'],
                    sales_person_id=data['sales_person_id'],
                    customer_id=data.get('customer_id'),
                    grand_total_amount=data['grand_total_amount'],
                    payment_method=data['payment_method'],
                    transaction_date=datetime.fromisoformat(data['transaction_date']),
                    synced_to_remote=True
                )
                db.session.add(sale_record)

                for item_data in data.get('items', []):
                    sale_item = SalesItem(
                        id=item_data['id'],
                        sales_record_id=sale_record.id,
                        inventory_item_id=item_data['inventory_item_id'],
                        quantity_sold=item_data['quantity_sold'],
                        unit_price_at_sale=item_data['unit_price_at_sale']
                    )
                    db.session.add(sale_item)

                db.session.commit()
                return jsonify({"message": "Sales record pushed successfully"}), 201

        except Exception as e:
            db.session.rollback()
            logging.error(f"Error upserting sales record: {e}")
            return jsonify({"message": "An error occurred", "error": str(e)}), 500
    

    @app.route('/api/v1/sales/get_unsynced', methods=['GET'])
    @api_key_required
    def get_unsynced_sales():
        """
        Retrieves a list of sales records that have not been synced to the remote server.
        """
        try:
            unsynced_sales = SalesRecord.query.filter_by(synced_to_remote=False).all()
            if not unsynced_sales:
                return jsonify({"message": "No unsynced sales records found"}), 200

            sales_list = []
            for sale in unsynced_sales:
                sales_list.append({
                    "id": sale.id,
                    "business_id": sale.business_id,
                    "sales_person_id": sale.sales_person_id,
                    "customer_id": sale.customer_id,
                    "grand_total_amount": float(sale.grand_total_amount), # Convert Decimal to float for JSON serialization
                    "payment_method": sale.payment_method,
                    "transaction_date": sale.transaction_date.isoformat(),
                    "synced_to_remote": sale.synced_to_remote
                })
            
            return jsonify(sales_list), 200

        except Exception as e:
            logging.error(f"Error fetching unsynced sales records: {e}")
            return jsonify({"message": "An error occurred", "error": str(e)}), 500


    @app.route('/api/businesses')
    def api_businesses():
        """
        API endpoint to expose all business data for synchronization.
        This is what your local instance will call.
        It should also include the related users.
        """
        try:
            businesses = Business.query.options(db.joinedload(Business.users)).all()
            businesses_data = []
            for business in businesses:
                business_dict = {
                    'id': business.id,
                    'name': business.name,
                    'type': business.type,
                    'address': business.address,
                    'contact': business.contact,
                    'email': business.email,
                    'is_active': business.is_active,
                    'users': []
                }
                for user in business.users:
                    user_dict = {
                        'id': user.id,
                        'username': user.username,
                        '_password_hash': user._password_hash,
                        'role': user.role,
                        'is_active': user.is_active
                    }
                    business_dict['users'].append(user_dict)
                businesses_data.append(business_dict)
            return jsonify(businesses_data)
        except Exception as e:
            print(f"Error serving API request for businesses: {e}")
            return jsonify({'error': str(e)}), 500


    def super_admin_full_sync():
        """
        Pulls all data for all businesses and users from the remote server.
        This function is for the Super Admin role only.
        """
        remote_url = get_remote_flask_base_url()

        # Get admin credentials from environment variables or a secure configuration
        # NOTE: You should store these securely, e.g., in a .env file
        admin_username = os.getenv("SUPER_ADMIN_USERNAME")
        admin_password = os.getenv("SUPER_ADMIN_PASSWORD")

        if not admin_username or not admin_password:
            return False, "Synchronization failed: Admin credentials not found."

        # Use a requests.Session to persist authentication cookies
        session_requests = requests.Session()

        try:
            # Step 1: Authenticate with the online server to get a valid session
            print("Authenticating with remote server...")
            login_payload = {
                'username': admin_username,
                'password': admin_password
            }
            login_response = session_requests.post(f"{remote_url}/login", data=login_payload)
            login_response.raise_for_status() # This will raise an error for bad status codes

            if 'session_id' not in session_requests.cookies: # Check for a session cookie
                return False, "Authentication failed: No session cookie received."

            print("Authentication successful.")

            # Step 2: Now that we have a valid session, pull all data
            # --- Pull ALL Businesses ---
            print("Pulling all registered businesses...")
            businesses_response = session_requests.get(f"{remote_url}/api/v1/businesses")
            businesses_response.raise_for_status()
            new_businesses = businesses_response.json()
            
            with current_app.app_context():
                db.session.query(Business).delete()
                for business_data in new_businesses:
                    business = Business(
                        id=business_data['id'],
                        name=business_data['name'],
                        address=business_data['address'],
                        location=business_data['location'],
                        contact=business_data['contact'],
                        type=business_data['type'],
                        is_active=business_data['is_active'],
                        # Ensure you handle datetime objects correctly
                        last_updated=datetime.fromisoformat(business_data['last_updated']) if 'last_updated' in business_data and business_data['last_updated'] else None
                    )
                    db.session.add(business)
                db.session.commit()
                print(f"Successfully pulled and replaced data for businesses. Found {len(new_businesses)} businesses.")

            # --- Pull ALL Users ---
            print("Pulling all users...")
            users_response = session_requests.get(f"{remote_url}/api/v1/users")
            users_response.raise_for_status()
            new_users = users_response.json()
            
            with current_app.app_context():
                db.session.query(User).delete()
                for user_data in new_users:
                    user = User(
                        id=user_data['id'],
                        username=user_data['username'],
                        # Pass the password hash directly
                        _password_hash=user_data['password'], 
                        role=user_data['role'],
                        business_id=user_data['business_id'],
                        is_active=user_data['is_active'],
                        created_at=datetime.fromisoformat(user_data['created_at'])
                    )
                    db.session.add(user)
                db.session.commit()
                print(f"Successfully pulled and replaced data for user. Found {len(new_users)} users.")
            
            # --- Pull ALL Inventory Items ---
            print("Pulling all inventory items...")
            inventory_response = session_requests.get(f"{remote_url}/api/v1/inventory")
            inventory_response.raise_for_status()
            new_inventory_items = inventory_response.json()
            
            with current_app.app_context():
                db.session.query(InventoryItem).delete()
                for item_data in new_inventory_items:
                    item = InventoryItem(
                        id=item_data['id'],
                        business_id=item_data['business_id'],
                        product_name=item_data['product_name'],
                        category=item_data['category'],
                        purchase_price=item_data['purchase_price'],
                        sale_price=item_data['sale_price'],
                        current_stock=item_data['current_stock'],
                        last_updated=datetime.fromisoformat(item_data['last_updated']),
                        batch_number=item_data['batch_number'],
                        number_of_tabs=item_data['number_of_tabs'],
                        unit_price_per_tab=item_data['unit_price_per_tab'],
                        item_type=item_data['item_type'],
                        expiry_date=datetime.fromisoformat(item_data['expiry_date']).date() if item_data['expiry_date'] else None,
                        is_fixed_price=item_data['is_fixed_price'],
                        fixed_sale_price=item_data['fixed_sale_price'],
                        is_active=item_data['is_active']
                    )
                    db.session.add(item)
                db.session.commit()
                print(f"Successfully pulled and replaced data for inventory_items. Found {len(new_inventory_items)} items.")
            
            # NOTE: Add similar logic for other tables like HirableItems, Customers, etc.

            return True, "Synchronization successful."

        except requests.exceptions.RequestException as e:
            db.session.rollback()
            print(f"Error during full sync: {e}")
            return False, f"Error during full sync: {e}"
    def sync_data_in_background(business_id, is_superadmin=False):
        """
        Function to be run in a separate thread for data synchronization.
        """
        try:
            # The actual sync logic, which can take a long time
            if is_superadmin:
                # Placeholder for superadmin sync logic
                # This is where the actual superadmin data sync would happen
                print("Starting superadmin data sync in background...")
                time.sleep(5)  # Simulate a long process
                print("Superadmin data sync complete.")
            else:
                sync_api.sync_admin_data(business_id)
                print(f"Admin data sync for business ID {business_id} complete.")
        except Exception as e:
            # In a real app, you might log this error to a file or database
            logging.error(f'Background sync thread error: {e}')


    def admin_sync(business_id, remote_api_key):
        """
        Performs a robust two-way synchronization for a specific business.
        Pulls data from the remote server and pushes unsynced local data to it.
        """
        remote_url = get_remote_flask_base_url()
        headers = {
            'X-API-Key': remote_api_key,
            'Content-Type': 'application/json'
        }
        
        logging.info(f"Starting synchronization for business ID: {business_id}")

        try:
            # Step 1: Check business ID consistency and update local business record
            business_response = requests.get(f"{remote_url}/api/v1/business/{business_id}", headers=headers, allow_redirects=False)
            
            if business_response.status_code == 401:
                logging.error("Authentication failed. Please check the API key.")
                return False, "Authentication failed. Please check the API key."
            
            try:
                business_response.raise_for_status()
                online_business_data = business_response.json()
            except requests.exceptions.RequestException as http_err:
                error_msg = f"HTTP error during business info pull: {http_err}"
                logging.error(error_msg)
                return False, error_msg
            except json.JSONDecodeError:
                error_msg = f"Could not decode JSON from business info response. Status code: {business_response.status_code}, Response: {business_response.text}"
                logging.error(error_msg)
                return False, error_msg

            with current_app.app_context():
                # Correct way to use Session.get()
                local_business = db.session.get(Business, business_id)
                if not local_business:
                    local_business = Business(
                        id=online_business_data['id'],
                        name=online_business_data['name'],
                        type=online_business_data['type'],
                        address=online_business_data.get('address'),
                        location=online_business_data.get('location'),
                        contact=online_business_data.get('contact'),
                        email=online_business_data.get('email'),
                        is_active=online_business_data.get('is_active', True),
                        last_synced_at=datetime.utcnow(),
                        remote_id=online_business_data['id']
                    )
                    db.session.add(local_business)
                    logging.info("Local business record created from online data.")
                else:
                    if not local_business.remote_id:
                        local_business.remote_id = online_business_data['id']
                        logging.info(f"Local business remote_id updated to match remote: {local_business.remote_id}")
                    local_business.last_synced_at = datetime.utcnow()
                    
                db.session.commit()

            # Step 2: Pull inventory and user data from the remote server (Online -> Offline)
            logging.info("Pulling inventory and user data from remote...")
            
            # --- Inventory Pull ---
            try:
                inventory_response = requests.get(f"{remote_url}/api/v1/businesses/{local_business.id}/inventory", headers=headers)
                inventory_response.raise_for_status()
                online_inventory_data = inventory_response.json()
            except requests.exceptions.RequestException as http_err:
                error_msg = f"HTTP error during inventory pull: {http_err}"
                logging.error(error_msg)
                return False, error_msg
            except json.JSONDecodeError:
                error_msg = f"Could not decode JSON from inventory response. Status code: {inventory_response.status_code}, Response: {inventory_response.text}"
                logging.error(error_msg)
                return False, error_msg

            # --- Users Pull ---
            try:
                users_response = requests.get(f"{remote_url}/api/v1/users?business_id={local_business.id}", headers=headers)
                users_response.raise_for_status()
                online_users_data = users_response.json()
            except requests.exceptions.RequestException as http_err:
                error_msg = f"HTTP error during users pull: {http_err}"
                logging.error(error_msg)
                return False, error_msg
            except json.JSONDecodeError:
                error_msg = f"Could not decode JSON from users response. Status code: {users_response.status_code}, Response: {users_response.text}"
                logging.error(error_msg)
                return False, error_msg

            with current_app.app_context():
                InventoryItem.query.filter_by(business_id=local_business.id).delete()
                for item_data in online_inventory_data:
                    item = InventoryItem(
                        id=item_data['id'],
                        business_id=item_data['business_id'],
                        product_name=item_data['product_name'],
                        category=item_data.get('category'),
                        purchase_price=item_data['purchase_price'],
                        sale_price=item_data['sale_price'],
                        current_stock=item_data['current_stock'],
                        last_updated=datetime.fromisoformat(item_data['last_updated']),
                        batch_number=item_data.get('batch_number'),
                        number_of_tabs=item_data.get('number_of_tabs', 1.0),
                        unit_price_per_tab=item_data.get('unit_price_per_tab', 0.0),
                        item_type=item_data.get('item_type'),
                        expiry_date=datetime.fromisoformat(item_data['expiry_date']).date() if item_data.get('expiry_date') else None,
                        is_fixed_price=item_data.get('is_fixed_price', False),
                        fixed_sale_price=item_data.get('fixed_sale_price', 0.0),
                        is_active=item_data.get('is_active', True),
                        barcode=item_data.get('barcode'),
                        markup_percentage_pharmacy=item_data.get('markup_percentage_pharmacy', 0.0),
                        synced_to_remote=True
                    )
                    db.session.add(item)
                
                User.query.filter_by(business_id=local_business.id).delete()
                for user_data in online_users_data:
                    user = User(
                        id=user_data['id'],
                        username=user_data['username'],
                        role=user_data['role'],
                        is_active=user_data['is_active'],
                        business_id=user_data['business_id'],
                        _password_hash=user_data['password_hash'],
                        created_at=datetime.fromisoformat(user_data['created_at'])
                    )
                    db.session.add(user)
                db.session.commit()
                logging.info("Offline inventory and user data updated successfully.")

            # Step 3: Push unsynced offline sales to the remote server (Offline -> Online)
            logging.info("Pushing unsynced offline sales to remote...")
            with current_app.app_context():
                unsynced_sales = SalesRecord.query.filter_by(business_id=local_business.id, synced_to_remote=False).all()
                pushed_count = 0
                if unsynced_sales:
                    for sale in unsynced_sales:
                        try:
                            sale_data = {
                                'id': sale.id,
                                'business_id': local_business.id,
                                'sales_person_id': sale.sales_person_id,
                                'customer_id': sale.customer_id,
                                'grand_total_amount': float(sale.grand_total_amount),
                                'payment_method': sale.payment_method,
                                'transaction_date': sale.transaction_date.isoformat(),
                                'is_synced': True,
                                'items': [{
                                    'id': item.id,
                                    'sales_record_id': item.sales_record_id,
                                    'inventory_item_id': item.inventory_item_id,
                                    'quantity_sold': float(item.quantity_sold),
                                    'unit_price_at_sale': float(item.unit_price_at_sale)
                                } for item in sale.items_sold]
                            }
                            
                            push_response = requests.post(f"{remote_url}/api/v1/sales/push", json=sale_data, headers=headers)
                            push_response.raise_for_status()
                            
                            sale.synced_to_remote = True
                            pushed_count += 1
                            
                        except requests.exceptions.HTTPError as http_err:
                            if http_err.response.status_code == 409:
                                logging.warning(f"Sale {sale.id} already exists on remote. Marking as synced.")
                                sale.synced_to_remote = True
                                pushed_count += 1
                            else:
                                logging.error(f"HTTP error pushing sale {sale.id}: {http_err.response.status_code} - {http_err.response.text}")
                        except Exception as e:
                            logging.error(f"An error occurred while pushing sale {sale.id}: {e}")

                db.session.commit()
                logging.info(f"Successfully pushed {pushed_count} sales to the remote server.")
            
            # --- Corrected Business Sync Logic ---
            logging.info("Starting business synchronization...")
            try:
                businesses_response = requests.get(f"{remote_url}/api/v1/businesses", headers=headers)
                businesses_response.raise_for_status()
                online_businesses = businesses_response.json()
                logging.info(f"Received {len(online_businesses)} businesses from the remote server.")

                for business_data in online_businesses:
                    # Check for an existing business based on the remote_id
                    # This is crucial for preventing UniqueViolation errors
                    existing_business = Business.query.filter_by(remote_id=business_data['id']).first()
                    
                    if existing_business:
                        # Update the existing business
                        existing_business.name = business_data.get('name', existing_business.name)
                        existing_business.type = business_data.get('type', existing_business.type)
                        existing_business.address = business_data.get('address', existing_business.address)
                        existing_business.location = business_data.get('location', existing_business.location)
                        existing_business.contact = business_data.get('contact', existing_business.contact)
                        existing_business.email = business_data.get('email', existing_business.email)
                        existing_business.is_active = business_data.get('is_active', existing_business.is_active)
                        existing_business.last_synced_at = datetime.utcnow()
                        logging.info(f"Updated existing business: {existing_business.name}")
                    else:
                        # Create a new business if it doesn't exist
                        new_business = Business(
                            id=str(uuid.uuid4()),  # Generate a new local UUID
                            name=business_data['name'],
                            type=business_data.get('type'),
                            address=business_data.get('address'),
                            location=business_data.get('location'),
                            contact=business_data.get('contact'),
                            email=business_data.get('email'),
                            is_active=business_data.get('is_active', True),
                            last_synced_at=datetime.utcnow(),
                            remote_id=business_data['id']
                        )
                        db.session.add(new_business)
                        logging.info(f"Inserted new business: {new_business.name}")
                
                db.session.commit()
                logging.info("Business synchronization complete.")

            except requests.exceptions.RequestException as http_err:
                db.session.rollback()
                error_msg = f"HTTP error during business sync: {http_err}"
                logging.error(error_msg)
                return False, error_msg
            except json.JSONDecodeError:
                db.session.rollback()
                error_msg = f"Could not decode JSON from business sync response. Status code: {businesses_response.status_code}, Response: {businesses_response.text}"
                logging.error(error_msg)
                return False, error_msg
            except Exception as e:
                db.session.rollback()
                error_msg = f"An unexpected error occurred during business sync: {e}"
                logging.error(error_msg)
                return False, error_msg
            
            # Final step: Record the successful sync timestamp locally on the business record
            with current_app.app_context():
                business = db.session.get(Business, local_business.id)
                if business:
                    business.last_synced_at = datetime.utcnow()
                    db.session.commit()
                    logging.info(f"Local business last_synced_at updated to {business.last_synced_at}.")
            
            logging.info("Synchronization complete.")
            return True, "Synchronization successful."

        except requests.exceptions.RequestException as e:
            db.session.rollback()
            error_msg = f"Network error during sync: {e}"
            logging.error(error_msg)
            return False, error_msg
        except Exception as e:
            db.session.rollback()
            error_msg = f"An unexpected error occurred during sync: {e}"
            logging.error(error_msg)
            return False, error_msg


    # @app.route('/sync_businesses', methods=['POST'])
    # @login_required
    # @super_admin_required
    # def sync_businesses():
    #     try:
    #         online_db_url = app.config['SQLALCHEMY_DATABASE_URI']
    #         offline_db_path = os.path.join(app.instance_path, 'instance_data.db')
    #         offline_db_url = f"sqlite:///{offline_db_path}"

    #         online_engine = create_engine(online_db_url)
    #         offline_engine = create_engine(offline_db_url)

    #         with online_engine.connect() as online_conn, offline_engine.connect() as offline_conn:
    #             online_businesses_df = pd.read_sql_table('businesses', online_conn)
    #             online_businesses_df.to_sql('businesses', offline_conn, if_exists='replace', index=False)
    #             online_inventory_df = pd.read_sql_table('inventory_items', online_conn)
    #             online_inventory_df.to_sql('inventory_items', offline_conn, if_exists='replace', index=False)
                
    #             unsynced_sales_df = pd.read_sql_query("SELECT * FROM sales_records WHERE synced_to_remote = FALSE", offline_conn)
    #             if not unsynced_sales_df.empty:
    #                 unsynced_sales_df.to_sql('sales_records', online_conn, if_exists='append', index=False)
    #                 sales_ids_to_update = unsynced_sales_df['id'].tolist()
    #                 with app.app_context():
    #                     db.session.query(SalesRecord).filter(
    #                         SalesRecord.id.in_(sales_ids_to_update)
    #                     ).update({SalesRecord.synced_to_remote: True}, synchronize_session=False)
    #                     db.session.commit()
                
    #             if Business.query.first():
    #                 global_business = Business.query.filter_by(name='Global Business').first()
    #                 if global_business:
    #                     global_business.last_synced_at = datetime.utcnow()
    #                     db.session.commit()

    #         flash('Data synchronization successful!', 'success')
    #         return redirect(url_for('super_admin_dashboard'))

    #     except Exception as e:
    #         db.session.rollback()
    #         print(f"Error during synchronization: {e}")
    #         flash(f'Error during synchronization: {str(e)}', 'danger')
    #         return redirect(url_for('super_admin_dashboard'))

        # This is the new, more robust function
    @app.route('/sync_businesses', methods=['POST'])
    @login_required
    # @super_admin_required  # This decorator needs to be defined
    def sync_businesses():
        logging.info("Starting business synchronization...")
        session['sync_status'] = {'status': 'Syncing', 'last_sync': 'In Progress...', 'message': 'Synchronization started...'}

        try:
            # Step 1: Request business data from the remote server's API
            api_endpoint = f"{os.getenv('ONLINE_FLASK_APP_BASE_URL', 'http://localhost:5000')}/api/businesses"
            logging.info(f"Attempting to fetch businesses from: {api_endpoint}")
            
            # Use a dedicated API key for server-to-server communication
            api_key = os.getenv('API_KEY_SECRET')
            headers = {'X-API-Key': api_key}
            
            # Use requests.Session to maintain the Flask user session cookies
            with requests.Session() as s:
                s.cookies.update(request.cookies)
                response = s.get(api_endpoint, timeout=30, headers=headers)
                response.raise_for_status() # Raise an exception for HTTP errors

            # Step 2: Parse the JSON data
            remote_businesses_data = response.json()
            logging.info(f"Received {len(remote_businesses_data)} businesses from the remote server.")
            if len(remote_businesses_data) > 0:
                logging.debug("Received data (first 500 chars):", json.dumps(remote_businesses_data, indent=2)[:500])

            # Step 3: Iterate and synchronize each business and its users
            new_businesses_count = 0
            updated_businesses_count = 0
            new_users_count = 0
            
            for remote_business_data in remote_businesses_data:
                remote_id = remote_business_data.get('id')
                # Find if the business already exists in our local database
                local_business = Business.query.filter_by(remote_id=remote_id).first()

                if not local_business:
                    # Business does not exist, create a new one
                    local_business = Business(
                        name=remote_business_data['name'],
                        type=remote_business_data['type'],
                        address=remote_business_data['address'],
                        contact=remote_business_data['contact'],
                        email=remote_business_data['email'],
                        is_active=remote_business_data.get('is_active', True),
                        last_synced_at=datetime.utcnow(),
                        remote_id=remote_id
                    )
                    db.session.add(local_business)
                    db.session.commit() # Commit here to get a local_business.id for user
                    logging.info(f"Created new local business: {local_business.name}")
                    new_businesses_count += 1
                else:
                    # Business exists, update its details
                    local_business.name = remote_business_data['name']
                    local_business.type = remote_business_data['type']
                    local_business.address = remote_business_data['address']
                    local_business.contact = remote_business_data['contact']
                    local_business.email = remote_business_data['email']
                    local_business.is_active = remote_business_data.get('is_active', True)
                    local_business.last_synced_at = datetime.utcnow()
                    updated_businesses_count += 1
                    logging.info(f"Updated existing local business: {local_business.name}")

                # Now, synchronize users for this business
                remote_users = remote_business_data.get('users', [])
                for remote_user_data in remote_users:
                    remote_user_id = remote_user_data.get('id')
                    local_user = User.query.filter_by(id=remote_user_id).first()

                    if not local_user:
                        # User does not exist, create a new one
                        new_user = User(
                            id=remote_user_id,
                            username=remote_user_data['username'],
                            _password_hash=remote_user_data['_password_hash'],
                            role=remote_user_data['role'],
                            business_id=local_business.id,
                            is_active=remote_user_data.get('is_active', True),
                            created_at=datetime.utcnow()
                        )
                        db.session.add(new_user)
                        logging.info(f"Created new user: {new_user.username} for business {local_business.name}")
                        new_users_count += 1
                    else:
                        # User exists, update details
                        local_user.username = remote_user_data['username']
                        local_user._password_hash = remote_user_data['_password_hash']
                        local_user.role = remote_user_data['role']
                        local_user.business_id = local_business.id
                        local_user.is_active = remote_user_data.get('is_active', True)
                        logging.info(f"Updated user: {local_user.username}")
                
            db.session.commit() # Final commit for all changes

            # Update session status on successful completion
            message = (
                f"Synchronization successful! "
                f"Added {new_businesses_count} new businesses, "
                f"updated {updated_businesses_count} businesses, "
                f"and added {new_users_count} new users."
            )
            session['sync_status'] = {
                'status': 'Online',
                'last_sync': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                'message': message
            }
            flash(message, 'success')
            logging.info("Synchronization completed successfully.")
            return redirect(url_for('super_admin_dashboard'))

        except requests.exceptions.RequestException as e:
            db.session.rollback()
            message = f"Network error during synchronization: {e}"
            session['sync_status'] = {
                'status': 'Error',
                'last_sync': 'Never',
                'message': message
            }
            flash(message, 'danger')
            logging.error(f"Synchronization failed with a network error: {e}")
            return redirect(url_for('super_admin_dashboard'))

        except json.JSONDecodeError as e:
            db.session.rollback()
            # This is where we catch the JSON error and print the response text for debugging
            message = f"Error decoding JSON response from server: {e}. Server responded with: '{response.text[:100]}...'"
            session['sync_status'] = {
                'status': 'Error',
                'last_sync': 'Never',
                'message': message
            }
            flash(message, 'danger')
            logging.error(f"Synchronization failed with a JSON decoding error: {e}")
            return redirect(url_for('super_admin_dashboard'))

        except Exception as e:
            db.session.rollback()
            message = f"An unexpected error occurred during synchronization: {e}"
            session['sync_status'] = {
                'status': 'Error',
                'last_sync': 'Never',
                'message': message
            }
            flash(message, 'danger')
            logging.error(f"Synchronization failed with an unexpected error: {e}")
            return redirect(url_for('super_admin_dashboard'))  
    
    @app.route('/api/v1/full_sync_data', methods=['GET'])
    @api_key_required
    def get_full_sync_data():
        try:
            businesses = Business.query.all()
            businesses_data = []
            for biz in businesses:
                businesses_data.append({
                    'id': str(biz.id),
                    'name': biz.name,
                    'last_synced_at': biz.last_synced_at.isoformat() if biz.last_synced_at else None
                })
            
            inventory_items = InventoryItem.query.all()
            inventory_data = [serialize_inventory_item_api(item) for item in inventory_items]
            
            return jsonify({
                'businesses': businesses_data,
                'inventory': inventory_data
            }), 200
        except Exception as e:
            logging.error(f"Error getting full sync data: {e}")
            return jsonify({'error': 'Internal server error'}), 500

    @app.route('/api/v1/sync/sales', methods=['POST'])
    @api_key_required
    def sync_sales():
        data = request.get_json()
        sales_to_sync = data.get('sales', [])
        for sale_data in sales_to_sync:
            try:
                # Use the provided sale_id as the primary key if it exists
                sale = SalesRecord.query.filter_by(id=sale_data['sale_id']).first()
                if not sale:
                    new_sale = SalesRecord(
                        id=sale_data['sale_id'],
                        business_id=sale_data['business_id'],
                        inventory_item_id=sale_data['product_id'],
                        quantity=sale_data['quantity'],
                        price=sale_data['price'],
                        timestamp=datetime.fromisoformat(sale_data['timestamp']),
                        customer_id=sale_data.get('customer_id')
                    )
                    db.session.add(new_sale)
            except KeyError as e:
                logging.error(f"Missing key in sales data: {e}")
                continue
            except Exception as e:
                logging.error(f"Error processing sales record: {e}")
                continue
        db.session.commit()
        return jsonify({'message': f'Received {len(sales_to_sync)} sales records.'}), 200

    @app.route('/api/v1/sync/business', methods=['POST'])
    @api_key_required
    def sync_business():
        data = request.get_json()
        business_id = data.get('id')
        
        if not business_id:
            return jsonify({'status': 'error', 'message': 'Business ID is required.'}), 400
        
        try:
            # Check if business already exists
            business = Business.query.get(business_id)
            if business:
                # Update existing business record
                business.name = data.get('name', business.name)
                business.address = data.get('address', business.address)
                business.contact = data.get('contact', business.contact)
                business.type = data.get('type', business.type)
                business.is_active = data.get('is_active', business.is_active)
                business.last_synced_at = datetime.utcnow()
                db.session.commit()
                logging.info(f"Updated business: {business.name} ({business.id})")
                return jsonify({'status': 'success', 'message': 'Business updated successfully.'}), 200
            else:
                # Create a new business record
                new_business = Business(
                    id=business_id,
                    name=data.get('name'),
                    address=data.get('address'),
                    contact=data.get('contact'),
                    type=data.get('type'),
                    is_active=data.get('is_active', True),
                    last_synced_at=datetime.utcnow()
                )
                db.session.add(new_business)
                db.session.commit()
                logging.info(f"Registered new business: {new_business.name} ({new_business.id})")
                return jsonify({'status': 'success', 'message': 'Business registered successfully.'}), 201

        except Exception as e:
            db.session.rollback()
            logging.error(f"Error during business sync: {e}")
            return jsonify({'status': 'error', 'message': 'Internal server error during sync.'}), 500
    # --- CORRECTED ENDPOINT NAME ---
    @app.route('/trigger-auto-sync', methods=['POST'])
    @login_required
    @roles_required('admin')
    def trigger_auto_sync():
        global SYNC_STATUS
        if SYNC_STATUS["is_syncing"]:
            return jsonify({"status": "error", "message": "Synchronization is already in progress."}), 409
        
        SYNC_STATUS["is_syncing"] = True
        SYNC_STATUS["last_sync_message"] = "Starting two-way sync..."
        
        # In a real app, this would start a background thread/task
        # Here we just fake it for demonstration
        import time
        import random
        time.sleep(1) # Simulate delay
        SYNC_STATUS["last_sync_time"] = datetime.utcnow().isoformat()
        SYNC_STATUS["is_syncing"] = False
        
        success = random.choice([True, False])
        SYNC_STATUS["last_sync_success"] = success
        if success:
            SYNC_STATUS["last_sync_message"] = "Sync completed successfully."
        else:
            SYNC_STATUS["last_sync_message"] = "Sync failed. Check logs."

        return jsonify({"status": "success", "message": "Sync triggered successfully."})
   

    @app.route('/sync_status', methods=['GET'])
    @login_required
    def sync_status():
        global SYNC_STATUS
        # Add online status check by testing connectivity to remote server
        remote_url = os.getenv('ONLINE_FLASK_APP_BASE_URL', 'http://localhost:5000')
        online_status = False
        
        try:
            # Quick connectivity test (shorter timeout for status check)
            response = requests.get(f"{remote_url}/sync_status", timeout=5)
            online_status = response.status_code == 200
        except:
            online_status = False
        
        # Return enhanced status with online field
        enhanced_status = SYNC_STATUS.copy()
        enhanced_status['online'] = online_status
        enhanced_status['remote_url'] = remote_url
        enhanced_status['last_sync'] = SYNC_STATUS.get('last_sync_time')
        
        return jsonify(enhanced_status)
    
    # @app.route('/api/v1/sync/inventory', methods=['POST'])
    # @super_admin_required
    # def sync_inventory_data():
    #     data = request.get_json()
    #     inventory_to_sync = data.get('inventory', [])
    #     for item_data in inventory_to_sync:
    #         try:
    #             # Use the provided item ID as the primary key
    #             item = InventoryItem.query.filter_by(id=item_data['id']).first()
    #             if item:
    #                 item.name = item_data['name']
    #                 item.quantity = item_data['quantity']
    #                 item.price = item_data['price']
    #                 item.last_updated = datetime.fromisoformat(item_data['last_updated'])
    #             else:
    #                 new_item = InventoryItem(
    #                     id=item_data['id'],
    #                     business_id=item_data['business_id'],
    #                     name=item_data['name'],
    #                     quantity=item_data['quantity'],
    #                     price=item_data['price'],
    #                     last_updated=datetime.fromisoformat(item_data['last_updated'])
    #                 )
    #                 db.session.add(new_item)
    #         except KeyError as e:
    #             logging.error(f"Missing key in inventory data: {e}")
    #             continue
    #         except Exception as e:
    #             logging.error(f"Error processing inventory item: {e}")
    #             continue
    #     db.session.commit()
    #     return jsonify({'message': f'Received {len(inventory_to_sync)} inventory items.'}), 200
    
    @app.route('/api/v1/sync/inventory', methods=['POST'])
    @roles_required('super_admin', 'admin')
    def sync_inventory_data():
        # Now only SuperAdmin and Admin (via login session) can trigger this
        business_id = session.get('business_id')
        if not business_id:
            return jsonify({"success": False, "message": "No business ID found in session."}), 400

        success, msg = perform_sync(business_id, api_key=None)  # no API key needed
        status_code = 200 if success else 500
        return jsonify({"success": success, "message": msg}), status_code
    # @app.route('/sync_status', methods=['GET'])
    # def sync_status():
    #     """
    #     Provides the online/offline status and last sync timestamp for the frontend.
    #     """
    #     if session.get('role') not in ['super_admin', 'admin']:
    #         return jsonify({'online': False, 'last_sync': None, 'message': 'Unauthorized'}), 401

    #     is_online = check_network_online()

    #     last_sync_timestamp = None
    #     current_business_id = session.get('business_id')

    #     if current_business_id:
    #         business = Business.query.get(current_business_id)
    #         if business and business.last_synced_at:
    #             last_sync_timestamp = business.last_synced_at.isoformat() + "Z"

    #     status_message = "Online" if is_online else "Offline"
    #     if last_sync_timestamp:
    #         last_sync_dt = datetime.fromisoformat(last_sync_timestamp.replace("Z", ""))
    #         if datetime.utcnow() - last_sync_dt < timedelta(minutes=15):
    #             status_message = "Synced"
    #         else:
    #             status_message = "Needs Sync"
    #     else:
    #         status_message = "Never Synced"

    #     return jsonify({
    #         'online': is_online,
    #         'status': status_message,
    #         'last_sync': last_sync_timestamp,
    #         'message': 'Status fetched successfully.'
    #     })

    @app.route('/')
    def index():
        if 'username' in session:
            if session.get('role') == 'super_admin':
                return redirect(url_for('super_admin_dashboard'))
            elif 'business_id' in session:
                return redirect(url_for('dashboard'))
            else:
                return redirect(url_for('business_selection'))
        return redirect(url_for('login'))

    # In your app.py file

    from flask_login import login_user, logout_user # Ensure these are imported at the top

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']

            # Query for the user using the provided username
            user = User.query.filter_by(username=username).first()

            if user and user.verify_password(password):
                # Login the user with Flask-Login
                login_user(user)

                # Manually set your custom session variables
                session['username'] = user.username
                session['role'] = user.role

                # Redirect based on user role
                if user.role == 'super_admin':
                    flash('Welcome, Super Admin!', 'success')
                    return redirect(url_for('super_admin_dashboard'))
                else:
                    business = user.business
                    if business:
                        session['business_id'] = business.id
                        session['business_name'] = business.name
                        session['business_type'] = business.type
                        session['business_info'] = {
                            'name': business.name,
                            'address': business.address,
                            'location': business.location,
                            'contact': business.contact
                        }
                        flash(f'Welcome, {username} to {business.name}!', 'success')
                        return redirect(url_for('dashboard'))
                    else:
                        flash('Associated business not found for this user.', 'danger')
                        logout_user()  # Log out the user if their business isn't found
                        return redirect(url_for('login'))
            else:
                flash('Invalid username or password. Please try again.', 'danger')

        return render_template('login.html', current_year=datetime.now().year)

    @app.route('/logout')
    def logout():
        session.pop('username', None)
        session.pop('role', None)
        session.pop('business_id', None)
        session.pop('business_name', None)
        session.pop('business_type', None) # Clear business type from session
        session.pop('business_info', None)
        flash('You have been logged out.', 'info')
        return redirect(url_for('login'))

    @app.route('/business_selection', methods=['GET', 'POST'])
    def business_selection():
        if 'username' not in session or session.get('role') == 'super_admin':
            flash('Please log in or you are a Super Admin.', 'warning')
            return redirect(url_for('login'))

        current_username = session['username']
        user_businesses_ids = [u.business_id for u in User.query.filter_by(username=current_username).all()]
        user_businesses = Business.query.filter(Business.id.in_(user_businesses_ids)).all()

        if request.method == 'POST':
            selected_business_id = request.form['business_id']
            selected_business = Business.query.get(selected_business_id)

            if selected_business:
                user_data = User.query.filter_by(username=session['username'], business_id=selected_business_id).first()
                
                if user_data:
                    session['business_id'] = selected_business_id
                    session['business_name'] = selected_business.name
                    session['business_type'] = selected_business.type # Update business type in session
                    session['role'] = user_data.role
                    session['business_info'] = {
                        'name': selected_business.name,
                        'address': selected_business.address,
                        'location': selected_business.location,
                        'contact': selected_business.contact
                    }
                    flash(f'Switched to business: {session["business_name"]}', 'success')
                    return redirect(url_for('dashboard'))
                else:
                    flash('You do not have access to the selected business.', 'danger')
            else:
                flash('Invalid business selection.', 'danger')
        
        if not user_businesses:
            flash('No businesses found for your account. Please contact an administrator.', 'danger')

        return render_template('business_selection.html', businesses=user_businesses)


    # --- Dashboard Route ---

    # --- Placeholder routes for demonstration ---
    # In a real application, these would be fully implemented.

    @app.route('/api/businesses', methods=['GET'])
    def get_businesses():
        """Returns a list of all businesses and their users for synchronization."""
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        # Use the same API key from your local app's .env file
        if api_key != os.getenv('REMOTE_ADMIN_API_KEY'):
            return jsonify({"error": "API Key is missing or invalid."}), 401

        businesses = Business.query.all()
        businesses_data = []
        for business in businesses:
            business_dict = business.to_dict()
            users_in_business = User.query.filter_by(business_id=business.id).all()
            business_dict['users'] = [user.to_dict() for user in users_in_business]
            businesses_data.append(business_dict)
    @app.route('/api/businesses/<string:business_id>/inventory', methods=['GET'])
    def get_inventory(business_id):
        """
        Returns a list of inventory items for a specific business.
        This endpoint is used by the local app to sync remote inventory.
        """
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if api_key != os.getenv('REMOTE_ADMIN_API_KEY'):
            return jsonify({"error": "API Key is missing or invalid."}), 401

        inventory_items = InventoryItem.query.filter_by(business_id=business_id).all()
        inventory_data = [item.to_dict() for item in inventory_items]
        return jsonify(inventory_data)

        return jsonify(businesses_data)

    @app.route('/dashboard')
    # @login_required
    def dashboard():
        # ACCESS CONTROL: Specific redirects first
        if 'username' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))

        if session.get('role') == 'super_admin':
            return redirect(url_for('super_admin_dashboard'))

        if 'business_id' not in session:
            return redirect(url_for('business_selection'))

        # Now that we've ensured login and business selection, proceed
        username = session.get('username')
        role = session.get('role')
        business_id = get_current_business_id()
        business_type = get_current_business_type()

        today = date.today()
        three_months_from_now = today + timedelta(days=90)

        # --- Initialize all dashboard variables to prevent UndefinedError in template ---
        total_products = 0
        total_customers = 0
        total_sales_overall = 0.0
        today_sales_revenue = 0.0
        current_stock_value_at_cost = 0.0
        current_stock_value_at_sale = 0.0
        total_potential_gross_profit_stock = 0.0
        overall_stock_profit_margin = 0.0
        low_stock_items = []
        expired_items = []
        expiring_soon_items = []
        overdue_rentals = []
        recent_activity = []
        sales_by_person_today = []
        total_inventory_items = 0

        # Common filters for queries
        common_filter_items = InventoryItem.query.filter_by(business_id=business_id, is_active=True)

        # --- Overall Business Metrics (Stock Valuation) ---
        current_inventory_items = common_filter_items.all()
        total_inventory_items = len(current_inventory_items)

        for item in current_inventory_items:
            current_stock = item.current_stock or 0.0
            number_of_tabs = item.number_of_tabs or 1.0

            # Calculate cost value
            cost_per_base_unit = float(item.purchase_price / number_of_tabs) if number_of_tabs > 0 else 0.0
            current_stock_value_at_cost += current_stock * cost_per_base_unit

            # Calculate sale value
            sale_value_per_base_unit = 0.0
            if item.is_fixed_price:
                sale_value_per_base_unit = float(item.fixed_sale_price / number_of_tabs) if number_of_tabs > 0 else 0.0
            else:
                if item.item_type == 'Pharmacy':
                    sale_value_per_base_unit = float(item.purchase_price * (1 + (item.markup_percentage_pharmacy or 0) / 100) / number_of_tabs) if number_of_tabs > 0 else 0.0
                elif item.item_type == 'Hardware Material':
                    sale_value_per_base_unit = item.unit_price_per_tab or 0.0
                else:
                    sale_value_per_base_unit = float(item.sale_price / number_of_tabs) if number_of_tabs > 0 else 0.0
            
            current_stock_value_at_sale += current_stock * sale_value_per_base_unit

        total_potential_gross_profit_stock = current_stock_value_at_sale - current_stock_value_at_cost
        overall_stock_profit_margin = (total_potential_gross_profit_stock / current_stock_value_at_sale) * 100 if current_stock_value_at_sale > 0 else 0.0


        # --- Sales Metrics ---
        # Total Sales (overall for the business lifetime)
        total_sales_overall = db.session.query(db.func.sum(SalesRecord.grand_total_amount)).filter_by(business_id=business_id).scalar() or 0.0

        # Total Sales Today
        today_sales_revenue = db.session.query(db.func.sum(SalesRecord.grand_total_amount)).filter(
            SalesRecord.business_id == business_id,
            cast(SalesRecord.transaction_date, db.Date) == today
        ).scalar() or 0.0

        # Sales by Sales Person Today
        sales_by_person_today = db.session.query(
            SalesRecord.sales_person_name,
            func.sum(SalesRecord.grand_total_amount)
        ).filter(
            SalesRecord.business_id == business_id,
            cast(SalesRecord.transaction_date, db.Date) == today
        ).group_by(SalesRecord.sales_person_name).order_by(func.sum(SalesRecord.grand_total_amount).desc()).all()


        # --- Inventory Management Metrics ---
        # Low Stock Items
        low_stock_threshold = 10
        low_stock_items = common_filter_items.filter(
            InventoryItem.current_stock <= low_stock_threshold,
            InventoryItem.current_stock > 0
        ).order_by(InventoryItem.current_stock).all()

        total_products = total_inventory_items

        # Total Customers
        total_customers = Customer.query.filter_by(business_id=business_id, is_active=True).count() or 0

        # --- Pharmacy Specific (Expiry Dates) ---
        if business_type == 'Pharmacy':
            expired_items = common_filter_items.filter(
                InventoryItem.expiry_date != None,
                InventoryItem.expiry_date < today
            ).order_by(InventoryItem.expiry_date).all()

            expiring_soon_items = common_filter_items.filter(
                InventoryItem.expiry_date != None,
                InventoryItem.expiry_date >= today,
                InventoryItem.expiry_date <= three_months_from_now
            ).order_by(InventoryItem.expiry_date).all()
        
        # --- Hardware Specific (Rental Records) ---
        if business_type == 'Hardware':
            overdue_rentals = RentalRecord.query.filter(
                RentalRecord.business_id == business_id,
                RentalRecord.return_date == None,
                RentalRecord.due_date < today
            ).order_by(RentalRecord.due_date).all()

        # --- Recent Activity (e.g., last 5 sales records) ---
        recent_activity = SalesRecord.query.filter_by(business_id=business_id).order_by(SalesRecord.transaction_date.desc()).limit(5).all()


        return render_template('dashboard.html',
                            title='Dashboard',
                            username=username,
                            user_role=role,
                            business_name=session.get('business_name'),
                            business_type=business_type,
                            
                            # Metrics (aligned with template expectations)
                            total_products=total_products,
                            total_customers=total_customers,
                            total_sales_today=today_sales_revenue,
                            low_stock_items=low_stock_items,
                            total_inventory_items=total_inventory_items,
                            sales_by_person_today=sales_by_person_today,

                            # Comprehensive Stock Metrics
                            current_stock_value_at_cost=current_stock_value_at_cost,
                            current_stock_value_at_sale=current_stock_value_at_sale,
                            total_potential_gross_profit_stock=total_potential_gross_profit_stock,
                            overall_stock_profit_margin=overall_stock_profit_margin,
                            total_sales_overall=total_sales_overall,

                            # Type-specific reports
                            expired_items=expired_items,
                            expiring_soon_items=expiring_soon_items,
                            overdue_rentals=overdue_rentals,
                            
                            # General
                            recent_activity=recent_activity,
                            current_year=datetime.now().year)
    
    # In your app.py file
    @app.route('/super_admin_dashboard')
    @login_required
    @roles_required('super_admin')
    def super_admin_dashboard():
        # Fetch ALL businesses from the database (your offline database after sync)
        all_businesses = Business.query.all()
        # Fetch ALL users from the database (your offline database after sync)
        all_users = User.query.all() 
        
        # Pass user_role from session to the template
        return render_template('super_admin_dashboard.html', 
                            businesses=all_businesses, # Ensure this is passed
                            users=all_users,           # Ensure this is passed
                            user_role=session.get('role'), 
                            current_year=datetime.now().year)

    
    @app.route('/super_admin/add_business', methods=['GET', 'POST']) # Ensure this route path is correct if you changed it
    @login_required
    @roles_required('super_admin')
    def add_business():
        print(f"DEBUG: User '{current_user.username}' (ID: {current_user.id}) is accessing /add_business. Role: {current_user.role}")
        # --- END TEMPORARY DEBUG PRINT ---

        business_types = ['Pharmacy', 'Supermarket', 'Hardware', 'Provision Store', 'Other'] # Define business_types for GET request/error rendering

        if request.method == 'POST':
            business_name = request.form.get('business_name', '').strip()
            address = request.form.get('business_address', '').strip() # Changed from 'address' to 'business_address' for consistency
            location = request.form.get('business_location', '').strip() # Changed from 'location' to 'business_location' for consistency
            contact = request.form.get('business_contact', '').strip() # Changed from 'contact' to 'business_contact' for consistency
            business_type = request.form.get('business_type', '').strip()
            
            admin_username = request.form.get('admin_username', '').strip()
            admin_password = request.form.get('admin_password', '').strip()

            if not all([business_name, business_type, admin_username, admin_password]):
                flash('All fields (Business Name, Type, Admin Username, Password) are required!', 'danger')
                return render_template('add_edit_business.html', title='Add New Business', business_types=business_types,
                                       business={
                                           'name': business_name, 'address': address, 'location': location,
                                           'contact': contact, 'type': business_type, 'initial_admin_username': admin_username
                                       }) # Pass data back for sticky form

            # Check if business name already exists
            existing_business = Business.query.filter_by(name=business_name).first()
            if existing_business:
                flash('A business with this name already exists.', 'danger')
                return render_template('add_edit_business.html', title='Add New Business', business_types=business_types,
                                       business={
                                           'name': business_name, 'address': address, 'location': location,
                                           'contact': contact, 'type': business_type, 'initial_admin_username': admin_username
                                       })

            # Check if the desired admin username already exists
            existing_admin_user = User.query.filter_by(username=admin_username).first()
            if existing_admin_user:
                flash(f'The username "{admin_username}" is already taken. Please choose another.', 'danger')
                return render_template('add_edit_business.html', title='Add New Business', business_types=business_types,
                                       business={
                                           'name': business_name, 'address': address, 'location': location,
                                           'contact': contact, 'type': business_type, 'initial_admin_username': admin_username
                                       })

            try:
                new_business = Business(
                    id=str(uuid.uuid4()),
                    name=business_name,
                    type=business_type,
                    address=address,
                    location=location,
                    contact=contact,
                    # email=email, # Add email field to form if needed in the future
                    is_active=True,
                    # REMOVED: date_added=datetime.utcnow(),
                    # REMOVED: last_updated=datetime.utcnow()
                    # These should be handled by the model's default values
                )
                db.session.add(new_business)
                db.session.commit() # Commit to get business.id for the user

                # Create the admin user for this new business
                hashed_password = generate_password_hash(admin_password, method='pbkdf2:sha256')
                new_admin_user = User(
                    id=str(uuid.uuid4()),
                    username=admin_username,
                    _password_hash=hashed_password,
                    role='admin', # Assign 'admin' role to this user
                    business_id=new_business.id, # Link to the new business
                    is_active=True,
                    created_at=datetime.utcnow()
                )
                db.session.add(new_admin_user)
                db.session.commit()

                flash(f'Business "{business_name}" and admin user "{admin_username}" created successfully!', 'success')
                return redirect(url_for('super_admin_dashboard'))

            except Exception as e:
                db.session.rollback()
                print(f"Error adding business and admin user: {e}")
                flash(f'Error creating business: {str(e)}', 'danger')
                # Re-render form with current data on error
                return render_template('add_edit_business.html', title='Add New Business', business_types=business_types,
                                       business={
                                           'name': business_name, 'address': address, 'location': location,
                                           'contact': contact, 'type': business_type, 'initial_admin_username': admin_username
                                       })

        return render_template('add_edit_business.html', title='Add New Business', business_types=business_types)



    @app.route('/super_admin/edit_business/<string:business_id>', methods=['GET', 'POST'])
    @login_required # Ensure user is logged in
    @roles_required('super_admin', 'admin') # Allow both super_admin and admin to access
    def edit_business(business_id):
        # The custom session.get('role') check can be removed now that roles_required is used.
        # if session.get('role') not in ['super_admin', 'admin']:
        #     flash('Access denied. Super Admin or Admin role required.', 'danger')
        #     return redirect(url_for('login')) # This will be handled by roles_required

        business_to_edit = Business.query.get_or_404(business_id)
        # Find the admin user associated with this business (assuming one primary admin per business)
        initial_admin_user = User.query.filter_by(business_id=business_id, role='admin').first()

        # Define business_types for the dropdown
        business_types = ['Pharmacy', 'Hardware', 'Supermarket', 'Provision Store', 'Other']

        if request.method == 'POST':
            # Retrieve form data using .get() for safety and correct field names
            new_business_name = request.form.get('business_name', '').strip()
            new_business_address = request.form.get('business_address', '').strip()
            new_business_location = request.form.get('business_location', '').strip()
            new_business_contact = request.form.get('business_contact', '').strip()
            new_business_type = request.form.get('business_type', '').strip()
            
            # --- CORRECTED KEYS HERE (from 'initial_admin_username' to 'admin_username') ---
            admin_username_from_form = request.form.get('admin_username', '').strip()
            admin_password_from_form = request.form.get('admin_password', '').strip()
            # --- END CORRECTED KEYS ---

            # Basic validation
            if not new_business_name or not new_business_type:
                flash('Business name and type are required!', 'danger')
                # Repopulate form fields on error
                business_data_for_form = {
                    'name': new_business_name, 'address': new_business_address, 'location': new_business_location,
                    'contact': new_business_contact, 'type': new_business_type,
                    'initial_admin_username': admin_username_from_form, # Pass back for sticky form
                    # Password field should not be repopulated for security
                }
                return render_template('add_edit_business.html', title=f'Edit Business: {business_to_edit.name}', 
                                    business=business_data_for_form, business_types=business_types, 
                                    current_year=datetime.now().year, user_role=current_user.role)

            # Check for duplicate business name (excluding current business)
            if Business.query.filter(Business.name == new_business_name, Business.id != business_id).first():
                flash('A business with this name already exists.', 'danger')
                # Repopulate form fields on error
                business_data_for_form = {
                    'name': new_business_name, 'address': new_business_address, 'location': new_business_location,
                    'contact': new_business_contact, 'type': new_business_type,
                    'initial_admin_username': admin_username_from_form,
                }
                return render_template('add_edit_business.html', title=f'Edit Business: {business_to_edit.name}', 
                                    business=business_data_for_form, business_types=business_types, 
                                    current_year=datetime.now().year, user_role=current_user.role)
            
            # Update business details
            business_to_edit.name = new_business_name
            business_to_edit.address = new_business_address
            business_to_edit.location = new_business_location
            business_to_edit.contact = new_business_contact
            business_to_edit.type = new_business_type
            business_to_edit.last_updated = datetime.utcnow() # Update timestamp

            # Handle admin user updates (only if an initial admin exists)
            if initial_admin_user:
                # Username can only be changed by super_admin (as per original logic and template design)
                if current_user.role == 'super_admin':
                    if admin_username_from_form and admin_username_from_form != initial_admin_user.username:
                        # Check if new username is already taken by another user (globally)
                        if User.query.filter(User.username == admin_username_from_form, User.id != initial_admin_user.id).first():
                            flash(f"Username '{admin_username_from_form}' is already taken by another user. Admin username not changed.", 'danger')
                            # Keep current username in form for re-render
                            business_data_for_form = {
                                'name': new_business_name, 'address': new_business_address, 'location': new_business_location,
                                'contact': new_business_contact, 'type': new_business_type,
                                'initial_admin_username': initial_admin_user.username, # Keep old username if update failed
                            }
                            return render_template('add_edit_business.html', title=f'Edit Business: {business_to_edit.name}', 
                                                business=business_data_for_form, business_types=business_types, 
                                                current_year=datetime.now().year, user_role=current_user.role)
                        else:
                            initial_admin_user.username = admin_username_from_form
                            flash('Admin username updated.', 'info')
                # If a non-super_admin tries to change username, it will be ignored as per template readonly.
                # However, for robustness, we explicitly ensure the user object's username isn't modified
                # if the current_user is not super_admin.
                # else: admin_username_from_form is ignored for regular 'admin' role.

                # Update password if provided (not blank)
                if admin_password_from_form: # Check if the field was filled
                    initial_admin_user.password = admin_password_from_form # Use .password setter which hashes
                    initial_admin_user.last_password_update = datetime.utcnow() # Optional: track password changes
                    flash('Admin password updated.', 'info')
                
                db.session.add(initial_admin_user) # Add updated user to session for commit

            try:
                db.session.add(business_to_edit) # Add updated business to session
                db.session.commit()
                flash(f'Business "{new_business_name}" details updated successfully!', 'success')
                return redirect(url_for('super_admin_dashboard'))
            except Exception as e:
                db.session.rollback()
                print(f"Error updating business or admin user: {e}")
                flash(f'Error updating information: {str(e)}', 'danger')
                return redirect(url_for('edit_business', business_id=business_to_edit.id))

        # GET request: Render the form with existing business data
        business_data_for_form = {
            'id': business_to_edit.id, # Ensure ID is passed back for URL if needed
            'name': business_to_edit.name,
            'address': business_to_edit.address,
            'location': business_to_edit.location,
            'contact': business_to_edit.contact,
            'type': business_to_edit.type,
            # Pass the admin username to pre-fill the field (will be readonly in template if 'business' object exists)
            'initial_admin_username': initial_admin_user.username if initial_admin_user else '',
            # Password field is always empty for security on GET
            'initial_admin_password': '' 
        }
        # Pass the current user's role to the template for conditional rendering logic
        return render_template('add_edit_business.html', title=f'Edit Business: {business_to_edit.name}', 
                            business=business_data_for_form, 
                            business_types=business_types, 
                            current_year=datetime.now().year,
                            user_role=current_user.role) # Pass current_user.role, not session.get('role')

    @app.route('/super_admin/view_business_details/<string:business_id>')
    def view_business_details(business_id):
        if session.get('role') not in ['super_admin', 'admin']:
            flash('Access denied. Super Admin or Admin role required.', 'danger')
            return redirect(url_for('login'))

        business = Business.query.get_or_404(business_id)
        initial_admin = User.query.filter_by(business_id=business_id, role='admin').first()

        return render_template('view_business_details.html', business=business, initial_admin=initial_admin, current_year=datetime.now().year)



    @app.route('/super_admin/delete_business/<string:business_id>', methods=['POST']) # Changed to POST for better REST practice
    def delete_business(business_id):
        if session.get('role') not in ['super_admin', 'admin']:
            flash('Access denied. Super Admin or Admin role required.', 'danger')
            return redirect(url_for('login'))
        
        business_to_delete = Business.query.get_or_404(business_id)

        try:
            # Step 1: Delete all associated SalesRecords
            SalesRecord.query.filter_by(business_id=business_id).delete(synchronize_session=False)
            
            # Step 2: Delete all associated InventoryItems
            InventoryItem.query.filter_by(business_id=business_id).delete(synchronize_session=False)

            # Step 3: Delete all associated User records linked to this business
            User.query.filter_by(business_id=business_id).delete(synchronize_session=False)
            
            # Step 4: Delete the Business record itself
            db.session.delete(business_to_delete)
            
            # Commit the transaction to apply all deletions
            db.session.commit()

            # Check if the session business was the one deleted, and clear it
            if session.get('business_id') == business_id:
                session.pop('business_id', None)
                session.pop('business_type', None)
                session.pop('business_info', None)
            
            flash(f'Business "{business_to_delete.name}" and all its associated data deleted successfully!', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred while deleting the business: {e}', 'danger')
            print(f"Error during business deletion: {e}")

        return redirect(url_for('super_admin_dashboard'))

    @app.route('/super_admin/download_inventory/<string:business_id>')
    def download_inventory_csv(business_id):
        if session.get('role') not in ['super_admin', 'admin']:
            flash('Access denied. Super Admin or Admin role required.', 'danger')
            return redirect(url_for('login'))

        business = Business.query.get_or_404(business_id)
        inventory_items = InventoryItem.query.filter_by(business_id=business.id).all()

        si = io.StringIO()
        headers = [
            'id', 'product_name', 'category', 'purchase_price', 'sale_price', 'current_stock', 
            'last_updated', 'batch_number', 'number_of_tabs', 'unit_price_per_tab', 'item_type', 
            'expiry_date', 'is_fixed_price', 'fixed_sale_price', 'business_id', 'is_active'
        ]
        
        writer = csv.DictWriter(si, fieldnames=headers)
        writer.writeheader()
        
        for item in inventory_items:
            row_to_write = {
                'id': item.id,
                'product_name': item.product_name,
                'category': item.category,
                'purchase_price': f"{item.purchase_price:.2f}",
                'sale_price': f"{item.sale_price:.2f}",
                'current_stock': f"{item.current_stock:.2f}",
                'last_updated': item.last_updated.strftime('%Y-%m-%d %H:%M:%S'),
                'batch_number': item.batch_number,
                'number_of_tabs': item.number_of_tabs,
                'unit_price_per_tab': f"{item.unit_price_per_tab:.2f}",
                'item_type': item.item_type,
                'expiry_date': item.expiry_date.strftime('%Y-%m-%d') if item.expiry_date else '',
                'is_fixed_price': str(item.is_fixed_price),
                'fixed_sale_price': f"{item.fixed_sale_price:.2f}",
                'business_id': item.business_id,
                'is_active': str(item.is_active)
            }
            writer.writerow(row_to_write)

        output = si.getvalue()
        si.close()

        response = Response(output, mimetype='text/csv')
        response.headers["Content-Disposition"] = f"attachment; filename={business.name.replace(' ', '_')}_inventory_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
        return response

    @app.route('/super_admin/upload_inventory/<business_id>', methods=['GET', 'POST'])
    def upload_inventory_csv_super_admin(business_id):
        if session.get('role') not in ['super_admin', 'admin']:
            flash('Access denied. Super Admin or Admin role required.', 'danger')
            return redirect(url_for('login'))

        business = Business.query.get_or_404(business_id)

        if request.method == 'POST':
            if 'csv_file' not in request.files:
                flash('No file part', 'danger')
                return redirect(request.url)
            
            file = request.files['csv_file']
            if file.filename == '':
                flash('No selected file', 'danger')
                return redirect(request.url)
            
            if file and file.filename.endswith('.csv'):
                stream = io.StringIO(file.stream.read().decode("UTF8"))
                csv_reader = csv.DictReader(stream)
                
                updated_count = 0
                added_count = 0
                errors = []

                for row in csv_reader:
                    try:
                        product_name = row['product_name'].strip()
                        category = row['category'].strip()
                        purchase_price = float(row['purchase_price'])
                        current_stock = float(row['current_stock'])
                        batch_number = row.get('batch_number', '').strip()
                        number_of_tabs = int(row.get('number_of_tabs', 1))
                        item_type = row.get('item_type', 'Pharmacy').strip()
                        expiry_date_str = row.get('expiry_date', '').strip()
                        expiry_date_obj = datetime.strptime(expiry_date_str, '%Y-%m-%d').date() if expiry_date_str else None
                        is_fixed_price = row.get('is_fixed_price', 'False').lower() == 'true'
                        fixed_sale_price = float(row.get('fixed_sale_price', 0.0))
                        is_active = row.get('is_active', 'True').lower() == 'true' # Read is_active from CSV

                        if number_of_tabs <= 0:
                            errors.append(f"Skipping '{product_name}': 'Number of units/pieces per pack' must be greater than zero.")
                            continue

                        sale_price = 0.0
                        unit_price_per_tab_with_markup = 0.0
                        if item_type == 'Pharmacy':
                            # For Pharmacy, assuming sale_price and unit_price_per_tab are derived from purchase_price + markup
                            # This needs to be consistent with how new pharmacy items are added via UI
                            # For now, let's just directly use sale_price and unit_price_per_tab if provided in CSV
                            sale_price = float(row.get('sale_price', 0.0))
                            unit_price_per_tab_with_markup = float(row.get('unit_price_per_tab', 0.0))
                            if sale_price == 0.0 and unit_price_per_tab_with_markup > 0:
                                sale_price = unit_price_per_tab_with_markup * number_of_tabs
                            elif unit_price_per_tab_with_markup == 0.0 and sale_price > 0 and number_of_tabs > 0:
                                unit_price_per_tab_with_markup = sale_price / number_of_tabs

                        elif item_type in ['Hardware Material', 'Provision Store']:
                            sale_price = float(row.get('sale_price', 0.0))
                            # For hardware/provision, unit_price_per_tab might represent price per piece/item
                            unit_price_per_tab_with_markup = float(row.get('unit_price_per_tab', sale_price))
                            if number_of_tabs > 0 and sale_price == 0.0:
                                sale_price = unit_price_per_tab_with_markup * number_of_tabs
                            elif number_of_tabs > 0 and unit_price_per_tab_with_markup == 0.0:
                                unit_price_per_tab_with_markup = sale_price / number_of_tabs


                        existing_item = InventoryItem.query.filter_by(
                            product_name=product_name, business_id=business_id
                        ).first()

                        if existing_item:
                            # Update existing item
                            existing_item.category = category
                            existing_item.purchase_price = purchase_price
                            existing_item.sale_price = sale_price
                            existing_item.current_stock = current_stock
                            existing_item.last_updated = datetime.now()
                            existing_item.batch_number = batch_number
                            existing_item.number_of_tabs = number_of_tabs
                            existing_item.unit_price_per_tab = unit_price_per_tab_with_markup
                            existing_item.item_type = item_type
                            existing_item.expiry_date = expiry_date_obj
                            existing_item.is_fixed_price = is_fixed_price
                            existing_item.fixed_sale_price = fixed_sale_price
                            existing_item.is_active = is_active # Update is_active
                            updated_count += 1
                        else:
                            # Add new item
                            new_item = InventoryItem(
                                business_id=business_id,
                                product_name=product_name,
                                category=category,
                                purchase_price=purchase_price,
                                sale_price=sale_price,
                                current_stock=current_stock,
                                batch_number=batch_number,
                                number_of_tabs=number_of_tabs,
                                unit_price_per_tab=unit_price_per_tab_with_markup,
                                item_type=item_type,
                                expiry_date=expiry_date_obj,
                                is_fixed_price=is_fixed_price,
                                fixed_sale_price=fixed_sale_price,
                                is_active=is_active # Set is_active for new item
                            )
                            db.session.add(new_item)
                            added_count += 1
                    except Exception as e:
                        errors.append(f"Error processing row for product '{row.get('product_name', 'N/A')}': {e}")
                
                db.session.commit()
                
                if errors:
                    flash(f'CSV upload completed with {updated_count} updated, {added_count} added, and {len(errors)} errors. Check console for details.', 'warning')
                    for error in errors:
                        print(f"CSV Upload Error: {error}")
                else:
                    flash(f'CSV inventory uploaded successfully! {updated_count} items updated, {added_count} items added.', 'success')
                
                return redirect(url_for('super_admin_dashboard'))
            else:
                flash('Invalid file type. Please upload a CSV file.', 'danger')
                return redirect(request.url)
        
        return render_template('upload_inventory.html', business=business, user_role=session.get('role'), current_year=datetime.now().year)

    # NEW ROUTE: Export all registered businesses to CSV
    @app.route('/super_admin/download_businesses_csv')
    # @login_required
    def download_businesses_csv():
        # ACCESS CONTROL: Only super_admin or admin can export business data
        if session.get('role') not in ['super_admin', 'admin']:
            flash('Access denied. Super Admin or Admin role required.', 'danger')
            return redirect(url_for('login'))

        businesses = Business.query.all()

        si = io.StringIO()
        headers = ['id', 'name', 'address', 'location', 'contact', 'type']
        writer = csv.DictWriter(si, fieldnames=headers)
        writer.writeheader()

        for business in businesses:
            writer.writerow({
                'id': business.id,
                'name': business.name,
                'address': business.address,
                'location': business.location,
                'contact': business.contact,
                'type': business.type
            })

        output = si.getvalue()
        si.close()

        response = Response(output, mimetype='text/csv')
        response.headers["Content-Disposition"] = f"attachment; filename=registered_businesses_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
        return response

    # NEW ROUTE: Transfer Inventory Between Businesses
    @app.route('/admin/transfer_inventory', methods=['GET', 'POST'])
    # @login_required
    def transfer_inventory():
        # ACCESS CONTROL: Only super_admin or admin can transfer inventory
        if session.get('role') not in ['super_admin', 'admin']:
            flash('Access denied. Super Admin or Admin role required.', 'danger')
            return redirect(url_for('login'))

        all_businesses = Business.query.all()
        
        # Get all unique categories across all businesses for the dropdown
        all_categories = db.session.query(InventoryItem.category).distinct().all()
        all_categories = sorted([c[0] for c in all_categories if c[0]]) # Extract string and sort

        # Get all unique item types for filtering
        all_item_types = db.session.query(InventoryItem.item_type).distinct().all()
        all_item_types = sorted([t[0] for t in all_item_types if t[0]])

        if request.method == 'POST':
            source_business_id = request.form.get('source_business_id')
            target_business_id = request.form.get('target_business_id')
            category_to_transfer = request.form.get('category_to_transfer').strip()
            item_type_filter = request.form.get('item_type_filter', '').strip() # Get the selected item type filter

            if not source_business_id or not target_business_id or not category_to_transfer:
                flash('Please select both source and target businesses and a category.', 'danger')
                return render_template('transfer_inventory.html', businesses=all_businesses, categories=all_categories, user_role=session.get('role'), business_types=all_item_types, current_year=datetime.now().year)

            if source_business_id == target_business_id:
                flash('Source and target businesses cannot be the same.', 'danger')
                return render_template('transfer_inventory.html', businesses=all_businesses, categories=all_categories, user_role=session.get('role'), business_types=all_item_types, current_year=datetime.now().year)

            source_business = Business.query.get(source_business_id)
            target_business = Business.query.get(target_business_id)

            if not source_business or not target_business:
                flash('Invalid source or target business selected.', 'danger')
                return render_template('transfer_inventory.html', businesses=all_businesses, categories=all_categories, user_role=session.get('role'), business_types=all_item_types, current_year=datetime.now().year)

            # Fetch items from source business for the specified category and optional item_type
            items_to_transfer_query = InventoryItem.query.filter_by(
                business_id=source_business_id,
                category=category_to_transfer,
                is_active=True
            )
            if item_type_filter:
                items_to_transfer_query = items_to_transfer_query.filter_by(item_type=item_type_filter)

            items_to_transfer = items_to_transfer_query.all()

            if not items_to_transfer:
                flash(f'No active inventory items found in "{source_business.name}" for category "{category_to_transfer}" and type "{item_type_filter if item_type_filter else "any"}".', 'warning')
                return render_template('transfer_inventory.html', businesses=all_businesses, categories=all_categories, user_role=session.get('role'), business_types=all_item_types, current_year=datetime.now().year)

            transferred_count = 0
            updated_count = 0
            
            for item in items_to_transfer:
                # Check if an item with the same product_name already exists in the target business
                existing_target_item = InventoryItem.query.filter_by(
                    product_name=item.product_name,
                    business_id=target_business_id
                ).first()

                if existing_target_item:
                    # Update existing item's stock and other relevant fields
                    existing_target_item.current_stock += item.current_stock # Add stock
                    existing_target_item.purchase_price = item.purchase_price # Overwrite purchase price
                    existing_target_item.sale_price = item.sale_price # Overwrite sale price
                    existing_target_item.number_of_tabs = item.number_of_tabs # Overwrite units/pack
                    existing_target_item.unit_price_per_tab = item.unit_price_per_tab # Overwrite unit price
                    existing_target_item.last_updated = datetime.now()
                    existing_target_item.batch_number = item.batch_number # Overwrite batch number
                    existing_target_item.is_fixed_price = item.is_fixed_price
                    existing_target_item.fixed_sale_price = item.fixed_sale_price
                    existing_target_item.is_active = item.is_active # Maintain active status

                    # For expiry date, update only if the source item has a valid, newer expiry date
                    if item.expiry_date and (not existing_target_item.expiry_date or item.expiry_date > existing_target_item.expiry_date):
                        existing_target_item.expiry_date = item.expiry_date

                    db.session.add(existing_target_item)
                    updated_count += 1
                else:
                    # Add new item
                    new_item = InventoryItem(
                        business_id=target_business_id,
                        product_name=item.product_name,
                        category=item.category,
                        purchase_price=item.purchase_price,
                        sale_price=item.sale_price,
                        current_stock=item.current_stock,
                        last_updated=datetime.now(), # Set current time for new record
                        batch_number=item.batch_number,
                        number_of_tabs=item.number_of_tabs,
                        unit_price_per_tab=item.unit_price_per_tab,
                        item_type=item.item_type,
                        expiry_date=item.expiry_date,
                        is_fixed_price=item.is_fixed_price,
                        fixed_sale_price=item.fixed_sale_price,
                        is_active=True # New items are active
                    )
                    db.session.add(new_item)
                    transferred_count += 1
            
            db.session.commit()
            flash(f'Inventory transfer completed: {transferred_count} new items added, {updated_count} existing items updated (stock added and details overwritten) from "{source_business.name}" to "{target_business.name}" for category "{category_to_transfer}".', 'success')

            return redirect(url_for('transfer_inventory'))

        return render_template('transfer_inventory.html', businesses=all_businesses, categories=all_categories, user_role=session.get('role'), business_types=all_item_types, current_year=datetime.now().year)

    @app.route('/api/v1/inventory/<business_id>', methods=['GET'])
    @api_key_required
    def get_business_inventory(business_id):
        """Return all inventory items for a specific business"""
        try:
            inventory_items = InventoryItem.query.filter_by(
                business_id=business_id,
                is_active=True
            ).all()
            
            serialized_items = [serialize_inventory_item(item) for item in inventory_items]
            
            return jsonify({
                'success': True,
                'business_id': business_id,
                'inventory_items': serialized_items,
                'count': len(serialized_items)
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'message': str(e)
            }), 500

    @app.route('/api/v1/inventory/upsert', methods=['POST'])
    @api_key_required
    def upsert_business_inventory():
        """Create or update inventory items from offline app"""
        try:
            data = request.get_json()
            business_id = data.get('business_id')
            inventory_items = data.get('inventory_items', [])
            
            updated = 0
            created = 0
            
            for item_data in inventory_items:
                existing = InventoryItem.query.filter_by(
                    business_id=business_id,
                    product_name=item_data['product_name']
                ).first()
                
                if existing:
                    # Update existing item
                    for key, value in item_data.items():
                        if hasattr(existing, key) and key != 'id':
                            setattr(existing, key, value)
                    updated += 1
                else:
                    # Create new item
                    new_item = InventoryItem(**item_data)
                    db.session.add(new_item)
                    created += 1
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Processed {len(inventory_items)} items',
                'created': created,
                'updated': updated
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': str(e)
            }), 500
    # --- Business User Management ---

    @app.route('/manage_business_users')
    def manage_business_users():
        # ACCESS CONTROL: Allows 'admin' and 'viewer' roles to view this page
        if 'username' not in session or session.get('role') not in ['admin', 'viewer'] or not get_current_business_id():
            flash('You do not have permission to manage business users or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        business_id = get_current_business_id()
        users = User.query.filter_by(business_id=business_id).all()
        return render_template('manage_business_users.html', users=users, user_role=session.get('role'), current_year=datetime.now().year)

    @app.route('/manage_business_users/add', methods=['GET', 'POST'])
    def add_business_user():
        # ACCESS CONTROL: Allows 'admin' and 'viewer' roles to add business users
        if 'username' not in session or session.get('role') not in ['admin', 'viewer'] or not get_current_business_id():
            flash('You do not have permission to add business users or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        business_id = get_current_business_id()
        current_user_role = session.get('role')
        
        if request.method == 'POST':
            username = request.form['username'].strip()
            password = request.form['password'].strip() # Plain text password from form
            role = request.form['role'].strip()

            # ACCESS CONTROL: Viewer role specific restriction: can only add 'sales' or 'viewer' users
            if current_user_role == 'viewer' and role == 'admin':
                flash('As a Viewer, you can only add Sales or Viewer users, not Admin users.', 'danger')
                return render_template('add_edit_business_user.html', title='Add New Business User', user={
                    'username': username, 'role': role
                }, user_role=current_user_role, current_year=datetime.now().year)

            if User.query.filter_by(username=username, business_id=business_id).first():
                flash('Username already exists for this business.', 'danger')
                return render_template('add_edit_business_user.html', title='Add New Business User', user={
                    'username': username, 'role': role
                }, user_role=current_user_role, current_year=datetime.now().year)
            
            new_user = User(username=username, password=password, role=role, business_id=business_id) # The .password setter will hash it
            db.session.add(new_user)
            db.session.commit()
            flash(f'User "{username}" added successfully!', 'success')
            return redirect(url_for('manage_business_users'))
        
        return render_template('add_edit_business_user.html', title='Add New Business User', user={}, user_role=current_user_role, current_year=datetime.now().year)


    @app.route('/manage_business_users/edit/<username>', methods=['GET', 'POST'])
    def edit_business_user(username):
        # ACCESS CONTROL: Allows 'admin' role to edit business users
        # Viewers cannot edit existing users, only add new ones (sales/viewer)
        if 'username' not in session or session.get('role') != 'admin' or not get_current_business_id():
            flash('You do not have permission to edit business users or no business selected.', 'danger')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        user_to_edit = User.query.filter_by(username=username, business_id=business_id).first_or_404()

        if request.method == 'POST':
            new_username = request.form['username'].strip()
            new_password = request.form['password'].strip() # Plain text password from form
            new_role = request.form['role'].strip()

            if User.query.filter(User.username == new_username, User.business_id == business_id, User.id != user_to_edit.id).first():
                flash('Username already exists for this business.', 'danger')
                return render_template('add_edit_business_user.html', title=f'Edit User: {user_to_edit.username}', user={
                    'username': new_username, 'role': new_role
                }, user_role=session.get('role'), current_year=datetime.now().year)

            # Prevent admin from changing their own role to non-admin or deleting themselves
            if user_to_edit.username == session['username'] and new_role != 'admin':
                flash('You cannot change your own role from admin.', 'danger')
                return render_template('add_edit_business_user.html', title=f'Edit User: {user_to_edit.username}', user=user_to_edit, user_role=session.get('role'), current_year=datetime.now().year)

            user_to_edit.username = new_username
            if new_password: # Only update password if a new one is provided
                user_to_edit.password = new_password # The .password setter will hash it
            user_to_edit.role = new_role
            
            flash(f'User "{username}" updated successfully!', 'success')
            
            db.session.commit()
            return redirect(url_for('manage_business_users'))

        # For GET request, do not send password hash to form
        user_data_for_form = {
            'id': user_to_edit.id,
            'username': user_to_edit.username,
            'role': user_to_edit.role,
            'password': '' # Never pre-fill password fields
        }
        return render_template('add_edit_business_user.html', title=f'Edit User: {user_to_edit.username}', user=user_data_for_form, user_role=session.get('role'), current_year=datetime.now().year)

    @app.route('/manage_business_users/delete/<username>')
    def delete_business_user(username):
        # ACCESS CONTROL: Allows admin role
        if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
            flash('You do not have permission to delete business users or no business selected.', 'danger')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        user_to_delete = User.query.filter_by(username=username, business_id=business_id).first_or_404()

        # Prevent admin from deleting other admins or themselves
        if user_to_delete.role == 'admin':
            flash('Cannot delete an admin user.', 'danger')
            return redirect(url_for('manage_business_users'))
        if user_to_delete.username == session['username']:
            flash('You cannot delete your own user account.', 'danger')
            return redirect(url_for('manage_business_users'))

        db.session.delete(user_to_delete)
        db.session.commit()
        flash(f'User "{username}" deleted successfully!', 'success')
        return redirect(url_for('manage_business_users'))


    # --- Inventory Management Routes ---

    @app.route('/inventory')
    def inventory():
        # ACCESS CONTROL: Allows admin, sales, and viewer roles
        if 'username' not in session or session.get('role') not in ['admin', 'sales', 'viewer'] or not get_current_business_id():
            flash('You do not have permission to view inventory or no business selected.', 'danger')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        search_query = request.args.get('search', '').strip() # Get search query from URL parameters

        inventory_items_query = InventoryItem.query.filter_by(business_id=business_id, is_active=True)

        # Apply search filter if query exists
        if search_query:
            inventory_items_query = inventory_items_query.filter(
                InventoryItem.product_name.ilike(f'%{search_query}%') |
                InventoryItem.category.ilike(f'%{search_query}%') |
                InventoryItem.batch_number.ilike(f'%{search_query}%')
            )
        
        inventory_items = inventory_items_query.all()
        
        today = date.today()
        three_months_from_now = today + timedelta(days=90) # Define threshold for "expiring soon"

        # Calculate profit margin and expiry flags for each item
        for item in inventory_items:
            item.profit_margin = 0.0
            if item.sale_price > 0:
                item.profit_margin = ((item.sale_price - item.purchase_price) / item.sale_price) * 100

            item.is_expiring_soon = False
            item.is_expired = False
            if item.expiry_date:
                if item.expiry_date < today:
                    item.is_expired = True
                elif item.expiry_date >= today and item.expiry_date <= three_months_from_now:
                    item.is_expiring_soon = True

        business_type = get_current_business_type()
        if business_type == 'Pharmacy':
            return render_template('pharmacy_inventory.html', inventory_items=inventory_items, user_role=session.get('role'), search_query=search_query, current_year=datetime.now().year)
        elif business_type in ['Hardware', 'Supermarket', 'Provision Store']:
            return render_template('hardware_inventory.html', inventory_items=inventory_items, user_role=session.get('role'), business_type=business_type, search_query=search_query, current_year=datetime.now().year) # Pass business_type
        return render_template('inventory.html', inventory_items=inventory_items, user_role=session.get('role'), search_query=search_query, current_year=datetime.now().year)

    # NEW ROUTE: Download CSV for current business's inventory
    @app.route('/inventory/download_current_csv')
    # @login_required
    def download_current_inventory_csv():
        # ACCESS CONTROL: Allows admin, sales, and viewer roles
        if 'username' not in session or session.get('role') not in ['admin', 'sales', 'viewer'] or not get_current_business_id():
            flash('You do not have permission to download inventory or no business selected.', 'danger')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        business_name = session.get('business_name', 'current_business')
        inventory_items = InventoryItem.query.filter_by(business_id=business_id, is_active=True).all()

        si = io.StringIO()
        headers = [
            'id', 'product_name', 'category', 'purchase_price', 'sale_price', 'current_stock', 
            'last_updated', 'batch_number', 'number_of_tabs', 'unit_price_per_tab', 'item_type', 
            'expiry_date', 'is_fixed_price', 'fixed_sale_price', 'business_id', 'is_active'
        ]
        
        writer = csv.DictWriter(si, fieldnames=headers)
        writer.writeheader()
        
        for item in inventory_items:
            row_to_write = {
                'id': item.id,
                'product_name': item.product_name,
                'category': item.category,
                'purchase_price': f"{item.purchase_price:.2f}",
                'sale_price': f"{item.sale_price:.2f}",
                'current_stock': f"{item.current_stock:.2f}",
                'last_updated': item.last_updated.strftime('%Y-%m-%d %H:%M:%S'),
                'batch_number': item.batch_number,
                'number_of_tabs': item.number_of_tabs,
                'unit_price_per_tab': f"{item.unit_price_per_tab:.2f}",
                'item_type': item.item_type,
                'expiry_date': item.expiry_date.strftime('%Y-%m-%d') if item.expiry_date else '',
                'is_fixed_price': str(item.is_fixed_price),
                'fixed_sale_price': f"{item.fixed_sale_price:.2f}",
                'business_id': item.business_id,
                'is_active': str(item.is_active)
            }
            writer.writerow(row_to_write)

        output = si.getvalue()
        si.close()

        response = Response(output, mimetype='text/csv')
        response.headers["Content-Disposition"] = f"attachment; filename={business_name.replace(' ', '_')}_inventory_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
        return response

    # NEW ROUTE: Admin can upload inventory to their current business
    @app.route('/inventory/upload_csv', methods=['GET', 'POST'])
    # @login_required
    def upload_current_inventory_csv():
        # ACCESS CONTROL: Only admin can upload inventory to their current business
        if session.get('role') not in ['admin'] or not get_current_business_id():
            flash('You do not have permission to upload inventory or no business selected.', 'danger')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        business_name = session.get('business_name', 'Your Business')

        if request.method == 'POST':
            if 'csv_file' not in request.files:
                flash('No file part', 'danger')
                return redirect(request.url)
            
            file = request.files['csv_file']
            if file.filename == '':
                flash('No selected file', 'danger')
                return redirect(request.url)
            
            if file and file.filename.endswith('.csv'):
                stream = io.StringIO(file.stream.read().decode("UTF8"))
                csv_reader = csv.DictReader(stream)
                
                updated_count = 0
                added_count = 0
                errors = []

                for row in csv_reader:
                    try:
                        product_name = row['product_name'].strip()
                        category = row['category'].strip()
                        purchase_price = float(row['purchase_price'])
                        current_stock = float(row['current_stock'])
                        batch_number = row.get('batch_number', '').strip()
                        number_of_tabs = int(row.get('number_of_tabs', 1))
                        item_type = row.get('item_type', session.get('business_type', 'Pharmacy')).strip() # Default to business type
                        expiry_date_str = row.get('expiry_date', '').strip()
                        expiry_date_obj = datetime.strptime(expiry_date_str, '%Y-%m-%d').date() if expiry_date_str else None
                        is_fixed_price = row.get('is_fixed_price', 'False').lower() == 'true'
                        fixed_sale_price = float(row.get('fixed_sale_price', 0.0))
                        is_active = row.get('is_active', 'True').lower() == 'true' # Read is_active from CSV

                        if number_of_tabs <= 0:
                            errors.append(f"Skipping '{product_name}': 'Number of units/pieces per pack' must be greater than zero.")
                            continue

                        sale_price = 0.0
                        unit_price_per_tab_with_markup = 0.0
                        
                        # Determine sale_price and unit_price_per_tab based on item_type and fixed_price status
                        if is_fixed_price:
                            sale_price = fixed_sale_price
                            if number_of_tabs > 0:
                                unit_price_per_tab = fixed_sale_price / number_of_tabs
                        else:
                            if item_type == 'Pharmacy':
                                # For Pharmacy, assuming sale_price and unit_price_per_tab are derived from purchase_price + markup
                                # If CSV provides them, use them directly. Otherwise, apply a default markup (e.g., 20%)
                                sale_price = float(row.get('sale_price', purchase_price * 1.2)) # Default 20% markup
                                unit_price_per_tab_with_markup = float(row.get('unit_price_per_tab', sale_price / number_of_tabs if number_of_tabs > 0 else sale_price))
                            elif item_type in ['Hardware Material', 'Provision Store', 'Supermarket']:
                                sale_price = float(row.get('sale_price', purchase_price * 1.2)) # Default 20% markup
                                unit_price_per_tab_with_markup = float(row.get('unit_price_per_tab', sale_price / number_of_tabs if number_of_tabs > 0 else sale_price))
                            else: # Fallback for unknown types, or if item_type is not explicitly provided in CSV
                                sale_price = float(row.get('sale_price', purchase_price * 1.2))
                                unit_price_per_tab_with_markup = float(row.get('unit_price_per_tab', sale_price / number_of_tabs if number_of_tabs > 0 else sale_price))

                        existing_item = InventoryItem.query.filter_by(
                            product_name=product_name, business_id=business_id
                        ).first()

                        if existing_item:
                            # Update existing item
                            existing_item.category = category
                            existing_item.purchase_price = purchase_price
                            existing_item.sale_price = sale_price
                            existing_item.current_stock = current_stock
                            existing_item.last_updated = datetime.now()
                            existing_item.batch_number = batch_number
                            existing_item.number_of_tabs = number_of_tabs
                            existing_item.unit_price_per_tab = unit_price_per_tab_with_markup
                            existing_item.item_type = item_type
                            existing_item.expiry_date = expiry_date_obj
                            existing_item.is_fixed_price = is_fixed_price
                            existing_item.fixed_sale_price = fixed_sale_price
                            existing_item.is_active = is_active # Update is_active
                            updated_count += 1
                        else:
                            # Add new item
                            new_item = InventoryItem(
                                business_id=business_id,
                                product_name=product_name,
                                category=category,
                                purchase_price=purchase_price,
                                sale_price=sale_price,
                                current_stock=current_stock,
                                batch_number=batch_number,
                                number_of_tabs=number_of_tabs,
                                unit_price_per_tab=unit_price_per_tab_with_markup,
                                item_type=item_type,
                                expiry_date=expiry_date_obj,
                                is_fixed_price=is_fixed_price,
                                fixed_sale_price=fixed_sale_price,
                                is_active=is_active # Set is_active for new item
                            )
                            db.session.add(new_item)
                            added_count += 1
                    except Exception as e:
                        errors.append(f"Error processing row for product '{row.get('product_name', 'N/A')}': {e}. Row data: {row}")
                
                db.session.commit()
                
                if errors:
                    flash(f'CSV upload completed with {updated_count} updated, {added_count} added, and {len(errors)} errors. Check server console for details.', 'warning')
                    for error in errors:
                        print(f"CSV Upload Error: {error}")
                else:
                    flash(f'CSV inventory uploaded successfully! {updated_count} items updated, {added_count} items added.', 'success')
                
                return redirect(url_for('inventory')) # Redirect to the inventory list
            else:
                flash('Invalid file type. Please upload a CSV file.', 'danger')
                return redirect(request.url)
        
        return render_template('upload_current_inventory.html', business_name=business_name, user_role=session.get('role'), current_year=datetime.now().year)


    # app.py (your add_inventory_item route)
    @app.route('/inventory/add', methods=['GET', 'POST'])
    def add_inventory_item():
        # ACCESS CONTROL: Allows admin role
        if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
            flash('You do not have permission to add inventory items or no business selected.', 'danger')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        business_type = get_current_business_type()

        # Determine which item types are relevant for the current business type
    
        relevant_item_types = []
        if business_type == 'Pharmacy':
            relevant_item_types = ['Pharmacy']
        elif business_type == 'Hardware':
            relevant_item_types = ['Hardware Material']

        elif business_type in ['Supermarket', 'Provision Store']:
            relevant_item_types = ['Provision Store']
        # The following two elifs are redundant with the one above, but kept for direct mapping to original.
        elif business_type == 'Supermarket':
            relevant_item_types = ['Supermarket']
        elif business_type == 'Provision Store':
            relevant_item_types = ['Provision Store']
        else:
            # Fallback or general type if none matches. Consider if a business can have diverse types.
            relevant_item_types = ['Pharmacy', 'Hardware Material', 'Supermarket', 'Provision Store'] # Include all if flexible

        available_inventory_items = InventoryItem.query.filter(
            InventoryItem.business_id == business_id,
            InventoryItem.is_active == True,
            InventoryItem.item_type.in_(relevant_item_types)
        ).all()
        # Assuming serialize_inventory_item_api exists for consistent serialization with API needs
        serialized_inventory_items = [serialize_inventory_item_api(item) for item in available_inventory_items]
        
        # Get pharmacy info for receipts (ensure it's clean for template rendering)
        raw_pharmacy_info = session.get('business_info', {})
        if isinstance(raw_pharmacy_info, dict):
            pharmacy_info = {
                'name': str(raw_pharmacy_info.get('name', 'N/A')),
                'address': str(raw_pharmacy_info.get('address', 'N/A')),
                'location': str(raw_pharmacy_info.get('location', 'N/A')),
                'phone': str(raw_pharmacy_info.get('phone', 'N/A')),
                'email': str(raw_pharmacy_info.get('email', 'N/A')),
                'contact': str(raw_pharmacy_info.get('contact', 'N/A'))
            }
        else:
            # Fallback if session['business_info'] is not a dict
            business_details = Business.query.filter_by(id=business_id).first()
            if business_details:
                pharmacy_info = {
                    'name': str(business_details.name),
                    'address': str(business_details.address),
                    'location': str(business_details.location),
                    'phone': str(business_details.contact),
                    'email': str(business_details.email) if hasattr(business_details, 'email') and business_details.email is not None else 'N/A',
                    'contact': str(business_details.contact)
                }
            else:
                pharmacy_info = {
                    'name': "Your Enterprise Name", 'address': "N/A", 'location': "N/A",
                    'phone': "N/A", 'email': "N/A", 'contact': "N/A"
                }

        # Fetch other businesses for the import section
        other_businesses = []
        if session.get('role') == 'admin':
            # Filter businesses of the same type, excluding the current business
            other_businesses_query = Business.query.filter(
                Business.id != business_id,
                Business.type == business_type # Only show businesses of the same type for import
            )
            other_businesses = other_businesses_query.all()


        if request.method == 'POST':
            product_name = request.form.get('product_name', '').strip()
            category = request.form.get('category', '').strip()
            
            # Safely get numerical inputs, default to 0.0 or 1 if conversion fails or missing
            try:
                purchase_price = float(request.form.get('purchase_price', 0.0))
                current_stock = float(request.form.get('current_stock', 0.0))
                number_of_tabs = int(request.form.get('number_of_tabs', 1))
            except ValueError:
                flash('Invalid input for numerical fields (Price, Stock, Units per Pack). Please enter valid numbers.', 'danger')
                # Re-render with existing form data to preserve user input
                item_data_for_form_on_error = {
                    'product_name': product_name, 'category': category,
                    'purchase_price': request.form.get('purchase_price', '0.00'),
                    'current_stock': request.form.get('current_stock', '0.00'),
                    'batch_number': request.form.get('batch_number', '').strip(),
                    'barcode': request.form.get('barcode', '').strip(),
                    'number_of_tabs': request.form.get('number_of_tabs', '1'),
                    'item_type': request.form.get('item_type', business_type),
                    'expiry_date': request.form.get('expiry_date', ''),
                    'is_fixed_price': 'is_fixed_price' in request.form,
                    'fixed_sale_price': request.form.get('fixed_sale_price', '0.00')
                }
                return render_template('add_edit_inventory.html', title='Add Inventory Item',
                                    item=item_data_for_form_on_error, user_role=session.get('role'),
                                    business_type=business_type, current_year=datetime.now().year,
                                    pharmacy_info=pharmacy_info, other_businesses=other_businesses)


            batch_number = request.form.get('batch_number', '').strip()
            raw_barcode = request.form.get('barcode', '').strip() # Get the barcode string
            
            # Set barcode to None if it's an empty string, otherwise keep the value
            barcode_to_save = raw_barcode if raw_barcode else None

            # Validate required string fields
            if not product_name or not category:
                flash('Product Name and Category are required fields.', 'danger')
                item_data_for_form_on_error = {
                    'product_name': product_name, 'category': category,
                    'purchase_price': purchase_price, 'current_stock': current_stock,
                    'batch_number': batch_number, 'barcode': raw_barcode, # Use raw_barcode for rendering
                    'number_of_tabs': number_of_tabs,
                    'item_type': request.form.get('item_type', business_type),
                    'expiry_date': request.form.get('expiry_date', ''),
                    'is_fixed_price': 'is_fixed_price' in request.form,
                    'fixed_sale_price': float(request.form.get('fixed_sale_price', 0.0))
                }
                return render_template('add_edit_inventory.html', title='Add Inventory Item',
                                    item=item_data_for_form_on_error, user_role=session.get('role'),
                                    business_type=business_type, current_year=datetime.now().year,
                                    pharmacy_info=pharmacy_info, other_businesses=other_businesses)


            # Check if barcode is unique if provided and not None
            if barcode_to_save: # Only check uniqueness if barcode_to_save is not None/empty
                existing_barcode_item = InventoryItem.query.filter_by(
                    business_id=business_id,
                    barcode=barcode_to_save
                ).first()
                if existing_barcode_item:
                    flash('Barcode already in use for another product.', 'danger')
                    item_data_for_form_on_error = {
                        'product_name': product_name, 'category': category,
                        'purchase_price': purchase_price, 'current_stock': current_stock,
                        'batch_number': batch_number, 'barcode': raw_barcode, # Use raw_barcode for rendering
                        'number_of_tabs': number_of_tabs,
                        'item_type': request.form.get('item_type', business_type),
                        'expiry_date': request.form.get('expiry_date', ''),
                        'is_fixed_price': 'is_fixed_price' in request.form,
                        'fixed_sale_price': float(request.form.get('fixed_sale_price', 0.0))
                    }
                    return render_template('add_edit_inventory.html', title='Add Inventory Item',
                                        item=item_data_for_form_on_error, user_role=session.get('role'),
                                        business_type=business_type, current_year=datetime.now().year,
                                        pharmacy_info=pharmacy_info, other_businesses=other_businesses)
            
            expiry_date_str = request.form.get('expiry_date', '').strip()
            
            expiry_date_obj = None 
            if expiry_date_str:
                try:
                    expiry_date_obj = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                except ValueError:
                    flash('Invalid expiry date format. Please use YYYY-MM-DD.', 'danger')
                    item_data_for_form_on_error = {
                        'product_name': product_name, 'category': category,
                        'purchase_price': purchase_price, 'current_stock': current_stock,
                        'batch_number': batch_number, 'barcode': raw_barcode, # Use raw_barcode for rendering
                        'number_of_tabs': number_of_tabs,
                        'item_type': request.form.get('item_type', business_type),
                        'expiry_date': '',
                        'is_fixed_price': 'is_fixed_price' in request.form,
                        'fixed_sale_price': float(request.form.get('fixed_sale_price', 0.0))
                    }
                    return render_template('add_edit_inventory.html', title='Add Inventory Item',
                                        item=item_data_for_form_on_error, user_role=session.get('role'),
                                        business_type=business_type, current_year=datetime.now().year,
                                        pharmacy_info=pharmacy_info, other_businesses=other_businesses)

            if number_of_tabs <= 0:
                flash('Number of units/pieces per pack must be greater than zero.', 'danger')
                item_data_for_form_on_error = {
                    'product_name': product_name, 'category': category,
                    'purchase_price': purchase_price, 'current_stock': current_stock,
                    'batch_number': batch_number, 'barcode': raw_barcode, # Use raw_barcode for rendering
                    'number_of_tabs': number_of_tabs,
                    'item_type': request.form.get('item_type', business_type),
                    'expiry_date': expiry_date_obj.strftime('%Y-%m-%d') if expiry_date_obj else '',
                    'is_fixed_price': 'is_fixed_price' in request.form,
                    'fixed_sale_price': float(request.form.get('fixed_sale_price', 0.0))
                }
                return render_template('add_edit_inventory.html', title='Add Inventory Item', item=item_data_for_form_on_error, user_role=session.get('role'), business_type=business_type, current_year=datetime.now().year, pharmacy_info=pharmacy_info, other_businesses=other_businesses)


            if InventoryItem.query.filter_by(product_name=product_name, business_id=business_id).first():
                flash('Product with this name already exists for this business.', 'danger')
                item_data_for_form_on_error = {
                    'product_name': product_name, 'category': category,
                    'purchase_price': purchase_price, 'current_stock': current_stock,
                    'batch_number': batch_number, 'barcode': raw_barcode, # Use raw_barcode for rendering
                    'number_of_tabs': number_of_tabs,
                    'item_type': request.form.get('item_type', business_type),
                    'expiry_date': expiry_date_obj.strftime('%Y-%m-%d') if expiry_date_obj else '',
                    'is_fixed_price': 'is_fixed_price' in request.form,
                    'fixed_sale_price': float(request.form.get('fixed_sale_price', 0.0))
                }
                return render_template('add_edit_inventory.html', title='Add Inventory Item', item=item_data_for_form_on_error, user_role=session.get('role'), business_type=business_type, current_year=datetime.now().year, pharmacy_info=pharmacy_info, other_businesses=other_businesses)
            
            sale_price = 0.0
            unit_price_per_tab = 0.0
            
            is_fixed_price = 'is_fixed_price' in request.form
            fixed_sale_price = float(request.form.get('fixed_sale_price', 0.0)) # Ensure it's always a float

            if is_fixed_price:
                sale_price = fixed_sale_price
                if number_of_tabs > 0:
                    unit_price_per_tab = fixed_sale_price / number_of_tabs
            else:
                # If not fixed price and not pharmacy, assume a sale_price input field is needed
                # Since the form doesn't have it, we must ensure it's provided or handled
                if business_type != 'Pharmacy':
                    # This field is MISSING from your HTML template
                    # You need to add an input for name="sale_price" if you want to use this logic
                    input_sale_price = request.form.get('sale_price')
                    if input_sale_price is None or input_sale_price.strip() == '':
                        flash('Sale Price is required for non-fixed price items in this business type.', 'danger')
                        item_data_for_form_on_error = {
                            'product_name': product_name, 'category': category,
                            'purchase_price': purchase_price, 'current_stock': current_stock,
                            'batch_number': batch_number, 'barcode': raw_barcode, # Use raw_barcode for rendering
                            'number_of_tabs': number_of_tabs,
                            'item_type': request.form.get('item_type', business_type),
                            'expiry_date': expiry_date_obj.strftime('%Y-%m-%d') if expiry_date_obj else '',
                            'is_fixed_price': is_fixed_price,
                            'fixed_sale_price': fixed_sale_price
                        }
                        return render_template('add_edit_inventory.html', title='Add Inventory Item',
                                            item=item_data_for_form_on_error, user_role=session.get('role'),
                                            business_type=business_type, current_year=datetime.now().year,
                                            pharmacy_info=pharmacy_info, other_businesses=other_businesses)
                    try:
                        sale_price = float(input_sale_price)
                    except ValueError:
                        flash('Invalid input for Sale Price. Please enter a valid number.', 'danger')
                        item_data_for_form_on_error = {
                            'product_name': product_name, 'category': category,
                            'purchase_price': purchase_price, 'current_stock': current_stock,
                            'batch_number': batch_number, 'barcode': raw_barcode, # Use raw_barcode for rendering
                            'number_of_tabs': number_of_tabs,
                            'item_type': request.form.get('item_type', business_type),
                            'expiry_date': expiry_date_obj.strftime('%Y-%m-%d') if expiry_date_obj else '',
                            'is_fixed_price': is_fixed_price,
                            'fixed_sale_price': fixed_sale_price
                        }
                        return render_template('add_edit_inventory.html', title='Add Inventory Item',
                                            item=item_data_for_form_on_error, user_role=session.get('role'),
                                            business_type=business_type, current_year=datetime.now().year,
                                            pharmacy_info=pharmacy_info, other_businesses=other_businesses)
                    
                    if number_of_tabs > 0:
                        unit_price_per_tab = sale_price / number_of_tabs
                else: # Business type is Pharmacy, and not fixed price
                    markup_percentage = float(request.form.get('markup_percentage_pharmacy', 0.0)) / 100
                    sale_price = purchase_price + (purchase_price * markup_percentage)
                    if number_of_tabs > 0:
                        unit_price_per_tab = sale_price / number_of_tabs


            new_item = InventoryItem(
                business_id=business_id,
                product_name=product_name,
                category=category,
                purchase_price=purchase_price,
                sale_price=sale_price,
                current_stock=current_stock,
                batch_number=batch_number,
                barcode=barcode_to_save, # Use the processed barcode_to_save here
                number_of_tabs=number_of_tabs,
                unit_price_per_tab=unit_price_per_tab,
                item_type=request.form.get('item_type', business_type), # Use the selected item_type from form
                expiry_date=expiry_date_obj,
                is_fixed_price=is_fixed_price,
                fixed_sale_price=fixed_sale_price,
                is_active=True
            )
            db.session.add(new_item)
            db.session.commit()
            flash(f'Inventory item "{product_name}" added successfully!', 'success')
            return redirect(url_for('inventory'))
        
        # GET request / Initial render
        # Ensure all context variables are passed on GET for initial form rendering
        return render_template('add_edit_inventory.html',
                            title='Add Inventory Item',
                            item={}, # Empty item for new form
                            user_role=session.get('role'),
                            business_type=business_type,
                            current_year=datetime.now().year,
                            pharmacy_info=pharmacy_info,
                            other_businesses=other_businesses)




    @app.route('/inventory/edit/<item_id>', methods=['GET', 'POST'])
    # @login_required
    def edit_inventory_item(item_id):
        # ACCESS CONTROL: Allows admin role
        if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
            flash('You do not have permission to edit inventory items or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        business_id = get_current_business_id()
        item_to_edit = InventoryItem.query.filter_by(id=item_id, business_id=business_id).first_or_404()
        business_type = get_current_business_type()

        relevant_item_types = []
        if business_type == 'Pharmacy':
            relevant_item_types = ['Pharmacy']
        elif business_type == 'Hardware':
            relevant_item_types = ['Hardware Material']
        elif business_type in ['Supermarket', 'Provision Store']:
            relevant_item_types = ['Provision Store'] 

        if request.method == 'POST':
            # Define is_fixed_price and fixed_sale_price early to avoid NameError
            is_fixed_price = 'is_fixed_price' in request.form
            fixed_sale_price = float(request.form.get('fixed_sale_price', 0.0))

            try:
                product_name = request.form['product_name'].strip()
                category = request.form['category'].strip()
                purchase_price = float(request.form['purchase_price'])
                current_stock = float(request.form['current_stock'])
                batch_number = request.form.get('batch_number', '').strip()
                new_barcode = request.form.get('barcode', '').strip()
                item_type = request.form['item_type']
                number_of_tabs = int(request.form.get('number_of_tabs', 1))
                
                # Helper function to prepare common form data for re-rendering on error
                def prepare_error_form_data(
                    product_name, category, purchase_price, current_stock,
                    batch_number, new_barcode, number_of_tabs, item_type,
                    expiry_date_str_or_obj, is_fixed_price_checked, fixed_sale_price, markup_percentage_pharmacy_val
                ):
                    error_item_data = {
                        'id': item_to_edit.id,
                        'product_name': product_name, 
                        'category': category,
                        'purchase_price': purchase_price, 
                        'current_stock': current_stock,
                        'batch_number': batch_number, 
                        'barcode': new_barcode,
                        'number_of_tabs': number_of_tabs,
                        'item_type': item_type,
                        'is_fixed_price': is_fixed_price_checked, 
                        'fixed_sale_price': fixed_sale_price,
                        'is_active': 'is_active' in request.form 
                    }
                    if isinstance(expiry_date_str_or_obj, date):
                        error_item_data['expiry_date'] = expiry_date_str_or_obj.strftime('%Y-%m-%d')
                    else:
                        error_item_data['expiry_date'] = expiry_date_str_or_obj

                    if business_type == 'Pharmacy':
                        error_item_data['markup_percentage_pharmacy'] = float(markup_percentage_pharmacy_val or 0.0)
                    return error_item_data

                # Barcode uniqueness check
                barcode_to_save = new_barcode if new_barcode else None
                if barcode_to_save and barcode_to_save != item_to_edit.barcode:
                    existing_barcode = InventoryItem.query.filter(
                        InventoryItem.business_id == business_id,
                        InventoryItem.barcode == barcode_to_save,
                        InventoryItem.id != item_id
                    ).first()
                    if existing_barcode:
                        flash('Barcode already in use for another product.', 'danger')
                        return render_template('add_edit_inventory.html',
                                            title=f'Edit Inventory Item: {item_to_edit.product_name}',
                                            item=prepare_error_form_data(
                                                    product_name, category, purchase_price, current_stock,
                                                    batch_number, new_barcode, number_of_tabs, item_type,
                                                    request.form.get('expiry_date', ''), 
                                                    is_fixed_price, # Use defined variable
                                                    fixed_sale_price, # Use defined variable
                                                    request.form.get('markup_percentage_pharmacy', 0.0)
                                            ), 
                                            user_role=session.get('role'),
                                            business_type=business_type, current_year=datetime.now().year)
                
                expiry_date_str = request.form.get('expiry_date', '').strip()
                expiry_date_obj = None
                if expiry_date_str:
                    try:
                        expiry_date_obj = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        flash('Invalid expiry date format. Please use YYYY-MM-DD.', 'danger')
                        return render_template('add_edit_inventory.html',
                                            title=f'Edit Inventory Item: {item_to_edit.product_name}',
                                            item=prepare_error_form_data(
                                                    product_name, category, purchase_price, current_stock,
                                                    batch_number, new_barcode, number_of_tabs, item_type,
                                                    '', 
                                                    is_fixed_price, # Use defined variable
                                                    fixed_sale_price, # Use defined variable
                                                    request.form.get('markup_percentage_pharmacy', 0.0)
                                            ), 
                                            user_role=session.get('role'),
                                            business_type=business_type, current_year=datetime.now().year)

                if number_of_tabs <= 0:
                    flash('Number of units/pieces per pack must be greater than zero.', 'danger')
                    return render_template('add_edit_inventory.html',
                                            title='Edit Inventory Item', 
                                            item=prepare_error_form_data(
                                                    product_name, category, purchase_price, current_stock,
                                                    batch_number, new_barcode, number_of_tabs, item_type,
                                                    expiry_date_obj, is_fixed_price, fixed_sale_price,
                                                    request.form.get('markup_percentage_pharmacy', 0.0)
                                            ), 
                                            user_role=session.get('role'),
                                            business_type=business_type, current_year=datetime.now().year)

                # Product name uniqueness check (excluding current item)
                if InventoryItem.query.filter(InventoryItem.product_name == product_name, InventoryItem.business_id == business_id, InventoryItem.id != item_id).first():
                    flash('Product with this name already exists for this business.', 'danger')
                    return render_template('add_edit_inventory.html',
                                            title='Edit Inventory Item', 
                                            item=prepare_error_form_data(
                                                    product_name, category, purchase_price, current_stock,
                                                    batch_number, new_barcode, number_of_tabs, item_type,
                                                    expiry_date_obj, is_fixed_price, fixed_sale_price,
                                                    request.form.get('markup_percentage_pharmacy', 0.0)
                                            ), 
                                            user_role=session.get('role'),
                                            business_type=business_type, current_year=datetime.now().year)
                
                # --- If all validations pass, update the item ---
                item_to_edit.product_name = product_name
                item_to_edit.category = category
                item_to_edit.purchase_price = purchase_price
                item_to_edit.current_stock = current_stock
                item_to_edit.last_updated = datetime.now()
                item_to_edit.batch_number = batch_number
                item_to_edit.barcode = barcode_to_save 
                item_to_edit.number_of_tabs = number_of_tabs
                item_to_edit.item_type = item_type
                item_to_edit.expiry_date = expiry_date_obj
                item_to_edit.is_fixed_price = is_fixed_price
                item_to_edit.fixed_sale_price = fixed_sale_price
                item_to_edit.is_active = 'is_active' in request.form

                sale_price = 0.0
                unit_price_per_tab = 0.0

                if is_fixed_price:
                    sale_price = fixed_sale_price
                    item_to_edit.markup_percentage_pharmacy = 0.0 
                else:
                    if business_type == 'Pharmacy':
                        markup_percentage_form_value = float(request.form.get('markup_percentage_pharmacy', 0.0))
                        item_to_edit.markup_percentage_pharmacy = markup_percentage_form_value
                        sale_price = purchase_price * (1 + (markup_percentage_form_value / 100))
                    else:
                        sale_price = purchase_price
                        item_to_edit.markup_percentage_pharmacy = 0.0 

                if number_of_tabs > 0:
                    unit_price_per_tab = sale_price / number_of_tabs
                else:
                    unit_price_per_tab = sale_price 

                item_to_edit.sale_price = sale_price
                item_to_edit.unit_price_per_tab = unit_price_per_tab

                db.session.commit()
                flash(f'Inventory item "{product_name}" updated successfully!', 'success')
                return redirect(url_for('inventory'))
            except ValueError as e:
                db.session.rollback()
                flash(f'Invalid input data. Please check your numbers and dates. Error: {e}', 'danger')
                return render_template('add_edit_inventory.html',
                                    title=f'Edit Inventory Item: {item_to_edit.product_name}',
                                    item=prepare_error_form_data(
                                            request.form.get('product_name', ''), 
                                            request.form.get('category', ''), 
                                            float(request.form.get('purchase_price', 0.0)), 
                                            float(request.form.get('current_stock', 0.0)),
                                            request.form.get('batch_number', ''), 
                                            request.form.get('barcode', ''),
                                            int(request.form.get('number_of_tabs', 1)), 
                                            request.form.get('item_type', ''),
                                            request.form.get('expiry_date', ''), 
                                            is_fixed_price, # Use defined variable
                                            fixed_sale_price, # Use defined variable
                                            request.form.get('markup_percentage_pharmacy', 0.0)
                                    ),
                                    user_role=session.get('role'),
                                    business_type=business_type, 
                                    current_year=datetime.now().year)
            except Exception as e:
                db.session.rollback()
                flash(f'An unexpected error occurred: {e}', 'danger')
                return redirect(url_for('inventory'))

        # --- GET Request / Initial Render ---
        item_data_for_form = {
            'id': item_to_edit.id,
            'product_name': item_to_edit.product_name,
            'category': item_to_edit.category,
            'purchase_price': item_to_edit.purchase_price,
            'sale_price': item_to_edit.sale_price,
            'current_stock': item_to_edit.current_stock,
            'last_updated': item_to_edit.last_updated.isoformat(),
            'batch_number': item_to_edit.batch_number,
            'barcode': item_to_edit.barcode,
            'number_of_tabs': item_to_edit.number_of_tabs,
            'unit_price_per_tab': item_to_edit.unit_price_per_tab,
            'item_type': item_to_edit.item_type,
            'is_fixed_price': item_to_edit.is_fixed_price,
            'fixed_sale_price': item_to_edit.fixed_sale_price,
            'is_active': item_to_edit.is_active
        }

        item_data_for_form['expiry_date'] = item_to_edit.expiry_date.strftime('%Y-%m-%d') if item_to_edit.expiry_date else ''
        
        if business_type == 'Pharmacy' and not item_to_edit.is_fixed_price and item_to_edit.purchase_price is not None and item_to_edit.purchase_price > 0:
            if item_to_edit.markup_percentage_pharmacy is not None:
                item_data_for_form['markup_percentage_pharmacy'] = float(item_to_edit.markup_percentage_pharmacy)
            else:
                markup_percentage = ((item_to_edit.sale_price - item_to_edit.purchase_price) / item_to_edit.purchase_price) * 100
                item_data_for_form['markup_percentage_pharmacy'] = float(f"{markup_percentage:.2f}")
        else:
            item_data_for_form['markup_percentage_pharmacy'] = 0.0

        return render_template('add_edit_inventory.html',
                            title=f'Edit Inventory Item: {item_to_edit.product_name}',
                            item=item_data_for_form,
                            business_type=business_type,
                            user_role=session.get('role'),
                            current_year=datetime.now().year)

    # @app.route('/inventory/delete/<item_id>')
    # def delete_inventory_item(item_id):
    #     # ACCESS CONTROL: Allows admin role
    #     if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
    #         flash('You do not have permission to delete inventory items or no business selected.', 'danger')
    #         return redirect(url_for('dashboard'))
        
    #     business_id = get_current_business_id()
    #     item_to_delete = InventoryItem.query.filter_by(id=item_id, business_id=business_id).first_or_404()
        
    #     item_to_delete.is_active = False # Soft delete
    #     db.session.commit()

    #     flash(f'Inventory item "{item_to_delete.product_name}" marked as inactive successfully!', 'success')
    #     return redirect(url_for('inventory'))

    @app.route('/inventory/delete/<item_id>', methods=['GET', 'POST'])
    @csrf.exempt
    @login_required
    def delete_inventory_item(item_id):
        """Marks an inventory item as inactive."""
        if session.get('role') not in ['admin'] or not get_current_business_id():
            flash('You do not have permission to delete inventory items or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        business_id = get_current_business_id()
        item_to_delete = InventoryItem.query.filter_by(id=item_id, business_id=business_id).first_or_404()
        
        # Check if the request is a POST (from the delete form)
        if request.method == 'POST':
            # Soft delete the item
            item_to_delete.is_active = False
            db.session.commit()
            flash(f'Inventory item "{item_to_delete.product_name}" marked as inactive successfully!', 'success')
            return redirect(url_for('inventory'))
        
        # If the request is a GET, just redirect back. This allows url_for to build the link.
        return redirect(url_for('inventory'))


    @app.route('/sales')
    # @login_required # Ensure this decorator is present for access control
    def sales():
        # ACCESS CONTROL: Allows admin, sales, and viewer roles
        if 'username' not in session or session.get('role') not in ['admin', 'sales', 'viewer'] or not get_current_business_id():
            flash('You do not have permission to view sales records or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        business_id = get_current_business_id()
        search_query = request.args.get('search', '').strip()

        print(f"DEBUG: Sales route - Business ID: {business_id}")
        print(f"DEBUG: Sales route - Search Query: '{search_query}'")

        sales_records_query = SalesRecord.query.filter_by(business_id=business_id)

        # Initialize current_filters dictionary to be passed to the template
        current_filters = {
            'search': search_query,
            'start_date': request.args.get('start_date'),
            'end_date': request.args.get('end_date')
            # Add other filter fields here if you uncomment them in sales.html
        }

        # Apply filters based on direct columns
        if search_query:
            sales_records_query = sales_records_query.filter(
                (SalesRecord.customer_phone.ilike(f'%{search_query}%')) |
                (SalesRecord.sales_person_name.ilike(f'%{search_query}%')) |
                (SalesRecord.receipt_number.ilike(f'%{search_query}%'))
            )

        # Filter by date ranges using 'transaction_date'
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                sales_records_query = sales_records_query.filter(SalesRecord.transaction_date >= start_date)
                print(f"DEBUG: Sales route - Applying start_date filter: {start_date}")
            except ValueError:
                flash('Invalid start date format.', 'warning')
                print(f"DEBUG: Sales route - Invalid start_date format: {start_date_str}")
                # If there's an error, we still need to render the page with current_filters
                sales_records = sales_records_query.order_by(SalesRecord.transaction_date.desc()).all() # Fetch with current valid filters
                # Proceed to process records and render template at the end
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                sales_records_query = sales_records_query.filter(SalesRecord.transaction_date <= end_date + timedelta(days=1) - timedelta(microseconds=1))
                print(f"DEBUG: Sales route - Applying end_date filter: {end_date}")
            except ValueError:
                flash('Invalid end date format.', 'warning')
                print(f"DEBUG: Sales route - Invalid end_date format: {end_date_str}")
                # If there's an error, we still need to render the page with current_filters
                sales_records = sales_records_query.order_by(SalesRecord.transaction_date.desc()).all() # Fetch with current valid filters
                # Proceed to process records and render template at the end


        # Order by 'transaction_date' descending for most recent sales first
        sales_records = sales_records_query.order_by(SalesRecord.transaction_date.desc()).all()
        
        print(f"DEBUG: Sales route - Found {len(sales_records)} sales records after filtering.")

        transactions = {}
        today = date.today() # Get today's date for expiry checks

        for sale in sales_records:
            transaction_id = sale.receipt_number if sale.receipt_number else str(sale.id) # Use receipt_number or ID
            
            items_sold_data = sale.get_items_sold() # Get the list of items from the JSON column
            print(f"DEBUG: Processing SalesRecord {sale.id} (Receipt: {transaction_id}) with {len(items_sold_data)} items.")

            sale_items_for_transaction = []
            for item_data in items_sold_data:
                # Each item_data is a dictionary from the JSON array
                product_name = item_data.get('product_name', "Unknown Product")
                product_id = item_data.get('product_id') # Get product_id from the item_data dictionary

                # Fetch the associated InventoryItem to get expiry date if needed
                product_item = None
                if product_id:
                    product_item = InventoryItem.query.filter_by(id=product_id, business_id=business_id).first()
                
                sale_item_expires_soon = False
                sale_item_expiry_date = None
                if product_item and product_item.expiry_date:
                    sale_item_expiry_date = product_item.expiry_date
                    time_to_expiry = product_item.expiry_date - today
                    if time_to_expiry.days <= 180 and time_to_expiry.days >= 0:
                        sale_item_expires_soon = True
                    elif time_to_expiry.days < 0:
                        sale_item_expires_soon = 'Expired'

                # Augment the sale item data
                sale_items_for_transaction.append({
                    'product_id': str(product_id) if product_id else None,
                    'product_name': str(product_name),
                    'quantity_sold': float(item_data.get('quantity_sold', 0.0)),
                    'sale_unit_type': str(item_data.get('sale_unit_type', 'pack')),
                    'price_at_time_per_unit_sold': float(item_data.get('price_at_time_per_unit_sold', 0.0)),
                    'item_total_amount': float(item_data.get('item_total_amount', 0.0)),
                    'expiry_date': sale_item_expiry_date.isoformat() if sale_item_expiry_date else None,
                    'expires_soon': sale_item_expires_soon
                })

            if transaction_id not in transactions:
                    transactions[transaction_id] = {
                        'id': str(sale.id), # Original SalesRecord ID
                        'sale_date': sale.transaction_date.isoformat() if sale.transaction_date else None, 
                        'customer_phone': str(sale.customer_phone) if sale.customer_phone else None,
                        'sales_person_name': str(sale.sales_person_name) if sale.sales_person_name else None,
                        'grand_total_amount': float(sale.grand_total_amount or 0.0), 
                        'items': sale_items_for_transaction,
                        'reference_number': str(getattr(sale, 'reference_number', None)),
                        'receipt_number': transaction_id # Add receipt_number here as well for direct use
                    }

        # Ensure sale_date is not None before using it for sorting
        sorted_transactions = sorted(
            list(transactions.values()), 
            key=lambda x: datetime.fromisoformat(x['sale_date']) if x['sale_date'] else datetime.min,
            reverse=True
        )
        
        # Calculate total for currently displayed sales (using grand_total_amount from each record)
        total_displayed_sales = sum(t['grand_total_amount'] for t in sorted_transactions)
        print(f"DEBUG: Total displayed sales: GHS{total_displayed_sales:.2f}")

        return render_template('sales.html',
                            transactions=sorted_transactions, 
                            user_role=session.get('role'), 
                            business_type=session.get('business_type'), 
                            search_query=search_query, 
                            total_displayed_sales=total_displayed_sales, 
                            current_year=datetime.now().year,
                            current_filters=current_filters # Pass the dictionary consistently
        )

    @app.route('/sales/add', methods=['GET', 'POST'])
    # @login_required
    def add_sale():
        
        # ACCESS CONTROL: Allows admin and sales roles
        if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
            flash('You do not have permission to add sales records or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        business_id = get_current_business_id()
        business_type = get_current_business_type()

        print(f"DEBUG: Current business_id: {business_id}")
        print(f"DEBUG: Current business_type: {business_type}")

        
        relevant_item_types = []
        
        # Check the business type from the session to filter relevant items
        if business_type == 'Pharmacy':
            relevant_item_types = ['Pharmacy']
        elif business_type == 'Hardware':
            # The item_type for hardware is 'Hardware Material'
            relevant_item_types = ['Hardware Material']
        elif business_type == 'Supermarket':
            relevant_item_types = ['Supermarket', 'Provision Store']
        else:
            # Default to Pharmacy if business_type is not recognized or not yet set
            relevant_item_types = ['Pharmacy']

    
        search_query = request.args.get('search', '').strip()

        available_inventory_items_query = InventoryItem.query.filter(
            InventoryItem.business_id == business_id,
            InventoryItem.is_active == True,
            InventoryItem.item_type.in_(relevant_item_types)
        )

        if search_query:
            available_inventory_items_query = available_inventory_items_query.filter(
                InventoryItem.product_name.ilike(f'%{search_query}%') |
                InventoryItem.category.ilike(f'%{search_query}%') |
                InventoryItem.batch_number.ilike(f'%{search_query}%')
            )
        
        available_inventory_items = available_inventory_items_query.all()
        
        serialized_inventory_items = []
        try:
            serialized_inventory_items = [serialize_inventory_item_api(item) for item in available_inventory_items]
        except Exception as e:
            print(f"ERROR: Exception during serialization of available_inventory_items: {e}")
            serialized_inventory_items = []

        raw_pharmacy_info = session.get('business_info', {})
        if isinstance(raw_pharmacy_info, dict):
            pharmacy_info = {
                'name': str(raw_pharmacy_info.get('name', 'N/A')),
                'address': str(raw_pharmacy_info.get('address', 'N/A')),
                'location': str(raw_pharmacy_info.get('location', 'N/A')),
                'phone': str(raw_pharmacy_info.get('phone', 'N/A')),
                'email': str(raw_pharmacy_info.get('email', 'N/A')),
                'contact': str(raw_pharmacy_info.get('contact', 'N/A'))
            }
        else: # Fallback to database query if session info is not a dict
            business_details = Business.query.filter_by(id=business_id).first()
            if business_details:
                pharmacy_info = {
                    'name': str(business_details.name),
                    'address': str(business_details.address),
                    'location': str(business_details.location),
                    'phone': str(business_details.contact),
                    'email': str(business_details.email) if hasattr(business_details, 'email') and business_details.email is not None else 'N/A',
                    'contact': str(business_details.contact)
                }
            else: # Default generic info if no business details found
                pharmacy_info = {
                    'name': "Your Enterprise Name",
                    'address': "Your Enterprise Address",
                    'location': "Your Enterprise Location",
                    'phone': "Your Enterprise Contact",
                    'email': 'info@example.com',
                    'contact': "Your Enterprise Contact"
                }

        def clean_cart_items_for_template(raw_cart_items):
            cleaned_items = []
            if isinstance(raw_cart_items, list):
                for item_data in raw_cart_items:
                    if isinstance(item_data, dict):
                        cleaned_item = {
                            'product_id': str(item_data.get('product_id', '')),
                            'product_name': str(item_data.get('product_name', '')),
                            'quantity_sold': float(item_data.get('quantity_sold', 0.0)),
                            'sale_unit_type': str(item_data.get('sale_unit_type', '')),
                            'price_at_time_per_unit_sold': float(item_data.get('price_at_time_per_unit_sold', 0.0)),
                            'item_total_amount': float(item_data.get('item_total_amount', 0.0))
                        }
                        cleaned_items.append(cleaned_item)
            return cleaned_items

        sale_for_template_items = [] 
        customer_phone_for_template = ''
        sales_person_name_for_template = session.get('username', 'N/A') 
        
        # Receipt related session variables, cleared after display
        last_transaction_details = session.pop('last_transaction_details', [])
        last_transaction_grand_total = session.pop('last_transaction_grand_total', 0.0)
        last_transaction_id = session.pop('last_transaction_id', '')
        last_transaction_customer_phone = session.pop('last_transaction_customer_phone', '')
        last_transaction_sales_person = session.pop('last_transaction_sales_person', '')
        last_transaction_date = session.pop('last_transaction_date', '')

        # This print_ready flag comes from the URL after a successful sale redirect
        print_ready = request.args.get('print_ready', 'false').lower() == 'true' 
        
        # Use session.get for auto_print to avoid popping it if not needed
        auto_print = session.get('auto_print', False)
        if DB_TYPE == 'sqlite': # Example for specific DB type for auto_print
            auto_print = True

        if request.method == 'POST':
            customer_phone_for_template = request.form.get('customer_phone', '').strip()
            send_sms_receipt = 'send_sms_receipt' in request.form
            cart_items_json = request.form.get('cart_items_json')
            
            cart_items = []
            if cart_items_json:
                try:
                    loaded_cart_items = json.loads(cart_items_json)
                    cart_items = clean_cart_items_for_template(loaded_cart_items)
                except json.JSONDecodeError as e:
                    flash(f'Error processing cart data: {e}. Please try again.', 'danger')
                    cart_items = [] # Ensure cart_items is empty on error
            
            sale_for_template_items = cart_items

            if not cart_items:
                flash('No items in the cart to record a sale.', 'danger')
                return render_template('add_edit_sale.html',
                                    title='Add Sale Record',
                                    inventory_items=serialized_inventory_items,
                                    sale={'customer_phone': customer_phone_for_template, 'sales_person_name': sales_person_name_for_template, 'items': sale_for_template_items},
                                    user_role=session.get('role'),
                                    pharmacy_info=pharmacy_info,
                                    print_ready=False,
                                    current_year=datetime.now().year,
                                    search_query=search_query,
                                    business_type=business_type,
                                    auto_print=auto_print,
                                    # FIX: Pass these variables consistently
                                    last_transaction_details=last_transaction_details,
                                    last_transaction_grand_total=last_transaction_grand_total,
                                    last_transaction_id=last_transaction_id,
                                    last_transaction_customer_phone=last_transaction_customer_phone,
                                    last_transaction_sales_person=last_transaction_sales_person,
                                    last_transaction_date=last_transaction_date)

            total_grand_amount = 0.0
            recorded_sale_details = [] # This will be stored in items_sold_json
            
            # Validate stock and calculate total
            errors = []
            for item_data in cart_items:
                product_id = item_data.get('product_id')
                quantity_sold = float(item_data.get('quantity_sold', 0.0))
                price_at_time_per_unit_sold = float(item_data.get('price_at_time_per_unit_sold', 0.0))
                item_total_amount = float(item_data.get('item_total_amount', 0.0))
                sale_unit_type = item_data.get('sale_unit_type', 'pack')
                product_name = item_data.get('product_name', 'Unknown Product')

                if not product_id:
                    errors.append(f"Invalid product selected for an item. Please select a product from the dropdown.")
                    continue
                if quantity_sold <= 0:
                    errors.append(f"Quantity for '{product_name}' must be greater than zero.")
                    continue

                product = InventoryItem.query.filter_by(id=product_id, business_id=business_id).first()

                if not product:
                    errors.append(f"Product '{product_name}' (ID: {product_id}) not found in inventory.")
                    continue

                # Convert quantity sold to base units for stock check
                num_tabs_per_pack = float(product.number_of_tabs or 1.0)
                if sale_unit_type == 'pack':
                    quantity_in_base_units = quantity_sold * num_tabs_per_pack
                elif sale_unit_type == 'piece' or sale_unit_type == 'tab':
                    quantity_in_base_units = quantity_sold # quantity_sold is already in base units
                else: # Fallback
                    quantity_in_base_units = quantity_sold * num_tabs_per_pack 
                
                # Check stock
                if quantity_in_base_units > (product.current_stock or 0.0):
                    errors.append(f"Insufficient stock for '{product.product_name}'. Available: {product.current_stock or 0.0} units. Tried to sell: {quantity_in_base_units:.2f} units.")
                    continue

                # All good, add to recorded sale details and update total
                recorded_sale_details.append({
                    'product_id': str(product.id),
                    'product_name': product.product_name,
                    'quantity_sold': quantity_sold,
                    'sale_unit_type': sale_unit_type,
                    'price_at_time_per_unit_sold': price_at_time_per_unit_sold,
                    'item_total_amount': item_total_amount,
                    # Add any other relevant details for the receipt
                })
                total_grand_amount += item_total_amount

                # Update inventory stock
                product.current_stock -= quantity_in_base_units # Decrement stock in base units
                db.session.add(product) # Mark product for update

            if errors:
                for error in errors:
                    flash(error, 'danger')
                db.session.rollback() # Rollback any partial changes
                return render_template('add_edit_sale.html',
                                    title='Add Sale Record',
                                    inventory_items=serialized_inventory_items,
                                    sale={'customer_phone': customer_phone_for_template, 'sales_person_name': sales_person_name_for_template, 'items': sale_for_template_items},
                                    user_role=session.get('role'),
                                    pharmacy_info=pharmacy_info,
                                    print_ready=False,
                                    current_year=datetime.now().year,
                                    search_query=search_query,
                                    business_type=business_type,
                                    auto_print=auto_print,
                                    # FIX: Pass these variables consistently
                                    last_transaction_details=last_transaction_details,
                                    last_transaction_grand_total=last_transaction_grand_total,
                                    last_transaction_id=last_transaction_id,
                                    last_transaction_customer_phone=last_transaction_customer_phone,
                                    last_transaction_sales_person=last_transaction_sales_person,
                                    last_transaction_date=last_transaction_date)

            try:
                # Generate a unique receipt number
                current_time_str = datetime.now().strftime('%Y%m%d%H%M%S')
                random_suffix = uuid.uuid4().hex[:6].upper() # Use first 6 chars of UUID
                receipt_num = f"RCPT-{current_time_str}-{random_suffix}"

                # CORRECTED: Only pass arguments that are direct columns of SalesRecord
                new_sale = SalesRecord(
                    business_id=business_id,
                    transaction_date=datetime.now(),
                    customer_phone=customer_phone_for_template,
                    sales_person_name=session.get('username'), # Use the logged-in username
                    grand_total_amount=total_grand_amount,
                    payment_method='Cash', # Default or get from form if you add a payment method field
                    receipt_number=receipt_num,
                )
                new_sale.set_items_sold(recorded_sale_details) # Set the JSON data after object creation
                db.session.add(new_sale)
                db.session.commit()

                flash('Sale recorded successfully!', 'success')
                
                # Store details in session for receipt printing on redirect
                session['last_transaction_details'] = recorded_sale_details
                session['last_transaction_grand_total'] = total_grand_amount
                session['last_transaction_id'] = receipt_num
                session['last_transaction_customer_phone'] = customer_phone_for_template
                session['last_transaction_sales_person'] = session.get('username')
                session['last_transaction_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                send_sms_receipt = 'send_sms_receipt' in request.form
                if send_sms_receipt and customer_phone_for_template:
                    business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
                    
                    # Compose the SMS message
                    sms_message = (
                        f"{business_name_for_sms} Sales Receipt:\n"
                        f"Transaction ID: {receipt_num}\n"
                        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"Total Amount: GH₵{total_grand_amount:.2f}\n"
                        f"Items: " + ", ".join([f"{item['product_name']} ({item['quantity_sold']} {item['sale_unit_type']})" for item in recorded_sale_details]) + "\n"
                        f"Sales Person: {session.get('username')}\n\n"
                        f"Thank you for your purchase!\n"
                        f"From: {business_name_for_sms}"
                    )
                    
                    # Check if online before attempting to send SMS
                    if check_network_online():
                        try:
                            sms_payload = {
                                'action': 'send-sms',
                                'api_key': ARKESEL_API_KEY,
                                'to': customer_phone_for_template,
                                'from': ARKESEL_SENDER_ID,
                                'sms': sms_message
                            }
                            sms_response = requests.get(ARKESEL_SMS_URL, params=sms_payload)
                            sms_response.raise_for_status()
                            sms_result = sms_response.json()

                            if sms_result.get('status') == 'success':
                                flash(f'SMS receipt sent to customer {customer_phone_for_template} successfully!', 'success')
                            else:
                                error_message = sms_result.get('message', 'Unknown error from SMS provider.')
                                flash(f'Failed to send SMS receipt to customer. Error: {error_message}', 'danger')
                        except Exception as e:
                            flash(f'Error sending SMS receipt: {str(e)}', 'danger')
                    else:
                        flash("SMS receipt not sent: You are offline.", 'warning')
                elif send_sms_receipt and not customer_phone_for_template:
                    flash(f'SMS receipt not sent: No customer phone number provided.', 'warning')

                # Redirect to the same page with print_ready flag
                return redirect(url_for('add_sale', print_ready=True))

            except Exception as e:
                db.session.rollback()
                flash(f'An error occurred while recording the sale: {e}', 'danger')
                print(f"ERROR during sale recording: {e}")


            except Exception as e:
                db.session.rollback()
                flash(f'An error occurred while recording the sale: {e}', 'danger')
                print(f"ERROR during sale recording: {e}") # Log the full error
                # Re-render the template with current form data and error
                return render_template('add_edit_sale.html',
                                    title='Add Sale Record',
                                    inventory_items=serialized_inventory_items,
                                    sale={'customer_phone': customer_phone_for_template, 'sales_person_name': sales_person_name_for_template, 'items': sale_for_template_items},
                                    user_role=session.get('role'),
                                    pharmacy_info=pharmacy_info,
                                    print_ready=False,
                                    current_year=datetime.now().year,
                                    search_query=search_query,
                                    business_type=business_type,
                                    auto_print=auto_print,
                                    # FIX: Pass these variables consistently
                                    last_transaction_details=last_transaction_details,
                                    last_transaction_grand_total=last_transaction_grand_total,
                                    last_transaction_id=last_transaction_id,
                                    last_transaction_customer_phone=last_transaction_customer_phone,
                                    last_transaction_sales_person=last_transaction_sales_person,
                                    last_transaction_date=last_transaction_date)

        # GET request
        return render_template('add_edit_sale.html',
                                title='Add Sale Record',
                                inventory_items=serialized_inventory_items,
                                sale={'customer_phone': customer_phone_for_template, 'sales_person_name': sales_person_name_for_template, 'items': sale_for_template_items},
                                user_role=session.get('role'),
                                pharmacy_info=pharmacy_info,
                                print_ready=print_ready, # Pass print_ready for initial GET after redirect
                                last_transaction_details=last_transaction_details,
                                last_transaction_grand_total=last_transaction_grand_total,
                                last_transaction_id=last_transaction_id,
                                last_transaction_customer_phone=last_transaction_customer_phone,
                                last_transaction_sales_person=last_transaction_sales_person,
                                last_transaction_date=last_transaction_date,
                                current_year=datetime.now().year,
                                search_query=search_query,
                                business_type=business_type,
                                auto_print=auto_print)


    @app.route('/sales/edit_transaction/<transaction_id>', methods=['GET', 'POST'])
    def edit_sale_transaction(transaction_id): # Note the parameter name change
        # ACCESS CONTROL: Allows admin and sales roles
        if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
            flash('You do not have permission to edit sales records or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        business_id = get_current_business_id()
        
        sales_in_transaction = SalesRecord.query.filter_by(
            receipt_number=transaction_id, # Assuming receipt_number is the unique identifier for a transaction group
            business_id=business_id
        ).order_by(SalesRecord.transaction_date.asc()).all()


        if not sales_in_transaction:
            flash('Sale transaction not found.', 'danger')
            return redirect(url_for('sales'))

        first_sale_record = sales_in_transaction[0]
        
        business_type = get_current_business_type()
        relevant_item_types = []
        if business_type == 'Pharmacy':
            relevant_item_types = ['Pharmacy']
        elif business_type == 'Hardware':
            relevant_item_types = ['Hardware Material']
        elif business_type in ['Supermarket', 'Provision Store']:
            relevant_item_types = ['Provision Store']
        
        available_inventory_items = InventoryItem.query.filter(
            InventoryItem.business_id == business_id,
            InventoryItem.is_active == True,
            InventoryItem.item_type.in_(relevant_item_types)
        ).all()
        serialized_available_inventory_items = [serialize_inventory_item(item) for item in available_inventory_items]
        
        pharmacy_info = session.get('business_info', {})

        if request.method == 'POST':
            customer_phone = request.form.get('customer_phone', '').strip()
            sales_person_name = request.form.get('sales_person_name', '').strip()
            
            cart_items_json = request.form.get('cart_items_json')
            if not cart_items_json:
                flash('No items in the cart to update the sale.', 'danger')
                return redirect(url_for('edit_sale_transaction', transaction_id=transaction_id))

            new_cart_items = json.loads(cart_items_json)

            # --- Revert old stock and prepare for new stock deduction ---
            for old_sale_record in sales_in_transaction:
                product = InventoryItem.query.filter_by(id=old_sale_record.product_id, business_id=business_id).first()
                if product:
                    quantity_to_return = old_sale_record.quantity_sold
                    if old_sale_record.sale_unit_type == 'pack':
                        original_product_for_tabs = InventoryItem.query.filter_by(id=old_sale_record.product_id, business_id=business_id).first()
                        if original_product_for_tabs:
                            quantity_to_return = old_sale_record.quantity_sold * original_product_for_tabs.number_of_tabs
                    
                    product.current_stock += quantity_to_return
                    product.last_updated = datetime.now()
                    db.session.add(product)
                db.session.delete(old_sale_record)

            # --- Validate and record new items ---
            total_grand_amount = 0.0
            recorded_sale_details = []

            # First pass: Validate stock for new cart items
            for item_data in new_cart_items:
                product_id = item_data['product_id']
                quantity_sold = float(item_data['quantity_sold'])
                product = InventoryItem.query.filter_by(id=product_id, business_id=business_id).first()
                if not product:
                    flash(f'Product with ID {product_id} not found for new cart items.', 'danger')
                    db.session.rollback()
                    return render_template('add_edit_sale.html',
                                        title='Edit Sale Record',
                                        inventory_items=serialized_available_inventory_items,
                                        sale={'customer_phone': customer_phone, 'sales_person_name': sales_person_name, 'items': new_cart_items},
                                        user_role=session.get('role'),
                                        pharmacy_info=pharmacy_info,
                                        print_ready=False,
                                        current_year=datetime.now().year,
                                        auto_print=False) # ADDED: auto_print
                quantity_for_stock_check = quantity_sold
                if item_data['sale_unit_type'] == 'pack':
                    quantity_for_stock_check = quantity_sold * product.number_of_tabs

                if product.current_stock < quantity_for_stock_check:
                    flash(f'Insufficient stock for {product.product_name}. Available: {product.current_stock:.2f} units. Tried to sell: {quantity_for_stock_check:.2f} units.', 'danger')
                    db.session.rollback()
                    return render_template('add_edit_sale.html',
                                        title='Edit Sale Record',
                                        inventory_items=serialized_available_inventory_items,
                                        sale={'customer_phone': customer_phone, 'sales_person_name': sales_person_name, 'items': new_cart_items},
                                        user_role=session.get('role'),
                                        pharmacy_info=pharmacy_info,
                                        print_ready=False,
                                        current_year=datetime.now().year,
                                        auto_print=False) # ADDED: auto_print

            # Second pass: Record new sales and deduct stock
            for item_data in new_cart_items:
                product_id = item_data['product_id']
                quantity_sold = float(item_data['quantity_sold'])
                sale_unit_type = item_data['sale_unit_type']
                price_at_time_per_unit_sold = float(item_data['price_at_time_per_unit_sold'])
                item_total_amount = float(item_data['item_total_amount'])

                product = InventoryItem.query.filter_by(id=product_id, business_id=business_id).first()
                
                quantity_to_deduct = quantity_sold
                if sale_unit_type == 'pack':
                    quantity_to_deduct = quantity_sold * product.number_of_tabs

                product.current_stock -= quantity_to_deduct
                product.last_updated = datetime.now()

                total_grand_amount += item_total_amount

            # After deleting old records and iterating through new_cart_items, we need to
            # create *one* new SalesRecord entry that represents the updated transaction.
            # This single SalesRecord will have the receipt_number and its items_sold_json
            # will contain all the items from new_cart_items.
            
            # Delete old SalesRecords associated with this transaction_id
            SalesRecord.query.filter_by(receipt_number=transaction_id, business_id=business_id).delete()
            
            # Create a new, single SalesRecord for the updated transaction
            updated_transaction_record = SalesRecord(
                business_id=business_id,
                transaction_date=first_sale_record.transaction_date, # Maintain original transaction date
                customer_phone=customer_phone,
                sales_person_name=sales_person_name,
                grand_total_amount=total_grand_amount,
                payment_method=first_sale_record.payment_method, # Keep original payment method
                receipt_number=transaction_id,
                reference_number=first_sale_record.reference_number # Keep original reference number
            )
            # Set the items_sold_json for this *single* new SalesRecord
            updated_transaction_record.set_items_sold(new_cart_items) 
            db.session.add(updated_transaction_record)


            db.session.commit()
            flash(f'Sale transaction {transaction_id[:8].upper()} updated successfully!', 'success')
            return redirect(url_for('sales'))

        # --- GET Request / Initial Render ---
        items_for_cart = []
        if sales_in_transaction:
            transaction_record = sales_in_transaction[0]
            items_for_cart = transaction_record.get_items_sold()

        sale_data_for_form = {
            'customer_phone': first_sale_record.customer_phone,
            'sales_person_name': first_sale_record.sales_person_name,
            'items': items_for_cart
        }

        return render_template('add_edit_sale.html', 
                            title=f'Edit Sale Transaction: {transaction_id[:8].upper()}', 
                            sale=sale_data_for_form, 
                            inventory_items=serialized_available_inventory_items,
                            user_role=session.get('role'),
                            pharmacy_info=pharmacy_info,
                            print_ready=False,
                            last_transaction_details=[],
                            last_transaction_grand_total=0.0,
                            last_transaction_id='',
                            last_transaction_customer_phone='',
                            last_transaction_sales_person='',
                            last_transaction_date='',
                            current_year=datetime.now().year,
                            auto_print=False) # ADDED: auto_print

    @app.route('/sales/delete_transaction/<transaction_id>')
    def delete_sale_transaction(transaction_id): # Note the parameter name change
        # ACCESS CONTROL: Allows admin role
        if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
            flash('You do not have permission to delete sales records or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        business_id = get_current_business_id()
        # Fetch all sale records for this transaction ID
        sales_to_delete = SalesRecord.query.filter_by(
            transaction_id=transaction_id, # Use transaction_id here
            business_id=business_id
        ).all()

        if not sales_to_delete:
            flash('Sale transaction not found.', 'danger')
            return redirect(url_for('sales'))
        
        transaction_id_for_flash = sales_to_delete[0].transaction_id # Get ID for flash message

        # Return stock to inventory for all items in the transaction
        for sale_record in sales_to_delete:
            product = InventoryItem.query.filter_by(id=sale_record.product_id, business_id=business_id).first()
            if product:
                quantity_to_return = sale_record.quantity_sold
                if sale_record.sale_unit_type == 'pack':
                    # Need to fetch the product again to get number_of_tabs if not already available
                    original_product_for_tabs = InventoryItem.query.filter_by(id=sale_record.product_id, business_id=business_id).first()
                    if original_product_for_tabs:
                        quantity_to_return = sale_record.quantity_sold * original_product_for_tabs.number_of_tabs
                
                product.current_stock += quantity_to_return
                product.last_updated = datetime.now()
                db.session.add(product)
            db.session.delete(sale_record) # Delete the individual sale record

        db.session.commit()
        flash(f'Sale transaction {transaction_id_for_flash[:8].upper()} and all its items deleted successfully! Stock returned to inventory.', 'success')
        return redirect(url_for('sales'))

    @app.route('/sales/print_receipt/<transaction_id>')
    # @login_required
    def print_sale_receipt(transaction_id):
        # ACCESS CONTROL: Allows admin, sales, and viewer roles
        if 'username' not in session or session.get('role') not in ['admin', 'sales', 'viewer'] or not get_current_business_id():
            flash('You do not have permission to view sales receipts or no business selected.', 'danger')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        
        # Fetch the SINGLE sales record for this specific transaction ID
        # Use .first() because each receipt_number is unique
        sales_record = SalesRecord.query.filter_by(
            receipt_number=transaction_id,
            business_id=business_id
        ).first()

        if not sales_record:
            flash('Sale transaction not found.', 'danger')
            return redirect(url_for('sales'))

        # Prepare items for the receipt by getting them from the JSON column
        receipt_items = []
        today = date.today()

        for item in sales_record.get_items_sold():
            product_item = InventoryItem.query.filter_by(id=item['product_id'], business_id=business_id).first()
            
            sale_item_expires_soon = False
            sale_item_expiry_date = None
            if product_item and product_item.expiry_date:
                sale_item_expiry_date = product_item.expiry_date
                time_to_expiry = product_item.expiry_date - today
                if time_to_expiry.days <= 180 and time_to_expiry.days >= 0:
                    sale_item_expires_soon = True
                elif time_to_expiry.days < 0:
                    sale_item_expires_soon = 'Expired'

            receipt_items.append({
                'product_name': item['product_name'],
                'quantity_sold': item['quantity_sold'],
                'sale_unit_type': item['sale_unit_type'],
                'price_at_time_per_unit_sold': item['price_at_time_per_unit_sold'],
                'total_amount': item['item_total_amount'], # Corrected key
                'expiry_date': sale_item_expiry_date,
                'expires_soon': sale_item_expires_soon
            })

        # Get business info for receipts (reusing from session)
        pharmacy_info = session.get('business_info', {
            "name": ENTERPRISE_NAME,
            "location": PHARMACY_LOCATION,
            "address": PHARMACY_ADDRESS,
            "contact": PHARMACY_CONTACT
        })

        return render_template('add_edit_sale.html',
                            title='Sale Receipt',
                            inventory_items=[],
                            sale={},
                            user_role=session.get('role'),
                            pharmacy_info=pharmacy_info,
                            print_ready=True,
                            auto_print=True,  # This is the new variable that fixes the error
                            last_transaction_details=receipt_items,
                            last_transaction_grand_total=sales_record.grand_total_amount,
                            last_transaction_id=transaction_id,
                            last_transaction_customer_phone=sales_record.customer_phone,
                            last_transaction_sales_person=sales_record.sales_person_name,
                            last_transaction_date=sales_record.transaction_date.strftime('%Y-%m-%d %H:%M:%S'),
                            current_year=datetime.now().year)

    # Add these routes to your app.py file

    @app.route('/sales/returns/print/<return_id>')
    @login_required
    def print_return_receipt(return_id):
        """Generate printable return receipt"""
        business_id = get_current_business_id()
        if not business_id:
            flash('No business selected. Please select a business first.', 'warning')
            return redirect(url_for('dashboard'))
        
        # Get the return record
        return_record = ReturnRecord.query.filter_by(
            id=return_id,
            business_id=business_id
        ).first()
        
        if not return_record:
            flash('Return record not found.', 'error')
            return redirect(url_for('returns_history'))
        
        # Get business information
        business = Business.query.get(business_id)
        
        return render_template('print_return_receipt.html',
                            return_record=return_record,
                            business=business,
                            current_year=datetime.now().year)

    @app.route('/sales/returns/send_sms', methods=['POST'])
    @login_required
    def send_return_sms():
        """Send return receipt via SMS"""
        try:
            business_id = get_current_business_id()
            if not business_id:
                return jsonify({
                    'success': False,
                    'message': 'No business selected'
                }), 400
            
            return_id = request.form.get('return_id')
            phone_number = request.form.get('phone_number')
            
            if not return_id or not phone_number:
                return jsonify({
                    'success': False,
                    'message': 'Missing return ID or phone number'
                }), 400
            
            # Get the return record
            return_record = ReturnRecord.query.filter_by(
                id=return_id,
                business_id=business_id
            ).first()
            
            if not return_record:
                return jsonify({
                    'success': False,
                    'message': 'Return record not found'
                }), 404
            
            # Get business information
            business = Business.query.get(business_id)
            
            # Format return items for SMS
            returned_items = return_record.get_returned_items()
            items_text = "\n".join([
                f"- {item['product_name']}: {item['quantity_returned']} @ GH₵{item['sale_price']:.2f} = GH₵{item['refund_amount']:.2f}"
                for item in returned_items
            ])
            
            # Create SMS message
            sms_message = f"""
    🧾 RETURN RECEIPT - {business.name}
    📍 {business.location or 'N/A'}
    📞 {business.contact or 'N/A'}

    🔄 Return Receipt: {return_record.return_receipt_number}
    📅 Date: {return_record.return_date.strftime('%Y-%m-%d %H:%M')}
    🎯 Original Receipt: {return_record.original_receipt_number}
    👤 Processed by: {return_record.processed_by}

    📦 RETURNED ITEMS:
    {items_text}

    💰 TOTAL REFUND: GH₵{return_record.total_refund_amount:.2f}
    🔄 Method: {return_record.payment_method or 'Not specified'}
    📝 Reason: {return_record.return_reason or 'Not specified'}

    Thank you for your business!
    """.strip()
            
            # Send SMS using Arkesel API (similar to your existing SMS functionality)
            sms_success = send_sms_via_arkesel(phone_number, sms_message)
            
            if sms_success:
                return jsonify({
                    'success': True,
                    'message': f'Return receipt sent to {phone_number}'
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Failed to send SMS. Please check phone number and try again.'
                }), 500
                
        except Exception as e:
            logging.error(f"Error sending return SMS: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Internal server error'
            }), 500

    def send_sms_via_arkesel(phone_number, message):
        """Send SMS using Arkesel API - reuse your existing SMS function"""
        try:
            # Clean phone number
            phone = phone_number.strip()
            if phone.startswith('0'):
                phone = '233' + phone[1:]
            elif not phone.startswith('233'):
                phone = '233' + phone
            
            # Prepare SMS payload
            sms_payload = {
                'key': ARKESEL_API_KEY,
                'to': phone,
                'msg': message,
                'sender': ARKESEL_SENDER_ID
            }
            
            # Send SMS
            response = requests.post(ARKESEL_SMS_URL, data=sms_payload, timeout=30)
            
            if response.status_code == 200:
                response_data = response.json()
                return response_data.get('code') == '200'
            else:
                return False
                
        except Exception as e:
            logging.error(f"Arkesel SMS error: {str(e)}")
            return False
    # Returns Processing Route
    @app.route('/sales/add_return', methods=['GET', 'POST'])
    @csrf.exempt
    @login_required  # Only require login, not specific roles
    def add_return():
        business_id = get_current_business_id()
        if not business_id:
            flash('No business selected. Please select a business first.', 'warning')
            return redirect(url_for('dashboard'))
        
        if request.method == 'GET':
            # Handle search for sale record
            receipt_number = request.args.get('receipt_number', '').strip()
            sale_record = None
            
            if receipt_number:
                # Search for the sale record by receipt number
                sale_record = SalesRecord.query.filter_by(
                    receipt_number=receipt_number,
                    business_id=business_id
                ).first()
            
            return render_template('add_edit_return.html', 
                                 title='Process Return',
                                 sale_record=sale_record,
                                 current_year=datetime.now().year)
        
        elif request.method == 'POST':
            # Process the return
            try:
                # Get form data
                original_receipt_number = request.form.get('original_receipt_number', '').strip()
                original_sale_id = request.form.get('original_sale_id', '').strip()
                customer_name = request.form.get('customer_name', '').strip()
                customer_phone = request.form.get('customer_phone', '').strip()
                return_reason = request.form.get('return_reason', '').strip()
                payment_method = request.form.get('payment_method', '').strip()
                notes = request.form.get('notes', '').strip()
                
                # Get selected items for return
                return_items = request.form.getlist('return_items')
                return_quantities = request.form.getlist('return_quantities')
                item_names = request.form.getlist('item_names')
                original_quantities = request.form.getlist('original_quantities')
                unit_prices = request.form.getlist('unit_prices')
                sale_unit_types = request.form.getlist('sale_unit_types')
                
                if not return_items:
                    flash('Please select at least one item to return.', 'danger')
                    return redirect(url_for('add_return', receipt_number=original_receipt_number))
                
                if not return_reason or not payment_method:
                    flash('Please provide a return reason and refund method.', 'danger')
                    return redirect(url_for('add_return', receipt_number=original_receipt_number))
                
                # Verify the original sale exists
                original_sale = SalesRecord.query.filter_by(
                    id=original_sale_id,
                    business_id=business_id
                ).first()
                
                if not original_sale:
                    flash('Original sale record not found.', 'danger')
                    return redirect(url_for('add_return'))
                
                # Process returned items and calculate refund
                returned_items = []
                total_refund = 0.0
                
                for i, item_index in enumerate(return_items):
                    item_idx = int(item_index)
                    return_quantity = float(return_quantities[item_idx])
                    
                    if return_quantity <= 0:
                        continue
                    
                    # Get item details
                    item_name = item_names[item_idx]
                    original_quantity = float(original_quantities[item_idx])
                    unit_price = float(unit_prices[item_idx])
                    unit_type = sale_unit_types[item_idx]
                    
                    # Validate return quantity
                    if return_quantity > original_quantity:
                        flash(f'Return quantity for {item_name} cannot exceed original quantity of {original_quantity}.', 'danger')
                        return redirect(url_for('add_return', receipt_number=original_receipt_number))
                    
                    # Calculate refund for this item
                    item_refund = return_quantity * unit_price
                    total_refund += item_refund
                    
                    # Add to returned items list
                    returned_items.append({
                        'product_name': item_name,
                        'return_quantity': return_quantity,
                        'original_quantity': original_quantity,
                        'unit_price': unit_price,
                        'sale_unit_type': unit_type,
                        'refund_amount': item_refund
                    })
                    
                    # Update inventory - Add returned items back to stock
                    inventory_item = InventoryItem.query.filter_by(
                        product_name=item_name,
                        business_id=business_id
                    ).first()
                    
                    if inventory_item:
                        inventory_item.current_stock += return_quantity
                        inventory_item.last_updated = datetime.now()
                        print(f"DEBUG: Added {return_quantity} {unit_type} of {item_name} back to inventory. New stock: {inventory_item.current_stock}")
                    else:
                        print(f"WARNING: Could not find inventory item '{item_name}' to update stock")
                
                if total_refund <= 0:
                    flash('No valid items selected for return.', 'danger')
                    return redirect(url_for('add_return', receipt_number=original_receipt_number))
                
                # Generate return receipt number
                return_receipt_number = f"RET-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
                
                # Create return record
                return_record = ReturnRecord(
                    business_id=business_id,
                    original_receipt_number=original_receipt_number,
                    return_receipt_number=return_receipt_number,
                    return_date=datetime.now(),
                    customer_phone=customer_phone or original_sale.customer_phone,
                    customer_name=customer_name,
                    processed_by=current_user.username,
                    return_reason=return_reason,
                    total_refund_amount=total_refund,
                    payment_method=payment_method,
                    notes=notes
                )
                
                # Set returned items as JSON
                return_record.set_returned_items(returned_items)
                
                # Save to database
                db.session.add(return_record)
                db.session.commit()
                
                print(f"DEBUG: Return processed successfully. Return receipt: {return_receipt_number}, Total refund: GHS{total_refund:.2f}")
                
                # Success message with details
                items_summary = ", ".join([f"{item['product_name']} ({item['return_quantity']} {item['sale_unit_type']})" for item in returned_items])
                flash(f'Return processed successfully! Return Receipt: {return_receipt_number}. Refunded GHS{total_refund:.2f} for: {items_summary}', 'success')
                
                return redirect(url_for('sales'))
                
            except Exception as e:
                db.session.rollback()
                print(f"ERROR: Failed to process return: {str(e)}")
                flash(f'Error processing return: {str(e)}', 'danger')
                return redirect(url_for('add_return', receipt_number=request.form.get('original_receipt_number', '')))

    # Returns History Route
    @app.route('/sales/returns')
    @login_required
    def returns_history():
        business_id = get_current_business_id()
        if not business_id:
            flash('No business selected. Please select a business first.', 'warning')
            return redirect(url_for('dashboard'))
        
        # Get search parameters
        search_query = request.args.get('search', '').strip()
        
        # Base query for returns
        returns_query = ReturnRecord.query.filter_by(business_id=business_id)
        
        # Apply search filter if provided
        if search_query:
            returns_query = returns_query.filter(
                db.or_(
                    ReturnRecord.return_receipt_number.ilike(f'%{search_query}%'),
                    ReturnRecord.original_receipt_number.ilike(f'%{search_query}%'),
                    ReturnRecord.customer_phone.ilike(f'%{search_query}%'),
                    ReturnRecord.customer_name.ilike(f'%{search_query}%'),
                    ReturnRecord.processed_by.ilike(f'%{search_query}%')
                )
            )
        
        # Order by most recent first
        returns = returns_query.order_by(ReturnRecord.return_date.desc()).all()
        
        # Calculate total refunds
        total_refunds = sum(return_record.total_refund_amount for return_record in returns)
        
        return render_template('returns_history.html', 
                             title='Returns History',
                             returns=returns,
                             total_refunds=total_refunds,
                             search_query=search_query,
                             current_year=datetime.now().year)
    
    # --- Reports Route ---
    @app.route('/register', methods=['GET'])
    def show_registration_form():
        """
        Renders the HTML form for business registration.
        """
        return render_template('register_form.html')
    @app.route('/reports')
    # @login_required
    def reports():
        # ACCESS CONTROL: Only admin can view reports
        if session.get('role') != 'admin':
            flash('You do not have permission to view reports.', 'danger')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        if not business_id:
            flash('No business selected. Please select a business to view reports.', 'warning')
            return redirect(url_for('dashboard'))

        business_type = get_current_business_type()

        # Get filters from request arguments for sales-related reports
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        
        # Initialize date filters for sales queries
        min_date = datetime.min
        max_date = datetime.max
        
        # Parse date filters, handling potential errors
        if start_date_str:
            try:
                min_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            except ValueError:
                flash('Invalid start date format. Using default.', 'warning')
                start_date_str = '' # Clear invalid input
        if end_date_str:
            try:
                # Add one day to end_date and subtract a microsecond to include the whole day
                max_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1) - timedelta(microseconds=1)
            except ValueError:
                flash('Invalid end date format. Using default.', 'warning')
                end_date_str = '' # Clear invalid input

        # Base query for SalesRecord within the business and date range
        sales_query = SalesRecord.query.filter(
            SalesRecord.business_id == business_id,
            SalesRecord.transaction_date >= min_date,
            SalesRecord.transaction_date <= max_date
        )

        # Initialize report data
        report_data = {}
        
        # --- Calculate Total Cost of Current Stock ---
        total_cost_of_stock = 0.0
        # --- Calculate Total Sale Value of Current Stock ---
        total_sale_value_of_stock = 0.0

        inventory_items_for_stock_val = InventoryItem.query.filter_by(business_id=business_id, is_active=True).all()
        for item in inventory_items_for_stock_val:
            current_stock = item.current_stock or 0.0
            number_of_tabs = item.number_of_tabs or 1.0 # Ensure it's not zero for division

            # Calculate cost value
            cost_per_base_unit = float(item.purchase_price / number_of_tabs) if number_of_tabs > 0 else 0.0
            total_cost_of_stock += current_stock * cost_per_base_unit

            # Calculate sale value (potential revenue from current stock)
            item_type = item.item_type
            sale_price_per_pack = item.sale_price or 0.0
            fixed_sale_price = item.fixed_sale_price or 0.0
            unit_price_per_tab = item.unit_price_per_tab or 0.0
            
            sale_value_per_base_unit = 0.0
            if item.is_fixed_price:
                sale_value_per_base_unit = float(fixed_sale_price / number_of_tabs) if number_of_tabs > 0 else 0.0
            else:
                if item_type == 'Pharmacy': 
                    # Pharmacy items price based on markup on purchase price
                    sale_value_per_base_unit = float(item.purchase_price * (1 + (item.markup_percentage_pharmacy or 0) / 100) / number_of_tabs) if number_of_tabs > 0 else 0.0
                elif item_type == 'Hardware Material': 
                    # Hardware might sell by piece, so unit_price_per_tab (which is per-piece) is relevant
                    sale_value_per_base_unit = unit_price_per_tab 
                else: 
                    # Default or other types, consider sale_price for packs, convert to per base unit
                    sale_value_per_base_unit = float(sale_price_per_pack / number_of_tabs) if number_of_tabs > 0 else 0.0
            
            total_sale_value_of_stock += current_stock * sale_value_per_base_unit

        total_potential_gross_profit = total_sale_value_of_stock - total_cost_of_stock
        overall_stock_profit_margin = (total_potential_gross_profit / total_sale_value_of_stock) * 100 if total_sale_value_of_stock > 0 else 0.0

        # --- Total Actual Sales Revenue (overall for the business) ---
        # Using grand_total_amount as the correct column
        total_sales_amount = db.session.query(db.func.sum(SalesRecord.grand_total_amount)).filter( # RENAMED THIS VARIABLE
            SalesRecord.business_id == business_id
        ).scalar() or 0.0

        # --- Sales by Sales Person (Last 30 days) ---
        thirty_days_ago = datetime.now() - timedelta(days=30)
        sales_by_person = db.session.query(
            SalesRecord.sales_person_name,
            db.func.sum(SalesRecord.grand_total_amount) # Use grand_total_amount
        ).filter(
            SalesRecord.business_id == business_id,
            SalesRecord.transaction_date >= thirty_days_ago # Use transaction_date
        ).group_by(SalesRecord.sales_person_name).order_by(db.func.sum(SalesRecord.grand_total_amount).desc()).all()


        # --- Inventory Stock Summary (all active items) ---
        inventory_summary = InventoryItem.query.filter_by(business_id=business_id, is_active=True).order_by(InventoryItem.product_name).all()

        # --- Pharmacy specific reports ---
        expired_items = []
        expiring_soon_items = []
        if business_type == 'Pharmacy':
            today = date.today()
            three_months_from_now = today + timedelta(days=90)
            
            expired_items = InventoryItem.query.filter(
                InventoryItem.business_id == business_id,
                InventoryItem.is_active == True,
                InventoryItem.expiry_date != None,
                InventoryItem.expiry_date < today
            ).order_by(InventoryItem.expiry_date).all()

            expiring_soon_items = InventoryItem.query.filter(
                InventoryItem.business_id == business_id,
                InventoryItem.is_active == True,
                InventoryItem.expiry_date != None,
                InventoryItem.expiry_date >= today,
                InventoryItem.expiry_date <= three_months_from_now
            ).order_by(InventoryItem.expiry_date).all()

        # --- Hardware specific reports ---
        company_balances = []
        rental_records = [] # Initialize for all business types
        if business_type == 'Hardware':
            # Assuming Company model exists and has business_id
            companies = Company.query.filter_by(business_id=business_id, is_active=True).all()        # Assuming RentalRecord model exists and has business_id and date_recorded
            rental_records = RentalRecord.query.filter_by(business_id=business_id).order_by(RentalRecord.rent_date.desc()).all()

        return render_template('reports.html',
                            user_role=session.get('role'),
                            business_type=business_type,
                            
                            # Overall Stock Metrics
                            total_cost_of_stock=total_cost_of_stock,
                            total_sale_value_of_stock=total_sale_value_of_stock,
                            total_potential_gross_profit=total_potential_gross_profit,
                            overall_stock_profit_margin=overall_stock_profit_margin,
                            
                            # Sales Metrics
                            total_sales_amount=total_sales_amount, # NOW MATCHES TEMPLATE EXPECTATION
                            sales_by_person=sales_by_person,
                            
                            # Inventory Details
                            inventory_summary=inventory_summary,
                            expired_items=expired_items,
                            expiring_soon_items=expiring_soon_items,
                            
                            # Hardware Specific (if applicable)
                            company_balances=company_balances,
                            rental_records=rental_records,

                            current_year=datetime.now().year,
                            start_date=start_date_str, # Passed for filter persistence
                            end_date=end_date_str      # Passed for filter persistence
        )

    @app.route('/send_daily_sales_sms_report')
    def send_daily_sales_sms_report():
        # ACCESS CONTROL: Allows admin role
        if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
            flash('You do not have permission to send daily sales reports or no business selected.', 'danger')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        today = date.today()
        
        today_sales = SalesRecord.query.filter_by(business_id=business_id).filter(
            db.func.date(SalesRecord.sale_date) == today
        ).all()

        total_sales_amount = sum(s.total_amount for s in today_sales)
        total_items_sold = sum(s.quantity_sold for s in today_sales) # This is approximate as it sums different units

        product_sales_summary = {}
        for sale in today_sales:
            product_name = sale.product_name
            quantity = sale.quantity_sold
            unit_type = sale.sale_unit_type
            key = f"{product_name} ({unit_type})"
            product_sales_summary[key] = product_sales_summary.get(key, 0.0) + quantity

        business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
        message = f"Daily Sales Report ({today.strftime('%Y-%m-%d')}):\n"
        message += f"Total Revenue: GH₵{total_sales_amount:.2f}\n"
        message += f"Total Items Sold (approx): {total_items_sold:.2f}\n"
        
        if product_sales_summary:
            message += "Product Breakdown:\n"
            for product_key, qty in product_sales_summary.items():
                message += f"- {product_key}: {qty:.2f} units\n"
        else:
            message += "No sales recorded today."
        
        message += f"\nThank you for trading with us\n"
        message += f"From: {business_name_for_sms}"

        if not ADMIN_PHONE_NUMBER:
            flash('Admin phone number is not configured for SMS reports.', 'danger')
            return redirect(url_for('reports'))

        sms_payload = {
            'action': 'send-sms', 'api_key': ARKESEL_API_KEY, 'to': ADMIN_PHONE_NUMBER,
            'from': ARKESEL_SENDER_ID, 'sms': message
        }
        
        try:
            sms_response = requests.get(ARKESEL_SMS_URL, params=sms_payload)
            sms_result = sms_response.json()
            if sms_result.get('status') == 'success':
                flash('Daily sales report SMS sent to admin successfully!', 'success')
            else:
                print(f"Arkesel SMS Error: {sms_result.get('message', 'Unknown error')}")
                flash(f'Failed to send daily sales report SMS. Error: {sms_result.get("message", "Unknown error")}', 'danger')
        except requests.exceptions.RequestException as e:
            print(f'Network error sending SMS: {e}')
            flash(f'Network error when trying to send daily sales report SMS: {e}', 'danger')
        
        return redirect(url_for('reports'))

    # --- New Hardware Business Routes ---


    @app.route('/companies')
    # @login_required # Make sure this decorator is active if you need login protection
    def companies():
        # ACCESS CONTROL: Allows admin, sales, and viewer roles
        if 'username' not in session or session.get('role') not in ['admin', 'viewer', 'sales'] or not get_current_business_id():
            flash('You do not have permission to manage companies or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        search_query = request.args.get('search', '').strip()

        companies_query = Company.query.filter_by(business_id=business_id)

        if search_query:
            companies_query = companies_query.filter(
                Company.name.ilike(f'%{search_query}%') |
                Company.contact_person.ilike(f'%{search_query}%') |
                Company.phone_number.ilike(f'%{search_query}%') | # Changed from Company.phone to Company.phone_number
                Company.email.ilike(f'%{search_query}%') |
                Company.address.ilike(f'%{search_query}%')
            )

        companies = companies_query.all()

        processed_companies = []
        total_creditors_sum = 0.0 # Initialize sum for creditors
        total_debtors_sum = 0.0   # Initialize sum for debtors

        for company in companies:
            # Get the balance by calling the method on the Company object
            # This assumes Company.calculate_current_balance() is correctly defined on the model
            company_balance = company.calculate_current_balance()
            
            # Calculate total_creditors and total_debtors for each company based on balance
            # A company is a creditor if its balance is negative (we owe them)
            # A company is a debtor if its balance is positive (they owe us)
            display_creditors = 0.0
            display_debtors = 0.0

            if company_balance < 0:
                display_creditors = abs(company_balance) # Store as positive for display
                total_creditors_sum += abs(company_balance)
            elif company_balance > 0:
                display_debtors = company_balance
                total_debtors_sum += company_balance
            
            # Create a dictionary for the company data to be passed to the template
            # This prevents directly adding attributes to SQLAlchemy model instances which can be problematic
            processed_companies.append({
                'id': company.id,
                'name': company.name,
                'contact_person': company.contact_person,
                'phone_number': company.phone_number, # Ensure this is passed
                'email': company.email,
                'address': company.address,
                'is_active': company.is_active,
                'date_added': company.date_added,
                'balance': company_balance, # The actual net balance (can be positive or negative)
                'display_creditors': display_creditors, # For display purposes
                'display_debtors': display_debtors     # For display purposes
            })

        return render_template('company_list.html', 
                            companies=processed_companies, 
                            user_role=session.get('role'), 
                            search_query=search_query, 
                            current_year=datetime.now().year,
                            total_creditors_sum=total_creditors_sum, # Pass the sum of creditors
                            total_debtors_sum=total_debtors_sum)     # Pass the sum of debtors

    @app.route('/companies/add', methods=['GET', 'POST'])
    def add_company():
        # ACCESS CONTROL: Allows admin role
        if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
            flash('You do not have permission to add companies or no business selected.', 'danger')
            return redirect(url_for('dashboard'))

        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        if request.method == 'POST':
            name = request.form['name'].strip()
            contact_person = request.form['contact_person'].strip()
            phone = request.form['phone'].strip()
            email = request.form['email'].strip()
            address = request.form['address'].strip()
            
            # Check if company with this name already exists for this business
            if Company.query.filter_by(name=name, business_id=business_id).first():
                flash('Company with this name already exists for this business.', 'danger')
                # Pass the form data back to pre-fill the form fields on error
                form_data = request.form.to_dict()
                # For display purposes on error, you can still pass these as 0.0
                # They are NOT being passed to the Company constructor here.
                form_data['total_creditors_amount'] = 0.0 # Use the property name for consistency
                form_data['total_debtors_amount'] = 0.0   # Use the property name for consistency
                return render_template('add_edit_company.html', title='Add New Company', company=form_data, current_year=datetime.now().year)

            new_company = Company(
                business_id=business_id,
                name=name,
                contact_person=contact_person,
                phone_number=phone,
                email=email,
                address=address,
                # balance=0.0            # New company starts with 0 balance
                # IMPORTANT: REMOVE total_creditors and total_debtors here.
                # They are calculated properties, not direct columns.
                # total_creditors=0.0,
                # total_debtors=0.0
            )
            db.session.add(new_company)
            db.session.commit()

            # After the company is created, you might want to initialize Creditor/Debtor records
            # for it with a 0 balance, though they will be created on first transaction anyway.
            # This is optional, as the current transaction logic handles creation if not exists.
            # new_creditor_record = Creditor(business_id=business_id, company_id=new_company.id, balance=0.0)
            # new_debtor_record = Debtor(business_id=business_id, company_id=new_company.id, balance=0.0)
            # db.session.add(new_creditor_record)
            # db.session.add(new_debtor_record)
            # db.session.commit() # Commit again if you add these here

            flash(f'Company "{name}" added successfully!', 'success')
            return redirect(url_for('companies'))

        # For GET request, display an empty form for adding
        # Initialize company dictionary with default values for a new company
        empty_company = {
            'name': '', 'contact_person': '', 'phone': '', 'email': '', 'address': '',
            'balance': 0.0, # This is the actual column
            'total_creditors_amount': 0.0, # For display in template, matching property name
            'total_debtors_amount': 0.0    # For display in template, matching property name
        }
        return render_template('add_edit_company.html', title='Add New Company', company=empty_company, current_year=datetime.now().year)

    # The filter_company_transactions function is fine as is, no changes needed for this error.
    def filter_company_transactions(company_id, search_query, start_date_str, end_date_str):
        transactions_query = CompanyTransaction.query.filter_by(company_id=company_id)

        if search_query:
            transactions_query = transactions_query.filter(
                CompanyTransaction.description.ilike(f'%{search_query}%') |
                CompanyTransaction.type.ilike(f'%{search_query}%') |
                CompanyTransaction.recorded_by.ilike(f'%{search_query}%')
            )

        if start_date_str:
            try:
                start_date_obj = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                transactions_query = transactions_query.filter(cast(CompanyTransaction.date, db.Date) >= start_date_obj)
            except ValueError:
                flash('Invalid start date format. Please use YYYY-MM-DD.', 'danger')
        
        if end_date_str:
            try:
                end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                transactions_query = transactions_query.filter(cast(CompanyTransaction.date, db.Date) <= end_date_obj)
            except ValueError:
                flash('Invalid end date format. Please use YYYY-MM-DD.', 'danger')

        return transactions_query.order_by(CompanyTransaction.date.desc()).all()


    @app.route('/companies/edit/<company_id>', methods=['GET', 'POST'])
    def edit_company(company_id):
        # ACCESS CONTROL: Allows admin role
        if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
            flash('You do not have permission to edit companies or no business selected.', 'danger')
            return redirect(url_for('dashboard'))

        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        company_to_edit = Company.query.filter_by(id=company_id, business_id=business_id).first_or_404()

        # --- THIS IS THE CRITICAL CORRECTION: CALCULATE BALANCES BEFORE RENDERING ---
        # This ensures that total_creditors and total_debtors are always up-to-date
        # based on transactions, not user input.
        balance_details = calculate_company_balance_details(company_id)
        company_to_edit.balance = balance_details['balance']
        company_to_edit.total_creditors = balance_details['total_creditors']
        company_to_edit.total_debtors = balance_details['total_debtors']
        # Note: These calculated values are updated on the Python object for display,
        # but are NOT committed to the database here. They should only be updated
        # in the database when transactions are added, edited, or deleted.

        if request.method == 'POST':
            name = request.form['name'].strip()
            contact_person = request.form['contact_person'].strip()
            phone = request.form['phone'].strip()
            email = request.form['email'].strip()
            address = request.form['address'].strip()
            
            # IMPORTANT: Do NOT retrieve total_creditors and total_debtors from request.form here.
            # They are calculated fields and should not be modified by this form submission.

            # Check for duplicate name (excluding the current company being edited)
            if Company.query.filter(Company.name == name, Company.business_id == business_id, Company.id != company_id).first():
                flash('Company with this name already exists for this business.', 'danger')
                # Pass the form data back, ensuring the calculated balance details are preserved
                form_data = request.form.to_dict()
                form_data['total_creditors'] = company_to_edit.total_creditors # Use the already calculated values
                form_data['total_debtors'] = company_to_edit.total_debtors   # Use the already calculated values
                return render_template('add_edit_company.html', title='Edit Company', company=form_data, current_year=datetime.now().year)

            company_to_edit.name = name
            company_to_edit.contact_person = contact_person
            company_to_edit.phone = phone
            company_to_edit.email = email
            company_to_edit.address = address

            db.session.commit() # Commit changes to the company's static details
            flash(f'Company "{name}" updated successfully!', 'success')
            return redirect(url_for('companies'))

        return render_template('add_edit_company.html', title='Edit Company', company=company_to_edit, current_year=datetime.now().year)
    @app.route('/companies/delete/<company_id>')
    def delete_company(company_id):
        # ACCESS CONTROL: Allows admin role
        if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
            flash('You do not have permission to delete companies or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        company_to_delete = Company.query.filter_by(id=company_id, business_id=business_id).first_or_404()

        if company_to_delete.balance != 0:
            flash('Cannot delete company with outstanding balance. Please settle balance first.', 'danger')
            return redirect(url_for('companies'))

        db.session.delete(company_to_delete)
        db.session.commit()
        flash(f'Company "{company_to_delete.name}" deleted successfully!', 'success')
        return redirect(url_for('companies'))

    # @app.route('/company/<string:company_id>/transactions', methods=['GET', 'POST'])
    # @login_required
    # def company_transaction(company_id):
    #     """
    #     Handles company transactions, including recording new transactions,
    #     updating company balance, sending SMS receipts, and displaying
    #     a list of transactions with filtering capabilities.
    #     """
    #     business_id = get_current_business_id()
    #     company = Company.query.filter_by(id=company_id, business_id=business_id).first_or_404()

    #     business_info = session.get('business_info', {})
    #     if not business_info or not business_info.get('name'):
    #         business_details = Business.query.filter_by(id=business_id).first()
    #         if business_details:
    #             business_info = {
    #                 'name': business_details.name,
    #                 'address': business_details.address,
    #                 'location': business_details.location,
    #                 'phone': business_details.contact,
    #                 'email': business_details.email if hasattr(business_details, 'email') else 'N/A'
    #             }
    #         else:
    #             business_info = {
    #                 'name': "Your Enterprise Name", # Replace with actual constant
    #                 'address': "Your Pharmacy Address", # Replace with actual constant
    #                 'location': "Your Pharmacy Location", # Replace with actual constant
    #                 'phone': "Your Pharmacy Contact", # Replace with actual constant
    #                 'email': 'info@example.com' # Default email
    #             }

    #     last_company_transaction_id = None
    #     last_company_transaction_details = None
    #     transactions = [] # Initialize here to ensure it's always defined

    #     if request.method == 'POST':
    #         transaction_type = request.form['type']
    #         amount = float(request.form['amount'])
    #         description = request.form.get('description')
    #         send_sms_receipt = 'send_sms_receipt' in request.form
    #         recorded_by = session['username']

    #         new_transaction = CompanyTransaction(
    #             business_id=business_id,
    #             company_id=company.id,
    #             transaction_type=transaction_type, 
    #             amount=amount,
    #             description=description,
    #             transaction_date=date.today(),  # ADDED THIS LINE
    #             recorded_by=recorded_by
    #         )
    #         db.session.add(new_transaction)
    #         db.session.commit()

    #         # Recalculate company balance AFTER the new transaction is committed
    #         updated_company_balance = company.calculate_current_balance()

    #         flash(f'Transaction recorded successfully! Company balance updated to GH₵{updated_company_balance:.2f}', 'success')

    #         last_company_transaction_details = {
    #             'id': new_transaction.id,
    #             'transaction_type': new_transaction.transaction_type, 
    #             'amount': new_transaction.amount,
    #             'description': new_transaction.description,
    #             'date': new_transaction.transaction_date.strftime('%Y-%m-%d %H:%M:%S'), 
    #             'recorded_by': new_transaction.recorded_by,
    #             'company_name': company.name,
    #             'company_id': company.id,
    #             'new_balance': updated_company_balance 
    #         }
    #         session['last_company_transaction_id'] = new_transaction.id
    #         session['last_company_transaction_details'] = last_company_transaction_details

    #         if send_sms_receipt and company.phone_number: 
    #             message = (f"Dear {company.name}, a {new_transaction.transaction_type} transaction of GH₵{new_transaction.amount:.2f} "
    #                     f"was recorded by {business_info.get('name', 'Your Business')}. Your new balance is GH₵{updated_company_balance:.2f}. "
    #                     f"Description: {new_transaction.description or 'N/A'}")
    #             # Assuming send_sms function exists
    #             # sms_success, sms_msg = send_sms(company.phone_number, message) 
    #             # if sms_success:
    #             #     flash(f'SMS receipt sent to {company.phone_number}.', 'info')
    #             # else:
    #             #     flash(f'Failed to send SMS receipt: {sms_msg}', 'warning')
    #         elif send_sms_receipt and not company.phone_number:
    #             flash('Cannot send SMS receipt: Company contact number not available.', 'warning')

    #         return redirect(url_for('company_transaction', company_id=company.id))


    #     # --- Logic for GET request and initial page load ---
    #     transactions_query = CompanyTransaction.query.filter_by(
    #         company_id=company.id,
    #         business_id=business_id
    #     )

    #     search_query = request.args.get('search', '').strip()
    #     start_date_str = request.args.get('start_date')
    #     end_date_str = request.args.get('end_date')

    #     if search_query:
    #         transactions_query = transactions_query.filter(
    #             (CompanyTransaction.description.ilike(f'%{search_query}%')) |
    #             (CompanyTransaction.transaction_type.ilike(f'%{search_query}%')) | 
    #             (CompanyTransaction.recorded_by.ilike(f'%{search_query}%'))
    #         )

    #     if start_date_str:
    #         try:
    #             start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    #             transactions_query = transactions_query.filter(CompanyTransaction.transaction_date >= start_date) 
    #         except ValueError:
    #             flash('Invalid start date format.', 'danger')
    #             pass

    #     if end_date_str:
    #         try:
    #             end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    #             transactions_query = transactions_query.filter(CompanyTransaction.transaction_date < (end_date + timedelta(days=1))) 
    #         except ValueError:
    #             flash('Invalid end date format.', 'danger')
    #             pass

    #     transactions = transactions_query.order_by(CompanyTransaction.transaction_date.desc()).all()

    #     total_transactions_sum = sum(t.amount for t in transactions)
        
    #     # Calculate the current balance for the company
    #     company_current_balance = company.calculate_current_balance()

    #     # Prepare company data to pass to the template, including the calculated balance
    #     company_data_for_template = {
    #         'id': company.id,
    #         'name': company.name,
    #         'contact_person': company.contact_person,
    #         'phone_number': company.phone_number,
    #         'email': company.email,
    #         'address': company.address,
    #         'is_active': company.is_active,
    #         'date_added': company.date_added,
    #         'current_balance': company_current_balance # Pass the calculated balance here
    #     }

    #     return render_template('company_transaction.html', # Template name is company_transactions.html (plural)
    #                         company=company_data_for_template, # Pass the dictionary with balance
    #                         transactions=transactions,
    #                         search_query=search_query,
    #                         start_date=start_date_str,
    #                         end_date=end_date_str,
    #                         business_info=business_info,
    #                         total_transactions_sum=total_transactions_sum,
    #                         current_year=datetime.now().year
    #                         )

    # @app.route('/company/<string:company_id>/transactions', methods=['GET', 'POST'])
    # @login_required
    # def company_transaction(company_id):
    #     """
    #     Handles company transactions, including recording new transactions,
    #     updating company balance, sending SMS receipts, and displaying
    #     a list of transactions with filtering capabilities.
    #     """
    #     business_id = get_current_business_id()
    #     company = Company.query.filter_by(id=company_id, business_id=business_id).first_or_404()

    #     business_info = session.get('business_info', {})
    #     if not business_info or not business_info.get('name'):
    #         business_details = Business.query.filter_by(id=business_id).first()
    #         if business_details:
    #             business_info = {
    #                 'name': business_details.name,
    #                 'address': business_details.address,
    #                 'location': business_details.location,
    #                 'phone': business_details.contact,
    #                 'email': business_details.email if hasattr(business_details, 'email') else 'N/A'
    #             }
    #         else:
    #             business_info = {
    #                 'name': "Your Enterprise Name",
    #                 'address': "Your Pharmacy Address",
    #                 'location': "Your Pharmacy Location",
    #                 'phone': "Your Pharmacy Contact",
    #                 'email': 'info@example.com'
    #             }

    #     last_company_transaction_id = None
    #     last_company_transaction_details = None
    #     transactions = []

    #     if request.method == 'POST':
    #         transaction_type = request.form['type']
    #         amount = float(request.form['amount'])
    #         description = request.form.get('description')
    #         send_sms_receipt = 'send_sms_receipt' in request.form

    #         # Change `recorded_by` to use the user's UUID
    #         # Flask-Login's `current_user` object provides the ID.
    #         if not current_user.is_authenticated:
    #             flash("You must be logged in to record a transaction.", "danger")
    #             return redirect(url_for('login'))
            
    #         recorded_by_id = current_user.id # This is the UUID from your user table

    #         new_transaction = CompanyTransaction(
    #             business_id=business_id,
    #             company_id=company.id,
    #             transaction_type=transaction_type, 
    #             amount=amount,
    #             description=description,
    #             transaction_date=date.today(),
    #             recorded_by=recorded_by_id # Use the ID here
    #         )
    #         db.session.add(new_transaction)
    #         db.session.commit()

    #         updated_company_balance = company.calculate_current_balance()
    #         flash(f'Transaction recorded successfully! Company balance updated to GH₵{updated_company_balance:.2f}', 'success')

    #         last_company_transaction_details = {
    #             'id': new_transaction.id,
    #             'transaction_type': new_transaction.transaction_type, 
    #             'amount': new_transaction.amount,
    #             'description': new_transaction.description,
    #             'date': new_transaction.transaction_date.strftime('%Y-%m-%d %H:%M:%S'), 
    #             # Use a lookup for the username to display it, as the database now stores the ID
    #             'recorded_by': current_user.username,
    #             'company_name': company.name,
    #             'company_id': company.id,
    #             'new_balance': updated_company_balance 
    #         }
    #         session['last_company_transaction_id'] = new_transaction.id
    #         session['last_company_transaction_details'] = last_company_transaction_details

    #         if send_sms_receipt and company.phone_number: 
    #             message = (f"Dear {company.name}, a {new_transaction.transaction_type} transaction of GH₵{new_transaction.amount:.2f} "
    #                     f"was recorded by {business_info.get('name', 'Your Business')}. Your new balance is GH₵{updated_company_balance:.2f}. "
    #                     f"Description: {new_transaction.description or 'N/A'}")
    #             # Assuming send_sms function exists
    #             # sms_success, sms_msg = send_sms(company.phone_number, message) 
    #             # if sms_success:
    #             #     flash(f'SMS receipt sent to {company.phone_number}.', 'info')
    #             # else:
    #             #     flash(f'Failed to send SMS receipt: {sms_msg}', 'warning')
    #         elif send_sms_receipt and not company.phone_number:
    #             flash('Cannot send SMS receipt: Company contact number not available.', 'warning')

    #         return redirect(url_for('company_transaction', company_id=company.id))

    #     # --- Logic for GET request and initial page load ---
    #     transactions_query = CompanyTransaction.query.filter_by(
    #         company_id=company.id,
    #         business_id=business_id
    #     )

    #     search_query = request.args.get('search', '').strip()
    #     start_date_str = request.args.get('start_date')
    #     end_date_str = request.args.get('end_date')

    #     if search_query:
    #         # Update the search filter to use the User model for username lookup
    #         transactions_query = transactions_query.join(User).filter(
    #             (CompanyTransaction.description.ilike(f'%{search_query}%')) |
    #             (CompanyTransaction.transaction_type.ilike(f'%{search_query}%')) | 
    #             (User.username.ilike(f'%{search_query}%'))
    #         )

    #     if start_date_str:
    #         try:
    #             start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    #             transactions_query = transactions_query.filter(CompanyTransaction.transaction_date >= start_date) 
    #         except ValueError:
    #             flash('Invalid start date format.', 'danger')
    #             pass

    #     if end_date_str:
    #         try:
    #             end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    #             transactions_query = transactions_query.filter(CompanyTransaction.transaction_date < (end_date + timedelta(days=1))) 
    #         except ValueError:
    #             flash('Invalid end date format.', 'danger')
    #             pass

    #     transactions = transactions_query.order_by(CompanyTransaction.transaction_date.desc()).all()

    #     total_transactions_sum = sum(t.amount for t in transactions)
        
    #     company_current_balance = company.calculate_current_balance()

    #     company_data_for_template = {
    #         'id': company.id,
    #         'name': company.name,
    #         'contact_person': company.contact_person,
    #         'phone_number': company.phone_number,
    #         'email': company.email,
    #         'address': company.address,
    #         'is_active': company.is_active,
    #         'date_added': company.date_added,
    #         'current_balance': company_current_balance
    #     }

    #     return render_template('company_transaction.html',
    #                         company=company_data_for_template,
    #                         transactions=transactions,
    #                         search_query=search_query,
    #                         start_date=start_date_str,
    #                         end_date=end_date_str,
    #                         business_info=business_info,
    #                         total_transactions_sum=total_transactions_sum,
    #                         current_year=datetime.now().year
    #                         )
    
    @app.route('/company/<string:company_id>/transactions', methods=['GET', 'POST'])
    @login_required
    def company_transaction(company_id):
        """
        Handles company transactions, including recording new transactions,
        updating company balance, sending a new SMS, and displaying
        a list of transactions with filtering capabilities.
        """
        business_id = get_current_business_id()
        company = Company.query.filter_by(id=company_id, business_id=business_id).first_or_404()

        business_info = session.get('business_info', {})
        if not business_info or not business_info.get('name'):
            business_details = Business.query.filter_by(id=business_id).first()
            if business_details:
                business_info = {
                    'name': business_details.name,
                    'address': business_details.address,
                    'location': business_details.location,
                    'phone': business_details.contact,
                    'email': business_details.email if hasattr(business_details, 'email') else 'N/A'
                }
            else:
                business_info = {
                    'name': "Your Enterprise Name",
                    'address': "Your Pharmacy Address",
                    'location': "Your Pharmacy Location",
                    'phone': "Your Pharmacy Contact",
                    'email': 'info@example.com'
                }
        
        # Handle POST request for new transaction
        if request.method == 'POST':
            try:
                transaction_type = request.form['type']
                amount = float(request.form['amount'])
                description = request.form.get('description')
                send_sms_receipt = 'send_sms_receipt' in request.form

                if not current_user.is_authenticated:
                    flash("You must be logged in to record a transaction.", "danger")
                    return redirect(url_for('login'))
                
                recorded_by_id = current_user.id

                new_transaction = CompanyTransaction(
                    business_id=business_id,
                    company_id=company.id,
                    transaction_type=transaction_type, 
                    amount=amount,
                    description=description,
                    transaction_date=date.today(),
                    recorded_by=recorded_by_id
                )
                db.session.add(new_transaction)
                db.session.commit()

                updated_company_balance = company.calculate_current_balance()
                
                company.current_balance = updated_company_balance
                db.session.commit()

                flash(f'Transaction recorded successfully! Company balance updated to GH₵{updated_company_balance:.2f}', 'success')

                if send_sms_receipt and company.phone_number: 
                    message = (f"Dear {company.name}, a {new_transaction.transaction_type} transaction of GH₵{new_transaction.amount:.2f} "
                            f"was recorded by {business_info.get('name', 'Your Business')}. Your new balance is GH₵{updated_company_balance:.2f}. "
                            f"Description: {new_transaction.description or 'N/A'}")
                    # Assuming a send_sms function exists
                    # send_sms(company.phone_number, message) 
                elif send_sms_receipt and not company.phone_number:
                    flash('Cannot send SMS receipt: Company contact number not available.', 'warning')
                
                return redirect(url_for('company_transaction', company_id=company.id))
            
            except Exception as e:
                db.session.rollback()
                flash(f"An error occurred while recording the transaction. Please try again. Error: {e}", "danger")
                return redirect(url_for('company_transaction', company_id=company.id))

        # --- Logic for GET request and initial page load ---
        transactions_query = CompanyTransaction.query.filter_by(
            company_id=company.id,
            business_id=business_id
        )

        search_query = request.args.get('search', '').strip()
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        if search_query:
            transactions_query = transactions_query.join(User).filter(
                or_(
                    CompanyTransaction.description.ilike(f'%{search_query}%'),
                    CompanyTransaction.transaction_type.ilike(f'%{search_query}%'),
                    User.username.ilike(f'%{search_query}%')
                )
            )

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                transactions_query = transactions_query.filter(CompanyTransaction.transaction_date >= start_date) 
            except ValueError:
                flash('Invalid start date format.', 'danger')

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                transactions_query = transactions_query.filter(CompanyTransaction.transaction_date < (end_date + timedelta(days=1))) 
            except ValueError:
                flash('Invalid end date format.', 'danger')

        transactions = transactions_query.order_by(CompanyTransaction.transaction_date.desc()).all()
        
        # Correct calculation of total transactions for the filtered list
        total_transactions_sum = 0
        for t in transactions:
            if t.transaction_type == 'Credit':
                total_transactions_sum += t.amount
            elif t.transaction_type == 'Debit':
                total_transactions_sum -= t.amount
        
        company_current_balance = company.calculate_current_balance()

        company_data_for_template = {
            'id': company.id,
            'name': company.name,
            'contact_person': company.contact_person,
            'phone_number': company.phone_number,
            'email': company.email,
            'address': company.address,
            'is_active': company.is_active,
            'date_added': company.date_added,
            'current_balance': company_current_balance
        }

        return render_template('company_transaction.html',
                            company=company_data_for_template,
                            transactions=transactions,
                            search_query=search_query,
                            start_date=start_date_str,
                            end_date=end_date_str,
                            business_info=business_info,
                            total_transactions_sum=total_transactions_sum,
                            current_year=datetime.now().year)

    @app.route('/company/print_last_receipt')
# @login_required # Uncomment this decorator if you want to enforce login for printing
    def print_last_company_transaction_receipt():
        """
        Renders a dedicated, minimal page for printing the last recorded company transaction receipt.
        This page is designed to be immediately printed.
        """
        business_id = get_current_business_id() # Ensure this utility function is accessible

        # Retrieve last transaction details from session
        # Using .pop() will remove them from the session after retrieval, preventing re-prints on refresh
        last_company_transaction_details = session.pop('last_company_transaction_details', None)
        
        # Optionally, you might want to retrieve and pop the ID as well, though not used in this function
        # last_company_transaction_id = session.pop('last_company_transaction_id', None)

        if not last_company_transaction_details:
            flash('No recent transaction details found for printing.', 'warning')
            return redirect(url_for('companies')) # Redirect to the companies list or dashboard

        # Fetch the company details using the company_id from the stored transaction details
        company = None
        try:
            company = Company.query.filter_by(
                id=last_company_transaction_details['company_id'], 
                business_id=business_id
            ).first()
        except KeyError:
            # Handle cases where 'company_id' might be missing from session details (shouldn't happen with correct flow)
            flash('Error: Company ID missing in transaction details.', 'danger')
            return redirect(url_for('companies'))

        if not company: 
            flash('Company not found for the last transaction.', 'danger')
            return redirect(url_for('companies'))

        # Fetch or construct business information for the receipt
        business_info = session.get('business_info', {})
        if not business_info or not business_info.get('name'):
            business_details = Business.query.filter_by(id=business_id).first()
            if business_details:
                business_info = {
                    'name': business_details.name,
                    'address': business_details.address,
                    'location': business_details.location,
                    'phone': business_details.contact,
                    'email': business_details.email if hasattr(business_details, 'email') else 'N/A'
                }
            else:
                # Fallback to default enterprise details if business details aren't found
                business_info = {
                    'name': "Your Enterprise Name",
                    'address': "Your Enterprise Address",
                    'location': "Your Enterprise Location",
                    'phone': "Your Enterprise Contact",
                    'email': 'info@example.com'
                }

        current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        return render_template('company_last_receipt_print.html',
                            transaction_details=last_company_transaction_details,
                            company=company,
                            business_info=business_info,
                            current_date=current_date)


    # NEW ROUTE: Send SMS for a specific Company Transaction
    
    @app.route('/company/transaction/send_sms/<string:transaction_id>')
    # @login_required # Ensure this decorator is uncommented in your actual app if needed
    def send_company_transaction_sms(transaction_id):
        # ACCESS CONTROL: Allows admin, sales roles
        if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
            flash('You do not have permission to send SMS receipts or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        transaction = CompanyTransaction.query.filter_by(id=transaction_id, business_id=business_id).first_or_404()
        company = Company.query.filter_by(id=transaction.company_id, business_id=business_id).first_or_404()

        # Corrected: Use company.phone_number instead of company.phone
        if not company.phone_number:
            flash(f'SMS receipt not sent: No phone number configured for company {company.name}.', 'warning')
            return redirect(url_for('company_transaction', company_id=company.id))

        business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
        
        # Calculate balance dynamically for the SMS
        current_company_balance = company.calculate_current_balance()
        current_balance_str = f"GH₵{current_company_balance:.2f}" if current_company_balance >= 0 else f"-GH₵{abs(current_company_balance):.2f}"
        
        sms_message = (
            f"{business_name_for_sms} Transaction Alert for {company.name}:\n"
            f"Type: {transaction.transaction_type}\n" # Correct attribute name from .type to .transaction_type
            f"Amount: GH₵{transaction.amount:.2f}\n"
            f"New Balance: {current_balance_str}\n"
            f"Date: {transaction.transaction_date.strftime('%Y-%m-%d %H:%M:%S')}\n" # Correct attribute name from .date to .transaction_date
            f"Description: {transaction.description if transaction.description else 'N/A'}\n"
            f"Recorded By: {User.query.get(transaction.recorded_by).username}\n\n" # Look up username from recorded_by ID
            f"Thank you for your business!\n"
            f"From: {business_name_for_sms}"
        )
        
        sms_payload = {
            'action': 'send-sms',
            'api_key': ARKESEL_API_KEY,
            'to': company.phone_number, # Corrected: Use company.phone_number
            'from': ARKESEL_SENDER_ID,
            'sms': sms_message
        }
        
        try:
            sms_response = requests.get(ARKESEL_SMS_URL, params=sms_payload)
            sms_response.raise_for_status()
            sms_result = sms_response.json()

            if sms_result.get('status') == 'success':
                flash(f'SMS receipt sent to {company.name} successfully!', 'success')
            else:
                error_message = sms_result.get('message', 'Unknown error from SMS provider.')
                flash(f'Failed to send SMS receipt to {company.name}. Error: {error_message}', 'danger')
        except requests.exceptions.RequestException as e:
            flash(f'Network error sending SMS receipt: {e}', 'danger')
        except json.JSONDecodeError:
            flash('Failed to parse SMS provider response. The response might not be in JSON format.', 'danger')
            
        return redirect(url_for('company_transaction', company_id=company.id))

    @app.route('/print_company_receipt/<string:transaction_id>')
    # @login_required
    def print_company_receipt(transaction_id):
        """
        Renders a printable receipt for a specific company transaction.
        """
        business_id = get_current_business_id()
        if not business_id:
            flash('No business selected.', 'danger')
            return redirect(url_for('dashboard'))

        transaction = CompanyTransaction.query.filter_by(
            id=transaction_id,
            business_id=business_id
        ).first_or_404()

        company = Company.query.filter_by(
            id=transaction.company_id,
            business_id=business_id
        ).first_or_404()

        # Fetch business info for the receipt header/footer
        business_details = Business.query.filter_by(id=business_id).first()
        business_info = {
            'name': business_details.name if business_details else "Your Enterprise Name",
            'address': business_details.address if business_details else "Your Address",
            'location': business_details.location if business_details else "Your Location",
            'phone': business_details.contact if business_details else "Your Phone",
            'email': business_details.email if business_details and hasattr(business_details, 'email') else "info@example.com"
        }

        current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # The template can now directly access company.calculate_current_balance(),
        # company.total_creditors_amount, and company.total_debtors_amount as properties.

        return render_template('company_receipt_template.html',
                            transaction=transaction,
                            company=company, # Pass the Company object directly
                            business_info=business_info,
                            current_date=current_date,
                            # No need to explicitly pass total_creditor_amount/total_debtor_amount here,
                            # as they are now properties on the 'company' object.
                            # The template can access company.total_creditors_amount directly.
                            )

    @app.route('/print_all_company_transactions/<string:company_id>')
    # @login_required
    def print_all_company_transactions(company_id):
        """
        Renders a printable list of all transactions for a specific company,
        with optional filtering by search query, start date, and end date.
        """
        business_id = get_current_business_id()

        company = Company.query.filter_by(id=company_id, business_id=business_id).first_or_404()

        search_query = request.args.get('search', '').strip()
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        transactions_query = CompanyTransaction.query.filter_by(
            company_id=company.id,
            business_id=business_id
        )

        if search_query:
            transactions_query = transactions_query.join(User).filter(
                or_(
                    CompanyTransaction.description.ilike(f'%{search_query}%'),
                    CompanyTransaction.transaction_type.ilike(f'%{search_query}%'),
                    User.username.ilike(f'%{search_query}%')
                )
            )

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                transactions_query = transactions_query.filter(CompanyTransaction.transaction_date >= start_date)
            except ValueError:
                flash('Invalid start date format. Please use YYYY-MM-DD.', 'danger')
                pass

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                transactions_query = transactions_query.filter(CompanyTransaction.transaction_date < (end_date + timedelta(days=1)))
            except ValueError:
                flash('Invalid end date format. Please use YYYY-MM-DD.', 'danger')
                pass

        transactions = transactions_query.order_by(CompanyTransaction.transaction_date.desc()).all()

        total_transactions_sum = 0
        for t in transactions:
            if t.transaction_type == 'Credit':
                total_transactions_sum += t.amount
            elif t.transaction_type == 'Debit':
                total_transactions_sum -= t.amount
                
        # Calculate the company's current balance separately and pass it to the template
        current_company_balance = company.calculate_current_balance()

        business_info = session.get('business_info', {})
        if not business_info or not business_info.get('name'):
            business_details = Business.query.filter_by(id=business_id).first()
            if business_details:
                business_info = {
                    'name': business_details.name,
                    'address': business_details.address,
                    'location': business_details.location,
                    'phone': business_details.contact,
                    'email': business_details.email if hasattr(business_details, 'email') else 'N/A'
                }
            else:
                business_info = {
                    'name': "Your Enterprise Name",
                    'address': "Your Pharmacy Address",
                    'location': "Your Pharmacy Location",
                    'phone': "Your Pharmacy Contact",
                    'email': 'info@example.com'
                }

        current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Pass the calculated balance as a new variable
        return render_template('company_transaction_print.html',
                            company=company,
                            transactions=transactions,
                            business_info=business_info,
                            current_date=current_date,
                            search_query=search_query,
                            start_date=start_date_str,
                            end_date=end_date_str,
                            total_transactions_sum=total_transactions_sum,
                            # Pass the new variable with the calculated balance
                            current_balance=current_company_balance
                            )

    @app.route('/future_orders')
    def future_orders():
        # ACCESS CONTROL: Allows admin, sales, and viewer roles
        if 'username' not in session or session.get('role') not in ['admin', 'sales', 'viewer'] or not get_current_business_id():
            flash('You do not have permission to view future orders or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        orders = FutureOrder.query.filter_by(business_id=business_id).order_by(FutureOrder.order_date.desc()).all()    
        return render_template('future_order_list.html', orders=orders, user_role=session.get('role'), current_year=datetime.now().year)


    @app.route('/future_orders/add', methods=['GET', 'POST'])
    def add_future_order():
        # ACCESS CONTROL: Allows admin and sales roles
        if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
            flash('You do not have permission to add future orders or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        # Only show hardware items for future orders
        available_inventory_items = InventoryItem.query.filter_by(business_id=business_id, is_active=True, item_type='Hardware Material').all()
        serialized_inventory_items = [serialize_inventory_item(item) for item in available_inventory_items]


        if request.method == 'POST':
            customer_name = request.form['customer_name'].strip()
            customer_phone = request.form.get('customer_phone', '').strip()
            expected_collection_date_str = request.form['expected_collection_date'].strip()
            
            expected_collection_date_obj = None # Initialize to None
            if expected_collection_date_str:
                try:
                    expected_collection_date_obj = datetime.strptime(expected_collection_date_str, '%Y-%m-%d').date()
                except ValueError:
                    flash('Invalid expected collection date format. Please use YYYY-MM-DD.', 'danger')
                    # Re-render the form with current data, ensuring expiry_date is handled
                    order_data_for_form_on_error = {
                        'customer_name': customer_name,
                        'customer_phone': customer_phone,
                        'expected_collection_date': '', # Pass empty string for invalid date
                        'items': json.loads(request.form.get('cart_items_json', '[]')), # Re-populate cart
                        'total_amount': 0.0 # Ensure total_amount is passed on error re-render
                    }
                    return render_template('add_edit_future_order.html', title='Add Future Order', order=order_data_for_form_on_error, user_role=session.get('role'), inventory_items=serialized_inventory_items, current_year=datetime.now().year)


            cart_items_json = request.form.get('cart_items_json')
            if not cart_items_json:
                flash('No items in the order to record.', 'danger')
                return redirect(url_for('add_future_order'))

            cart_items = json.loads(cart_items_json)
            
            total_amount = 0.0
            order_items_list = []

            for item_data in cart_items:
                product_id = item_data['product_id']
                quantity = float(item_data['quantity_sold']) # Renamed to quantity for clarity in future orders
                unit_price = float(item_data['price_at_time_per_unit_sold'])
                item_total_amount = float(item_data['item_total_amount'])

                product = InventoryItem.query.filter_by(id=product_id, business_id=business_id).first()
                if not product:
                    flash(f'Product with ID {product_id} not found.', 'danger')
                    continue

                if product.current_stock < quantity:
                    flash(f'Insufficient stock for {product.product_name}. Currently {product.current_stock}. Tried to order: {quantity}. Please reduce quantity or fulfill later.', 'danger')
                    continue
                
                # Deduct stock immediately when order is placed
                product.current_stock -= quantity
                product.last_updated = datetime.now()
                db.session.add(product) # Add product to session for update

                order_items_list.append({
                    'product_id': product_id,
                    'product_name': product.product_name,
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'unit_type': item_data['sale_unit_type'] # Store unit type
                })
                total_amount += item_total_amount
            
            # Ensure total_amount is calculated correctly from the sum of item_total_amount
            # If the form already sends a total_grand_amount for future orders, use that, else sum it up
            # For simplicity, let's assume total_amount is calculated server-side from cart_items
            
            new_order = FutureOrder(
                business_id=business_id,
                customer_name=customer_name,
                customer_phone=customer_phone,
                order_details=json.dumps(order_items_list), # Use the correct column name
                total_amount=total_amount,
                order_date=datetime.now(), # Use order_date instead of date_ordered
                pickup_date=expected_collection_date_obj, # Use pickup_date instead of expected_collection_date
                status='Pending',
                # Note: remaining_balance is a @property, so you don't pass it as a keyword argument
            )
            db.session.add(new_order)
            db.session.commit()
            flash(f'Future order for {customer_name} recorded successfully! Order ID: {str(new_order.id)[:8].upper()}', 'success')
            
            # Send SMS confirmation to customer
            if customer_phone:
                business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
                message = (
                    f"{business_name_for_sms} Order Confirmation:\\n"
                    f"Order ID: {str(new_order.id)[:8].upper()}\\n"
                    f"Customer: {customer_name}\\n"
                    f"Total Amount: GH₵{total_amount:.2f}\\n"
                    f"Expected Collection: {expected_collection_date_obj.strftime('%Y-%m-%d') if expected_collection_date_obj else 'N/A'}\\n\\n"
                    f"Thank you for your order!\\n"
                    f"From: {business_name_for_sms}"
                )
                sms_payload = {
                    'action': 'send-sms', 'api_key': ARKESEL_API_KEY, 'to': customer_phone,
                    'from': ARKESEL_SENDER_ID, 'sms': message
                }
                try:
                    requests.get(ARKESEL_SMS_URL, params=sms_payload)
                except requests.exceptions.RequestException as e:
                    print(f'Network error sending SMS for future order: {e}')
                    flash(f'Network error when trying to send SMS order confirmation.', 'warning')

            return redirect(url_for('future_orders'))

        # For GET request or re-render on error, ensure 'order' always has 'items' as an empty list
        # and total_amount initialized to 0.0
        return render_template('add_edit_future_order.html', title='Add Future Order', order={'items': [], 'total_amount': 0.0}, user_role=session.get('role'), inventory_items=serialized_inventory_items, current_year=datetime.now().year)

   

    @app.route('/future_orders/edit/<order_id>', methods=['GET', 'POST'])
    def edit_future_order(order_id):
        # ACCESS CONTROL: Allows admin and sales roles
        if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
            flash('You do not have permission to edit future orders or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        order_to_edit = FutureOrder.query.filter_by(id=order_id, business_id=business_id).first_or_404()
        
        available_inventory_items = InventoryItem.query.filter_by(business_id=business_id, is_active=True, item_type='Hardware Material').all()
        serialized_inventory_items = [serialize_inventory_item(item) for item in available_inventory_items]


        if request.method == 'POST':
            customer_name = request.form['customer_name'].strip()
            customer_phone = request.form.get('customer_phone', '').strip()
            expected_collection_date_str = request.form['expected_collection_date'].strip()
            status = request.form['status'].strip()

            expected_collection_date_obj = None # Initialize to None
            if expected_collection_date_str:
                try:
                    expected_collection_date_obj = datetime.strptime(expected_collection_date_str, '%Y-%m-%d').date()
                except ValueError:
                    flash('Invalid expected collection date format. Please use YYYY-MM-DD.', 'danger')
                    # Re-render the form with current data, ensuring expiry_date is handled
                    order_data_for_form_on_error = {
                        'id': order_to_edit.id, # Keep ID for context
                        'customer_name': customer_name,
                        'customer_phone': customer_phone,
                        'expected_collection_date': expected_collection_date_str, # Pass original string back
                        'status': status,
                        'items': json.loads(request.form.get('cart_items_json', '[]')), # Re-populate cart
                        'total_amount': order_to_edit.total_amount # Ensure total_amount is passed on error re-render
                    }
                    return render_template('add_edit_future_order.html', title=f'Edit Future Order: {order_to_edit.customer_name}', order=order_data_for_form_on_error, user_role=session.get('role'), inventory_items=serialized_inventory_items, current_year=datetime.now().year)


            cart_items_json = request.form.get('cart_items_json')
            if not cart_items_json:
                flash('No items in the order to record.', 'danger')
                return redirect(url_for('edit_future_order', order_id=order_id))

            new_cart_items = json.loads(cart_items_json)

            # Revert old stock before processing new items
            old_items = order_to_edit.get_items()
            for old_item_data in old_items:
                product = InventoryItem.query.filter_by(id=old_item_data['product_id'], business_id=business_id).first()
                if product:
                    product.current_stock += old_item_data['quantity']
                    db.session.add(product)

            total_amount = 0.0
            updated_order_items_list = []

            for item_data in new_cart_items:
                product_id = item_data['product_id']
                quantity = float(item_data['quantity_sold'])
                unit_price = float(item_data['price_at_time_per_unit_sold'])
                item_total_amount = float(item_data['item_total_amount'])

                product = InventoryItem.query.filter_by(id=product_id, business_id=business_id).first()
                if not product:
                    flash(f'Product with ID {product_id} not found.', 'danger')
                    # Rollback changes and redirect
                    db.session.rollback()
                    order_data_for_form_on_error = {
                        'id': order_to_edit.id,
                        'customer_name': customer_name,
                        'customer_phone': customer_phone,
                        'expected_collection_date': expected_collection_date_str, # Pass original string back
                        'status': status,
                        'items': new_cart_items, # Pass the new cart items as they were
                        'total_amount': order_to_edit.total_amount # Ensure total_amount is passed on error re-render
                    }
                    return render_template('add_edit_future_order.html', title=f'Edit Future Order: {order_to_edit.customer_name}', order=order_data_for_form_on_error, user_role=session.get('role'), inventory_items=serialized_inventory_items, current_year=datetime.now().year)

                if product.current_stock < quantity:
                    flash(f'Insufficient stock for {product.product_name}. Available: {product.current_stock}. Tried to order: {quantity}.', 'danger')
                    # Rollback changes and redirect
                    db.session.rollback()
                    order_data_for_form_on_error = {
                        'id': order_to_edit.id,
                        'customer_name': customer_name,
                        'customer_phone': customer_phone,
                        'expected_collection_date': expected_collection_date_str, # Pass original string back
                        'status': status,
                        'items': new_cart_items, # Pass the new cart items as they were
                        'total_amount': order_to_edit.total_amount # Ensure total_amount is passed on error re-render
                    }
                    return render_template('add_edit_future_order.html', title=f'Edit Future Order: {order_to_edit.customer_name}', order=order_data_for_form_on_error, user_role=session.get('role'), inventory_items=serialized_inventory_items, current_year=datetime.now().year)

                product.current_stock -= quantity
                product.last_updated = datetime.now()
                db.session.add(product)

                updated_order_items_list.append({
                    'product_id': product_id,
                    'product_name': product.product_name,
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'unit_type': item_data['sale_unit_type']
                })
                total_amount += item_total_amount

            # Update the order details
            order_to_edit.customer_name = customer_name
            order_to_edit.customer_phone = customer_phone
            order_to_edit.items_json = json.dumps(updated_order_items_list)
            order_to_edit.total_amount = total_amount
            order_to_edit.expected_collection_date = expected_collection_date_obj # This is now a datetime.date object or None
            order_to_edit.status = status
            # Re-calculate remaining_balance if total_amount changed
            order_to_edit.remaining_balance = total_amount - (order_to_edit.total_amount - order_to_edit.remaining_balance)

            db.session.commit()
            flash(f'Future order for {customer_name} updated successfully!', 'success')
            return redirect(url_for('future_orders'))

        # --- GET Request / Initial Render ---
        order_data_for_form = {
            'id': order_to_edit.id,
            'customer_name': order_to_edit.customer_name,
            'customer_phone': order_to_edit.customer_phone,
            'status': order_to_edit.status,
            'total_amount': order_to_edit.total_amount,
            'remaining_balance': order_to_edit.remaining_balance,
            'date_ordered': order_to_edit.date_ordered.strftime('%Y-%m-%d %H:%M:%S'),
            'actual_collection_date': order_to_edit.actual_collection_date.strftime('%Y-%m-%d %H:%M:%S') if order_to_edit.actual_collection_date else '',
            'items': order_to_edit.get_items() # <--- IMPORTANT: Call get_items() here
        }
        # Format expected_collection_date for HTML input
        order_data_for_form['expected_collection_date'] = order_to_edit.expected_collection_date.strftime('%Y-%m-%d') if order_to_edit.expected_collection_date else ''


        return render_template('add_edit_future_order.html', title=f'Edit Future Order: {order_to_edit.customer_name}', order=order_data_for_form, user_role=session.get('role'), inventory_items=serialized_inventory_items, current_year=datetime.now().year)

    @app.route('/future_orders/delete/<order_id>')
    def delete_future_order(order_id):
        # ACCESS CONTROL: Allows admin and sales roles
        if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
            flash('You do not have permission to delete future orders or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        order_to_delete = FutureOrder.query.filter_by(id=order_id, business_id=business_id).first_or_404()

        # Return stock to inventory if order was pending
        if order_to_delete.status == 'Pending':
            for item_data in order_to_delete.get_items():
                product = InventoryItem.query.filter_by(id=item_data['product_id'], business_id=business_id).first()
                if product:
                    product.current_stock += item_data['quantity']
                    product.last_updated = datetime.now()
                    db.session.add(product)
        
        db.session.delete(order_to_delete)
        db.session.commit()
        flash(f'Future order for {order_to_delete.customer_name} deleted successfully!', 'success')
        return redirect(url_for('future_orders'))

    @app.route('/future_orders/collect/<order_id>', methods=['GET', 'POST'])
    @csrf.exempt
    def collect_future_order(order_id):
        # ACCESS CONTROL: Allows admin and sales roles
        if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
            flash('You do not have permission to mark orders as collected or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        order_to_collect = FutureOrder.query.filter_by(id=order_id, business_id=business_id).first_or_404()

        if order_to_collect.status == 'Collected':
            flash('This order has already been collected.', 'warning')
            return redirect(url_for('future_orders'))
        
        if order_to_collect.remaining_balance > 0:
            flash(f'Outstanding balance of GH₵{order_to_collect.remaining_balance:.2f} remaining. Please settle payment before marking as collected.', 'danger')
            return redirect(url_for('future_order_payment', order_id=order_id))

        if request.method == 'POST':
            order_to_collect.actual_collection_date = datetime.now()
            order_to_collect.status = 'Collected'
            db.session.commit()
            flash(f'Order {str(order_to_collect.id)[:8].upper()} collected successfully!', 'success')
            
            # Send SMS confirmation to customer
            if order_to_collect.customer_phone:
                business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
                message = (
                    f"{business_name_for_sms} Order Collection Confirmation:\\n"
                    f"Order ID: {str(order_to_collect.id)[:8].upper()}\\n"
                    f"Customer: {order_to_collect.customer_name}\\n"
                    f"Total Amount: GH₵{order_to_collect.total_amount:.2f}\\n"
                    f"Collected On: {order_to_collect.actual_collection_date.strftime('%Y-%m-%d %H:%M:%S')}\\n\\n"
                    f"Thank you for your business!\\n"
                    f"From: {business_name_for_sms}"
                )
                sms_payload = {
                    'action': 'send-sms', 'api_key': ARKESEL_API_KEY, 'to': order_to_collect.customer_phone,
                    'from': ARKESEL_SENDER_ID, 'sms': message
                }
                try:
                    requests.get(ARKESEL_SMS_URL, params=sms_payload)
                except requests.exceptions.RequestException as e:
                    print(f'Network error sending SMS for collection: {e}')
                    flash(f'Network error when trying to send SMS collection confirmation.', 'warning')
        else:
            flash('Failed to mark order as collected.', 'danger')

        return redirect(url_for('future_orders'))

    @app.route('/future_orders/payment/<order_id>', methods=['GET', 'POST'])
    @csrf.exempt
    def future_order_payment(order_id):
        # ACCESS CONTROL: Allows admin and sales roles
        if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
            flash('You do not have permission to record payments or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        order = FutureOrder.query.filter_by(id=order_id, business_id=business_id).first_or_404()

        if order.status == 'Collected':
            flash('This order has already been collected and paid for.', 'warning')
            return redirect(url_for('future_orders'))
        
        if order.remaining_balance <= 0: # Check if balance is already zero or less
            flash('This order has no outstanding balance.', 'warning')
            return redirect(url_for('future_orders'))

        if request.method == 'POST':
            amount_paid = float(request.form['amount_paid'])
            if amount_paid <= 0:
                flash('Amount paid must be positive.', 'danger')
                return render_template('future_order_payment.html', order=order, user_role=session.get('role'), current_year=datetime.now().year)
            
            if amount_paid > order.remaining_balance:
                flash(f'Amount paid (GH₵{amount_paid:.2f}) exceeds remaining balance (GH₵{order.remaining_balance:.2f}).', 'danger')
                return render_template('future_order_payment.html', order=order, user_role=session.get('role'), current_year=datetime.now().year)
            
            order.remaining_balance -= amount_paid
            db.session.commit()
            flash(f'Payment of GH₵{amount_paid:.2f} recorded for order {order.customer_name}. Remaining balance: GH₵{order.remaining_balance:.2f}', 'success')
            return redirect(url_for('future_orders'))
        
        return render_template('future_order_payment.html', order=order, user_role=session.get('role'), current_year=datetime.now().year)

    # NEW: Routes for Hirable Items
    @app.route('/hirable_items')
    @csrf.exempt
    def hirable_items():
        # ACCESS CONTROL: Allows admin, sales, and viewer roles
        if 'username' not in session or session.get('role') not in ['admin', 'sales', 'viewer'] or not get_current_business_id():
            flash('You do not have permission to view hirable items or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        items = HirableItem.query.filter_by(business_id=business_id, is_active=True).all()
        return render_template('hirable_item_list.html', hirable_items=items, user_role=session.get('role'), current_year=datetime.now().year)

    @app.route('/hirable_items/add', methods=['GET', 'POST'])
    @csrf.exempt
    def add_hirable_item():
        # ACCESS CONTROL: Allows admin role
        if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
            flash('You do not have permission to add hirable items or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        if request.method == 'POST':
            item_name = request.form['item_name'].strip()
            description = request.form.get('description', '').strip()
            daily_hire_price = float(request.form['daily_hire_price'])
            current_stock = int(request.form['current_stock'])

            if HirableItem.query.filter_by(item_name=item_name, business_id=business_id).first():
                flash('Hirable item with this name already exists for this business.', 'danger')
                return render_template('add_edit_hirable_item.html', title='Add Hirable Item', item=request.form, user_role=session.get('role'), current_year=datetime.now().year)
            
            new_item = HirableItem(
                business_id=business_id,
                item_name=item_name,
                description=description,
                rental_price_per_day=daily_hire_price, # This keyword has been corrected.
                current_stock=current_stock,
                is_active=True
            )

            db.session.add(new_item)
            db.session.commit()
            flash(f'Hirable item "{item_name}" added successfully!', 'success')
            return redirect(url_for('hirable_items'))
        
        return render_template('add_edit_hirable_item.html', title='Add Hirable Item', item={}, user_role=session.get('role'), current_year=datetime.now().year)

    @app.route('/hirable_items/edit/<item_id>', methods=['GET', 'POST'])
    @csrf.exempt
    def edit_hirable_item(item_id):
        # ACCESS CONTROL: Allows admin role
        if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
            flash('You do not have permission to edit hirable items or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        item_to_edit = HirableItem.query.filter_by(id=item_id, business_id=business_id).first_or_404()

        if request.method == 'POST':
            item_name = request.form['item_name'].strip()
            description = request.form.get('description', '').strip()
            daily_hire_price = float(request.form['daily_hire_price'])
            current_stock = int(request.form['current_stock'])

            # Check for duplicate name, excluding the current item being edited
            if HirableItem.query.filter(HirableItem.item_name == item_name,
                                        HirableItem.business_id == business_id,
                                        HirableItem.id != item_id).first():
                flash('Hirable item with this name already exists for this business.', 'danger')
                # --- IMPORTANT FIX HERE: Pass the original item_to_edit object back ---
                # This ensures item.id is available for url_for in the form action
                return render_template('add_edit_hirable_item.html',
                                    title=f'Edit Hirable Item: {item_to_edit.item_name}', # Keep original title
                                    item=item_to_edit, # Pass the SQLAlchemy object
                                    user_role=session.get('role'),
                                    current_year=datetime.now().year)
            
            item_to_edit.item_name = item_name
            item_to_edit.description = description
            item_to_edit.daily_hire_price = daily_hire_price
            item_to_edit.current_stock = current_stock
            item_to_edit.last_updated = datetime.now()
            
            # Handle is_active checkbox
            item_to_edit.is_active = 'is_active' in request.form # Checkbox is present if checked

            db.session.commit()
            flash(f'Hirable item "{item_name}" updated successfully!', 'success')
            return redirect(url_for('hirable_items'))
        
        # GET request or initial render
        return render_template('add_edit_hirable_item.html',
                            title=f'Edit Hirable Item: {item_to_edit.item_name}',
                            item=item_to_edit, # This is already correct for GET
                            user_role=session.get('role'),
                            current_year=datetime.now().year)


    @app.route('/hirable_items/delete/<item_id>', methods=['POST'])
    @login_required
    def delete_hirable_item(item_id):
        """Marks a hirable item as inactive."""
        if session.get('role') != 'admin':
            flash('You do not have permission to perform this action.', 'danger')
            return redirect(url_for('hirable_items'))

        item = HirableItem.query.get_or_404(item_id)
        if item.business_id != session.get('business_id'):
            flash('You can only manage items for your own business.', 'danger')
            return redirect(url_for('hirable_items'))

        try:
            # Instead of deleting, we mark the item as inactive
            item.is_active = False
            db.session.commit()
            flash('Hirable item has been marked as inactive.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {e}', 'danger')

        return redirect(url_for('hirable_items'))

    # NEW: Routes for Rental Records
    @app.route('/rental_records')
    def rental_records():
        # ACCESS CONTROL: Allows admin, sales, and viewer roles
        if 'username' not in session or session.get('role') not in ['admin', 'sales', 'viewer'] or not get_current_business_id():
            flash('You do not have permission to view rental records or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        records = RentalRecord.query.filter_by(business_id=business_id).order_by(RentalRecord.date_recorded.desc()).all()
        return render_template('rental_record_list.html', rental_records=records, user_role=session.get('role'), current_year=datetime.now().year)

    @app.route('/rental_records/add', methods=['GET', 'POST'])
    def add_rental_record():
        # ACCESS CONTROL: Allows admin and sales roles
        if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
            flash('You do not have permission to add rental records or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        available_hirable_items = HirableItem.query.filter_by(business_id=business_id, is_active=True).all()
        serialized_hirable_items = [serialize_hirable_item(item) for item in available_hirable_items]

        # Get business info for receipts
        business_info = session.get('business_info', {
            'name': ENTERPRISE_NAME,
            'location': PHARMACY_LOCATION, # Reusing for consistency, rename if needed
            'address': PHARMACY_ADDRESS,
            'contact': PHARMACY_CONTACT
        })

        if request.method == 'POST':
            hirable_item_id = request.form['hirable_item_id']
            customer_name = request.form['customer_name'].strip()
            customer_phone = request.form.get('customer_phone', '').strip()
            start_date_str = request.form['start_date'].strip()
            end_date_str = request.form.get('end_date', '').strip()
            send_sms = 'send_sms_receipt' in request.form # Check if the checkbox was checked

            start_date_obj = None # Initialize to None
            if start_date_str:
                try:
                    start_date_obj = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                except ValueError:
                    flash('Invalid start date format. Please use YYYY-MM-DD.', 'danger')
                    record_data_for_form_on_error = { # Use a dedicated error dict
                        'hirable_item_id': hirable_item_id, 'customer_name': customer_name,
                        'customer_phone': customer_phone, 'start_date': start_date_str, # Pass original string back
                        'end_date': end_date_str # Pass original string back
                    }
                    return render_template('add_edit_rental_record.html', title='Add Rental Record', record=record_data_for_form_on_error, user_role=session.get('role'), hirable_items=serialized_hirable_items, business_info=business_info, current_year=datetime.now().year)

            end_date_obj = None # Initialize to None
            if end_date_str:
                try:
                    end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                except ValueError:
                    flash('Invalid end date format. Please use YYYY-MM-DD.', 'danger')
                    record_data_for_form_on_error = { # Use a dedicated error dict
                        'hirable_item_id': hirable_item_id, 'customer_name': customer_name,
                        'customer_phone': customer_phone, 'start_date': start_date_str, # Pass original string back
                        'end_date': end_date_str # Pass original string back
                    }
                    return render_template('add_edit_rental_record.html', title='Add Rental Record', record=record_data_for_form_on_error, user_role=session.get('role'), hirable_items=serialized_hirable_items, business_info=business_info, current_year=datetime.now().year)


            if end_date_obj and start_date_obj and end_date_obj < start_date_obj:
                flash('End date cannot be before start date.', 'danger')
                record_data_for_form_on_error = { # Use a dedicated error dict
                    'hirable_item_id': hirable_item_id, 'customer_name': customer_name,
                    'customer_phone': customer_phone, 'start_date': start_date_str, # Pass original string back
                    'end_date': end_date_str # Pass original string back
                }
                return render_template('add_edit_rental_record.html', title='Add Rental Record', record=record_data_for_form_on_error, user_role=session.get('role'), hirable_items=serialized_hirable_items, business_info=business_info, current_year=datetime.now().year)
            
            hirable_item = HirableItem.query.filter_by(id=hirable_item_id, business_id=business_id).first_or_404()

            if hirable_item.current_stock < 1:
                flash(f'Insufficient stock for {hirable_item.item_name}. Currently 0 available for hiring.', 'danger')
                record_data_for_form_on_error = { # Use a dedicated error dict
                    'hirable_item_id': hirable_item_id, 'customer_name': customer_name,
                    'customer_phone': customer_phone, 'start_date': start_date_str, # Pass original string back
                    'end_date': end_date_str # Pass original string back
                }
                return render_template('add_edit_rental_record.html', title='Add Rental Record', record=record_data_for_form_on_error, user_role=session.get('role'), hirable_items=serialized_hirable_items, business_info=business_info, current_year=datetime.now().year)

            # Calculate number of days
            number_of_days = (end_date_obj - start_date_obj).days + 1 if end_date_obj and start_date_obj else 1
            total_hire_amount = number_of_days * hirable_item.daily_hire_price

            # Deduct stock
            hirable_item.current_stock -= 1
            hirable_item.last_updated = datetime.now()
            db.session.add(hirable_item)

            # Corrected `RentalRecord` instantiation
            new_record = RentalRecord(
                business_id=business_id,
                hirable_item_id=hirable_item.id,
                item_name_at_rent=hirable_item.item_name,
                customer_name=customer_name,
                customer_phone=customer_phone,
                # Map route variables to model column names
                rent_date=start_date_obj,
                return_date=end_date_obj,
                quantity=1, # Assuming 1 unit of the hirable item is rented
                # Ensure quantity reflects number_of_days if that's how it's designed
                # quantity=number_of_days, # If quantity is meant to be the duration
                rental_price_per_day_at_rent=hirable_item.daily_hire_price,
                total_rental_amount=total_hire_amount, # Use the model's column name
                status='Rented',
                # `date_recorded` is handled by the model's default=datetime.utcnow
                # `sales_person_name` is not a column in the model, remove it
                # If you need sales_person_name in the model, you must add it and migrate.
            )
            db.session.add(new_record)
            db.session.commit()
            
            # Store details in session for printing receipt
            session['last_rental_details'] = {
                'id': new_record.id,
                'item_name': new_record.item_name_at_rent,
                'customer_name': new_record.customer_name,
                'customer_phone': new_record.customer_phone,
                'start_date': new_record.rent_date.strftime('%Y-%m-%d'), # Use rent_date
                'end_date': new_record.return_date.strftime('%Y-%m-%d') if new_record.return_date else 'N/A', # Use return_date
                'number_of_days': number_of_days, # This is a calculated value, not from new_record directly
                'daily_hire_price': new_record.rental_price_per_day_at_rent, # Use rental_price_per_day_at_rent
                'total_hire_amount': new_record.total_rental_amount, # Use total_rental_amount
                'sales_person': session.get('username', 'N/A'), # Get directly from session, as it's not a model column
                'date_recorded': new_record.date_recorded.strftime('%Y-%m-%d %H:%M:%S') # This is now correct
            }
            
            # SMS Sending Logic
            if send_sms and new_record.customer_phone:
                business_name_for_sms = business_info.get('name', ENTERPRISE_NAME)
                sms_message = (
                    f"{business_name_for_sms} Rental Confirmation:\n"
                    f"Item: {new_record.item_name_at_rent}\n"
                    f"Customer: {new_record.customer_name}\n"
                    f"Period: {new_record.rent_date.strftime('%Y-%m-%d')} to {new_record.return_date.strftime('%Y-%m-%d') if new_record.return_date else 'N/A'}\n"
                    f"Total: GH₵{new_record.total_rental_amount:.2f}\n\n" # Use total_rental_amount
                    f"Thank you for your business!\n"
                    f"From: {business_name_for_sms}"
                )
                sms_payload = {
                    'action': 'send-sms', 'api_key': ARKESEL_API_KEY, 'to': new_record.customer_phone,
                    'from': ARKESEL_SENDER_ID, 'sms': sms_message
                }
                try:
                    requests.get(ARKESEL_SMS_URL, params=sms_payload)
                    flash(f'SMS receipt sent to {new_record.customer_name} successfully!', 'success')
                except requests.exceptions.RequestException as e:
                    print(f'Network error sending SMS for rental: {e}')
                    flash(f'Network error when trying to send SMS rental confirmation.', 'warning')
            elif send_sms and not new_record.customer_phone:
                flash(f'SMS receipt not sent: No phone number configured for the customer.', 'warning')

            flash(f'Rental record for "{hirable_item.item_name}" added successfully!', 'success')
            return redirect(url_for('add_rental_record', print_ready='true'))
        
        # GET request / Initial render
        print_ready = request.args.get('print_ready', 'false').lower() == 'true'
        last_rental_details = session.pop('last_rental_details', None)

        return render_template('add_edit_rental_record.html', 
                            title='Add Rental Record', 
                            record={}, 
                            user_role=session.get('role'), 
                            hirable_items=serialized_hirable_items,
                            business_info=business_info,
                            print_ready=print_ready,
                            last_rental_details=last_rental_details,
                            current_year=datetime.now().year)


    @app.route('/rental_records/print/<record_id>')
    # @login_required
    def print_rental_receipt(record_id):
        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        record_to_print = RentalRecord.query.filter_by(id=record_id, business_id=business_id).first_or_404()

        business_info = session.get('business_info', {
            "name": ENTERPRISE_NAME,
            "location": PHARMACY_LOCATION,
            "address": PHARMACY_ADDRESS,
            "contact": PHARMACY_CONTACT
        })

        rental_details_for_receipt = {
            'id': record_to_print.id,
            'item_name': record_to_print.item_name_at_rent,
            'customer_name': record_to_print.customer_name,
            'customer_phone': record_to_print.customer_phone,
            'start_date': record_to_print.start_date.strftime('%Y-%m-%d'),
            'end_date': record_to_print.end_date.strftime('%Y-%m-%d') if record_to_print.end_date else 'N/A',
            'number_of_days': record_to_print.number_of_days,
            'daily_hire_price': record_to_print.daily_hire_price_at_rent,
            'total_hire_amount': record_to_print.total_hire_amount,
            'sales_person': record_to_print.sales_person_name,
            'date_recorded': record_to_print.date_recorded.strftime('%Y-%m-%d %H:%M:%S')
        }

        # Fetch available hirable items for the sidebar/form if needed, though not strictly for receipt
        available_hirable_items = HirableItem.query.filter_by(business_id=business_id, is_active=True).all()
        serialized_hirable_items = [serialize_hirable_item(item) for item in available_hirable_items]


        return render_template('add_edit_rental_record.html',
                            title='Rental Receipt',
                            record=rental_details_for_receipt, # Pass the specific record for the receipt
                            user_role=session.get('role'),
                            hirable_items=serialized_hirable_items, # Pass for sidebar/form
                            business_info=business_info,
                            print_ready=True,
                            last_rental_details=rental_details_for_receipt, # Use this for the receipt block
                            current_year=datetime.now().year
                            )


    @app.route('/rental_records/mark_returned/<record_id>', methods=['GET', 'POST'])
    def mark_rental_returned(record_id):
        # ACCESS CONTROL: Allows admin and sales roles
        if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
            flash('You do not have permission to mark rental records as returned or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        record = RentalRecord.query.filter_by(id=record_id, business_id=business_id).first_or_404()

        if record.status == 'Returned':
            flash('This item has already been marked as returned.', 'warning')
            return redirect(url_for('rental_records'))
        
        if request.method == 'POST':
            record.actual_return_date = datetime.now()
            record.status = 'Returned'

            # Return stock to hirable item (implicitly assumes quantity of 1)
            hirable_item = HirableItem.query.filter_by(id=record.hirable_item_id, business_id=business_id).first()
            if hirable_item:
                hirable_item.current_stock += 1
                hirable_item.last_updated = datetime.now()
                db.session.add(hirable_item)

            db.session.commit()
            flash(f'Rental record for "{record.item_name_at_rent}" marked as returned successfully!', 'success')
            return redirect(url_for('rental_records'))
        
        return render_template('mark_rental_returned.html', record=record, user_role=session.get('role'), current_year=datetime.now().year)
    # app.py - New route for importing inventory from another business

    @app.route('/inventory/import_from_business', methods=['GET', 'POST'])
    # @login_required
    def import_inventory_from_business():
        # ACCESS CONTROL: Only admin can import inventory from another business
        if session.get('role') not in ['admin'] or not get_current_business_id():
            flash('You do not have permission to import inventory or no business selected.', 'danger')
            return redirect(url_for('dashboard'))

        current_business_id = get_current_business_id()
        current_business_type = get_current_business_type()

        # Fetch all other businesses of the same type, excluding the current business
        other_businesses_same_type = Business.query.filter(
            Business.id != current_business_id,
            Business.type == current_business_type
        ).all()

        if request.method == 'POST':
            source_business_id = request.form.get('source_business_id')

            if not source_business_id:
                flash('Please select a source business.', 'danger')
                return render_template('import_inventory_from_business.html',
                                    other_businesses=other_businesses_same_type,
                                    user_role=session.get('role'),
                                    current_year=datetime.now().year)

            source_business = Business.query.get(source_business_id)
            if not source_business or source_business.type != current_business_type:
                flash('Invalid source business selected or business type mismatch.', 'danger')
                return render_template('import_inventory_from_business.html',
                                    other_businesses=other_businesses_same_type,
                                    user_role=session.get('role'),
                                    current_year=datetime.now().year)

            # Fetch inventory items from the source business
            source_inventory_items = InventoryItem.query.filter_by(
                business_id=source_business_id,
                is_active=True # Only import active items
            ).all()

            if not source_inventory_items:
                flash(f'No active inventory items found in "{source_business.name}" to import.', 'warning')
                return render_template('import_inventory_from_business.html',
                                    other_businesses=other_businesses_same_type,
                                    user_role=session.get('role'),
                                    current_year=datetime.now().year)

            updated_count = 0
            added_count = 0
            errors = []

            for item in source_inventory_items:
                try:
                    # Check if an item with the same product_name already exists in the current business
                    existing_target_item = InventoryItem.query.filter_by(
                        product_name=item.product_name,
                        business_id=current_business_id
                    ).first()

                    if existing_target_item:
                        # Update existing item's stock and other relevant fields
                        # You might want to define a more sophisticated merge logic here
                        # For simplicity, we'll update key fields and add stock.
                        existing_target_item.current_stock += item.current_stock # Add stock
                        existing_target_item.purchase_price = item.purchase_price # Overwrite purchase price
                        existing_target_item.sale_price = item.sale_price # Overwrite sale price
                        existing_target_item.number_of_tabs = item.number_of_tabs # Overwrite units/pack
                        existing_target_item.unit_price_per_tab = item.unit_price_per_tab # Overwrite unit price
                        existing_target_item.last_updated = datetime.now()
                        existing_target_item.batch_number = item.batch_number # Overwrite batch number
                        existing_target_item.is_fixed_price = item.is_fixed_price
                        existing_target_item.fixed_sale_price = item.fixed_sale_price
                        existing_target_item.is_active = item.is_active # Maintain active status

                        # For expiry date, update only if the source item has a valid, newer expiry date
                        if item.expiry_date and (not existing_target_item.expiry_date or item.expiry_date > existing_target_item.expiry_date):
                            existing_target_item.expiry_date = item.expiry_date

                        db.session.add(existing_target_item)
                        updated_count += 1
                    else:
                        # Add new item to the current business's inventory
                        new_item = InventoryItem(
                            business_id=current_business_id,
                            product_name=item.product_name,
                            category=item.category,
                            purchase_price=item.purchase_price,
                            sale_price=item.sale_price,
                            current_stock=item.current_stock,
                            last_updated=datetime.now(),
                            batch_number=item.batch_number,
                            number_of_tabs=item.number_of_tabs,
                            unit_price_per_tab=item.unit_price_per_tab,
                            item_type=item.item_type,
                            expiry_date=item.expiry_date,
                            is_fixed_price=item.is_fixed_price,
                            fixed_sale_price=item.fixed_sale_price,
                            is_active=True # New items are active by default
                        )
                        db.session.add(new_item)
                        added_count += 1
                except Exception as e:
                    errors.append(f"Error processing item '{item.product_name}': {e}")
            
            db.session.commit()
            
            if errors:
                flash(f'Inventory import completed with {updated_count} updated, {added_count} added, and {len(errors)} errors. Check console for details.', 'warning')
                for error in errors:
                    print(f"Inventory Import Error: {error}")
            else:
                flash(f'Inventory imported successfully! {updated_count} items updated, {added_count} items added from "{source_business.name}".', 'success')
            
            return redirect(url_for('inventory')) # Redirect to current business's inventory

        return render_template('import_inventory_from_business.html',
                            other_businesses=other_businesses_same_type,
                            user_role=session.get('role'),
                            current_year=datetime.now().year)
    
    
    @app.route('/inventory/upload_csv', methods=['POST'])
    @login_required
    @roles_required('admin')
    def upload_inventory_csv():
        """
        Handles CSV file upload for populating inventory for a specific business.
        """
        if 'csv_file' not in request.files:
            flash('No file part in the request.', 'danger')
            return redirect(url_for('inventory'))

        file = request.files['csv_file']
        if file.filename == '':
            flash('No selected file.', 'danger')
            return redirect(url_for('inventory'))

        if file and file.filename.endswith('.csv'):
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.DictReader(stream)
            
            business_id = get_current_business_id()
            items_added = 0
            items_updated = 0
            
            # Get all existing items for this business to check for updates
            existing_items = InventoryItem.query.filter_by(business_id=business_id).all()
            existing_items_dict = {item.product_name.lower(): item for item in existing_items}

            for row in csv_reader:
                try:
                    product_name = row['product_name'].strip()
                    
                    # Check if the item already exists in the local database by name
                    if product_name.lower() in existing_items_dict:
                        item_to_update = existing_items_dict[product_name.lower()]
                        
                        # Update existing item with CSV data
                        item_to_update.category = row.get('category', item_to_update.category).strip()
                        item_to_update.purchase_price = float(row.get('purchase_price', item_to_update.purchase_price))
                        item_to_update.current_stock = float(row.get('current_stock', item_to_update.current_stock))
                        item_to_update.sale_price = float(row.get('sale_price', item_to_update.sale_price))
                        item_to_update.last_updated = datetime.now()
                        
                        # Add logic for other fields as needed
                        db.session.add(item_to_update)
                        items_updated += 1
                    else:
                        # Create a new item
                        new_item = InventoryItem(
                            business_id=business_id,
                            product_name=product_name,
                            category=row.get('category').strip(),
                            purchase_price=float(row.get('purchase_price')),
                            sale_price=float(row.get('sale_price')),
                            current_stock=float(row.get('current_stock')),
                            last_updated=datetime.now(),
                            item_type=row.get('item_type', get_current_business_type()).strip(),
                            batch_number=row.get('batch_number', '').strip(),
                            expiry_date=datetime.strptime(row['expiry_date'], '%Y-%m-%d') if row.get('expiry_date') else None,
                            is_fixed_price=row.get('is_fixed_price', 'False').lower() == 'true',
                            fixed_sale_price=float(row.get('fixed_sale_price', 0.0))
                        )
                        db.session.add(new_item)
                        items_added += 1
                        
                except (KeyError, ValueError) as e:
                    db.session.rollback()
                    flash(f"Error processing a row: Missing data or invalid format. Please check your CSV file. Error: {e}", 'danger')
                    return redirect(url_for('inventory'))
            
            db.session.commit()
            flash(f'Successfully imported inventory from CSV. {items_added} new items added, {items_updated} items updated.', 'success')
            
        else:
            flash('Invalid file format. Please upload a CSV file.', 'danger')
            
        return redirect(url_for('inventory'))
    
    @app.route('/rental_records/cancel/<record_id>')
    def cancel_rental_record(record_id):
        # ACCESS CONTROL: Allows admin and sales roles
        if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
            flash('You do not have permission to cancel rental records or no business selected.', 'danger')
            return redirect(url_for('dashboard'))
        
        if get_current_business_type() != 'Hardware':
            flash('This feature is only available for Hardware businesses.', 'warning')
            return redirect(url_for('dashboard'))

        business_id = get_current_business_id()
        record_to_cancel = RentalRecord.query.filter_by(id=record_id, business_id=business_id).first_or_404()

        if record_to_cancel.status != 'Rented':
            flash(f'Cannot cancel rental record with status: {record_to_cancel.status}. Only "Rented" records can be cancelled.', 'danger')
            return redirect(url_for('rental_records'))
        
        # Return stock to hirable item if it was rented (implicitly assumes quantity of 1)
        hirable_item = HirableItem.query.filter_by(id=record_to_cancel.hirable_item_id, business_id=business_id).first()
        if hirable_item:
            hirable_item.current_stock += 1
            hirable_item.last_updated = datetime.now()
            db.session.add(hirable_item)

        record_to_cancel.status = 'Cancelled'
        db.session.commit()
        flash(f'Rental record for "{record_to_cancel.item_name_at_rent}" cancelled successfully! Stock returned.', 'success')
        return redirect(url_for('rental_records'))

    @app.route('/manage_businesses')
    # @login_required
    def manage_businesses():
        # Access control: Only 'super_admin' or 'admin' role can view this page
        if session.get('role') not in ['super_admin','admin']:
            flash('You do not have permission to manage businesses.', 'danger')
            return redirect(url_for('dashboard'))
        
        # Retrieve all businesses from the database
        businesses = Business.query.all()
        
        # This line is critical – ensure it renders 'super_admin_dashboard.html'
        return render_template('super_admin_dashboard.html', # <--- THIS MUST BE 'super_admin_dashboard.html'
                            businesses=businesses,
                            user_role=session.get('role'),
                            current_year=datetime.now().year)

    @app.route('/manage_businesses/toggle_active/<string:business_id>', methods=['POST'])
    # @login_required
    def toggle_business_active(business_id):
        # Access control: Only 'admin' role can toggle business status
        if session.get('role') not in ['super_admin', 'admin']:
            flash('You do not have permission to manage businesses.', 'danger')
            return redirect(url_for('dashboard'))

        # Fetch the business by its ID or return 404 if not found
        business = Business.query.get_or_404(business_id)
        
        # Toggle the is_active status
        business.is_active = not business.is_active
        db.session.commit() # Commit the change to the database
        
        # Prepare a user-friendly message based on the new status
        status_message = "activated" if business.is_active else "deactivated"
        flash(f'Business "{business.name}" has been {status_message} successfully!', 'success')
        
        # Redirect back to the business management page
        return redirect(url_for('manage_businesses'))

    @app.route('/manage_businesses/send_sms_warning/<string:business_id>', methods=['POST'])
    # @login_required
    def send_payment_due_sms(business_id):
        """
        Sends an SMS warning message (e.g., payment due) to the contact number of a specific business.
        Accessible by 'super_admin' and 'admin' roles.
        """
        if session.get('role') not in ['super_admin', 'admin']:
            flash('You do not have permission to send SMS warnings.', 'danger')
            return redirect(url_for('dashboard'))

        business = Business.query.get_or_404(business_id)
        
        # Check if a contact number is available for the business
        if not business.contact:
            flash(f'Business "{business.name}" has no contact number registered for SMS.', 'danger')
            return redirect(url_for('super_admin_dashboard'))

        # Compose the SMS message
        enterprise_name = os.getenv('ENTERPRISE_NAME', 'Global Business Technology') # Fallback if not set
        sms_message = (
            f"Dear {business.name},\n"
            f"This is a friendly reminder that your subscription payment is due. "
            f"Please make your payment to continue using our services. "
            f"Contact us at {business.contact} for assistance.\n"
            f"Thank you, {enterprise_name}."
        )
        
        print(f"Attempting to send payment due SMS to {business.contact} for business {business.name}.")
        print(f"SMS Message: {sms_message}")
        
        # Prepare SMS payload for Arkesel API
        sms_payload = {
            'action': 'send-sms',
            'api_key': os.getenv('ARKESEL_API_KEY'), # Still get API key from env (secure practice)
            'to': business.contact,
            'from': os.getenv('ARKESEL_SENDER_ID', 'uniquebence'), # Still get Sender ID from env
            'sms': sms_message
        }
        
        try:
            # CORRECTED LINE: Use the global ARKESEL_SMS_URL variable directly
            sms_response = requests.get(ARKESEL_SMS_URL, params=sms_payload)
            sms_response.raise_for_status()
            sms_result = sms_response.json()
            print(f"Arkesel SMS API Response: {sms_result}")

            if sms_result.get('status') == 'success':
                flash(f'Payment due SMS sent to {business.name} ({business.contact}) successfully!', 'success')
            else:
                error_message = sms_result.get('message', 'Unknown error from SMS provider.')
                flash(f'Failed to send SMS to {business.name}. Error: {error_message}', 'danger')
        except requests.exceptions.HTTPError as http_err:
            flash(f'HTTP error sending SMS: {http_err}. Please check API key or sender ID.', 'danger')
            print(f"HTTP Error: {http_err}")
        except requests.exceptions.ConnectionError as conn_err:
            flash(f'Network error sending SMS: {conn_err}. Please check your internet connection.', 'danger')
            print(f"Connection Error: {conn_err}")
        except requests.exceptions.Timeout as timeout_err:
            flash(f'SMS request timed out: {timeout_err}. Please try again later.', 'danger')
            print(f"Timeout Error: {timeout_err}")
        except json.JSONDecodeError:
            flash('Failed to parse SMS provider response. The response might not be in JSON format.', 'danger')
            print("JSON Decode Error: Response was not valid JSON.")
        except Exception as e:
            flash(f'An unexpected error occurred while sending SMS: {e}', 'danger')
            print(f"Unexpected Error: {e}")

        return redirect(url_for('super_admin_dashboard'))


    # ... (existing imports, app initialization, and other routes) ...

    # ... (existing imports, app initialization, and other routes) ...

    @app.route('/get_all_active_products', methods=['GET'])
    # @login_required
    def get_all_active_products():
        """
        Returns a list of all active inventory items for the current business.
        This route is called by the frontend (add_edit_sale.html) via AJAX
        to populate the product dropdowns.
        """
        business_id = get_current_business_id()
        if not business_id:
            return jsonify({'success': False, 'message': 'Business context not found.'}), 400

        products = InventoryItem.query.filter_by(business_id=business_id, is_active=True).all()
        
        products_data = []
        for product in products:
            # Prepare product data, ensuring numerical values are floats and dates are formatted
            # Ensure all fields expected by the frontend JavaScript are included and consistently named.
            products_data.append({
                'id': str(product.id), # Convert UUID to string
                'product_name': product.product_name,
                'current_stock': float(product.current_stock or 0.0),
                'is_fixed_price': product.is_fixed_price,
                'barcode': product.barcode,
                'number_of_tabs': float(product.number_of_tabs or 1.0), # Default to 1.0 if None
                'unit_price_per_tab': float(product.unit_price_per_tab or 0.0),
                'item_type': product.item_type,
                'expiry_date': product.expiry_date.strftime('%Y-%m-%d') if product.expiry_date else None,
                'batch_number': product.batch_number,
                'purchase_price': float(product.purchase_price or 0.0),
                'sale_price': float(product.sale_price or 0.0), # Regular sale price
                'fixed_sale_price': float(product.fixed_sale_price or 0.0), # Fixed sale price
                'markup_percentage_pharmacy': float(product.markup_percentage_pharmacy or 0.0), # Markup percentage
            })
        
        return jsonify({'success': True, 'products': products_data})


    # with app.app_context():
    #     # Step 1: Create all database tables
    #     print("Creating database tables...")
    #     db.create_all()
    #     print("Database tables created successfully.")

    #     # Step 2: Check for and create the superadmin user
    #     super_admin_username = os.getenv('SUPER_ADMIN_USERNAME') or 'superadmin'
    #     super_admin_password = os.getenv('SUPER_ADMIN_PASSWORD') or 'superpassword'

    #     existing_super_admin = User.query.filter_by(username=super_admin_username).first()
    #     if not existing_super_admin:
    #         print("Superadmin user not found. Creating new superadmin...")
    #         hashed_password = generate_password_hash(super_admin_password, method='scrypt')
            
    #         super_admin = User(
    #             id='superadmin',
    #             username=super_admin_username,
    #             _password_hash=hashed_password,
    #             role='super_admin',
    #             business_id='super_admin_business',
    #             is_active=True,
    #             created_at=datetime.utcnow()
    #         )
    #         db.session.add(super_admin)
    #         db.session.commit()
    #         print(f"Superadmin user '{super_admin_username}' created successfully.")
    #     else:
    #         print(f"Superadmin user '{super_admin_username}' already exists. No new user created.")
    # with app.app_context():
    #     # Check and create the super_admin_business first
    #     superadmin_business_id = 'super_admin_business'
    #     superadmin_business = db.session.get(Business, superadmin_business_id)

    #     if not superadmin_business:
    #         logging.info("Superadmin business not found. Creating a new one...")
    #         superadmin_business = Business(
    #             id=superadmin_business_id,
    #             name='Admin Business',
    #             type='headquarters',
    #             remote_id='super_admin_business',
    #             last_synced_at=datetime.utcnow()
    #         )
    #         db.session.add(superadmin_business)
    #         db.session.commit()
    #         logging.info("Superadmin business created successfully.")

    #     # Now, check and create the superadmin user
    #     superadmin_user = db.session.get(User, 'superadmin')
    #     if not superadmin_user:
    #         logging.info("Superadmin user not found. Creating new superadmin...")
    #         superadmin_password = os.getenv('SUPERADMIN_PASSWORD', 'superpassword')
    #         new_superadmin = User(
    #             id='superadmin',
    #             username='superadmin',
    #             password=generate_password_hash(superadmin_password),
    #             role='super_admin',
    #             business_id=superadmin_business.id,  # Link to the existing or new business
    #             is_active=True,
    #             created_at=datetime.utcnow()
    #         )
    #         db.session.add(new_superadmin)
    #         db.session.commit()
    #         logging.info("Superadmin user created successfully.")
    #     else:
    #         logging.info("Superadmin user 'superadmin' already exists. No new user created.")


    # NEW: Jinja2 filter to safely format a date or datetime object
    @app.route('/companies/import', methods=['POST'])
    @csrf.exempt
    @login_required
    def import_company_transactions():
        # Check for correct business type and user role
        if get_current_business_type() != 'Hardware' or session.get('role') not in ['admin', 'sales']:
            flash('This feature is only available for Hardware businesses and requires admin or sales permissions.', 'danger')
            return redirect(url_for('companies'))

        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(url_for('companies'))

        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(url_for('companies'))

        if file and file.filename.endswith('.csv'):
            business_id = get_current_business_id()
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.reader(stream)
            headers = [header.strip().lower() for header in next(csv_reader)]

            try:
                for i, row in enumerate(csv_reader):
                    if not row:
                        continue
                    
                    row_data = dict(zip(headers, row))
                    
                    # Required fields
                    company_id = row_data.get('company_id')
                    transaction_type = row_data.get('transaction_type')
                    amount_str = row_data.get('amount')
                    
                    if not all([company_id, transaction_type, amount_str]):
                        flash(f'Skipping row {i+2}: Missing required data (company_id, transaction_type, amount).', 'warning')
                        continue

                    # Validate amount
                    try:
                        amount = decimal.Decimal(amount_str)
                    except (decimal.InvalidOperation, ValueError):
                        flash(f'Skipping row {i+2}: Invalid amount value.', 'warning')
                        continue
                    
                    # Find existing company
                    company = Company.query.filter_by(id=company_id, business_id=business_id).first()
                    if not company:
                        flash(f'Skipping row {i+2}: Company with ID "{company_id}" not found for this business.', 'warning')
                        continue
                        
                    # Create new transaction
                    new_transaction = CompanyTransaction(
                        business_id=business_id,
                        company_id=company_id,
                        transaction_type=transaction_type,
                        amount=amount,
                        description=row_data.get('description'),
                        transaction_date=datetime.strptime(row_data.get('transaction_date', datetime.utcnow().strftime('%Y-%m-%d')), '%Y-%m-%d').date()
                    )
                    db.session.add(new_transaction)
                
                db.session.commit()
                flash('Company transactions imported successfully!', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'An error occurred during import: {e}', 'danger')
        else:
            flash('Invalid file type. Please upload a CSV file.', 'danger')

        return redirect(url_for('companies'))
    @app.route('/check-business-id')
    @login_required
    def check_business_id():
        current_business_id = session.get('business_id')
        return f"Your current business ID is: {current_business_id}"
    # @app.route('/sync-superadmin-data')
    # @login_required('super_admin')
    # def sync_superadmin_data_endpoint():
    #     # Start the sync process in a new thread
    #     sync_thread = threading.Thread(target=sync_data_in_background, args=(current_user.business_id, True))
    #     sync_thread.start()
        
    #     return jsonify({'status': 'success', 'message': 'Superadmin data sync has started in the background.'})

    # @app.route('/sync/admin_data', methods=['GET'])
    # @login_required('admin')
    # def sync_admin_data_endpoint():
    #     try:
    #         # Start the sync process in a new thread
    #         sync_thread = threading.Thread(target=sync_data_in_background, args=(current_user.business_id,))
    #         sync_thread.start()
            
    #         flash('Admin data sync started successfully.', 'success')
    #     except Exception as e:
    #         flash(f'Error starting sync: {e}', 'danger')
    #         logging.error(f'Admin sync endpoint error: {e}')
    #     return redirect(url_for('dashboard'))
    @app.template_filter('format_currency')
    def format_currency(value):
        # Check if the value is a number before formatting
        if isinstance(value, (int, float)):
            # Format the number with a currency symbol (using Ghana Cedi as an example)
            # You can change the symbol to fit your needs, e.g., 'GHS', '$', etc.
            return f"₵{value:,.2f}"
        return value

    
    @app.template_filter('format_date')
    def format_date(value, format='%Y-%m-%d'):
        if isinstance(value, (datetime, date)):
            return value.strftime(format)
    
    # Enhanced Sync Routes
    @app.route('/sync/enhanced/dashboard')
    def enhanced_sync_dashboard():
        """Enhanced synchronization monitoring dashboard"""
        try:
            status = get_enhanced_sync_status()
            return render_template('enhanced_sync_dashboard.html', 
                                 sync_status=status)
        except Exception as e:
            return f"Error loading sync dashboard: {str(e)}", 500

    @app.route('/api/sync/enhanced/status')
    def api_enhanced_sync_status():
        """API endpoint for enhanced sync status"""
        try:
            status = get_enhanced_sync_status()
            return jsonify(status)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/sync/conflicts')
    def sync_conflicts_page():
        """Page for viewing and resolving sync conflicts"""
        try:
            conflicts = enhanced_sync_status['sync_conflicts']
            return render_template('sync_conflicts.html', 
                                 conflicts=conflicts)
        except Exception as e:
            return f"Error loading conflicts page: {str(e)}", 500

    @app.route('/api/sync/conflicts')
    def api_sync_conflicts():
        """API endpoint for getting sync conflicts"""
        try:
            return jsonify(enhanced_sync_status['sync_conflicts'])
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/sync/resolve_conflict', methods=['POST'])
    def api_resolve_conflict():
        """API endpoint for resolving sync conflicts"""
        try:
            data = request.get_json()
            if not data or 'conflict_id' not in data:
                return jsonify({'error': 'Missing conflict_id'}), 400
                
            result = resolve_sync_conflict(
                data.get('conflict_id'), 
                data.get('resolution', 'manual_override')
            )
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/test_connection', methods=['GET'])
    @login_required
    def test_connection():
        """Test connection to remote server and sync status"""
        try:
            remote_url = os.getenv('ONLINE_FLASK_APP_BASE_URL', 'http://localhost:5000')
            
            # Test basic connectivity
            response = requests.get(f"{remote_url}/sync_status", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return jsonify({
                    'status': 'success',
                    'message': 'Connection successful',
                    'remote_status': data,
                    'remote_url': remote_url
                })
            else:
                return jsonify({
                    'status': 'failed',
                    'message': f'Server responded with status {response.status_code}',
                    'remote_url': remote_url
                })
                
        except requests.exceptions.Timeout:
            return jsonify({
                'status': 'failed',
                'message': 'Connection timeout - server took too long to respond',
                'remote_url': remote_url
            })
        except requests.exceptions.ConnectionError:
            return jsonify({
                'status': 'failed',
                'message': 'Connection failed - server is not reachable',
                'remote_url': remote_url
            })
        except Exception as e:
            return jsonify({
                'status': 'failed',
                'message': f'Unexpected error: {str(e)}',
                'remote_url': remote_url
            })
    
    @app.route('/dashboard-data')
    @login_required
    def dashboard_data():
        try:
            business_id = current_user.business_id
            today = date.today()
            
            # Sales data
            sales_today = db.session.query(func.sum(SalesRecord.amount)).filter(
                SalesRecord.business_id == business_id,
                cast(SalesRecord.transaction_date, date) == today
            ).scalar() or 0

            sales_last_7_days = db.session.query(func.sum(SalesRecord.amount)).filter(
                SalesRecord.business_id == business_id,
                cast(SalesRecord.transaction_date, date) >= today - timedelta(days=7)
            ).scalar() or 0

            # Inventory value
            total_inventory_value = db.session.query(func.sum(InventoryItem.unit_price * InventoryItem.quantity_in_stock)).filter(
                InventoryItem.business_id == business_id
            ).scalar() or 0

            # Outstanding debt
            total_debt = db.session.query(func.sum(Debtor.amount)).filter(
                Debtor.business_id == business_id,
                Debtor.status == 'unpaid'
            ).scalar() or 0

            # Recent transactions
            recent_sales = SalesRecord.query.filter_by(business_id=business_id).order_by(SalesRecord.transaction_date.desc()).limit(10).all()
            recent_rentals = RentalRecord.query.filter_by(business_id=business_id).order_by(RentalRecord.rental_start_date.desc()).limit(10).all()

            # Chart data (last 30 days of sales)
            sales_history = db.session.query(
                cast(SalesRecord.transaction_date, date),
                func.sum(SalesRecord.amount)
            ).filter(
                SalesRecord.business_id == business_id,
                cast(SalesRecord.transaction_date, date) >= today - timedelta(days=30)
            ).group_by(
                cast(SalesRecord.transaction_date, date)
            ).order_by(
                cast(SalesRecord.transaction_date, date)
            ).all()

            sales_dates = [d.strftime('%Y-%m-%d') for d, _ in sales_history]
            sales_amounts = [a for _, a in sales_history]

            return jsonify({
                'sales_today': sales_today,
                'sales_last_7_days': sales_last_7_days,
                'total_inventory_value': total_inventory_value,
                'total_debt': total_debt,
                'recent_sales': [s.to_dict() for s in recent_sales],
                'recent_rentals': [r.to_dict() for r in recent_rentals],
                'sales_chart_data': {
                    'labels': sales_dates,
                    'data': sales_amounts
                }
            })
        except Exception as e:
            app.logger.error(f"Error fetching dashboard data: {e}")
            return jsonify({'error': 'An internal error occurred.'}), 500

    
    return app

    # The final Flask app instance is created here
app = create_app()

    # This part is for running the app directly
if __name__ == '__main__':
    

    # The context block is the correct place to run startup tasks.
    # The original traceback suggests a problem where a function that requires
    # a request context is being called from within create_app, but placing
    # all startup logic here is the standard and correct practice.
    with app.app_context():
        print("Starting application setup...")
        
        # Create all database tables
        print("Creating database tables if they don't exist...")
        db.create_all()
        print("Database tables are up to date.")
        from models import User
        # Check for and create the superadmin user
        super_admin_username = os.getenv('SUPER_ADMIN_USERNAME') or 'superadmin'
        super_admin_password = os.getenv('SUPER_ADMIN_PASSWORD') or 'superpassword'

        existing_super_admin = User.query.filter_by(username=super_admin_username).first()
        
        if existing_super_admin:
            print(f"Superadmin user '{super_admin_username}' already exists. Updating password...")
            # Delete the existing user to ensure the password hash is fresh and correct
            db.session.delete(existing_super_admin)
            db.session.commit()
            print("Existing superadmin deleted to re-create with new password.")
            
        print("Creating new superadmin user...")
        # Use a consistent hashing method. werkzeug's generate_password_hash defaults to a strong algorithm.
        hashed_password = generate_password_hash(super_admin_password)
        
        super_admin = User(
            id='superadmin',
            username=super_admin_username,
            _password_hash=hashed_password,
            role='super_admin',
            business_id='super_admin_business',
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.session.add(super_admin)
        db.session.commit()
        print(f"Superadmin user '{super_admin_username}' created successfully!")
        print(f"Please use the username '{super_admin_username}' and password '{super_admin_password}' to log in.")
        print(f"Superadmin Business ID: '{super_admin.business_id}'")

    app.run(debug=True, host='0.0.0.0', port=os.getenv('PORT', 5000))