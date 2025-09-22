from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort, Response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, current_user, login_required, UserMixin
from functools import wraps
from datetime import datetime, date, timedelta
import os
import csv
import sys
import uuid
import pandas as pd
import requests
import json
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Index, create_engine, text, func, cast, or_
from dotenv import load_dotenv
from flask import current_app
from extensions import db, migrate
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

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# --- Global Configuration ---
ARKESEL_API_KEY = os.getenv('ARKESEL_API_KEY')
ARKESEL_SENDER_ID = os.getenv('ARKESEL_SENDER_ID', 'YourSenderID')
ARKESEL_SMS_URL = "https://sms.arkesel.com/sms/api"
REMOTE_SERVER_URL = os.getenv('ONLINE_FLASK_APP_BASE_URL', 'http://localhost:5000')
ENTERPRISE_NAME = os.getenv('ENTERPRISE_NAME', 'Global Business App')
PHARMACY_LOCATION = os.getenv('PHARMACY_LOCATION', 'Your Town, Your Region')
PHARMACY_ADDRESS = os.getenv('PHARMACY_ADDRESS', '123 Business St')
PHARMACY_CONTACT = os.getenv('PHARMACY_CONTACT', '+1234567890')
ADMIN_PHONE_NUMBER = os.getenv('ADMIN_PHONE_NUMBER', '')

# Determine template folder path
if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'templates')
    db_path = os.path.join(sys._MEIPASS, 'instance', 'instance_data.db')
else:
    template_folder = 'templates'
    db_path = os.path.join('instance', 'instance_data.db')

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
    
    conflicts = []
    
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
            conflict['status'] = 'resolved'
            conflict['resolution'] = resolution
            conflict['resolved_at'] = datetime.now().isoformat()
            
            enhanced_sync_status['sync_conflicts'].pop(i)
            
            return {'success': True, 'message': 'Conflict resolved successfully'}
    
    return {'success': False, 'message': 'Conflict not found'}

def get_enhanced_sync_status():
    """Get current enhanced synchronization status"""
    from datetime import datetime
    
    check_sync_conflicts()
    
    return {
        'last_sync': enhanced_sync_status.get('last_sync') or datetime.now().isoformat(),
        'sync_health': enhanced_sync_status['sync_health'],
        'sync_running': enhanced_sync_status['sync_running'],
        'conflicts_count': len(enhanced_sync_status['sync_conflicts']),
        'conflicts': enhanced_sync_status['sync_conflicts'],
        'status_updated': datetime.now().isoformat()
    }

def create_app():
    """Application factory function"""
    app = Flask(__name__, template_folder=template_folder)
    
    # --- Enhanced Configuration for Production ---
    
    # Database configuration with better error handling
    DB_TYPE = os.getenv('DB_TYPE', 'postgresql')
    
    if DB_TYPE == 'sqlite':
        if not os.path.exists(app.instance_path):
            os.makedirs(app.instance_path)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'instance_data.db')
        print(f"Using SQLite database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    else:
        # Enhanced PostgreSQL configuration for Render
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            database_url = 'postgresql://bisinessdb_user:QceRMwRe2FtjhPk8iMLCIKB3j3s4KmhI@dpg-d1olvgbuibrs73cum700-a.oregon-postgres.render.com/bisinessdb'
        
        # Fix for modern PostgreSQL drivers
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        
        # Add psycopg2 for better compatibility
        if 'psycopg2' not in database_url:
            database_url = database_url.replace('postgresql://', 'postgresql+psycopg2://')
        
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        print(f"Using PostgreSQL database: {database_url[:60]}...")

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'your_super_secret_key_here_change_in_production')
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_recycle': 300,
        'pool_pre_ping': True,
        'pool_timeout': 20,
        'max_overflow': 0
    }
    
    # Environment-specific configuration
    if os.getenv('RENDER') or os.getenv('FLASK_ENV') == 'production':
        app.config['ENV'] = 'production'
        app.config['DEBUG'] = False
        app.config['TESTING'] = False
    else:
        app.config['ENV'] = 'development'
        app.config['DEBUG'] = True
        app.config['TESTING'] = False

    # Initialize extensions with app
    try:
        db.init_app(app)
        migrate.init_app(app, db)
        print("Database and migration initialized successfully")
    except Exception as e:
        print(f"Error initializing database: {e}")
        
    csrf = CSRFProtect(app)
    
    # Configure login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message_category = 'info'
    
    # Import models after extensions are initialized
    from models import (User, Business, SalesRecord, InventoryItem, HirableItem, 
                       RentalRecord, Creditor, Debtor, CompanyTransaction, 
                       FutureOrder, Company, Customer, ReturnRecord)
    
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, user_id)

    # Helper functions
    def login_required(f):
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

    def super_admin_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get('role') != 'super_admin':
                flash('Access denied: Super Admin only.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function

    def api_key_required(f):
        """Decorator to check for a valid API key in the request header."""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            api_key = request.headers.get('X-API-Key')
            if not api_key or api_key != os.getenv('REMOTE_ADMIN_API_KEY'):
                return jsonify({'message': 'API Key is missing or invalid.'}), 401
            return f(*args, **kwargs)
        return decorated_function

    def permission_required(roles):
        def wrapper(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                if session.get('role') not in roles:
                    flash(f'Access denied. Required roles: {", ".join(roles)}.', 'danger')
                    return redirect(url_for('dashboard'))
                return f(*args, **kwargs)
            return decorated_function
        return wrapper

    def roles_required(*roles):
        """Decorator to check if the current user has at least one of the specified roles."""
        def wrapper(fn):
            @wraps(fn)
            def decorated_view(*args, **kwargs):
                if not current_user.is_authenticated:
                    return current_app.login_manager.unauthorized()
                
                if not current_user.role in roles:
                    abort(403)
                return fn(*args, **kwargs)
            return decorated_view
        return wrapper

    @app.before_request
    def handle_authentication_and_authorization():
        """Handle authentication for all routes except public ones."""
        public_endpoints = {
            'login', 'static', 'sync_status', 'get_users_for_sync',
            'get_inventory_for_sync', 'api_upsert_inventory', 'api_record_sales',
            'enhanced_sync_dashboard', 'api_enhanced_sync_status', 'sync_conflicts_page',
            'api_sync_conflicts', 'api_resolve_conflict', 'test_connection',
            'health_check', 'api_businesses', 'api_get_businesses', 'api_get_inventory',
            'api_get_users'
        }

        if request.endpoint in public_endpoints:
            return

        # For all other routes, check if a user is logged in
        if 'username' not in session:
            return redirect(url_for('login'))

    def get_current_business_id():
        return session.get('business_id')

    def get_current_business_type():
        business_id = session.get('business_id')
        if business_id:
            business = Business.query.get(business_id)
            if business:
                return business.type
        return None

    # Serialization helpers
    def safe_convert(value, converter, default):
        """Safely converts a value using a specified converter."""
        try:
            return converter(value) if value is not None else default
        except (TypeError, ValueError):
            return default

    def safe_currency_print(amount, label="Amount"):
        """Print currency safely with fallback for encoding issues."""
        try:
            return f"{label}: GH₵{amount:.2f}"
        except UnicodeEncodeError:
            return f"{label}: GHS{amount:.2f}"

    def serialize_inventory_item(item):
        """Serializes an InventoryItem object to a dictionary for JSON conversion."""
        try:
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

            # Handle dates defensively
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
                'last_updated': last_updated_iso,
                'batch_number': safe_convert(_batch_number, str, 'N/A'),
                'number_of_tabs': safe_convert(_number_of_tabs, float, 1.0),
                'unit_price_per_tab': safe_convert(_unit_price_per_tab, float, 0.0),
                'item_type': safe_convert(_item_type, str, 'N/A'),
                'expiry_date': expiry_date_iso,
                'is_fixed_price': safe_convert(_is_fixed_price, bool, False),
                'fixed_sale_price': safe_convert(_fixed_sale_price, float, 0.0),
                'is_active': safe_convert(_is_active, bool, False),
                'barcode': safe_convert(_barcode, str, '')
            }
        except Exception as e:
            error_id = getattr(item, 'id', 'UNKNOWN_ID_ERROR')
            error_product_name = getattr(item, 'product_name', 'UNKNOWN_PRODUCT_NAME_ERROR')
            logging.error(f"Serialization failed for item '{error_product_name}' (ID: {error_id}): {str(e)}")
            
            return {
                "id": "serialization_error_" + str(error_id)[:8],
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

    def calculate_company_balance_details(company_id):
        """Calculates the balance, total debtors, and total creditors for a single company."""
        transactions = CompanyTransaction.query.filter_by(company_id=company_id).all()
        current_balance = 0.0

        for transaction in transactions:
            if transaction.transaction_type == 'Debit':
                current_balance += transaction.amount
            elif transaction.transaction_type == 'Credit':
                current_balance -= transaction.amount

        total_debtors = 0.0
        total_creditors = 0.0

        if current_balance > 0:
            total_debtors = current_balance
        elif current_balance < 0:
            total_creditors = abs(current_balance)

        return {
            'balance': current_balance,
            'total_debtors': total_debtors,
            'total_creditors': total_creditors
        }

    # Health check route for deployment monitoring
    @app.route('/health')
    @app.route('/health_check')
    def health_check():
        """Health check endpoint for deployment monitoring."""
        try:
            # Test database connection
            db.session.execute(text('SELECT 1'))
            db.session.commit()
            
            return jsonify({
                'status': 'healthy',
                'timestamp': datetime.utcnow().isoformat(),
                'database': 'connected',
                'version': '1.0.0'
            }), 200
        except Exception as e:
            logging.error(f"Health check failed: {str(e)}")
            return jsonify({
                'status': 'unhealthy',
                'timestamp': datetime.utcnow().isoformat(),
                'database': 'disconnected',
                'error': str(e)
            }), 500

    # Routes
    @app.route('/')
    def home():
        """Redirect to login if not authenticated, otherwise to dashboard."""
        if 'username' in session:
            return redirect(url_for('dashboard'))
        return redirect(url_for('login'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """User login route."""
        if request.method == 'POST':
            username = request.form['username'].strip()
            password = request.form['password'].strip()
            
            if not username or not password:
                flash('Please provide both username and password.', 'danger')
                return render_template('login.html')
            
            try:
                user = User.query.filter_by(username=username).first()
                
                if user and user.check_password(password):
                    if not user.is_active:
                        flash('Your account has been deactivated. Please contact an administrator.', 'danger')
                        return render_template('login.html')
                    
                    # Set session variables
                    session['username'] = user.username
                    session['user_id'] = user.id
                    session['role'] = user.role
                    session['business_id'] = user.business_id
                    
                    # Get business info if available
                    if user.business_id:
                        business = Business.query.get(user.business_id)
                        if business:
                            session['business_type'] = business.type
                            session['business_info'] = {
                                'name': business.name,
                                'location': business.location,
                                'address': business.address,
                                'contact': business.contact
                            }
                    
                    flash(f'Welcome back, {user.username}!', 'success')
                    
                    # Redirect based on role
                    if user.role == 'super_admin':
                        return redirect(url_for('super_admin_dashboard'))
                    else:
                        return redirect(url_for('dashboard'))
                else:
                    flash('Invalid username or password.', 'danger')
                    
            except Exception as e:
                logging.error(f"Login error: {str(e)}")
                flash('An error occurred during login. Please try again.', 'danger')
        
        return render_template('login.html')

    @app.route('/logout')
    def logout():
        """User logout route."""
        username = session.get('username', 'User')
        session.clear()
        flash(f'Goodbye, {username}! You have been logged out.', 'info')
        return redirect(url_for('login'))

    @app.route('/dashboard')
    @login_required
    def dashboard():
        """Main dashboard route."""
        try:
            user_role = session.get('role')
            business_id = session.get('business_id')
            business_type = session.get('business_type')
            
            # Get business info
            business_info = session.get('business_info', {})
            
            # Initialize dashboard data
            dashboard_data = {
                'user_role': user_role,
                'business_type': business_type,
                'business_info': business_info,
                'current_year': datetime.now().year
            }
            
            if business_id:
                # Get basic statistics for the business
                try:
                    total_inventory = InventoryItem.query.filter_by(
                        business_id=business_id, is_active=True
                    ).count()
                    
                    low_stock_items = InventoryItem.query.filter(
                        InventoryItem.business_id == business_id,
                        InventoryItem.is_active == True,
                        InventoryItem.current_stock <= 10
                    ).count()
                    
                    # Recent sales (last 30 days)
                    thirty_days_ago = datetime.now() - timedelta(days=30)
                    recent_sales = SalesRecord.query.filter(
                        SalesRecord.business_id == business_id,
                        SalesRecord.sale_date >= thirty_days_ago
                    ).count()
                    
                    dashboard_data.update({
                        'total_inventory': total_inventory,
                        'low_stock_items': low_stock_items,
                        'recent_sales': recent_sales
                    })
                    
                except Exception as e:
                    logging.error(f"Error fetching dashboard statistics: {str(e)}")
                    dashboard_data.update({
                        'total_inventory': 0,
                        'low_stock_items': 0,
                        'recent_sales': 0
                    })
            
            return render_template('dashboard.html', **dashboard_data)
            
        except Exception as e:
            logging.error(f"Dashboard error: {str(e)}")
            flash('An error occurred loading the dashboard.', 'danger')
            return render_template('dashboard.html', 
                                 user_role=session.get('role'),
                                 current_year=datetime.now().year)

    @app.route('/super_admin_dashboard')
    @super_admin_required
    def super_admin_dashboard():
        """Super admin dashboard route."""
        try:
            # Get system statistics
            total_businesses = Business.query.count()
            active_businesses = Business.query.filter_by(is_active=True).count()
            total_users = User.query.count()
            active_users = User.query.filter_by(is_active=True).count()
            
            dashboard_data = {
                'total_businesses': total_businesses,
                'active_businesses': active_businesses,
                'total_users': total_users,
                'active_users': active_users,
                'user_role': session.get('role'),
                'current_year': datetime.now().year
            }
            
            return render_template('super_admin_dashboard.html', **dashboard_data)
            
        except Exception as e:
            logging.error(f"Super admin dashboard error: {str(e)}")
            flash('An error occurred loading the super admin dashboard.', 'danger')
            return render_template('super_admin_dashboard.html',
                                 user_role=session.get('role'),
                                 current_year=datetime.now().year)

    @app.route('/business_selection', methods=['GET', 'POST'])
    @login_required
    def business_selection():
        """Business selection route for users with access to multiple businesses."""
        try:
            user_id = session.get('user_id')
            user_role = session.get('role')
            
            if user_role == 'super_admin':
                businesses = Business.query.filter_by(is_active=True).all()
            else:
                # For regular users, show only their assigned business
                user = User.query.get(user_id)
                if user and user.business_id:
                    businesses = [Business.query.get(user.business_id)]
                else:
                    businesses = []
            
            if request.method == 'POST':
                selected_business_id = request.form.get('business_id')
                if selected_business_id:
                    business = Business.query.get(selected_business_id)
                    if business:
                        session['business_id'] = business.id
                        session['business_type'] = business.type
                        session['business_info'] = {
                            'name': business.name,
                            'location': business.location,
                            'address': business.address,
                            'contact': business.contact
                        }
                        flash(f'Selected business: {business.name}', 'success')
                        return redirect(url_for('dashboard'))
                
                flash('Please select a valid business.', 'danger')
            
            return render_template('business_selection.html', 
                                 businesses=businesses,
                                 user_role=user_role,
                                 current_year=datetime.now().year)
                                 
        except Exception as e:
            logging.error(f"Business selection error: {str(e)}")
            flash('An error occurred during business selection.', 'danger')
            return redirect(url_for('logout'))

    # API Routes for synchronization
    @app.route('/api/v1/businesses', methods=['GET'])
    @api_key_required
    def api_get_businesses():
        """API endpoint to get all businesses."""
        try:
            businesses = Business.query.all()
            businesses_data = []
            
            for business in businesses:
                business_dict = {
                    'id': str(business.id),
                    'name': business.name,
                    'type': business.type,
                    'address': business.address,
                    'location': business.location,
                    'contact': business.contact,
                    'is_active': business.is_active,
                    'last_updated': business.last_updated.isoformat() if business.last_updated else None
                }
                businesses_data.append(business_dict)
            
            return jsonify(businesses_data), 200
            
        except Exception as e:
            logging.error(f"API get businesses error: {str(e)}")
            return jsonify({'error': 'Failed to fetch businesses'}), 500

    @app.route('/api/businesses')
    def api_businesses():
        """API endpoint to expose all business data for synchronization."""
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
                    'email': getattr(business, 'email', ''),
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

    @app.route('/api/v1/inventory', methods=['GET'])
    @api_key_required  
    def api_get_inventory():
        """API endpoint to get inventory items."""
        try:
            business_id = request.args.get('business_id')
            
            if business_id:
                items = InventoryItem.query.filter_by(business_id=business_id).all()
            else:
                items = InventoryItem.query.all()
            
            inventory_data = []
            for item in items:
                item_dict = {
                    'id': str(item.id),
                    'business_id': str(item.business_id),
                    'product_name': item.product_name,
                    'category': item.category,
                    'purchase_price': float(item.purchase_price),
                    'sale_price': float(item.sale_price),
                    'current_stock': float(item.current_stock),
                    'last_updated': item.last_updated.isoformat() if item.last_updated else None,
                    'batch_number': item.batch_number,
                    'number_of_tabs': int(item.number_of_tabs),
                    'unit_price_per_tab': float(item.unit_price_per_tab),
                    'item_type': item.item_type,
                    'expiry_date': item.expiry_date.isoformat() if item.expiry_date else None,
                    'is_fixed_price': item.is_fixed_price,
                    'fixed_sale_price': float(item.fixed_sale_price),
                    'is_active': item.is_active
                }
                inventory_data.append(item_dict)
            
            return jsonify(inventory_data), 200
            
        except Exception as e:
            logging.error(f"API get inventory error: {str(e)}")
            return jsonify({'error': 'Failed to fetch inventory'}), 500

    @app.route('/api/v1/inventory/<business_id>', methods=['GET'])
    @api_key_required
    def api_get_business_inventory(business_id):
        """API endpoint to get inventory for a specific business."""
        try:
            items = InventoryItem.query.filter_by(business_id=business_id).all()
            inventory_data = [serialize_inventory_item_api(item) for item in items]
            return jsonify(inventory_data), 200
        except Exception as e:
            logging.error(f"API get business inventory error: {str(e)}")
            return jsonify({'error': 'Failed to fetch inventory for business'}), 500

    @app.route('/api/v1/users', methods=['GET'])
    @api_key_required
    def api_get_users():
        """API endpoint to get users."""
        try:
            business_id = request.args.get('business_id')
            
            if business_id:
                users = User.query.filter_by(business_id=business_id).all()
            else:
                users = User.query.all()
            
            users_data = []
            for user in users:
                user_dict = {
                    'id': str(user.id),
                    'username': user.username,
                    'role': user.role,
                    'business_id': str(user.business_id) if user.business_id else None,
                    'is_active': user.is_active,
                    'created_at': user.created_at.isoformat() if user.created_at else None,
                    'password_hash': user._password_hash
                }
                users_data.append(user_dict)
            
            return jsonify(users_data), 200
            
        except Exception as e:
            logging.error(f"API get users error: {str(e)}")
            return jsonify({'error': 'Failed to fetch users'}), 500

    @app.route('/api/v1/business/<string:business_id>', methods=['GET'])
    @api_key_required
    def api_get_business(business_id):
        """API endpoint to get a specific business."""
        try:
            business = Business.query.get_or_404(business_id)
            business_data = serialize_business(business)
            return jsonify(business_data), 200
        except Exception as e:
            logging.error(f"API get business error: {str(e)}")
            return jsonify({'error': 'Failed to fetch business'}), 500

    @app.route('/api/v1/businesses/<string:business_id>/inventory', methods=['GET'])
    @api_key_required
    def api_get_business_inventory_alt(business_id):
        """Alternative API endpoint to get inventory for a specific business."""
        try:
            items = InventoryItem.query.filter_by(business_id=business_id).all()
            inventory_data = [serialize_inventory_item_api(item) for item in items]
            return jsonify(inventory_data), 200
        except Exception as e:
            logging.error(f"API get business inventory (alt) error: {str(e)}")
            return jsonify({'error': 'Failed to fetch inventory for business'}), 500

    @app.route('/api/v1/sales', methods=['POST'])
    @api_key_required
    def api_record_sales():
        """API endpoint to record sales from remote systems."""
        try:
            sales_data = request.get_json()
            
            if not isinstance(sales_data, list):
                sales_data = [sales_data]
            
            recorded_sales = []
            
            for sale_record in sales_data:
                # Create new sales record
                new_sale = SalesRecord(
                    id=sale_record.get('id', str(uuid.uuid4())),
                    business_id=sale_record['business_id'],
                    product_id=sale_record['product_id'],
                    product_name=sale_record['product_name'],
                    quantity_sold=sale_record['quantity_sold'],
                    sale_unit_type=sale_record.get('sale_unit_type'),
                    price_at_time_per_unit_sold=sale_record['price_at_time_per_unit_sold'],
                    total_amount=sale_record['total_amount'],
                    sale_date=datetime.fromisoformat(sale_record['sale_date']),
                    customer_phone=sale_record.get('customer_phone'),
                    sales_person_name=sale_record.get('sales_person_name'),
                    transaction_id=sale_record.get('transaction_id', str(uuid.uuid4()))
                )
                
                db.session.add(new_sale)
                recorded_sales.append(serialize_sale_record_api(new_sale))
            
            db.session.commit()
            
            return jsonify({
                'message': 'Sales records synchronized successfully.',
                'records_processed': len(recorded_sales),
                'sales': recorded_sales
            }), 201
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"API record sales error: {str(e)}")
            return jsonify({'error': 'Failed to record sales'}), 500

    @app.route('/api/v1/inventory', methods=['POST'])
    @api_key_required
    def api_upsert_inventory():
        """API endpoint to upsert inventory items."""
        try:
            inventory_data = request.get_json()
            
            if not isinstance(inventory_data, list):
                inventory_data = [inventory_data]
            
            processed_items = []
            
            for item_data in inventory_data:
                existing_item = InventoryItem.query.filter_by(
                    id=item_data.get('id')
                ).first()
                
                if existing_item:
                    # Update existing item
                    for key, value in item_data.items():
                        if hasattr(existing_item, key):
                            if key in ['last_updated', 'expiry_date'] and value:
                                setattr(existing_item, key, datetime.fromisoformat(value))
                            else:
                                setattr(existing_item, key, value)
                    processed_items.append(serialize_inventory_item_api(existing_item))
                else:
                    # Create new item
                    new_item = InventoryItem(**item_data)
                    if item_data.get('last_updated'):
                        new_item.last_updated = datetime.fromisoformat(item_data['last_updated'])
                    if item_data.get('expiry_date'):
                        new_item.expiry_date = datetime.fromisoformat(item_data['expiry_date']).date()
                    
                    db.session.add(new_item)
                    processed_items.append(serialize_inventory_item_api(new_item))
            
            db.session.commit()
            
            return jsonify({
                'message': 'Inventory synchronized successfully.',
                'items_processed': len(processed_items),
                'items': processed_items
            }), 200
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"API upsert inventory error: {str(e)}")
            return jsonify({'error': 'Failed to synchronize inventory'}), 500

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('errors/403.html'), 403

    # Initialize database tables
    with app.app_context():
        try:
            db.create_all()
            logging.info("Database tables created successfully")
        except Exception as e:
            logging.error(f"Error creating database tables: {str(e)}")

    return app

# Create the Flask application
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    if os.getenv('RENDER') or os.getenv('FLASK_ENV') == 'production':
        # Production settings for Render
        app.run(host='0.0.0.0', port=port, debug=False)
    else:
        # Development settings
        app.run(host='127.0.0.1', port=port, debug=True)